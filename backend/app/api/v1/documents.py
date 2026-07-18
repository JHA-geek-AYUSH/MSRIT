from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.security import current_user
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import crud
from app.storage.supabase_client import upload_bytes

router = APIRouter()


class DocumentCreateResponse(BaseModel):
    id: UUID
    ocr_status: str


@router.post("/matters/{matter_id}/documents", response_model=DocumentCreateResponse)
async def upload_document(
    matter_id: UUID,
    file: UploadFile = File(...),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # Resolve Clerk ID → DB UUID (auto-create user on first login)
    db_user_id = await crud.resolve_db_user_id(db, user["id"], user.get("email", ""))

    # Upload to Supabase Storage
    data = await file.read()
    storage_path = f"matters/{matter_id}/{uuid4()}-{file.filename}"
    ok, err = upload_bytes(
        bucket="matters",
        path=storage_path,
        data=data,
        content_type=file.content_type or "application/octet-stream",
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {err}",
        )

    doc = await crud.create_document(
        db,
        matter_id=matter_id,
        storage_path=storage_path,
        filetype=file.content_type or "application/octet-stream",
        size=len(data),
        uploaded_by=db_user_id,  # real UUID, not Clerk string
    )

    # Enqueue ingestion only if Celery is configured
    try:
        from app.core.tasks import get_celery
        get_celery().send_task(
            "app.ingestion.pipeline.ingest_document", args=[str(doc.id)]
        )
    except Exception:
        pass  # Celery not running in dev — ingestion is optional

    return DocumentCreateResponse(id=doc.id, ocr_status=doc.ocr_status)


@router.get("/matters/{matter_id}/documents")
async def get_documents(
    matter_id: UUID,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    docs = await crud.get_documents_by_matter(db, matter_id)
    return {
        "data": [
            {
                "id": str(d.id),
                "filetype": d.filetype,
                "size": d.size,
                "status": d.ocr_status,
                "created_at": d.created_at.isoformat(),
                "storage_path": d.storage_path,
                "name": d.storage_path.split("/")[-1],
            }
            for d in docs
        ]
    }
