"""Microsoft Graph connector — real OAuth2 client-credentials integration backing
Outlook (invoice/vendor email scanning), Excel (workbook reads), and SharePoint
(document library reads). One connector class because all three ride the same
Graph API + app registration.

Setup required (documented here since there's no working default — this needs
the user's own Azure AD tenant):
  1. Register an app in Azure AD (portal.azure.com -> App registrations).
  2. Grant Application permissions (admin consent required): Mail.Read,
     Files.Read.All, Sites.Read.All.
  3. Set env vars: MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET.
  4. For Outlook, also set MS_GRAPH_MAILBOX_UPN (the shared/finance mailbox to scan,
     e.g. ap-invoices@yourcompany.com) since application-permission mail reads
     target a specific mailbox, not "the current user".

Without those env vars, is_configured() returns False and callers get a clear
ConnectorNotConfigured instead of a confusing network/auth error.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

from app.connectors.base import BaseConnector, ConnectorNotConfigured

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class MicrosoftGraphConnector(BaseConnector):
    name = "microsoft_graph"

    def __init__(self) -> None:
        self.tenant_id = os.getenv("MS_GRAPH_TENANT_ID")
        self.client_id = os.getenv("MS_GRAPH_CLIENT_ID")
        self.client_secret = os.getenv("MS_GRAPH_CLIENT_SECRET")
        self.mailbox_upn = os.getenv("MS_GRAPH_MAILBOX_UPN")
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret)

    async def _get_token(self) -> str:
        if not self.is_configured():
            raise ConnectorNotConfigured(
                "Microsoft Graph not configured — set MS_GRAPH_TENANT_ID, "
                "MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET."
            )
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            body = resp.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + body.get("expires_in", 3600)
        return self._token

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def test_connection(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"connected": False, "reason": "not_configured"}
        try:
            await self._get_token()
            return {"connected": True}
        except httpx.HTTPStatusError as e:
            return {"connected": False, "reason": f"auth_failed: {e.response.status_code}"}

    # ── Outlook ───────────────────────────────────────────────────────────

    async def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Generic dispatch so this one connector covers Outlook/Excel/SharePoint."""
        source = kwargs.get("source", "outlook")
        if source == "outlook":
            return await self.scan_invoice_emails(kwargs.get("query", "invoice"), kwargs.get("top", 25))
        if source == "excel":
            return await self.read_excel_range(kwargs["drive_item_path"], kwargs.get("worksheet", "Sheet1"))
        if source == "sharepoint":
            return await self.list_sharepoint_files(kwargs["site_id"], kwargs.get("folder_path", ""))
        raise ValueError(f"Unknown source: {source}")

    async def scan_invoice_emails(self, query: str = "invoice", top: int = 25) -> List[Dict[str, Any]]:
        """Scan the configured finance mailbox for invoice/vendor emails — the
        Outlook-side complement to the invoice-mismatch/duplicate-payment detectors
        in app/ml/document_anomalies.py (feeds transaction extraction from attachments)."""
        if not self.mailbox_upn:
            raise ConnectorNotConfigured("Set MS_GRAPH_MAILBOX_UPN to the finance mailbox to scan.")
        data = await self._get(
            f"/users/{self.mailbox_upn}/messages",
            params={"$search": f'"{query}"', "$top": top, "$select": "id,subject,from,receivedDateTime,hasAttachments"},
        )
        return [
            {
                "id": m["id"], "subject": m.get("subject"),
                "from": m.get("from", {}).get("emailAddress", {}).get("address"),
                "received": m.get("receivedDateTime"), "has_attachments": m.get("hasAttachments", False),
            }
            for m in data.get("value", [])
        ]

    async def get_email_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        if not self.mailbox_upn:
            raise ConnectorNotConfigured("Set MS_GRAPH_MAILBOX_UPN to the finance mailbox to scan.")
        data = await self._get(f"/users/{self.mailbox_upn}/messages/{message_id}/attachments")
        return data.get("value", [])

    # ── Excel ─────────────────────────────────────────────────────────────

    async def read_excel_range(self, drive_item_path: str, worksheet: str = "Sheet1") -> List[Dict[str, Any]]:
        """Read a worksheet's used range from an Excel file in the finance mailbox's
        OneDrive/SharePoint (e.g. a shared 'Vendor Payments.xlsx' tracker)."""
        if not self.mailbox_upn:
            raise ConnectorNotConfigured("Set MS_GRAPH_MAILBOX_UPN (or extend to target a specific drive).")
        data = await self._get(
            f"/users/{self.mailbox_upn}/drive/root:/{drive_item_path}:/workbook/worksheets/{worksheet}/usedRange"
        )
        values = data.get("values", [])
        if not values:
            return []
        headers = values[0]
        return [dict(zip(headers, row)) for row in values[1:]]

    # ── SharePoint ────────────────────────────────────────────────────────

    async def list_sharepoint_files(self, site_id: str, folder_path: str = "") -> List[Dict[str, Any]]:
        path = f"/sites/{site_id}/drive/root/children" if not folder_path else f"/sites/{site_id}/drive/root:/{folder_path}:/children"
        data = await self._get(path)
        return [
            {"id": f["id"], "name": f["name"], "web_url": f.get("webUrl"), "last_modified": f.get("lastModifiedDateTime"), "size": f.get("size")}
            for f in data.get("value", [])
        ]
