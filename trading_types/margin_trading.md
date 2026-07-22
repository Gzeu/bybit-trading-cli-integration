# Margin Trading

**Category**: `spot` (with margin enabled)  
**Margin**: Borrowed USDT or coin from Bybit lending pool  
**Max leverage**: Up to 10x (varies by asset)  
**Risk**: Margin call and liquidation if equity falls below maintenance margin

## When to use
- Leveraged spot exposure without perpetual funding costs
- Short selling spot assets
- Access liquidity without selling existing holdings

## Account types
- **Unified Margin Account (UMA)**: cross-margin across spot, linear, options
- **Classic Margin**: isolated to spot only

## Core commands

```bash
# Check margin account info
bybit-cli account wallet-balance --accountType UNIFIED

# Borrow USDT
bybit-cli margin borrow \
  --coin USDT --qty 1000 --yes

# Repay borrowed USDT
bybit-cli margin repay \
  --coin USDT --qty 1000 --yes

# Check borrow limit
bybit-cli margin borrow-able-amount --coin USDT

# Check active loans
bybit-cli margin interest-record --coin USDT --limit 10

# Borrow rate
bybit-cli margin borrow-rate --coin USDT

# Buy on margin (borrow USDT, buy BTC)
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Buy --orderType Market \
  --qty 0.01 --isLeverage 1 \
  --cap-usd 1000 --yes

# Short on margin (borrow BTC, sell it)
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Sell --orderType Market \
  --qty 0.01 --isLeverage 1 \
  --cap-usd 1000 --yes

# Risk rate (liquidation proximity)
bybit-cli account wallet-balance --accountType UNIFIED | python3 -c "
import sys,json
d=json.load(sys.stdin)
acc=d['result']['list'][0]
print(f\"Margin ratio: {acc.get('marginRatio','N/A')} | Maintenance: {acc.get('totalMaintenanceMargin','N/A')}\") 
"
```

## Margin safety rules

| Alert level | Action |
|---|---|
| Margin ratio > 80% | Reduce position or add collateral |
| Margin ratio > 90% | Close half the position immediately |
| Margin ratio > 95% | Close all, repay loan |
| Margin call received | Bybit auto-liquidates if not resolved |

```bash
# Emergency: close margin position + repay
bybit-cli order create --category spot --symbol BTCUSDT --side Sell --orderType Market --qty 0.01 --yes
bybit-cli margin repay --coin USDT --qty 1000 --yes
```

## Interest calculation
```
Daily interest = borrowed_amount * hourly_rate * 24
Check rate: bybit-cli margin borrow-rate --coin USDT
```
