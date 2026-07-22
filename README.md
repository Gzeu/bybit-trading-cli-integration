# bybit-trading-cli-integration

> Advanced AI agent integration layer for [bybit-official-trading-cli](https://github.com/bybit-exchange/trading-cli) — V5 API, multi-strategy automation, safety guards, Telegram bot support.

## Stack

- **Runtime**: Node 20.6+ / Python 3.11+
- **CLI**: `bybit-official-trading-cli` (npm)
- **Auth**: HMAC or RSA
- **Strategies**: Trend-follow, Mean-reversion, Grid, Scalping, Breakout, Funding Rate Arb, Kalman Filter, Regime Detection
- **Safety**: Kill-switch, per-order caps, hourly caps, idempotency
- **Alerts**: Telegram bot

## Install

```bash
npm i -g bybit-official-trading-cli@latest
cp .env.example .env
# fill in your keys
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

## Safety model

See `SKILL.md` for the full agent context and safety rules.

## License

MIT
