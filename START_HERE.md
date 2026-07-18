# GemmaFinOS - How to Run (WORKING VERSION)

## Status: ✅ WORKING

The minimal backend has been tested and all endpoints work.

## Start in 2 Steps

### Step 1: Start Backend (Terminal 1)

```bash
cd backend
python -m uvicorn app_minimal:app --host 0.0.0.0 --port 8000
```

You should see:
```
Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Start Frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

You should see:
```
ready - started server on 0.0.0.0:3000
```

## Access the App

Open browser: **http://localhost:3000**

## Test Compliance Triage

1. Sign in (use any credentials, Clerk is bypassed)
2. Click **Compliance** in navigation
3. Paste this text:
   ```
   Customer transferred ₹9.8L three times in 5 days to different accounts. 
   No clear business purpose. Shell company with 1 director.
   ```
4. Click **Run Compliance Triage**
5. See results instantly

## API Endpoints (All Working)

- `GET http://localhost:8000/health` — Health check
- `POST http://localhost:8000/v1/compliance/triage` — Compliance analysis
- `POST http://localhost:8000/v1/matters` — Create matter
- `GET http://localhost:8000/v1/matters` — List matters
- `POST http://localhost:8000/v1/chat` — Chat endpoint
- `GET http://localhost:8000/docs` — API documentation

## Test Backend Directly

```bash
cd backend
python test_minimal.py
```

Expected output:
```
[TEST] Health endpoint
  Status: 200
  Response: {'status': 'ok', 'service': 'GemmaFinOS Backend'}

[TEST] Compliance triage
  Status: 200
  Risk Level: high
  Domains: 1

[TEST] Create matter
  Status: 200
  Matter ID: b2aa1c75

[SUCCESS] All endpoints working!
```

## What Works

✅ Backend starts instantly
✅ Frontend connects
✅ Compliance triage returns results
✅ Chat works
✅ Matter creation works
✅ Analytics endpoint works
✅ All API endpoints respond

## What's Mock

- Compliance analysis is heuristic-based (not AI)
- No database (in-memory only)
- No real authentication
- Data lost on restart

## Next Steps

To make it production-ready:
1. Add database (PostgreSQL/SQLite)
2. Add real LLM (OpenAI API)
3. Add real compliance agents
4. Add authentication
5. Add legal case law database

## Troubleshooting

**Backend won't start:**
```bash
# Check if port 8000 is in use
netstat -ano | findstr ":8000"

# Kill process if needed
taskkill /PID <PID> /F
```

**Frontend won't connect:**
- Verify backend is running: `curl http://localhost:8000/health`
- Check `.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`
- Clear browser cache

**"Failed to fetch" error:**
- Refresh page
- Check browser console
- Verify both backend and frontend are running

## Files

- `backend/app_minimal.py` — Minimal backend (MAIN FILE)
- `backend/test_minimal.py` — Test script
- `backend/start_backend.bat` — Windows batch file
- `frontend/start_frontend.bat` — Windows batch file
- `README_MINIMAL.md` — Full documentation

## Summary

**This works. Run it now:**

```bash
# Terminal 1
cd backend && python -m uvicorn app_minimal:app --host 0.0.0.0 --port 8000

# Terminal 2
cd frontend && npm run dev

# Browser
http://localhost:3000
```

Done!
