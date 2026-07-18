# FinTriage AI — Gemma Financial Compliance & Risk Triage Platform
## Track 2 Master Plan | Hackathon 18 July 2026

---

## 1. Product Vision

**FinTriage AI** is an intelligent compliance assistant for SMEs and financial review teams.
It ingests raw transaction data, onboarding documents, and financial records — runs them through
a 3-stage ML pipeline — and surfaces a ranked, explainable compliance risk triage with
Gemma-generated audit-ready reports.

The system operates as both a **batch compliance scanner** (upload → report) and a
**live conversational agent** (analyst asks questions, agent re-runs pipeline, simulates
regulatory penalties, compares entity risk profiles in natural language).

**Who uses it:**
| User | Need |
|---|---|
| SME Owner | Understand my compliance exposure before an audit |
| Compliance Officer | Triage 50 entities by risk, generate reports for review board |
| Bank / NBFC Onboarding Team | Instantly score new business applicants for KYC/AML risk |
| Regulatory Analyst | Ask "what if this entity's cash ratio doubles?" and get instant re-assessment |

---

## 2. Core Capabilities (Track 2 Requirements — All Covered)

| Track 2 Requirement | How FinTriage Covers It |
|---|---|
| Analyze transactions | Transaction anomaly scorer — 12 flag types, weighted risk per flag |
| Analyze onboarding documents | Gemma extracts business registration, turnover, director details from PDF/image |
| Analyze financial records | Bank statement parser — extracts cash ratio, velocity, round-number patterns |
| Detect anomalies | Stage 0 anomaly scorer + XGBoost classifier (Stage 1) |
| Assess risk | 3-stage ML pipeline → risk tier (Low / Medium / High / Critical) |
| Summarize findings | Gemma generates plain-English finding summaries per entity |
| Generate compliance-ready reports | `/api/report` → structured PDF-ready JSON with all findings, flags, scores |
| Conversational agent | 7-tool orchestration agent — natural language queries over live pipeline |

---

## 3. System Architecture

```
Browser (Next.js 16 — TypeScript)
  │
  ├── Onboarding Form (5-step entity intake)
  ├── Document Upload (PDF / image → Gemma extraction)
  ├── Privacy Review Screen (extracted values, editable)
  ├── Compliance Dashboard (risk card + finding cards)
  ├── Penalty Simulator
  ├── Entity Comparison Table
  └── AI Agent Chat (persistent bottom bar)
        │
        ▼
  FastAPI + Uvicorn (Python 3.12)
        │
        ├── Supabase JWT Auth (HS256) ──────────────────────────────────┐
        │                                                               │
        └── 3-Stage ML Pipeline                                         │
              │                                                    Supabase PostgreSQL
              ├── Stage 0: Anomaly Scorer                          (RLS enforced)
              │     └── Gemma flags → risk weights (0.0–1.0)       entities
              │         + local cache (condition_cache pattern)     assessments
              │                                                     findings
              ├── Stage 1: XGBoost Risk Classifier                  penalty_sims
              │     └── 9 features → Low/Medium/High/Critical       chat_messages
              │         + confidence score                          audit_reports
              │
              ├── Stage 2: Weighted Compliance Gap Scorer
              │     └── 6 factors → gap score 0–10 per rule
              │
              └── Stage 3: Cosine Similarity Ranker
                    └── 9D entity vector vs rule ideal_vector
                        Final = 60% gap score + 40% similarity
                              │
                    Gemma: plain-English finding per rule
                              │
                    ◄── Ranked compliance findings + report JSON
        │
        └── Gemma Agent (7 tools, intent classifier, tool dispatcher)
              reassess / penalty_sim / threshold_sim /
              compare / explain_risk / rule_info / generate_report
```

---

## 4. ML Pipeline — Full Detail

### Stage 0 — Anomaly Scorer (`anomaly_scorer.py`)

Scores each transaction flag extracted from documents or entered manually.
Uses the same cache + Gemma pattern as `condition_scorer.py`.

**12 Transaction Flag Types:**

