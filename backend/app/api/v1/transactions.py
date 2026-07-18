"""POST /v1/transactions/ingest — batch transaction ingestion with AML/CFT analysis.

Implements the Transaction Monitoring Workflow (design.md §2.2):
  1. PII redact all description and supplier fields
  2. Run DocumentAnomalies.scan_all() for duplicate payments, invoice mismatches,
     unusual patterns
  3. Call TransactionAgent.run() with Gemma for AML/CFT reasoning
  4. Gate behind ApprovalRequest when risk_tier=critical
  5. Persist TransactionBatch; return structured response

Requirements: 3.1–3.5
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.sap_mapper import TransactionRecord
from app.core.pii_redaction import redact_user_input
from app.core.security import get_db_user
from app.db.models import ApprovalRequest, AuditTrailEntry, TransactionBatch
from app.db.session import get_db
from app.ml.document_anomalies import (
    Transaction as DaTransaction,
    scan_all as da_scan_all,
)

log = structlog.get_logger()
router = APIRouter()

# ---------------------------------------------------------------------------
# Valid ingestion sources (Requirement 3.1)
# ---------------------------------------------------------------------------
VALID_SOURCES = {"manual", "sap", "excel", "outlook", "csv"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

# TransactionRecord is imported from app.connectors.sap_mapper — it is the
# shared canonical DTO used by all ingestion paths (SAP mapper, Excel, manual).


class TransactionIngestRequest(BaseModel):
    """Request body for POST /v1/transactions/ingest."""

    transactions: List[TransactionRecord]
    source: str = Field("manual", description="One of: manual | sap | excel | outlook | csv")
    import_purchase_orders: bool = False
    historical_avg_amount: Optional[float] = None
    historical_avg_monthly_count: Optional[float] = None


class TransactionIngestResponse(BaseModel):
    """Response body from POST /v1/transactions/ingest."""

    batch_id: str
    total_processed: int
    flagged_count: int
    duplicate_payments: List[Dict[str, Any]]
    invoice_mismatches: List[Dict[str, Any]]
    unusual_transactions: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    requires_approval: bool
    approval_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_uuid(v: Any) -> Optional[uuid.UUID]:
    """Coerce *v* to UUID or return None."""
    try:
        return uuid.UUID(str(v)) if v else None
    except Exception:
        return None


async def _append_batch_audit(
    db: AsyncSession,
    batch_id: uuid.UUID,
    action: str,
    actor: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditTrailEntry:
    """Append an AuditTrailEntry for a transaction batch. TransactionBatch itself
    only stores aggregate counts (total_processed, flagged_count, risk_tier) —
    the actual duplicate/mismatch/unusual findings and agent reasoning only
    survive here, so the frontend detail drawer reads them back via
    GET /v1/audit-trail?entity_type=transaction_batch&entity_id=<batch_id>."""
    entry = AuditTrailEntry(
        action=action,
        actor=actor,
        entity_type="transaction_batch",
        entity_id=str(batch_id),
        metadata_=metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry


def _record_to_da_transaction(rec: TransactionRecord) -> DaTransaction:
    """Convert a TransactionRecord Pydantic model to the DocumentAnomalies Transaction dataclass.

    DocumentAnomalies.scan_all() uses its own ``Transaction`` dataclass
    (with a ``datetime`` date field), while the ingestion DTO uses an ISO-string
    date.  This function bridges the two representations.
    """
    try:
        date = datetime.strptime(rec.transaction_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        date = datetime.now()

    return DaTransaction(
        id=rec.external_id or str(uuid.uuid4()),
        supplier=rec.supplier,
        amount=rec.amount,
        date=date,
        invoice_number=rec.invoice_number,
        po_number=rec.po_number,
        description=rec.description,
    )


def _redact_records(records: List[TransactionRecord], user_id: str) -> List[TransactionRecord]:
    """Apply PII redaction to ``description`` and ``supplier`` on every record.

    Returns a new list of TransactionRecord instances with clean field values
    safe for LLM processing (Requirement 3.2).
    """
    redacted: List[TransactionRecord] = []
    for rec in records:
        clean_desc = redact_user_input(rec.description, user_id)["redacted_text"]
        clean_supplier = redact_user_input(rec.supplier, user_id)["redacted_text"]
        # model_copy preserves all other fields unchanged
        redacted.append(rec.model_copy(update={"description": clean_desc, "supplier": clean_supplier}))
    return redacted


def _infer_risk_tier(scan_result: Dict[str, Any], agent_reasoning: str) -> str:
    """Derive a simple risk tier from anomaly scan results and agent reasoning.

    Logic (in priority order):
    - any critical-severity finding → critical
    - ``requires_human_approval`` flagged by scan_all → critical
    - 1+ high-severity findings in combined text → high
    - agent reasoning contains "high risk" / "str" keywords → high
    - any finding at all → medium
    - no findings → low
    """
    all_findings: List[Dict[str, Any]] = (
        scan_result.get("duplicate_payments", [])
        + scan_result.get("invoice_mismatches", [])
        + scan_result.get("unusual_transactions", [])
    )

    severities = {f.get("severity", "low") for f in all_findings}

    if "critical" in severities or scan_result.get("requires_human_approval"):
        return "critical"

    reasoning_lower = agent_reasoning.lower()
    high_keywords = ["high risk", "str required", "money laundering", "critical", "suspicious transaction"]
    if "high" in severities or any(kw in reasoning_lower for kw in high_keywords):
        return "high"

    if all_findings:
        return "medium"

    return "low"


# ---------------------------------------------------------------------------
# Core ingest endpoint
# ---------------------------------------------------------------------------

@router.post("/transactions/ingest", response_model=TransactionIngestResponse)
async def ingest_transactions(
    req: TransactionIngestRequest,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionIngestResponse:
    """Ingest a batch of financial transactions, scan for anomalies, and run AML/CFT analysis.

    Steps:
      1. Validate ``source`` — 422 if unknown.
      2. PII-redact all ``description`` and ``supplier`` fields.
      3. Convert to DocumentAnomalies Transaction dataclasses and call ``scan_all()``.
      4. Call ``TransactionAgent.run()`` with Gemma for structured AML reasoning.
      5. Derive risk_tier; create ``ApprovalRequest`` when critical.
      6. Persist ``TransactionBatch``; return ``TransactionIngestResponse``.
    """
    # ── Step 1: Validate source (Requirement 3.1) ────────────────────────────
    if req.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{req.source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    user_id: str = user["id"]

    log.info(
        "transactions.ingest.start",
        user_id=user_id,
        source=req.source,
        count=len(req.transactions),
    )

    try:
        # ── Step 2: PII redaction (Requirement 3.2) ─────────────────────────
        clean_records = _redact_records(req.transactions, user_id)

        # ── Step 3: DocumentAnomalies.scan_all() (Requirement 3.3) ──────────
        da_transactions = [_record_to_da_transaction(r) for r in clean_records]

        scan_result = da_scan_all(
            transactions=da_transactions,
            purchase_orders=None,  # PO import path handled by task 4.2
            provided_docs=None,
            sector=None,
        )

        duplicate_payments: List[Dict[str, Any]] = scan_result.get("duplicate_payments", [])
        invoice_mismatches: List[Dict[str, Any]] = scan_result.get("invoice_mismatches", [])
        unusual_transactions: List[Dict[str, Any]] = scan_result.get("unusual_transactions", [])

        total_findings = (
            len(duplicate_payments) + len(invoice_mismatches) + len(unusual_transactions)
        )
        flagged_count = total_findings

        # ── Step 4: TransactionAgent.run() (Requirement 3.3 / 3.4) ─────────
        # Build a compact description of the batch for the agent prompt.
        batch_summary_parts = [
            f"Batch of {len(clean_records)} transactions from source '{req.source}'.",
            f"Anomaly scan: {len(duplicate_payments)} duplicate payments, "
            f"{len(invoice_mismatches)} invoice mismatches, "
            f"{len(unusual_transactions)} unusual patterns detected.",
        ]

        # Include a brief sample of supplier/amount to give the agent context.
        for i, rec in enumerate(clean_records[:5]):
            batch_summary_parts.append(
                f"  [{i+1}] Supplier: {rec.supplier}, Amount: ₹{rec.amount:,.2f}, "
                f"Date: {rec.transaction_date}, Desc: {rec.description[:80]}"
            )
        if len(clean_records) > 5:
            batch_summary_parts.append(f"  … and {len(clean_records) - 5} more.")

        if scan_result.get("mapped_stage0_flags"):
            batch_summary_parts.append(
                "Stage-0 flags: " + ", ".join(scan_result["mapped_stage0_flags"])
            )

        agent_query = "\n".join(batch_summary_parts)

        from app.agents.transaction_agent import TransactionAgent  # local import avoids circular

        agent = TransactionAgent()
        try:
            agent_output = await agent.run(query=agent_query, packs=[], matter_docs=[])
            agent_reasoning: str = agent_output.get("reasoning", "")
            agent_confidence: float = float(agent_output.get("confidence", 0.5))
        except Exception as exc:
            log.error("transactions.ingest.agent_error", error=str(exc))
            agent_reasoning = f"Agent unavailable: {exc}"
            agent_confidence = 0.3

        # ── Derive risk_tier ────────────────────────────────────────────────
        risk_tier = _infer_risk_tier(scan_result, agent_reasoning)

        risk_assessment: Dict[str, Any] = {
            "risk_tier": risk_tier,
            # "reasoning" and "confidence" are the canonical keys per the response contract
            "reasoning": agent_reasoning,
            "confidence": agent_confidence,
            # Additional context fields
            "total_findings": total_findings,
            "mapped_stage0_flags": scan_result.get("mapped_stage0_flags", []),
            "requires_human_approval": scan_result.get("requires_human_approval", False),
        }

        # ── Step 5: ApprovalRequest when risk_tier=critical (Requirement 3.5) ─
        requires_approval = risk_tier == "critical"
        approval_id: Optional[str] = None

        if requires_approval:
            approval = ApprovalRequest(
                requested_by_user_id=_safe_uuid(user["db_id"]),
                action_type="escalate_transaction",
                risk_level="critical",
                payload={
                    "source": req.source,
                    "total_processed": len(clean_records),
                    "flagged_count": flagged_count,
                    "duplicate_count": len(duplicate_payments),
                    "mismatch_count": len(invoice_mismatches),
                    "unusual_count": len(unusual_transactions),
                    "risk_tier": risk_tier,
                    "agent_confidence": agent_confidence,
                },
                reason=(
                    f"Critical risk transaction batch ({len(clean_records)} records, "
                    f"{flagged_count} flagged). AML/CFT review required before escalation."
                ),
                status="pending",
            )
            db.add(approval)
            await db.flush()  # populate approval.id before commit
            approval_id = str(approval.id)
            log.info("transactions.ingest.approval_created", approval_id=approval_id)

        # ── Step 6: Persist TransactionBatch ────────────────────────────────
        batch = TransactionBatch(
            user_id=uuid.UUID(user["db_id"]),
            source=req.source,
            total_processed=len(clean_records),
            flagged_count=flagged_count,
            risk_tier=risk_tier,
            requires_approval=requires_approval,
            approval_id=_safe_uuid(approval_id) if approval_id else None,
        )
        db.add(batch)
        await db.flush()  # obtain batch.id before writing audit entries

        await _append_batch_audit(
            db, batch.id, "batch_ingested", user_id,
            {"source": req.source, "total_processed": len(clean_records)},
        )
        await _append_batch_audit(
            db, batch.id, "batch_risk_scored", user_id,
            {
                "risk_tier": risk_tier,
                "agent_reasoning": agent_reasoning,
                "agent_confidence": agent_confidence,
                "duplicate_payments": duplicate_payments,
                "invoice_mismatches": invoice_mismatches,
                "unusual_transactions": unusual_transactions,
                "requires_approval": requires_approval,
                "approval_id": approval_id,
            },
        )

        await db.commit()
        await db.refresh(batch)

    except HTTPException:
        raise
    except Exception as exc:
        log.error("transactions.ingest.error", error=str(exc), user_id=user_id)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Transaction ingest failed") from exc

    batch_id = str(batch.id)

    log.info(
        "transactions.ingest.complete",
        batch_id=batch_id,
        risk_tier=risk_tier,
        flagged_count=flagged_count,
        requires_approval=requires_approval,
    )

    return TransactionIngestResponse(
        batch_id=batch_id,
        total_processed=len(clean_records),
        flagged_count=flagged_count,
        duplicate_payments=duplicate_payments,
        invoice_mismatches=invoice_mismatches,
        unusual_transactions=unusual_transactions,
        risk_assessment=risk_assessment,
        requires_approval=requires_approval,
        approval_id=approval_id,
    )


# ---------------------------------------------------------------------------
# SAP ingestion sub-route (Requirements 3.6, 3.8)
# ---------------------------------------------------------------------------

@router.post("/transactions/ingest/from-sap", response_model=TransactionIngestResponse)
async def ingest_transactions_from_sap(
    top: int = 100,
    filter_expr: Optional[str] = None,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionIngestResponse:
    """Fetch supplier invoices from SAP OData and run the standard ingest pipeline.

    Query params:
      - ``top``: maximum number of invoices to fetch (default 100).
      - ``filter_expr``: optional OData ``$filter`` expression passed through to SAP.

    Steps:
      1. Guard: return HTTP 503 if SAPODataConnector is not configured (Req 3.8).
      2. Fetch ``A_SupplierInvoice`` records via ``SAPODataConnector.fetch_supplier_invoices()``.
      3. Map each raw OData dict to a ``TransactionRecord`` via ``map_sap_invoice_to_transaction``.
      4. Delegate to the shared ingest pipeline (``ingest_transactions``) with source='sap'.
    """
    from app.connectors.sap_odata import SAPODataConnector
    from app.connectors.sap_mapper import map_sap_invoice_to_transaction

    connector = SAPODataConnector()

    # Requirement 3.8 — return 503 when SAP connector is not configured
    if not connector.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "SAP connector is not configured. "
                "Set SAP_ODATA_BASE_URL, SAP_USERNAME, and SAP_PASSWORD environment variables "
                "pointing at your SAP Gateway / S/4HANA Cloud OData endpoint."
            ),
        )

    user_id: str = user["id"]
    log.info("transactions.ingest.from_sap.start", user_id=user_id, top=top, filter_expr=filter_expr)

    try:
        raw_invoices = await connector.fetch_supplier_invoices(top=top, filter_expr=filter_expr)
    except Exception as exc:
        log.error("transactions.ingest.from_sap.fetch_error", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=502, detail=f"SAP OData fetch failed: {exc}") from exc

    # Map raw SAP OData dicts → canonical TransactionRecord objects (Req 3.6)
    records: List[TransactionRecord] = [map_sap_invoice_to_transaction(inv) for inv in raw_invoices]

    log.info("transactions.ingest.from_sap.mapped", user_id=user_id, count=len(records))

    # Reuse the core ingest pipeline by constructing a TransactionIngestRequest
    ingest_req = TransactionIngestRequest(transactions=records, source="sap")
    return await ingest_transactions(ingest_req, user=user, db=db)


# ---------------------------------------------------------------------------
# Excel (Microsoft Graph) ingestion sub-route (Requirement 3.7)
# ---------------------------------------------------------------------------

def _excel_row_to_transaction_record(row: Dict[str, Any]) -> TransactionRecord:
    """Map a flat Excel row dict to a ``TransactionRecord``.

    Expected column names (case-insensitive lookup with common aliases):
      - ExternalId / ID / InvoiceId / external_id
      - Supplier / Vendor / SupplierName / supplier
      - Amount / InvoiceAmount / GrossAmount / amount
      - Date / TransactionDate / InvoiceDate / DocumentDate / transaction_date
      - InvoiceNumber / Invoice / invoice_number
      - PONumber / PO / PurchaseOrder / po_number
      - Description / Notes / Remarks / description
      - Currency / currency
      - AccountCode / Account / account_code
    """
    def _get(keys: List[str], default: Any = None) -> Any:
        """Case-insensitive key lookup against the row dict."""
        row_lower = {k.lower().replace(" ", "_"): v for k, v in row.items()}
        for key in keys:
            val = row_lower.get(key.lower().replace(" ", "_"))
            if val is not None and str(val).strip() != "":
                return val
        return default

    external_id = str(_get(["externalid", "id", "invoiceid", "external_id"], "") or "")
    supplier = str(_get(["supplier", "vendor", "suppliername", "vendor_name"], "") or "")

    raw_amount = _get(["amount", "invoiceamount", "grossamount", "invoice_amount", "gross_amount"], 0.0)
    try:
        amount = abs(float(str(raw_amount).strip()))
    except (ValueError, TypeError):
        amount = 0.0

    raw_date = _get(["date", "transactiondate", "invoicedate", "documentdate",
                     "transaction_date", "invoice_date", "document_date"])
    from app.connectors.sap_mapper import _parse_date  # reuse the same date normaliser
    transaction_date = _parse_date(str(raw_date) if raw_date else None)

    raw_invoice = _get(["invoicenumber", "invoice", "invoice_number"])
    invoice_number = str(raw_invoice) if raw_invoice else None

    raw_po = _get(["ponumber", "po", "purchaseorder", "po_number", "purchase_order"])
    po_number = str(raw_po) if raw_po else None

    raw_currency = _get(["currency"])
    currency = str(raw_currency) if raw_currency else "INR"

    raw_description = _get(["description", "notes", "remarks"])
    description = str(raw_description) if raw_description else ""

    raw_account = _get(["accountcode", "account", "account_code"])
    account_code = str(raw_account) if raw_account else None

    return TransactionRecord(
        external_id=external_id,
        supplier=supplier,
        amount=amount,
        transaction_date=transaction_date,
        invoice_number=invoice_number,
        po_number=po_number,
        description=description,
        currency=currency,
        account_code=account_code,
    )


@router.post("/transactions/ingest/from-excel", response_model=TransactionIngestResponse)
async def ingest_transactions_from_excel(
    drive_item_path: str,
    worksheet: str = "Sheet1",
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionIngestResponse:
    """Fetch rows from an Excel workbook via Microsoft Graph and run the standard ingest pipeline.

    Query params:
      - ``drive_item_path``: path to the .xlsx file in the mailbox's OneDrive,
        e.g. ``Finance/Vendor Payments.xlsx``.
      - ``worksheet``: worksheet name to read (default ``Sheet1``).

    Steps:
      1. Guard: return HTTP 503 if MicrosoftGraphConnector is not configured.
      2. Retrieve the worksheet's used range via ``MicrosoftGraphConnector.read_excel_range()``.
      3. Map each row dict to a ``TransactionRecord`` via ``_excel_row_to_transaction_record``.
      4. Delegate to the shared ingest pipeline (``ingest_transactions``) with source='excel'.
    """
    from app.connectors.microsoft_graph import MicrosoftGraphConnector

    connector = MicrosoftGraphConnector()

    # Graceful 503 when Microsoft Graph credentials are not configured (Req 3.7)
    if not connector.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Microsoft Graph connector is not configured. "
                "Set MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, "
                "and MS_GRAPH_MAILBOX_UPN environment variables for your Azure AD app registration."
            ),
        )

    user_id: str = user["id"]
    log.info(
        "transactions.ingest.from_excel.start",
        user_id=user_id,
        drive_item_path=drive_item_path,
        worksheet=worksheet,
    )

    try:
        rows = await connector.read_excel_range(drive_item_path=drive_item_path, worksheet=worksheet)
    except Exception as exc:
        log.error("transactions.ingest.from_excel.fetch_error", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=502, detail=f"Excel (Microsoft Graph) fetch failed: {exc}") from exc

    if not rows:
        log.warning("transactions.ingest.from_excel.empty", user_id=user_id, drive_item_path=drive_item_path)
        raise HTTPException(
            status_code=422,
            detail=f"Worksheet '{worksheet}' in '{drive_item_path}' is empty or contains no data rows.",
        )

    # Map Excel row dicts → canonical TransactionRecord objects (Req 3.7)
    records: List[TransactionRecord] = [_excel_row_to_transaction_record(row) for row in rows]

    log.info("transactions.ingest.from_excel.mapped", user_id=user_id, count=len(records))

    # Reuse the core ingest pipeline by constructing a TransactionIngestRequest
    ingest_req = TransactionIngestRequest(transactions=records, source="excel")
    return await ingest_transactions(ingest_req, user=user, db=db)


@router.get("/transactions/batches")
async def list_transaction_batches(
    risk_tier: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List transaction batches for the authenticated user, most recent first."""
    from sqlalchemy import select, desc

    user_id = uuid.UUID(str(user["db_id"]))
    stmt = select(TransactionBatch).where(TransactionBatch.user_id == user_id)
    if risk_tier:
        stmt = stmt.where(TransactionBatch.risk_tier == risk_tier)
    stmt = stmt.order_by(desc(TransactionBatch.created_at)).limit(limit)

    result = await db.execute(stmt)
    batches = result.scalars().all()

    return {
        "total": len(batches),
        "batches": [
            {
                "batch_id": str(b.id),
                "source": b.source,
                "total_processed": b.total_processed,
                "flagged_count": b.flagged_count,
                "risk_tier": b.risk_tier,
                "requires_approval": b.requires_approval,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in batches
        ],
    }
