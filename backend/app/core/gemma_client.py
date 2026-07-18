"""
LLM client — Gemma-only, with a strict fallback order (per hackathon rules:
Gemma models only, no general-purpose OpenAI/GPT reasoning).

Fallback chain:
  1. Ollama (local Gemma — gemma3:*, free, no API key, fully private)
  2. Gemma via Google AI Studio (if USE_GEMMA + GEMMA_API_KEY) — still a Gemma model,
     just hosted rather than local
  3. Mock client (always works — returns template responses)

OpenAI/GPT is NOT part of this chain. It previously sat between (1) and (2) as a
general-purpose fallback; that violated the "Gemma models only" constraint, since
an assessment could silently be produced by GPT-4o-mini instead of Gemma. If you
need an emergency non-Gemma fallback for local dev, set ALLOW_NON_GEMMA_FALLBACK=true
and OPENAI_API_KEY — this is opt-in and off by default, and should not be enabled
for the actual hackathon submission/demo.

Usage:
    from app.core.gemma_client import get_llm_client, get_llm_model
    client = get_llm_client()
    model  = get_llm_model()
    resp   = client.chat.completions.create(model=model, messages=[...])
"""
from __future__ import annotations

import os
from typing import Optional
import structlog

from openai import OpenAI

from app.core.config import get_settings

log = structlog.get_logger()

# Cache the active provider so we don't retry failed connections every time
_active_client: Optional[OpenAI] = None
_active_model: str = "gemma3:1b"
_active_provider: str = "unavailable"
_AUTHORS = {
    "Ollama": "Ollama (Gemma, local, free)",
    "Gemma": "Gemma (Google AI Studio)",
    "OpenAI": "OpenAI (non-Gemma emergency fallback — opt-in only)",
    "Mock": "Mock (template fallback)",
}


def _try_ollama() -> OpenAI | None:
    """Try connecting to local Ollama, and only accept it if a Gemma model is
    actually installed — this connector must not silently pick a non-Gemma model
    (llama3/mistral/etc) just because it happens to be the first one installed."""
    global _active_model
    try:
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            timeout=120.0,
        )
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        for pref in ["gemma3:27b", "gemma3:12b", "gemma3:4b", "gemma3:2b", "gemma3:1b", "gemma2", "gemma"]:
            for mid in model_ids:
                if pref in mid:
                    _active_model = mid
                    return client
        # No Gemma model installed in Ollama — do not fall back to whatever else is
        # there (that could be llama3/mistral, violating the Gemma-only constraint).
        log.warning("llm.ollama_no_gemma_model",
                    message="Ollama is running but no gemma* model is installed. Run `ollama pull gemma3:1b`.",
                    available=model_ids)
        return None
    except Exception:
        return None


# Ordered list of free Gemma models on OpenRouter, tried in sequence on rate-limit
# or availability errors so a single congested slug doesn't take the whole app
# down mid-demo. The .env GEMMA_MODEL is always tried FIRST; these are the backup
# rotation if it 429s. All are genuine Gemma-family models (OpenRouter's free
# roster rotates over time — update this list if OpenRouter retires one).
_GEMMA_FALLBACK_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3-4b-it:free",
    "google/gemma-3-27b-it:free",
]


class _ResilientChatCompletions:
    """Wraps client.chat.completions.create so that a 429/404/5xx on the
    configured model automatically retries against the next free Gemma model
    in _GEMMA_FALLBACK_MODELS, instead of surfacing a raw provider error to the
    end user. Only used for the OpenRouter/Gemma-Studio path — Ollama already
    has zero rate limits so it doesn't need this."""

    def __init__(self, inner_completions, primary_model: str):
        self._inner = inner_completions
        self._primary_model = primary_model

    def create(self, *args, **kwargs):
        global _active_model
        # Try the configured model first, then the fallback rotation, skipping
        # duplicates and preserving order.
        candidates = [self._primary_model] + [m for m in _GEMMA_FALLBACK_MODELS if m != self._primary_model]
        last_error: Exception | None = None
        for model in candidates:
            try:
                kwargs["model"] = model
                resp = self._inner.create(*args, **kwargs)
                if model != _active_model:
                    log.info("llm.fallback_model_used", model=model)
                    _active_model = model
                return resp
            except Exception as e:
                msg = str(e)
                is_retriable = any(code in msg for code in ("429", "404", "503", "rate", "unavailable"))
                log.warning("llm.model_attempt_failed", model=model, error=msg, retriable=is_retriable)
                last_error = e
                if not is_retriable:
                    raise
                continue
        raise last_error  # every candidate failed

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _ResilientChat:
    def __init__(self, inner_chat, primary_model: str):
        self.completions = _ResilientChatCompletions(inner_chat.completions, primary_model)


