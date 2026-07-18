"""POST /v1/workflows — unified workflow tracker & dispatcher (tasks.md §9).

`entity_assessment` / `full_triage` run entirely through this endpoint (JSON body,
no file upload) using the same ML pipeline as /v1/compliance/assess. `invoice` /
`transaction_batch` / `vendor_onboarding` / `policy_review` require multipart file
uploads and already have dedicated endpoints (/v1/invoices/upload, /v1/transactions/ingest,
/v1/vendors/onboard) — this router still creates the tracking WorkflowRun row for
those types when called with `run_llm_agents=false` style dry-run params, but the
actual file-bearing work happens at the dedicated endpoint. Posting one of those
types here without a file returns HTTP 400 pointing at the right endpoint, rather
than silently no-opping.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_user
from app.db.session import get_db
from app.db.models import WorkflowRun
from app.ml.pipeline import run_full_assessment

log = structlog.get_logger()
router = APIRouter()


def _parse_user_uuid(user: dict) -> uuid.UUID:
    """Safely resolve a DB UUID for the workflow owner.

    Preference order:
    1. ``db_id`` (already a UUID string from get_db_user)
    2. ``id`` if it happens to be UUID-parseable
    3. Deterministic name-UUID derived from the Clerk ID string
       (ensures inserts never fail for non-UUID Clerk IDs like ``user_abc123``)
    """
    raw = user.get("db_id") or user.get("id", "")
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        # Fall back to a deterministic UUID5 so every Clerk ID maps consistently
        return uuid.uuid5(uuid.NAMESPACE_OID, str(raw))

_FILE_BASED_TYPES = {
    "invoice": "/v1/invoices/upload",
    "transaction_batch": "/v1/transactions/ingest",
    "vendor_onboarding": "/v1/vendors/onboard",
    "policy_review": "/v1/policies/upload",
}


class WorkflowType(str, Enum):
    invoice = "invoice"
    transaction_batch = "transaction_batch"
    vendor_onboarding = "vendor_onboarding"
    policy_review = "policy_review"
    entity_assessment = "entity_assessment"
    full_triage = "full_triage"


class WorkflowContext(BaseModel):
    features: Dict[str, float] = Field(default_factory=dict)
    detected_flags: List[str] = Field(default_factory=list)
    sector: Optional[str] = None
    business_name: Optional[str] = None


class WorkflowRequest(BaseModel):
    workflow_type: WorkflowType
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    run_llm_agents: bool = True


class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    awaiting_approval = "awaiting_approval"


class WorkflowResponse(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str
    risk_tier: Optional[str] = None
    requires_approval: bool = False
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class WorkflowListResponse(BaseModel):
    total: int
    workflows: List[WorkflowResponse]


def _to_response(run: WorkflowRun, result: Optional[Dict[str, Any]] = None) -> WorkflowResponse:
    return WorkflowResponse(
        workflow_id=str(run.id),
        workflow_type=run.workflow_type,
        status=run.status,
        risk_tier=run.risk_tier,
        requires_approval=run.requires_approval,
        result=result,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(
    req: WorkflowRequest,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    user_id = _parse_user_uuid(user)

    if req.workflow_type.value in _FILE_BASED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"workflow_type='{req.workflow_type.value}' requires a file upload — "
                f"POST to {_FILE_BASED_TYPES[req.workflow_type.value]} directly instead. "
                f"This endpoint handles JSON-only workflow types: entity_assessment, full_triage."
            ),
        )

    run = WorkflowRun(user_id=user_id, workflow_type=req.workflow_type.value, status="running")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    try:
        result = run_full_assessment(
            req.context.features,
            detected_flags=req.context.detected_flags,
            sector=req.context.sector,
            use_llm=req.run_llm_agents,
        )
        run.risk_tier = result["risk_tier"]
        run.requires_approval = result.get("auto_escalated", False) or result["risk_tier"] == "critical"
        run.status = "awaiting_approval" if run.requires_approval else "completed"
        run.completed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(run)
        return _to_response(run, result)
    except Exception as exc:
        log.error("workflow.execution_failed", workflow_id=str(run.id), error=str(exc))
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {exc}")


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, user=Depends(get_db_user), db: AsyncSession = Depends(get_db)) -> WorkflowResponse:
    try:
        wid = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workflow_id")

    res = await db.execute(select(WorkflowRun).where(WorkflowRun.id == wid))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _to_response(run)


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    workflow_type: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowListResponse:
    user_id = _parse_user_uuid(user)
    stmt = select(WorkflowRun).where(WorkflowRun.user_id == user_id)
    if workflow_type:
        stmt = stmt.where(WorkflowRun.workflow_type == workflow_type)
    stmt = stmt.order_by(desc(WorkflowRun.created_at)).limit(limit)

    res = await db.execute(stmt)
    runs = res.scalars().all()
    return WorkflowListResponse(total=len(runs), workflows=[_to_response(r) for r in runs])
