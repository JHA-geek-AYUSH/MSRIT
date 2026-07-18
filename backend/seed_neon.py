import asyncio
import uuid
import sys
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load env before importing models
load_dotenv()

from app.db.session import SessionLocal
from app.db.models import User, Matter, Query, Run, ComplianceAuditLog

async def seed_data():
    async with SessionLocal() as session:
        # Create an admin user (matching default local clerk ID if needed)
        admin_id = uuid.uuid4()
        admin_user = User(
            id=admin_id,
            clerk_id="user_2p5A7WkE8...", # mock clerk ID
            email="admin@gemmaFin.track2",
            role="admin",
            wallet_address="0x123..."
        )
        session.add(admin_user)

        # Create some matters
        matters = []
        for i in range(3):
            m = Matter(
                id=uuid.uuid4(),
                user_id=admin_id,
                title=f"Compliance Review - SME Corp {i+1}",
                language="en"
            )
            matters.append(m)
            session.add(m)
            
        await session.flush()

        # Create queries and runs
        for i, m in enumerate(matters):
            q = Query(
                id=uuid.uuid4(),
                matter_id=m.id,
                message=f"Check recent financial transactions for {m.title}",
                mode="general"
            )
            session.add(q)
            
            r = Run(
                id=uuid.uuid4(),
                query_id=q.id,
                answer_text="Triage complete. Awaiting review.",
                confidence=0.85 + (i * 0.05)
            )
            session.add(r)
            
            # Create Audit Logs for these runs
            audit = ComplianceAuditLog(
                id=uuid.uuid4(),
                run_id=r.id,
                original_tier=f"tier_{i+1}",
                status="pending" if i % 2 == 0 else "approved",
                comments="Looks good" if i % 2 != 0 else None,
                officer_id=admin_id if i % 2 != 0 else None,
                reviewed_at=datetime.utcnow() if i % 2 != 0 else None
            )
            session.add(audit)

        await session.commit()
        print("Neon Database seeded successfully!")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_data())
