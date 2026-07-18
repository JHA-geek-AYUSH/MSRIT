"""GET /v1/dashboard — one endpoint, role-shaped response (Plan.md: "role-based
dashboards allow finance teams, auditors, compliance officers and CFOs to access
insights and reports from one place"). The user's DB role (app.db.models.User.role,
set via PUT /v1/profile) determines which sections are populated; all roles share
the same underlying data so nothing has to be duplicated per-role in the frontend.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_user
from app.db.session import get_db
from app.db import fintriage_crud as fcrud

router = APIRouter()

# Maps role → list of dashboard section keys visible to that role (tasks.md §10.1)
ROLE_SECTIONS: Dict[str, list] = {
    "finance_analyst": [
        "recent_assessments",
        "invoice_queue",
        "transaction_feed",
        "penalty_exposure_summary",
    ],
    "compliance_officer": [
        "critical_findings",
        "pending_approvals",
        "str_queue",
        "policy_gaps",
    ],
    "auditor": [
        "audit_log",
        "report_archive",
        "pending_reviews",
        "critical_findings",
    ],
    "cfo": [
        "penalty_exposure_summary",
        "trend_charts",
        "risk_heatmap",
        "top_critical_rules",
    ],
    "admin": [
        # Superset — all sections from all roles plus management tools
        "recent_assessments",
        "invoice_queue",
        "transaction_feed",
        "penalty_exposure_summary",
        "critical_findings",
        "pending_approvals",
        "str_queue",
        "policy_gaps",
        "audit_log",
        "report_archive",
        "pending_reviews",
        "trend_charts",
        "risk_heatmap",
        "top_critical_rules",
        "user_management",
        "connector_status",
        "system_health",
    ],
    "viewer": [
        "recent_assessments",
        "penalty_exposure_summary",
    ],
}

# Roles that can see org-wide pending approvals; others see only their own
_ORG_APPROVAL_ROLES = {"compliance_officer", "auditor", "cfo", "admin"}


@router.get("/dashboard")
async def dashboard(user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    role = user.get("role", "viewer")
    sections = ROLE_SECTIONS.get(role)
    if sections is None:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' is not recognised. Contact an administrator to assign a valid role.",
        )

    # ── Core assessment data (used by multiple sections) ────────────────────
    try:
        assessments = await fcrud.list_assessments_for_user(db, user["id"], limit=20)
    except Exception:
        assessments = []

    total_exposure = sum(float(a.total_penalty_exposure_inr or 0) for a in assessments)
    critical = [a for a in assessments if a.risk_tier == "critical"]

    payload: Dict[str, Any] = {
        "role": role,
        "sections_visible": sections,
    }

    # ── recent_assessments ──────────────────────────────────────────────────
    if "recent_assessments" in sections:
        payload["recent_assessments"] = [
            {
                "id": str(a.id),
                "risk_tier": a.risk_tier,
                "confidence_pct": a.confidence_pct,
                "total_penalty_exposure_inr": a.total_penalty_exposure_inr,
                "created_at": a.created_at,
            }
            for a in assessments
        ]

    # ── penalty_exposure_summary ────────────────────────────────────────────
    if "penalty_exposure_summary" in sections:
        payload["penalty_exposure_summary"] = {
            "total": total_exposure,
            "count": len(assessments),
            "critical_count": len(critical),
            "trend_7d": None,   # placeholder — implement with time-series query
            "by_framework": {}, # placeholder — implement with rule framework grouping
        }

    # ── critical_findings ───────────────────────────────────────────────────
    if "critical_findings" in sections:
        payload["critical_findings"] = [
            {"id": str(a.id), "risk_tier": a.risk_tier, "created_at": a.created_at}
            for a in critical
        ]

    # ── pending_approvals (scoped by role) ──────────────────────────────────
    if "pending_approvals" in sections:
        from app.db.models import ApprovalRequest
        try:
            stmt = (
                select(ApprovalRequest)
                .where(ApprovalRequest.status == "pending")
                .order_by(desc(ApprovalRequest.created_at))
                .limit(20)
            )
            # Org-level roles see all pending; finance_analyst/viewer see own only
            if role not in _ORG_APPROVAL_ROLES:
                stmt = stmt.where(
                    ApprovalRequest.requested_by_user_id == user.get("db_id")
                )
            res = await db.execute(stmt)
            payload["pending_approvals"] = [
                {
                    "id": str(r.id),
                    "action_type": r.action_type,
                    "risk_level": r.risk_level,
                    "reason": r.reason,
                    "created_at": r.created_at,
                }
                for r in res.scalars().all()
            ]
        except Exception:
            payload["pending_approvals"] = []

    # ── stub sections — populated as dedicated endpoints are added ──────────
    for stub_key in (
        "invoice_queue", "transaction_feed", "str_queue", "policy_gaps",
        "audit_log", "report_archive", "pending_reviews",
        "trend_charts", "risk_heatmap", "top_critical_rules",
        "user_management", "connector_status", "system_health",
    ):
        if stub_key in sections and stub_key not in payload:
            payload[stub_key] = []  # empty list is a safe default for a queue/feed

    return payload
