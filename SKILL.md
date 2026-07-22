---
name: bybit-trading-cli-advanced
description: >
  Use when the user mentions Bybit trading, spot/futures/options/inverse operations,
  algorithmic strategies, risk management, position sizing, funding rate arbitrage,
  Kalman filter signals, regime detection, grid trading, or any Bybit V5 API interaction.
  Requires `bybit-official-trading-cli` npm package installed globally.
version: 2.0.0
---

# Bybit Trading CLI — Advanced Agent Skill

## 1. Bootstrap (ALWAYS run first)

```bash
bybit-cli agent-briefing
```

Returns ~300 words: auth setup, safety model, command exploration guide. **Read before any API call.**

---

## 2. Auth

### HMAC (default)
```bash
export BYBIT_API_KEY=<key>
export BYBIT_API_SECRET=<secret>
export BYBIT_ENV=testnet   # omit for mainnet
```

### RSA (uploaded public key on Bybit dashboard)
```bash
export BYBIT_API_KEY=<key>
export BYBIT_API_PRIVATE_KEY_PATH=/path/to/private.pem
```

---

## 3. Discovery

```bash
bybit-cli catalog                          # ~435 commands, ~30 domains, JSON
bybit-cli <domain> <cmd> --json-schema     # exact params + types
bybit-cli <domain> <cmd> --help            # human-readable
```

Key domains: `order`, `position`, `market`, `account`, `asset`, `spot`, `margin`, `lending`, `broker`, `ins-loan`

---

## 4. Core Trading Operations

### Place order (linear futures)
```bash
bybit-cli order create \
  --category linear \
  --symbol BTCUSDT \
  --side Buy \
  --orderType Market \
  --qty 0.01 \
  --cap-usd 500 \
  --yes
```

### Place limit order with TP/SL
```bash
bybit-cli order create \
  --category linear \
  --symbol BTCUSDT \
  --side Buy \
  --orderType Limit \
  --price 60000 \
  --qty 0.01 \
  --takeProfit 65000 \
  --stopLoss 58000 \
  --tpTriggerBy LastPrice \
  --slTriggerBy LastPrice \
  --cap-usd 500 \
  --yes
```

### Cancel order
```bash
bybit-cli order cancel --category linear --symbol BTCUSDT --orderId <id> --yes
```

### Amend order
```bash
bybit-cli order amend --category linear --symbol BTCUSDT --orderId <id> --price 61000 --yes
```

### Get open orders
```bash
bybit-cli order realtime --category linear --symbol BTCUSDT
```

### Get position
```bash
bybit-cli position info --category linear --symbol BTCUSDT
```

### Set leverage
```bash
bybit-cli position set-leverage --category linear --symbol BTCUSDT --buyLeverage 5 --sellLeverage 5 --yes
```

### Close position (market)
```bash
bybit-cli order create \
  --category linear \
  --symbol BTCUSDT \
  --side Sell \
  --orderType Market \
  --qty 0.01 \
  --reduceOnly true \
  --yes
```

---

## 5. Market Data

```bash
# Orderbook
bybit-cli market orderbook --category linear --symbol BTCUSDT --limit 50

# Klines / OHLCV
bybit-cli market kline --category linear --symbol BTCUSDT --interval 15 --limit 200

# Ticker
bybit-cli market tickers --category linear --symbol BTCUSDT

# Funding rate history
bybit-cli market funding-history --category linear --symbol BTCUSDT --limit 100

# Open interest
bybit-cli market open-interest --category linear --symbol BTCUSDT --intervalTime 5min

# Instruments info
bybit-cli market instruments-info --category linear --symbol BTCUSDT
```

---

## 6. Account & Risk

```bash
# Wallet balance
bybit-cli account wallet-balance --accountType UNIFIED

# Fee rate
bybit-cli account fee-rate --category linear --symbol BTCUSDT

# P&L history
bybit-cli position closed-pnl --category linear --limit 50

# Transaction log
bybit-cli account transaction-log --accountType UNIFIED --limit 50
```

---

## 7. Safety Rules (MANDATORY on mainnet)

| Guard | Usage |
|---|---|
| Confirmation gate | `--yes` required on every write |
| Per-order USD cap | `--cap-usd 500` |
| Rolling 1h total cap | `--cap-usd-total-hour 2000` |
| Rolling 1h order count | `--max-orders-per-hour 20` |
| Kill-switch | `bybit-cli kill-switch` blocks ALL writes |
| Re-enable | `bybit-cli enable-switch` |
| Advanced money ops | Withdraw/transfer need `--enable-advanced-money-ops` |
| Idempotency | `orderLinkId` auto-injected per retry |
| Integrity check | `bybit-cli verify` — SHA256 vs Bybit manifest |

**Always run testnet first. Never bypass `--yes` in automated pipelines without human review.**

---

## 8. Strategy Execution Guide

### Trend Following (EMA Cross)
- Fetch klines → compute EMA fast/slow → on cross: place market order with TP/SL
- Recommended: 1h / 4h candles, leverage ≤ 5x, risk 1-2% per trade

### Mean Reversion (Z-score)
- Compute rolling mean/std → z-score → enter when |z| > 2, exit when |z| < 0.5
- Best on ranging markets, use `regime_detection` to confirm

### Grid Trading
- Define price range + grid levels → place limit buy/sell pairs at each level
- Monitor fills → replace filled orders at next level

### Scalping
- Use orderbook imbalance + 1m klines → micro entries with tight SL (0.1-0.2%)
- Requires low-latency execution, keep `--max-orders-per-hour` high

### Breakout (ATR)
- Compute ATR(14) → set breakout threshold as `close ± 1.5×ATR`
- Enter on confirmed breakout candle close, SL at opposite ATR band

### Funding Rate Arbitrage
- Fetch funding rate history → if rate > 0.01% enter short futures + hedge spot
- Collect funding every 8h, exit when rate normalizes

### Kalman Filter
- Use Kalman filter as dynamic trend estimator → trade when price deviates from filter
- More adaptive than EMA, reduces lag on trend changes

### Regime Detection (HMM)
- Classify market into Bull / Bear / Sideways regimes
- Apply appropriate strategy per regime: trend strategies in Bull/Bear, grid/mean-reversion in Sideways

---

## 9. Output Shape

```json
{"retCode": 0, "retMsg": "OK", "result": {...}, "cli": {"env": "mainnet|testnet", "hint": "...", "retry": true, "nextSteps": [...]}}
```

- `retCode=0` → success
- `retCode≠0` → check `retMsg` + `cli.hint`
- `cli.retry=true` → safe to retry automatically
- `cli.nextSteps` → exact commands to unblock the situation
- Always use `--pretty` for human-readable JSON output

---

## 10. Telegram Alert Integration

After any fill or error, send alert:
```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d text="[BYBIT] Order filled: BTCUSDT BUY 0.01 @ 60000"
```

---

## 11. Troubleshooting

| Issue | Fix |
|---|---|
| `fetch failed: certificate` | `export NODE_EXTRA_CA_CERTS=/etc/ssl/cert.pem` |
| `retCode=10004` (invalid sign) | Check API key/secret, clock sync |
| `retCode=110007` (insufficient margin) | Reduce qty or leverage |
| Kill-switch active | `bybit-cli enable-switch` |
| Stale version | `bybit-cli self-update` |
