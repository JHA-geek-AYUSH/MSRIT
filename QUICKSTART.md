# GemmaFinOS Quick Start Guide

## 🚀 Get Running in 5 Minutes

### Prerequisites

- Docker & Docker Compose
- Node.js 18+
- Python 3.11+
- Git

### Step 1: Clone & Navigate

```bash
git clone https://github.com/gemmaFin/gemmaFin-os.git
cd gemmaFin-os
```

### Step 2: Start Infrastructure (PostgreSQL, Redis, Qdrant)

```bash
cd infra
docker-compose up -d
cd ..
```

Verify services are running:
```bash
docker-compose ps
```

### Step 3: Start Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

✅ Backend running at: `http://localhost:8000`
📚 API docs at: `http://localhost:8000/docs`

### Step 4: Start Frontend (New Terminal)

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

✅ Frontend running at: `http://localhost:3000`

### Step 5: Access the App

1. Open `http://localhost:3000` in your browser
2. Click **Sign In** (Clerk authentication)
3. Create account or sign in
4. Navigate to **Compliance** → **Financial Compliance & Risk Triage**
5. Enter test description and click **Run Compliance Triage**

---

## 📝 Test Inputs

### Transaction Triage
```
Customer transferred ₹9.8L three times in 5 days to three different accounts 
in different cities. No clear business purpose. Customer is a shell company 
with high turnover but only 1 director and 2 employees.
```

### Onboarding Triage
```
New corporate client applying for account. Directors include a politically 
exposed person (PEP) with connections to government. UBO declaration missing. 
No supporting documents for beneficial ownership verification.
```

### Financial Risk Triage
```
SME with ₹2.4Cr annual turnover. 60-day overdue invoices totaling ₹45L. 
Debt-to-equity ratio 3:1. No credit insurance. Supplier concentration: 
80% from single vendor.
```

---

## 🔧 Configuration

### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/gemmaFin
ASYNC_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/gemmaFin

# Vector DB
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=gemmaFin_chunks

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Clerk Auth
CLERK_JWKS_URL=https://your-clerk-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://your-clerk-instance.clerk.accounts.dev
CLERK_SECRET_KEY=sk_test_...

# Compliance
USE_GEMMA=false  # Use OpenAI instead
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
```

---

## 🧪 Testing

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"ok":true}
```

### Test Compliance Endpoint

```bash
# Get a Clerk token first, then:
curl -X POST http://localhost:8000/v1/compliance/triage \
  -H "Authorization: Bearer YOUR_CLERK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Customer transferred ₹9.8L three times in 5 days",
    "mode": "full"
  }'
```

### Run Integration Tests

```bash
cd backend
python test_compliance_flow.py
```

---

## 📊 Expected Output

When you run a compliance triage, you'll get:

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "overall_rating": "high",
  "domains": [
    {
      "name": "Transaction",
      "rating": "high",
      "summary": "Structuring pattern detected: multiple transactions just below ₹10L threshold",
      "confidence": 0.92
    },
    {
      "name": "Onboarding",
      "rating": "medium",
      "summary": "Shell company indicators: high turnover, low employee count",
      "confidence": 0.85
    }
  ],
  "full_report": "## COMPLIANCE & RISK TRIAGE REPORT\n\n### Executive Summary\nHigh-risk transaction profile with clear structuring indicators...",
  "recommendations": [
    "File STR within 7 working days",
    "Conduct enhanced due diligence on customer",
    "Review transaction patterns for past 12 months"
  ],
  "requires_str": true,
  "requires_edd": true
}
```

---

## 🐛 Troubleshooting

### "Failed to Fetch" Error

**Solution:**
1. Ensure you're signed in (check Clerk)
2. Verify backend is running: `curl http://localhost:8000/health`
3. Check browser console for detailed error
4. Verify `NEXT_PUBLIC_API_URL` in `.env.local`

### Backend Won't Start

**Solution:**
1. Check PostgreSQL is running: `docker-compose ps`
2. Verify `DATABASE_URL` in `.env`
3. Run migrations: `alembic upgrade head`
4. Check logs: `docker-compose logs postgres`

### Agents Timing Out

**Solution:**
1. Verify OpenAI API key is valid
2. Check API quota not exceeded
3. Increase timeout in `app/core/config.py`
4. Check network connectivity

### Port Already in Use

**Solution:**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

---

## 📚 Documentation

- **Full Guide:** `TRACK2_GUIDE.md`
- **Financial Solution:** `FINANCIAL_SOLUTION.md`
- **Fix Summary:** `FIX_SUMMARY.md`
- **API Docs:** `http://localhost:8000/docs`

---

## 🎯 Next Steps

1. ✅ Run the quick start above
2. ✅ Test with sample inputs
3. ✅ Review compliance output
4. ✅ Check API documentation
5. ✅ Deploy to production (see `TRACK2_GUIDE.md`)

---

## 💡 Key Features

- ✅ **Multi-Agent AI** — 5 specialized compliance agents
- ✅ **Real-Time Analysis** — 10-15 seconds per triage
- ✅ **India-Specific** — PMLA, FEMA, RBI, GST compliance
- ✅ **STR/EDD Auto-Flagging** — Automatic regulatory flagging
- ✅ **Compliance Reports** — Formal, audit-ready documents
- ✅ **Secure** — End-to-end encryption, PII redaction
- ✅ **Scalable** — 240+ triages/hour per instance

---

## 🚀 Production Deployment

For production deployment, see `TRACK2_GUIDE.md` section "Deployment Checklist"

---

**Questions?** Check the documentation or open an issue on GitHub.

**Ready to go!** 🎉
