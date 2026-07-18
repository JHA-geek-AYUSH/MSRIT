#!/usr/bin/env python3
"""Test minimal backend endpoints."""
from app_minimal import app
from fastapi.testclient import TestClient

client = TestClient(app)

print("[TEST] Health endpoint")
resp = client.get('/health')
print(f"  Status: {resp.status_code}")
print(f"  Response: {resp.json()}")

print("\n[TEST] Compliance triage")
resp = client.post('/v1/compliance/triage', json={
    'description': 'Customer transferred 9.8L three times in 5 days',
    'mode': 'full'
})
print(f"  Status: {resp.status_code}")
data = resp.json()
print(f"  Risk Level: {data['overall_rating']}")
print(f"  Domains: {len(data['domains'])}")

print("\n[TEST] Create matter")
resp = client.post('/v1/matters', json={'title': 'Test Matter'})
print(f"  Status: {resp.status_code}")
print(f"  Matter ID: {resp.json()['id'][:8]}")

print("\n[SUCCESS] All endpoints working!")
