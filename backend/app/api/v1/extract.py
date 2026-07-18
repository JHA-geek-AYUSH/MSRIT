"""Document extraction endpoint — accepts file uploads or raw text for financial
documents and extracts structured entity data for compliance assessment.

Supported inputs:
  - file: PDF (.pdf), DOCX (.docx), or image (.png / .jpg / .jpeg) via multipart upload
  - text: raw document text via form field

At least one of file or text must be provided; HTTP 422 is returned otherwise.

File routing:
  - .png / .jpg / .jpeg → OCR pipeline (app/ingestion/ocr.py)
  - .pdf               → PDF text parser (app/ingestion/parse_pdf.py)
  - .docx              → DOCX text parser (app/ingestion/parse_docx.py)

All extracted text is passed through redact_user_input() before any downstream
processing (Gemma prompt construction or regex extraction).

Extraction path (Requirement 6.4, 6.5, 6.6, 6.8):
  1. If Gemma is available → call Gemma with a document-type-specific prompt.
     Populate extraction_fields with source="gemma" and per-field confidence.
  2. If Gemma is unavailable or fails → fall back to regex extraction.
     Regex hits use source="regex" + float confidence (0.7 for numeric/pct fields,
     0.5 for other fields). Unextracted fields use source="default" + confidence=0.0.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.core.pii_redaction import redact_for_processing
from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.ml.risk_model_runner import extract_financial_features
import structlog

log = structlog.get_logger()
router = APIRouter()

# ---------------------------------------------------------------------------
# Supported file extensions — checked case-insensitively
# ---------------------------------------------------------------------------
_OCR_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_PDF_EXTENSION = ".pdf"
_DOCX_EXTENSION = ".docx"
_ALL_SUPPORTED = _OCR_EXTENSIONS | {_PDF_EXTENSION, _DOCX_EXTENSION}

# ---------------------------------------------------------------------------
# Financial fields to extract
# ---------------------------------------------------------------------------
_FINANCIAL_FIELDS = [
    "monthly_txn_volume",
    "avg_ticket_size",
    "cash_ratio",
    "cross_border_ratio",
    "late_payment_rate",
    "business_age_years",
    "sector_risk_score",
    "director_count",
    "anomaly_risk_score",
]

# ---------------------------------------------------------------------------
# Gemma prompt templates — one per supported document_type (Requirement 6.8)
# ---------------------------------------------------------------------------
_FIELD_SCHEMA = """\
{
  "monthly_txn_volume": <number — total monthly transaction count>,
  "monthly_txn_volume_confidence": <float 0.0-1.0>,
  "avg_ticket_size": <number — average transaction amount in INR>,
  "avg_ticket_size_confidence": <float 0.0-1.0>,
  "cash_ratio": <float 0.0-1.0 — fraction of transactions that are cash>,
  "cash_ratio_confidence": <float 0.0-1.0>,
  "cross_border_ratio": <float 0.0-1.0 — fraction of cross-border transactions>,
  "cross_border_ratio_confidence": <float 0.0-1.0>,
  "late_payment_rate": <float 0.0-1.0 — fraction of payments made late>,
  "late_payment_rate_confidence": <float 0.0-1.0>,
  "business_age_years": <number — years the business has been operating>,
  "business_age_years_confidence": <float 0.0-1.0>,
  "sector_risk_score": <float 0.0-1.0 — risk level of the business sector>,
  "sector_risk_score_confidence": <float 0.0-1.0>,
  "director_count": <integer — number of directors / key persons>,
  "director_count_confidence": <float 0.0-1.0>,
  "anomaly_risk_score": <float 0.0-1.0 — overall anomaly / irregularity score>,
  "anomaly_risk_score_confidence": <float 0.0-1.0>
}"""

_GEMMA_PROMPT_PREFIX = (
    "You are a financial document analysis expert. "
    "Extract the following fields from the document text provided. "
    "Return ONLY a valid JSON object matching the schema below — no markdown fences, "
    "no extra keys, no commentary. "
    "If a field cannot be determined from the document, use null for its value and "
    "0.0 for its confidence.\n\n"
    "Schema:\n" + _FIELD_SCHEMA + "\n\n"
)

GEMMA_EXTRACT_PROMPTS: Dict[str, str] = {
    "general": (
        _GEMMA_PROMPT_PREFIX
        + "This is a general financial document. Extract any financial metrics present.\n\n"
        + "Document:\n{document_text}"
    ),
    "bank_statement": (
        _GEMMA_PROMPT_PREFIX
        + "This is a bank statement. Focus on transaction volumes, cash ratios, "
        "average transaction sizes, and any cross-border activity.\n\n"
        + "Document:\n{document_text}"
    ),
    "gst_filing": (
        _GEMMA_PROMPT_PREFIX
        + "This is a GST filing / return document. Focus on turnover-derived transaction "
        "volumes, average invoice sizes, sector classification, and late filing indicators.\n\n"
        + "Document:\n{document_text}"
    ),
    "onboarding": (
        _GEMMA_PROMPT_PREFIX
        + "This is a business onboarding / KYC document. Focus on business age, director "
        "count, sector risk, and any stated transaction profile.\n\n"
        + "Document:\n{document_text}"
    ),
    "invoice": (
        _GEMMA_PROMPT_PREFIX
        + "This is an invoice or set of invoices. Derive monthly transaction volume from "
        "invoice count, average ticket size from amounts, and flag any cross-border or "
        "late-payment indicators.\n\n"
        + "Document:\n{document_text}"
    ),
}

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ExtractionField(BaseModel):
    """Per-field extraction result with provenance and confidence."""

    value: Optional[float] = Field(None, description="Extracted numeric value, or null if unavailable")
    source: str = Field(
        ...,
        description="Extraction source: 'gemma' | 'regex' | 'default'",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in [0.0, 1.0]",
    )


class ExtractResponse(BaseModel):
    """Response shape for POST /v1/compliance/extract."""

    document_type: str
    extraction_source: str = Field(
        ...,
        description="Primary extraction method used: 'gemma' | 'regex'",
    )
    extraction_fields: Dict[str, ExtractionField]
    raw_text_length: int = Field(0, description="Character length of the (redacted) document text")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_text_from_file(file: UploadFile) -> str:
    """Route an uploaded file to the appropriate ingestion method and return raw text."""
    filename = (file.filename or "").lower()
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1]

    if ext not in _ALL_SUPPORTED:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Supported: {sorted(_ALL_SUPPORTED)}",
        )

    raw_bytes = file.file.read()

    if ext in _OCR_EXTENSIONS:
        try:
            from app.ingestion.ocr import extract_text_from_image  # type: ignore
            return extract_text_from_image(raw_bytes)
        except Exception as exc:
            log.warning("extract.ocr_failed", error=str(exc))
            return ""

    if ext == _PDF_EXTENSION:
        try:
            from app.ingestion.parse_pdf import extract_text_from_pdf  # type: ignore
            return extract_text_from_pdf(io.BytesIO(raw_bytes))
        except Exception as exc:
            log.warning("extract.pdf_parse_failed", error=str(exc))
            return ""

    if ext == _DOCX_EXTENSION:
        try:
            from app.ingestion.parse_docx import extract_text_from_docx  # type: ignore
            return extract_text_from_docx(io.BytesIO(raw_bytes))
        except Exception as exc:
            log.warning("extract.docx_parse_failed", error=str(exc))
            return ""

    return ""


def _gemma_extract(
    clean_text: str,
    document_type: str,
) -> Optional[Dict[str, ExtractionField]]:
    """
    Try Gemma extraction. Returns a dict of field_name → ExtractionField on success,
    or None if Gemma is unavailable or the response cannot be parsed.

    Requirement 6.4 — calls get_llm_client_or_none() / get_llm_model().
    Requirement 6.5 — every field gets source="gemma" and a float confidence.
    """
    client = get_llm_client_or_none()
    if client is None:
        log.info("extract.gemma_unavailable")
        return None

    prompt_template = GEMMA_EXTRACT_PROMPTS.get(document_type, GEMMA_EXTRACT_PROMPTS["general"])
    prompt = prompt_template.format(document_text=clean_text)
    model = get_llm_model()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
    except Exception as exc:
        log.warning("extract.gemma_call_failed", error=str(exc))
        return None

    raw = (response.choices[0].message.content or "").strip()

    # Strip any accidental markdown fences Gemma might include
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

    try:
        data: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("extract.gemma_json_parse_failed", error=str(exc), raw=raw[:300])
        return None

    fields: Dict[str, ExtractionField] = {}
    for field_name in _FINANCIAL_FIELDS:
        raw_value = data.get(field_name)
        raw_conf = data.get(f"{field_name}_confidence", 0.0)

        # Coerce value to float or keep as None
        value: Optional[float]
        if raw_value is None:
            value = None
        else:
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = None

        # Confidence must be a float in [0.0, 1.0]
        try:
            conf = float(raw_conf)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))

        # If Gemma returned null for the value, treat confidence as 0.0
        if value is None:
            conf = 0.0

        fields[field_name] = ExtractionField(
            value=value,
            source="gemma",
            confidence=conf,
        )

    log.info("extract.gemma_success", fields_extracted=sum(1 for f in fields.values() if f.value is not None))
    return fields


def _regex_extract(clean_text: str) -> Dict[str, ExtractionField]:
    """
    Fall back to the existing regex-based heuristics from extract_financial_features().
    Uses the defaults dict from that function to detect which fields were actually hit
    by a regex pattern vs left at default values.

    Requirement 6.6 — regex hits get source="regex", unextracted get source="default".
    Confidence values:
      - source="regex":   0.7 for integer/percentage fields, 0.5 for others
      - source="default": 0.0
    """
    # These are the hardcoded defaults in extract_financial_features
    _DEFAULTS: Dict[str, float] = {
        "monthly_txn_volume": 100,
        "avg_ticket_size": 50000.0,
        "cash_ratio": 0.1,
        "cross_border_ratio": 0.05,
        "late_payment_rate": 0.05,
        "business_age_years": 5.0,
        "sector_risk_score": 0.3,
        "director_count": 2,
        "anomaly_risk_score": 0.5,
    }
    # Fields where we treat a regex hit with higher confidence (integer / percentage fields)
    _HIGH_CONF_FIELDS = {
        "monthly_txn_volume",
        "avg_ticket_size",
        "business_age_years",
        "director_count",
    }

    extracted = extract_financial_features(clean_text)
    fields: Dict[str, ExtractionField] = {}

    for field_name in _FINANCIAL_FIELDS:
        value = float(extracted.get(field_name, _DEFAULTS[field_name]))
        default_value = float(_DEFAULTS[field_name])

        if value != default_value:
            # Regex pattern matched — field was updated from the default
            conf = 0.7 if field_name in _HIGH_CONF_FIELDS else 0.5
            source = "regex"
        else:
            # Value sits at the hard-coded default — no pattern hit
            conf = 0.0
            source = "default"

        fields[field_name] = ExtractionField(
            value=value,
            source=source,
            confidence=conf,
        )

    return fields


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/compliance/extract", response_model=ExtractResponse)
async def extract_document(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    document_type: str = Form("general"),
    user=Depends(current_user),
) -> ExtractResponse:
    """
    Extract financial features from a document (file upload or raw text).

    - Validates that at least one of `file` / `text` is supplied (HTTP 422 otherwise).
    - Routes file to the appropriate ingestion method (OCR / PDF / DOCX).
    - Redacts PII before any LLM or regex processing.
    - Tries Gemma first; falls back to regex extraction if Gemma is unavailable.
    - Returns ExtractResponse with per-field source and float confidence.

    Validates: Requirements 6.4, 6.5, 6.6, 6.8
    """
    # --- Validate inputs (Requirement 6.1, 6.2) ---
    if file is None and (text is None or text.strip() == ""):
        raise HTTPException(
            status_code=422,
            detail="At least one of 'file' or 'text' must be provided.",
        )

    valid_doc_types = {"general", "bank_statement", "gst_filing", "onboarding", "invoice"}
    if document_type not in valid_doc_types:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid document_type '{document_type}'. Must be one of: {sorted(valid_doc_types)}",
        )

    # --- Build raw document text ---
    raw_text_parts: List[str] = []

    if file is not None:
        file_text = _extract_text_from_file(file)
        if file_text:
            raw_text_parts.append(file_text)

    if text and text.strip():
        raw_text_parts.append(text.strip())

    raw_text = "\n\n".join(raw_text_parts)

    # --- PII redaction (Requirement 6.7) ---
    user_id = getattr(user, "id", "anonymous")
    clean_text = redact_for_processing(raw_text, str(user_id))

    log.info(
        "extract.processing",
        document_type=document_type,
        raw_length=len(raw_text),
        clean_length=len(clean_text),
        has_file=file is not None,
        has_text=bool(text),
    )

    # --- Gemma-first extraction (Requirement 6.4, 6.5) ---
    gemma_fields = _gemma_extract(clean_text, document_type)

    if gemma_fields is not None:
        return ExtractResponse(
            document_type=document_type,
            extraction_source="gemma",
            extraction_fields=gemma_fields,
            raw_text_length=len(clean_text),
        )

    # --- Regex fallback (Requirement 6.6) ---
    log.info("extract.fallback_to_regex")
    regex_fields = _regex_extract(clean_text)

    return ExtractResponse(
        document_type=document_type,
        extraction_source="regex",
        extraction_fields=regex_fields,
        raw_text_length=len(clean_text),
    )
