from __future__ import annotations

from uuid import uuid4
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.core.pii_redaction import redact_user_input
from app.agents.cashflow_agent import CashflowAgent
from app.agents.growth_advisory_agent import GrowthAdvisoryAgent
import structlog

log = structlog.get_logger()
router = APIRouter()


# ── Track 1: SME Cashflow Copilot ────────────────────────────────────────────

class CashflowRequest(BaseModel):
    description: str = Field(..., min_length=10, description="Business description or cashflow query")
    context: Optional[Dict[str, Any]] = None


class CashflowResponse(BaseModel):
    run_id: str
    analysis: str
    confidence: float


@router.post("/financial/cashflow", response_model=CashflowResponse)
async def cashflow_analysis(req: CashflowRequest, user=Depends(current_user)):
    """Track 1 — SME Cashflow Copilot: forecast cash flow, identify liquidity risks,
    automate invoice follow-ups, optimise payment schedules."""
    run_id = str(uuid4())
    log.info("cashflow.start", user_id=user["id"], run_id=run_id)

    pii = redact_user_input(req.description, user["id"], mode="placeholder")
    agent = CashflowAgent()
    output = await agent.run(pii["redacted_text"], req.context)

    return CashflowResponse(run_id=run_id, analysis=output["reasoning"], confidence=output["confidence"])


# ── Track 3: SME Growth & Advisory ───────────────────────────────────────────

class GrowthRequest(BaseModel):
    description: str = Field(..., min_length=10, description="Business description or growth query")
    context: Optional[Dict[str, Any]] = None


class GrowthResponse(BaseModel):
    run_id: str
    advisory: str
    confidence: float


@router.post("/financial/growth", response_model=GrowthResponse)
async def growth_advisory(req: GrowthRequest, user=Depends(current_user)):
    """Track 3 — SME Growth & Advisory: pricing, revenue forecasting, supplier management,
    collections, operational planning, and strategic business growth."""
    run_id = str(uuid4())
    log.info("growth_advisory.start", user_id=user["id"], run_id=run_id)

    pii = redact_user_input(req.description, user["id"], mode="placeholder")
    agent = GrowthAdvisoryAgent()
    output = await agent.run(pii["redacted_text"], req.context)

    return GrowthResponse(run_id=run_id, advisory=output["reasoning"], confidence=output["confidence"])