| Flag | Risk Weight Range | Trigger |
|---|---|---|
| `large_cash_deposit` | 0.55 – 0.75 | Single cash deposit > ₹10L |
| `round_number_transactions` | 0.30 – 0.50 | >30% of txns are round numbers |
| `rapid_succession_transfers` | 0.60 – 0.80 | >5 transfers within 24 hours |
| `structuring_pattern` | 0.75 – 0.95 | Multiple txns just below reporting threshold |
| `dormant_account_spike` | 0.65 – 0.85 | Account inactive >6 months, sudden high volume |
| `cross_border_unregistered` | 0.70 – 0.90 | International txns without FEMA registration |
| `shell_company_indicator` | 0.80 – 0.95 | No employees, high turnover, single director |
| `invoice_mismatch` | 0.40 – 0.65 | Invoice amount ≠ bank credit within 5% tolerance |
| `late_gst_filing` | 0.20 – 0.40 | GST returns filed >30 days late |
| `director_pep_match` | 0.85 – 1.00 | Director name matches PEP/sanctions list |
| `high_cash_ratio` | 0.35 – 0.60 | Cash transactions >40% of total volume |
| `unusual_sector_activity` | 0.30 – 0.55 | Transaction pattern inconsistent with declared sector |

Output: `anomaly_risk_score` (0–5 normalized), `dominant_flag`, `risk_summary`

---

### Stage 1 — XGBoost Risk Classifier

**Input Features (9D):**

| Feature | Description | Source |
|---|---|---|
| `monthly_txn_volume` | Number of transactions/month | Form / bank statement |
| `avg_ticket_size` | Average transaction amount (₹) | Computed |
| `cash_ratio` | % of cash transactions | Bank statement |
| `cross_border_ratio` | % of international transactions | Bank statement |
| `late_payment_rate` | % of invoices paid >30 days late | Invoice records |
| `business_age_years` | Years since incorporation | Onboarding doc |
| `sector_risk_score` | Encoded sector risk (0.0–1.0) | Sector lookup table |
| `director_count` | Number of active directors | Onboarding doc |
| `anomaly_risk_score` | Stage 0 output (0–5) | Stage 0 |

**Output:** Risk tier (Low / Medium / High / Critical) + confidence %

**Training Dataset:** 80,000 synthetic SME records generated via `generate_dataset.py`
with realistic distributions per sector (retail, real estate, fintech, manufacturing, services).

**Sector Risk Lookup Table:**

| Sector | Risk Score |
|---|---|
| Real Estate | 0.85 |
| Cryptocurrency / Virtual Assets | 0.90 |
| Jewellery / Precious Metals | 0.80 |
| Money Services / Forex | 0.88 |
| Construction | 0.70 |
| Retail (Cash-heavy) | 0.55 |
| IT / Software Services | 0.20 |
| Manufacturing | 0.30 |
| Healthcare | 0.25 |
| Education | 0.15 |

---

### Stage 2 — Weighted Compliance Gap Scorer

Scores each of **40 compliance rules** in the rule catalogue against the entity profile.

**6 Scoring Factors:**

| Factor | Weight | Logic |
|---|---|---|
| Rule Trigger Match | 35% | Does the entity's profile directly trigger this rule? |
| Risk Tier Alignment | 20% | Does the entity's risk tier meet the rule's severity threshold? |
| Sector Applicability | 15% | Is this rule mandatory for the entity's sector? |
| Recency of Flags | 15% | How recent are the triggering transactions? (decay function) |
| Volume Threshold Proximity | 15% | How close is the entity to the rule's reporting threshold? |

**Hard gates:** Rules with `mandatory: true` for a sector always appear regardless of score.

---

### Stage 3 — Cosine Similarity Ranker

- Builds a 9D entity vector from the same features as Stage 1
- Each compliance rule has an `ideal_risk_vector` (the profile of an entity most likely to breach it)
- Cosine similarity computed between entity vector and each rule's ideal vector
- **Final score = 60% gap score + 40% cosine similarity**
- Returns top 5 highest-risk rules per entity

---

## 5. Compliance Rule Catalogue (`rules_db.py`) — 40 Rules

**Categories:**

| Category | Rules | Regulatory Body |
|---|---|---|
| AML (Anti-Money Laundering) | 10 rules | PMLA 2002, FIU-IND |
| KYC (Know Your Customer) | 8 rules | RBI KYC Master Direction 2016 |
| GST Compliance | 6 rules | GST Act 2017, GSTN |
| FEMA (Foreign Exchange) | 5 rules | FEMA 1999, RBI |
| Income Tax | 5 rules | IT Act 1961, Section 269ST |
| Corporate Governance | 6 rules | Companies Act 2013, MCA |

