# Inverse Futures (Coin-Margined)

**Category**: `inverse`  
**Margin**: Base coin (BTC for BTCUSD, ETH for ETHUSD)  
**Settlement**: Base coin  
**Contract size**: $1 per contract (BTCUSD) or $10 (BTCUSDT inverse)

## When to use
- You hold BTC and want to hedge without converting to USDT
- Coin-denominated PnL (gain more BTC when right)
- Short during bear market while holding underlying
- No USDT needed — margin is your coin

## Key difference from linear

| | Linear | Inverse |
|---|---|---|
| Margin | USDT | BTC/ETH/SOL |
| PnL | USDT | Coin |
| Contract value | Variable (USDT) | Fixed ($1 or $10) |
| Liquidation risk | Lose USDT | Lose coin |

## Core commands

```bash
# Market short BTCUSD (hedge 100 contracts = $100)
bybit-cli order create \
  --category inverse --symbol BTCUSD \
  --side Sell --orderType Market \
  --qty 100 --yes

# Limit long
bybit-cli order create \
  --category inverse --symbol BTCUSD \
  --side Buy --orderType Limit \
  --price 58000 --qty 100 \
  --takeProfit 70000 --stopLoss 55000 --yes

# Set leverage
bybit-cli position set-leverage \
  --category inverse --symbol BTCUSD \
  --buyLeverage 3 --sellLeverage 3 --yes

# Position info
bybit-cli position info --category inverse --symbol BTCUSD

# Cancel all
bybit-cli order cancel-all --category inverse --symbol BTCUSD --yes

# Available inverse symbols
bybit-cli market instruments-info --category inverse | python3 -c "
import sys,json
d=json.load(sys.stdin)
for i in d['result']['list'][:10]: print(i['symbol'])
"

# Funding rate
bybit-cli market tickers --category inverse --symbol BTCUSD
```

## PnL calculation (inverse)

```
PnL (BTC) = contracts * (1/entry_price - 1/exit_price)
```

Example: Long 1000 BTCUSD contracts at $60,000, exit at $66,000
```
PnL = 1000 * (1/60000 - 1/66000) = 0.00152 BTC ≈ $100
```

## Hedge strategy example

```bash
# You hold 1 BTC spot. Hedge with inverse short:
# 1 BTC * $60,000 = $60,000 = 60,000 contracts
bybit-cli order create \
  --category inverse --symbol BTCUSD \
  --side Sell --orderType Market \
  --qty 60000 --yes
```

## Fees
- Maker: 0.01% | Taker: 0.06%
