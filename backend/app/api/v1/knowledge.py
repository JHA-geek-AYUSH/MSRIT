"""GET/POST /v1/knowledge/ask — Platform Knowledge Base (Plan.md, README, the 40-rule
catalogue, penalty scenarios), retrieved locally via TF-IDF and synthesized by Gemma.
Lets any role ask end-to-end platform questions ("how is the risk score computed",
"what happens if GST filing is late twice") without needing an active assessment.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.ml.knowledge_base import answer_platform_question

router = APIRouter()


class KnowledgeAskRequest(BaseModel):
    question: str = Field(..., min_length=3)


@router.post("/knowledge/ask")
async def ask_knowledge_base(req: KnowledgeAskRequest, user=Depends(current_user)):
    return await answer_platform_question(req.question)
