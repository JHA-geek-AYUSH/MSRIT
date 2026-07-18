from __future__ import annotations

import math
import json
from typing import Dict, List, Any, Optional
import structlog

from app.agents.base import AgentOutput
from app.agents.weights import get_weights, update_weights, get_subdomain
from app.core.gemma_client import get_llm_client_or_none, get_llm_model

log = structlog.get_logger()

ETA = 0.15
MIN_WEIGHT = 0.2
MAX_WEIGHT = 5.0


def aggregate(outputs: Dict[str, AgentOutput], query: str = "", subdomain: Optional[str] = None) -> Dict:
    if not outputs:
        return {"answer": "", "weights": {}, "aligned": [], "confidence": 0.0}

    log.info("aggregator.start", agents_count=len(outputs))

    if not subdomain:
        subdomain = get_subdomain(query)

    current_weights = get_weights(subdomain)
    weights_before = current_weights.copy()

    synthesized_answer = _synthesize_with_llm(outputs, current_weights, query)

    aligned_agents = _determine_alignment(outputs, synthesized_answer)

    updated_weights = _update_weights_mwu(current_weights, outputs, aligned_agents)
    update_weights(subdomain, updated_weights)

    overall_confidence = _calculate_overall_confidence(outputs, updated_weights, aligned_agents)

    log.info("aggregator.complete",
             aligned_count=len(aligned_agents),
             subdomain=subdomain,
             confidence=overall_confidence)

    return {
        "answer": synthesized_answer,
        "weights": updated_weights,
        "weights_before": weights_before,
        "aligned": aligned_agents,
        "confidence": overall_confidence,
        "subdomain": subdomain
    }


def _synthesize_with_llm(outputs: Dict[str, AgentOutput], weights: Dict[str, float], query: str) -> str:
    """Use LLM to synthesize all agent outputs into a coherent final answer."""
    client = get_llm_client_or_none()
    if not client:
        # Fallback: return best agent's reasoning
        best = max(outputs.items(), key=lambda kv: weights.get(kv[0], 1.0) * kv[1]["confidence"])
        return best[1]["reasoning"]

    try:
        model = get_llm_model()

        # Build agent summaries sorted by weighted score
        agent_sections = []
        for name, output in outputs.items():
            w = weights.get(name, 1.0)
            score = w * output["confidence"]
            reasoning = output.get("reasoning", "")
            if reasoning and not reasoning.startswith("Agent ") and len(reasoning) > 50:
                agent_sections.append((score, name, reasoning))

        agent_sections.sort(reverse=True)

        if not agent_sections:
            return "Unable to generate analysis. Please try again."

        agents_text = "\n\n".join([
            f"### {name.upper()} AGENT (score: {score:.2f}):\n{reasoning[:600]}"
            for score, name, reasoning in agent_sections[:6]
        ])

        prompt = f"""You are GemmaFinOS, an AI legal co-counsel for Indian lawyers. Synthesize the following specialist agent analyses into a single, comprehensive, well-structured legal answer.

USER QUERY: {query}

SPECIALIST AGENT ANALYSES:
{agents_text}

SYNTHESIS INSTRUCTIONS:
- Combine insights from all agents into one coherent answer
- Lead with the most critical legal points
- Include specific statute sections, case citations, and limitation periods where mentioned
- Flag risks and counterarguments clearly
- Use markdown formatting with headers for readability
- Be precise and actionable for a practicing Indian lawyer
- Do NOT mention the agent system or that this is synthesized
- Write as a direct, authoritative legal analysis

SYNTHESIZED LEGAL ANALYSIS:"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content or agent_sections[0][2]

    except Exception as e:
        log.error("aggregator.synthesis_failed", error=str(e))
        best = max(outputs.items(), key=lambda kv: weights.get(kv[0], 1.0) * kv[1]["confidence"])
        return best[1]["reasoning"]


def _determine_alignment(outputs: Dict[str, AgentOutput], synthesized_answer: str) -> List[str]:
    aligned = []
    answer_words = set(synthesized_answer.lower().split()) - _STOP_WORDS

    for name, output in outputs.items():
        if output["confidence"] < 0.2:
            continue
        agent_words = set(output["reasoning"].lower().split()) - _STOP_WORDS
        if not agent_words or not answer_words:
            continue
        jaccard = len(agent_words & answer_words) / len(agent_words | answer_words)
        if jaccard >= 0.15 or output["confidence"] >= 0.7:
            aligned.append(name)

    if not aligned:
        best = max(outputs.keys(), key=lambda a: outputs[a]["confidence"])
        aligned.append(best)
    return aligned


def _update_weights_mwu(current_weights: Dict[str, float], outputs: Dict[str, AgentOutput],
                        aligned_agents: List[str]) -> Dict[str, float]:
    updated = current_weights.copy()
    for name in outputs:
        w = updated.get(name, 1.0)
        new_w = w * math.exp(ETA) if name in aligned_agents else w * math.exp(-ETA)
        updated[name] = max(MIN_WEIGHT, min(MAX_WEIGHT, new_w))
    return updated


def _calculate_overall_confidence(outputs: Dict[str, AgentOutput], weights: Dict[str, float],
                                  aligned_agents: List[str]) -> float:
    if not outputs:
        return 0.0
    total_wc = sum(
        weights.get(n, 1.0) * (min(1.0, o["confidence"] * 1.1) if n in aligned_agents else o["confidence"] * 0.9)
        for n, o in outputs.items()
    )
    total_w = sum(weights.get(n, 1.0) for n in outputs)
    base = total_wc / total_w if total_w > 0 else 0.0
    alignment_boost = (len(aligned_agents) / len(outputs)) * 0.1
    return min(0.95, base + alignment_boost)


_STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'can', 'may', 'might', 'must', 'shall', 'this', 'that', 'it',
    'as', 'from', 'not', 'also', 'which', 'who', 'what', 'when', 'where'
}
