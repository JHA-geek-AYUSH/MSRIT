from typing import Dict, Any, List
import structlog
import json
from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.ml.risk_model_runner import extract_financial_features, predict_risk_tier
from app.ml.compliance_scorer import score_compliance_gaps

log = structlog.get_logger()

class ComplianceOrchestrator:
    """Master agent that parses natural language intent and dispatches to tools."""
    name = "orchestrator"

    async def chat(self, user_query: str, session_context: Dict[str, Any]) -> str:
        log.info("orchestrator.chat.start", query=user_query)
        client = get_llm_client_or_none()
        if not client:
            return "No Gemma provider is configured. Start Ollama with Gemma or set GEMMA_API_KEY."

        # Step 1: Intent parsing
        system_prompt = """
        You are the GemmaFinOS Compliance Orchestrator.
        Given the user's message and current session context, determine the intent.
        Intents:
        1. 'penalty_sim': User wants to run a what-if scenario (e.g. "what if cash ratio doubles?").
        2. 'explain_risk': User wants an explanation of why a specific risk tier was assigned.
        3. 'general_chat': General questions about compliance.
        
        Output ONLY valid JSON:
        {
           "intent": "penalty_sim" | "explain_risk" | "general_chat",
           "parameters": {
               "what_if": "extracted scenario string if penalty_sim"
           }
        }
        """

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            intent = parsed.get("intent", "general_chat")
            params = parsed.get("parameters", {})
        except Exception as e:
            log.error("orchestrator.intent_parse_failed", error=str(e))
            intent = "general_chat"
            params = {}

        # Step 2: Dispatch
        if intent == "penalty_sim":
            base_desc = session_context.get("last_triage_description", "")
            if not base_desc:
                return "I cannot run a penalty simulation without an active triage session."

            what_if = params.get("what_if", user_query)
            base_features = extract_financial_features(base_desc)
            base_pred = predict_risk_tier(base_features)
            base_gaps = score_compliance_gaps(base_features)

            sim_features = base_features.copy()
            wl = what_if.lower()
            if "double" in wl and "cash" in wl:
                sim_features["cash_ratio"] = min(1.0, sim_features.get("cash_ratio", 0) * 2)
            elif "pep" in wl or "sanction" in wl:
                sim_features["anomaly_risk_score"] = min(5.0, sim_features.get("anomaly_risk_score", 0) + 3.0)
            sim_pred = predict_risk_tier(sim_features)
            sim_gaps = score_compliance_gaps(sim_features)

            tier_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            b, s = tier_map.get(base_pred["tier"], 2), tier_map.get(sim_pred["tier"], 2)
            impact = "Risk Increased" if s > b else ("Risk Mitigated" if s < b else "Risk Unchanged")
            return (f"**Penalty Simulation Result:**\n\n"
                    f"- **Baseline Risk Tier:** {base_pred['tier'].upper()} ({len(base_gaps)} gaps)\n"
                    f"- **Simulated Risk Tier:** {sim_pred['tier'].upper()} ({len(sim_gaps)} gaps)\n\n"
                    f"**Impact:** {impact}")

        elif intent == "explain_risk":
            report = session_context.get("last_report", "No report found.")
            prompt = f"Explain the key drivers behind the risk assessment in this report simply: {report}"
            if client:
                explanation = client.chat.completions.create(
                    model=get_llm_model(),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                return explanation.choices[0].message.content or "Could not generate explanation."
            return f"LLM not configured. Report context: {report[:100]}"

        else:
            # General Chat
            prompt = f"You are GemmaFinOS, an Indian financial compliance AI assistant. Answer the user based on context: {json.dumps(session_context)}. User query: {user_query}"
            if client:
                general_resp = client.chat.completions.create(
                    model=get_llm_model(),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4
                )
                return general_resp.choices[0].message.content or "Could not respond."
            return f"LLM not configured. Context: {json.dumps(session_context)[:200]}. Query: {user_query}"
