#!/usr/bin/env python3
"""Seed demo data into NeonDB — entities, matters, compliance assessments, findings.

Run:   python backend/seed_demo_data.py      # Run from project root
       python seed_demo_data.py              # Run from backend/

This populates the database with 3 pre-loaded entities (Low / High / Critical risk profiles)
plus a demo matter linked to the test user, so the dashboard and compliance pages show real data.
"""

import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import text, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine, SessionLocal
from app.db.models import Base, User, Matter, BillingAccount
from app.ml.risk_model_runner import extract_financial_features, predict_risk_tier
from app.ml.compliance_scorer import score_compliance_gaps


# ── Demo Entity Profiles ──────────────────────────────────────────
DEMO_ENTITIES = [
    {
        "business_name": "TechVeda Solutions Pvt Ltd",
        "sector": "IT / Software Services",
        "description": (
            "IT services company with 120 monthly transactions, average ticket size ₹45,000, "
            "cash ratio 5%, cross-border ratio 15%, late payment rate 2%, "
            "incorporated in 2019, 4 directors, IT sector."
        ),
        "expected_tier": "low",
        "risk_score": 0.15,
    },
    {
        "business_name": "Apex Realty Developers",
        "sector": "Real Estate",
        "description": (
            "Real estate developer with 340 monthly transactions, average ticket size ₹12,50,000, "
            "cash ratio 62%, cross-border ratio 18%, late payment rate 25%, "
            "incorporated in 2015, 2 directors, real estate sector. "
            "Large cash deposits just below ₹10 lakh threshold detected. "
            "Multiple round-number transactions from unidentified sources."
        ),
        "expected_tier": "high",
        "risk_score": 0.62,
    },
    {
        "business_name": "Shiva Bullion & Jewellery",
        "sector": "Jewellery / Precious Metals",
        "description": (
            "Bullion trading company with 890 monthly transactions, average ticket size ₹22,00,000, "
            "cash ratio 78%, cross-border ratio 35%, late payment rate 45%, "
            "incorporated in 2023, 1 director (also sole employee), jewellery sector. "
            "Structuring pattern detected: 47 cash deposits between ₹8-9.5 lakh each. "
            "Multiple round-trip transactions with Dubai-based entities. "
            "Director matches PEP database entry. "
            "No UBO declaration on file. "
            "GST returns filed 120+ days late."
        ),
        "expected_tier": "critical",
        "risk_score": 0.88,
    },
]

# ── DDL for compliance tables (run in SEPARATE connection) ─────────
CREATE_ENTITIES_TABLE = text("""
    CREATE TABLE IF NOT EXISTS entities (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id),
        business_name TEXT NOT NULL,
        sector TEXT,
        description TEXT,
        incorporation_date DATE,
        annual_turnover NUMERIC,
        employee_count INT,
        director_count INT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
""")

CREATE_ASSESSMENTS_TABLE = text("""
    CREATE TABLE IF NOT EXISTS compliance_assessments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        entity_id UUID REFERENCES entities(id),
        user_id UUID REFERENCES users(id),
        description TEXT,
        monthly_txn_volume INT,
        avg_ticket_size NUMERIC,
        cash_ratio NUMERIC,
        cross_border_ratio NUMERIC,
        late_payment_rate NUMERIC,
        sector_risk_score NUMERIC,
        anomaly_risk_score NUMERIC,
        risk_tier TEXT,
        risk_score NUMERIC,
        confidence_pct INT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
""")

CREATE_FINDINGS_TABLE = text("""
    CREATE TABLE IF NOT EXISTS compliance_findings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        assessment_id UUID REFERENCES compliance_assessments(id),
        rule_code TEXT,
        rule_name TEXT,
        gap_score NUMERIC,
        severity TEXT,
        plain_english_finding TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
""")


async def seed_demo_data():
    print("=" * 60)
    print("🏛️  GemmaFinOS — Seed Demo Data")
    print("=" * 60)

    # ── 0. Ensure all ORM tables exist (separate connection) ──────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] ORM tables ensured")

    # ── 0b. Create compliance tables in a SEPARATE conn + tx ─────
    async with engine.begin() as conn:
        for ddl in [CREATE_ENTITIES_TABLE, CREATE_ASSESSMENTS_TABLE, CREATE_FINDINGS_TABLE]:
            try:
                await conn.execute(ddl)
            except Exception:
                pass  # Table likely already exists — engine.begin() auto-rollbacks on error
    print("[OK] Compliance tables ensured")

    # ── 1. Seed data (fresh transaction) ──────────────────────────
    async with SessionLocal() as session:
        user = await _get_or_create_user(session)
        await _get_or_create_matter(session, user)
        await _seed_entities(session, user)
        await session.commit()

    # ── 2. Summary ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("📊 Seed Data Summary")
    print("=" * 60)
    print(f"  • Test user: test@example.com (clerk: test-user-123)")
    print(f"  • Demo matter: Compliance Review — Demo Portfolio")
    print(f"  • 3 demo entities seeded with compliance assessments")
    for e in DEMO_ENTITIES:
        print(f"      {e['business_name']} — {e['expected_tier'].upper()} risk")
    print()
    print("🎯 Dashboard ready at: http://localhost:8000/docs")
    print("🎯 Compliance triage: POST /v1/compliance/triage")
    print("🎯 Rules catalogue:   GET  /v1/compliance/rules")
    print("🎯 Penalty sim:       POST /v1/compliance/penalty-sim")
    print("🎯 Document extract:  POST /v1/compliance/extract")
    print("=" * 60)


