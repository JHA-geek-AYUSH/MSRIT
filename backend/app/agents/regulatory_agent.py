from __future__ import annotations

import re
from typing import Any, Dict, List
import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput
from app.ml.compliance_scorer import score_compliance_gaps
from app.ml.risk_model_runner import extract_financial_features

log = structlog.get_logger()


# Regulatory framework reference table
FRAMEWORKS = {
    "PMLA": {
        "full_name": "Prevention of Money Laundering Act, 2002",
        "triggers": ["money laundering", "proceeds of crime", "aml", "suspicious transaction", "str"],
    },
    "FEMA": {
        "full_name": "Foreign Exchange Management Act, 1999",
        "triggers": ["foreign exchange", "fdi", "fpi", "odi", "ecb", "remittance", "repatriation"],
    },
    "RBI_KYC": {
        "full_name": "RBI KYC Master Direction, 2016",
        "triggers": ["kyc", "cdd", "edd", "customer due diligence", "periodic update"],
    },
    "SEBI": {
        "full_name": "SEBI (Prohibition of Insider Trading) Regulations, 2015",
        "triggers": ["insider trading", "upsi", "trading window", "unpublished price sensitive"],
    },
    "INCOME_TAX": {
        "full_name": "Income Tax Act, 1961",
        "triggers": ["income tax", "tds", "advance tax", "black money", "undisclosed income"],
    },
    "IBC": {
        "full_name": "Insolvency and Bankruptcy Code, 2016",
        "triggers": ["insolvency", "bankruptcy", "resolution plan", "liquidation", "nclt"],
    },
    "COMPANIES_ACT": {
        "full_name": "Companies Act, 2013",
        "triggers": ["company", "director", "shareholder", "board", "related party", "mca"],
    },
    "FATF": {
        "full_name": "FATF 40 Recommendations",
        "triggers": ["fatf", "international", "correspondent banking", "de-risking"],
    },
}


class RegulatoryAgent:
    """Maps compliance findings to applicable regulatory frameworks and breach severity."""
    name = "regulatory"

    async def run(
        self,
        query: str,
        packs: List[Dict[str, Any]],
        matter_docs: List[Dict[str, Any]],
    ) -> AgentOutput:
        log.info("regulatory_agent.start")

        # 1. Deterministic Cosine Similarity Score (Stages 2 & 3)
        features = extract_financial_features(query, matter_docs)
        gap_scores = score_compliance_gaps(features)

        # 2. Text heuristics
        applicable = self._identify_frameworks(query, matter_docs)
        breaches = self._identify_potential_breaches(query, applicable)
        penalties = self._assess_penalties(breaches)

        reasoning = await self._analyze(query, applicable, breaches, penalties, gap_scores, packs)
        confidence = self._calc_confidence(applicable, breaches) + min(0.3, len(gap_scores) * 0.1)
        confidence = min(0.95, confidence)

        log.info("regulatory_agent.complete", frameworks=len(applicable), gaps=len(gap_scores))
        return AgentOutput(reasoning=reasoning, sources=[], confidence=confidence)

    def _identify_frameworks(self, query: str, docs: List[Dict[str, Any]]) -> List[str]:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        applicable = []
        for code, info in FRAMEWORKS.items():
            if any(trigger in text for trigger in info["triggers"]):
                applicable.append(code)
        return applicable

    def _identify_potential_breaches(self, query: str, frameworks: List[str]) -> List[Dict[str, Any]]:
        text = query.lower()
        breaches = []
        breach_patterns = [
            (r"fail(?:ed|ure)\s+to\s+(?:report|file|submit|disclose)", "reporting_failure"),
            (r"non-?compliance|violat(?:ed|ion)|breach", "non_compliance"),
            (r"unauthoris(?:ed|ed)|without\s+(?:approval|permission)", "unauthorised_activity"),
            (r"false\s+statement|misrepresent|suppress\s+information", "misrepresentation"),
            (r"exceed(?:ed|ing)\s+(?:limit|threshold|cap)", "limit_breach"),
        ]
        for pattern, breach_type in breach_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                breaches.append({"type": breach_type, "severity": self._breach_severity(breach_type)})
        return breaches

    def _breach_severity(self, breach_type: str) -> str:
        high = {"misrepresentation", "unauthorised_activity"}
        medium = {"reporting_failure", "non_compliance"}
        return "high" if breach_type in high else ("medium" if breach_type in medium else "low")

    def _assess_penalties(self, breaches: List[Dict[str, Any]]) -> Dict[str, str]:
        if not breaches:
            return {}
        max_severity = max((b["severity"] for b in breaches), key=lambda s: {"high": 2, "medium": 1, "low": 0}.get(s, 0))
        penalty_map = {
            "high": "Imprisonment up to 7 years (PMLA) / Compounding up to 3× transaction value (FEMA) / Disgorgement + penalty (SEBI)",
            "medium": "Monetary penalty up to ₹50L / License suspension / Regulatory censure",
            "low": "Warning / Compounding / Minor fine",
        }
        return {"max_severity": max_severity, "indicative_penalty": penalty_map.get(max_severity, "N/A")}

    async def _analyze(
        self,
        query: str,
        frameworks: List[str],
        breaches: List[Dict[str, Any]],
        penalties: Dict[str, str],
        gap_scores: List[Dict[str, Any]],
        packs: List[Dict[str, Any]],
    ) -> str:
        client = get_llm_client_or_none()
        if not client:
            return f"Regulatory analysis (offline):\nFrameworks: {', '.join(frameworks)}"

        fw_lines = "\n".join(f"• {f}: {FRAMEWORKS[f]['full_name']}" for f in frameworks) or "None identified"
        breach_lines = "\n".join(f"• {b['type']} ({b['severity']})" for b in breaches) or "No specific breaches detected"
        penalty_line = penalties.get("indicative_penalty", "N/A")
        
        gap_lines = "\n".join(f"• {g['rule_code']} ({g['framework']}): {g['rule_name']} (Sim: {g['similarity_score']}, Gap: {g['gap_score']})" for g in gap_scores) or "No major gaps detected."

        prompt = f"""You are a financial regulatory compliance expert (India).

Matter description:
{query}

Applicable regulatory frameworks:
{fw_lines}

Potential breach indicators (Heuristics):
{breach_lines}

Cosine Similarity Gap Analysis (ML Stages 2 & 3):
{gap_lines}

Indicative penalty exposure: {penalty_line}

Generate a regulatory compliance assessment:
1. **Framework Analysis** – how each applicable law applies to this matter
2. **Breach Assessment** – severity and likelihood of regulatory action
3. **Penalty Exposure** – potential fines, imprisonment, or licence revocation
4. **Compliance Gaps** – specific requirements not met
5. **Remediation Plan** – steps to achieve compliance
6. **Voluntary Disclosure** – whether self-reporting is advisable

Reference specific sections/regulations where applicable. Be actionable."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=950,
            )
            return resp.choices[0].message.content or "Analysis unavailable."
        except Exception as e:
            log.error("regulatory_agent.llm_error", error=str(e))
            return f"Regulatory analysis (offline):\nFrameworks: {', '.join(frameworks)}"

    def _calc_confidence(self, frameworks: List[str], breaches: List[Dict[str, Any]]) -> float:
        base = 0.50
        base += min(0.25, len(frameworks) * 0.05)
        base += min(0.15, len(breaches) * 0.05)
        return min(0.90, base)
