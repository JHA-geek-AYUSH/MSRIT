import os
import re
import pandas as pd
import xgboost as xgb
import joblib
import structlog
from typing import Dict, Any, List, Optional

log = structlog.get_logger()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(BASE_DIR, "risk_model.json")
ENCODER_FILE = os.path.join(BASE_DIR, "label_encoder.pkl")

_model = None
_encoder = None

def _load_model():
    global _model, _encoder
    if _model is None and os.path.exists(MODEL_FILE):
        try:
            _model = xgb.XGBClassifier()
            _model.load_model(MODEL_FILE)
            if os.path.exists(ENCODER_FILE):
                _encoder = joblib.load(ENCODER_FILE)
        except Exception as e:
            log.error("risk_model.load_failed", error=str(e))

def extract_financial_features_gemma(text: str, documents: List[Dict[str, Any]] = None) -> Optional[Dict[str, float]]:
    """Ask Gemma to read the WHOLE free-text description holistically and produce
    the 9 XGBoost feature values as JSON, instead of relying on regexes that only
    catch a handful of exact phrasings ("NN% cash", "N directors", ...). This is
    the actual Gemma integration point for the assessment pipeline -- previously
    this file never called an LLM at all, so most free-text descriptions fell
    straight through to hardcoded defaults regardless of what was actually
    written, which is why assessments felt generic / non-differentiated.

    Returns None (never raises) if no LLM provider is configured or parsing
    fails, so callers can fall back to the regex extractor below.
    """
    from app.core.gemma_client import get_llm_client_or_none, get_llm_model
    import json as _json

    client = get_llm_client_or_none()
    if not client:
        return None

    full_text = text or ""
    if documents:
        full_text += "\n" + "\n".join(str(d.get("content", "")) for d in documents)
    if not full_text.strip():
        return None

    system_prompt = (
        "You extract structured financial-compliance features from a free-text "
        "description of a business entity or transaction pattern, for an Indian "
        "AML/KYC risk pipeline. Output ONLY valid JSON (no markdown, no commentary) "
        "with exactly these keys and numeric values:\n"
        "{\n"
        '  "monthly_txn_volume": <int, count of transactions per month, default 100>,\n'
        '  "avg_ticket_size": <float, average transaction size in INR, default 50000>,\n'
        '  "cash_ratio": <float 0-1, fraction of activity that is cash, default 0.1>,\n'
        '  "cross_border_ratio": <float 0-1, fraction cross-border/international, default 0.05>,\n'
        '  "late_payment_rate": <float 0-1, default 0.05>,\n'
        '  "business_age_years": <float, default 5.0>,\n'
        '  "sector_risk_score": <float 0-1, inherent sector risk -- crypto/forex/jewellery/real '
        "estate/casino are high, IT/manufacturing/education are low, default 0.3>,\n"
        '  "director_count": <int, default 2>,\n'
        '  "anomaly_risk_score": <float 0-5, your own holistic judgement of how anomalous or '
        'suspicious the overall pattern is, default 0.5>\n'
        "}\n"
        "Infer values from context even when no explicit number is given -- e.g. \"three cash "
        "deposits totalling 9.8L over 5 days, 1 director, dormant for 8 months before this\" "
        "implies a high cash_ratio, director_count=1, and an elevated anomaly_risk_score."
    )
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_text[:4000]},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if "\n" in raw:
                raw = raw.split("\n", 1)[1]
        parsed = _json.loads(raw)
        expected_keys = {
            "monthly_txn_volume", "avg_ticket_size", "cash_ratio", "cross_border_ratio",
            "late_payment_rate", "business_age_years", "sector_risk_score",
            "director_count", "anomaly_risk_score",
        }
        features = {k: float(v) for k, v in parsed.items() if k in expected_keys and v is not None}
        if not features:
            return None
        for k in ("cash_ratio", "cross_border_ratio", "late_payment_rate", "sector_risk_score"):
            if k in features:
                features[k] = max(0.0, min(1.0, features[k]))
        log.info("risk_model.gemma_extraction_ok", keys=list(features.keys()))
        return features
    except Exception as e:
        log.warning("risk_model.gemma_extraction_failed", error=str(e))
        return None


