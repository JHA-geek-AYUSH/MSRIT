from __future__ import annotations

from typing import Any, Dict, List
import structlog

log = structlog.get_logger()


async def verify_comprehensive(answer: str, sources: List[Dict[str, Any]],
                               retrieval_set: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Lightweight verification that never blocks a response.
    When retrieval_set is empty (no legal data indexed yet), passes with a warning.
    """
    if not retrieval_set and not sources:
        return {
            "valid": True,
            "confidence": 0.6,
            "flags": ["no_sources_available"],
            "verification_level": "low",
            "summary": "No indexed legal sources available — answer based on LLM knowledge only",
            "individual_results": {},
            "passed_checks": 0,
            "failed_checks": 0,
            "total_checks": 0,
        }

    flags = []
    confidence_scores = []

    # 1. Basic answer quality check
    if len(answer) < 100:
        flags.append("answer_too_short")
        confidence_scores.append(0.3)
    else:
        confidence_scores.append(0.8)

    # 2. Citation presence check
    import re
    has_citations = bool(re.search(
        r'[Ss]ection\s+\d+|[Aa]rticle\s+\d+|v\.\s+[A-Z]|\bIPC\b|\bCrPC\b|\bSCC\b|\bAIR\b',
        answer
    ))
    if has_citations:
        confidence_scores.append(0.85)
    else:
        flags.append("no_legal_citations")
        confidence_scores.append(0.6)

    # 3. Source coverage
    if retrieval_set:
        confidence_scores.append(0.85)
    else:
        confidence_scores.append(0.5)

    overall_confidence = sum(confidence_scores) / len(confidence_scores)

    if overall_confidence >= 0.8:
        level = "high"
    elif overall_confidence >= 0.6:
        level = "medium"
    else:
        level = "low"

    return {
        "valid": True,  # Never block — let the answer through with confidence metadata
        "confidence": overall_confidence,
        "flags": flags,
        "verification_level": level,
        "summary": f"Verification {level} — {len(retrieval_set)} sources retrieved",
        "individual_results": {},
        "passed_checks": len(confidence_scores),
        "failed_checks": len(flags),
        "total_checks": len(confidence_scores),
    }


async def verify_basic(answer: str) -> Dict[str, Any]:
    return await verify_comprehensive(answer, [], [])
