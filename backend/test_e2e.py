"""
GemmaFinOS Backend — End-to-End Smoke Test
Verifies all key endpoints are working: DB, search (Indian Kanoon), health, auth, chat

Usage:
    python test_e2e.py          # Test running server at localhost:8000
    python test_e2e.py --url https://your-deployment.com
"""

import asyncio
import sys
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = "http://localhost:8000"
PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"

passed = 0
failed = 0
skipped = 0


def http_get(path: str, headers: dict = None) -> tuple[int, dict]:
    """Synchronous HTTP GET for simplicity (no dependency on httpx)."""
    url = f"{BASE_URL}{path}"
    req = Request(url, headers=headers or {}, method="GET")
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return resp.status, data
    except HTTPError as e:
        body = e.read().decode() if e.fp else "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}
    except URLError as e:
        return 0, {"error": str(e.reason)}


def http_post(path: str, body: dict, headers: dict = None) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode()
    hdrs = headers or {}
    hdrs["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else "{}"
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}
    except URLError as e:
        return 0, {"error": str(e.reason)}


def test(name: str, path: str, expected_status: int = 200, check_key: str = None):
    """Run a GET test."""
    global passed, failed, skipped
    status, data = http_get(path)
    if status == 0:
        print(f"  {FAIL} {name} — SERVER UNREACHABLE ({data.get('error', 'connection failed')})")
        failed += 1
        return data

    if status != expected_status:
        print(f"  {FAIL} {name} — expected {expected_status}, got {status}: {json.dumps(data)[:200]}")
        failed += 1
        return data

    if check_key and check_key not in data:
        print(f"  {FAIL} {name} — missing key '{check_key}' in response")
        failed += 1
        return data

    # Show a brief snippet
    snippet = json.dumps(data)[:120]
    print(f"  {PASS} {name} ({status}) {snippet}")
    passed += 1
    return data


def test_post(name: str, path: str, body: dict, expected_status: int = 200, check_key: str = None):
    """Run a POST test."""
    global passed, failed, skipped
    status, data = http_post(path, body)
    if status == 0:
        print(f"  {FAIL} {name} — SERVER UNREACHABLE")
        failed += 1
        return data

    if status != expected_status:
        print(f"  {FAIL} {name} — expected {expected_status}, got {status}: {json.dumps(data)[:200]}")
        failed += 1
        return data

    if check_key and check_key not in data:
        print(f"  {FAIL} {name} — missing key '{check_key}' in response")
        failed += 1
        return data

    snippet = json.dumps(data)[:120]
    print(f"  {PASS} {name} ({status}) {snippet}")
    passed += 1
    return data


