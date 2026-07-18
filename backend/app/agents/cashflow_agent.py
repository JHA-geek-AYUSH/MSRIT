from __future__ import annotations
from typing import Any, Dict, List
import structlog
from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput

log = structlog.get_logger()


class CashflowAgent:
    """Track 1 — SME Cashflow Copilot: forecasts cash flow, identifies liquidity risks,
    automates invoice follow-ups, optimises payment schedules."""
    name = "cashflow"

    async def run(self, query: str, context: Dict[str, Any] = None) -> AgentOutput:
        log.info("cashflow_agent.start", query_length=len(query))
        client = get_llm_client_or_none()
        if not client:
            return AgentOutput(
                reasoning="Cashflow analysis unavailable: No LLM API key configured. Set OPENAI_API_KEY or GEMMA_API_KEY in .env",
                sources=[],
                confidence=0.1
            )

        ctx_str = ""
        if context:
            ctx_str = f"\nAdditional context: {context}"

        prompt = f"""You are an expert SME financial advisor and cashflow analyst for Indian businesses.

Business description / query:
{query}{ctx_str}

Provide a comprehensive cashflow analysis covering:

## 1. Cash Flow Forecast (Next 90 Days)
- Projected inflows (receivables, revenue)
- Projected outflows (payables, salaries, taxes, EMIs)
- Net cash position by month

## 2. Liquidity Risk Assessment
- Current ratio analysis
- Days Sales Outstanding (DSO) estimate
- Working capital gap
- Risk level: High / Medium / Low

## 3. Invoice Follow-Up Recommendations
- Overdue invoices to prioritise
- Suggested follow-up schedule
- Escalation triggers

## 4. Payment Schedule Optimisation
- Vendor payment timing recommendations
- Early payment discount opportunities
- Cash conversion cycle improvement

## 5. Actionable Decisions
1. Immediate (this week)
2. Short-term (this month)
3. Strategic (next quarter)

Be specific, use INR figures where relevant, and tailor advice to Indian SME context (GST, TDS, MSME regulations)."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1200,
            )
            reasoning = resp.choices[0].message.content or "Analysis unavailable."
        except Exception as e:
            log.error("cashflow_agent.llm_error", error=str(e))
            reasoning = f"Cashflow analysis unavailable: {str(e)}"

        return AgentOutput(reasoning=reasoning, sources=[], confidence=0.82)