def extract_financial_features(text: str, documents: List[Dict[str, Any]] = None) -> Dict[str, float]:
    """Extract the 9 XGBoost features from free text. Tries Gemma first (reads the
    whole description holistically); the regex pass below always runs too and
    fills in any keys Gemma's response didn't include, so the result is never
    fully dependent on either path alone.
    """
    regex_features = _extract_financial_features_regex(text, documents)
    gemma_features = extract_financial_features_gemma(text, documents)
    if gemma_features:
        merged = dict(regex_features)
        merged.update(gemma_features)
        return merged
    return regex_features


def _extract_financial_features_regex(text: str, documents: List[Dict[str, Any]] = None) -> Dict[str, float]:
    """Heuristic regex fallback -- used when no Gemma provider is available, and
    to backstop any keys a Gemma response omits."""
    text = text.lower()
    if documents:
        for d in documents:
            text += " " + str(d.get("content", "")).lower()

    # Defaults
    features = {
        "monthly_txn_volume": 100,
        "avg_ticket_size": 50000.0,
        "cash_ratio": 0.1,
        "cross_border_ratio": 0.05,
        "late_payment_rate": 0.05,
        "business_age_years": 5.0,
        "sector_risk_score": 0.3,
        "director_count": 2,
        "anomaly_risk_score": 0.5
    }

    # Extractors
    # "150 transactions"
    m_vol = re.search(r"(\d+)\s*transactions", text)
    if m_vol:
        features["monthly_txn_volume"] = float(m_vol.group(1))

    # "avg size 100000" or "ticket size 100000"
    m_size = re.search(r"(?:ticket\s*size|avg\s*size|average)\s*(?:of)?\s*(?:₹|inr|rs\.?)?\s*([\d,]+)", text)
    if m_size:
        features["avg_ticket_size"] = float(m_size.group(1).replace(",", ""))

    # "cash ratio 0.4" or "40% cash"
    m_cash = re.search(r"(\d+)%\s*cash", text)
    if m_cash:
        features["cash_ratio"] = float(m_cash.group(1)) / 100.0

    m_cross = re.search(r"(\d+)%\s*(?:cross.?border|international|foreign)", text)
    if m_cross:
        features["cross_border_ratio"] = float(m_cross.group(1)) / 100.0

    m_age = re.search(r"business\s*age\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*years", text)
    if m_age:
        features["business_age_years"] = float(m_age.group(1))

    m_dir = re.search(r"(\d+)\s*directors?", text)
    if m_dir:
        features["director_count"] = int(m_dir.group(1))

    # High risk sector heuristics
    if "crypto" in text or "casino" in text or "betting" in text:
        features["sector_risk_score"] = 0.9
    elif "real estate" in text or "ngo" in text or "trust" in text:
        features["sector_risk_score"] = 0.7

    return features

def predict_risk_tier(features: Dict[str, float]) -> Dict[str, Any]:
    _load_model()
    
    if _model is None or _encoder is None:
        return {"tier": "medium", "confidence": 0.5, "fallback": True}

    try:
        cols = [
            "monthly_txn_volume", "avg_ticket_size", "cash_ratio", 
            "cross_border_ratio", "late_payment_rate", "business_age_years",
            "sector_risk_score", "director_count", "anomaly_risk_score"
        ]
        
        # Ensure correct order
        row = [features.get(c, 0.0) for c in cols]
        df = pd.DataFrame([row], columns=cols)
        
        preds = _model.predict_proba(df)
        pred_idx = preds.argmax(axis=1)[0]
        confidence = float(preds[0][pred_idx])
        
        tier = _encoder.inverse_transform([pred_idx])[0]
        
        return {"tier": tier, "confidence": confidence, "fallback": False}
        
    except Exception as e:
        log.error("risk_model.prediction_error", error=str(e))
        return {"tier": "medium", "confidence": 0.5, "fallback": True}
