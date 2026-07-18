from __future__ import annotations
from typing import Any, Dict
import structlog
from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput

log = structlog.get_logger()


class GrowthAdvisoryAgent:
    """Track 3 — SME Growth & Advisory: pricing, revenue forecasting, supplier management,
    collections, operational planning, and strategic business growth."""
    name = "growth_advisory"

    async def run(self, query: str, context: Dict[str, Any] = None) -> AgentOutput:
        log.info("growth_advisory_agent.start", query_length=len(query))
        client = get_llm_client_or_none()
        if not client:
            return AgentOutput(
                reasoning="Growth advisory unavailable: No LLM API key configured. Set OPENAI_API_KEY or GEMMA_API_KEY in .env",
                sources=[],
                confidence=0.1
            )

        ctx_str = f"\nAdditional context: {context}" if context else ""

        prompt = f"""You are a senior SME business growth advisor with deep expertise in Indian markets.

Business description / query:
{query}{ctx_str}

Provide a comprehensive growth advisory covering:

## 1. Pricing Strategy
- Current pricing assessment
- Competitive positioning
- Recommended pricing adjustments with rationale
- Value-based pricing opportunities

## 2. Revenue Forecasting (12-Month Outlook)
- Conservative / Base / Optimistic scenarios
- Key revenue drivers
- Growth rate assumptions
- Milestone targets

## 3. Supplier Management
- Supplier concentration risk
- Negotiation leverage points
- Alternative sourcing recommendations
- Payment term optimisation

## 4. Collections Optimisation
- Receivables aging analysis
- Collection efficiency improvements
- Credit policy recommendations
- Bad debt prevention

## 5. Operational Planning
- Capacity utilisation
- Cost reduction opportunities
- Process automation candidates
- Headcount planning

## 6. Strategic Growth Roadmap
1. Quick wins (0-3 months)
2. Growth initiatives (3-12 months)
3. Scale-up strategy (12-24 months)

Tailor all advice to Indian SME context including GST implications, MSME schemes, government incentives, and local market dynamics."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1200,
            )
            reasoning = resp.choices[0].message.content or "Advisory unavailable."
        except Exception as e:
            log.error("growth_advisory_agent.llm_error", error=str(e))
            reasoning = f"Growth advisory unavailable: {str(e)}"

        return AgentOutput(reasoning=reasoning, sources=[], confidence=0.80)
