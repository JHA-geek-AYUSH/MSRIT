from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.security import current_user
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import crud

router = APIRouter()


class MatterCreate(BaseModel):
    title: str
    language: str = "en"


class MatterOut(BaseModel):
    id: UUID
    title: str
    language: str
    created_at: str


async def _resolve_db_user_id(user: dict, db: AsyncSession) -> UUID:
    """Resolve Clerk clerk_id → internal DB UUID, auto-creating user if needed."""
    clerk_id: str = user["id"]
    db_user = await crud.get_user_by_clerk_id(db, clerk_id)
    if not db_user:
        db_user = await crud.create_user(
            db,
            clerk_id=clerk_id,
            email=user.get("email", ""),
            role="lawyer",
        )
        await crud.get_or_create_billing_account(db, db_user.id)
    return db_user.id


@router.post("/matters", response_model=MatterOut)
async def create_matter(
    req: MatterCreate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _resolve_db_user_id(user, db)
    m = await crud.create_matter(db, user_id=user_id, title=req.title, language=req.language)
    return MatterOut(id=m.id, title=m.title, language=m.language, created_at=m.created_at.isoformat())


@router.get("/matters/{matter_id}", response_model=MatterOut)
async def get_matter(
    matter_id: UUID,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await crud.get_matter(db, matter_id)
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return MatterOut(id=m.id, title=m.title, language=m.language, created_at=m.created_at.isoformat())


@router.get("/matters")
async def get_matters(
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = await _resolve_db_user_id(user, db)
    matters = await crud.get_matters_by_user(db, user_id)
    return {
        "data": [
            {
                "id": str(m.id),
                "title": m.title,
                "language": m.language,
                "created_at": m.created_at.isoformat(),
                "status": "active",
                "documents_count": 0,
            }
            for m in matters
        ]
    }
