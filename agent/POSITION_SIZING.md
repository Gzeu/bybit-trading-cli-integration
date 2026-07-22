# Position Sizing Guide

Never size positions by gut feel. Use one of these methods.

## Method 1: Fixed Fractional (simplest)

```
Risk per trade = 1% of balance
Stop distance = entry_price - stop_loss_price
Qty = (balance * 0.01) / stop_distance
```

```bash
# Get balance
BALANCE=$(bybit-cli account wallet-balance --accountType UNIFIED | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(d['result']['list'][0]['totalEquity'])
")

# Example: balance=10000, entry=60000, SL=58800 (2% stop)
# stop_dist = 60000 - 58800 = 1200
# qty = (10000 * 0.01) / 1200 = 0.083 BTC
echo "Balance: $BALANCE"
```

## Method 2: Kelly Criterion

```
f = (p * b - q) / b
Where:
  p = win rate (from backtest/trade history)
  q = 1 - p (loss rate)
  b = avg_win / avg_loss ratio
  f = fraction of capital to risk

Use half-Kelly (f/2) for safety.
```

```bash
# Get win rate from last 50 trades
bybit-cli position closed-pnl --category linear --limit 50 | python3 -c "
import sys, json
d = json.load(sys.stdin)
trades = d['result']['list']
wins = [t for t in trades if float(t['closedPnl']) > 0]
losses = [t for t in trades if float(t['closedPnl']) <= 0]
p = len(wins) / len(trades) if trades else 0
avg_win = sum(float(t['closedPnl']) for t in wins) / len(wins) if wins else 0
avg_loss = abs(sum(float(t['closedPnl']) for t in losses) / len(losses)) if losses else 1
b = avg_win / avg_loss
f = (p * b - (1-p)) / b
print(f'Win rate: {p:.2%}  Avg win: {avg_win:.2f}  Avg loss: {avg_loss:.2f}  Kelly: {f:.3f}  Half-Kelly: {f/2:.3f}')
"
```

## Method 3: ATR-based sizing

```
Risk = 1% balance
ATR = current ATR(14)
Stop = 1.5 * ATR
Qty = Risk / Stop
```

## Caps (always enforce)

| Rule | Value |
|---|---|
| Max risk per trade | 2% of balance |
| Max open positions | 5 |
| Max total exposure | 50% of balance |
| Max leverage | 10x (5x recommended) |
| Min confidence score | 6/9 |
