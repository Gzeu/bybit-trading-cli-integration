# Copy Trading

**API support**: Via V5 `/v5/copy-trading/*` endpoints  
**Category**: `linear` (copy trading uses linear perpetuals)  
**Role**: You can be a **follower** (copy masters) or a **master** (others copy you)

## When to use
- Automate following a proven trader
- Run your own strategy as a master and earn profit share
- Reduce time on active management

## Follower commands

```bash
# List available masters to follow
bybit-cli copy-trading master-list

# Your copy trading wallet
bybit-cli copy-trading wallet-balance

# Active copy positions
bybit-cli copy-trading position-list

# Active copy orders
bybit-cli copy-trading order-list

# Close a copy trading position
bybit-cli copy-trading close-order \
  --symbol BTCUSDT \
  --side Sell \
  --orderType Market \
  --qty 0.01 --yes

# Transfer to copy trading wallet
bybit-cli asset transfer-inter \
  --fromAccountType UNIFIED \
  --toAccountType COPYTRADING \
  --coin USDT --amount 500 --yes
```

## Master trader commands

```bash
# Place order as master (followers copy proportionally)
bybit-cli copy-trading create-order \
  --symbol BTCUSDT \
  --side Buy \
  --orderType Market \
  --qty 0.1 \
  --takeProfit 70000 \
  --stopLoss 58000 --yes

# Your master P&L
bybit-cli copy-trading master-position-list
```

## Copy trading safety
- Copy trading positions are **separate** from regular trading account
- Use `bybit-cli copy-trading wallet-balance` to monitor exposure
- Kill-switch does NOT affect copy trading — close positions manually
- Max drawdown for masters: Bybit auto-disables at -50% in rolling 30 days
