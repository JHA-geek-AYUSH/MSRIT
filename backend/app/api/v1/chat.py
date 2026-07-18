from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.core.pii_redaction import redact_user_input
from app.db.session import get_db
from app.db.models import PIIRecord
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.retrieval.assemble import retrieve_packs
from app.agents.drafting_agent import DraftingAgent
from app.agents.statute_agent import StatuteAgent
from app.agents.precedent_agent import PrecedentAgent
from app.agents.limitation_agent import LimitationAgent
from app.agents.risk_agent import RiskAgent
from app.agents.devil_agent import DevilAgent
from app.agents.ethics_agent import EthicsAgent
from app.agents.aggregator import aggregate
from app.db import crud
from app.billing.credits import calculate_and_debit_query_cost
import structlog
import uuid as _uuid

log = structlog.get_logger()

router = APIRouter()


class ChatRequest(BaseModel):
    matterId: UUID
    message: str
    mode: str = Field("general", pattern="^(general|precedent|limitation|draft)$")
    filters: Dict[str, Any] = {}


class Citation(BaseModel):
    authority_id: str
    para_ids: List[int]


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
    runId: UUID
    merkleRoot: Optional[str] = None
    notarization: Optional[Dict[str, Any]] = None


async def _run_agent_safe(name: str, agent, query: str, packs: list, matter_docs: list) -> tuple[str, dict]:
    try:
        output = await agent.run(query, packs, matter_docs)
        return name, output
    except Exception as e:
        log.error("agent.error", agent=name, error=str(e))
        return name, {"reasoning": f"Agent {name} unavailable: {str(e)}", "sources": [], "confidence": 0.1}


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    clerk_id = user["id"]
    db_user_id = str(await crud.resolve_db_user_id(db, clerk_id, user.get("email", "")))

    log.info("chat.start", user_id=clerk_id, mode=req.mode, message_length=len(req.message))

    # Step 1: PII Detection and Redaction
    pii_result = redact_user_input(req.message, clerk_id, mode="placeholder")
    redacted_message = pii_result["redacted_text"]

    if pii_result["has_pii"]:
        log.warning("chat.pii_detected", user_id=clerk_id, pii_count=len(pii_result["pii_detected"]))
        for pii_detection in pii_result["pii_detected"]:
            pii_record = PIIRecord(
                user_id=_uuid.UUID(db_user_id),
                pii_type=pii_detection["type"],
                detection_confidence=pii_detection["confidence"],
                redacted_count=1,
            )
            if pii_detection["confidence"] >= 0.8:
                pii_record.encrypt_original(pii_detection["value"], clerk_id)
            db.add(pii_record)

    # Step 2: Billing pre-flight (skipped in development)
    from app.core.config import get_settings
    if get_settings().ENVIRONMENT != "development":
        billing_result = await calculate_and_debit_query_cost(
            db, db_user_id, None, redacted_message, req.mode, req.filters, sources_count=12
        )
        if not billing_result["success"]:
            dummy_run_id = uuid4()
            return ChatResponse(
                answer=f"**Insufficient Credits**: {billing_result.get('shortfall', 0)} credits short.\n\nPlease purchase more credits to continue.",
                citations=[],
                runId=dummy_run_id,
                merkleRoot=None,
            )

    # Step 3: Retrieval
    packs = await retrieve_packs(db, redacted_message, limit=12, filters=req.filters)

    # Step 4: Load matter documents for agent context
    matter_docs_result = await db.execute(
        text("""
            SELECT d.id, d.storage_path, d.filetype, a.title, a.court, a.neutral_cite
            FROM documents d
            LEFT JOIN authorities a ON a.storage_path = d.storage_path
            WHERE d.matter_id = :mid
            ORDER BY d.created_at DESC LIMIT 5
        """),
        {"mid": str(req.matterId)}
    )
    matter_docs = [dict(r._mapping) for r in matter_docs_result.fetchall()]

    # Step 5: Run all 7 agents in parallel
    agents = {
        "statute": StatuteAgent(),
        "precedent": PrecedentAgent(),
        "limitation": LimitationAgent(),
        "risk": RiskAgent(),
        "devil": DevilAgent(),
        "ethics": EthicsAgent(),
        "drafting": DraftingAgent(),
    }

    results = await asyncio.gather(*[
        _run_agent_safe(name, agent, redacted_message, packs, matter_docs)
        for name, agent in agents.items()
    ])
    agent_outputs = dict(results)

    # Step 6: Aggregate with MWU voting
    agg = aggregate(agent_outputs, query=redacted_message)

    # Step 7: Build citations from packs
    citations = []
    for pack in packs:
        auth_id = pack.get("authority_id")
        if auth_id:
            citations.append(Citation(
                authority_id=str(auth_id),
                para_ids=[p.get("para_id", 0) for p in pack.get("paras", [])]
            ))

    # Step 8: Persist query + run
    q = await crud.create_query(
        db, matter_id=req.matterId, message=req.message, mode=req.mode, filters_json=req.filters
    )

    if pii_result["has_pii"]:
        await db.execute(text("""
            UPDATE pii_records
            SET query_id = :query_id
            WHERE user_id = :user_id AND query_id IS NULL
            AND created_at >= NOW() - INTERVAL '1 hour'
        """), {"query_id": str(q.id), "user_id": db_user_id})

    r = await crud.create_run(
        db,
        query_id=q.id,
        answer_text=agg["answer"],
        confidence=agg.get("confidence", 0.0),
        retrieval_set_json=packs
    )

    # Update billing ledger with run_id
    await db.execute(text("""
        UPDATE billing_ledger
        SET run_id = :run_id
        WHERE id = (
            SELECT id FROM billing_ledger
            WHERE user_id = :user_id AND run_id IS NULL
            AND created_at >= NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC LIMIT 1
        )
    """), {"run_id": str(r.id), "user_id": db_user_id})

    # Step 9: Store agent votes
    for agent_name, output in agent_outputs.items():
        await crud.create_agent_vote(
            db,
            run_id=r.id,
            agent=agent_name,
            decision_json=output,
            confidence=output["confidence"],
            aligned=(agent_name in agg.get("aligned", [])),
            weights_before=agg.get("weights_before", {}),
            weights_after=agg.get("weights", {})
        )

    confidence_pct = f"{agg.get('confidence', 0):.0%}"
    answer_with_meta = (
        agg["answer"]
        + f"\n\n---\n*Confidence: {confidence_pct} · Mode: {req.mode} · Sources: {len(packs)}*"
    )

    return ChatResponse(
        answer=answer_with_meta,
        citations=citations[:5],
        runId=r.id,
        merkleRoot=None
    )


@router.get("/conversation/{matter_id}")
async def get_conversation(matter_id: UUID, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    history = await crud.get_queries_by_matter(db, matter_id)
    return {"messages": history}


@router.delete("/conversation/{matter_id}")
async def clear_conversation(matter_id: UUID, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    success = await crud.delete_queries_by_matter(db, matter_id)
    return {"success": success}


@router.get("/conversation/{matter_id}/export")
async def export_conversation(matter_id: UUID, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    history = await crud.get_queries_by_matter(db, matter_id)
    lines = []
    for msg in history:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")
        lines.append(f"[{ts}] {role}:\n{content}\n")
    text_content = "\n".join(lines)
    import base64
    encoded = base64.b64encode(text_content.encode()).decode()
    return {"download_url": f"data:text/plain;base64,{encoded}", "matter_id": str(matter_id)}