**Sample Rule Schema:**
```python
{
  "id": 1,
  "code": "AML-001",
  "name": "Cash Transaction Reporting (CTR)",
  "category": "AML",
  "regulatory_body": "FIU-IND",
  "description": "Any cash transaction above ₹10 lakh must be reported to FIU-IND within 7 days.",
  "threshold": 1000000,
  "threshold_unit": "INR_single_transaction",
  "mandatory_sectors": ["all"],
  "severity": "High",
  "max_penalty_inr": 1000000,
  "penalty_per_day_inr": 10000,
  "imprisonment_risk": False,
  "ideal_risk_vector": [500, 250000, 0.65, 0.05, 0.10, 3, 0.55, 2, 3.5],
  "remediation_steps": [
    "File CTR with FIU-IND portal within 7 days",
    "Maintain transaction records for 5 years",
    "Train staff on cash handling thresholds"
  ],
  "references": ["PMLA Section 12", "FIU-IND Circular 2023-04"]
}
```

---

## 6. API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/api/health` | System status — model loaded, rule count, LLM status |
| `POST` | `/api/assess` | Full 3-stage pipeline → risk tier + top 5 rules breached |
| `POST` | `/api/extract` | Gemma extracts entity data from PDF / bank statement image |
| `POST` | `/api/rank-rules` | Score all 40 rules against an entity (no Gemma, fast) |
| `GET` | `/api/rules` | Full compliance rule catalogue |
| `GET` | `/api/rules/{rule_id}` | Single rule detail with remediation steps |
| `POST` | `/api/penalty-sim` | Simulate regulatory fine for a specific violation scenario |
| `POST` | `/api/agent` | Conversational agent — 7 tools, natural language |
| `POST` | `/api/report` | Generate full compliance-ready audit report (Gemma) |
| `POST` | `/api/chat` | Simple compliance Q&A chat (no tool execution) |
| `POST` | `/api/score-flags` | Stage 0 only — score a list of transaction flags |
| `POST` | `/api/parse-flags` | NER extract flags from free text → Stage 0 score |

---

## 7. Agent — 7 Tools

The agent uses the same `run_agent()` orchestration pattern:
**Intent Classifier (regex + Gemma hybrid) → Tool Dispatcher → Gemma response generation**

| Tool | Trigger Phrases | What it does |
|---|---|---|
| `reassess` | "what if cash ratio increases", "add structuring pattern", "update profile" | Re-run full 3-stage pipeline with updated entity data |
| `penalty_sim` | "what fine", "penalty for", "how much would I owe", "worst case" | Calculate regulatory fine exposure for a violation |
| `threshold_sim` | "what if volume crosses", "if transactions double", "near threshold" | Re-rank rules when a metric crosses a reporting threshold |
| `compare` | "compare entity A and B", "vs", "side by side", "difference between" | Side-by-side compliance gap comparison of 2–3 entities |
| `explain_risk` | "why high risk", "explain my score", "what drives", "what caused" | Plain-English explanation of risk tier and top drivers |
| `rule_info` | "tell me about AML-001", "details on rule", "what is CTR" | Full rule detail — threshold, penalty, remediation steps |
| `generate_report` | "generate report", "create audit report", "export findings" | Gemma generates a structured compliance summary report |

---

## 8. Penalty Simulator — 10 Violation Scenarios (`penalty_simulator.py`)

