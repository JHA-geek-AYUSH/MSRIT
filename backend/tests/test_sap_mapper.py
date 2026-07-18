"""Unit tests for map_sap_invoice_to_transaction (Requirements 8.1–8.9).

Run with:
    pytest backend/tests/test_sap_mapper.py
from the workspace root.
"""
from __future__ import annotations

import pytest
from datetime import datetime

from app.connectors.sap_mapper import map_sap_invoice_to_transaction, TransactionRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_SAP_INVOICE: dict = {
    "SupplierInvoice": "5100001234",                  # → external_id      (Req 8.1)
    "SupplierInvoiceIDByInvcgParty": "VINV-2024-001", # → invoice_number   (Req 8.2)
    "Supplier": "ACME_CORP",                           # → supplier         (Req 8.3)
    "DocumentDate": "2024-03-15",                      # → transaction_date (Req 8.4)
    "InvoiceGrossAmount": "12500.00",                  # → amount           (Req 8.5)
    "DocumentCurrency": "USD",                         # → currency         (Req 8.6)
    "PurchaseOrder": "PO-2024-9900",                   # → po_number        (Req 8.7)
    "DocumentHeaderText": "Q1 software licences",     # → description      (Req 8.8)
}


# ---------------------------------------------------------------------------
# 1. Full mapping — all 8 fields present
# ---------------------------------------------------------------------------

class TestFullMapping:
    """Req 8.1–8.8: every field maps to the correct TransactionRecord attribute."""

    def setup_method(self):
        self.result = map_sap_invoice_to_transaction(FULL_SAP_INVOICE)

    def test_returns_transaction_record(self):
        assert isinstance(self.result, TransactionRecord)

    def test_external_id_mapped(self):
        """Req 8.1: SupplierInvoice → external_id."""
        assert self.result.external_id == "5100001234"

    def test_invoice_number_mapped(self):
        """Req 8.2: SupplierInvoiceIDByInvcgParty → invoice_number."""
        assert self.result.invoice_number == "VINV-2024-001"

    def test_supplier_mapped(self):
        """Req 8.3: Supplier → supplier."""
        assert self.result.supplier == "ACME_CORP"

    def test_transaction_date_mapped(self):
        """Req 8.4: DocumentDate → transaction_date (YYYY-MM-DD)."""
        assert self.result.transaction_date == "2024-03-15"

    def test_amount_mapped(self):
        """Req 8.5: InvoiceGrossAmount → amount (positive float)."""
        assert self.result.amount == 12500.0

    def test_currency_mapped(self):
        """Req 8.6: DocumentCurrency → currency."""
        assert self.result.currency == "USD"

    def test_po_number_mapped(self):
        """Req 8.7: PurchaseOrder → po_number."""
        assert self.result.po_number == "PO-2024-9900"

    def test_description_mapped(self):
        """Req 8.8: DocumentHeaderText → description."""
        assert self.result.description == "Q1 software licences"

    def test_account_code_is_none(self):
        """account_code is not sourced from SAP A_SupplierInvoice — must be None."""
        assert self.result.account_code is None


# ---------------------------------------------------------------------------
# 2. Optional fields absent one at a time (Req 8.9)
# ---------------------------------------------------------------------------

