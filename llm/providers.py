"""Multi-provider LLM client — Groq / OpenRouter / Gemini / Ollama / Together / Mistral / DeepSeek.

Features:
  - Auto-fallback chain: tries providers in order until one responds
  - Health-check: python -m llm.providers test [provider]
  - List: python -m llm.providers list
  - All providers use OpenAI-compatible /chat/completions
  - Zero extra deps beyond `openai` package
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict[str, Any]] = {
    # ---- Free / free-tier providers ----------------------------------------
    "groq": {
        "base_url":     "https://api.groq.com/openai/v1",
        "api_key_env":  "GROQ_API_KEY",
        "default_model": "llama-3.1-8b-instant",
        "free":         True,
        "note":         "Fastest free (~1000 tok/s). ~30 RPM on free tier.",
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "gemma2-9b-it",
            "mixtral-8x7b-32768",
        ],
    },
    "openrouter": {
        "base_url":     "https://openrouter.ai/api/v1",
        "api_key_env":  "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.1-8b-instruct:free",
        "free":         True,
        "note":         "Multi-model fallback. Free models end in :free.",
        "models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "qwen/qwen-2.5-7b-instruct:free",
            "google/gemma-3-12b-it:free",
        ],
    },
    "gemini": {
        "base_url":     "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env":  "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash-lite",
        "free":         True,
        "note":         "Google AI Studio free tier. Strict RPM/RPD limits.",
        "models": [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ],
    },
    "ollama": {
        "base_url":     os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env":  None,  # no key needed
        "default_model": os.getenv("OLLAMA_MODEL", "llama3.2"),
        "free":         True,
        "note":         "Local, offline, zero cloud. Needs Ollama running.",
        "models": ["llama3.2", "llama3.1", "qwen2.5", "mistral", "phi3"],
    },
    # ---- Paid but cheap providers ------------------------------------------
    "together": {
        "base_url":     "https://api.together.xyz/v1",
        "api_key_env":  "TOGETHER_API_KEY",
        "default_model": "meta-llama/Llama-3-8b-chat-hf",
        "free":         False,
        "note":         "Cheap pay-per-use. $0.10-0.20/M tokens.",
        "models": [
            "meta-llama/Llama-3-8b-chat-hf",
            "meta-llama/Llama-3-70b-chat-hf",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ],
    },
    "mistral": {
        "base_url":     "https://api.mistral.ai/v1",
        "api_key_env":  "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
        "free":         False,
        "note":         "Mistral AI direct. mistral-small cheap & fast.",
        "models": ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest"],
    },
    "deepseek": {
        "base_url":     "https://api.deepseek.com/v1",
        "api_key_env":  "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "free":         False,
        "note":         "Ultra-cheap. ~$0.07/M input tokens.",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
}

# Fallback chain: tried in order when active provider fails
# Override with LLM_FALLBACK_CHAIN=groq,openrouter,gemini
_DEFAULT_FALLBACK_CHAIN = ["groq", "openrouter", "gemini", "ollama"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_client(provider: str) -> tuple[OpenAI, str]:
    """Build OpenAI client for a given provider name."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Available: {list(PROVIDERS)}")
    cfg = PROVIDERS[provider]
    api_key = (os.getenv(cfg["api_key_env"]) if cfg["api_key_env"] else None) or "nokey"
    model   = os.getenv("LLM_MODEL", cfg["default_model"])
    client  = OpenAI(base_url=cfg["base_url"], api_key=api_key)
    return client, model


def _active_provider() -> str:
    return os.getenv("LLM_PROVIDER", "groq").lower()


def _fallback_chain() -> list[str]:
    raw = os.getenv("LLM_FALLBACK_CHAIN", "")
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip() in PROVIDERS]
    return _DEFAULT_FALLBACK_CHAIN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat_complete(
    system: str,
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 512,
    provider: str | None = None,
    use_fallback: bool = True,
) -> str:
    """Send chat completion. Falls back to next provider on rate-limit or error.

    Args:
        system: System prompt text.
        user: User message text.
        temperature: Sampling temperature (0.0–1.0).
        max_tokens: Max tokens in response.
        provider: Override LLM_PROVIDER env var for this call.
        use_fallback: If True, try fallback chain on failure.

    Returns:
        Assistant message string (JSON expected).
    """
    primary = provider or _active_provider()
    chain   = [primary] if not use_fallback else (
        [primary] + [p for p in _fallback_chain() if p != primary]
    )

    last_err: Exception | None = None
    for attempt_provider in chain:
        try:
            client, model = _build_client(attempt_provider)
            if attempt_provider != primary:
                print(f"[llm] Falling back to provider='{attempt_provider}' model='{model}'",
                      file=sys.stderr)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""

        except RateLimitError as e:
            print(f"[llm] Rate limit on '{attempt_provider}': {e}", file=sys.stderr)
            last_err = e
            time.sleep(2)
        except APIConnectionError as e:
            print(f"[llm] Connection error on '{attempt_provider}': {e}", file=sys.stderr)
            last_err = e
        except APIStatusError as e:
            print(f"[llm] API error {e.status_code} on '{attempt_provider}': {e.message}",
                  file=sys.stderr)
            last_err = e
        except Exception as e:
            print(f"[llm] Unexpected error on '{attempt_provider}': {e}", file=sys.stderr)
            last_err = e

    raise RuntimeError(f"All providers failed. Last error: {last_err}")


