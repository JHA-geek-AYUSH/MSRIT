from __future__ import annotations

from typing import Literal, Dict, Any
from uuid import UUID
import tempfile
import os
from pathlib import Path
import structlog

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.security import current_user
from app.db.session import get_db
from app.billing.credits import calculate_and_debit_export_cost
from app.export.to_docx import export_docx
from app.export.to_pdf import export_pdf
from app.export.audit_bundle import write_audit_json
from app.storage.supabase_client import upload_file, get_signed_url

log = structlog.get_logger()
router = APIRouter()


class ExportRequest(BaseModel):
    format: Literal["docx", "pdf", "json"]


class ExportResponse(BaseModel):
    url: str
    format: str
    file_size: int
    cost_credits: int
    expires_at: str


@router.post("/runs/{run_id}/export", response_model=ExportResponse)
async def export_run(
    run_id: UUID,
    req: ExportRequest,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    from app.db import crud as _crud
    clerk_id = user["id"]
    db_user_id = str(await _crud.resolve_db_user_id(db, clerk_id, user.get("email", "")))

    log.info("export.start", run_id=str(run_id), format=req.format, user_id=clerk_id)

    try:
        # Fetch run data — enforces ownership via db_user_id (UUID)
        run_data = await _fetch_run_data(db, run_id, db_user_id)
        if not run_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found or access denied")

        billing_result = await calculate_and_debit_export_cost(
            db, db_user_id, str(run_id), req.format, run_data
        )
        if not billing_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient credits. Required: {billing_result['total_cost']}, Available: {billing_result.get('current_balance', 0)}"
            )

        export_file_path = await _generate_export_file(run_data, req.format, run_id)
        storage_path = f"exports/{db_user_id}/{run_id}.{req.format}"

        upload_success, upload_error = upload_file(
            bucket="exports", path=storage_path,
            file_path=export_file_path, content_type=_get_content_type(req.format)
        )
        if not upload_success:
            raise HTTPException(status_code=500, detail=f"Storage upload failed: {upload_error}")

        signed_url = get_signed_url(bucket="exports", path=storage_path, expires_in=24 * 3600)
        file_size = os.path.getsize(export_file_path)
        os.unlink(export_file_path)

        log.info("export.complete", run_id=str(run_id), format=req.format, file_size=file_size)
        return ExportResponse(
            url=signed_url, format=req.format, file_size=file_size,
            cost_credits=billing_result["total_cost"], expires_at="24 hours"
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("export.error", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=500, detail="Export generation failed")


async def _fetch_run_data(db: AsyncSession, run_id: UUID, user_id: str) -> Dict[str, Any]:
    """Fetch complete run data — user_id (DB UUID str) enforces ownership."""
    run_query = """
        SELECT r.id, r.answer_text, r.confidence, r.retrieval_set_json, r.created_at,
               q.id, q.message, q.mode, q.filters_json,
               m.id, m.title, m.language,
               p.merkle_root, p.tx_hash, p.network, p.block_number
        FROM runs r
        JOIN queries q ON r.query_id = q.id
        JOIN matters m ON q.matter_id = m.id
        LEFT JOIN onchain_proofs p ON p.run_id = r.id
        WHERE r.id = :run_id
          AND m.user_id = :uid
    """
    result = await db.execute(text(run_query), {"run_id": str(run_id), "uid": user_id})
    run_row = result.fetchone()
    if not run_row:
        return None

    votes_result = await db.execute(
        text("SELECT agent, decision_json, confidence, aligned, weights_before, weights_after FROM agent_votes WHERE run_id = :rid ORDER BY agent"),
        {"rid": str(run_id)},
    )
    agent_votes = votes_result.fetchall()

    return {
        "run_id": str(run_row[0]),
        "answer": run_row[1],
        "confidence": float(run_row[2]) if run_row[2] else 0.0,
        "retrieval_set": run_row[3] or [],
        "created_at": run_row[4].isoformat() if run_row[4] else None,
        "query": {"id": str(run_row[5]), "message": run_row[6], "mode": run_row[7], "filters": run_row[8] or {}},
        "matter": {"id": str(run_row[9]), "title": run_row[10], "language": run_row[11]},
        "notarization": {"merkle_root": run_row[12], "tx_hash": run_row[13], "network": run_row[14], "block_number": run_row[15]} if run_row[12] else None,
        "agent_results": {
            v[0]: {"reasoning": v[1].get("reasoning", "") if v[1] else "", "confidence": float(v[2] or 0), "aligned": v[3]}
            for v in agent_votes
        },
        "citations": _extract_citations_from_retrieval(run_row[3] or []),
        "verification": {"confidence": float(run_row[2]) if run_row[2] else 0.0, "verification_level": _determine_verification_level(float(run_row[2]) if run_row[2] else 0.0)},
    }


def _extract_citations_from_retrieval(retrieval_set: list) -> list:
    """Extract citation information from retrieval set"""
    citations = []
    seen_authorities = set()
    
    for pack in retrieval_set:
        authority_id = pack.get("authority_id")
        if authority_id and authority_id not in seen_authorities:
            citations.append({
                "authority_id": authority_id,
                "title": pack.get("title", "Unknown Case"),
                "court": pack.get("court", "Unknown Court"),
                "neutral_cite": pack.get("neutral_cite", ""),
                "reporter_cite": pack.get("reporter_cite", ""),
                "para_ids": [p.get("para_id", 0) for p in pack.get("paras", [])]
            })
            seen_authorities.add(authority_id)
    
    return citations


def _determine_verification_level(confidence: float) -> str:
    """Determine verification level based on confidence score"""
    if confidence >= 0.8:
        return "high"
    elif confidence >= 0.6:
        return "medium"
    elif confidence >= 0.4:
        return "low"
    else:
        return "very_low"


async def _generate_export_file(run_data: Dict[str, Any], format: str, run_id: UUID) -> str:
    """Generate export file in requested format"""
    
    if format == "docx":
        return export_docx(str(run_id), run_data)
    elif format == "pdf":
        return export_pdf(str(run_id), run_data)
    elif format == "json":
        return write_audit_json(str(run_id), run_data)
    else:
        raise ValueError(f"Unsupported export format: {format}")


def _get_content_type(format: str) -> str:
    """Get MIME content type for export format"""
    content_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "json": "application/json"
    }
    return content_types.get(format, "application/octet-stream")


