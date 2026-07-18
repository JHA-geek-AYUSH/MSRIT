"""Unified 3-stage compliance assessment pipeline (Plan.md Section 3 & 4).

Stage 0 -> anomaly_scorer.score_anomalies
Stage 1 -> risk_model_runner.predict_risk_tier (XGBoost)
Stage 2+3 -> compliance_scorer.score_compliance_gaps (5-factor gap score + cosine, 60/40)

This module is the single source of truth for "run the pipeline" — it backs:
  - POST /v1/compliance/assess
  - the agent's `reassess` / `threshold_sim` / `compare` tools
  - POST /v1/compliance/report

Previously this logic was duplicated ad-hoc inside app/agents/orchestrator.py.
That duplication is now removed; orchestrator/agent code calls into here instead.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.ml.anomaly_scorer import score_anomalies
from app.ml.compliance_scorer import score_compliance_gaps
from app.ml.risk_model_runner import extract_financial_features, predict_risk_tier

# The 12 transaction flag types from Plan.md Section 4, Stage 0, with light
# keyword triggers used by detect_flags_from_text() for the /parse-flags endpoint
# and for auto-detecting flags inside a free-text assessment description.
FLAG_KEYWORDS: Dict[str, List[str]] = {
    "large_cash_deposit": ["large cash deposit", "cash deposit exceeding", "cash deposit above", "10 lakh cash", "10l cash"],
    "round_number_transactions": ["round number", "round-number", "round amount transactions"],
    "rapid_succession_transfers": ["rapid succession", "multiple transfers within", "several transfers in a day", "24 hours transfers"],
    "structuring_pattern": ["structuring", "smurfing", "just below the threshold", "below reporting threshold"],
    "dormant_account_spike": ["dormant account", "inactive account", "sudden spike", "sudden high volume"],
    "cross_border_unregistered": ["cross-border", "cross border", "unregistered international", "unreported foreign", "fema"],
    "shell_company_indicator": ["shell company", "no employees", "single director", "no physical presence"],
    "invoice_mismatch": ["invoice mismatch", "invoice amount does not match", "invoice discrepancy"],
    "late_gst_filing": ["late gst", "gst filed late", "gstr filed after"],
    "director_pep_match": ["pep", "politically exposed person", "sanctions list", "sanctioned entity"],
    "high_cash_ratio": ["high cash ratio", "cash intensive", "cash-heavy", "predominantly cash"],
    "unusual_sector_activity": ["unusual sector activity", "inconsistent with declared sector", "sector mismatch"],
}


def detect_flags_from_text(text: str) -> List[str]:
    """Stage 0 pre-step: NER-lite flag detection from free text (backs /parse-flags)."""
    text_l = text.lower()
    detected: List[str] = []
    for flag_name, keywords in FLAG_KEYWORDS.items():
        if any(kw in text_l for kw in keywords):
            detected.append(flag_name)
    return detected


def _llm_generate_fn():
    """Adapter so anomaly_scorer's llm_generate(prompt, user_prompt, max_tokens) shape
    can call through the shared multi-provider client, or return None if unavailable."""
    client = get_llm_client_or_none()
    if not client:
        return None

    def _generate(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    return _generate


def run_full_assessment(
    features: Dict[str, float],
    detected_flags: Optional[List[str]] = None,
    sector: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Run Stage 0 -> 1 -> 2/3 and return a single structured assessment result.

    `features` should contain the 9 XGBoost feature keys (missing ones default via
    risk_model_runner / compliance_scorer). `detected_flags` are Stage 0 transaction
    flag names (see FLAG_KEYWORDS above); pass [] if none.
    """
    detected_flags = detected_flags or []

    # Align Stage-1 numeric features with Stage-0 detected flags. Without this,
    # free-text descriptions that trip a flag (e.g. cross_border_unregistered) can
    # still feed the XGBoost classifier near-default low-risk numbers if the regex
    # feature extractor didn't happen to catch an exact "NN% cash" pattern in the
    # same text -- producing a contradictory "low risk" verdict next to critical
    # rule findings. This keeps both signal paths consistent.
    features = dict(features)
    _FLAG_FEATURE_FLOORS = {
        "cross_border_unregistered": ("cross_border_ratio", 0.35),
        "high_cash_ratio": ("cash_ratio", 0.4),
        "large_cash_deposit": ("cash_ratio", 0.35),
        "structuring_pattern": ("cash_ratio", 0.4),
        "late_gst_filing": ("late_payment_rate", 0.3),
        "unusual_sector_activity": ("sector_risk_score", 0.6),
        "invoice_mismatch": ("late_payment_rate", 0.2),
    }
    for _flag in detected_flags:
        _floor = _FLAG_FEATURE_FLOORS.get(_flag)
        if _floor:
            _key, _min_val = _floor
            features[_key] = max(features.get(_key, 0.0), _min_val)
    if "shell_company_indicator" in detected_flags:
        features["director_count"] = min(features.get("director_count", 2), 1)
        features["sector_risk_score"] = max(features.get("sector_risk_score", 0.3), 0.6)

    # ── Stage 0: Anomaly scorer ──────────────────────────────────────────────
    llm_fn = _llm_generate_fn() if use_llm else None
    anomaly_result = score_anomalies(detected_flags, llm_generate=llm_fn)
    features["anomaly_risk_score"] = anomaly_result.get("normalized_for_xgboost", features.get("anomaly_risk_score", 0.0))

    # PEP/sanctions match -> auto-escalate regardless of ML tier (Plan.md Section 14)
    pep_hit = "director_pep_match" in detected_flags
    shell_hit = "shell_company_indicator" in detected_flags

    # ── Stage 1: XGBoost risk classifier ─────────────────────────────────────
    risk_pred = predict_risk_tier(features)
    tier = risk_pred["tier"]
    if pep_hit or shell_hit:
        tier = "critical"

    # ── Stage 2 + 3: weighted gap scorer + cosine ranker ─────────────────────
    findings = score_compliance_gaps(features, risk_tier=tier, sector=sector)

    # A hard-gate finding means the rule engine is confident this is a real,
    # serious violation (critical severity + a genuine trigger signal on the
    # entity's actual feature vector) -- that must never be silently overridden
    # by a "low"/"medium" verdict from the numeric classifier alone. Escalate,
    # then recompute findings against the corrected tier so the tier-alignment
    # factor and the returned findings stay internally consistent.
    hard_gate_hit = any(f.get("hard_gate") and f.get("severity") == "critical" for f in findings)
    auto_escalated = pep_hit or shell_hit or hard_gate_hit
    if hard_gate_hit and tier != "critical":
        tier = "critical"
        findings = score_compliance_gaps(features, risk_tier=tier, sector=sector)

    total_penalty_exposure = sum(f.get("max_penalty_inr") or 0 for f in findings if f.get("severity") in ("critical", "high"))
    imprisonment_risk = any(f.get("imprisonment_risk") for f in findings)

    return {
        "risk_tier": tier,
        "confidence": risk_pred.get("confidence", 0.5),
        "model_fallback": risk_pred.get("fallback", True),
        "auto_escalated": auto_escalated,
        "anomaly": anomaly_result,
        "detected_flags": detected_flags,
        "features": features,
        "findings": findings,
        "total_penalty_exposure_inr": total_penalty_exposure,
        "imprisonment_risk": imprisonment_risk,
    }


