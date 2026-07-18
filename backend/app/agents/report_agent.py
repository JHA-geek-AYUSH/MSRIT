from __future__ import annotations

from typing import Any, Dict, List
import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput

log = structlog.get_logger()


class ReportAgent:
    """Synthesises findings from all compliance agents into a compliance-ready report."""
    name = "report"

    async def run(
        self,
        query: str,
        packs: List[Dict[str, Any]],
        matter_docs: List[Dict[str, Any]],
        agent_outputs: Dict[str, AgentOutput] | None = None,
    ) -> AgentOutput:
        log.info("report_agent.start")

        summary = self._build_summary(agent_outputs or {})
        reasoning = await self._generate_report(query, summary, packs)

        log.info("report_agent.complete")
        return AgentOutput(reasoning=reasoning, sources=[], confidence=0.85)

    def _build_summary(self, agent_outputs: Dict[str, AgentOutput]) -> str:
        lines = []
        for agent_name, output in agent_outputs.items():
            if agent_name == "report":
                continue
            lines.append(f"### {agent_name.replace('_', ' ').title()} Agent\n{output.get('reasoning', '')[:600]}")
        return "\n\n".join(lines) if lines else "No prior agent findings available."

    async def _generate_report(self, query: str, summary: str, packs: List[Dict[str, Any]]) -> str:
        client = get_llm_client_or_none()
        if not client:
            return f"Report (offline):\n{summary[:1000]}"

        prompt = f"""You are a senior compliance officer generating a formal compliance review report.

Subject matter:
{query}

Agent findings summary:
{summary[:3000]}

Generate a comprehensive, compliance-ready report with the following structure:

---
## COMPLIANCE & RISK TRIAGE REPORT

### Executive Summary
[2-3 sentence high-level summary of overall compliance posture]

### Risk Scorecard
| Risk Domain | Rating | Key Finding |
|-------------|--------|-------------|
[Fill in rows for each domain: AML/CFT, KYC/Onboarding, Regulatory, Financial, Operational]

### Critical Findings
[List each high-severity finding with remediation priority]

### Regulatory Obligations
[Summary of mandatory actions under applicable laws]

### Recommended Actions (Prioritised)
1. Immediate (within 24 hours)
2. Short-term (within 7 days)
3. Medium-term (within 30 days)

### Disclosure & Reporting Requirements
[STR filing, regulator notifications, board reporting]

### Conclusion & Sign-off
[Overall compliance verdict: Satisfactory / Requires Attention / Non-Compliant]
---

Make the report professional, factual, and suitable for submission to a compliance committee."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1400,
            )
            return resp.choices[0].message.content or "Report generation failed."
        except Exception as e:
            log.error("report_agent.llm_error", error=str(e))
            return f"Report (offline):\n{summary[:1000]}"