```python
SCENARIOS = [
  {
    "id": "ctr_breach",
    "name": "Cash Transaction Reporting Failure",
    "rule_code": "AML-001",
    "base_fine_inr": 100000,
    "per_day_fine_inr": 10000,
    "max_fine_inr": 1000000,
    "imprisonment_months": 0,
    "aggravating_factors": ["repeat_offence", "high_volume"]
  },
  {
    "id": "str_failure",
    "name": "Suspicious Transaction Report Not Filed",
    "rule_code": "AML-003",
    "base_fine_inr": 500000,
    "per_day_fine_inr": 25000,
    "max_fine_inr": 5000000,
    "imprisonment_months": 7
  },
  {
    "id": "kyc_non_compliance",
    "name": "KYC Documentation Incomplete",
    "rule_code": "KYC-002",
    "base_fine_inr": 200000,
    "per_day_fine_inr": 5000,
    "max_fine_inr": 1000000,
    "imprisonment_months": 0
  },
  {
    "id": "gst_late_filing",
    "name": "GST Return Filed Late (>90 days)",
    "rule_code": "GST-001",
    "base_fine_inr": 50000,
    "per_day_fine_inr": 200,
    "max_fine_inr": 500000,
    "imprisonment_months": 0
  },
  {
    "id": "fema_violation",
    "name": "Unreported Foreign Remittance",
    "rule_code": "FEMA-001",
    "base_fine_inr": 300000,
    "per_day_fine_inr": 5000,
    "max_fine_inr": 3000000,
    "imprisonment_months": 0
  },
  {
    "id": "section_269st",
    "name": "Cash Receipt Above ₹2L (Section 269ST)",
    "rule_code": "IT-003",
    "base_fine_inr": 200000,
    "per_day_fine_inr": 0,
    "max_fine_inr": 200000,
    "imprisonment_months": 0
  },
  {
    "id": "structuring",
    "name": "Transaction Structuring (Smurfing)",
    "rule_code": "AML-005",
    "base_fine_inr": 1000000,
    "per_day_fine_inr": 50000,
    "max_fine_inr": 10000000,
    "imprisonment_months": 84
  },
  {
    "id": "pep_undisclosed",
    "name": "Undisclosed PEP Director",
    "rule_code": "KYC-006",
    "base_fine_inr": 500000,
    "per_day_fine_inr": 10000,
    "max_fine_inr": 5000000,
    "imprisonment_months": 0
  },
  {
    "id": "beneficial_owner",
    "name": "Beneficial Ownership Non-Disclosure",
    "rule_code": "CORP-003",
    "base_fine_inr": 100000,
    "per_day_fine_inr": 500,
    "max_fine_inr": 500000,
    "imprisonment_months": 0
  },
  {
    "id": "shell_company",
    "name": "Shell Company Activity Detected",
    "rule_code": "AML-009",
    "base_fine_inr": 2000000,
    "per_day_fine_inr": 100000,
    "max_fine_inr": 50000000,
    "imprisonment_months": 84
  }
]
```

**Penalty calculation logic:**
```
base_fine
+ (days_since_breach × per_day_fine)
× aggravating_multiplier (1.0 – 3.0 based on repeat offence, volume, sector)
capped at max_fine
```

---

## 9. Document Extraction via Gemma

`/api/extract` accepts PDF text or base64 image of:
- Bank statements → extracts: monthly_txn_volume, avg_ticket_size, cash_ratio, cross_border_ratio
- GST filings → extracts: filing_date, turnover_declared, late_days
- Business registration / onboarding docs → extracts: incorporation_date, sector, director_names, registered_capital
- Invoice batches → extracts: invoice_count, mismatch_count, avg_days_to_payment

Gemma prompt returns structured JSON. Same privacy review screen pattern — all extracted
values shown as editable fields before any pipeline runs.

---

## 10. Compliance Report Generation (`/api/report`)

Gemma generates a structured audit-ready report containing:

```
SECTION 1 — Entity Summary
  Business name, sector, incorporation date, assessment date

SECTION 2 — Risk Assessment
  Risk tier, confidence %, top 3 risk drivers with % contribution

SECTION 3 — Compliance Findings (per rule breached)
  Rule code, rule name, gap score, severity, plain-English finding,
  evidence (which flags triggered it), remediation steps

SECTION 4 — Penalty Exposure Summary
  Total estimated fine exposure (₹), breakdown per rule,
  imprisonment risk flag (yes/no), urgency tier

SECTION 5 — Recommended Actions
  Prioritized action list (Critical → High → Medium → Low)
  with estimated effort and regulatory deadline

SECTION 6 — Analyst Sign-off Block
  Prepared by, reviewed by, date fields (for human review teams)
```

---

## 11. Frontend — Page Structure

```
/login                  → Supabase Auth (email + password)
/register               → Business registration
/assess                 → 5-step entity intake form
/dashboard              → Risk card + compliance finding cards + agent chat
/rules                  → Full rule catalogue with filters (category, severity, sector)
/rules/[id]             → Rule detail page (threshold, penalty, remediation)
/penalty-sim            → Penalty simulator (10 scenarios)
/compare                → Side-by-side entity comparison (up to 3)
/report/[assessment_id] → Generated compliance report (print-ready)
/history                → Past assessments for this user
```

### 5-Step Intake Form Fields

