"""
Indian Kanoon API Client

Provides programmatic access to Indian legal documents via api.indiankanoon.org.
Supports search, document retrieval, citation lookup, and statute queries.

API docs: https://api.indiankanoon.org/documentation/
Registration: https://api.indiankanoon.org/
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rate limiting: 10 req/s max — we stay well under at 5/s
REQUESTS_PER_SECOND = 5
MIN_INTERVAL = 1.0 / REQUESTS_PER_SECOND

# Timeouts
TIMEOUT_SECONDS = 15

# Max results
MAX_RESULTS = 50

# ---------------------------------------------------------------------------
# Rate-limit lock (async-safe)
# ---------------------------------------------------------------------------

_rate_lock = asyncio.Lock()
_last_request_time: float = 0.0


def _get_base_url() -> str:
    """Return configured Indian Kanoon base URL."""
    return (get_settings().INDIAN_KANOON_BASE_URL or "https://api.indiankanoon.org").rstrip("/")


async def _rate_limited_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with client-side rate limiting (async-safe)."""
    global _last_request_time

    async with _rate_lock:
        now = time.monotonic()
        since_last = now - _last_request_time
        if since_last < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - since_last)

        headers = _build_headers()
        # Merge headers: auth headers from _build_headers take precedence
        merged_headers = {**kwargs.pop("headers", {}), **headers}

        try:
            response = await client.request(
                method, url, timeout=TIMEOUT_SECONDS, headers=merged_headers, **kwargs
            )
            _last_request_time = time.monotonic()
            return response
        except httpx.TimeoutException:
            log.warning("indian_kanoon.timeout", url=url)
            raise
        except httpx.HTTPStatusError as e:
            log.warning("indian_kanoon.http_error", url=url, status=e.response.status_code)
            raise
        except httpx.RequestError as e:
            log.warning("indian_kanoon.request_error", url=url, error=str(e))
            raise


def _build_headers() -> Dict[str, str]:
    """Build standard headers including auth token if configured."""
    headers: Dict[str, str] = {
        "Accept": "application/json",
    }
    settings = get_settings()
    token = settings.INDIAN_KANOON_API_TOKEN
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