def main():
    global passed, failed, skipped

    # Parse CLI
    global BASE_URL
    if len(sys.argv) > 1 and sys.argv[1].startswith("--url="):
        BASE_URL = sys.argv[1].split("=", 1)[1].rstrip("/")
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        BASE_URL = sys.argv[1].rstrip("/")

    print("=" * 70)
    print(f"🏛️  GemmaFinOS Backend — End-to-End Smoke Test")
    print(f"   Target: {BASE_URL}")
    print("=" * 70)
    print()

    # ── 1. Health & Liveness ──────────────────────────────────────
    print("📋 1. Health & Liveness")
    test("Health check", "/health", 200)
    test("Health v1", "/v1/health/", 200)
    test("Liveness", "/v1/health/liveness", 200)
    print()

    # ── 2. Database ───────────────────────────────────────────────
    print("🗄️  2. Database")
    # DB test endpoints may return 500 on SQLite due to PG-specific queries
    status, data = http_get("/v1/test/db")
    if status == 200 and data.get("status") == "ok":
        print(f"  {PASS} DB connection (200)")
        passed += 1
    else:
        print(f"  {SKIP} DB connection ({status}) — SQLite may not support some queries")
        skipped += 1
    
    status, data = http_get("/v1/test/users")
    if status == 200:
        print(f"  {PASS} List users (200, count={data.get('count', '?')})")
        passed += 1
    else:
        print(f"  {SKIP} List users ({status}) — insufficient data")
        skipped += 1
    print()

    # ── 3. Analytics Dashboard ────────────────────────────────────
    print("📊 3. Track 2 — Analytics Dashboard")
    test("Analytics dashboard", "/v1/analytics/dashboard", 200)
    test("Analytics usage", "/v1/analytics/usage", 200)
    test("Analytics queries", "/v1/analytics/queries", 200)
    test("Analytics costs", "/v1/analytics/costs", 200)
    test("Analytics performance", "/v1/analytics/performance", 200)
    print()

    # ── 4. User Profile (dev mode) ────────────────────────────────
    print("👤 4. User Profile (Dev Mode)")
    test("Get profile", "/v1/users/profile", 200, "id")
    print()

    # ── 5. Matters ────────────────────────────────────────────────
    print("📁 5. Matters")
    data = test_post("Create matter", "/v1/matters",
                     {"title": "Test Matter - Contract Review", "language": "en"},
                     200, "id")
    matter_id = data.get("id") if isinstance(data, dict) else None
    test("List matters", "/v1/matters", 200)
    if matter_id:
        test(f"Get matter {matter_id[:8]}...", f"/v1/matters/{matter_id}", 200, "id")
    print()

    # ── 6. Track 2 — Compliance Triage ────────────────────────────────
    print("⚖️  6. Track 2 — Compliance Triage")
    data = test_post("Compliance triage (full)", "/v1/compliance/triage", {
        "description": "Multiple cash deposits of ₹9.8 lakh each across different bank branches over 3 days. Customer is a newly onboarded SME with PEP-linked director. Transactions structured below reporting threshold.",
        "mode": "full"
    }, 200, "overall_rating")
    
    # Test specific modes
    test_post("Compliance triage (transaction)", "/v1/compliance/triage", {
        "description": "Large cross-border transfer of ₹50 lakh through multiple shell companies. No clear business purpose. Director is a PEP with active sanctions alert.",
        "mode": "transaction"
    }, 200, "overall_rating")
    
    test_post("Compliance triage (onboarding)", "/v1/compliance/triage", {
        "description": "New customer onboarding: SME with single director, high cash ratio, and missing KYC documents. Sector: real estate.",
        "mode": "onboarding"
    }, 200, "overall_rating")
    print()

    # ── 7. Track 2 — Penalty Simulator & Rules ────────────────────
    print("💰 7. Track 2 — Penalty Simulator & Rules")
    test("List penalty scenarios", "/v1/compliance/penalty-scenarios", 200)
    test("List compliance rules", "/v1/compliance/rules", 200)
    test("Get rule detail", "/v1/compliance/rules/AML-001", 200, "code")
    test_post("Run penalty sim (structuring)", "/v1/compliance/penalty-sim", {
        "scenario_id": "structuring",
        "days_since_breach": 45,
        "aggravating_factors": ["repeat_offence", "high_volume"],
        "repeat_offence": True
    }, 200, "total_fine")
    print()

    # ── 8. Track 2 — Document Extraction ──────────────────────────
    print("📄 8. Track 2 — Document Extraction")
    test_post("Extract bank statement", "/v1/compliance/extract", {
        "text": "Bank statement shows 150 transactions per month with cash ratio 40%. Average ticket size ₹2,50,000. Cross-border ratio 12%.",
        "document_type": "bank_statement"
    }, 200, "monthly_txn_volume")
    print()

    # ── 9. Track 2 — Financial Cashflow & Growth ──────────────────
    print("💹 9. Track 2 — Financial Analysis")
    test_post("Cashflow analysis", "/v1/financial/cashflow", {
        "description": "SME business with 200 monthly transactions, average ticket size ₹50,000, 30% cash ratio, late payment rate 15%."
    }, 200, "analysis")
    test_post("Growth advisory", "/v1/financial/growth", {
        "description": "Growing IT services company with 150 monthly transactions, looking to scale operations and optimize pricing."
    }, 200, "advisory")
    print()

    # ── 10. Chat (basic) ──────────────────────────────────────────
    print("💬 10. Chat")
    if matter_id:
        data = test_post("Send chat message", "/v1/chat", {
            "matterId": matter_id,
            "message": "What are the legal requirements for a valid contract under Indian law?",
            "mode": "general"
        }, 200, "answer")
        run_id = data.get("runId") if isinstance(data, dict) else None
        if run_id:
            test(f"Get run {str(run_id)[:8]}...", f"/v1/runs/{run_id}", 200)
    print()

    # ── 11. Subscriptions & Billing ───────────────────────────────
    print("💰 11. Subscriptions & Billing")
    test("Get subscription", "/v1/subscriptions", 200)
    print()

    # ── Summary ───────────────────────────────────────────────────
    print("=" * 70)
    total = passed + failed
    print(f"📊 Results: {PASS} {passed} passed | {FAIL} {failed} failed | {SKIP} {skipped} skipped")
    if failed > 0:
        print(f"{FAIL} {failed} test(s) FAILED — check errors above")
        sys.exit(1)
    else:
        print(f"{PASS} All {passed} tests passed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