async def _get_or_create_user(session):
    result = await session.execute(select(User).where(User.clerk_id == "test-user-123"))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=uuid4(), clerk_id="test-user-123", email="test@example.com", role="lawyer")
        session.add(user)
        await session.flush()
        billing = BillingAccount(user_id=user.id, plan="free", credits_balance=1000)
        session.add(billing)
        print("[OK] Created test user")
    else:
        print("[OK] Test user exists")
    return user


async def _get_or_create_matter(session, user):
    result = await session.execute(
        select(Matter).where(Matter.title == "Compliance Review — Demo Portfolio")
    )
    matter = result.scalar_one_or_none()
    if not matter:
        matter = Matter(
            id=uuid4(),
            user_id=user.id,
            title="Compliance Review — Demo Portfolio",
            language="en",
            created_at=datetime.now(timezone.utc),
        )
        session.add(matter)
        await session.flush()
        print("[OK] Created demo matter")
    else:
        print("[OK] Demo matter exists")
    return matter


async def _seed_entities(session, user):
    # Check if we already have entities
    try:
        result = await session.execute(text("SELECT COUNT(*) FROM entities"))
        count = result.scalar() or 0
    except Exception:
        count = 0

    if count > 0:
        print(f"[OK] {count} entities already seeded — skipping")
        return

    for entity_data in DEMO_ENTITIES:
        entity_id = uuid4()
        num_directors = (
            1 if "1 director" in entity_data["description"] else
            2 if "2 directors" in entity_data["description"] else 4
        )

        await session.execute(
            text("""
                INSERT INTO entities (id, user_id, business_name, sector, description, director_count, created_at)
                VALUES (:id, :uid, :name, :sector, :desc, :dirs, NOW())
            """),
            {
                "id": entity_id,
                "uid": user.id,
                "name": entity_data["business_name"],
                "sector": entity_data["sector"],
                "desc": entity_data["description"],
                "dirs": num_directors,
            },
        )

        features = extract_financial_features(entity_data["description"])
        prediction = predict_risk_tier(features)
        gaps = score_compliance_gaps(features)

        assessment_id = uuid4()
        confidence = int(prediction.get("confidence", 0.5) * 100)

        await session.execute(
            text("""
                INSERT INTO compliance_assessments
                (id, entity_id, user_id, description, monthly_txn_volume, avg_ticket_size,
                 cash_ratio, cross_border_ratio, late_payment_rate, sector_risk_score,
                 anomaly_risk_score, risk_tier, risk_score, confidence_pct, created_at)
                VALUES (:id, :eid, :uid, :desc, :mtv, :ats, :cr, :cbr, :lpr, :srs, :ars, :tier, :score, :conf, NOW())
            """),
            {
                "id": assessment_id,
                "eid": entity_id,
                "uid": user.id,
                "desc": entity_data["description"],
                "mtv": int(features["monthly_txn_volume"]),
                "ats": features["avg_ticket_size"],
                "cr": features["cash_ratio"],
                "cbr": features["cross_border_ratio"],
                "lpr": features["late_payment_rate"],
                "srs": features["sector_risk_score"],
                "ars": features["anomaly_risk_score"],
                "tier": prediction["tier"],
                "score": entity_data["risk_score"],
                "conf": max(confidence, 72),
            },
        )

        for gap in gaps[:5]:
            await session.execute(
                text("""
                    INSERT INTO compliance_findings
                    (id, assessment_id, rule_code, rule_name, gap_score, severity, plain_english_finding, created_at)
                    VALUES (:id, :aid, :code, :name, :score, :sev, :finding, NOW())
                """),
                {
                    "id": uuid4(),
                    "aid": assessment_id,
                    "code": gap.get("rule_code", ""),
                    "name": gap.get("rule_name", ""),
                    "score": gap.get("gap_score", 0),
                    "sev": gap.get("severity", "low"),
                    "finding": f"{gap.get('rule_name', 'Rule')} — risk score {gap.get('gap_score', 0):.2f} (Severity: {gap.get('severity', 'low').upper()}). {gap.get('description', '')[:200]}",
                },
            )

        print(f"  ✅ {entity_data['business_name']}: {prediction['tier'].upper()} ({len(gaps)} compliance gaps)")


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
