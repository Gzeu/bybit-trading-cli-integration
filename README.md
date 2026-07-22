# bybit-trading-cli-integration

> Advanced AI agent integration layer for [bybit-official-trading-cli](https://github.com/bybit-exchange/trading-cli) — V5 API, 26 strategies, free LLM decision layer, safety guards, Telegram alerts.

## Quick start

```bash
git clone https://github.com/Gzeu/bybit-trading-cli-integration
cd bybit-trading-cli-integration
bash scripts/setup.sh        # installs deps, creates .env, tests LLM
nano .env                    # fill BYBIT_API_KEY + GROQ_API_KEY
bash scripts/health_check.sh # verify everything is green
```

First decision (no orders):
```bash
python llm/agent_loop.py --dry-run --once
```

Live loop (testnet, every 15 min):
```bash
python llm/agent_loop.py --interval 900
```

## Stack

| Layer | Tech |
|---|---|
| Exchange CLI | `bybit-official-trading-cli` (npm, Node 20+) |
| Trading engine | `core/engine.py` (Python 3.11+) |
| LLM decision | `llm/` — Groq / OpenRouter / Gemini / Ollama (free) |
| Auth | HMAC or RSA |
| Safety | Kill-switch, per-order caps, hourly caps, daily loss guard |
| Alerts | Telegram bot |

## Architecture

```
Market Snapshot  ←→  core/engine.py --snapshot
       ↓
llm/agent_loop.py
       ↓   system prompt + briefing + snapshot
LLM free  (Groq / OpenRouter / Gemini / Ollama)
       ↓   JSON { action, strategy, side, qty, sl, tp, reason }
Whitelist validation
       ↓
core/engine.py --action ...    (real execution via bybit-cli)
       ↓
Telegram notify
```

LLM **decides only** — execution stays in `core/engine.py` + `bybit-cli`. The whitelist blocks anything outside `open_long | open_short | close_position | reduce_size | hold | wait`.

## LLM providers (free)

| Provider | Model | Speed | Limit |
|---|---|---|---|
| **Groq** | `llama-3.1-8b-instant` | ~1000 tok/s | ~30 RPM free |
| **Groq** | `llama-3.3-70b-versatile` | ~280 tok/s | ~30 RPM free |
| **OpenRouter** | `meta-llama/llama-3.1-8b-instruct:free` | Variable | Free models |
| **Gemini** | `gemini-2.0-flash-lite` | Fast | RPM/RPD strict |
| **Ollama** | `llama3.2` local | Hardware | Unlimited |

Test all providers:
```bash
bash llm/connect.sh all
```

Switch provider in `.env`:
```bash
LLM_PROVIDER=groq          # groq | openrouter | gemini | ollama
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.1-8b-instant
LLM_FALLBACK_CHAIN=groq,openrouter,gemini   # auto-fallback order
```

## Strategies (26)

| File | Strategy | Type | Market |
|---|---|---|---|
| `trend_follow.py` | EMA crossover trend following | Trend | Futures |
| `mean_reversion.py` | Z-score mean reversion | Mean-rev | Spot/Futures |
| `grid_trading.py` | Range grid | Grid | Spot |
| `scalping.py` | High-frequency scalping | Scalp | Futures |
| `breakout.py` | ATR volatility breakout | Breakout | Futures |
| `funding_arb.py` | Funding rate arbitrage | Arb | Futures |
| `kalman_filter.py` | Kalman filter trend | Quant | Futures |
| `regime_detection.py` | HMM market regime | Quant | Any |
| `bollinger_bands.py` | Bollinger band reversion | Mean-rev | Any |
| `macd_signal.py` | MACD histogram signal | Trend | Any |
| `rsi_divergence.py` | RSI divergence | Reversal | Any |
| `stochastic_rsi.py` | Stochastic RSI overbought/oversold | Oscillator | Any |
| `adx_trend_filter.py` | ADX trend strength filter | Trend | Futures |
| `supertrend.py` | Supertrend ATR | Trend | Futures |
| `ichimoku_cloud.py` | Ichimoku cloud signals | Trend | Any |
| `heikin_ashi_trend.py` | Heikin Ashi smoothed trend | Trend | Any |
| `parabolic_sar.py` | Parabolic SAR stops | Trend | Futures |
| `triple_ema.py` | Triple EMA ribbon | Trend | Futures |
| `turtle_trading.py` | Donchian channel breakout | Breakout | Futures |
| `vwap_reversion.py` | VWAP reversion | Mean-rev | Spot/Futures |
| `williams_r.py` | Williams %R oscillator | Oscillator | Any |
| `cci_reversal.py` | CCI reversal | Reversal | Any |
| `momentum_roc.py` | Rate of change momentum | Momentum | Any |
| `volatility_targeting.py` | Vol-targeted position sizing | Risk | Any |
| `market_making.py` | Basic market making | MM | Spot |
| `dca_accumulation.py` | DCA accumulation | DCA | Spot |
| `multi_timeframe.py` | Multi-timeframe confirmation | Confluence | Futures |
| `pairs_trading.py` | Statistical pairs trading | Stat-arb | Spot |
| `open_interest_spike.py` | OI spike signal | On-chain | Futures |
| `liquidation_hunt.py` | Liquidation level targeting | Flow | Futures |

Run any strategy directly:
```bash
python strategies/trend_follow.py
python strategies/scalping.py
```

## Safety model

- `MAX_RISK_PCT` — max % of balance per trade (default 1%)
- `CAP_USD` — max single order size in USDT
- `BYBIT_CAP_USD_TOTAL_HOUR` — hourly cap
- `BYBIT_MAX_ORDERS_PER_HOUR` — order rate cap
- Daily loss kill-switch: auto-triggers if PnL > `max_daily_loss_pct` (3% default)
- LLM whitelist: only 6 actions allowed, no shell access
- Testnet by default (`BYBIT_ENV=testnet`)

Full agent context: see [`SKILL.md`](SKILL.md) and [`agent/AGENT_BRIEFING.md`](agent/AGENT_BRIEFING.md)

## File structure

```
.
├── core/
│   └── engine.py          # shared engine: CLI wrapper, indicators, sizing, logging
├── llm/
│   ├── providers.py       # multi-provider client (Groq/OpenRouter/Gemini/Ollama/...)
│   ├── agent_loop.py      # main loop: snapshot → LLM → validate → engine
│   ├── SYSTEM_PROMPT.md   # strict JSON-only prompt with whitelist
│   ├── connect.sh         # provider test helper
│   └── README.md
├── strategies/            # 26+ strategy files
├── agent/
│   ├── AGENT_BRIEFING.md
│   ├── DECISION_TREE.md
│   └── PROMPT_TEMPLATES.md
├── scripts/
│   ├── setup.sh           # one-shot setup
│   ├── health_check.sh    # full system check with colored output
│   ├── run_strategy.sh
│   └── daily_report.sh
├── logs/                  # auto-created, gitignored
├── .env.example
├── requirements.txt
└── .gitignore
```

## License

MIT
