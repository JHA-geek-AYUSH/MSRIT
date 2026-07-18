from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.core.security import current_user, get_db_user
from app.core.pii_redaction import redact_user_input
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import ApprovalRequest, ComplianceTriageRun

from app.agents.transaction_agent import TransactionAgent
from app.agents.onboarding_agent import OnboardingAgent
from app.agents.regulatory_agent import RegulatoryAgent
from app.agents.financial_risk_agent import FinancialRiskAgent
from app.agents.report_agent import ReportAgent

import structlog

log = structlog.get_logger()
router = APIRouter()


# ─────────────────────────────────── Schemas ──────────────────────────────────

class ComplianceRequest(BaseModel):
    """Request body for compliance triage."""
    description: str = Field(..., min_length=10, description="Transaction, onboarding, or financial record description")
    mode: str = Field(
        "full",
        pattern="^(full|transaction|onboarding|regulatory|financial_risk)$",
        description="Which compliance modules to run",
    )
    documents: List[Dict[str, Any]] = Field(default_factory=list, description="Optional parsed document payloads")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context (entity type, jurisdiction, etc.)")


class RiskDomain(BaseModel):
    name: str
    rating: str           # high | medium | low
    summary: str
    confidence: float


class ComplianceResponse(BaseModel):
    run_id: UUID
    overall_rating: str   # high | medium | low
    domains: List[RiskDomain]
    full_report: str
    recommendations: List[str]
    requires_str: bool    # Suspicious Transaction Report
    requires_edd: bool    # Enhanced Due Diligence


# ─────────────────────────────────── Helpers ──────────────────────────────────

def _overall_rating(domains: List[RiskDomain]) -> str:
    """Overall = highest severity across all domains."""
    score_map = {"high": 3, "medium": 2, "low": 1}
    if not domains:
        return "low"
    # Weight by confidence too — high-confidence medium > low-confidence high
    weighted = [(score_map.get(d.rating, 1) * (0.5 + d.confidence * 0.5)) for d in domains]
    max_score = max(weighted)
    if max_score >= 2.4:
        return "high"
    elif max_score >= 1.5:
        return "medium"
    return "low"


def _extract_recommendations(report_text: str) -> List[str]:
    """Pull out numbered action items from report text."""
    import re
    recs = re.findall(r"^\s*\d+\.\s+(.+)", report_text, re.MULTILINE)
    return [r.strip() for r in recs[:10]]


# ─────────────────────────────────── Endpoints ────────────────────────────────

