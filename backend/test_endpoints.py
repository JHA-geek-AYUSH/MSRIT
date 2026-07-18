"""
End-to-end endpoint smoke test.
Run: .\venv\Scripts\python.exe test_endpoints.py
"""
import json, time
import urllib.request, urllib.error

BASE = "http://localhost:8000"
RESULTS = []

def req(method, path, body=None, label=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=headers, method=method),
            timeout=60
        )
        resp = json.loads(r.read())
        status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            resp = json.loads(e.read())
        except Exception:
            resp = {}
    except Exception as e:
        status = 0
        resp = {"error": str(e)}
    
    tag = label or f"{method} {path}"
    ok = status in (200, 201, 400, 401, 402, 404)  # 400/401/402/404 are expected without real auth
    symbol = "✓" if ok else "✗"
    print(f"  {symbol} [{status}] {tag}")
    if status == 500:
        print(f"       DETAIL: {resp.get('detail', resp)}")
    RESULTS.append((tag, status, ok))
    return status, resp

print("\n=== Backend Health ===")
req("GET",  "/health",    label="GET /health")
req("GET",  "/v1/health", label="GET /v1/health")

print("\n=== Auth-required routes (expect 400/401, NOT 500) ===")
req("GET",  "/v1/matters",              label="GET /v1/matters (no auth)")
req("POST", "/v1/matters", {"title":"t","language":"en"}, label="POST /v1/matters (no auth)")
req("GET",  "/v1/analytics/dashboard",  label="GET /v1/analytics/dashboard (no auth)")
req("GET",  "/v1/subscriptions/subscription", label="GET /v1/subscriptions (no auth)")
req("GET",  "/v1/privacy/data-summary", label="GET /v1/privacy/data-summary (no auth)")

print("\n=== Compliance Triage (no auth fallback) ===")
status, resp = req("POST", "/v1/compliance/triage", {
    "description": "Customer deposited Rs 9.8L three times in 5 days to 3 different accounts. PAN missing. Director is PEP.",
    "mode": "transaction"
}, label="POST /v1/compliance/triage")
if status == 200 and resp.get("run_id"):
    print(f"       run_id={resp['run_id'][:8]}.. overall={resp.get('overall_rating')} edd={resp.get('requires_edd')}")

print("\n=== Summary ===")
ok_count = sum(1 for _, _, ok in RESULTS if ok)
fail_count = len(RESULTS) - ok_count
print(f"  {ok_count}/{len(RESULTS)} passed, {fail_count} need attention")
for tag, status, ok in RESULTS:
    if not ok:
        print(f"  FAIL [{status}] {tag}")
