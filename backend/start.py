#!/usr/bin/env python3
"""Initialize database and start GemmaFinOS backend."""
import asyncio
import sys
import subprocess
from pathlib import Path

async def init_database():
    """Create database tables from models."""
    print("[*] Initializing database...")
    try:
        from app.db.models import Base
        from app.db.session import engine
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] Database tables created")
        
        # Create test user
        from app.db.session import SessionLocal
        from app.db.models import User, BillingAccount
        from uuid import uuid4
        
        async with SessionLocal() as session:
            from sqlalchemy import select
            existing = await session.execute(select(User).where(User.clerk_id == 'test-user-123'))
            if not existing.scalar():
                user = User(
                    id=uuid4(),
                    clerk_id='test-user-123',
                    email='test@example.com',
                    role='lawyer'
                )
                session.add(user)
                await session.flush()
                
                billing = BillingAccount(
                    user_id=user.id,
                    plan='free',
                    credits_balance=1000
                )
                session.add(billing)
                await session.commit()
                print("[OK] Test user created (clerk_id: test-user-123)")
            else:
                print("[OK] Test user already exists")
        
        return True
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {str(e)[:200]}")
        return False

async def main():
    """Initialize and start backend."""
    print("=" * 60)
    print("GemmaFinOS Backend Startup")
    print("=" * 60)
    
    # Initialize database
    success = await init_database()
    if not success:
        print("\n[WARN] Database initialization failed, but continuing...")
    
    print("\n[*] Starting backend server...")
    print("[*] http://localhost:8000")
    print("[*] API docs: http://localhost:8000/docs")
    print("[*] Test endpoint: http://localhost:8000/v1/test/db")
    print("\nPress Ctrl+C to stop\n")
    
    # Start uvicorn
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000"
    ])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[*] Backend stopped")
        sys.exit(0)