@router.get("/runs/{run_id}/export-cost")
async def get_export_cost(
    run_id: UUID,
    format: Literal["docx", "pdf", "json"],
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get cost estimate for exporting a run without actually performing export
    """
    from app.billing.cost_calculator import CostCalculator
    
    try:
        # Fetch basic run data for cost calculation
        run_query = """
            SELECT r.retrieval_set_json, r.answer_text
            FROM runs r
            JOIN queries q ON r.query_id = q.id
            JOIN matters m ON q.matter_id = m.id
            WHERE r.id = :run_id
        """
        
        result = await db.execute(text(run_query), {"run_id": str(run_id)})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Run not found"
            )
        
        retrieval_set, answer_text = row
        run_data = {
            "retrieval_set": retrieval_set or [],
            "answer": answer_text or ""
        }
        
        calculator = CostCalculator()
        cost_breakdown = calculator.calculate_export_cost(format, run_data)
        
        return {
            "format": format,
            "estimated_cost_credits": cost_breakdown["total_credits"],
            "cost_breakdown": cost_breakdown,
            "user_balance": await _get_user_balance(db, user["id"])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error("export.cost_estimate_error", 
                 run_id=str(run_id), 
                 format=format, 
                 error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate export cost"
        )


async def _get_user_balance(db: AsyncSession, user_id: str) -> int:
    """Get user's current credit balance"""
    result = await db.execute(
        text("SELECT credits_balance FROM billing_accounts WHERE user_id = :user_id"),
        {"user_id": user_id}
    )
    row = result.fetchone()
    return row[0] if row else 0


