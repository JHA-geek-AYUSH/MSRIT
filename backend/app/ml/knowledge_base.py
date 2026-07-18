"""Platform Knowledge Base — local TF-IDF retrieval index over the project's own
docs (Plan.md, README, the 40-rule catalogue, penalty scenarios) so the agent can
answer end-to-end questions about the platform itself — "how does the risk score
work", "what happens if I don't file an STR", "what does gap_score mean" — not
just questions about a specific assessment.

Deliberately NOT an embeddings-API-based RAG: TF-IDF (scikit-learn, already a
dependency) keeps this Gemma-only-compliant — no OpenAI embeddings call sneaks
into the "Gemma models only" pipeline. Retrieval is local and instant; only the
final answer synthesis goes through Gemma.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import structlog

from app.ml.rules_db import COMPLIANCE_RULES
from app.core.gemma_client import get_llm_client_or_none, get_llm_model

log = structlog.get_logger()

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

DOC_SOURCES = [
    os.path.join(_PROJECT_ROOT, "Plan.md"),
    os.path.join(_PROJECT_ROOT, "README.md"),
    os.path.join(_PROJECT_ROOT, "README_FINAL.md"),
    os.path.join(_PROJECT_ROOT, "QUICKSTART.md"),
]


def _chunk_text(text: str, source: str, chunk_size: int = 600, overlap: int = 100) -> List[Dict[str, str]]:
    # Split on markdown headers first so chunks stay topically coherent
    sections = re.split(r"\n(?=#{1,3} )", text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= chunk_size:
            chunks.append({"text": section, "source": source})
            continue
        start = 0
        while start < len(section):
            chunk = section[start:start + chunk_size]
            chunks.append({"text": chunk, "source": source})
            start += chunk_size - overlap
    return chunks


class PlatformKnowledgeBase:
    """Lazily-built, process-lifetime TF-IDF index. Rebuild by constructing a new
    instance (cheap — a few hundred short chunks) if docs change during dev."""

    def __init__(self) -> None:
        self._chunks: List[Dict[str, str]] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None
        self._build()

    def _build(self) -> None:
        chunks: List[Dict[str, str]] = []

        for path in DOC_SOURCES:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        chunks.extend(_chunk_text(f.read(), os.path.basename(path)))
                except Exception as e:
                    log.warning("knowledge_base.doc_read_failed", path=path, error=str(e))

        # Fold in the rule catalogue and penalty scenarios as first-class,
        # queryable knowledge (not just narrative docs)
        for rule in COMPLIANCE_RULES:
            text = (
                f"{rule['code']} — {rule['name']} ({rule['framework']}, {rule['severity']} severity). "
                f"{rule['description']} Max penalty ₹{rule.get('max_penalty_inr', 0):,}. "
                f"Remediation: {'; '.join(rule.get('remediation_steps', []))}"
            )
            chunks.append({"text": text, "source": f"rules_db:{rule['code']}"})

        try:
            from app.api.v1.simulator import SCENARIOS
            for s in SCENARIOS:
                text = f"Penalty scenario '{s['name']}' ({s['rule_code']}): {s['description']} Base fine ₹{s['base_fine_inr']:,}, max ₹{s['max_fine_inr']:,}."
                chunks.append({"text": text, "source": f"penalty_scenario:{s['id']}"})
        except Exception as e:
            log.warning("knowledge_base.scenarios_load_failed", error=str(e))

        if not chunks:
            self._chunks = []
            return

        self._chunks = chunks
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self._matrix = self._vectorizer.fit_transform([c["text"] for c in chunks])

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._chunks or self._vectorizer is None:
            return []
        query_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._matrix)[0]
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [
            {"text": self._chunks[i]["text"], "source": self._chunks[i]["source"], "score": round(float(sims[i]), 4)}
            for i in top_idx if sims[i] > 0.05
        ]


_kb: Optional[PlatformKnowledgeBase] = None


def get_knowledge_base() -> PlatformKnowledgeBase:
    global _kb
    if _kb is None:
        _kb = PlatformKnowledgeBase()
    return _kb


async def answer_platform_question(question: str) -> Dict[str, Any]:
    """RAG over the platform's own docs/rules — retrieval is local TF-IDF (no
    embeddings API), synthesis goes through Gemma only, degrading to a raw
    excerpt list if no Gemma provider is available."""
    kb = get_knowledge_base()
    hits = kb.retrieve(question, top_k=5)
    if not hits:
        return {"answer": "I don't have indexed documentation to answer that yet.", "sources": []}

    context = "\n\n".join(f"[{h['source']}] {h['text']}" for h in hits)
    client = get_llm_client_or_none()
    if not client:
        return {
            "answer": "No Gemma provider available to synthesize an answer — here are the most relevant excerpts:\n\n" + context[:1500],
            "sources": [h["source"] for h in hits],
        }

    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[{
                "role": "user",
                "content": f"Answer the question using ONLY this context from the platform's own documentation and rule catalogue. "
                            f"Be concise (3-5 sentences). If the context doesn't cover it, say so.\n\nContext:\n{context}\n\nQuestion: {question}",
            }],
            temperature=0.2,
            max_tokens=300,
        )
        answer = resp.choices[0].message.content or "Couldn't generate an answer."
    except Exception as e:
        log.warning("knowledge_base.gemma_failed", error=str(e))
        answer = "Gemma call failed — here are the most relevant excerpts:\n\n" + context[:1500]

    return {"answer": answer, "sources": [h["source"] for h in hits]}
