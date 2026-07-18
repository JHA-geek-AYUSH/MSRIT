from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db import crud

router = APIRouter()

@router.get("/test/users")
async def test_users(db: AsyncSession = Depends(get_db)):
    """Test endpoint - list all users (no auth required)"""
    from sqlalchemy import select
    from app.db.models import User
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    return {
        "count": len(users),
        "users": [{"id": str(u.id), "clerk_id": u.clerk_id, "email": u.email} for u in users]
    }

@router.get("/test/db")
async def test_db(db: AsyncSession = Depends(get_db)):
    """Test database connection"""
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1 as test"))
    return {"status": "ok", "result": result.scalar()}
