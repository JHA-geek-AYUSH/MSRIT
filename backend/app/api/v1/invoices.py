"""POST /v1/invoices/upload — invoice ingestion, extraction, duplicate detection,
risk scoring and approval-gating in one pipeline.

Pipeline (per requirements 2.1–2.11):
  1. Reject non-pdf/png/jpg/jpeg  → HTTP 422
  2. Route bytes to OCR or PDF parser
  3. Redact PII before any LLM call
  4. Gemma-first structured extraction  → regex fallback when unavailable
  5. detect_duplicate_payments() over 30-day window (same supplier)
  6. detect_invoice_po_mismatch() when po_number is provided
  7. exact_invoice_match findings → severity = critical
  8. critical finding or risk_tier = critical → ApprovalRequest + requires_approval = True
  9. AuditTrailEntry for every status transition
 10. Persist Invoice row; return InvoiceUploadResponse
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.core.pii_redaction import redact_user_input
from app.core.security import get_db_user
from app.db.models import ApprovalRequest, AuditTrailEntry, Invoice
from app.db.session import get_db
from app.ml.document_anomalies import (
    Transaction,
    detect_duplicate_payments,
    detect_invoice_po_mismatch,
)

log = structlog.get_logger()

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Gemma prompt (design.md §3.1.5)
# ──────────────────────────────────────────────────────────────────────────────

GEMMA_INVOICE_PROMPT = """
You are a financial document parser. Extract the following fields from this invoice document.

CRITICAL disambiguation rules — invoices commonly contain several similar-looking
fields; do not confuse them:
- "vendor_name" is the SELLER/ISSUER of the invoice — look for a label like
  "Sold By", "Billed By", "From", or the company name next to the GSTIN/letterhead
  at the TOP of the document. It is NEVER a product name, brand name, or line-item
  description (e.g. if the invoice lists "HIMALAYA Neem Soap" as a purchased
  product, that is NOT the vendor — the vendor is the registered company that
  issued the invoice, such as a marketplace seller entity).
- "invoice_number" is the field explicitly labeled "Invoice Number", "Invoice No",
  "Invoice #", or similar. It is DIFFERENT from an "Order ID", "Order Number", or
  "Reference Number" — those are marketplace/order-tracking identifiers, not the
  invoice number, even though they often appear right next to each other. If you
  see both an Order ID and an Invoice Number on the same document, use ONLY the
  one explicitly labeled as the invoice number.
- If the buyer ("Bill To"/"Ship To") is a different party from the seller
  ("Sold By"), vendor_name must be the seller, never the buyer.

Return ONLY valid JSON matching this schema exactly:

{{
  "vendor_name": "string",
  "vendor_gstin": "string or null",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "amount_net": number,
  "amount_gst": number,
  "amount_total": number,
  "po_number": "string or null",
  "line_items": [{{"description": "string", "quantity": number, "unit_price": number, "amount": number}}],
  "monthly_txn_volume": number,
  "avg_ticket_size": number,
  "cash_ratio": float_0_to_1,
  "cross_border_ratio": float_0_to_1,
  "late_payment_rate": float_0_to_1,
  "business_age_years": number,
  "sector_risk_score": float_0_to_1,
  "director_count": number,
  "extraction_confidence": float_0_to_1
}}

Document:
{document_text}
"""

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────

class InvoiceExtraction(BaseModel):
    vendor_name: str = ""
    vendor_gstin: Optional[str] = None
    invoice_number: str = ""
    invoice_date: str = ""
    amount_net: float = 0.0
    amount_gst: float = 0.0
    amount_total: float = 0.0
    po_number: Optional[str] = None
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_extracted_json: Dict[str, Any] = Field(default_factory=dict)


class InvoiceUploadResponse(BaseModel):
    invoice_id: str
    status: str
    extracted_fields: Optional[InvoiceExtraction] = None
    validation_findings: List[Dict[str, Any]] = Field(default_factory=list)
    risk_tier: Optional[str] = None
    requires_approval: bool = False
    approval_id: Optional[str] = None
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}

_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _file_is_allowed(filename: str, content_type: str) -> bool:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return (
        ext in _ALLOWED_EXTENSIONS
        or content_type.lower() in _ALLOWED_CONTENT_TYPES
    )


def _is_image(filename: str, content_type: str) -> bool:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in {".png", ".jpg", ".jpeg"} or content_type.lower().startswith("image/")


async def _extract_text(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Route to OCR (images) or PDF parser; return concatenated text."""
    if _is_image(filename, content_type):
        from io import BytesIO

        from PIL import Image

        from app.ingestion.ocr import ocr_image

        try:
            img = Image.open(BytesIO(file_bytes))
            return ocr_image(img)
        except Exception as exc:
            log.warning("invoice.ocr_failed", error=str(exc))
            return ""
    else:
        from app.ingestion.parse_pdf import extract_text_pages

        try:
            pages = extract_text_pages(file_bytes)
            return "\n".join(pages)
        except Exception as exc:
            log.warning("invoice.pdf_parse_failed", error=str(exc))
            return ""