def parse_action(raw: str) -> dict[str, Any]:
    """Parse LLM JSON response. Returns {} on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


def health_check(provider: str) -> dict[str, Any]:
    """Quick connectivity + auth test for a provider. Returns result dict."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return {"provider": provider, "ok": False, "error": "Unknown provider"}

    api_key_env = cfg.get("api_key_env")
    api_key     = os.getenv(api_key_env) if api_key_env else "nokey"

    if api_key_env and not api_key:
        return {
            "provider": provider,
            "ok":       False,
            "error":    f"Missing env var: {api_key_env}",
            "fix":      f"export {api_key_env}=your_key_here",
        }

    t0 = time.time()
    try:
        client, model = _build_client(provider)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": 'Reply with {"ok":true}'}],
            max_tokens=16,
            temperature=0,
        )
        latency_ms = round((time.time() - t0) * 1000)
        content    = resp.choices[0].message.content or ""
        return {
            "provider":   provider,
            "ok":         True,
            "model":      model,
            "latency_ms": latency_ms,
            "response":   content[:80],
        }
    except RateLimitError:
        return {"provider": provider, "ok": False, "error": "Rate limited (key works but quota hit)"}
    except APIStatusError as e:
        return {"provider": provider, "ok": False, "error": f"HTTP {e.status_code}: {e.message}"}
    except APIConnectionError:
        return {"provider": provider, "ok": False, "error": "Connection failed (check base_url / network)"}
    except Exception as e:
        return {"provider": provider, "ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# CLI entrypoint: python -m llm.providers [test|list] [provider]
# ---------------------------------------------------------------------------

def _cmd_list() -> None:
    print(f"\n{'Provider':<14} {'Free':<6} {'Default model':<45} {'Note'}")
    print("-" * 110)
    active = _active_provider()
    for name, cfg in PROVIDERS.items():
        marker = " ← active" if name == active else ""
        free   = "✓" if cfg["free"] else "$"
        print(f"{name:<14} {free:<6} {cfg['default_model']:<45} {cfg['note']}{marker}")
    print()
    print(f"Active provider : LLM_PROVIDER={active}")
    print(f"Active model    : LLM_MODEL={os.getenv('LLM_MODEL', '(provider default)')}")
    chain = _fallback_chain()
    print(f"Fallback chain  : {' -> '.join(chain)}")
    print("  Override with: LLM_FALLBACK_CHAIN=groq,openrouter,gemini\n")


def _cmd_test(targets: list[str]) -> None:
    if not targets:
        targets = [_active_provider()]
    print()
    for p in targets:
        result = health_check(p)
        status = "✅ OK" if result["ok"] else "❌ FAIL"
        print(f"  {status}  {p}")
        for k, v in result.items():
            if k not in ("provider", "ok"):
                print(f"         {k}: {v}")
        print()


if __name__ == "__main__":
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "list"
    args = sys.argv[2:]

    if cmd == "list":
        _cmd_list()
    elif cmd == "test":
        # test all known providers if 'all' passed
        if args == ["all"]:
            _cmd_test(list(PROVIDERS))
        else:
            _cmd_test(args or [_active_provider()])
    elif cmd == "models":
        p = args[0] if args else _active_provider()
        cfg = PROVIDERS.get(p, {})
        models = cfg.get("models", [])
        print(f"\nModels for '{p}':")
        for m in models:
            default_marker = " (default)" if m == cfg.get("default_model") else ""
            print(f"  {m}{default_marker}")
        print()
    else:
        print("Usage: python -m llm.providers [list | test [provider|all] | models [provider]]")
        sys.exit(1)