def _is_configured() -> bool:
    """Check if the Indian Kanoon API token is configured."""
    return bool(get_settings().INDIAN_KANOON_API_TOKEN)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search(
    query: str,
    pagenum: int = 0,
    doctypes: Optional[str] = None,
    fromdate: Optional[str] = None,
    todate: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
    bench: Optional[str] = None,
    cite: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """
    Search Indian Kanoon for legal documents.

    Parameters
    ----------
    query : str
        Free-text search query. Supports operators: ANDD, ORR, NOTT, phrase "quotes".
    pagenum : int
        Page number (zero-indexed).
    doctypes : str | None
        Comma-separated court/doc type filters, e.g. "supremecourt,delhi".
    fromdate : str | None
        Start date in DD-MM-YYYY format.
    todate : str | None
        End date in DD-MM-YYYY format.
    title : str | None
        Filter by words in document title.
    author : str | None
        Filter by judge/author name.
    bench : str | None
        Filter by bench name.
    cite : str | None
        Filter by citation (e.g. "1993 AIR").
    max_results : int
        Max results across all pages fetched (capped at 50).

    Returns
    -------
    dict with keys: results, total, query, took, page
    """
    if not query or not query.strip():
        return {"results": [], "total": 0, "query": query, "took": 0, "page": 0}

    if not _is_configured():
        log.warning("indian_kanoon.not_configured", query=query)
        return {"results": [], "total": 0, "query": query, "took": 0, "page": 0,
                "error": "Indian Kanoon API token not configured. Set INDIAN_KANOON_API_TOKEN in .env"}

    params: Dict[str, Any] = {
        "formInput": query.strip(),
        "pagenum": pagenum,
    }

    if doctypes:
        params["doctypes"] = doctypes
    if fromdate:
        params["fromdate"] = fromdate
    if todate:
        params["todate"] = todate
    if title:
        params["title"] = title
    if author:
        params["author"] = author
    if bench:
        params["bench"] = bench
    if cite:
        params["cite"] = cite

    log.info("indian_kanoon.search", query=query, params={k: v for k, v in params.items() if k != "formInput"})

    base_url = _get_base_url()
    start_time = time.time()
    t0 = time.monotonic()

    try:
        async with httpx.AsyncClient() as client:
            # Indian Kanoon API requires POST with formInput as a form-encoded body param
            response = await _rate_limited_request(
                client, "POST", f"{base_url}/search/",
                data={"formInput": query.strip(), "pagenum": pagenum},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        log.error("indian_kanoon.search_failed", query=query, error=str(e))
        return {"results": [], "total": 0, "query": query, "took": int((time.monotonic() - t0) * 1000),
                "error": str(e)}

    took_ms = int((time.time() - start_time) * 1000)

    # Normalise Indian Kanoon response to our format
    results = _normalize_search_results(data.get("results", []), query)

    return {
        "results": results[:max_results],
        "total": data.get("total", 0),
        "query": query,
        "took": took_ms,
        "page": pagenum,
    }


async def get_document(docid: int) -> Optional[Dict[str, Any]]:
    """
    Fetch full document content from Indian Kanoon.
    """
    if not _is_configured():
        log.warning("indian_kanoon.not_configured")
        return None

    base_url = _get_base_url()
    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client, "GET", f"{base_url}/doc/{docid}/"
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("indian_kanoon.doc_fetch_failed", docid=docid, error=str(e))
        return None


async def get_doc_metadata(docid: int) -> Optional[Dict[str, Any]]:
    """
    Fetch document metadata (title, court, citations, etc.) from Indian Kanoon.
    """
    if not _is_configured():
        return None

    base_url = _get_base_url()
    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client, "GET", f"{base_url}/docmeta/{docid}/"
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        log.error("indian_kanoon.doc_meta_failed", docid=docid, error=str(e))
        return None


async def search_citations(
    citation: str,
    doctypes: Optional[str] = None,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Search by specific legal citation.

    Parameters
    ----------
    citation : str
        Legal citation, e.g. "(1993) 3 SCC 1", "AIR 1950 SC 1"
    doctypes : str | None
        Optional court filters (comma-separated).
    max_results : int
        Max results.

    Returns
    -------
    dict with results key.
    """
    return await search(
        query=citation,
        cite=citation,
        doctypes=doctypes,
        max_results=max_results,
    )


async def search_statute(
    statute_name: str,
    section: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """
    Search for documents related to a specific statute.

    Parameters
    ----------
    statute_name : str
        Name of the statute, e.g. "Indian Penal Code", "IPC"
    section : str | None
        Specific section, e.g. "302", "Section 302"
    max_results : int
        Max results.
    """
    if section:
        section_clean = re.sub(r'^(Section|Sec|S\.?)\s*', '', section, flags=re.IGNORECASE)
        query = f'{statute_name} Section {section_clean}'
    else:
        query = statute_name

    return await search(query=query, max_results=max_results)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalize_search_results(
    raw_results: List[Dict[str, Any]],
    query: str,
) -> List[Dict[str, Any]]:
    """
    Convert Indian Kanoon API results to the GemmaFinOS standard search result format.
    """
    normalized = []
    for item in raw_results:
        docid = item.get("docid")
        title = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()
        headnote = item.get("headnote", "").strip()
        court = item.get("court", "").strip()
        citation_str = item.get("citation", "").strip()

        excerpt = snippet or headnote
        if excerpt:
            excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()

        doc_type = _infer_type(court, title)
        date_str = _extract_date(item)

        normalized.append({
            "id": str(docid),
            "title": title or f"Document {docid}",
            "description": court or "Indian Kanoon",
            "type": doc_type,
            "date": date_str,
            "source": court or "Indian Kanoon",
            "relevance_score": _calculate_relevance(item, query),
            "url": f"https://indiankanoon.org/doc/{docid}/" if docid else None,
            "excerpt": excerpt[:500] if excerpt else None,
            "docid": docid,
            "citation": citation_str,
            "authority_id": str(docid),
        })

    return normalized


def _infer_type(court: str, title: str) -> str:
    """Infer document type from court name and title."""
    court_upper = court.upper()

    if "SUPREME" in court_upper:
        return "case"
    if "HIGH COURT" in court_upper:
        return "case"
    if "TRIBUNAL" in court_upper:
        return "precedent"
    if re.search(r'\bACT\b|\bCODE\b|\bRULES\b|\bREGULATIONS?\b', title, re.IGNORECASE):
        return "statute"
    if re.search(r'\bIPC\b|\bCRPC\b|\bCPC\b|\bCONSTITUTION\b', title, re.IGNORECASE):
        return "statute"

    return "case"


def _extract_date(item: Dict[str, Any]) -> Optional[str]:
    """Extract date from Indian Kanoon result."""
    for field in ("date", "decided_on", "judgment_date"):
        val = item.get(field)
        if val:
            return str(val)[:10]

    citation = item.get("citation", "")
    match = re.search(r'(19|20)\d{2}', citation)
    if match:
        return f"{match.group(0)}-01-01"

    return None


def _calculate_relevance(item: Dict[str, Any], query: str) -> float:
    """Calculate a relevance score (0-1) for Indian Kanoon result."""
    confidence = item.get("confidence")
    if confidence is not None:
        try:
            return min(1.0, float(confidence) / 100.0)
        except (ValueError, TypeError):
            pass

    score = 0.5
    query_terms = query.lower().split()
    if not query_terms:
        return score

    title_lower = item.get("title", "").lower()
    title_matches = sum(1 for t in query_terms if t in title_lower)
    score += 0.3 * min(1.0, title_matches / len(query_terms))

    snippet_lower = (item.get("snippet", "") or item.get("headnote", "")).lower()
    snippet_matches = sum(1 for t in query_terms if t in snippet_lower)
    score += 0.2 * min(1.0, snippet_matches / len(query_terms))

    return min(1.0, score)


# ---------------------------------------------------------------------------
# Utility: map GemmaFinOS filter keys → Indian Kanoon query params
# ---------------------------------------------------------------------------

def filters_to_ik_params(filters: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Convert GemmaFinOS filter dict to Indian Kanoon API query parameters.
    Returns a flat dict of string values suitable for passing as **kwargs
    to the search() function.
    """
    params: Dict[str, str] = {}
    if not filters:
        return params

    court_doctype_map = {
        "sc": "supremecourt",
        "hc-del": "delhi",
        "hc-bom": "bombay",
        "hc-mad": "madras",
        "hc-cal": "calcutta",
        "hc-kar": "karnataka",
        "hc-ker": "kerala",
        "hc-raj": "rajasthan",
        "hc-guj": "gujarat",
        "hc-pun": "punjabandharyana",
        "hc-mp": "madhyapradesh",
        "hc-all": "allahabad",
        "hc-pat": "patna",
        "hc-ori": "orissa",
        "hc-utt": "uttarakhand",
        "hc-hp": "himachalpradesh",
        "hc-j&k": "jammuandkashmir",
        "hc-sik": "sikkim",
        "hc-tri": "tripura",
        "hc-man": "manipur",
        "hc-meg": "meghalaya",
        "hc-gau": "gauhati",
    }

    court_codes = filters.get("court")
    if court_codes:
        if isinstance(court_codes, str):
            court_codes = [court_codes]
        doctypes = []
        for code in court_codes:
            mapped = court_doctype_map.get(code.lower().strip())
            if mapped:
                doctypes.append(mapped)
        if doctypes:
            params["doctypes"] = ",".join(sorted(set(doctypes)))

    year_filter = filters.get("year")
    if isinstance(year_filter, dict):
        year_from = year_filter.get("from")
        year_to = year_filter.get("to")
        if year_from:
            params["fromdate"] = f"01-01-{year_from}"
        if year_to:
            params["todate"] = f"31-12-{year_to}"
    elif isinstance(year_filter, int):
        params["fromdate"] = f"01-01-{year_filter}"
        params["todate"] = f"31-12-{year_filter}"

    judge = filters.get("judge")
    if judge and isinstance(judge, str):
        params["author"] = judge

    return params