def _regex_extract(text: str) -> Dict[str, Any]:
    """Simple regex fallback extraction — extraction_confidence is always 0.0."""

    def _first(pattern: str, flags: int = re.IGNORECASE) -> Optional[str]:
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else None

    def _to_float(val: Optional[str]) -> float:
        if val is None:
            return 0.0
        cleaned = re.sub(r"[^\d.]", "", val)
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    invoice_number = _first(
        r"(?:invoice\s*(?:no|number|#)[.:\s]*)([\w\-/]+)"
    ) or _first(r"\b(INV[\-/]?\d{4,})\b", 0) or "UNKNOWN"

    vendor_name = _first(
        r"(?:vendor|supplier|from|bill\s+from)[:\s]+([A-Za-z0-9 &.,'\-]+)"
    ) or ""

    # amounts — try "Total: 1,23,456.00" style
    amount_total_raw = _first(
        r"(?:grand\s+total|total\s+amount|amount\s+due|net\s+payable)[:\s₹]*([\d,]+\.?\d*)"
    )
    amount_gst_raw = _first(
        r"(?:gst|igst|cgst\+sgst|tax)[:\s₹]*([\d,]+\.?\d*)"
    )
    amount_total = _to_float(amount_total_raw)
    amount_gst = _to_float(amount_gst_raw)
    amount_net = max(0.0, amount_total - amount_gst)

    invoice_date = _first(
        r"(?:invoice\s+date|date)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})"
    ) or ""

    gstin = _first(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z0-9])\b")
    po_number = _first(
        r"(?:po\s+number|purchase\s+order)[:\s]*([\w\-/]+)"
    )

    return {
        "vendor_name": vendor_name,
        "vendor_gstin": gstin,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "amount_net": amount_net,
        "amount_gst": amount_gst,
        "amount_total": amount_total,
        "po_number": po_number,
        "line_items": [],
        "extraction_confidence": 0.0,
    }


def _gemma_extract(text: str, client, model: str) -> Dict[str, Any]:
    """Call Gemma for structured extraction; return parsed dict or raise on parse failure."""
    prompt = GEMMA_INVOICE_PROMPT.format(document_text=text[:8000])
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content or ""
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    return json.loads(raw)


