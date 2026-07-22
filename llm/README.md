# llm/ — Free LLM Agent for bybit-trading-cli-integration

Adaugă un strat de decizie LLM (Groq / OpenRouter / Gemini / Ollama) **fără costuri**.
Trading-ul real rămâne pe `core/engine.py` + `bybit-cli`. LLM-ul **doar decide**, nu execută.

## Arhitectură

```
Market Snapshot (engine --snapshot)
        ↓
  llm/agent_loop.py
        ↓  (system prompt + briefing + snapshot)
  LLM free (Groq/OpenRouter/Gemini/Ollama)
        ↓  JSON { action, strategy, side, qty, sl, tp, reason }
  Whitelist validation
        ↓
  core/engine.py --action ... (execuție reală)
        ↓
  Telegram notify
```

## Instalare

```bash
pip install openai  # singurul dep suplimentar — toți providerii sunt OAI-compat
```

## Configurare `.env`

Copiază blocul LLM din `.env.example` și completează:

```bash
LLM_PROVIDER=groq               # groq | openrouter | gemini | ollama
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.1-8b-instant  # sau llama-3.3-70b-versatile pentru raționament greu
```

## Utilizare

```bash
# O singură decizie
python llm/agent_loop.py --once

# Loop la 15 minute
python llm/agent_loop.py --interval 900

# Analiză fără ordine
python llm/agent_loop.py --dry-run

# Combinat: loop + dry-run
python llm/agent_loop.py --interval 300 --dry-run
```

## Provideri free (2026)

| Provider | Model recomandat | Rate limit free | Note |
|---|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | ~30 RPM | Cel mai rapid (~280–1000 tok/s) |
| **Groq** | `llama-3.3-70b-versatile` | ~30 RPM | Pentru raționament complex |
| **OpenRouter** | `meta-llama/llama-3.1-8b-instruct:free` | Variabil | Fallback multi-model |
| **Gemini** | `gemini-2.0-flash-lite` | RPM/RPD stricte | Backup stabil |
| **Ollama** | `llama3.2` (local) | Nelimitat | Zero cloud, offline |

## Limitări importante

- **Rate limits Groq free**: sparge request-urile — 1 decizie / câteva minute, nu chat continuu.
- **Nu lăsa LLM-ul să scrie comenzi shell** — whitelist strict în `validate_action()`.
- **Testnet first** — mainnet doar după confirmare manuală.
- Modelele 8B sunt OK pentru routing simplu; pentru raționament complex folosește 70B când ai cotă.

## Fișiere

| Fișier | Rol |
|---|---|
| `providers.py` | Client multi-provider (Groq/OpenRouter/Gemini/Ollama) |
| `agent_loop.py` | Loop principal: snapshot → LLM → validare → engine |
| `SYSTEM_PROMPT.md` | Prompt sistem: reguli stricte + format JSON |
| `README.md` | Documentație |
