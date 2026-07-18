"""Local database connector — reads the platform's own Postgres (entities,
compliance_assessments, etc.) plus, optionally, a second read-only connection
string for a customer's own local finance DB. This is the "process sensitive
data locally" path from Plan.md: no data leaves the machine/network for this
connector — it's a direct DB query executed in-process.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.connectors.base import BaseConnector, ConnectorNotConfigured


class LocalDatabaseConnector(BaseConnector):
    name = "local_db"

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db
        self.external_dsn = os.getenv("LOCAL_FINANCE_DB_URL")  # optional second DB

    def is_configured(self) -> bool:
        return self.db is not None or bool(self.external_dsn)

    async def test_connection(self) -> Dict[str, Any]:
        if self.db is not None:
            try:
                await self.db.execute(text("SELECT 1"))
                return {"connected": True, "target": "platform_db"}
            except Exception as e:
                return {"connected": False, "reason": str(e)}
        if self.external_dsn:
            try:
                engine = create_async_engine(self.external_dsn, pool_pre_ping=True)
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                await engine.dispose()
                return {"connected": True, "target": "external_finance_db"}
            except Exception as e:
                return {"connected": False, "reason": str(e)}
        return {"connected": False, "reason": "not_configured"}

    async def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Read-only parameterized query against the platform DB or the optional
        external finance DB. `query` must be a SELECT — enforced below since this
        connector has no business ever writing to a customer's finance database."""
        query: str = kwargs.get("query", "")
        params: Dict[str, Any] = kwargs.get("params", {})
        if not query.strip().lower().startswith("select"):
            raise ValueError("LocalDatabaseConnector.fetch only allows SELECT queries.")

        if self.db is not None:
            result = await self.db.execute(text(query), params)
            return [dict(row._mapping) for row in result]

        if not self.external_dsn:
            raise ConnectorNotConfigured("No DB session or LOCAL_FINANCE_DB_URL configured.")
        engine = create_async_engine(self.external_dsn, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(query), params)
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()
