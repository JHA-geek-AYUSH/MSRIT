"""Persistence helpers for the FinTriage AI pipeline (Plan.md Section 12).

Kept separate from app/db/crud.py (legal-chat CRUD) to avoid coupling the two
product surfaces. All functions are best-effort: if the migration
540d6b34a446_add_fintriage_tables hasn't been applied yet, callers should wrap
these in try/except (the API layer does this) so the rest of the pipeline
still works without persistence during early demo/dev.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.models import (
    Entity,
    ComplianceAssessment,
    ComplianceFinding,
    PenaltySimulationRecord,
    AuditReportRecord,
    FinTriageChatMessage,
)


def _safe_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


async def get_or_create_entity(
    db: AsyncSession,
    user_id: Optional[str],
    business_name: str,
    sector: Optional[str] = None,
    **extra: Any,
) -> Entity:
    entity = Entity(
        user_id=_safe_uuid(user_id),
        business_name=business_name,
        sector=sector,
        annual_turnover=extra.get("annual_turnover"),
        employee_count=extra.get("employee_count"),
        director_count=extra.get("director_count"),
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


async def save_assessment(
    db: AsyncSession,
    user_id: Optional[str],
    entity_id: Optional[str],
    result: Dict[str, Any],
    narrative_agents: Optional[Dict[str, Any]] = None,
) -> ComplianceAssessment:
    """Persist the output of ml/pipeline.run_full_assessment(), plus the optional
    narrative-agent reasoning (Transaction/Onboarding/Regulatory/FinancialRisk --
    the agents that used to only run in the now-merged /compliance/triage flow).
    Stored in feature_importance since it's the one flexible JSON column already
    on this row; keeps assessment + narrative as a single durable record instead
    of two disconnected ones."""
    features = result.get("features", {})
    feature_importance: Dict[str, Any] = {"dominant_flag": result.get("anomaly", {}).get("dominant_flag")}
    if narrative_agents:
        feature_importance["narrative_agents"] = {
            name: out.get("reasoning") for name, out in narrative_agents.items() if out
        }
    assessment = ComplianceAssessment(
        entity_id=_safe_uuid(entity_id),
        user_id=_safe_uuid(user_id),
        monthly_txn_volume=features.get("monthly_txn_volume"),
        avg_ticket_size=features.get("avg_ticket_size"),
        cash_ratio=features.get("cash_ratio"),
        cross_border_ratio=features.get("cross_border_ratio"),
        late_payment_rate=features.get("late_payment_rate"),
        sector_risk_score=features.get("sector_risk_score"),
        anomaly_risk_score=features.get("anomaly_risk_score"),
        risk_tier=result.get("risk_tier"),
        risk_score=result.get("confidence"),
        confidence_pct=int(round(result.get("confidence", 0.0) * 100)),
        feature_importance=feature_importance,
        detected_flags=result.get("detected_flags", []),
        total_penalty_exposure_inr=result.get("total_penalty_exposure_inr"),
        raw_features=features,
    )
    db.add(assessment)
    await db.flush()

    for finding in result.get("findings", []):
        db.add(ComplianceFinding(
            assessment_id=assessment.id,
            rule_code=finding["rule_code"],
            gap_score=finding.get("gap_score"),
            cosine_similarity=finding.get("similarity_score"),
            combined_score=finding.get("combined_score"),
            severity=finding.get("severity"),
            warning_flags=finding.get("factors"),
            plain_english_finding=finding.get("description"),
            remediation_steps=finding.get("remediation_steps", []),
        ))

    await db.commit()
    await db.refresh(assessment)
    return assessment


async def get_assessment(db: AsyncSession, assessment_id: str) -> Optional[ComplianceAssessment]:
    aid = _safe_uuid(assessment_id)
    if not aid:
        return None
    res = await db.execute(select(ComplianceAssessment).where(ComplianceAssessment.id == aid))
    return res.scalar_one_or_none()


async def get_findings(db: AsyncSession, assessment_id: str) -> List[ComplianceFinding]:
    aid = _safe_uuid(assessment_id)
    if not aid:
        return []
    res = await db.execute(select(ComplianceFinding).where(ComplianceFinding.assessment_id == aid))
    return list(res.scalars().all())


async def list_assessments_for_user(db: AsyncSession, user_id: str, limit: int = 20) -> List[ComplianceAssessment]:
    uid = _safe_uuid(user_id)
    if not uid:
        return []
    res = await db.execute(
        select(ComplianceAssessment)
        .where(ComplianceAssessment.user_id == uid)
        .order_by(desc(ComplianceAssessment.created_at))
        .limit(limit)
    )
    return list(res.scalars().all())


async def save_penalty_sim(
    db: AsyncSession,
    user_id: Optional[str],
    assessment_id: Optional[str],
    sim_result: Dict[str, Any],
) -> PenaltySimulationRecord:
    rec = PenaltySimulationRecord(
        assessment_id=_safe_uuid(assessment_id),
        user_id=_safe_uuid(user_id),
        scenario_id=sim_result["scenario_id"],
        rule_code=sim_result.get("rule_code"),
        days_since_breach=sim_result.get("days_since_breach"),
        aggravating_factors=[d["factor"] for d in sim_result.get("aggravating_details", [])],
        base_fine=sim_result.get("base_fine"),
        per_day_fine=sim_result.get("per_day_fine"),
        total_fine=sim_result.get("total_fine"),
        imprisonment_risk=sim_result.get("imprisonment_risk"),
        verdict=sim_result.get("verdict"),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def save_audit_report(
    db: AsyncSession,
    user_id: Optional[str],
    assessment_id: Optional[str],
    report: Dict[str, Any],
) -> AuditReportRecord:
    rec = AuditReportRecord(
        assessment_id=_safe_uuid(assessment_id),
        user_id=_safe_uuid(user_id),
        report_json=report,
        gemma_summary=report.get("gemma_summary"),
        total_penalty_exposure=report.get("penalty_exposure_summary", {}).get("total_estimated_fine_inr"),
        urgency_tier=report.get("penalty_exposure_summary", {}).get("urgency_tier"),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def save_chat_message(
    db: AsyncSession,
    user_id: Optional[str],
    assessment_id: Optional[str],
    role: str,
    content: str,
    tool_used: Optional[str] = None,
    tool_result: Optional[Dict[str, Any]] = None,
    confidence: Optional[float] = None,
) -> FinTriageChatMessage:
    msg = FinTriageChatMessage(
        assessment_id=_safe_uuid(assessment_id),
        user_id=_safe_uuid(user_id),
        role=role,
        content=content,
        tool_used=tool_used,
        tool_result=tool_result,
        confidence=confidence,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_chat_history(db: AsyncSession, user_id: str, limit: int = 50) -> List[FinTriageChatMessage]:
    uid = _safe_uuid(user_id)
    if not uid:
        return []
    res = await db.execute(
        select(FinTriageChatMessage)
        .where(FinTriageChatMessage.user_id == uid)
        .order_by(desc(FinTriageChatMessage.created_at))
        .limit(limit)
    )
    return list(reversed(res.scalars().all()))