class TestOptionalFieldDefaults:
    """Req 8.9: each optional field falls back to the specified default when absent."""

    def _invoice_without(self, key: str) -> dict:
        d = dict(FULL_SAP_INVOICE)
        d.pop(key)
        return d

    def test_missing_invoice_number_defaults_to_none(self):
        """SupplierInvoiceIDByInvcgParty absent → invoice_number is None."""
        result = map_sap_invoice_to_transaction(self._invoice_without("SupplierInvoiceIDByInvcgParty"))
        assert result.invoice_number is None

    def test_missing_po_number_defaults_to_none(self):
        """PurchaseOrder absent → po_number is None."""
        result = map_sap_invoice_to_transaction(self._invoice_without("PurchaseOrder"))
        assert result.po_number is None

    def test_missing_currency_defaults_to_inr(self):
        """DocumentCurrency absent → currency == 'INR'."""
        result = map_sap_invoice_to_transaction(self._invoice_without("DocumentCurrency"))
        assert result.currency == "INR"

    def test_missing_description_defaults_to_empty_string(self):
        """DocumentHeaderText absent → description == ''."""
        result = map_sap_invoice_to_transaction(self._invoice_without("DocumentHeaderText"))
        assert result.description == ""

    def test_missing_document_date_defaults_to_today(self):
        """DocumentDate absent → transaction_date is today's date (YYYY-MM-DD)."""
        result = map_sap_invoice_to_transaction(self._invoice_without("DocumentDate"))
        today = datetime.now().strftime("%Y-%m-%d")
        assert result.transaction_date == today

    def test_none_invoice_number_defaults_to_none(self):
        """SupplierInvoiceIDByInvcgParty=None → invoice_number is None."""
        invoice = dict(FULL_SAP_INVOICE, SupplierInvoiceIDByInvcgParty=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.invoice_number is None

    def test_none_po_number_defaults_to_none(self):
        """PurchaseOrder=None → po_number is None."""
        invoice = dict(FULL_SAP_INVOICE, PurchaseOrder=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.po_number is None

    def test_none_currency_defaults_to_inr(self):
        """DocumentCurrency=None → currency == 'INR'."""
        invoice = dict(FULL_SAP_INVOICE, DocumentCurrency=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.currency == "INR"

    def test_none_description_defaults_to_empty_string(self):
        """DocumentHeaderText=None → description == ''."""
        invoice = dict(FULL_SAP_INVOICE, DocumentHeaderText=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.description == ""


# ---------------------------------------------------------------------------
# 3. InvoiceGrossAmount type coercion (Req 8.5)
# ---------------------------------------------------------------------------

class TestAmountCoercion:
    """Req 8.5: amount must be a positive float regardless of input type."""

    def test_amount_as_string(self):
        """SAP OData commonly returns amount as a numeric string."""
        invoice = dict(FULL_SAP_INVOICE, InvoiceGrossAmount="12500.00")
        result = map_sap_invoice_to_transaction(invoice)
        assert isinstance(result.amount, float)
        assert result.amount == 12500.0

    def test_amount_as_int(self):
        """Integer amounts must be coerced to float."""
        invoice = dict(FULL_SAP_INVOICE, InvoiceGrossAmount=12500)
        result = map_sap_invoice_to_transaction(invoice)
        assert isinstance(result.amount, float)
        assert result.amount == 12500.0

    def test_amount_as_float(self):
        """Float amounts pass through as-is."""
        invoice = dict(FULL_SAP_INVOICE, InvoiceGrossAmount=12500.00)
        result = map_sap_invoice_to_transaction(invoice)
        assert isinstance(result.amount, float)
        assert result.amount == 12500.0

    def test_negative_amount_becomes_positive(self):
        """Req 8.5: amount is always non-negative (abs applied)."""
        invoice = dict(FULL_SAP_INVOICE, InvoiceGrossAmount="-100.0")
        result = map_sap_invoice_to_transaction(invoice)
        assert result.amount == 100.0

    def test_missing_amount_defaults_to_zero(self):
        """InvoiceGrossAmount absent → amount == 0.0."""
        invoice = {k: v for k, v in FULL_SAP_INVOICE.items() if k != "InvoiceGrossAmount"}
        result = map_sap_invoice_to_transaction(invoice)
        assert result.amount == 0.0

    def test_none_amount_defaults_to_zero(self):
        """InvoiceGrossAmount=None → amount == 0.0."""
        invoice = dict(FULL_SAP_INVOICE, InvoiceGrossAmount=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.amount == 0.0


# ---------------------------------------------------------------------------
# 4. Missing / None required-ish string fields (external_id and supplier)
# ---------------------------------------------------------------------------

class TestRequiredStringFieldFallbacks:
    """Verify external_id and supplier degrade gracefully when absent."""

    def test_missing_supplier_invoice_yields_empty_external_id(self):
        """SupplierInvoice absent → external_id == ''."""
        invoice = {k: v for k, v in FULL_SAP_INVOICE.items() if k != "SupplierInvoice"}
        result = map_sap_invoice_to_transaction(invoice)
        assert result.external_id == ""

    def test_none_supplier_invoice_yields_empty_external_id(self):
        """SupplierInvoice=None → external_id == ''."""
        invoice = dict(FULL_SAP_INVOICE, SupplierInvoice=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.external_id == ""

    def test_missing_supplier_yields_empty_supplier(self):
        """Supplier absent → supplier == ''."""
        invoice = {k: v for k, v in FULL_SAP_INVOICE.items() if k != "Supplier"}
        result = map_sap_invoice_to_transaction(invoice)
        assert result.supplier == ""

    def test_none_supplier_yields_empty_supplier(self):
        """Supplier=None → supplier == ''."""
        invoice = dict(FULL_SAP_INVOICE, Supplier=None)
        result = map_sap_invoice_to_transaction(invoice)
        assert result.supplier == ""

    def test_empty_dict_does_not_raise(self):
        """Completely empty input dict must not raise; all defaults applied."""
        result = map_sap_invoice_to_transaction({})
        assert isinstance(result, TransactionRecord)
        assert result.external_id == ""
        assert result.supplier == ""
        assert result.amount == 0.0
        assert result.currency == "INR"
        assert result.invoice_number is None
        assert result.po_number is None
        assert result.description == ""
