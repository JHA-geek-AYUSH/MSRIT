"""POST /v1/compliance/assess — the real, unified 3-stage pipeline endpoint
(Plan.md Section 6: `/api/assess`, `/api/rank-rules`, `/api/score-flags`, `/api/parse-flags`).

This was previously missing entirely — the frontend's /compliance/triage endpoint
runs a different, LLM-reasoning-based system (see app/agents/transaction_agent.py etc)
that does NOT implement the Stage 0->1->2->3 ML pipeline specified in Plan.md.
This file is the actual Plan.md-spec pipeline, exposed as its own endpoint set so it
can be adopted by the frontend without breaking the existing /triage flow.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_user
from app.core.pii_redaction import redact_user_input
from app.db.session import get_db
from app.db import fintriage_crud as fcrud
from app.ml.pipeline import detect_flags_from_text, run_full_assessment
from app.ml.risk_model_runner import extract_financial_features
from app.ml.compliance_scorer import rank_all_rules
from app.ml.anomaly_scorer import score_anomalies
from app.ml.pipeline import _llm_generate_fn
import structlog

log = structlog.get_logger()
router = APIRouter()


# ─────────────────────────────────── Schemas ──────────────────────────────────

class AssessRequest(BaseModel):
    description: Optional[str] = Field(None, description="Free-text description of the entity/transactions (optional if features given directly)")
    features: Optional[Dict[str, float]] = Field(None, description="Explicit 9D feature overrides")
    flags: Optional[List[str]] = Field(None, description="Explicit Stage-0 transaction flag names; auto-detected from description if omitted")
    sector: Optional[str] = None
    business_name: Optional[str] = Field(None, description="If given, persists an Entity + Assessment record")
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    persist: bool = True


class AssessResponse(BaseModel):
    assessment_id: Optional[str] = None
    risk_tier: str
    confidence: float
    model_fallback: bool
    auto_escalated: bool
    detected_flags: List[str]
    anomaly_summary: str
    total_penalty_exposure_inr: float
    imprisonment_risk: bool
    findings: List[Dict[str, Any]]
    features: Dict[str, float]


async def _build_features(req: "AssessRequest") -> tuple[Dict[str, float], List[str]]:
    text = req.description or ""
    for d in req.documents:
        text += "\n" + str(d.get("content", ""))

    features = extract_financial_features(text, req.documents) if text.strip() else {
        "monthly_txn_volume": 100, "avg_ticket_size": 50000.0, "cash_ratio": 0.1,
        "cross_border_ratio": 0.05, "late_payment_rate": 0.05, "business_age_years": 5.0,
        "sector_risk_score": 0.3, "director_count": 2, "anomaly_risk_score": 0.5,
    }
    if req.features:
        features.update(req.features)

    flags = req.flags if req.flags is not None else (detect_flags_from_text(text) if text.strip() else [])
    return features, flags


@router.post("/compliance/assess", response_model=AssessResponse)
async def assess_entity(
    req: AssessRequest,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the full Stage 0 -> 1 -> 2/3 pipeline and return risk tier + top rule breaches.

    This is the single entry point that Plan.md's `/api/assess` describes: anomaly
    scoring, XGBoost classification, and the weighted compliance gap + cosine ranker,
    combined into one structured, explainable result.
    """
    log.info("assess.start", user_id=user["id"])

    clean_description = None
    if req.description:
        pii = redact_user_input(req.description, user["id"], mode="placeholder")
        clean_description = pii["redacted_text"]

    working_req = req.model_copy(update={"description": clean_description}) if clean_description else req
    features, flags = await _build_features(working_req)

    result = run_full_assessment(features, detected_flags=flags, sector=req.sector)

    assessment_id = None
    if req.persist:
        try:
            entity_id = None
            if req.business_name:
                entity = await fcrud.get_or_create_entity(db, user["db_id"], req.business_name, sector=req.sector)
                entity_id = str(entity.id)
            saved = await fcrud.save_assessment(db, user["db_id"], entity_id, result)
            assessment_id = str(saved.id)
        except Exception as e:
            # Migration 540d6b34a446 may not be applied yet — pipeline still works, just unsaved.
            log.warning("assess.persist_failed", error=str(e))

    return AssessResponse(
        assessment_id=assessment_id,
        risk_tier=result["risk_tier"],
        confidence=result["confidence"],
        model_fallback=result["model_fallback"],
        auto_escalated=result["auto_escalated"],
        detected_flags=result["detected_flags"],
        anomaly_summary=result["anomaly"].get("anomaly_summary", ""),
        total_penalty_exposure_inr=result["total_penalty_exposure_inr"],
        imprisonment_risk=result["imprisonment_risk"],
        findings=result["findings"],
        features=result["features"],
    )


