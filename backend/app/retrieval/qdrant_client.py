from __future__ import annotations

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import get_settings

# Cache for Qdrant availability — avoids repeated connection timeouts
_qdrant_available: Optional[QdrantClient | bool] = None  # None=unchecked, False=unavailable, QdrantClient=connected


def get_qdrant() -> Optional[QdrantClient]:
    """Return a connected Qdrant client, or None if unavailable (cached)."""
    global _qdrant_available

    if _qdrant_available is False:
        return None
    if _qdrant_available is not None:
        return _qdrant_available

    s = get_settings()
    try:
        client = QdrantClient(url=s.QDRANT_URL, api_key=s.QDRANT_API_KEY, timeout=2)
        # Quick health check — list collections to confirm connectivity
        _ = client.get_collections()
        _qdrant_available = client
        return client
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.warning("qdrant.connection_failed", error=str(e), url=s.QDRANT_URL)
        _qdrant_available = False  # Cache: don't retry
        return None


def reset_qdrant_cache() -> None:
    """Reset the cached connection state (e.g., after Qdrant becomes available)."""
    global _qdrant_available
    _qdrant_available = None


def ensure_collection() -> None:
    s = get_settings()
    client = get_qdrant()
    if client is None:
        return  # Qdrant not available, skip

    try:
        if s.QDRANT_COLLECTION in [c.name for c in client.get_collections().collections]:
            return
    except Exception:
        return  # Skip on error

    client.create_collection(
        collection_name=s.QDRANT_COLLECTION,
        vectors=qm.VectorParams(size=3072, distance=qm.Distance.COSINE),
        hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=128),
        optimizers_config=qm.OptimizersConfigDiff(memmap_threshold=200_000_000),
        quantization_config=qm.ScalarQuantization(scalar=qm.ScalarQuantizationConfig(type="int8", always_ram=False)),
    )
    for field, ftype in [
        ("court", qm.PayloadSchemaType.KEYWORD),
        ("year", qm.PayloadSchemaType.INTEGER),
        ("has_citation", qm.PayloadSchemaType.BOOL),
        ("statute_tags", qm.PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(s.QDRANT_COLLECTION, field_name=field, field_schema=qm.PayloadSchemaType(ftype))


def search(query_vector: List[float], filters: Optional[Dict[str, Any]] = None, top_k: int = 24) -> List[qm.ScoredPoint]:
    s = get_settings()
    client = get_qdrant()
    if client is None:
        return []

    try:
        qfilter = None
        if filters:
            must = []
            for k, v in filters.items():
                if isinstance(v, list):
                    must.append(qm.FieldCondition(key=k, match=qm.MatchAny(any=v)))
                else:
                    must.append(qm.FieldCondition(key=k, match=qm.MatchValue(value=v)))
            qfilter = qm.Filter(must=must)
        return client.search(collection_name=s.QDRANT_COLLECTION, query_vector=query_vector, limit=top_k, query_filter=qfilter)
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.warning("qdrant.search_failed", error=str(e))
        return []