class _ResilientClientWrapper:
    """Thin proxy around the real OpenAI client — same interface, but
    client.chat.completions.create() gains automatic Gemma-model failover."""

    def __init__(self, inner_client: OpenAI, primary_model: str):
        self._inner = inner_client
        self.chat = _ResilientChat(inner_client.chat, primary_model)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _try_gemma() -> OpenAI | None:
    """Try connecting to Gemma via Google AI Studio / OpenRouter (still a Gemma
    model, just hosted). Wrapped with automatic failover across multiple free
    Gemma slugs so a single congested model doesn't break the demo."""
    global _active_model
    settings = get_settings()
    if not (settings.USE_GEMMA and settings.GEMMA_API_KEY):
        return None
    try:
        raw_client = OpenAI(
            api_key=settings.GEMMA_API_KEY,
            base_url=settings.GEMMA_BASE_URL,
            timeout=20.0,
        )
        _active_model = settings.GEMMA_MODEL
        return _ResilientClientWrapper(raw_client, settings.GEMMA_MODEL)  # type: ignore[return-value]
    except Exception as e:
        log.warning("llm.gemma_init_failed", error=str(e))
        return None


def _try_openai_emergency_fallback() -> OpenAI | None:
    """Opt-in only, and NOT part of the default chain — see module docstring."""
    global _active_model
    if os.getenv("ALLOW_NON_GEMMA_FALLBACK", "false").lower() != "true":
        return None
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        return None
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=5.0)
        _active_model = settings.OPENAI_GEN_MODEL
        log.warning("llm.non_gemma_fallback_active",
                    message="ALLOW_NON_GEMMA_FALLBACK=true — responses are NOT coming from Gemma right now.")
        return client
    except Exception as e:
        log.warning("llm.openai_init_failed", error=str(e))
        return None


def _refresh_client() -> OpenAI:
    """Try each Gemma provider in order, return first working client or raise RuntimeError."""
    global _active_client, _active_provider, _active_model

    client = _try_ollama()
    if client:
        _active_provider = _AUTHORS["Ollama"]
        _active_client = client
        log.info("llm.using_provider", provider=_active_provider, model=_active_model)
        return client

    client = _try_gemma()
    if client:
        _active_provider = _AUTHORS["Gemma"]
        _active_client = client
        log.info("llm.using_provider", provider=_active_provider, model=_active_model)
        return client

    _active_provider = "unavailable"
    _active_client = None
    log.warning("llm.no_provider",
                message="No Gemma provider available. Run `ollama pull gemma3:1b && ollama serve`, "
                        "or set USE_GEMMA=true + GEMMA_API_KEY in .env")
    raise RuntimeError(
        "No Gemma provider available. "
        "Run `ollama pull gemma3:1b` (then `ollama serve`), or set USE_GEMMA=true + GEMMA_API_KEY in .env"
    )


def get_llm_client() -> OpenAI:
    """Return an OpenAI-compatible client with auto-detected provider.
    
    Fallback chain:
      1. Ollama (local, free) — auto-detects installed models
      2. OpenAI API — if OPENAI_API_KEY is set
      3. Gemma (Google AI Studio) — if USE_GEMMA=True + GEMMA_API_KEY
    
    Raises RuntimeError if no provider is available (agents handle this).
    """
    if _active_client is not None:
        return _active_client
    return _refresh_client()


def get_llm_model() -> str:
    """Return the model name to use for generation."""
    get_llm_client()  # Ensures provider is initialized
    return _active_model


def get_llm_client_or_none() -> OpenAI | None:
    """Return a Gemma-backed OpenAI-compatible client, or None if no Gemma provider
    is available (callers should degrade to deterministic/templated logic, not
    silently substitute a non-Gemma model)."""
    client = _try_ollama()
    if client:
        global _active_client, _active_provider
        _active_client = client
        _active_provider = _AUTHORS["Ollama"]
        log.info("llm.using_provider", provider=_active_provider, model=_active_model)
        return client

    client = _try_gemma()
    if client:
        _active_client = client
        _active_provider = _AUTHORS["Gemma"]
        log.info("llm.using_provider", provider=_active_provider, model=_active_model)
        return client

    return None


def get_active_provider() -> str:
    """Return the name of the currently active LLM provider."""
    get_llm_client()
    return _active_provider


def get_llm_status() -> dict:
    """Live, honest status for the /v1/system/status endpoint and the frontend's
    Gemma status indicator — answers "is this actually calling Gemma?" directly
    instead of leaving it as a black box. Never raises: reports unavailability
    as data, not an exception."""
    client = get_llm_client_or_none()
    is_gemma = _active_provider in (_AUTHORS["Ollama"], _AUTHORS["Gemma"])
    return {
        "connected": client is not None,
        "provider": _active_provider if client is not None else "none",
        "model": _active_model if client is not None else None,
        "is_gemma": is_gemma,
        "setup_needed": client is None,
        "setup_hint": None if client is not None else (
            "Run `ollama pull gemma3:4b && ollama serve` for a free local Gemma model, "
            "or set USE_GEMMA=true + GEMMA_API_KEY (from aistudio.google.com/apikey) in backend/.env. "
            "See KEYS.md §2."
        ),
    }
