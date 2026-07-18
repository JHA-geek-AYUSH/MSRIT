from __future__ import annotations

import re
from typing import Any, Dict, List
import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.agents.base import AgentOutput
from app.ml.risk_model_runner import extract_financial_features, predict_risk_tier

log = structlog.get_logger()


class FinancialRiskAgent:
    """Assesses financial risk across credit, market, liquidity, and operational dimensions."""
    name = "financial_risk"

    async def run(
        self,
        query: str,
        packs: List[Dict[str, Any]],
        matter_docs: List[Dict[str, Any]],
    ) -> AgentOutput:
        log.info("financial_risk_agent.start")

        # 1. Extract heuristic features
        features = extract_financial_features(query, matter_docs)

        # 2. Add some heuristics for credit/market/liquidity to augment features
        credit_risk = self._assess_credit_risk(query, matter_docs)
        market_risk = self._assess_market_risk(query)
        liquidity_risk = self._assess_liquidity_risk(query, matter_docs)
        op_risk = self._assess_operational_risk(query, matter_docs)

        # 3. XGBoost prediction (Stage 1)
        pred = predict_risk_tier(features)

        reasoning = await self._analyze(query, credit_risk, market_risk, liquidity_risk, op_risk, pred, features, packs)
        confidence = pred["confidence"]

        log.info("financial_risk_agent.complete", predicted_tier=pred["tier"], confidence=confidence)
        return AgentOutput(reasoning=reasoning, sources=[], confidence=confidence)

    def _assess_credit_risk(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        indicators = []
        high_kws = ["default", "npa", "npa account", "bankruptcy", "insolvency", "write-off", "stressed asset"]
        medium_kws = ["overdue", "delay", "restructure", "moratorium", "renegotiate", "watch list"]
        for k in high_kws:
            if k in text:
                indicators.append(k)
        level = "high" if any(k in text for k in high_kws) else ("medium" if any(k in text for k in medium_kws) else "low")
        return {"level": level, "indicators": indicators}

    def _assess_market_risk(self, query: str) -> Dict[str, Any]:
        text = query.lower()
        factors = []
        kws = {
            "volatility": "price_volatility",
            "exchange rate": "fx_risk",
            "interest rate": "interest_rate_risk",
            "commodity": "commodity_risk",
            "equity": "equity_risk",
        }
        for kw, risk_type in kws.items():
            if kw in text:
                factors.append(risk_type)
        return {"factors": factors, "level": "high" if len(factors) >= 3 else ("medium" if factors else "low")}

    def _assess_liquidity_risk(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        signals = []
        kws = ["cash crunch", "liquidity", "illiquid", "frozen funds", "redemption pressure", "margin call"]
        for k in kws:
            if k in text:
                signals.append(k)
        return {"signals": signals, "level": "high" if len(signals) >= 2 else ("medium" if signals else "low")}

    def _assess_operational_risk(self, query: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = (query + " " + " ".join(str(d.get("content", "")) for d in docs)).lower()
        events = []
        kws = ["fraud", "cyber", "data breach", "system failure", "process failure", "human error", "misconduct"]
        for k in kws:
            if k in text:
                events.append(k)
        return {"events": events, "level": "high" if events else "low"}

    async def _analyze(
        self,
        query: str,
        credit: Dict[str, Any],
        market: Dict[str, Any],
        liquidity: Dict[str, Any],
        op: Dict[str, Any],
        pred: Dict[str, Any],
        features: Dict[str, float],
        packs: List[Dict[str, Any]],
    ) -> str:
        ctx = (
            f"XGBoost Risk Tier: {pred['tier'].upper()} (Confidence: {pred['confidence']:.2f})\n"
            f"Extracted Features: Cash Ratio={features.get('cash_ratio')}, Cross Border={features.get('cross_border_ratio')}\n"
            f"Credit risk indicators: {', '.join(credit['indicators']) or 'none'}\n"
            f"Market risk factors: {', '.join(market['factors']) or 'none'}\n"
            f"Liquidity risk signals: {', '.join(liquidity['signals']) or 'none'}\n"
            f"Operational risk events: {', '.join(op['events']) or 'none'}"
        )

        client = get_llm_client_or_none()
        if not client:
            return f"Financial risk analysis (offline):\n{ctx}"

        prompt = f"""You are a financial risk analyst specialising in Indian banking and capital markets.

Matter/document context:
{query}

Risk assessment signals:
{ctx}

Provide a comprehensive financial risk report:
1. **Overall Risk Rating** – composite score (High/Medium/Low) with rationale
2. **Credit Risk Analysis** – NPA likelihood, counterparty exposure, collateral adequacy
3. **Market Risk Analysis** – price, FX, interest rate, and concentration risk
4. **Liquidity Risk Analysis** – short-term funding gaps, asset-liability mismatch
5. **Operational Risk Analysis** – fraud, process, and technology risks
6. **Risk Mitigation Recommendations** – hedging, diversification, provisioning
7. **Regulatory Capital Implications** – Basel III / RBI ICAAP considerations

Be quantitative where possible and reference RBI/SEBI/Basel guidelines."""

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=950,
            )
            return resp.choices[0].message.content or "Analysis unavailable."
        except Exception as e:
            log.error("financial_risk_agent.llm_error", error=str(e))
            return f"Financial risk analysis (offline):\n{ctx}"

    def _calc_confidence(self, credit, market, liquidity) -> float:
        levels = [credit["level"], market["level"], liquidity["level"]]
        score_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
        avg = sum(score_map.get(l, 0.5) for l in levels) / len(levels)
        return round(min(0.90, avg), 2)
