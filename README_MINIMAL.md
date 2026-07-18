# GemmaFinOS - Minimal Working Version

## What This Is

A **truly minimal, working** version of GemmaFinOS (Financial Compliance & Risk Triage) that:
- ✅ Actually starts without errors
- ✅ Has zero external dependencies (just FastAPI)
- ✅ Provides mock compliance analysis
- ✅ Works with the frontend
- ✅ Can be extended later

## Quick Start (2 Steps)

### Step 1: Start Backend

**Windows:**
```bash
cd backend
start_backend.bat
```

Or manually:
```bash
cd backend
python -m uvicorn app_minimal:app --host 0.0.0.0 --port 8000
```

**Expected output:**
```
Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Start Frontend

**New terminal:**
```bash
cd frontend
npm run dev
```

**Expected output:**
```
ready - started server on 0.0.0.0:3000
```

## Access the App

1. Open `http://localhost:3000` in browser
2. Sign in (Clerk authentication)
3. Navigate to **Compliance** page
4. Enter a test description
5. Click **Run Compliance Triage**
6. See results in 1-2 seconds

## Test Inputs

### Transaction Triage
```
Customer transferred ₹9.8L three times in 5 days to different accounts. 
No clear business purpose. Shell company with high turnover but only 1 director.
```

### Onboarding Triage
```
New corporate client. Directors include PEP (politically exposed person). 
UBO declaration missing. No supporting documents.
```

### Financial Risk Triage
```
SME with ₹2.4Cr turnover. 60-day overdue invoices totaling ₹45L. 
Debt-to-equity ratio 3:1. No credit insurance.
```

## API Endpoints

All endpoints return mock data:

- `GET /health` — Health check
- `POST /v1/matters` — Create legal matter
- `GET /v1/matters` — List matters
- `POST /v1/compliance/triage` — Run compliance analysis
- `POST /v1/chat` — Legal research chat
- `GET /v1/analytics/dashboard` — Get analytics

## API Documentation

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## What Works

✅ Backend starts without errors
✅ Frontend connects to backend
✅ Compliance triage returns results
✅ Chat endpoint works
✅ Analytics endpoint works
✅ Matter creation works
✅ Conversation history works

## What's Mock

- All responses are hardcoded/heuristic-based
- No real database
- No real AI/LLM
- No real authentication (bypassed)
- No real compliance analysis

## Next Steps to Make It Real

1. **Add Database** — PostgreSQL or SQLite
2. **Add Real LLM** — OpenAI API integration
3. **Add Real Auth** — Clerk integration
4. **Add Real Agents** — Compliance analysis agents
5. **Add Real Data** — Legal case law database

## Troubleshooting

### Backend won't start
```bash
# Make sure port 8000 is free
netstat -ano | findstr ":8000"

# Kill process if needed
taskkill /PID <PID> /F
```

### Frontend won't connect
- Check backend is running: `curl http://localhost:8000/health`
- Check `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`
- Clear browser cache

### "Failed to fetch" error
- Refresh page
- Check browser console for errors
- Verify backend is running

## File Structure

```
backend/
  app_minimal.py          <- Minimal backend (START THIS)
  start_backend.bat       <- Windows batch file to start backend
  
frontend/
  start_frontend.bat      <- Windows batch file to start frontend
  .env.local              <- Frontend config
```

## Performance

- Backend startup: <1 second
- Compliance triage response: <1 second
- No database queries
- No external API calls
- Pure in-memory storage

## Limitations

- Data is lost when backend restarts
- No persistence
- No real compliance analysis
- No real authentication
- Single instance only

## Status

✅ **WORKING** - This minimal version actually works and can be extended.

---

**To run:** 
1. `cd backend && python -m uvicorn app_minimal:app --host 0.0.0.0 --port 8000`
2. `cd frontend && npm run dev`
3. Open `http://localhost:3000`

That's it!
