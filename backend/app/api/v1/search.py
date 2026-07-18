from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query as FastApiQuery
from pydantic import BaseModel

from app.core.security import current_user
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.retrieval.assemble import retrieve_packs
from app.retrieval.fts import fts_search
from app.retrieval.indian_kanoon import search as ik_search, filters_to_ik_params
from app.core.config import get_settings
import structlog

log = structlog.get_logger()

router = APIRouter()


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int
    query: str
    took: int


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = FastApiQuery(...),
    type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    ik_source: str = "true",
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()

    filters: Dict[str, Any] = {}
    if type and type in ("case", "statute", "document", "precedent"):
        filters["type"] = type
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    ik_enabled = ik_source.lower() in ("true", "1", "yes")
    seen_ids: set = set()
    results: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------
    # PRIMARY SOURCE: Indian Kanoon API (real-time legal DB)
    # Always returns within timeout, never hangs
    # ---------------------------------------------------------------
    ik_config = get_settings()
    if ik_enabled and ik_config.INDIAN_KANOON_API_TOKEN:
        try:
            # Enforce a 10-second timeout for the IK API call
            ik_result = await asyncio.wait_for(
                _search_indian_kanoon(q, offset, limit, type, filters),
                timeout=10.0,
            )
            for r in ik_result.get("results", []):
                rid = r.get("id") or r.get("docid")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    results.append(r)
            # If IK returned results, skip local fallback (faster)
            if results:
                took_ms = int((time.time() - start_time) * 1000)
                return SearchResponse(results=results[:max(limit, 1)], total=len(seen_ids), query=q, took=took_ms)
        except asyncio.TimeoutError:
            log.warning("search.ik_timeout", query=q)
        except Exception as e:
            log.warning("search.ik_error", error=str(e))

    # ---------------------------------------------------------------
    # SECONDARY SOURCE: Local DB + Qdrant (with timeout)
    # ---------------------------------------------------------------
    try:
        packs = await asyncio.wait_for(
            retrieve_packs(db, q, limit=offset + limit, filters=filters),
            timeout=8.0,
        )
        paginated = packs[offset:]

        for pack in paginated:
            court = pack.get("court", "").upper()
            if court in ("SC", "SUPREME COURT"):
                doc_type = "case"
            elif "HIGH COURT" in court or "HC" in court:
                doc_type = "case"
            elif "TRIBUNAL" in court:
                doc_type = "precedent"
            else:
                doc_type = type or "case"

            local_id = str(pack.get("authority_id", "unknown"))
            if local_id in seen_ids:
                continue
            seen_ids.add(local_id)

            results.append({
                "id": local_id,
                "title": pack.get("title", "Unknown Authority"),
                "description": pack.get("court", "Unknown Court"),
                "type": doc_type,
                "date": pack.get("date").isoformat() if pack.get("date") else None,
                "source": pack.get("court"),
                "relevance_score": round(pack.get("score", 0.0), 3),
                "url": pack.get("url"),
                "excerpt": (pack.get("paras") or [{}])[0].get("text", "")[:300] if pack.get("paras") else "",
                "neutral_cite": pack.get("neutral_cite"),
                "reporter_cite": pack.get("reporter_cite"),
            })
    except asyncio.TimeoutError:
        log.warning("search.local_db_timeout", query=q)
    except Exception as e:
        log.warning("search.local_db_error", error=str(e))

    took_ms = int((time.time() - start_time) * 1000)

    return SearchResponse(
        results=results[:max(limit, 1)],
        total=len(seen_ids),
        query=q,
        took=took_ms
    )


async def _search_indian_kanoon(q: str, offset: int, limit: int, type: Optional[str], filters: Dict[str, Any]) -> Dict[str, Any]:
    """Helper: build IK params and execute search."""
    ik_params = filters_to_ik_params(filters)
    if type:
        type_doctype_map = {
            "case": "supremecourt,supreme%20court,highcourts",
            "precedent": "tribunals",
        }
        mapped = type_doctype_map.get(type)
        if mapped:
            existing = ik_params.get("doctypes", "")
            ik_params["doctypes"] = f"{existing},{mapped}" if existing else mapped

    return await ik_search(
        query=q,
        pagenum=offset // max(limit, 1),
        max_results=offset + limit,
        **ik_params,
    )
