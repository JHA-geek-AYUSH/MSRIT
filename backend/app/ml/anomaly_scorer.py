import os
import json
import threading
from typing import List, Dict, Any, Optional, Callable
import structlog

log = structlog.get_logger()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "anomaly_cache.json")

_cache_lock = threading.Lock()

ANOMALY_SCORER_SYSTEM_PROMPT = """
You are a financial crime anomaly detector for a compliance triage system.
Analyze each transaction flag and assign a risk weight between 0.0 and 1.0.

Risk Weight Scale:
  0.00 – 0.20 : Negligible / Routine business variance
  0.21 – 0.45 : Low / Minor anomaly requiring low-level review
  0.46 – 0.65 : Medium / Concerning pattern (e.g., cash intensity, invoice mismatch)
  0.66 – 0.85 : High / Strong indicator of structuring, layering, or evasion
  0.86 – 1.00 : Critical / Immediate STR required (e.g., sanctioned entity, shell company)

Rules:
- Output ONLY valid raw JSON. No markdown. No explanation outside the JSON.
{
  "flags": [
    {"name": "...", "weight": 0.00, "category": "...", "justification": "one sentence"}
  ],
  "total_anomaly_score": 0.00,
  "dominant_flag": "highest weight flag name, or null",
  "anomaly_summary": "one sentence overall anomaly profile"
}
"""

def load_cache() -> Dict[str, float]:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            log.warning("anomaly_scorer.cache_load_failed", error=str(e))
    return {}

def save_cache(cache: Dict[str, float]) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        log.warning("anomaly_scorer.cache_save_failed", error=str(e))

def normalize_for_xgboost(raw_sum: float) -> float:
    return round(min(5.0, raw_sum), 4)

def score_anomalies(
    detected_flags: List[str],
    llm_generate: Optional[Callable] = None,
) -> Dict[str, Any]:
    if not detected_flags:
        return {
            "flags": [],
            "total_anomaly_score": 0.0,
            "normalized_for_xgboost": 0.0,
            "dominant_flag": None,
            "anomaly_summary": "No anomalies detected.",
        }

    with _cache_lock:
        cache = load_cache()

        all_in_cache = True
        cached_flags = []
        for flag in detected_flags:
            norm_flag = flag.strip().lower()
            if norm_flag in cache:
                weight = cache[norm_flag]
                cached_flags.append({
                    "name": flag,
                    "weight": weight,
                    "category": "cached",
                    "justification": "Retrieved from known anomaly database.",
                })
            else:
                all_in_cache = False

        if all_in_cache:
            return _build_result_from_flags(cached_flags)

    if llm_generate:
        user_prompt = f"Analyze the following transaction flags: {', '.join(detected_flags)}"
        for attempt, prompt in enumerate([ANOMALY_SCORER_SYSTEM_PROMPT, 
                                          ANOMALY_SCORER_SYSTEM_PROMPT + "\nRemember: Output ONLY valid JSON, do not wrap in markdown ```json."],
                                         start=1):
            try:
                response_str = llm_generate(prompt, user_prompt, max_tokens=300)
                result = parse_llm_json(response_str)
                if result:
                    with _cache_lock:
                        cache = load_cache()
                        update_cache_with_new_flags(result, cache)
                    result["normalized_for_xgboost"] = normalize_for_xgboost(
                        result.get("total_anomaly_score", 0.0)
                    )
                    return result
            except Exception as e:
                log.warning("anomaly_scorer.llm_failed", attempt=attempt, error=str(e))

    return build_fallback_response(detected_flags, load_cache())

def _build_result_from_flags(flags: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_score = sum(f["weight"] for f in flags)
    dominant = max(flags, key=lambda e: e["weight"]) if flags else None
    dominant_name = dominant["name"] if dominant else None

    if dominant and dominant["weight"] >= 0.86:
        summary = f"Critical anomaly profile dominated by {dominant_name}."
    elif dominant and dominant["weight"] >= 0.46:
        summary = f"Medium risk anomaly profile with {dominant_name}."
    elif dominant:
        summary = f"Low risk anomaly profile: {dominant_name}."
    else:
        summary = "Negligible transaction risk profile."

    return {
        "flags": flags,
        "total_anomaly_score": round(total_score, 4),
        "normalized_for_xgboost": normalize_for_xgboost(total_score),
        "dominant_flag": dominant_name,
        "anomaly_summary": summary,
    }

def parse_llm_json(response_str: str) -> Optional[Dict[str, Any]]:
    if not response_str:
        return None
    cleaned = response_str.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) > 2:
            cleaned = "\n".join(lines[1:-1]) if "json" in lines[0] else "\n".join(lines[1:])
    cleaned = cleaned.strip("` \n\r\t")

    try:
        data = json.loads(cleaned)
        if "flags" in data and "total_anomaly_score" in data:
            return data
    except Exception as e:
        log.warning("anomaly_scorer.json_parse_failed", error=str(e))
    return None

def update_cache_with_new_flags(result: Dict[str, Any], cache: Dict[str, float]) -> None:
    updated = False
    for flag in result.get("flags", []):
        name = flag.get("name")
        weight = flag.get("weight")
        if name and isinstance(weight, (int, float)):
            norm_name = name.strip().lower()
            if norm_name not in cache:
                cache[norm_name] = float(weight)
                updated = True
    if updated:
        save_cache(cache)

def build_fallback_response(detected_flags: List[str], cache: Dict[str, float]) -> Dict[str, Any]:
    flags = []
    total_score = 0.0

    for flag in detected_flags:
        norm_flag = flag.strip().lower()
        if norm_flag in cache:
            weight = cache[norm_flag]
            justification = "Retrieved from known anomaly database."
        else:
            if any(x in norm_flag for x in ["sanction", "pep", "shell"]):
                weight = 0.95; justification = "High-risk entity indicator."
            elif any(x in norm_flag for x in ["structur", "round", "layer"]):
                weight = 0.85; justification = "Structuring / Layering pattern."
            elif any(x in norm_flag for x in ["cash", "large"]):
                weight = 0.60; justification = "Cash intensity or high value transfer."
            else:
                weight = 0.35; justification = "Uncategorized anomaly."

        flags.append({
            "name": flag,
            "weight": weight,
            "category": "fallback",
            "justification": justification,
        })
        total_score += weight

    return _build_result_from_flags(flags)
