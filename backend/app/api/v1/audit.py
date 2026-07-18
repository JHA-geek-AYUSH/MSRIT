"""GET /v1/audit-trail — append-only audit log viewer (tasks.md §19.1, Requirement 10.8).

Returns AuditTrailEntry rows across all workflow types (invoices, vendor onboarding,
transaction batches, workflow runs) in one paginated feed, since AuditTrailEntry is
a single shared table by design (see models.py).

Note on scoping: AuditTrailEntry.actor is populated inconsistently across callers
(invoices.py stores the user's db_id string, vendors.py stores email-or-clerk-id) —
a real multi-tenant deployment should normalize this to a single actor_user_id
column and filter by it here. For now this endpoint returns the full log
unscoped, which is fine at single-tenant/hackathon scale but should not ship
as-is to a multi-org deployment.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_user
from app.db.models import AuditTrailEntry
from app.db.session import get_db

router = APIRouter()


@router.get("/audit-trail")
async def list_audit_trail(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    invoice_id: Optional[str] = None,
    limit: int = 100,
    user=Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(AuditTrailEntry)

    if entity_type:
        stmt = stmt.where(AuditTrailEntry.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditTrailEntry.entity_id == entity_id)
    if workflow_id:
        stmt = stmt.where(AuditTrailEntry.workflow_id == workflow_id)
    if invoice_id:
        stmt = stmt.where(AuditTrailEntry.invoice_id == invoice_id)

    stmt = stmt.order_by(desc(AuditTrailEntry.timestamp)).limit(limit)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return {
        "total": len(entries),
        "entries": [
            {
                "id": str(e.id),
                "action": e.action,
                "actor": e.actor,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "workflow_id": str(e.workflow_id) if e.workflow_id else None,
                "invoice_id": str(e.invoice_id) if e.invoice_id else None,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "metadata": e.metadata_,
            }
            for e in entries
        ],
    }
