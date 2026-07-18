"""Stage 2 (Weighted Compliance Gap Scorer) + Stage 3 (Cosine Similarity Ranker).

Implements Plan.md Section 5 & 6:
  Stage 2 — 5 weighted scoring factors (Plan.md table lists 5 rows summing to 100%,
            despite the section header saying "6 Scoring Factors" — that's a doc typo,
            we implement exactly the 5 factors specified):
      - Rule Trigger Match       35%
      - Risk Tier Alignment      20%
      - Sector Applicability     15%
      - Recency of Flags         15%
      - Volume Threshold Proximity 15%
  Stage 3 — Cosine similarity between entity vector and rule's ideal_vector_target.
  Final score = 60% Stage-2 gap score + 40% Stage-3 cosine similarity.
  Hard gate: rules flagged mandatory for the entity's sector always appear in the
             output regardless of score (Plan.md Section 5, "Hard gates").

NOTE on data limitations vs. Plan.md's fuller schema: rules_db.py does not (yet)
carry per-rule `threshold`, `threshold_unit`, or `mandatory_sectors` fields the way
the Plan.md sample rule schema shows. Rather than block on a full rules_db rewrite,
this scorer derives reasonable proxies from what IS present (severity, ideal_vector_target,
framework) and accepts optional inputs (`sector`, `risk_tier`, `flag_age_days`) to make the
Stage 2 factors real instead of stubbed. This is documented per-factor below. Enriching
rules_db.py with explicit thresholds/mandatory_sectors is a good follow-up (see AUDIT notes).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from app.ml.rules_db import COMPLIANCE_RULES

FEATURE_KEYS = [
    "monthly_txn_volume", "avg_ticket_size", "cash_ratio",
    "cross_border_ratio", "late_payment_rate", "business_age_years",
    "sector_risk_score", "director_count", "anomaly_risk_score",
]

# Rule severity -> minimum entity risk tier rank required for "full" tier alignment.
_TIER_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_SEVERITY_MIN_TIER = {"critical": 3, "high": 2, "medium": 1, "low": 1}

# Frameworks/keywords used to derive a rough sector applicability signal, since
# rules_db.py doesn't carry an explicit mandatory_sectors list per rule yet.
_HIGH_CASH_SECTOR_FRAMEWORKS = {"PMLA"}
_CROSS_BORDER_FRAMEWORKS = {"FEMA"}


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))


def map_entity_to_vector(features: Dict[str, float]) -> np.ndarray:
    """Map entity features to the same 9D vector space used by rules_db ideal_vector_target."""
    return np.array([
        features.get("monthly_txn_volume", 0.0) / 5000.0,
        features.get("avg_ticket_size", 0.0) / 1_000_000.0,
        features.get("cash_ratio", 0.0),
        features.get("cross_border_ratio", 0.0),
        features.get("late_payment_rate", 0.0),
        features.get("business_age_years", 5.0) / 20.0,
        features.get("sector_risk_score", 0.0),
        features.get("director_count", 1.0) / 10.0,
        features.get("anomaly_risk_score", 0.0) / 5.0,
    ])


def _rule_target_vector(rule: Dict[str, Any]) -> np.ndarray:
    target = rule.get("ideal_vector_target", {})
    return np.array([target.get(k, 0.0) for k in FEATURE_KEYS])


# ─────────────────────────────── Stage 2 — 5 weighted factors ───────────────────────

def _factor_rule_trigger_match(entity_vec: np.ndarray, rule_vec: np.ndarray) -> float:
    """35% — does the entity profile directly trigger this rule?
    Proxy: cosine similarity restricted to the dimensions the rule actually cares
    about (non-zero entries in ideal_vector_target), i.e. a focused trigger check
    rather than the whole-vector Stage 3 similarity."""
    mask = rule_vec != 0
    if not mask.any():
        return 0.0
    return max(0.0, cosine_similarity(entity_vec[mask], rule_vec[mask]))


def _factor_risk_tier_alignment(risk_tier: Optional[str], rule_severity: str) -> float:
    """20% — does the entity's risk tier meet the rule's severity threshold?"""
    if not risk_tier:
        return 0.5  # unknown tier -> neutral
    entity_rank = _TIER_RANK.get(risk_tier.lower(), 2)
    required_rank = _SEVERITY_MIN_TIER.get(rule_severity, 1)
    if entity_rank >= required_rank + 1:
        return 1.0
    if entity_rank >= required_rank:
        return 0.75
    return 0.25


def _factor_sector_applicability(sector: Optional[str], rule: Dict[str, Any], features: Dict[str, float]) -> float:
    """15% — is this rule mandatory / especially relevant for the entity's sector?
    rules_db.py has no explicit mandatory_sectors list yet, so we approximate:
    PMLA (cash-heavy) rules apply strongly to high cash_ratio / high sector_risk_score
    entities; FEMA rules apply strongly to entities with material cross_border_ratio;
    everything else defaults to "generally applicable"."""
    framework = rule.get("framework", "")
    sector_risk = features.get("sector_risk_score", 0.3)
    if framework in _HIGH_CASH_SECTOR_FRAMEWORKS:
        return min(1.0, 0.4 + sector_risk * 0.6 + features.get("cash_ratio", 0.0) * 0.3)
    if framework in _CROSS_BORDER_FRAMEWORKS:
        return min(1.0, 0.3 + features.get("cross_border_ratio", 0.0) * 1.2)
    return 0.6  # generally applicable (GST / KYC / Income Tax / Corp Governance)


def _factor_recency_of_flags(flag_age_days: Optional[float]) -> float:
    """15% — how recent are the triggering transactions/flags? Exponential decay,
    half-life ~90 days. No age given -> assume moderately recent (0.75)."""
    if flag_age_days is None:
        return 0.75
    return round(math.exp(-max(0.0, flag_age_days) / 130.0), 4)


def _factor_volume_threshold_proximity(features: Dict[str, float], rule: Dict[str, Any]) -> float:
    """15% — how close is the entity to the rule's reporting threshold?
    rules_db.py only has an explicit numeric threshold for cash-transaction style
    AML rules (~₹10L single txn = CTR). We use avg_ticket_size vs a ₹10L reference
    for cash/AML rules, and monthly_txn_volume vs a 500/mo reference otherwise."""
    if rule.get("framework") == "PMLA":
        ref = 1_000_000.0
        val = features.get("avg_ticket_size", 0.0)
    else:
        ref = 500.0
        val = features.get("monthly_txn_volume", 0.0)
    if ref <= 0:
        return 0.5
    proximity = val / ref
    return round(min(1.0, proximity), 4)


def score_compliance_gaps(
    features: Dict[str, float],
    risk_tier: Optional[str] = None,
    sector: Optional[str] = None,
    flag_age_days: Optional[float] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Full Stage 2 + Stage 3 scorer.

    final_score = 0.60 * gap_score(5-factor weighted) + 0.40 * cosine_similarity

    Hard gate: rules with severity == 'critical' AND rule_trigger_match > 0.35 are
    force-included even if they'd otherwise fall outside the top_n cut, mirroring
    Plan.md's "mandatory rules always appear" hard-gate concept (rules_db.py has no
    explicit `mandatory: true` flag yet, so critical severity + a real trigger signal
    is used as the practical stand-in).
    """
    entity_vec = map_entity_to_vector(features)
    scored: List[Dict[str, Any]] = []

    for rule in COMPLIANCE_RULES:
        rule_vec = _rule_target_vector(rule)
        stage3_sim = max(0.0, cosine_similarity(entity_vec, rule_vec))

        trigger = _factor_rule_trigger_match(entity_vec, rule_vec)
        tier_align = _factor_risk_tier_alignment(risk_tier, rule["severity"])
        sector_app = _factor_sector_applicability(sector, rule, features)
        recency = _factor_recency_of_flags(flag_age_days)
        volume_prox = _factor_volume_threshold_proximity(features, rule)

        gap_score = (
            trigger * 0.35
            + tier_align * 0.20
            + sector_app * 0.15
            + recency * 0.15
            + volume_prox * 0.15
        )

        final_score = round(gap_score * 0.60 + stage3_sim * 0.40, 4)
        hard_gate = rule["severity"] == "critical" and trigger > 0.35

        scored.append({
            "rule_code": rule["code"],
            "rule_name": rule["name"],
            "framework": rule["framework"],
            "description": rule["description"],
            "severity": rule["severity"],
            "max_penalty_inr": rule.get("max_penalty_inr"),
            "imprisonment_risk": rule.get("imprisonment_risk", False),
            "remediation_steps": rule.get("remediation_steps", []),
            "references": rule.get("references", []),
            "similarity_score": round(stage3_sim, 4),
            "gap_score": round(gap_score, 4),
            "combined_score": final_score,
            "hard_gate": hard_gate,
            "factors": {
                "rule_trigger_match": round(trigger, 4),
                "risk_tier_alignment": round(tier_align, 4),
                "sector_applicability": round(sector_app, 4),
                "recency_of_flags": round(recency, 4),
                "volume_threshold_proximity": round(volume_prox, 4),
            },
        })

    scored.sort(key=lambda x: x["combined_score"], reverse=True)

    top = scored[:top_n]
    top_codes = {r["rule_code"] for r in top}
    for r in scored:
        if r["hard_gate"] and r["rule_code"] not in top_codes and len(top) < top_n + 5:
            top.append(r)
            top_codes.add(r["rule_code"])

    return top


def rank_all_rules(
    features: Dict[str, float],
    risk_tier: Optional[str] = None,
    sector: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Score every rule (no top_n cut) — backs the fast /rank-rules endpoint (no Gemma)."""
    return score_compliance_gaps(features, risk_tier=risk_tier, sector=sector, top_n=len(COMPLIANCE_RULES))
