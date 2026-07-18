"""POST /v1/agent — the canonical FinTriage 7-tool conversational agent endpoint
(Plan.md Section 6: `/api/agent`).

Also see app/api/v1/compliance.py's /compliance/chat, which now delegates to the
same FinTriageAgent for backward compatibility with the existing frontend
(lib/compliance-api.ts -> sendComplianceChat -> /v1/compliance/chat).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.session import get_db
from app.db import fintriage_crud as fcrud
from app.agents.fintriage_agent import FinTriageAgent
import structlog

log = structlog.get_logger()
router = APIRouter()
_agent = FinTriageAgent()


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_context: Dict[str, Any] = Field(default_factory=dict)
    assessment_id: Optional[str] = None


class AgentResponse(BaseModel):
    tool_used: str
    confidence: float
    reply: str
    data: Optional[Dict[str, Any]] = None


@router.post("/agent", response_model=AgentResponse)
async def run_agent(req: AgentRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Natural-language entry point into the 7-tool FinTriage agent
    (reassess / penalty_sim / threshold_sim / compare / explain_risk / rule_info / generate_report)."""
    ctx = dict(req.session_context)
    ctx.setdefault("user_id", user["id"])

    result = await _agent.handle(req.message, ctx)

    try:
        await fcrud.save_chat_message(db, user["id"], req.assessment_id, "user", req.message)
        await fcrud.save_chat_message(
            db, user["id"], req.assessment_id, "agent", result["reply"],
            tool_used=result["tool_used"], tool_result=result.get("data"), confidence=result["confidence"],
        )
    except Exception as e:
        log.warning("agent.chat_persist_failed", error=str(e))

    return AgentResponse(**result)


@router.get("/agent/history")
async def agent_history(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        messages = await fcrud.get_chat_history(db, user["id"])
        return {
            "messages": [
                {"role": m.role, "content": m.content, "tool_used": m.tool_used, "created_at": m.created_at}
                for m in messages
            ]
        }
    except Exception as e:
        return {"messages": [], "note": f"Persistence unavailable: {e}"}