def reassess_with_overrides(
    base_features: Dict[str, float],
    overrides: Dict[str, float],
    base_flags: Optional[List[str]] = None,
    sector: Optional[str] = None,
) -> Dict[str, Any]:
    """Re-run the pipeline with a modified feature set — backs the agent's `reassess` tool."""
    new_features = dict(base_features)
    new_features.update(overrides)
    return run_full_assessment(new_features, detected_flags=base_flags, sector=sector)


# ── Lightweight what-if parsing used by the agent's reassess/threshold_sim tools ──

_WHATIF_PATTERNS = [
    (re.compile(r"cash ratio.*?(?:to|=)\s*(\d+)%"), "cash_ratio", lambda v: float(v) / 100.0),
    (re.compile(r"cash ratio.*?doubles?"), "cash_ratio", "double"),
    (re.compile(r"cash ratio.*?drops? to (\d+)%"), "cash_ratio", lambda v: float(v) / 100.0),
    (re.compile(r"cross.?border.*?(?:to|=)\s*(\d+)%"), "cross_border_ratio", lambda v: float(v) / 100.0),
    (re.compile(r"(?:transaction volume|transactions?).*?doubles?"), "monthly_txn_volume", "double"),
    (re.compile(r"(?:transaction volume|transactions?).*?(?:to|=)\s*(\d+)"), "monthly_txn_volume", lambda v: float(v)),
    (re.compile(r"director.*?count.*?(?:to|=)\s*(\d+)"), "director_count", lambda v: float(v)),
]


def parse_what_if(what_if_text: str, base_features: Dict[str, float]) -> Dict[str, float]:
    """Turn a natural-language what-if phrase into a feature override dict."""
    text_l = what_if_text.lower()
    overrides: Dict[str, float] = {}

    for pattern, feature_key, transform in _WHATIF_PATTERNS:
        m = pattern.search(text_l)
        if not m:
            continue
        if transform == "double":
            overrides[feature_key] = min(1.0 if feature_key.endswith("ratio") else 1e9,
                                          base_features.get(feature_key, 0.0) * 2)
        else:
            groups = m.groups()
            if groups:
                overrides[feature_key] = transform(groups[0])

    # PEP / sanction / shell what-ifs bump anomaly score directly
    if any(k in text_l for k in ("pep", "sanction", "shell company")):
        overrides["anomaly_risk_score"] = min(5.0, base_features.get("anomaly_risk_score", 0.0) + 3.0)

    return overrides