@router.get("/compliance/assess/{assessment_id}")
async def get_assessment(assessment_id: str, user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    try:
        assessment = await fcrud.get_assessment(db, assessment_id)
        if not assessment or str(assessment.user_id) != user["db_id"]:
            raise HTTPException(status_code=404, detail="Assessment not found")
        findings = await fcrud.get_findings(db, assessment_id)
        return {
            "id": str(assessment.id),
            "risk_tier": assessment.risk_tier,
            "confidence_pct": assessment.confidence_pct,
            "total_penalty_exposure_inr": assessment.total_penalty_exposure_inr,
            "detected_flags": assessment.detected_flags,
            "created_at": assessment.created_at,
            "findings": [
                {
                    "rule_code": f.rule_code,
                    "severity": f.severity,
                    "combined_score": f.combined_score,
                    "plain_english_finding": f.plain_english_finding,
                    "remediation_steps": f.remediation_steps,
                }
                for f in findings
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Assessment persistence unavailable (run the DB migration): {e}")


class RankRulesRequest(BaseModel):
    features: Dict[str, float]
    risk_tier: Optional[str] = None
    sector: Optional[str] = None


@router.post("/compliance/rank-rules")
async def rank_rules(req: RankRulesRequest, user=Depends(get_db_user)):
    """Fast path — score all 40 rules against a feature set, no Gemma call (Plan.md `/api/rank-rules`)."""
    ranked = rank_all_rules(req.features, risk_tier=req.risk_tier, sector=req.sector)
    return {"total": len(ranked), "rules": ranked}


class ScoreFlagsRequest(BaseModel):
    flags: List[str] = Field(..., min_length=1)


@router.post("/compliance/score-flags")
async def score_flags(req: ScoreFlagsRequest, user=Depends(get_db_user)):
    """Stage 0 only — score a list of transaction flags (Plan.md `/api/score-flags`)."""
    llm_fn = _llm_generate_fn()
    result = score_anomalies(req.flags, llm_generate=llm_fn)
    return result


class ParseFlagsRequest(BaseModel):
    text: str = Field(..., min_length=5)


@router.post("/compliance/parse-flags")
async def parse_flags(req: ParseFlagsRequest, user=Depends(get_db_user)):
    """NER-lite: extract Stage-0 flag names from free text, then score them (Plan.md `/api/parse-flags`)."""
    flags = detect_flags_from_text(req.text)
    if not flags:
        return {"detected_flags": [], "scoring": {"flags": [], "total_anomaly_score": 0.0, "anomaly_summary": "No known flag patterns detected in text."}}
    llm_fn = _llm_generate_fn()
    scoring = score_anomalies(flags, llm_generate=llm_fn)
    return {"detected_flags": flags, "scoring": scoring}


@router.get("/compliance/history")
async def assessment_history(user=Depends(get_db_user), db: AsyncSession = Depends(get_db)):
    try:
        assessments = await fcrud.list_assessments_for_user(db, user["db_id"])
        return {
            "total": len(assessments),
            "assessments": [
                {
                    "id": str(a.id),
                    "risk_tier": a.risk_tier,
                    "confidence_pct": a.confidence_pct,
                    "total_penalty_exposure_inr": a.total_penalty_exposure_inr,
                    "created_at": a.created_at,
                }
                for a in assessments
            ],
        }
    except Exception as e:
        return {"total": 0, "assessments": [], "note": f"Persistence unavailable: {e}"}
