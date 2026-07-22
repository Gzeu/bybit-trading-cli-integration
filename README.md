# bybit-trading-cli-integration

> Advanced AI agent integration layer for [bybit-official-trading-cli](https://github.com/bybit-exchange/trading-cli) — V5 API, multi-strategy automation, free LLM decision layer, safety guards, Telegram bot support.

## Stack

- **Runtime**: Node 20.6+ / Python 3.11+
- **CLI**: `bybit-official-trading-cli` (npm)
- **Auth**: HMAC or RSA
- **Strategies**: Trend-follow, Mean-reversion, Grid, Scalping, Breakout, Funding Rate Arb, Kalman Filter, Regime Detection
- **LLM Agent**: Groq / OpenRouter / Gemini / Ollama — free tier, no paid API required
- **Safety**: Kill-switch, per-order caps, hourly caps, idempotency
- **Alerts**: Telegram bot

## Install

```bash
npm i -g bybit-official-trading-cli@latest
cp .env.example .env
# fill in your keys
pip install openai   # only extra dep for LLM agent
```

## Quick start

```bash
bybit-cli agent-briefing          # read this first
bybit-cli catalog                 # ~435 commands across ~30 domains
```

## Strategies

| File | Type | Market |
|---|---|---|
| `strategies/trend_follow.py` | Trend following (EMA cross) | Futures |
| `strategies/mean_reversion.py` | Z-score mean reversion | Spot / Futures |
| `strategies/grid_trading.py` | Grid (range) | Spot |
| `strategies/scalping.py` | High-frequency scalping | Futures |
| `strategies/breakout.py` | Volatility breakout (ATR) | Futures |
| `strategies/funding_arb.py` | Funding rate arbitrage | Futures |
| `strategies/kalman_filter.py` | Kalman filter trend | Futures |
| `strategies/regime_detection.py` | HMM regime detection | Any |

## LLM Agent (free, zero cost)

Stratul LLM decide acțiunea de trading. Execuția rămâne pe `core/engine.py` + `bybit-cli`.

```
Market Snapshot (core/engine.py --snapshot)
        ↓
  llm/agent_loop.py
        ↓  (system prompt + briefing + snapshot)
  LLM free (Groq / OpenRouter / Gemini / Ollama)
        ↓  JSON { action, strategy, side, qty, sl, tp, reason }
  Whitelist validation
        ↓
  core/engine.py --action ...  (execuție reală)
        ↓
  Telegram notify
```

### Provideri free

| Provider | Model | Viteză | Note |
|---|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | ~1000 tok/s | Default, cel mai rapid |
| **Groq** | `llama-3.3-70b-versatile` | ~280 tok/s | Raționament complex |
| **OpenRouter** | `meta-llama/llama-3.1-8b-instruct:free` | Variabil | Fallback multi-model |
| **Gemini** | `gemini-2.0-flash-lite` | Rapid | Backup stabil |
| **Ollama** | `llama3.2` (local) | Hardware propriu | Offline, zero cloud |

### Configurare `.env`

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.1-8b-instant
```

### Rulare

```bash
# O singură decizie (testnet first)
python llm/agent_loop.py --once

# Loop la 15 minute
python llm/agent_loop.py --interval 900

# Analiză fără ordine
python llm/agent_loop.py --dry-run
```

### Snapshot engine (folosit de agent)

```bash
# Afișează market + account state ca JSON
python -m core.engine --snapshot

# Output compact (pentru pipe)
python -m core.engine --snapshot --json
```

### Limitări free tier

- **Groq**: ~30 RPM pe model — 1 decizie / câteva minute, nu chat continuu
- **Whitelist strict**: LLM poate emite doar `open_long | open_short | close_position | reduce_size | hold | wait`
- **Testnet first**: mainnet doar după confirmare manuală
- **8B** pentru routing simplu; **70B** pentru raționament complex când ai cotă

## Safety model

See `SKILL.md` for the full agent context and safety rules.

## License

MIT
