"""POST /v1/connectors/* — MCP-style read/write surface for SAP, Microsoft Graph
(Outlook/Excel/SharePoint), and local databases (Plan.md: "the platform can connect
with SAP, Outlook, Excel, SharePoint and local databases").

Read (`fetch`) endpoints execute immediately — they're non-destructive. Any write
or external action goes through /v1/approvals first (Plan.md: "high-risk actions
always require human approval") and is only carried out after a reviewer with an
approver role signs off.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.session import get_db
from app.connectors.base import ConnectorNotConfigured
from app.connectors.microsoft_graph import MicrosoftGraphConnector
from app.connectors.sap_odata import SAPODataConnector
from app.connectors.local_db import LocalDatabaseConnector
from app.connectors.composio_client import ComposioConnector, FINTRIAGE_TOOLKITS
from app.ml.document_anomalies import Transaction, PurchaseOrder, scan_all
from datetime import datetime

router = APIRouter()


@router.get("/connectors/composio/toolkits")
async def composio_toolkits(user=Depends(current_user)):
    """Which toolkits this platform requests, and whether Composio itself is
    configured. Real per-user connection status comes from /connectors/composio/connect."""
    connector = ComposioConnector()
    return {"configured": connector.is_configured(), "toolkits": FINTRIAGE_TOOLKITS}


@router.post("/connectors/composio/connect/{toolkit}")
async def composio_connect(toolkit: str, user=Depends(current_user)):
    """Start the Composio-managed OAuth flow for one toolkit (e.g. OUTLOOK, SLACK).
    Returns a redirect_url the frontend opens in a popup; Composio handles the
    callback and stores the resulting token server-side."""
    connector = ComposioConnector()
    if not connector.is_configured():
        raise HTTPException(status_code=503, detail="Set COMPOSIO_API_KEY to enable Composio connectors.")
    try:
        return connector.start_connection(user_id=user["id"], toolkit=toolkit.upper())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Composio connection failed: {e}")


@router.get("/connectors/status")
async def connector_status(db: AsyncSession = Depends(get_db), user=Depends(current_user)):
    """Which connectors are configured and reachable — powers a settings/status page."""
    graph = MicrosoftGraphConnector()
    sap = SAPODataConnector()
    local = LocalDatabaseConnector(db=db)
    composio = ComposioConnector()

    results = {}
    for connector in (graph, sap, local, composio):
        if not connector.is_configured():
            results[connector.name] = {"configured": False}
            continue
        try:
            results[connector.name] = {"configured": True, **(await connector.test_connection())}
        except Exception as e:
            results[connector.name] = {"configured": True, "connected": False, "reason": str(e)}
    return results


@router.get("/connectors/outlook/invoices")
async def scan_outlook_invoices(query: str = "invoice", top: int = 25, user=Depends(current_user)):
    graph = MicrosoftGraphConnector()
    if not graph.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft Graph not configured. Set MS_GRAPH_TENANT_ID / MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET / MS_GRAPH_MAILBOX_UPN.")
    try:
        return {"emails": await graph.scan_invoice_emails(query, top)}
    except ConnectorNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/connectors/excel/read")
async def read_excel(drive_item_path: str, worksheet: str = "Sheet1", user=Depends(current_user)):
    graph = MicrosoftGraphConnector()
    if not graph.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft Graph not configured.")
    try:
        return {"rows": await graph.read_excel_range(drive_item_path, worksheet)}
    except ConnectorNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/connectors/sharepoint/files")
async def list_sharepoint(site_id: str, folder_path: str = "", user=Depends(current_user)):
    graph = MicrosoftGraphConnector()
    if not graph.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft Graph not configured.")
    try:
        return {"files": await graph.list_sharepoint_files(site_id, folder_path)}
    except ConnectorNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/connectors/sap/supplier-invoices")
async def sap_supplier_invoices(top: int = 50, filter_expr: Optional[str] = None, user=Depends(current_user)):
    sap = SAPODataConnector()
    if not sap.is_configured():
        raise HTTPException(status_code=503, detail="SAP not configured. Set SAP_ODATA_BASE_URL / SAP_USERNAME / SAP_PASSWORD.")
    try:
        return {"invoices": await sap.fetch_supplier_invoices(top, filter_expr)}
    except ConnectorNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SAP request failed: {e}")


# ── Document/transaction anomaly scan (duplicate payments, invoice-PO mismatch,
#    missing onboarding docs, unusual transactions) — ties connector data or
#    manually-entered records into app/ml/document_anomalies.py ─────────────────

class TxnIn(BaseModel):
    id: str
    supplier: str
    amount: float
    date: str  # ISO date
    invoice_number: Optional[str] = None
    po_number: Optional[str] = None
    description: str = ""


class POIn(BaseModel):
    po_number: str
    supplier: str
    amount: float


class ScanDocumentsRequest(BaseModel):
    transactions: List[TxnIn]
    purchase_orders: List[POIn] = []
    provided_docs: List[str] = []
    sector: Optional[str] = None


@router.post("/compliance/scan-documents")
async def scan_documents(req: ScanDocumentsRequest, user=Depends(current_user)):
    """Runs duplicate-payment, invoice/PO-mismatch, missing-document, and unusual-
    transaction detection over a batch of records (manually entered, or pulled from
    a connector via /connectors/* first)."""
    txns = [Transaction(id=t.id, supplier=t.supplier, amount=t.amount, date=datetime.fromisoformat(t.date), invoice_number=t.invoice_number, po_number=t.po_number, description=t.description) for t in req.transactions]
    pos = [PurchaseOrder(po_number=p.po_number, supplier=p.supplier, amount=p.amount) for p in req.purchase_orders]
    result = scan_all(txns, pos, req.provided_docs, req.sector)
    return result


@router.post("/connectors/sap/import-and-scan")
async def sap_import_and_scan(
    top: int = 50,
    filter_expr: Optional[str] = None,
    user=Depends(current_user),
):
    """Fetch supplier invoices from SAP OData, map to TransactionRecord, run the
    anomaly scan pipeline, and return findings.

    Requirements: tasks.md section 4.3 / requirement 8.10
    """
    sap = SAPODataConnector()
    if not sap.is_configured():
        raise HTTPException(
            status_code=503,
            detail="SAP not configured. Set SAP_ODATA_BASE_URL / SAP_USERNAME / SAP_PASSWORD.",
        )

    try:
        raw_invoices = await sap.fetch_supplier_invoices(top, filter_expr)
    except ConnectorNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SAP request failed: {e}")

    from app.connectors.sap_mapper import map_sap_invoice_to_transaction

    transactions = []
    for i, inv in enumerate(raw_invoices):
        try:
            rec = map_sap_invoice_to_transaction(inv)
            txn_date = rec.transaction_date
            if isinstance(txn_date, str):
                txn_date = datetime.fromisoformat(txn_date)
            transactions.append(
                Transaction(
                    id=rec.external_id or str(i),
                    supplier=rec.supplier,
                    amount=float(rec.amount),
                    date=txn_date,
                    invoice_number=rec.invoice_number,
                    po_number=rec.po_number,
                    description=rec.description or "",
                )
            )
        except Exception:
            continue

    scan_result = scan_all(transactions, [], [], None)

    return {
        "source": "sap",
        "transactions_fetched": len(raw_invoices),
        "transactions_mapped": len(transactions),
        **scan_result,
    }
