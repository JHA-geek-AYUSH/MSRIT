"""FinTriage AI — 7-tool conversational agent (Plan.md Section 7).

Intent Classifier (regex + Gemma hybrid) -> Tool Dispatcher -> Gemma response generation

This replaces app/agents/orchestrator.py, which only implemented 2 of the 7
required tools (penalty_sim, explain_risk) and re-implemented pipeline logic
inline instead of reusing app/ml/pipeline.py. orchestrator.py is left in place
for backward compatibility (nothing else calls it after this change) but new
code should import FinTriageAgent from here.

Tools:
  reassess        - re-run the pipeline with a modified feature (what-if)
  penalty_sim     - calculate regulatory fine exposure for a violation scenario
  threshold_sim   - find how far a feature is from crossing a rule's threshold
  compare         - side-by-side compliance comparison of 2-3 entities
  explain_risk    - plain-English explanation of the risk tier and its drivers
  rule_info       - full detail on a specific compliance rule
  generate_report - generate the 6-section structured audit report
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import structlog

from app.core.gemma_client import get_llm_client_or_none, get_llm_model
from app.ml.pipeline import parse_what_if, reassess_with_overrides, run_full_assessment
from app.ml.compliance_scorer import rank_all_rules
from app.ml.rules_db import COMPLIANCE_RULES, get_rule_by_code
from app.api.v1.simulator import SCENARIOS, PenaltySimRequest, run_penalty_simulation
from app.api.v1.report import build_report_sections, generate_gemma_narrative

log = structlog.get_logger()

TOOLS = ["reassess", "penalty_sim", "threshold_sim", "compare", "explain_risk", "rule_info", "generate_report", "external_action", "platform_help"]

# Regex-first intent classification (Plan.md Section 7 trigger phrases). Cheap,
# deterministic, and free — Gemma is only consulted when nothing matches.
_INTENT_PATTERNS: List[tuple[str, re.Pattern]] = [
    ("platform_help", re.compile(r"how does .* work|what happens if|what is fintriage|how (is|are) .* (calculated|computed|scored)|help me understand the platform", re.I)),
    ("external_action", re.compile(r"send (an? )?(email|message)|draft (an? )?(email|message)|reach out to|let .* know|notify|create (a |an )?task|post (to|in) slack|schedule a (meeting|call)", re.I)),
    ("compare", re.compile(r"\bcompare\b|\bvs\.?\b|side.by.side|difference between", re.I)),
    ("penalty_sim", re.compile(r"what fine|penalty for|how much would.*owe|worst case|run.*scenario", re.I)),
    ("threshold_sim", re.compile(r"cross(es|ing)? (a |the )?threshold|near threshold|if (transactions?|volume) (double|increase|cross)", re.I)),
    ("rule_info", re.compile(r"tell me about ([a-z]+-\d+)|details? on rule|what is (ctr|str|edd|aml-\d+|kyc-\d+|gst-\d+|fema-\d+|it-\d+|corp-\d+)", re.I)),
    ("generate_report", re.compile(r"generate.*report|create.*audit report|export findings", re.I)),
    ("explain_risk", re.compile(r"why (is it|am i)? ?high risk|explain (my|the) score|what drives|what caused", re.I)),
    ("reassess", re.compile(r"what if|update (the |my )?profile|add (a |the )?(structuring|flag)|increases?|decreases?|doubles?|drops? to", re.I)),
]

_RULE_CODE_RE = re.compile(r"\b([A-Z]{2,5}-\d{3})\b", re.I)

# Execution order for multi-intent messages (Req 5.5, 5.6).
# reassess must run first so downstream tools (compare, explain_risk) see
# the updated context produced by the what-if simulation.
_TOOL_EXECUTION_ORDER: List[str] = [
    "reassess",
    "penalty_sim",
    "threshold_sim",
    "compare",
    "explain_risk",
    "rule_info",
    "generate_report",
    "external_action",
]


def classify_intent_regex(message: str) -> Optional[str]:
    """Return the FIRST matching intent (legacy single-intent path)."""
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(message):
            return intent
    return None


def classify_all_intents_regex(message: str) -> List[str]:
    """Return ALL matching intents, preserving de-duplication (insertion order).

    The returned list is NOT yet sorted — callers sort by _TOOL_EXECUTION_ORDER.
    """
    seen: set = set()
    matched: List[str] = []
    for intent, pattern in _INTENT_PATTERNS:
        if intent not in seen and pattern.search(message):
            seen.add(intent)
            matched.append(intent)
    return matched


async def classify_intent_llm(message: str) -> str:
    client = get_llm_client_or_none()
    if not client:
        return "explain_risk"  # safest default with an LLM-free fallback path
    system_prompt = (
        "Classify the user's message into exactly one of these intents: "
        f"{', '.join(TOOLS)}, or general_chat. "
        "Output ONLY valid JSON: {\"intent\": \"...\"}"
    )
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
            temperature=0.0,
            max_tokens=30,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        intent = parsed.get("intent", "general_chat")
        return intent if intent in TOOLS else "general_chat"
    except Exception as e:
        log.warning("agent.llm_intent_failed", error=str(e))
        return "general_chat"


class FinTriageAgent:
    """Stateless per-call; all state comes from session_context so it can be
    persisted/reloaded across HTTP requests (see app/api/v1/agent.py)."""

    name = "fintriage_agent"

    async def classify(self, message: str) -> str:
        """Return the single highest-priority regex match, or fall back to LLM."""
        regex_hit = classify_intent_regex(message)
        if regex_hit:
            return regex_hit
        return await classify_intent_llm(message)

    async def classify_all(self, message: str) -> List[str]:
        """Return ALL matched intents sorted by _TOOL_EXECUTION_ORDER.

        Falls back to a single LLM-classified intent when regex finds nothing.
        """
        matched = classify_all_intents_regex(message)
        if not matched:
            llm_intent = await classify_intent_llm(message)
            matched = [llm_intent]

        # Sort by the canonical execution order; unknown intents go to the end.
        order_index = {intent: i for i, intent in enumerate(_TOOL_EXECUTION_ORDER)}
        matched.sort(key=lambda x: order_index.get(x, len(_TOOL_EXECUTION_ORDER)))
        return matched

    async def handle(self, message: str, session_context: Dict[str, Any]) -> Dict[str, Any]:
        """Detect ALL matching intents, execute in canonical order, combine replies.

        Requirements 5.5 (multi-intent detection) and 5.6 (ordered execution with
        context propagation).

        Returns the standard {tool_used, confidence, reply, data} envelope.
        For multi-intent responses, tool_used is a comma-joined list and data is
        a dict keyed by intent name.
        """
        intents = await self.classify_all(message)
        log.info("agent.dispatch", intents=intents)

        # ── Single-intent path (unchanged behaviour) ─────────────────────
        if len(intents) == 1:
            intent = intents[0]
            handler = getattr(self, f"_tool_{intent}", None)
            if not handler:
                reply = await self._general_chat(message, session_context)
                return {"tool_used": "general_chat", "confidence": 0.5, "reply": reply, "data": None}
            try:
                return await handler(message, session_context)
            except Exception as e:
                log.error("agent.tool_error", tool=intent, error=str(e))
                return {
                    "tool_used": intent,
                    "confidence": 0.2,
                    "reply": f"I hit an error running the `{intent}` tool: {e}. Try rephrasing, or run a fresh assessment first.",
                    "data": None,
                }

        # ── Multi-intent path ─────────────────────────────────────────────
        # Work on a mutable copy of session_context so reassess can propagate
        # updated last_result / last_features to subsequent tools without
        # mutating the caller's dict permanently (the caller may save it back).
        accumulated_context: Dict[str, Any] = dict(session_context)

        replies: List[str] = []
        all_data: Dict[str, Any] = {}
        confidences: List[float] = []

        for intent in intents:
            handler = getattr(self, f"_tool_{intent}", None)
            if not handler:
                log.warning("agent.unknown_intent_skipped", intent=intent)
                continue

            try:
                result = await handler(message, accumulated_context)
            except Exception as e:
                log.error("agent.tool_error", tool=intent, error=str(e))
                replies.append(f"*(Error running `{intent}`: {e})*")
                continue

            reply_text = result.get("reply", "")
            if reply_text:
                replies.append(reply_text)
            if result.get("data") is not None:
                all_data[intent] = result["data"]
            confidences.append(result.get("confidence", 0.5))

            # Propagate reassess output into accumulated_context so that
            # compare / explain_risk / generate_report see the updated state.
            if intent == "reassess" and result.get("data"):
                sim_data = result["data"]
                simulated = sim_data.get("simulated") or {}
                if simulated:
                    accumulated_context["last_result"] = simulated
                if sim_data.get("overrides"):
                    # Merge overrides into the feature vector
                    updated_features = dict(accumulated_context.get("last_features") or {})
                    updated_features.update(sim_data["overrides"])
                    accumulated_context["last_features"] = updated_features

        if not replies:
            reply = await self._general_chat(message, session_context)
            return {"tool_used": "general_chat", "confidence": 0.5, "reply": reply, "data": None}

        # ── Combine replies ───────────────────────────────────────────────
        combined_reply = await self._combine_replies(replies, message)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        tools_used = ", ".join(intents)

        return {
            "tool_used": tools_used,
            "confidence": round(avg_confidence, 2),
            "reply": combined_reply,
            "data": all_data if all_data else None,
        }

    async def _combine_replies(self, replies: List[str], original_message: str) -> str:
        """Synthesise multiple tool replies into a single coherent response.

        Tries Gemma first; falls back to a plain separator join so the method
        always returns something useful even without an LLM.
        """
        if len(replies) == 1:
            return replies[0]

        separator_joined = "\n\n---\n\n".join(replies)

        client = get_llm_client_or_none()
        if not client:
            return separator_joined

        prompt = (
            "You are FinTriage AI. The user asked: \"{user_msg}\"\n\n"
            "Multiple compliance tools ran and each produced a section below. "
            "Synthesise these into a single, coherent, well-structured response. "
            "Preserve all numbers, rule codes, and monetary figures exactly.\n\n"
            "{sections}"
        ).format(user_msg=original_message, sections=separator_joined)

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            return resp.choices[0].message.content or separator_joined
        except Exception as e:
            log.warning("agent.combine_replies_llm_failed", error=str(e))
            return separator_joined

    # ── Shared helpers ────────────────────────────────────────────────────

    def _composio_status_line(self) -> str:
        """One-line, honest description of whether external actions are actually
        wired up right now, so Gemma can decide whether to propose them."""
        try:
            from app.connectors.composio_client import ComposioConnector
            connector = ComposioConnector()
            if connector.is_configured():
                return ("Composio is CONNECTED. You may propose a concrete external action "
                        "(send an email via Outlook, post to Slack, create a task) as a next step "
                        "when it genuinely helps — the platform will stage it for human approval "
                        "before anything is sent.")
            return ("Composio is NOT connected right now, so do not promise to send emails, "
                    "notify anyone, or take external actions — only recommend them as manual steps.")
        except Exception:
            return "External-action status unknown — do not promise external actions."

    async def _gemma_synthesize(
        self,
        user_message: str,
        computed: Dict[str, Any],
        deterministic_reply: str,
        tool_name: str,
    ) -> str:
        """Route a tool's already-computed, ground-truth numbers through Gemma so
        the final reply is real reasoning grounded in this specific case, not a
        canned template. The deterministic numbers are handed to Gemma as fact;
        Gemma is instructed to explain, contextualize, and recommend a concrete
        next step — never to invent or alter the figures.

        Always falls back to `deterministic_reply` if no Gemma provider is
        configured or the call fails, so the agent never breaks."""
        client = get_llm_client_or_none()
        if not client:
            return deterministic_reply

        system_prompt = (
            "You are FinTriage AI, a financial-compliance risk copilot embedded in the GemmaFin OS "
            "platform (Indian AML/KYC/GST/FEMA/Income-Tax/Corporate-Governance compliance triage for SMEs "
            f"and financial review teams). You just ran the '{tool_name}' tool and it returned the exact, "
            "correct, ground-truth data below as JSON. Do not recompute, invent, round differently, or "
            "contradict any number in it — treat it as fact.\n\n"
            "Write a short, specific reply (3-6 sentences) that:\n"
            "1. Directly answers the user's question using the real figures/rule codes/entity names from the data.\n"
            "2. Explains WHY in plain English (what in the data drives this result).\n"
            "3. Recommends one concrete, specific next action the user can take on THIS platform "
            "(e.g. 'run a threshold_sim on cash_ratio', 'generate the audit report', 'compare against "
            "your other entities', or — only if Composio is connected — a real external action).\n\n"
            f"{self._composio_status_line()}\n\n"
            "Never say generic things like 'I can help with that' — always ground the reply in the "
            "specific numbers, rule codes, and entity names present in the data JSON."
        )
        payload = json.dumps(computed, default=str)[:3000]
        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User asked: \"{user_message}\"\n\nTool output (ground truth):\n{payload}"},
                ],
                temperature=0.3,
                max_tokens=350,
            )
            text = resp.choices[0].message.content
            return text.strip() if text and text.strip() else deterministic_reply
        except Exception as e:
            log.warning("agent.gemma_synthesize_failed", tool=tool_name, error=str(e))
            return deterministic_reply

    def _base_features(self, session_context: Dict[str, Any]) -> Dict[str, float]:
        return session_context.get("last_features") or {
            "monthly_txn_volume": 100, "avg_ticket_size": 50000.0, "cash_ratio": 0.1,
            "cross_border_ratio": 0.05, "late_payment_rate": 0.05, "business_age_years": 5.0,
            "sector_risk_score": 0.3, "director_count": 2, "anomaly_risk_score": 0.5,
        }

    # ── Tool: reassess ────────────────────────────────────────────────────

    async def _tool_reassess(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        base_features = self._base_features(ctx)
        overrides = parse_what_if(message, base_features)
        if not overrides:
            return {
                "tool_used": "reassess", "confidence": 0.3,
                "reply": "I couldn't identify a specific change to simulate (e.g. \"what if cash ratio doubles?\"). "
                         "Try naming the metric and new value explicitly.",
                "data": None,
            }

        base_result = run_full_assessment(base_features, detected_flags=ctx.get("last_flags"), sector=ctx.get("sector"))
        new_result = reassess_with_overrides(base_features, overrides, base_flags=ctx.get("last_flags"), sector=ctx.get("sector"))

        tier_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        b, s = tier_rank.get(base_result["risk_tier"], 2), tier_rank.get(new_result["risk_tier"], 2)
        impact = "increased" if s > b else ("decreased" if s < b else "unchanged")

        reply = (
            f"**Reassessment result** (changed: {', '.join(overrides.keys())})\n\n"
            f"- Baseline: **{base_result['risk_tier'].upper()}** ({len(base_result['findings'])} rules flagged, "
            f"₹{int(base_result['total_penalty_exposure_inr']):,} exposure)\n"
            f"- Simulated: **{new_result['risk_tier'].upper()}** ({len(new_result['findings'])} rules flagged, "
            f"₹{int(new_result['total_penalty_exposure_inr']):,} exposure)\n\n"
            f"**Risk {impact}.**"
        )
        data = {"base": base_result, "simulated": new_result, "overrides": overrides}
        reply = await self._gemma_synthesize(message, data, reply, "reassess")
        return {"tool_used": "reassess", "confidence": 0.85, "reply": reply, "data": data}

    # ── Tool: penalty_sim ────────────────────────────────────────────────

    async def _tool_penalty_sim(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        msg_l = message.lower()
        scenario = next((s for s in SCENARIOS if s["id"] in msg_l or s["name"].lower() in msg_l), None)
        if not scenario:
            # try matching by keyword overlap against scenario names
            best, best_score = None, 0
            for s in SCENARIOS:
                score = sum(1 for w in s["name"].lower().split() if w in msg_l)
                if score > best_score:
                    best, best_score = s, score
            scenario = best if best_score > 0 else SCENARIOS[0]

        req = PenaltySimRequest(
            scenario_id=scenario["id"],
            days_since_breach=30,
            repeat_offence="repeat" in msg_l,
        )
        resp = await run_penalty_simulation(req, user={"id": ctx.get("user_id", "agent")})
        reply = (
            f"**Penalty Simulation — {resp.scenario_name}** ({resp.rule_code})\n\n"
            f"{resp.verdict}\n\n"
            f"- Base fine: ₹{resp.base_fine:,}\n"
            f"- Time penalty (30 days): ₹{resp.time_penalty:,}\n"
            f"- Aggravating multiplier: {resp.aggravating_multiplier}x\n"
            f"- **Total exposure: ₹{resp.total_fine:,}**"
            + (f"\n- Imprisonment risk: {resp.imprisonment_months} months" if resp.imprisonment_risk else "")
        )
        data = resp.model_dump()
        reply = await self._gemma_synthesize(message, data, reply, "penalty_sim")
        return {"tool_used": "penalty_sim", "confidence": 0.9, "reply": reply, "data": data}

    # ── Tool: threshold_sim ──────────────────────────────────────────────

    async def _tool_threshold_sim(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        base_features = self._base_features(ctx)
        msg_l = message.lower()
        feature_key = "monthly_txn_volume"
        if "cash" in msg_l:
            feature_key = "cash_ratio"
        elif "cross" in msg_l or "border" in msg_l or "international" in msg_l:
            feature_key = "cross_border_ratio"
        elif "director" in msg_l:
            feature_key = "director_count"

        multipliers = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
        trace = []
        breach_at = None
        for mult in multipliers:
            trial = dict(base_features)
            trial[feature_key] = min(1.0, base_features.get(feature_key, 0.0) * mult) if feature_key.endswith("ratio") else base_features.get(feature_key, 0.0) * mult
            ranked = rank_all_rules(trial, sector=ctx.get("sector"))
            top = ranked[0] if ranked else None
            trace.append({"multiplier": mult, "value": trial[feature_key], "top_rule": top["rule_code"] if top else None, "top_score": top["combined_score"] if top else 0})
            if top and top["combined_score"] > 0.6 and breach_at is None:
                breach_at = mult

        reply = (
            f"**Threshold Simulation — `{feature_key}`**\n\n"
            + "\n".join(f"- {t['multiplier']}x (→ {round(t['value'], 3)}): top rule {t['top_rule']} @ {round(t['top_score'], 2)}" for t in trace)
            + (f"\n\n**Breaches a high-confidence rule match at ~{breach_at}x current value.**" if breach_at else "\n\nNo high-confidence breach found within the tested range (up to 3x).")
        )
        data = {"feature": feature_key, "trace": trace, "breach_at_multiplier": breach_at}
        reply = await self._gemma_synthesize(message, data, reply, "threshold_sim")
        return {"tool_used": "threshold_sim", "confidence": 0.75, "reply": reply, "data": data}

    # ── Tool: compare ────────────────────────────────────────────────────

    async def _load_recent_entities(self, user_id: str) -> Dict[str, Dict]:
        """Query the DB for the most recent 3 compliance assessments for user_id.

        Returns a dict keyed by entity.business_name → feature dict extracted
        from raw_features (or individual numeric columns as fallback).

        Uses local imports to avoid circular-import issues at module load time.
        Returns {} gracefully if the DB is unavailable or not configured.
        """
        try:
            from sqlalchemy import select
            from app.db.session import SessionLocal
            from app.db.models import ComplianceAssessment, Entity

            async with SessionLocal() as db:
                stmt = (
                    select(ComplianceAssessment, Entity)
                    .join(Entity, ComplianceAssessment.entity_id == Entity.id, isouter=True)
                    .where(ComplianceAssessment.user_id == user_id)
                    .order_by(ComplianceAssessment.created_at.desc())
                    .limit(3)
                )
                rows = (await db.execute(stmt)).all()

            result: Dict[str, Dict] = {}
            for assessment, entity in rows:
                # Prefer raw_features if stored; fall back to individual columns
                features: Dict = dict(assessment.raw_features or {})
                if not features:
                    for col in (
                        "monthly_txn_volume", "avg_ticket_size", "cash_ratio",
                        "cross_border_ratio", "late_payment_rate", "sector_risk_score",
                        "anomaly_risk_score",
                    ):
                        val = getattr(assessment, col, None)
                        if val is not None:
                            features[col] = float(val)

                business_name = (entity.business_name if entity else None) or str(assessment.id)
                result[business_name] = features

            return result
        except Exception as e:
            log.warning("agent.load_recent_entities_failed", error=str(e))
            return {}

    async def _tool_compare(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        entities: Dict[str, Dict[str, float]] = dict(ctx.get("entities") or {})

        if len(entities) < 2:
            user_id = ctx.get("user_id")
            if user_id:
                db_entities = await self._load_recent_entities(str(user_id))
                # Merge DB results; session context takes precedence for shared keys
                merged = {**db_entities, **entities}
                entities = merged

        if len(entities) < 2:
            return {
                "tool_used": "compare", "confidence": 0.3,
                "reply": "I need at least 2 entities with feature profiles in session_context['entities'] "
                         "(e.g. {\"Apex Realty\": {...features...}, \"Clean IT Co\": {...features...}}) to compare.",
                "data": None,
            }
        results = {}
        for name, feats in list(entities.items())[:3]:
            results[name] = run_full_assessment(feats, sector=feats.get("sector"))

        lines = [f"**Comparison — {', '.join(results.keys())}**\n"]
        for name, r in results.items():
            lines.append(f"- **{name}**: {r['risk_tier'].upper()} ({round(r['confidence']*100)}% confidence), "
                          f"{len(r['findings'])} rules flagged, ₹{int(r['total_penalty_exposure_inr']):,} exposure")
        reply = await self._gemma_synthesize(message, results, "\n".join(lines), "compare")
        return {"tool_used": "compare", "confidence": 0.85, "reply": reply, "data": results}

    # ── Tool: explain_risk ───────────────────────────────────────────────

    async def _tool_explain_risk(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        last_result = ctx.get("last_result")
        if not last_result:
            return {
                "tool_used": "explain_risk", "confidence": 0.3,
                "reply": "I don't have an active assessment to explain yet. Run `/compliance/assess` first, "
                         "then ask me to explain the result.",
                "data": None,
            }
        findings = last_result.get("findings", [])[:3]
        drivers = ", ".join(f"{f['rule_code']} ({f['severity']})" for f in findings) or "no specific rule breaches"
        anomaly_summary = last_result.get("anomaly", {}).get("anomaly_summary", "")

        base_reply = (
            f"This entity is rated **{last_result['risk_tier'].upper()}** "
            f"({round(last_result.get('confidence', 0) * 100)}% model confidence). "
            f"Top drivers: {drivers}. {anomaly_summary}"
        )

        data = {"risk_tier": last_result["risk_tier"], "confidence": last_result.get("confidence", 0),
                "findings": findings, "anomaly_summary": anomaly_summary,
                "total_penalty_exposure_inr": last_result.get("total_penalty_exposure_inr")}
        base_reply = await self._gemma_synthesize(message, data, base_reply, "explain_risk")

        return {"tool_used": "explain_risk", "confidence": 0.8, "reply": base_reply, "data": {"findings": findings}}

    # ── Tool: rule_info ──────────────────────────────────────────────────

    async def _tool_rule_info(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        m = _RULE_CODE_RE.search(message)
        rule = get_rule_by_code(m.group(1).upper()) if m else None

        if not rule:
            msg_l = message.lower()
            best, best_score = None, 0
            for r in COMPLIANCE_RULES:
                score = sum(1 for w in r["name"].lower().split() if w in msg_l)
                if score > best_score:
                    best, best_score = r, score
            rule = best

        if not rule:
            return {"tool_used": "rule_info", "confidence": 0.2, "reply": "I couldn't identify which rule you mean — try a code like `AML-001` or a keyword like `CTR`.", "data": None}

        reply = (
            f"**{rule['code']} — {rule['name']}** ({rule['framework']}, {rule['severity']} severity)\n\n"
            f"{rule['description']}\n\n"
            f"Max penalty: ₹{rule.get('max_penalty_inr', 0):,}"
            + (f" · Imprisonment risk: {rule.get('imprisonment_months', 0)} months" if rule.get("imprisonment_risk") else "")
            + "\n\nRemediation steps:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(rule.get("remediation_steps", [])))
        )
        reply = await self._gemma_synthesize(message, rule, reply, "rule_info")
        return {"tool_used": "rule_info", "confidence": 0.95, "reply": reply, "data": rule}

    # ── Tool: generate_report ────────────────────────────────────────────

    async def _tool_generate_report(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        last_result = ctx.get("last_result")
        if not last_result:
            return {
                "tool_used": "generate_report", "confidence": 0.3,
                "reply": "I need an active assessment before I can generate a report. Run `/compliance/assess` first.",
                "data": None,
            }
        sections = build_report_sections(
            ctx.get("business_name"), ctx.get("sector"),
            last_result["risk_tier"], last_result.get("confidence", 0.5),
            last_result.get("findings", []), last_result.get("total_penalty_exposure_inr", 0.0),
            last_result.get("imprisonment_risk", False),
        )
        narrative = await generate_gemma_narrative(sections)
        sections["gemma_summary"] = narrative or "Report generated from pipeline results (LLM narrative unavailable)."
        return {
            "tool_used": "generate_report", "confidence": 0.9,
            "reply": f"Report generated. {sections['gemma_summary']}",
            "data": sections,
        }

    # ── Tool: external_action (Composio, gated by human approval) ───────

    async def _tool_external_action(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Routes external, real-world actions (send an email, notify a vendor,
        create a task, post to Slack) through Composio's tool catalogue, using
        Gemma's function-calling to pick the right tool + arguments. Every write
        action is staged as a pending approval instead of executing immediately
        (see app/connectors/composio_client.execute_composio_tool_gated) — this
        is the concrete tie between the Composio integration and the Gemma agent
        the user asked to keep "correlated"."""
        from app.connectors.composio_client import ComposioConnector, execute_composio_tool_gated
        from app.db.session import SessionLocal

        connector = ComposioConnector()
        if not connector.is_configured():
            return {
                "tool_used": "external_action", "confidence": 0.2,
                "reply": "Composio isn't connected yet (COMPOSIO_API_KEY not set), so I can't take external actions like sending emails or posting to Slack. I can still reassess, simulate penalties, or explain the risk score.",
                "data": None,
            }

        client = get_llm_client_or_none()
        if not client:
            return {"tool_used": "external_action", "confidence": 0.2, "reply": "No Gemma provider available to plan this action.", "data": None}

        user_id = ctx.get("user_id", "default")
        try:
            tools_schema = connector.get_openai_tools(user_id)
        except Exception as e:
            log.warning("agent.composio_tools_fetch_failed", error=str(e))
            return {"tool_used": "external_action", "confidence": 0.2, "reply": f"Couldn't load connected-app tools from Composio: {e}", "data": None}

        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": "You plan one concrete external action using the available tools. Call exactly one tool with fully-specified arguments."},
                    {"role": "user", "content": message},
                ],
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.0,
            )
            tool_calls = resp.choices[0].message.tool_calls
        except Exception as e:
            # Req 5.9: Not every Gemma build/quantization supports tool-calling.
            # Instead of pure keyword matching (zero reasoning), try one plain
            # completion (no tools= schema) asking Gemma to actually plan the
            # action in JSON. This keeps a real Gemma-authored plan in the
            # approval payload even when function-calling itself isn't supported.
            log.warning("agent.gemma_tool_calling_failed", error=str(e))

            action_type = "external_action"
            gemma_plan: Dict[str, Any] | None = None
            try:
                plan_resp = client.chat.completions.create(
                    model=get_llm_model(),
                    messages=[
                        {"role": "system", "content": (
                            "The user wants to take an external action (email/Slack/task/notification/meeting). "
                            "This model build doesn't support tool-calling, so respond with ONLY a JSON object: "
                            '{"action_type": "send_email|post_slack|create_task|send_notification|schedule_meeting", '
                            '"target": "who/where", "subject": "...", "body": "the actual message content, grounded in '
                            'any compliance context the user gave you"}. No prose, no markdown, JSON only.'
                        )},
                        {"role": "user", "content": message},
                    ],
                    temperature=0.1, max_tokens=300,
                )
                raw = plan_resp.choices[0].message.content or "{}"
                raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                gemma_plan = json.loads(raw)
                action_type = gemma_plan.get("action_type", "external_action")
            except Exception as plan_err:
                log.warning("agent.gemma_plain_plan_failed", error=str(plan_err))
                # Last-resort keyword classification only if Gemma reasoning itself failed
                msg_l = message.lower()
                if "email" in msg_l or "mail" in msg_l:
                    action_type = "send_email"
                elif "slack" in msg_l:
                    action_type = "post_slack"
                elif "task" in msg_l or "create" in msg_l:
                    action_type = "create_task"
                elif "notify" in msg_l or "notification" in msg_l:
                    action_type = "send_notification"
                elif "schedule" in msg_l or "meeting" in msg_l or "call" in msg_l:
                    action_type = "schedule_meeting"

            # Stage a bare ApprovalRequest with the raw message as reason
            try:
                from app.db.session import SessionLocal
                from app.db.models import ApprovalRequest

                reason_text = message
                if gemma_plan:
                    reason_text = (
                        f"[Gemma-planned {action_type}] Target: {gemma_plan.get('target', 'unspecified')} | "
                        f"Subject: {gemma_plan.get('subject', '')} | Body: {gemma_plan.get('body', message)}"
                    )

                async with SessionLocal() as db:
                    approval = ApprovalRequest(
                        requested_by_user_id=None,
                        action_type=action_type,
                        reason=reason_text,
                        payload=gemma_plan or {"raw_message": message},
                        status="pending",
                        risk_level="high",
                        assessment_id=None,
                    )
                    db.add(approval)
                    await db.commit()
                    await db.refresh(approval)
                    approval_id = str(approval.id)

                if gemma_plan:
                    reply = (
                        f"I've planned this as a **{action_type}** to {gemma_plan.get('target', 'the recipient')} "
                        f"— \"{gemma_plan.get('subject') or gemma_plan.get('body', '')[:80]}\". This Gemma model "
                        f"build doesn't support native tool-calling, so I reasoned out the plan directly instead "
                        f"of guessing from keywords. It's staged as approval `{approval_id}` — a compliance "
                        f"officer, CFO, or auditor needs to approve it before anything actually sends."
                    )
                else:
                    reply = (
                        f"This Gemma runtime doesn't support tool-calling ({e}), so I couldn't plan "
                        f"the action automatically. I've staged a **{action_type}** approval request "
                        f"(ID: `{approval_id}`) for a human to review and approve before any external "
                        f"action is taken."
                    )

                return {
                    "tool_used": "external_action",
                    "confidence": 0.6 if gemma_plan else 0.4,
                    "reply": reply,
                    "data": {"status": "pending_approval", "approval_id": approval_id, "plan": gemma_plan},
                }
            except Exception as db_err:
                log.error("agent.external_action_fallback_db_failed", error=str(db_err))
                return {
                    "tool_used": "external_action",
                    "confidence": 0.2,
                    "reply": (
                        f"This Gemma runtime doesn't support tool-calling ({e}) and I also couldn't "
                        f"stage the approval request ({db_err}). Please describe the action manually "
                        f"for a human operator."
                    ),
                    "data": None,
                }

        if not tool_calls:
            return {"tool_used": "external_action", "confidence": 0.3, "reply": resp.choices[0].message.content or "I couldn't identify a specific action to take.", "data": None}

        import json as _json
        call = tool_calls[0]
        tool_slug = call.function.name
        try:
            arguments = _json.loads(call.function.arguments or "{}")
        except Exception:
            arguments = {}

        async with SessionLocal() as db:
            result = await execute_composio_tool_gated(
                tool_slug, user_id, arguments, db,
                assessment_id=ctx.get("assessment_id"),
                reason=f"Agent action requested via chat: \"{message}\"",
            )

        if result.get("status") == "pending_approval":
            reply = (
                f"This would call **{tool_slug}** with {arguments}. Since that's a write/external action, "
                f"I've staged it for human approval (request `{result['approval_id']}`) instead of executing it directly — "
                f"a compliance officer, CFO, or auditor needs to approve it first."
            )
        else:
            reply = f"Executed **{tool_slug}**: {result}"

        return {"tool_used": "external_action", "confidence": 0.8, "reply": reply, "data": {"tool_slug": tool_slug, "arguments": arguments, "result": result}}

    # ── Tool: platform_help (Knowledge Base RAG) ─────────────────────────

    async def _tool_platform_help(self, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        from app.ml.knowledge_base import answer_platform_question
        result = await answer_platform_question(message)
        return {"tool_used": "platform_help", "confidence": 0.75, "reply": result["answer"], "data": {"sources": result["sources"]}}

    # ── Fallback: general_chat ──────────────────────────────────────────

    async def _general_chat(self, message: str, ctx: Dict[str, Any]) -> str:
        client = get_llm_client_or_none()
        if not client:
            return ("I'm the FinTriage compliance agent. I can reassess what-if scenarios, simulate penalties, "
                    "explain risk drivers, look up specific rules, compare entities, and generate audit reports — "
                    "but no LLM provider is configured right now (start Ollama or set USE_GEMMA + GEMMA_API_KEY), "
                    "so I can only run the deterministic tools, not free-form chat.")

        # Pull real, live context instead of dumping the raw session dict —
        # this is what actually grounds the reply in THIS user's data rather
        # than producing a generic answer.
        last_result = ctx.get("last_result")
        recent_entities: Dict[str, Any] = {}
        user_id = ctx.get("user_id")
        if user_id:
            recent_entities = await self._load_recent_entities(str(user_id))

        live_context = {
            "active_assessment": {
                "business_name": ctx.get("business_name"),
                "sector": ctx.get("sector"),
                "risk_tier": last_result.get("risk_tier") if last_result else None,
                "confidence": last_result.get("confidence") if last_result else None,
                "top_findings": (last_result.get("findings") or [])[:3] if last_result else [],
                "total_penalty_exposure_inr": last_result.get("total_penalty_exposure_inr") if last_result else None,
            } if last_result else None,
            "other_recent_entities": {k: {kk: vv for kk, vv in v.items() if kk in (
                "cash_ratio", "cross_border_ratio", "monthly_txn_volume", "sector_risk_score")}
                for k, v in list(recent_entities.items())[:3]},
        }

        system_prompt = (
            "You are FinTriage AI, the conversational agent inside the GemmaFin OS platform — an Indian "
            "financial-compliance risk triage system covering AML/CFT, KYC/KYB, GST, FEMA, Income Tax, and "
            "Corporate Governance rules. You are not a generic chatbot: you sit on top of a real 3-stage ML "
            "pipeline (anomaly scorer -> XGBoost risk classifier -> compliance gap ranker), a 40-rule compliance "
            "catalogue, a penalty simulator, and (when connected) Composio for real external actions like sending "
            "email/Slack notifications or creating tasks — all gated behind human approval.\n\n"
            "Below is the REAL, LIVE data for this user/session right now (may be partially empty if they haven't "
            "run an assessment yet — in that case, tell them to run one instead of inventing numbers):\n"
            f"{json.dumps(live_context, default=str)[:2500]}\n\n"
            f"{self._composio_status_line()}\n\n"
            "Other tools available if the user's next message matches: reassess (what-if simulation), "
            "penalty_sim (fine exposure), threshold_sim (distance to a reporting threshold), compare (2-3 "
            "entities side by side), rule_info (detail on one of the 40 rules), generate_report (6-section audit "
            "report). If the user's question is really asking for one of these, tell them the exact phrasing that "
            "triggers it rather than answering vaguely.\n\n"
            "Never give a generic, platform-agnostic compliance answer. Ground every reply in the live data above, "
            "or explicitly say what's missing (e.g. 'run an assessment first') if it isn't there."
        )
        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                temperature=0.4, max_tokens=400,
            )
            return resp.choices[0].message.content or "I couldn't generate a response."
        except Exception as e:
            log.warning("agent.general_chat_failed", error=str(e))
            return f"LLM call failed: {e}"