@router.post("/compliance/triage", response_model=ComplianceResponse)
async def compliance_triage(
    req: ComplianceRequest,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run multi-agent compliance & risk triage on a financial record / description.
    Returns domain-level risk ratings and a compliance-ready summary report.
    """
    run_id = uuid4()
    log.info("compliance.triage.start", user_id=user["id"], mode=req.mode, run_id=str(run_id))

    # PII redaction before any LLM call
    pii_result = redact_user_input(req.description, user["id"], mode="placeholder")
    clean_text = pii_result["redacted_text"]

    triage_run = ComplianceTriageRun(
        id=run_id,
        user_id=UUID(user["db_id"]),
        mode=req.mode,
        status="running",
        redacted_description=clean_text,
        context_json=req.context or {},
    )
    db.add(triage_run)
    await db.commit()

    docs = req.documents or []
    packs: List[Dict[str, Any]] = []   # No vector retrieval for compliance triage (doc-first)

    # ── Select agents based on mode ──────────────────────────────────────────
    agent_map: Dict[str, Any] = {}

    if req.mode in ("full", "transaction"):
        agent_map["transaction"] = TransactionAgent()
    if req.mode in ("full", "onboarding"):
        agent_map["onboarding"] = OnboardingAgent()
    if req.mode in ("full", "regulatory"):
        agent_map["regulatory"] = RegulatoryAgent()
    if req.mode in ("full", "financial_risk"):
        agent_map["financial_risk"] = FinancialRiskAgent()

    # ── Run agents in parallel ────────────────────────────────────────────────
    async def _run(name: str, agent: Any):
        try:
            return name, await agent.run(clean_text, packs, docs)
        except Exception as exc:
            log.error("compliance.agent.error", agent=name, error=str(exc))
            return name, {"reasoning": f"Agent error: {exc}", "sources": [], "confidence": 0.1}

    results = await asyncio.gather(*[_run(n, a) for n, a in agent_map.items()])
    agent_outputs: Dict[str, Any] = dict(results)

    # ── Generate consolidated report ──────────────────────────────────────────
    report_agent = ReportAgent()
    try:
        report_output = await report_agent.run(clean_text, packs, docs, agent_outputs)
    except Exception as exc:
        triage_run.status = "failed"
        triage_run.error_message = str(exc)[:1000]
        triage_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=502, detail="Compliance report synthesis failed") from exc

    # ── Build response domains ────────────────────────────────────────────────
    rating_kw_map = {
        "high":   ["high risk", "critical", "severe", "non-compliant", "immediate", "str required",
                   "money laundering", "aml", "suspicious", "flagged", "structuring"],
        "medium": ["medium risk", "moderate", "requires attention", "conditional", "review",
                   "enhanced due diligence", "edd", "caution"],
        "low":    ["low risk", "satisfactory", "compliant", "minor", "no significant"],
    }

    def _infer_rating(text: str) -> str:
        text_l = text.lower()
        # Check high first (most important)
        for rating in ("high", "medium", "low"):
            if any(k in text_l for k in rating_kw_map[rating]):
                return rating
        return "low"

    domains: List[RiskDomain] = []
    for name, output in agent_outputs.items():
        reasoning = output.get("reasoning", "")
        domains.append(RiskDomain(
            name=name.replace("_", " ").title(),
            rating=_infer_rating(reasoning),
            summary=reasoning[:300].strip(),
            confidence=output.get("confidence", 0.5),
        ))

    full_report_text = report_output.get("reasoning", "")
    overall = _overall_rating(domains)

    # STR / EDD flags
    str_kws = ["str", "suspicious transaction", "money laundering", "financial crime", "str filing"]
    edd_kws = ["edd", "enhanced due diligence", "pep", "sanctioned", "high risk customer"]
    combined_text = full_report_text.lower() + " ".join(d.summary.lower() for d in domains)
    requires_str = any(k in combined_text for k in str_kws)
    requires_edd = any(k in combined_text for k in edd_kws)

    recommendations = _extract_recommendations(full_report_text) or [
        "Review flagged items with compliance officer",
        "Conduct enhanced due diligence if customer risk is High",
        "File STR within 7 working days if suspicious activity confirmed",
    ]

    triage_run.status = "completed"
    triage_run.overall_rating = overall
    triage_run.requires_str = requires_str
    triage_run.requires_edd = requires_edd
    triage_run.result_json = jsonable_encoder({
        "run_id": run_id,
        "overall_rating": overall,
        "domains": domains,
        "full_report": full_report_text,
        "recommendations": recommendations,
        "requires_str": requires_str,
        "requires_edd": requires_edd,
    })
    triage_run.completed_at = datetime.now(timezone.utc)

    # Elevated triage outcomes enter the human review queue automatically.
    if overall == "high" or requires_str or requires_edd:
        db.add(ApprovalRequest(
            requested_by_user_id=UUID(user["db_id"]),
            action_type="review_triage",
            risk_level="critical" if requires_str else "high",
            payload={"triage_run_id": str(run_id)},
            reason="Triage requires compliance review before escalation or external action.",
            status="pending",
        ))
    await db.commit()

    log.info("compliance.triage.complete", run_id=str(run_id), overall=overall)

    return ComplianceResponse(
        run_id=run_id,
        overall_rating=overall,
        domains=domains,
        full_report=full_report_text,
        recommendations=recommendations,
        requires_str=requires_str,
        requires_edd=requires_edd,
    )


@router.get("/compliance/triage/{run_id}")
async def get_triage_run(run_id: UUID, user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    """Retrieve a durable triage run belonging to the authenticated user."""
    result = await db.execute(
        select(ComplianceTriageRun).where(
            ComplianceTriageRun.id == run_id,
            ComplianceTriageRun.user_id == UUID(user["db_id"]),
        )
    )
    triage_run = result.scalar_one_or_none()
    if not triage_run:
        raise HTTPException(status_code=404, detail="Triage run not found")
    return {
        "run_id": str(triage_run.id), "status": triage_run.status,
        "mode": triage_run.mode, "created_at": triage_run.created_at,
        "completed_at": triage_run.completed_at, "result": triage_run.result_json,
        "error_message": triage_run.error_message,
    }


@router.get("/compliance/triage")
async def list_triage_runs(user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    """Return the authenticated user's recent compliance triage timeline."""
    result = await db.execute(
        select(ComplianceTriageRun)
        .where(ComplianceTriageRun.user_id == UUID(user["db_id"]))
        .order_by(ComplianceTriageRun.created_at.desc())
        .limit(50)
    )
    runs = result.scalars().all()
    return {
        "runs": [
            {
                "run_id": str(run.id), "status": run.status,
                "mode": run.mode, "overall_rating": run.overall_rating,
                "requires_str": run.requires_str, "requires_edd": run.requires_edd,
                "created_at": run.created_at,
                "description_preview": run.redacted_description[:180],
            }
            for run in runs
        ]
    }

class ComplianceChatRequest(BaseModel):
    message: str = Field(..., description="User chat message")
    session_context: Dict[str, Any] = Field(default_factory=dict, description="Context from current triage session")

class ComplianceChatResponse(BaseModel):
    reply: str

@router.post("/compliance/chat", response_model=ComplianceChatResponse)
async def compliance_chat(req: ComplianceChatRequest, user=Depends(current_user)):
    """Kept for backward compatibility with the existing frontend chat widget.
    Now delegates to the full 7-tool FinTriageAgent (see app/agents/fintriage_agent.py)
    instead of the old 2-intent ComplianceOrchestrator. New integrations should call
    POST /v1/agent directly, which also persists conversation history."""
    from app.agents.fintriage_agent import FinTriageAgent
    agent = FinTriageAgent()
    ctx = dict(req.session_context)
    ctx.setdefault("user_id", user["id"])
    result = await agent.handle(req.message, ctx)
    return ComplianceChatResponse(reply=result["reply"])

# ─────────────────────────────────── Audit Flow ────────────────────────────────

class AuditReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected|escalated)$")
    overridden_tier: Optional[str] = None
    comments: Optional[str] = None

