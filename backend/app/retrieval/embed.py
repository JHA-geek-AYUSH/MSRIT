"""Local, deterministic embedding and Qdrant indexing utilities.

The retrieval layer deliberately avoids hosted embedding APIs.  A fixed-width
feature-hashing vector is stable across processes, requires no credentials, and
keeps GemmaFinOS's only generative model dependency limited to Gemma.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, List, Dict

import structlog
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize
from qdrant_client.http import models as qm

from app.core.config import get_settings
from app.retrieval.qdrant_client import get_qdrant

log = structlog.get_logger()

VECTOR_SIZE = 3072
BATCH_SIZE = 100
_vectorizer = HashingVectorizer(
    n_features=VECTOR_SIZE,
    alternate_sign=False,
    norm="l2",
    analyzer="word",
    ngram_range=(1, 2),
    lowercase=True,
)


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    """Produce deterministic, normalized 3072-dimensional vectors locally."""
    materialized = list(texts)
    if not materialized:
        return []
    matrix = normalize(_vectorizer.transform(materialized), norm="l2", copy=False)
    return matrix.toarray().astype("float32").tolist()


async def embed_chunks_batch(chunks: List[Dict[str, Any]], authority_metadata: Dict[str, Any]) -> List[str]:
    """Embed and index chunks.  Never returns fabricated IDs when indexing fails."""
    if not chunks:
        return []
    settings = get_settings()
    qdrant = get_qdrant()
    if qdrant is None:
        log.warning("embed.qdrant_unavailable", chunks_count=len(chunks))
        return []

    vector_ids: List[str] = []
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        try:
            vectors = embed_texts(chunk["text"] for chunk in batch)
            points = []
            for offset, (chunk, vector) in enumerate(zip(batch, vectors)):
                chunk_key = f"{authority_metadata['id']}:{chunk.get('para_from')}:{chunk.get('para_to')}:{start + offset}"
                vector_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_key))
                points.append(qm.PointStruct(id=vector_id, vector=vector, payload=_build_qdrant_payload(chunk, authority_metadata)))
                vector_ids.append(vector_id)
            qdrant.upsert(collection_name=settings.QDRANT_COLLECTION, points=points, wait=True)
        except Exception as exc:
            log.error("embed.batch_error", batch_start=start, error=str(exc))
            del vector_ids[-len(batch):]
    return vector_ids


def _build_qdrant_payload(chunk: Dict[str, Any], authority_metadata: Dict[str, Any]) -> Dict[str, Any]:
    date = authority_metadata.get("date")
    year = getattr(date, "year", None)
    payload = {
        "chunk_id": f"{authority_metadata['id']}_{chunk.get('para_from')}_{chunk.get('para_to')}",
        "authority_id": str(authority_metadata["id"]),
        "court": authority_metadata.get("court", "UNKNOWN"),
        "year": year,
        "statute_tags": chunk.get("statute_tags", []),
        "has_citation": chunk.get("has_citation", False),
        "neutral_cite": authority_metadata.get("neutral_cite"),
        "reporter_cite": authority_metadata.get("reporter_cite"),
        "chunk_type": chunk.get("chunk_type", "content"),
        "para_from": chunk.get("para_from"),
        "para_to": chunk.get("para_to"),
        "token_count": chunk.get("tokens", 0),
    }
    return {key: value for key, value in payload.items() if value is not None}


def embed_single_query(query: str) -> List[float]:
    return embed_texts([query])[0] if query.strip() else [0.0] * VECTOR_SIZE


async def reindex_authority(authority_id: str, chunks: List[Dict[str, Any]], authority_metadata: Dict[str, Any]) -> bool:
    settings = get_settings()
    qdrant = get_qdrant()
    if qdrant is None:
        return False
    try:
        qdrant.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=qm.FilterSelector(filter=qm.Filter(must=[qm.FieldCondition(key="authority_id", match=qm.MatchValue(value=str(authority_id)))])),
            wait=True,
        )
        return bool(await embed_chunks_batch(chunks, authority_metadata))
    except Exception as exc:
        log.error("reindex.failed", authority_id=authority_id, error=str(exc))
        return False
