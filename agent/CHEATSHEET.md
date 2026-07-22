# Bybit CLI Cheatsheet — Most Used Commands

## ⚡ Quick reference for agent execution

### Market Data
```bash
# Price
bybit-cli market tickers --category linear --symbol BTCUSDT

# Candles (interval: 1 3 5 15 30 60 120 240 360 720 D W M)
bybit-cli market kline --category linear --symbol BTCUSDT --interval 60 --limit 200

# Orderbook
bybit-cli market orderbook --category linear --symbol BTCUSDT --limit 25

# Funding rate (current)
bybit-cli market tickers --category linear --symbol BTCUSDT | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['list'][0]['fundingRate'])"

# Funding history
bybit-cli market funding-history --category linear --symbol BTCUSDT --limit 10

# Open Interest
bybit-cli market open-interest --category linear --symbol BTCUSDT --intervalTime 5min --limit 5

# All linear tickers (scan for opportunity)
bybit-cli market tickers --category linear
```

### Orders
```bash
# Market buy
bybit-cli order create --category linear --symbol BTCUSDT --side Buy --orderType Market --qty 0.01 --cap-usd 500 --yes

# Limit buy with TP/SL
bybit-cli order create --category linear --symbol BTCUSDT --side Buy --orderType Limit --price 60000 --qty 0.01 --takeProfit 65000 --stopLoss 58000 --cap-usd 500 --yes

# Cancel single order
bybit-cli order cancel --category linear --symbol BTCUSDT --orderId <id> --yes

# Cancel ALL open orders
bybit-cli order cancel-all --category linear --symbol BTCUSDT --yes

# Open orders
bybit-cli order realtime --category linear --symbol BTCUSDT

# Order history
bybit-cli order history --category linear --symbol BTCUSDT --limit 10
```

### Positions
```bash
# View position
bybit-cli position info --category linear --symbol BTCUSDT

# Set leverage
bybit-cli position set-leverage --category linear --symbol BTCUSDT --buyLeverage 5 --sellLeverage 5 --yes

# Add TP/SL to open position
bybit-cli position trading-stop --category linear --symbol BTCUSDT --takeProfit 70000 --stopLoss 58000 --yes

# Close position (market)
bybit-cli order create --category linear --symbol BTCUSDT --side Sell --orderType Market --qty 0.01 --reduceOnly true --yes

# PnL history
bybit-cli position closed-pnl --category linear --limit 20
```

### Account
```bash
# Balance
bybit-cli account wallet-balance --accountType UNIFIED

# Fee rate
bybit-cli account fee-rate --category linear --symbol BTCUSDT

# Transaction log
bybit-cli account transaction-log --accountType UNIFIED --limit 20
```

### Safety
```bash
bybit-cli kill-switch             # STOP all writes
bybit-cli enable-switch           # re-enable
bybit-cli verify                  # integrity check
bybit-cli self-update             # update CLI
```

### Spot
```bash
bybit-cli order create --category spot --symbol BTCUSDT --side Buy --orderType Market --qty 0.001 --cap-usd 200 --yes
bybit-cli order create --category spot --symbol BTCUSDT --side Sell --orderType Limit --price 70000 --qty 0.001 --timeInForce GTC --cap-usd 200 --yes
```

### Inverse (coin-margined)
```bash
bybit-cli order create --category inverse --symbol BTCUSD --side Buy --orderType Market --qty 100 --yes
```