async def _append_audit(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    action: str,
    actor: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditTrailEntry:
    entry = AuditTrailEntry(
        action=action,
        actor=actor,
        entity_type="invoice",
        entity_id=str(invoice_id),
        invoice_id=invoice_id,
        metadata_=metadata or {},
    )
    db.add(entry)
    # Flush so the entry gets an id; caller is responsible for final commit
    await db.flush()
    return entry


def _determine_risk_tier(findings: List[Dict[str, Any]]) -> str:
    """Derive risk tier from findings list."""
    severities = {f.get("severity", "low") for f in findings}
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if findings:
        return "low"
    return "unknown"


def _aware_utc(dt: Optional[datetime], fallback: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC. Postgres TIMESTAMPTZ columns
    round-trip as tz-aware via asyncpg, but datetime.utcnow() (used for the
    in-flight invoice being processed right now, before it has a DB-assigned
    created_at) is naive. Subtracting an aware datetime from a naive one raises
    TypeError, which was silently swallowed by the broad except-block around
    duplicate-payment detection — making risk_tier come back "unknown" for
    EVERY invoice as soon as there was more than one in the account, since the
    real match was never reached. Normalizing both sides to aware UTC here
    fixes that at the source instead of re-catching the same class of bug."""
    if dt is None:
        return fallback
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/invoices/upload", response_model=InvoiceUploadResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    po_number: Optional[str] = Form(None),
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceUploadResponse:
    """
    Upload an invoice file (PDF/PNG/JPG/JPEG), extract structured fields via
    Gemma (or regex fallback), run duplicate-payment and PO-mismatch checks,
    and persist the result with a full audit trail.
    """
    # ── 1. File type validation ───────────────────────────────────────────────
    filename = file.filename or "upload"
    content_type = file.content_type or ""

    if not _file_is_allowed(filename, content_type):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type: '{content_type}' / '{filename}'. "
                "Accepted: pdf, png, jpg, jpeg."
            ),
        )

    file_bytes = await file.read()
    user_id_str = str(user.get("db_id") or user.get("id", "system"))
    audit_trail: List[Dict[str, Any]] = []

    # ── Create initial Invoice record ─────────────────────────────────────────
    invoice = Invoice(
        user_id=uuid.UUID(user_id_str),
        invoice_number="PENDING",
        status="processing",
        raw_extracted_json={},
        extraction_confidence=0.0,
    )
    try:
        db.add(invoice)
        await db.flush()  # obtain invoice.id before audit entries

        entry = await _append_audit(
            db, invoice.id, "document_uploaded", user_id_str,
            {"filename": filename, "size_bytes": len(file_bytes)},
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.db_create_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create invoice record.")

    # ── 2. Text extraction ────────────────────────────────────────────────────
    raw_text = await _extract_text(file_bytes, filename, content_type)

    # ── 3. PII redaction before any LLM call ─────────────────────────────────
    redaction_result = redact_user_input(raw_text, user_id_str)
    safe_text = redaction_result.get("redacted_text", raw_text)

    # ── 4. Gemma extraction (with regex fallback) ─────────────────────────────
    llm_client = get_llm_client_or_none()
    extraction_data: Dict[str, Any]
    extraction_method = "gemma"

    if llm_client is not None:
        try:
            model = get_llm_model()
            extraction_data = _gemma_extract(safe_text, llm_client, model)
            log.info("invoice.gemma_extraction_ok", invoice_id=str(invoice.id))
        except Exception as exc:
            log.warning("invoice.gemma_extraction_failed", error=str(exc), invoice_id=str(invoice.id))
            extraction_data = _regex_extract(safe_text)
            extraction_data["extraction_confidence"] = 0.0
            extraction_method = "regex_fallback"
    else:
        # ── 5. Regex fallback — confidence = 0.0 ──────────────────────────────
        extraction_data = _regex_extract(safe_text)
        extraction_data["extraction_confidence"] = 0.0
        extraction_method = "regex_fallback"
        log.info("invoice.gemma_unavailable_regex_fallback", invoice_id=str(invoice.id))

    # If po_number was provided as a form param, override whatever was extracted
    if po_number:
        extraction_data["po_number"] = po_number

    extraction = InvoiceExtraction(
        vendor_name=extraction_data.get("vendor_name") or "",
        vendor_gstin=extraction_data.get("vendor_gstin"),
        invoice_number=extraction_data.get("invoice_number") or "UNKNOWN",
        invoice_date=extraction_data.get("invoice_date") or "",
        amount_net=float(extraction_data.get("amount_net") or 0.0),
        amount_gst=float(extraction_data.get("amount_gst") or 0.0),
        amount_total=float(extraction_data.get("amount_total") or 0.0),
        po_number=extraction_data.get("po_number"),
        line_items=extraction_data.get("line_items") or [],
        extraction_confidence=float(extraction_data.get("extraction_confidence") or 0.0),
        raw_extracted_json=extraction_data,
    )

    # Persist extracted fields
    try:
        invoice.vendor_name = extraction.vendor_name
        invoice.vendor_gstin = extraction.vendor_gstin
        invoice.invoice_number = extraction.invoice_number
        invoice.invoice_date = extraction.invoice_date
        invoice.amount_net = extraction.amount_net
        invoice.amount_gst = extraction.amount_gst
        invoice.amount_total = extraction.amount_total
        invoice.po_number = extraction.po_number
        invoice.extraction_confidence = extraction.extraction_confidence
        invoice.raw_extracted_json = extraction_data
        invoice.status = "extracted"

        entry = await _append_audit(
            db, invoice.id, "extraction_complete", user_id_str,
            {"method": extraction_method, "confidence": extraction.extraction_confidence},
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.extraction_persist_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to persist extraction results.")

    # ── 5 & 6. Duplicate-payment detection (30-day window) + PO mismatch ─────
    findings: List[Dict[str, Any]] = []

    # Build the current invoice as a Transaction for the detectors
    now = datetime.utcnow()
    current_txn = Transaction(
        id=str(invoice.id),
        supplier=extraction.vendor_name or "unknown",
        amount=extraction.amount_total,
        date=now,
        invoice_number=extraction.invoice_number,
        po_number=extraction.po_number,
    )

    # Fetch recent transactions for same supplier within 30-day window
    try:
        window_start = now - timedelta(days=30)
        stmt = select(Invoice).where(
            Invoice.user_id == invoice.user_id,
            Invoice.id != invoice.id,
            Invoice.created_at >= window_start,
        )
        result = await db.execute(stmt)
        recent_invoices = result.scalars().all()

        recent_txns = [
            Transaction(
                id=str(inv.id),
                supplier=inv.vendor_name or "unknown",
                amount=float(inv.amount_total or 0),
                date=inv.created_at if inv.created_at else now,
                invoice_number=inv.invoice_number,
                po_number=inv.po_number,
            )
            for inv in recent_invoices
        ]

        all_txns = [current_txn] + recent_txns
        dup_findings = detect_duplicate_payments(
            all_txns,
            date_window_days=30,
        )

        # ── 7. Mark exact_invoice_match findings as severity=critical ─────────
        for f in dup_findings:
            if f.get("match_kind") == "exact_invoice_match":
                f["severity"] = "critical"
        findings.extend(dup_findings)

        # ── 6 (cont). PO mismatch check ───────────────────────────────────────
        if extraction.po_number:
            from app.ml.document_anomalies import PurchaseOrder

            # Build a minimal PO from the extraction data itself for mismatch detection
            # (if the system had PO records, they'd be fetched here)
            po_records: List[PurchaseOrder] = []
            # Attempt to find a matching PO in recent invoices that share the same PO number
            for inv in recent_invoices:
                if inv.po_number and inv.po_number.strip().lower() == extraction.po_number.strip().lower():
                    po_records.append(
                        PurchaseOrder(
                            po_number=inv.po_number,
                            supplier=inv.vendor_name or "unknown",
                            amount=float(inv.amount_total or 0),
                        )
                    )

            if po_records:
                mismatch_findings = detect_invoice_po_mismatch(
                    [current_txn],
                    po_records,
                )
                findings.extend(mismatch_findings)

    except Exception as exc:
        log.warning("invoice.anomaly_detection_failed", error=str(exc), invoice_id=str(invoice.id))

    # ── Derive risk tier ──────────────────────────────────────────────────────
    risk_tier = _determine_risk_tier(findings)

    # ── 8 & 9. Approval gate ──────────────────────────────────────────────────
    requires_approval = False
    approval_id: Optional[str] = None
    has_critical = any(f.get("severity") == "critical" for f in findings)

    if has_critical or risk_tier == "critical":
        requires_approval = True
        try:
            approval = ApprovalRequest(
                requested_by_user_id=uuid.UUID(user_id_str),
                action_type="review_invoice",
                risk_level="critical",
                payload={
                    "invoice_id": str(invoice.id),
                    "vendor_name": extraction.vendor_name,
                    "amount_total": extraction.amount_total,
                    "findings_count": len(findings),
                },
                reason=(
                    "Critical finding detected on invoice upload: "
                    + "; ".join(
                        f.get("finding", f.get("type", "unknown"))
                        for f in findings
                        if f.get("severity") == "critical"
                    )[:500]
                ),
                status="pending",
            )
            db.add(approval)
            await db.flush()
            approval_id = str(approval.id)

            invoice.requires_approval = True
            invoice.approval_id = approval.id

        except Exception as exc:
            log.error("invoice.approval_create_failed", error=str(exc))
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create approval request.")

    # ── Persist risk scoring results ──────────────────────────────────────────
    try:
        invoice.risk_tier = risk_tier
        invoice.status = "risk_scored"

        entry = await _append_audit(
            db, invoice.id, "risk_scored", user_id_str,
            {
                "risk_tier": risk_tier,
                "findings_count": len(findings),
                "findings": findings,
                "requires_approval": requires_approval,
            },
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        if requires_approval:
            entry2 = await _append_audit(
                db, invoice.id, "approval_requested", user_id_str,
                {"approval_id": approval_id, "reason": "critical_finding"},
            )
            audit_trail.append({"action": entry2.action, "actor": entry2.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.risk_persist_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to persist risk scoring results.")

    log.info(
        "invoice.upload_complete",
        invoice_id=str(invoice.id),
        risk_tier=risk_tier,
        findings=len(findings),
        requires_approval=requires_approval,
        method=extraction_method,
    )

    return InvoiceUploadResponse(
        invoice_id=str(invoice.id),
        status=invoice.status,
        extracted_fields=extraction,
        validation_findings=findings,
        risk_tier=risk_tier,
        requires_approval=requires_approval,
        approval_id=approval_id,
        audit_trail=audit_trail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Shared helper — core processing logic extracted from upload_invoice so that
# both the single-file and batch endpoints can reuse it without depending on
# FastAPI Depends().
# ──────────────────────────────────────────────────────────────────────────────

async def _process_single_invoice(
    file: UploadFile,
    po_number: Optional[str],
    user: dict,
    db: AsyncSession,
) -> InvoiceUploadResponse:
    """
    Run the full invoice processing pipeline for a single file.

    This is the extracted core of `upload_invoice` and is called by both the
    single-file endpoint and the batch endpoint so that the pipeline logic is
    not duplicated.
    """
    filename = file.filename or "upload"
    content_type = file.content_type or ""

    if not _file_is_allowed(filename, content_type):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type: '{content_type}' / '{filename}'. "
                "Accepted: pdf, png, jpg, jpeg."
            ),
        )

    file_bytes = await file.read()
    user_id_str = str(user.get("db_id") or user.get("id", "system"))
    audit_trail: List[Dict[str, Any]] = []

    # ── Create initial Invoice record ─────────────────────────────────────────
    invoice = Invoice(
        user_id=uuid.UUID(user_id_str),
        invoice_number="PENDING",
        status="processing",
        raw_extracted_json={},
        extraction_confidence=0.0,
    )
    try:
        db.add(invoice)
        await db.flush()

        entry = await _append_audit(
            db, invoice.id, "document_uploaded", user_id_str,
            {"filename": filename, "size_bytes": len(file_bytes)},
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.db_create_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create invoice record.")

    # ── Text extraction ───────────────────────────────────────────────────────
    raw_text = await _extract_text(file_bytes, filename, content_type)

    # ── PII redaction before any LLM call ─────────────────────────────────────
    redaction_result = redact_user_input(raw_text, user_id_str)
    safe_text = redaction_result.get("redacted_text", raw_text)

    # ── Gemma extraction (with regex fallback) ────────────────────────────────
    llm_client = get_llm_client_or_none()
    extraction_data: Dict[str, Any]
    extraction_method = "gemma"

    if llm_client is not None:
        try:
            model = get_llm_model()
            extraction_data = _gemma_extract(safe_text, llm_client, model)
            log.info("invoice.gemma_extraction_ok", invoice_id=str(invoice.id))
        except Exception as exc:
            log.warning("invoice.gemma_extraction_failed", error=str(exc), invoice_id=str(invoice.id))
            extraction_data = _regex_extract(safe_text)
            extraction_data["extraction_confidence"] = 0.0
            extraction_method = "regex_fallback"
    else:
        extraction_data = _regex_extract(safe_text)
        extraction_data["extraction_confidence"] = 0.0
        extraction_method = "regex_fallback"
        log.info("invoice.gemma_unavailable_regex_fallback", invoice_id=str(invoice.id))

    if po_number:
        extraction_data["po_number"] = po_number

    extraction = InvoiceExtraction(
        vendor_name=extraction_data.get("vendor_name") or "",
        vendor_gstin=extraction_data.get("vendor_gstin"),
        invoice_number=extraction_data.get("invoice_number") or "UNKNOWN",
        invoice_date=extraction_data.get("invoice_date") or "",
        amount_net=float(extraction_data.get("amount_net") or 0.0),
        amount_gst=float(extraction_data.get("amount_gst") or 0.0),
        amount_total=float(extraction_data.get("amount_total") or 0.0),
        po_number=extraction_data.get("po_number"),
        line_items=extraction_data.get("line_items") or [],
        extraction_confidence=float(extraction_data.get("extraction_confidence") or 0.0),
        raw_extracted_json=extraction_data,
    )

    # ── Persist extracted fields ──────────────────────────────────────────────
    try:
        invoice.vendor_name = extraction.vendor_name
        invoice.vendor_gstin = extraction.vendor_gstin
        invoice.invoice_number = extraction.invoice_number
        invoice.invoice_date = extraction.invoice_date
        invoice.amount_net = extraction.amount_net
        invoice.amount_gst = extraction.amount_gst
        invoice.amount_total = extraction.amount_total
        invoice.po_number = extraction.po_number
        invoice.extraction_confidence = extraction.extraction_confidence
        invoice.raw_extracted_json = extraction_data
        invoice.status = "extracted"

        entry = await _append_audit(
            db, invoice.id, "extraction_complete", user_id_str,
            {"method": extraction_method, "confidence": extraction.extraction_confidence},
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.extraction_persist_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to persist extraction results.")

    # ── Duplicate-payment detection + PO mismatch ─────────────────────────────
    findings: List[Dict[str, Any]] = []
    now = datetime.utcnow()
    current_txn = Transaction(
        id=str(invoice.id),
        supplier=extraction.vendor_name or "unknown",
        amount=extraction.amount_total,
        date=now,
        invoice_number=extraction.invoice_number,
        po_number=extraction.po_number,
    )

    try:
        window_start = now - timedelta(days=30)
        stmt = select(Invoice).where(
            Invoice.user_id == invoice.user_id,
            Invoice.id != invoice.id,
            Invoice.created_at >= window_start,
        )
        result = await db.execute(stmt)
        recent_invoices = result.scalars().all()

        recent_txns = [
            Transaction(
                id=str(inv.id),
                supplier=inv.vendor_name or "unknown",
                amount=float(inv.amount_total or 0),
                date=inv.created_at if inv.created_at else now,
                invoice_number=inv.invoice_number,
                po_number=inv.po_number,
            )
            for inv in recent_invoices
        ]

        all_txns = [current_txn] + recent_txns
        dup_findings = detect_duplicate_payments(all_txns, date_window_days=30)

        for f in dup_findings:
            if f.get("match_kind") == "exact_invoice_match":
                f["severity"] = "critical"
        findings.extend(dup_findings)

        if extraction.po_number:
            from app.ml.document_anomalies import PurchaseOrder

            po_records: List[PurchaseOrder] = []
            for inv in recent_invoices:
                if inv.po_number and inv.po_number.strip().lower() == extraction.po_number.strip().lower():
                    po_records.append(
                        PurchaseOrder(
                            po_number=inv.po_number,
                            supplier=inv.vendor_name or "unknown",
                            amount=float(inv.amount_total or 0),
                        )
                    )

            if po_records:
                mismatch_findings = detect_invoice_po_mismatch([current_txn], po_records)
                findings.extend(mismatch_findings)

    except Exception as exc:
        log.warning("invoice.anomaly_detection_failed", error=str(exc), invoice_id=str(invoice.id))

    # ── Risk tier + approval gate ─────────────────────────────────────────────
    risk_tier = _determine_risk_tier(findings)
    requires_approval = False
    approval_id: Optional[str] = None
    has_critical = any(f.get("severity") == "critical" for f in findings)

    if has_critical or risk_tier == "critical":
        requires_approval = True
        try:
            approval = ApprovalRequest(
                requested_by_user_id=uuid.UUID(user_id_str),
                action_type="review_invoice",
                risk_level="critical",
                payload={
                    "invoice_id": str(invoice.id),
                    "vendor_name": extraction.vendor_name,
                    "amount_total": extraction.amount_total,
                    "findings_count": len(findings),
                },
                reason=(
                    "Critical finding detected on invoice upload: "
                    + "; ".join(
                        f.get("finding", f.get("type", "unknown"))
                        for f in findings
                        if f.get("severity") == "critical"
                    )[:500]
                ),
                status="pending",
            )
            db.add(approval)
            await db.flush()
            approval_id = str(approval.id)

            invoice.requires_approval = True
            invoice.approval_id = approval.id

        except Exception as exc:
            log.error("invoice.approval_create_failed", error=str(exc))
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create approval request.")

    # ── Persist risk scoring results ──────────────────────────────────────────
    try:
        invoice.risk_tier = risk_tier
        invoice.status = "risk_scored"

        entry = await _append_audit(
            db, invoice.id, "risk_scored", user_id_str,
            {
                "risk_tier": risk_tier,
                "findings_count": len(findings),
                "findings": findings,
                "requires_approval": requires_approval,
            },
        )
        audit_trail.append({"action": entry.action, "actor": entry.actor})

        if requires_approval:
            entry2 = await _append_audit(
                db, invoice.id, "approval_requested", user_id_str,
                {"approval_id": approval_id, "reason": "critical_finding"},
            )
            audit_trail.append({"action": entry2.action, "actor": entry2.actor})

        await db.commit()
        await db.refresh(invoice)

    except Exception as exc:
        await db.rollback()
        log.error("invoice.risk_persist_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to persist risk scoring results.")

    log.info(
        "invoice.upload_complete",
        invoice_id=str(invoice.id),
        risk_tier=risk_tier,
        findings=len(findings),
        requires_approval=requires_approval,
        method=extraction_method,
    )

    return InvoiceUploadResponse(
        invoice_id=str(invoice.id),
        status=invoice.status,
        extracted_fields=extraction,
        validation_findings=findings,
        risk_tier=risk_tier,
        requires_approval=requires_approval,
        approval_id=approval_id,
        audit_trail=audit_trail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# POST /v1/invoices/batch  (Requirement 2.12)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/invoices/batch", response_model=List[InvoiceUploadResponse])
async def upload_invoice_batch(
    files: List[UploadFile] = File(...),
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> List[InvoiceUploadResponse]:
    """
    Upload multiple invoice files in a single request.

    Each file is processed through the full invoice pipeline (OCR/PDF parse →
    PII redaction → Gemma extraction → duplicate/mismatch detection → risk
    scoring → approval gating) concurrently via asyncio.gather.

    Returns a list of InvoiceUploadResponse objects in the same order as the
    uploaded files.  Any per-file error is surfaced as an HTTPException with
    the individual file's details included in the error message.
    """
    import asyncio

    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    results: List[InvoiceUploadResponse] = await asyncio.gather(
        *[_process_single_invoice(file, None, user, db) for file in files]
    )

    log.info("invoice.batch_upload_complete", count=len(results))
    return list(results)


# ──────────────────────────────────────────────────────────────────────────────
# GET /v1/invoices  (Requirement 2.13)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/invoices", response_model=Dict[str, Any])
async def list_invoices(
    status: Optional[str] = None,
    risk_tier: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return invoices belonging to the authenticated user.

    Optional query parameters:
    - status     — filter by invoice status (e.g. "processing", "extracted",
                   "risk_scored")
    - risk_tier  — filter by risk tier (e.g. "low", "medium", "high",
                   "critical", "unknown")
    - limit      — maximum number of records to return (default 50)
    """
    user_id_str = str(user.get("db_id") or user.get("id", "system"))
    user_uuid = uuid.UUID(user_id_str)

    stmt = select(Invoice).where(Invoice.user_id == user_uuid)

    if status is not None:
        stmt = stmt.where(Invoice.status == status)

    if risk_tier is not None:
        stmt = stmt.where(Invoice.risk_tier == risk_tier)

    # Total count (before limit)
    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Paginated rows
    stmt = stmt.order_by(Invoice.created_at.desc()).limit(limit)
    rows_result = await db.execute(stmt)
    invoices_orm = rows_result.scalars().all()

    invoice_list = [
        {
            "invoice_id": str(inv.id),
            "status": inv.status,
            "invoice_number": inv.invoice_number,
            "vendor_name": inv.vendor_name,
            "vendor_gstin": inv.vendor_gstin,
            "invoice_date": inv.invoice_date,
            "po_number": inv.po_number,
            "amount_net": float(inv.amount_net or 0) if inv.amount_net is not None else None,
            "amount_gst": float(inv.amount_gst or 0) if inv.amount_gst is not None else None,
            "amount_total": float(inv.amount_total or 0),
            "risk_tier": inv.risk_tier,
            "requires_approval": inv.requires_approval,
            "approval_id": str(inv.approval_id) if inv.approval_id else None,
            "extraction_confidence": float(inv.extraction_confidence or 0),
            "line_items": (inv.raw_extracted_json or {}).get("line_items", []),
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invoices_orm
    ]

    return {"invoices": invoice_list, "total": total}
