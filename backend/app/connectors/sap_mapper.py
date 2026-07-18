"""SAP OData → TransactionRecord mapper.

Maps raw SAP OData A_SupplierInvoice fields to the platform's canonical
TransactionRecord Pydantic model. This module is intentionally pure (no I/O,
no DB, no HTTP) so it is straightforward to unit-test in isolation.

Field mapping (Requirements 8.1–8.8):
  SupplierInvoice            → external_id
  SupplierInvoiceIDByInvcgParty → invoice_number
  Supplier                   → supplier
  DocumentDate               → transaction_date  (YYYY-MM-DD)
  InvoiceGrossAmount         → amount            (positive float)
  DocumentCurrency           → currency
  PurchaseOrder              → po_number
  DocumentHeaderText         → description
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Canonical transaction representation (Requirement 8, TransactionRecord)
# Also referenced by app/api/v1/transactions.py once that module is created.
# ---------------------------------------------------------------------------

class TransactionRecord(BaseModel):
    """Canonical in-platform representation of a financial transaction.

    This model is the shared DTO used by the Transaction_Ingestor, the
    SAP_Mapper, and the Excel/manual ingestion paths.
    """

    external_id: str
    supplier: str
    amount: float
    transaction_date: str  # ISO date string: YYYY-MM-DD
    invoice_number: Optional[str] = None
    po_number: Optional[str] = None
    description: str = ""
    currency: str = "INR"
    account_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: coerce SAP's OData amount to a positive float
# SAP OData commonly returns numeric strings (e.g. "12500.00"), ints, or floats.
# ---------------------------------------------------------------------------

def _coerce_amount(raw: Union[str, int, float, None]) -> float:
    """Convert *raw* to a positive float.

    Handles the three types SAP OData may emit:
      - str  → float(raw)  (strips leading/trailing whitespace first)
      - int  → float(raw)
      - float → raw
      - None / missing → 0.0

    The result is always non-negative (abs is applied per Requirement 8.5).
    """
    if raw is None:
        return 0.0
    try:
        value = float(str(raw).strip())
    except (ValueError, TypeError):
        value = 0.0
    return abs(value)


# ---------------------------------------------------------------------------
# Helper: parse or default the document date
# ---------------------------------------------------------------------------

def _parse_date(raw: Optional[str]) -> str:
    """Return an ISO date string for *raw*.

    Accepts "YYYY-MM-DD" (SAP standard); falls back to today's date
    (datetime.now()) when the field is absent or unparseable, per Req 8.9.
    """
    if raw:
        try:
            # Validate the string really is YYYY-MM-DD
            datetime.strptime(raw.strip(), "%Y-%m-%d")
            return raw.strip()
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Public mapping function (Requirement 8.1–8.9)
# ---------------------------------------------------------------------------

def map_sap_invoice_to_transaction(sap_invoice: Dict[str, Any]) -> TransactionRecord:
    """Map a raw SAP OData A_SupplierInvoice dict to a ``TransactionRecord``.

    Preconditions:
        - *sap_invoice* is a plain dict (as returned by SAPODataConnector).
        - All fields are optional at the call-site; defaults are applied for
          every absent or ``None`` field (Requirement 8.9).

    Postconditions:
        - The returned ``TransactionRecord`` has all required fields set.
        - ``amount`` is always a non-negative float.
        - ``transaction_date`` is always a valid YYYY-MM-DD string.
        - Optional string fields (invoice_number, po_number) are ``None``
          when the corresponding SAP field is absent or empty.
        - ``description`` defaults to ``""`` when DocumentHeaderText is absent.
    """
    # Required string fields — both map to non-optional str on TransactionRecord.
    # SAP's SupplierInvoice is the internal document number; treat as external_id.
    external_id: str = str(sap_invoice.get("SupplierInvoice") or "")
    supplier: str = str(sap_invoice.get("Supplier") or "")

    # Amount: SAP OData may return string, int, or float — coerce to positive float.
    amount: float = _coerce_amount(sap_invoice.get("InvoiceGrossAmount"))

    # Date: parse from "YYYY-MM-DD"; default to today if missing.
    transaction_date: str = _parse_date(sap_invoice.get("DocumentDate"))  # type: ignore[arg-type]

    # Optional string fields — None when absent/empty (Requirement 8.9).
    raw_invoice_number = sap_invoice.get("SupplierInvoiceIDByInvcgParty")
    invoice_number: Optional[str] = str(raw_invoice_number) if raw_invoice_number else None

    raw_po_number = sap_invoice.get("PurchaseOrder")
    po_number: Optional[str] = str(raw_po_number) if raw_po_number else None

    raw_currency = sap_invoice.get("DocumentCurrency")
    currency: str = str(raw_currency) if raw_currency else "INR"

    # Description defaults to "" per Requirement 8.9.
    raw_description = sap_invoice.get("DocumentHeaderText")
    description: str = str(raw_description) if raw_description else ""

    return TransactionRecord(
        external_id=external_id,
        supplier=supplier,
        amount=amount,
        transaction_date=transaction_date,
        invoice_number=invoice_number,
        po_number=po_number,
        description=description,
        currency=currency,
        # account_code is not present in SAP A_SupplierInvoice — defaults to None.
        account_code=None,
    )
