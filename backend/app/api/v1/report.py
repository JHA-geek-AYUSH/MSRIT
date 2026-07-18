"""POST /v1/compliance/report — Gemma-generated 6-section audit-ready report
(Plan.md Section 10). Shared by the /report endpoint and the agent's
`generate_report` tool so there's exactly one implementation.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.db.session import get_db
from app.db import fintriage_crud as fcrud
import structlog

log = structlog.get_logger()
router = APIRouter()


def _urgency_tier(total_exposure: float, imprisonment_risk: bool) -> str:
    if imprisonment_risk or total_exposure >= 5_000_000:
        return "Critical"
    if total_exposure >= 1_000_000:
        return "High"
    if total_exposure >= 100_000:
        return "Medium"
    return "Low"


def build_report_sections(
    business_name: Optional[str],
    sector: Optional[str],
    risk_tier: str,
    confidence: float,
    findings: List[Dict[str, Any]],
    total_penalty_exposure_inr: float,
    imprisonment_risk: bool,
    gemma_narrative: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the 6 sections from Plan.md Section 10, independent of whether
    an LLM narrative is available (falls back to a templated summary)."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranked_actions = sorted(findings, key=lambda f: severity_order.get(f.get("severity"), 4))

    top_drivers = [
        {"rule_code": f["rule_code"], "rule_name": f.get("rule_name"), "contribution_pct": round(f.get("combined_score", 0) * 100, 1)}
        for f in findings[:3]
    ]

    return {
        "section_1_entity_summary": {
            "business_name": business_name or "Unnamed Entity",
            "sector": sector or "Unspecified",
            "assessment_date": datetime.utcnow().date().isoformat(),
        },
        "section_2_risk_assessment": {
            "risk_tier": risk_tier.upper(),
            "confidence_pct": round(confidence * 100, 1),
            "top_risk_drivers": top_drivers,
        },
        "section_3_compliance_findings": [
            {
                "rule_code": f["rule_code"],
                "rule_name": f.get("rule_name"),
                "gap_score": f.get("gap_score"),
                "severity": f.get("severity"),
                "plain_english_finding": f.get("description"),
                "remediation_steps": f.get("remediation_steps", []),
            }
            for f in findings
        ],
        "section_4_penalty_exposure": {
            "total_estimated_fine_inr": total_penalty_exposure_inr,
            "breakdown_per_rule": [
                {"rule_code": f["rule_code"], "max_penalty_inr": f.get("max_penalty_inr")}
                for f in findings if f.get("severity") in ("critical", "high")
            ],
            "imprisonment_risk": imprisonment_risk,
            "urgency_tier": _urgency_tier(total_penalty_exposure_inr, imprisonment_risk),
        },
        "section_5_recommended_actions": [
            {
                "priority": f.get("severity", "low").capitalize(),
                "action": (f.get("remediation_steps") or ["Review with compliance officer"])[0],
                "rule_code": f["rule_code"],
            }
            for f in ranked_actions
        ],
        "section_6_signoff": {
            "prepared_by": "FinTriage AI (automated)",
            "reviewed_by": None,
            "date": None,
        },
        "gemma_summary": gemma_narrative,
    }


async def generate_gemma_narrative(sections: Dict[str, Any]) -> Optional[str]:
    client = get_llm_client_or_none()
    if not client:
        return None
    prompt = (
        "You are a compliance report writer. Write a concise 3-4 sentence executive "
        "summary of this compliance assessment for a human reviewer, in plain English:\n\n"
        f"{json.dumps(sections, default=str)[:4000]}"
    )
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=250,
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.warning("report.gemma_narrative_failed", error=str(e))
        return None


class ReportRequest(BaseModel):
    assessment_id: Optional[str] = Field(None, description="Persisted assessment to report on")
    business_name: Optional[str] = None
    sector: Optional[str] = None
    risk_tier: Optional[str] = None
    confidence: Optional[float] = None
    findings: Optional[List[Dict[str, Any]]] = None
    total_penalty_exposure_inr: Optional[float] = None
    imprisonment_risk: Optional[bool] = None


@router.post("/compliance/report")
async def generate_report(req: ReportRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Generate the 6-section compliance audit report (Plan.md Section 10)."""
    business_name, sector = req.business_name, req.sector
    risk_tier, confidence = req.risk_tier, req.confidence
    findings = req.findings
    total_exposure = req.total_penalty_exposure_inr
    imprisonment_risk = req.imprisonment_risk

    if req.assessment_id:
        assessment = await fcrud.get_assessment(db, req.assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found")
        db_findings = await fcrud.get_findings(db, req.assessment_id)
        findings = findings or [
            {
                "rule_code": f.rule_code, "rule_name": f.rule_code, "severity": f.severity,
                "gap_score": f.gap_score, "combined_score": f.combined_score,
                "description": f.plain_english_finding, "remediation_steps": f.remediation_steps,
                "max_penalty_inr": None,
            }
            for f in db_findings
        ]
        risk_tier = risk_tier or assessment.risk_tier
        confidence = confidence if confidence is not None else float(assessment.confidence_pct or 0) / 100.0
        total_exposure = total_exposure if total_exposure is not None else float(assessment.total_penalty_exposure_inr or 0)
        imprisonment_risk = imprisonment_risk if imprisonment_risk is not None else False

    if findings is None or risk_tier is None:
        raise HTTPException(status_code=400, detail="Provide either assessment_id or (risk_tier, findings, ...) inline")

    sections = build_report_sections(
        business_name, sector, risk_tier, confidence or 0.5, findings,
        total_exposure or 0.0, bool(imprisonment_risk),
    )
    narrative = await generate_gemma_narrative(sections)
    sections["gemma_summary"] = narrative or (
        f"{business_name or 'This entity'} was assessed at {risk_tier.upper()} risk "
        f"({round((confidence or 0.5) * 100)}% confidence) with an estimated penalty exposure "
        f"of ₹{int(total_exposure or 0):,}. {len(findings)} compliance rule(s) were flagged for review."
    )

    try:
        await fcrud.save_audit_report(db, user["id"], req.assessment_id, sections)
    except Exception as e:
        log.warning("report.persist_failed", error=str(e))

    return sections
