from __future__ import annotations

import re
from typing import Any, Dict, List
import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput
from app.ml.anomaly_scorer import score_anomalies

log = structlog.get_logger()


class TransactionAgent:
    """Analyzes financial transactions for anomalies, suspicious patterns, and AML/CFT risks."""
    name = "transaction"

    # Risk thresholds (INR)
    HIGH_VALUE_THRESHOLD = 10_00_000   # 10 lakhs
    STRUCTURING_THRESHOLD = 10_00_000  # Potential structuring below this
    ROUND_TRIP_WINDOW_DAYS = 30

    async def run(
        self,
        query: str,
        packs: List[Dict[str, Any]],
        matter_docs: List[Dict[str, Any]],
    ) -> AgentOutput:
        log.info("transaction_agent.start", query_length=len(query))

        # Collect basic flags
        anomalies = self._detect_anomalies(query, matter_docs)
        structuring = self._detect_structuring(matter_docs)
        round_trip = self._detect_round_trip(matter_docs)
        high_risk = self._flag_high_risk_counterparties(query, matter_docs)

        # Consolidate strings for anomaly scorer
        detected_flags = []
        for a in anomalies:
            detected_flags.append(f"{a['category']}: {a['match']}")
        for s in structuring:
            detected_flags.append(s["description"])
        for r in round_trip:
            detected_flags.append(r["description"])
        for h in high_risk:
            detected_flags.append(f"High risk counterparty: {h}")

        # Run Stage 0 mathematical anomaly scoring
        anomaly_result = score_anomalies(detected_flags)

        reasoning = await self._analyze(query, anomaly_result, packs)
        confidence = 0.5 + min(0.4, anomaly_result["normalized_for_xgboost"] / 5.0)

        log.info("transaction_agent.complete", anomaly_score=anomaly_result["total_anomaly_score"], confidence=confidence)
        return AgentOutput(reasoning=reasoning, sources=[], confidence=confidence)

    # ──────────────────────────────────────────────────────────────────────
    def _detect_anomalies(self, query: str, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        patterns = [
            (r"(?:₹|INR|Rs\.?)\s*(\d[\d,]+)", "large_transfer"),
            (r"cash\s+(?:deposit|withdrawal|payment)", "cash_transaction"),
            (r"round.?trip|layering|smurfing|structur", "structuring"),
            (r"shell\s+company|offshore|tax\s+haven|hawala", "high_risk_entity"),
            (r"unusual|suspicious|irregular|anomal", "flagged_pattern"),
        ]
        text = query.lower()
        for doc in docs:
            text += " " + str(doc.get("content", "")).lower()

        for pattern, category in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                anomalies.append({"category": category, "match": m.group(0)[:80], "severity": self._severity(category)})
        return anomalies

    def _detect_structuring(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Look for multiple just-below-threshold transactions (structuring / smurfing)."""
        flags: List[Dict[str, Any]] = []
        amounts: List[float] = []
        for doc in docs:
            text = str(doc.get("content", ""))
            for m in re.finditer(r"(?:₹|INR|Rs\.?)\s*([\d,]+)", text):
                try:
                    val = float(m.group(1).replace(",", ""))
                    amounts.append(val)
                except ValueError:
                    pass

        below_threshold = [a for a in amounts if 8_00_000 <= a < self.STRUCTURING_THRESHOLD]
        if len(below_threshold) >= 3:
            flags.append({
                "type": "potential_structuring",
                "count": len(below_threshold),
                "description": f"{len(below_threshold)} transactions just below ₹10L threshold detected",
            })
        return flags

    def _detect_round_trip(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Very lightweight round-trip / layering heuristic."""
        flags: List[Dict[str, Any]] = []
        text = " ".join(str(d.get("content", "")) for d in docs).lower()
        if re.search(r"round.?trip|returned\s+funds|re-?credited|reversed\s+transfer", text):
            flags.append({"type": "round_trip_indicator", "description": "Potential round-trip / fund-layering pattern detected"})
        return flags

    def _flag_high_risk_counterparties(self, query: str, docs: List[Dict[str, Any]]) -> List[str]:
        high_risk_kws = ["sanctioned", "pep", "politically exposed", "ofac", "fatf", "watchlist", "blacklist", "debarred"]
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        return [kw for kw in high_risk_kws if kw in text]

    def _severity(self, category: str) -> str:
        mapping = {
            "high_risk_entity": "high",
            "structuring": "high",
            "cash_transaction": "medium",
            "large_transfer": "medium",
            "flagged_pattern": "low",
        }
        return mapping.get(category, "low")

    async def _analyze(
        self,
        query: str,
        anomaly_result: Dict[str, Any],
        packs: List[Dict[str, Any]],
    ) -> str:
        client = get_llm_client_or_none()
        if not client:
            return f"Transaction analysis (offline fallback):\nAnomaly Score: {anomaly_result['total_anomaly_score']}"

        context = f"Stage 0 Anomaly Score: {anomaly_result['total_anomaly_score']}\n"
        context += f"Summary: {anomaly_result['anomaly_summary']}\n"
        context += "Flags:\n"
        for f in anomaly_result.get("flags", []):
            context += f"- {f['name']} (Weight: {f['weight']} - {f['justification']})\n"

        prompt = f"""You are a financial crime compliance analyst specialising in AML/CFT (PMLA 2002, FEMA, RBI guidelines).

Transaction/document context:
{query}

Detected signals:
{context}

Provide a structured transaction risk assessment covering:
1. **Anomaly Summary** – key suspicious patterns found
2. **AML/CFT Risk Rating** – High / Medium / Low with justification
3. **Regulatory Triggers** – which PMLA / FEMA / RBI provisions may apply
4. **Recommended Actions** – STR filing, enhanced due-diligence, freezing, escalation
5. **Investigation Leads** – next steps for compliance team

Be concise, factual, and compliance-ready. Flag all red-flag indicators clearly."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=900,
            )
            return resp.choices[0].message.content or "Analysis unavailable."
        except Exception as e:
            log.error("transaction_agent.llm_error", error=str(e))
            return f"Transaction analysis (offline fallback):\n{context}"

    def _calc_confidence(self, anomalies, structuring, round_trip) -> float:
        base = 0.45
        base += min(0.25, len(anomalies) * 0.05)
        base += 0.1 if structuring else 0
        base += 0.1 if round_trip else 0
        return min(0.90, base)
