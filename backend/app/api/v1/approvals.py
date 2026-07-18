"""POST/GET /v1/approvals — human-in-the-loop queue for high-risk actions.

Plan.md: "high-risk actions always require human approval." Anything a connector
would write, or any critical-severity auto-escalation, is created here as
status='pending' and only executed after an authorized reviewer approves it.
Approving does not itself execute the action in this cut — it flips the DB
status and returns the payload for the caller (agent/connector) to act on next,
keeping the actual execution step explicit and auditable.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user, get_db_user
from app.db.session import get_db
from app.db.models import ApprovalRequest

router = APIRouter()

# Roles permitted to approve/reject high-risk actions (Plan.md role-based access:
# finance teams / auditors / compliance officers / CFOs). Finance analysts can
# *request*, but only compliance_officer/cfo/auditor can *approve*.
APPROVER_ROLES = {"compliance_officer", "cfo", "auditor", "admin"}


class CreateApprovalRequest(BaseModel):
    action_type: str
    connector: Optional[str] = None
    risk_level: str = Field("high", pattern="^(medium|high|critical)$")
    payload: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None
    assessment_id: Optional[str] = None


class ReviewRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None


def _safe_uuid(v):
    try:
        return uuid.UUID(str(v)) if v else None
    except Exception:
        return None


@router.post("/approvals")
async def create_approval(req: CreateApprovalRequest, user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    """Stage a high-risk action for human review instead of executing it directly."""
    approval = ApprovalRequest(
        requested_by_user_id=_safe_uuid(user["db_id"]),
        assessment_id=_safe_uuid(req.assessment_id),
        action_type=req.action_type,
        connector=req.connector,
        risk_level=req.risk_level,
        payload=req.payload,
        reason=req.reason,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return {"id": str(approval.id), "status": approval.status}


@router.get("/approvals")
async def list_approvals(status: Optional[str] = "pending", user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    query = select(ApprovalRequest).order_by(desc(ApprovalRequest.created_at)).limit(100)
    if status:
        query = query.where(ApprovalRequest.status == status)
    # Requesters may only see their own actions. Reviewers see the team queue;
    # organization scoping is added with the tenancy migration.
    if user.get("role") not in APPROVER_ROLES:
        query = query.where(ApprovalRequest.requested_by_user_id == _safe_uuid(user["db_id"]))
    res = await db.execute(query)
    rows = res.scalars().all()
    return {
        "total": len(rows),
        "approvals": [
            {
                "id": str(r.id), "action_type": r.action_type, "connector": r.connector,
                "risk_level": r.risk_level, "reason": r.reason, "status": r.status,
                "payload": r.payload, "created_at": r.created_at,
            }
            for r in rows
        ],
    }


@router.post("/approvals/{approval_id}/review")
async def review_approval(approval_id: str, req: ReviewRequest, user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    role = user.get("role", "viewer")
    if role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail=f"Role '{role}' cannot approve high-risk actions. Requires one of {sorted(APPROVER_ROLES)}.")

    aid = _safe_uuid(approval_id)
    res = await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == aid))
    approval = res.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Already {approval.status}")

    from datetime import datetime
    approval.status = "approved" if req.decision == "approve" else "rejected"
    approval.reviewed_by_user_id = _safe_uuid(user["db_id"])
    approval.reviewer_comment = req.comment
    approval.reviewed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(approval)

    return {"id": str(approval.id), "status": approval.status, "payload": approval.payload if approval.status == "approved" else None}
