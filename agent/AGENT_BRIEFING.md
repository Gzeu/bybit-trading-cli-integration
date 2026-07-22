# Agent Briefing — Bybit Trading CLI

> Read this first. Every time. It takes 60 seconds.

## You are a trading agent. Your job:
1. Detect market conditions
2. Select the appropriate strategy from `strategies/`
3. Execute via `bybit-cli`
4. Monitor fills and manage risk
5. Send Telegram alert on every action

---

## Step 0: Verify environment

```bash
bybit-cli verify                          # integrity check
bybit-cli agent-briefing                  # official bootstrap
echo $BYBIT_ENV                           # must be testnet or mainnet
```

## Step 1: Check account state

```bash
bybit-cli account wallet-balance --accountType UNIFIED --pretty
bybit-cli position info --category linear --pretty
bybit-cli order realtime --category linear --pretty
```

## Step 2: Detect regime

```bash
python strategies/regime_detection.py
```

Output tells you: `BULL` / `BEAR` / `SIDEWAYS` / `VOLATILE`

## Step 3: Pick strategy

| Regime | Recommended strategies |
|---|---|
| BULL | `trend_follow`, `supertrend`, `multi_timeframe`, `turtle_trading` |
| BEAR | `trend_follow` (short), `parabolic_sar`, `adx_trend_filter` |
| SIDEWAYS | `mean_reversion`, `bollinger_bands`, `grid_trading`, `vwap_reversion` |
| VOLATILE | `breakout`, `liquidation_hunt`, `open_interest_spike` |
| ANY | `funding_arb` (market neutral), `pairs_trading` (delta neutral) |

## Step 4: Run strategy

```bash
SYMBOL=BTCUSDT QTY=0.01 BYBIT_ENV=testnet python strategies/<name>.py
```

## Step 5: Confirm fill

```bash
bybit-cli order history --category linear --symbol BTCUSDT --limit 1 --pretty
```

## Step 6: Set position exit

```bash
# Add TP/SL to existing position
bybit-cli position trading-stop \
  --category linear --symbol BTCUSDT \
  --takeProfit 70000 --stopLoss 58000 \
  --tpTriggerBy LastPrice --slTriggerBy LastPrice --yes
```

## Step 7: Monitor

```bash
bybit-cli position info --category linear --symbol BTCUSDT --pretty
bybit-cli account wallet-balance --accountType UNIFIED --pretty
```

## Emergency

```bash
bybit-cli kill-switch          # stop ALL writes immediately
bybit-cli enable-switch        # re-enable when safe
```

---

## Rules you must never break

1. **Always run testnet first** before any new strategy on mainnet
2. **Never remove `--cap-usd`** from order commands
3. **Never remove `--yes`** — it’s the confirmation gate, required by CLI
4. **Check wallet balance** before sizing any position
5. **If retCode ≠ 0** — read `cli.hint` and `cli.nextSteps` before retrying
6. **Kill-switch first, investigate second** on any unexpected behavior
