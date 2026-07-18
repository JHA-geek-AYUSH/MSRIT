---
inclusion: always
---

# Track 2 — Gemma Financial Compliance & Risk Triage

## Project Context

This workspace contains **GemmaFinOS** — a Financial Compliance & Risk Triage Platform powered by Google Gemma.

## Architecture

### Backend agents (new, `backend/app/agents/`)
| Agent | File | Purpose |
|---|---|---|
| TransactionAgent | `transaction_agent.py` | AML/CFT anomaly detection, structuring, round-trip |
| OnboardingAgent | `onboarding_agent.py` | KYC/KYB document gaps, PEP/sanctions, UBO |
| RegulatoryAgent | `regulatory_agent.py` | Framework mapping (PMLA, FEMA, RBI, SEBI, IBC) |
| FinancialRiskAgent | `financial_risk_agent.py` | Credit, market, liquidity, operational risk |
| ReportAgent | `report_agent.py` | Synthesises all findings into compliance-ready report |

### API endpoint
`POST /v1/compliance/triage` — runs selected agents in parallel, returns risk scorecard + full report.

### Gemma integration (`backend/app/core/gemma_client.py`)
- Set `USE_GEMMA=true` and `GEMMA_API_KEY=<Google AI Studio key>` in `.env`
- Uses Google's OpenAI-compatible endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/`
- Default model: `gemma-3-27b-it`
- Falls back to OpenAI when `USE_GEMMA=false`

### Frontend pages (new)
- `/compliance` — main triage page with mode selector + results
- `/compliance/history` — session-scoped run history

### Frontend components (`frontend/components/compliance/`)
- `RiskBadge`, `RiskScorecard`, `ComplianceReport`, `AlertBanner`, `RecommendationsList`, `TriageForm`

## Coding Standards

- All new backend agents follow `app/agents/base.py` `AgentOutput` TypedDict
- All LLM calls go through `get_llm_client()` / `get_llm_model()` from `gemma_client.py`
- Agents run with `asyncio.gather` in `compliance.py` — keep agent `run()` methods async
- PII is always redacted before any LLM call (uses existing `redact_user_input`)
- Indian regulatory context: PMLA 2002, FEMA 1999, RBI KYC Master Direction 2016, SEBI PIT Regs

## Key env vars (backend/.env)
```
USE_GEMMA=true/false
GEMMA_API_KEY=...
GEMMA_MODEL=gemma-3-27b-it
GEMMA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```