```
Step 1 — Business Identity
  Business name, sector (dropdown), incorporation date, registered state,
  annual turnover (₹), number of employees, number of directors

Step 2 — Transaction Profile
  Monthly transaction volume, average ticket size (₹),
  cash transaction ratio (%), cross-border transaction ratio (%),
  late payment rate (%), primary payment modes (checkboxes)

Step 3 — Document Upload
  Bank statement PDF / GST filing / Business registration certificate
  Gemma extracts values → shown on Step 4

Step 4 — Privacy Review
  All extracted + entered values shown as editable fields
  Confidence indicators (green / amber / red) per field
  User confirms before pipeline runs

Step 5 — Flags Review (optional)
  Pre-populated transaction flags detected from documents
  User can add/remove flags before final submission
```

### Dashboard Components

| Component | Description |
|---|---|
| Risk Tier Card | Colour-coded (green/yellow/orange/red), confidence %, top 3 drivers bar chart |
| Finding Cards | One card per breached rule — rule code, gap score, severity badge, warning flags, Gemma explanation, remediation CTA |
| Penalty Exposure Banner | Total fine exposure in ₹, urgency level, "Run Penalty Sim" button |
| Agent Chat Bar | Persistent bottom bar — same pattern as Outsurance |
| Report Button | "Generate Audit Report" → calls `/api/report` → opens `/report/[id]` |

---

## 12. Database Schema

```sql
-- Entity profiles
CREATE TABLE entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id),
  business_name text NOT NULL,
  sector text,
  incorporation_date date,
  annual_turnover numeric,
  employee_count int,
  director_count int,
  created_at timestamptz DEFAULT now()
);

-- Compliance assessments (one per pipeline run)
CREATE TABLE compliance_assessments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id uuid REFERENCES entities(id),
  user_id uuid REFERENCES auth.users(id),
  monthly_txn_volume int,
  avg_ticket_size numeric,
  cash_ratio numeric,
  cross_border_ratio numeric,
  late_payment_rate numeric,
  sector_risk_score numeric,
  anomaly_risk_score numeric,
  risk_tier text,
  risk_score numeric,
  confidence_pct int,
  feature_importance jsonb,
  created_at timestamptz DEFAULT now()
);

-- Per-rule findings from Stage 2+3
CREATE TABLE compliance_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES compliance_assessments(id),
  rule_id int,
  rule_code text,
  gap_score numeric,
  cosine_similarity numeric,
  combined_score numeric,
  severity text,
  warning_flags jsonb,
  plain_english_finding text,
  remediation_steps jsonb,
  created_at timestamptz DEFAULT now()
);

-- Penalty simulations
CREATE TABLE penalty_simulations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES compliance_assessments(id),
  user_id uuid REFERENCES auth.users(id),
  scenario_id text,
  rule_code text,
  days_since_breach int,
  aggravating_factors jsonb,
  base_fine numeric,
  per_day_fine numeric,
  total_fine numeric,
  imprisonment_risk boolean,
  verdict text,
  created_at timestamptz DEFAULT now()
);

-- Audit reports
CREATE TABLE audit_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES compliance_assessments(id),
  user_id uuid REFERENCES auth.users(id),
  report_json jsonb,
  gemma_summary text,
  total_penalty_exposure numeric,
  urgency_tier text,
  created_at timestamptz DEFAULT now()
);

-- Agent chat history
CREATE TABLE chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES compliance_assessments(id),
  user_id uuid REFERENCES auth.users(id),
  role text,
  content text,
  tool_used text,
  tool_result jsonb,
  created_at timestamptz DEFAULT now()
);

-- RLS: all tables enforce user_id = auth.uid()
```

---

## 13. Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Frontend | Next.js 16 (App Router) + TypeScript | File-based routing, server components |
| Styling | Tailwind CSS v4 | Utility-first, rapid iteration |
| Animations | Framer Motion | Risk card transitions, finding card reveals |
| Backend | FastAPI + Uvicorn (Python 3.12) | Async, auto-docs, ML-native |
| ML | XGBoost + Cosine Similarity | Proven, fast, explainable |
| LLM | Gemma via Ollama (local) → OpenAI → Gemini fallback | Privacy-first, no data leaves device |
| Database | Supabase (PostgreSQL + RLS + Auth) | Zero infra, row-level security |
| Auth | Supabase Auth + JWT HS256 | Industry standard |
| Document Parsing | Gemma multimodal (text + base64 image) | On-device extraction |

---

## 14. Edge Cases Handled

