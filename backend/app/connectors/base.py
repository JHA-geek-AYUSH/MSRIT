"""Base interface for all external system connectors (Plan.md: "connect with SAP,
Outlook, Excel, SharePoint and local databases").

Each connector exposes a small, uniform surface:
  - test_connection()      -> health check
  - fetch(...)              -> read-only data pull
  - propose_action(...)     -> stage a write/high-risk action for human approval
                                (never executes directly — see app/api/v1/approvals.py)

Sensitive documents are processed locally wherever possible: connectors return raw
content to the FastAPI backend's own process (which already runs Gemma via Ollama
locally per app/core/gemma_client.py) rather than shipping documents to a third-party
SaaS AI endpoint. Nothing in this layer auto-executes a write against a connected
system — every mutating action must go through the approval queue first.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ConnectorError(Exception):
    pass


class ConnectorNotConfigured(ConnectorError):
    """Raised when required credentials/env vars for a connector are missing.
    Callers should surface this as a clear "connect this integration" prompt,
    not a 500 error."""


class BaseConnector(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        ...

    async def propose_action(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Default: every connector write is high-risk by default and must be
        approved via app/api/v1/approvals.py before app/connectors executes it."""
        return {
            "connector": self.name,
            "action_type": action_type,
            "payload": payload,
            "status": "pending_approval",
        }
