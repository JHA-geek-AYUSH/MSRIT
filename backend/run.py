#!/usr/bin/env python3
import asyncio
import sys
from app.db.models import Base
from app.db.session import engine, SessionLocal
from app.db.models import User, BillingAccount
from uuid import uuid4
from sqlalchemy import select

async def init_db():
    print("[*] Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] Tables created")
    
    async with SessionLocal() as session:
        from sqlalchemy import select
        existing = await session.execute(select(User).where(User.clerk_id == 'test-user-123'))
        if not existing.scalar():
            user = User(id=uuid4(), clerk_id='test-user-123', email='test@example.com', role='lawyer')
            session.add(user)
            await session.flush()
            billing = BillingAccount(user_id=user.id, plan='free', credits_balance=1000)
            session.add(billing)
            await session.commit()
            print("[OK] Test user created")
        else:
            print("[OK] Test user already exists")

    # Print startup info
    print("=" * 60)
    print("🏛️  GemmaFinOS Backend — Full Application")
    print("=" * 60)
    print("[*] Endpoints:")
    print("    📊 Health:  http://localhost:8000/health")
    print("    🔍 Search:  http://localhost:8000/v1/search?q=section+302+IPC")
    print("    💬 Chat:    http://localhost:8000/docs")
    print("    ⚖️  Compliance: http://localhost:8000/v1/compliance/triage")
    print("    📋 API Docs: http://localhost:8000/docs")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(init_db())

    import uvicorn
    print("[*] Starting server on http://0.0.0.0:8000")
    print("[*] Press Ctrl+C to stop\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
