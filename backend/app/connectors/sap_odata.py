"""SAP connector — targets SAP's standard OData V2/V4 services (e.g. API_PURCHASEORDER_PROCESS_SRV,
API_SUPPLIERINVOICE_PROCESS_SRV) via SAP Gateway / BTP, which is the realistic integration
path for an SME/mid-market SAP shop (S/4HANA Cloud or on-prem with Gateway) — not raw RFC,
which needs a SAP-side NetWeaver RFC SDK and is out of scope for a REST backend.

HONEST LIMITATION: this cannot be tested or fully validated without a real SAP
tenant + exposed OData service + a technical user's Basic/OAuth credentials. The
HTTP calls below follow SAP's documented OData conventions precisely, but you
will need to point SAP_ODATA_BASE_URL at your own Gateway instance and confirm
the exact entity-set names for your SAP version (they're consistent across most
S/4HANA installs but on-prem ECC systems sometimes expose custom Z-services instead).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from app.connectors.base import BaseConnector, ConnectorNotConfigured


class SAPODataConnector(BaseConnector):
    name = "sap"

    def __init__(self) -> None:
        self.base_url = os.getenv("SAP_ODATA_BASE_URL")  # e.g. https://<host>/sap/opu/odata/sap
        self.username = os.getenv("SAP_USERNAME")
        self.password = os.getenv("SAP_PASSWORD")

    def is_configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    async def test_connection(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"connected": False, "reason": "not_configured"}
        try:
            async with httpx.AsyncClient(timeout=15, auth=(self.username, self.password)) as client:
                resp = await client.get(f"{self.base_url}/API_SUPPLIERINVOICE_PROCESS_SRV/$metadata")
                resp.raise_for_status()
            return {"connected": True}
        except Exception as e:
            return {"connected": False, "reason": str(e)}

    async def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        entity_set = kwargs.get("entity_set", "A_SupplierInvoice")
        top = kwargs.get("top", 50)
        filter_expr = kwargs.get("filter")
        return await self._get_entity_set(
            "API_SUPPLIERINVOICE_PROCESS_SRV", entity_set, top=top, filter_expr=filter_expr
        )

    async def fetch_purchase_orders(self, top: int = 50, filter_expr: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._get_entity_set("API_PURCHASEORDER_PROCESS_SRV", "A_PurchaseOrder", top=top, filter_expr=filter_expr)

    async def fetch_supplier_invoices(self, top: int = 50, filter_expr: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._get_entity_set("API_SUPPLIERINVOICE_PROCESS_SRV", "A_SupplierInvoice", top=top, filter_expr=filter_expr)

    async def _get_entity_set(self, service: str, entity_set: str, top: int = 50, filter_expr: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_configured():
            raise ConnectorNotConfigured(
                "SAP not configured — set SAP_ODATA_BASE_URL, SAP_USERNAME, SAP_PASSWORD, "
                "pointing at your SAP Gateway / S/4HANA Cloud OData endpoint."
            )
        params: Dict[str, Any] = {"$format": "json", "$top": top}
        if filter_expr:
            params["$filter"] = filter_expr
        async with httpx.AsyncClient(timeout=20, auth=(self.username, self.password)) as client:
            resp = await client.get(f"{self.base_url}/{service}/{entity_set}", params=params)
            resp.raise_for_status()
            body = resp.json()
        return body.get("d", {}).get("results", body.get("value", []))
