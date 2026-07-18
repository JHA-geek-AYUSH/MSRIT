"""Composio integration - the primary path for SAP/Outlook/Excel/SharePoint/etc.
connectors (Plan.md), replacing hand-rolled OAuth per-service where a Composio
toolkit exists. Composio handles the OAuth dance, token storage/refresh, and
exposes tools in an LLM-tool-calling schema that plugs directly into the Gemma
chat-completions loop.

Setup:
  export COMPOSIO_API_KEY=...    (composio.dev dashboard - one key, no per-toolkit configs)
  pip install -U composio

This targets the current Composio v3 SDK (mid-2026). The old `ComposioToolSet` /
`composio-openai` / `entity.initiate_connection()` pattern this file used to use
is deprecated -- see https://docs.composio.dev/docs/migration-guide/new-sdk.
Key v3 changes that matter here:
  - `from composio import Composio` (one client, no framework-specific toolset
    class; tools come back in OpenAI tool-calling format by default)
  - `entity_id` was renamed to `user_id` everywhere
  - Connecting an account now needs an `auth_config_id`, not just a toolkit name
    -- `_get_or_create_auth_config()` below fetches or creates one on the fly

Toolkit coverage reality-check: Composio 1000+ toolkit catalogue covers Outlook,
Microsoft Teams, OneDrive/SharePoint, Google Sheets/Excel-equivalent, Gmail, Slack,
Notion, Salesforce, HubSpot, etc. SAP stays on the hand-rolled OData connector in
app/connectors/sap_odata.py.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.connectors.base import BaseConnector, ConnectorNotConfigured
from app.core.config import get_settings

log = structlog.get_logger()

# Toolkits this platform asks the user to connect for FinTriage workflows.
FINTRIAGE_TOOLKITS = ["OUTLOOK", "ONEDRIVE", "GOOGLESHEETS", "SLACK"]

# Heuristic for "this Composio tool call is a write/high-risk action"
_WRITE_VERBS = ("SEND", "CREATE", "UPDATE", "DELETE", "WRITE", "POST", "REMOVE", "ARCHIVE", "MOVE")


def _is_write_action(tool_slug: str) -> bool:
    return any(v in tool_slug.upper() for v in _WRITE_VERBS)


class ComposioConnector(BaseConnector):
    name = "composio"

    def __init__(self) -> None:
        self.api_key = get_settings().COMPOSIO_API_KEY
        self._toolset = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        """Return a cached Composio v3 client instance (deferred import)."""
        if not self.is_configured():
            raise ConnectorNotConfigured(
                "Set COMPOSIO_API_KEY (from the Composio dashboard) to enable Composio connectors."
            )
        if self._toolset is None:
            try:
                # Composio creates this directory during module import.  The
                # default lives under the user's profile, which may be
                # read-only in managed/CI environments; keep it in the
                # project instead.
                cache_dir = Path(__file__).resolve().parents[2] / ".composio-cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                os.environ.setdefault("COMPOSIO_CACHE_DIR", str(cache_dir))
                from composio import Composio
            except ImportError as exc:
                raise ConnectorNotConfigured(
                    "Composio package not installed or out of date. Run: pip install -U composio"
                ) from exc
            self._toolset = Composio(api_key=self.api_key)
        return self._toolset

    def _get_or_create_auth_config(self, toolkit: str) -> str:
        """v3 requires an auth_config_id (not just a toolkit name) to start a
        connection. Reuse an existing Composio-managed auth config for this
        toolkit if one exists on the account; otherwise create one."""
        client = self._get_client()
        try:
            existing = client.auth_configs.list(toolkit=toolkit)
            items = getattr(existing, "items", existing) or []
            if items:
                return items[0].id
        except Exception as e:
            log.warning("composio.auth_configs_list_failed", toolkit=toolkit, error=str(e))
        auth_config = client.auth_configs.create(
            toolkit=toolkit,
            options={"type": "use_composio_managed_auth"},
        )
        return auth_config.id

    async def test_connection(self) -> Dict[str, Any]:
        """Verify the API key is accepted. tools.get() is a lightweight, always-
        available v3 call (doesn't require any connected account), so a 401/403
        here reliably means a bad/missing COMPOSIO_API_KEY rather than "no
        connections yet"."""
        if not self.is_configured():
            return {"connected": False, "reason": "not_configured"}
        try:
            client = self._get_client()
            tools = client.tools.get(user_id="default", toolkits=[FINTRIAGE_TOOLKITS[0]], limit=1)
            return {"connected": True, "sample_tools_returned": len(tools) if tools else 0}
        except ImportError:
            return {
                "connected": False,
                "reason": "composio package not installed or out of date - pip install -U composio",
            }
        except Exception as e:
            return {"connected": False, "reason": str(e)}

    async def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Generic read: execute a named Composio action and return result as a list."""
        tool_slug = kwargs["tool_slug"]
        user_id = kwargs.get("user_id", "default")
        arguments = kwargs.get("arguments", {})
        result = await self.execute_tool(tool_slug, user_id, arguments)
        data = result.get("data", result)
        return data if isinstance(data, list) else [data]

    def get_openai_tools(self, user_id: str, toolkits: Optional[List[str]] = None):
        """Return OpenAI-function-calling-schema tool definitions for the requested
        toolkits, ready to pass straight into client.chat.completions.create(tools=...)
        against the Gemma (Ollama/Google AI Studio) client. v3's tools.get() returns
        OpenAI-formatted tools by default -- no separate provider object needed.
        """
        client = self._get_client()
        try:
            return client.tools.get(user_id=user_id, toolkits=toolkits or FINTRIAGE_TOOLKITS)
        except Exception as e:
            log.warning("composio.get_tools_failed", error=str(e))
            return []

    async def execute_tool(
        self, tool_slug: str, user_id: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Direct tool execution (no LLM in the loop)."""
        client = self._get_client()
        try:
            result = client.tools.execute(tool_slug, user_id=user_id, arguments=arguments)
            return result if isinstance(result, dict) else {"data": result}
        except Exception as e:
            log.error("composio.execute_tool_failed", tool_slug=tool_slug, error=str(e))
            return {"error": str(e), "tool_slug": tool_slug}

    def start_connection(
        self, user_id: str, toolkit: str, callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Begin the OAuth flow for a toolkit on behalf of a specific platform user.

        v3 requires an auth_config_id, not just a toolkit name -- see
        _get_or_create_auth_config(). Composio manages OAuth credentials
        server-side; the user just needs to visit the returned redirect_url to
        complete the flow.

        NOTE: for Composio-managed auth configs (the default -- no custom OAuth
        app credentials), Composio retired `connected_accounts.initiate()` as of
        2026-07-03 in favor of `connected_accounts.link()` (same shape, same
        redirect_url field). `initiate()` is kept for custom auth configs / non-
        OAuth schemes (API key, bearer token), which this platform doesn't use,
        so we call `.link()` unconditionally here.

        Args:
            user_id: Your platform user ID (Composio uses this to scope connections).
            toolkit: Toolkit slug, e.g. "OUTLOOK", "SLACK", "GMAIL", "GITHUB".
            callback_url: Optional URL Composio redirects to after OAuth completes.

        Returns:
            Dict with "redirect_url" and "connection_id".
        """
        client = self._get_client()
        try:
            auth_config_id = self._get_or_create_auth_config(toolkit)
            kwargs: Dict[str, Any] = {}
            if callback_url:
                kwargs["callback_url"] = callback_url
            connection_request = client.connected_accounts.link(
                user_id=user_id,
                auth_config_id=auth_config_id,
                **kwargs,
            )
            return {
                "redirect_url": getattr(connection_request, "redirect_url", None),
                "connection_id": getattr(connection_request, "id", None),
            }
        except Exception as e:
            log.error("composio.start_connection_failed", toolkit=toolkit, error=str(e))
            raise


async def execute_composio_tool_gated(
    tool_slug: str,
    user_id: str,
    arguments: Dict[str, Any],
    db,
    assessment_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """The one path anything in this codebase should use to call a Composio tool.
    Read-only tools execute immediately; write-shaped tools are staged as a pending
    ApprovalRequest instead of executing, honoring Plan.md high-risk action gate.
    """
    connector = ComposioConnector()
    if _is_write_action(tool_slug):
        from app.db.models import ApprovalRequest

        approval = ApprovalRequest(
            requested_by_user_id=None,
            action_type="composio_tool_call",
            connector="composio",
            risk_level="high",
            payload={"tool_slug": tool_slug, "user_id": user_id, "arguments": arguments},
            reason=reason or f"Agent requested write action {tool_slug}",
            status="pending",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return {"status": "pending_approval", "approval_id": str(approval.id), "tool_slug": tool_slug}

    return await connector.execute_tool(tool_slug, user_id, arguments)