| Edge Case | Handling |
|---|---|
| Entity with zero transaction history | Fallback to sector-only risk scoring, flags as "Insufficient Data" |
| Director name on PEP/sanctions list | `director_pep_match` flag → auto-escalates to Critical tier regardless of other scores |
| Structuring pattern (smurfing) | Detected via `structuring_pattern` flag — highest imprisonment risk scenario |
| Cross-border txns without FEMA registration | `cross_border_unregistered` flag → FEMA-001 rule auto-triggered |
| Dormant account sudden spike | `dormant_account_spike` flag → triggers AML-007 rule |
| Invoice amount ≠ bank credit | `invoice_mismatch` flag → triggers IT-004 (under-reporting income) |
| Entity near but not over threshold | `threshold_sim` tool — shows exactly how many more transactions breach the rule |
| Multiple rules breached simultaneously | All rules ranked and shown; total penalty exposure is sum of all, not just top 1 |
| Gemma LLM unavailable | Full fallback chain: Ollama → OpenAI → Gemini → hardcoded rule-based response |
| Incomplete document extraction | Amber confidence indicators on affected fields; user must confirm before pipeline runs |
| Repeat offence detection | `aggravating_multiplier` in penalty sim increases fine up to 3× for repeat breaches |
| Shell company indicators | Composite flag: no employees + high turnover + single director → auto Critical |

---

## 15. Implementation Phases

### Phase 1 — Backend Core (Day 1)
- [ ] `anomaly_scorer.py` — 12 flag types, Gemma scoring, cache layer
- [ ] `rules_db.py` — 40 compliance rules with ideal_risk_vectors
- [ ] `scorer.py` — 6-factor compliance gap scorer + cosine ranker
- [ ] `penalty_simulator.py` — 10 violation scenarios with fine calculation logic
- [ ] `main.py` — all 12 API endpoints with Pydantic models
- [ ] `generate_dataset.py` — 80,000 synthetic SME records

### Phase 2 — ML Training (Day 1 afternoon)
- [ ] Run `generate_dataset.py` → `sme_compliance_dataset.csv`
- [ ] Run `train_model.py` → new `risk_model.json` + `label_encoder.pkl`
- [ ] Validate: accuracy target >85%, Critical tier recall >90%

### Phase 3 — Agent (Day 2 morning)
- [ ] `agent.py` — 7 tools, intent classifier (regex + Gemma hybrid)
- [ ] Update intent patterns for financial compliance domain
- [ ] `generate_report` tool — Gemma structured report generation

### Phase 4 — Frontend (Day 2)
- [ ] 5-step intake form with document upload
- [ ] Privacy review screen (extracted values, confidence indicators)
- [ ] Dashboard — risk card, finding cards, penalty banner
- [ ] Penalty simulator page
- [ ] Entity comparison table
- [ ] Report page (print-ready layout)
- [ ] Agent chat bar

### Phase 5 — Integration + Polish (Day 3)
- [ ] Supabase schema + RLS policies
- [ ] End-to-end test: upload bank statement → extract → assess → report
- [ ] Edge case validation (PEP match, structuring, dormant spike)
- [ ] Demo data: 3 pre-loaded entities (Low / High / Critical risk profiles)
- [ ] Demo walkthrough recording

---

## 16. Demo Script (Judging Panel)

1. **Login** as compliance officer
2. **Upload** a bank statement PDF for "Apex Realty Pvt Ltd" (real estate sector)
3. Gemma **extracts** cash_ratio=62%, monthly_txn_volume=340, cross_border_ratio=18%
4. **Privacy screen** — review extracted values, confirm
5. **Dashboard loads** — Critical risk tier, 87% confidence
   - Top findings: AML-001 (CTR breach), AML-005 (structuring pattern), FEMA-001 (unreported remittance)
   - Total penalty exposure: ₹42,00,000
6. **Agent chat** — "What if the cash ratio drops to 30%?"
   - Agent re-runs pipeline → risk drops to High, penalty exposure drops to ₹18,00,000
7. **Penalty simulator** — run "Structuring (Smurfing)" scenario → ₹1Cr fine + 7yr imprisonment risk
8. **Compare** Apex Realty vs a Low-risk IT company side by side
9. **Generate Report** → full audit-ready PDF-structured report with remediation steps
10. Analyst **signs off** on report → saved to Supabase

---

*FinTriage AI — Built for Hackathon 18 July 2026 | Track 2: Gemma Financial Compliance & Risk Triage*
