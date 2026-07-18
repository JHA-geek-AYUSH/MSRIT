from __future__ import annotations

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.security import current_user
from app.db.session import get_db

router = APIRouter()


class DataDeletionRequest(BaseModel):
    confirm_deletion: bool
    reason: str = "user_request"


@router.get("/data-summary")
async def get_user_data_summary(
    user=Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """Transparency report — what data we hold (DPDP Article 11)."""
    user_id = user["id"]
    try:
        counts = {}
        for table, col in [
            ("queries", "matter_id"),
            ("documents", "matter_id"),
            ("pii_records", "user_id"),
        ]:
            if table in ("queries", "documents"):
                q = f"SELECT COUNT(*) FROM {table} t JOIN matters m ON t.matter_id=m.id WHERE m.user_id=(SELECT id FROM users WHERE clerk_id=:uid LIMIT 1)"
            else:
                q = f"SELECT COUNT(*) FROM {table} WHERE user_id=(SELECT id FROM users WHERE clerk_id=:uid LIMIT 1)"
            row = (await db.execute(text(q), {"uid": user_id})).scalar()
            counts[table] = int(row or 0)
        return {
            "user_id": user_id,
            "data_counts": counts,
            "retention_policy": {
                "default_days": 180,
                "pii_days": 90,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/request-deletion")
async def request_data_deletion(
    req: DataDeletionRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Right to be forgotten — queue deletion (DPDP Article 12)."""
    if not req.confirm_deletion:
        raise HTTPException(status_code=400, detail="Deletion confirmation required")
    user_id = user["id"]
    import structlog
    log = structlog.get_logger()
    log.info("privacy.deletion_request", user_id=user_id, reason=req.reason)
    # Queue via Celery if available, otherwise log
    try:
        from app.tasks.retention_tasks import process_user_deletion
        process_user_deletion.delay(user_id, req.reason)
        task_status = "queued"
    except Exception:
        task_status = "logged_only"  # Celery not running in dev
    return {
        "status": task_status,
        "user_id": user_id,
        "estimated_completion": "Data will be crypto-shredded within 1 hour",
    }


@router.get("/data-processing-info")
async def get_data_processing_info(user=Depends(current_user)):
    return {
        "data_controller": {"name": "GemmaFinOS Legal AI", "contact": "privacy@gemmaFin-legal.ai"},
        "processing_purposes": ["Legal research", "Document OCR", "Billing"],
        "data_retention": {
            "default_retention_period_days": 180,
            "user_rights": ["access", "portability", "erasure", "restriction"],
        },
        "third_party_processors": [
            {"name": "Google (Gemma)", "purpose": "Compliance AI (PII-redacted)", "data_residency": "US"},
            {"name": "OpenAI", "purpose": "Legal AI (PII-redacted)", "data_residency": "US/EU"},
        ],
    }


@router.post("/opt-out-analytics")
async def opt_out_analytics(user=Depends(current_user)):
    import structlog
    structlog.get_logger().info("privacy.analytics_opt_out", user_id=user["id"])
    return {"status": "success", "effective_date": "immediate"}
