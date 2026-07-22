# Linear Futures (USDT-Margined)

**Category**: `linear`  
**Margin**: USDT (stablecoin)  
**Types**: Perpetual (no expiry) + Delivery (quarterly)  
**Settlement**: USDT  
**Max leverage**: Up to 100x (BTC), varies per symbol

## When to use
- Directional speculation with leverage
- Hedging spot holdings
- Funding rate collection/arbitrage
- Most liquid crypto derivatives market

## Key concepts
- **Perpetual**: no expiry, funding every 8h
- **Delivery**: expires at settlement date (e.g. BTCUSDT-31DEC25)
- **Margin modes**: Isolated (per position) vs Cross (shared wallet)
- **Position modes**: One-way vs Hedge (both long+short open)

## Core commands

```bash
# Set isolated margin mode
bybit-cli position switch-margin \
  --category linear --symbol BTCUSDT \
  --tradeMode 1 --buyLeverage 5 --sellLeverage 5 --yes

# Set cross margin mode
bybit-cli position switch-margin \
  --category linear --symbol BTCUSDT \
  --tradeMode 0 --buyLeverage 5 --sellLeverage 5 --yes

# Set leverage
bybit-cli position set-leverage \
  --category linear --symbol BTCUSDT \
  --buyLeverage 5 --sellLeverage 5 --yes

# Switch to hedge mode (allow simultaneous long+short)
bybit-cli position switch-mode \
  --category linear --symbol BTCUSDT --mode 3 --yes

# Market long
bybit-cli order create \
  --category linear --symbol BTCUSDT \
  --side Buy --orderType Market --qty 0.01 \
  --cap-usd 500 --yes

# Limit short with TP/SL
bybit-cli order create \
  --category linear --symbol BTCUSDT \
  --side Sell --orderType Limit --price 70000 --qty 0.01 \
  --takeProfit 65000 --stopLoss 72000 \
  --tpTriggerBy LastPrice --slTriggerBy LastPrice \
  --cap-usd 500 --yes

# Trailing stop (activate when 1% in profit)
bybit-cli position trading-stop \
  --category linear --symbol BTCUSDT \
  --trailingStop 500 --activePrice 61000 --yes

# Add margin to isolated position
bybit-cli position add-margin \
  --category linear --symbol BTCUSDT \
  --margin 100 --yes

# Position info
bybit-cli position info --category linear --symbol BTCUSDT

# Delivery contracts list
bybit-cli market instruments-info --category linear --status Trading | python3 -c "
import sys,json
d=json.load(sys.stdin)
delivery=[i for i in d['result']['list'] if i.get('contractType')=='LinearFutures']
for i in delivery: print(i['symbol'], i.get('deliveryTime',''))
"
```

## Funding rate mechanics

```bash
# Current funding rate + next funding time
bybit-cli market tickers --category linear --symbol BTCUSDT | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d['result']['list'][0]
print(f\"Rate: {float(t['fundingRate'])*100:.4f}% | Next: {t['nextFundingTime']}\")
"

# Funding history (last 10 periods)
bybit-cli market funding-history --category linear --symbol BTCUSDT --limit 10
```

## Linear strategies
```bash
python3 strategies/trend_follow.py
python3 strategies/multi_timeframe.py
python3 strategies/funding_arb.py
python3 strategies/supertrend.py
python3 strategies/adx_trend_filter.py
```

## Fees
- Maker: 0.02% | Taker: 0.055%
- Funding: every 8h at 00:00, 08:00, 16:00 UTC