@router.get("/compliance/audit")
async def get_audits(db: AsyncSession = Depends(get_db), user=Depends(current_user)):
    """Get all pending audits for human review."""
    from sqlalchemy.future import select
    from sqlalchemy.orm import selectinload
    from app.db.models import ComplianceAuditLog, Run, Query, Matter
    
    stmt = (
        select(ComplianceAuditLog)
        .options(selectinload(ComplianceAuditLog.run).selectinload(Run.query).selectinload(Query.matter))
        .order_by(ComplianceAuditLog.created_at.desc())
    )
    result = await db.execute(stmt)
    audits = result.scalars().all()
    
    response = []
    for a in audits:
        matter = a.run.query.matter if a.run and a.run.query else None
        response.append({
            "id": a.id,
            "run_id": a.run_id,
            "status": a.status,
            "original_tier": a.original_tier,
            "overridden_tier": a.overridden_tier,
            "created_at": a.created_at,
            "matter_title": matter.title if matter else "Unknown Matter",
            "query_message": a.run.query.message if a.run and a.run.query else "No details"
        })
    return {"audits": response}

@router.post("/compliance/audit/{audit_id}")
async def review_audit(
    audit_id: UUID, 
    review: AuditReviewRequest,
    db: AsyncSession = Depends(get_db), 
    user=Depends(current_user)
):
    """Submit human review for an AI triage decision."""
    from sqlalchemy.future import select
    from datetime import datetime
    from fastapi import HTTPException
    from app.db.models import ComplianceAuditLog
    
    stmt = select(ComplianceAuditLog).where(ComplianceAuditLog.id == audit_id)
    result = await db.execute(stmt)
    audit = result.scalar_one_or_none()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit log not found")
        
    audit.status = review.status
    audit.overridden_tier = review.overridden_tier
    audit.comments = review.comments
    try:
        audit.officer_id = UUID(user["id"]) if isinstance(user["id"], str) and len(user["id"]) == 36 else None
    except (ValueError, AttributeError):
        audit.officer_id = None
    audit.reviewed_at = datetime.utcnow()
    
    await db.commit()
    return {"status": "success", "audit_id": audit_id, "new_status": review.status}
