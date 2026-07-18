"""GET /v1/system/status — public, unauthenticated health/status check. Answers
"is Gemma actually connected right now?" directly and honestly, so the AI
analysis isn't a black box. Surfaced in the frontend via a status pill on the
Agent Console (see frontend/app/agent/page.tsx).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.gemma_client import get_llm_status

router = APIRouter()


@router.get("/system/status")
async def system_status():
    return {"llm": get_llm_status()}
