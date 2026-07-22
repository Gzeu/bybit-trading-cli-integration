"""Multi-provider LLM client — Groq / OpenRouter / Gemini / Ollama (all free-tier).

Priority: LLM_PROVIDER env var → groq (default)
All providers expose an OpenAI-compatible /chat/completions endpoint.
"""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

# ---------------------------------------------------------------------------
# Provider configs
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.1-8b-instant",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.1-8b-instruct:free",
    },
    "gemini": {
        # Google AI Studio OpenAI-compat endpoint
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash-lite",
    },
    "ollama": {
        # Ollama local — no key required
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": None,
        "default_model": os.getenv("OLLAMA_MODEL", "llama3.2"),
    },
}


def _get_client() -> tuple[OpenAI, str]:
    """Return (OpenAI client, model_name) for the active provider."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER='{provider}'. Choose: {list(_PROVIDERS)}.")

    cfg = _PROVIDERS[provider]
    api_key = (
        os.getenv(cfg["api_key_env"]) if cfg["api_key_env"] else "ollama"
    ) or "ollama"

    model = os.getenv("LLM_MODEL", cfg["default_model"])

    client = OpenAI(base_url=cfg["base_url"], api_key=api_key)
    return client, model


def chat_complete(
    system: str,
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """Send a chat completion request; return the assistant message text."""
    client, model = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def parse_action(raw: str) -> dict[str, Any]:
    """Parse LLM JSON response; return empty dict on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first {...} block (models sometimes wrap in markdown)
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}
