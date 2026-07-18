from __future__ import annotations

import re
from typing import Any, Dict, List
import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput

log = structlog.get_logger()


class OnboardingAgent:
    """Validates KYC/KYB documents, assesses customer risk, and flags onboarding issues."""
    name = "onboarding"

    # Required KYC documents for individuals (India)
    INDIVIDUAL_DOCS = {"pan", "aadhaar", "passport", "voter_id", "driving_license"}
    ENTITY_DOCS = {"certificate_of_incorporation", "pan", "gst", "board_resolution", "ubo_declaration"}

    async def run(
        self,
        query: str,
        packs: List[Dict[str, Any]],
        matter_docs: List[Dict[str, Any]],
    ) -> AgentOutput:
        log.info("onboarding_agent.start")

        doc_gaps = self._check_document_gaps(matter_docs)
        risk_level = self._assess_customer_risk(query, matter_docs)
        pep_flags = self._check_pep_sanctions(query, matter_docs)
        ubo_issues = self._check_ubo(matter_docs)

        reasoning = await self._analyze(query, doc_gaps, risk_level, pep_flags, ubo_issues, packs)
        confidence = self._calc_confidence(doc_gaps, pep_flags, ubo_issues)

        log.info("onboarding_agent.complete", doc_gaps=len(doc_gaps), risk_level=risk_level)
        return AgentOutput(reasoning=reasoning, sources=[], confidence=confidence)

    def _check_document_gaps(self, docs: List[Dict[str, Any]]) -> List[str]:
        text = " ".join(str(d.get("content", "")).lower() for d in docs)
        gaps = []
        mandatory = {"pan", "aadhaar"}
        for doc_type in mandatory:
            if doc_type not in text:
                gaps.append(doc_type.upper())
        return gaps

    def _assess_customer_risk(self, query: str, docs: List[Dict[str, Any]]) -> str:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        high_risk_kws = ["pep", "sanctioned", "offshore", "cash-intensive", "high-value", "politically exposed"]
        medium_risk_kws = ["nri", "foreign national", "trust", "nominee", "new business"]
        if any(k in text for k in high_risk_kws):
            return "high"
        if any(k in text for k in medium_risk_kws):
            return "medium"
        return "low"

    def _check_pep_sanctions(self, query: str, docs: List[Dict[str, Any]]) -> List[str]:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        flags = []
        kws = ["pep", "politically exposed", "sanction", "ofac", "un list", "interpol", "fatf grey list"]
        for kw in kws:
            if kw in text:
                flags.append(kw)
        return flags

    def _check_ubo(self, docs: List[Dict[str, Any]]) -> List[str]:
        text = " ".join(str(d.get("content", "")).lower() for d in docs)
        issues = []
        if "ubo" not in text and "beneficial owner" not in text:
            issues.append("UBO declaration missing")
        if re.search(r"25\s*%|twenty.?five\s*percent", text) is None:
            issues.append("25% UBO threshold not addressed")
        return issues

    async def _analyze(
        self,
        query: str,
        doc_gaps: List[str],
        risk_level: str,
        pep_flags: List[str],
        ubo_issues: List[str],
        packs: List[Dict[str, Any]],
    ) -> str:
        client = get_llm_client_or_none()
        if not client:
            return f"Onboarding review (offline):\nCustomer risk level: {risk_level.upper()}"

        ctx_parts = [f"Customer risk level: {risk_level.upper()}"]
        if doc_gaps:
            ctx_parts.append(f"Missing documents: {', '.join(doc_gaps)}")
        if pep_flags:
            ctx_parts.append(f"PEP/Sanctions flags: {', '.join(pep_flags)}")
        if ubo_issues:
            ctx_parts.append(f"UBO issues: {'; '.join(ubo_issues)}")

        context = "\n".join(ctx_parts)

        prompt = f"""You are a KYC/AML compliance specialist (Indian regulatory framework: RBI KYC Master Direction 2016, PMLA 2002).

Onboarding context:
{query}

Compliance findings:
{context}

Provide a structured KYC/onboarding compliance report:
1. **Customer Risk Classification** – CDD / EDD / SDD recommendation
2. **Document Completeness** – gaps and remediation required
3. **PEP & Sanctions Check** – findings and required actions
4. **UBO Verification** – beneficial ownership status
5. **Onboarding Decision** – Approve / Conditional Approval / Reject / Escalate
6. **Ongoing Monitoring** – review frequency and triggers

Be precise and reference applicable RBI/PMLA guidelines where relevant."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=850,
            )
            return resp.choices[0].message.content or "Analysis unavailable."
        except Exception as e:
            log.error("onboarding_agent.llm_error", error=str(e))
            return f"Onboarding review (offline):\n{context}"

    def _calc_confidence(self, doc_gaps, pep_flags, ubo_issues) -> float:
        base = 0.55
        base += 0.1 if pep_flags else 0
        base += 0.05 * min(3, len(doc_gaps))
        base += 0.05 if ubo_issues else 0
        return min(0.90, base)
