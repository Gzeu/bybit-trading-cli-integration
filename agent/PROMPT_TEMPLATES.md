# Prompt Templates for AI Agents

Copy-paste these prompts directly into Claude Code, Cursor, or any agent.

---

## Template 1: Full autonomous trading session

```
You are a Bybit trading agent. Use the bybit-official-trading-cli.

1. Run `bybit-cli agent-briefing` and read it fully
2. Check wallet balance and open positions
3. Run `python strategies/regime_detection.py` to detect market regime
4. Consult `agent/DECISION_TREE.md` to select strategy
5. Score the signal using the confidence table (need score >= 6 to enter full size)
6. Run the selected strategy with BYBIT_ENV=testnet first
7. If testnet successful, ask me before running on mainnet
8. After any fill, send Telegram alert and log to `logs/trades.jsonl`
9. Monitor position every 15 minutes
10. Apply kill-switch if daily loss exceeds 3% of balance

SYMBOL=BTCUSDT QTY=0.01
```

---

## Template 2: Market scan + opportunity detection

```
Scan Bybit linear futures for trading opportunities:

1. `bybit-cli market tickers --category linear` — get all tickers
2. Filter for 24h volume > $50M
3. For top 5 by volume: fetch klines and compute RSI(14)
4. Flag any with RSI < 30 (oversold) or RSI > 70 (overbought)
5. Check funding rate for each flagged symbol
6. Return ranked list with: symbol, RSI, funding_rate, recommended_strategy
```

---

## Template 3: Risk check before session

```
Before trading, perform full risk assessment:

1. `bybit-cli account wallet-balance --accountType UNIFIED` — get balance
2. `bybit-cli position info --category linear` — list all open positions
3. Calculate total exposure as % of balance
4. Check if any position has no stop-loss set
5. Check if daily PnL from `bybit-cli position closed-pnl --category linear --limit 20` is below -3%
6. If exposure > 50% balance OR daily loss > 3%: run `bybit-cli kill-switch`
7. Report: balance, exposure%, daily_pnl%, positions_without_sl
```

---

## Template 4: Strategy backtest via kline data

```
Backtest `strategies/trend_follow.py` logic on historical data:

1. Fetch 500 candles: `bybit-cli market kline --category linear --symbol BTCUSDT --interval 60 --limit 200`
2. Simulate EMA 9/21 crossover signals on the data
3. Calculate: total trades, win rate, avg profit per trade, max drawdown, Sharpe ratio
4. Show equity curve as ASCII chart
5. Compare results for BTCUSDT, ETHUSDT, SOLUSDT
```

---

## Template 5: Emergency position cleanup

```
Emergency cleanup procedure:

1. `bybit-cli kill-switch` — stop all new orders
2. `bybit-cli order cancel-all --category linear --yes` — cancel all open orders
3. `bybit-cli position info --category linear` — list all open positions
4. For each open position: close at market with --reduceOnly true
5. `bybit-cli account wallet-balance --accountType UNIFIED` — final balance
6. Report: positions_closed, total_realized_pnl, final_balance
7. `bybit-cli enable-switch` only after confirming all positions closed
```

---

## Template 6: Funding rate scanner

```
Find best funding rate arbitrage opportunities right now:

1. Get top 20 linear symbols by OI
2. For each: fetch current funding rate from tickers
3. Sort by abs(funding_rate) descending
4. For top 3: check if spot market exists on Bybit
5. Calculate estimated 8h yield after fees (taker fee ~0.055%)
6. Return table: symbol | funding_rate | 8h_yield | recommended_side
```
