# Spot Trading

**Category**: `spot`  
**Margin**: None — you spend what you have  
**Settlement**: Immediate delivery of base asset  
**Risk**: No liquidation risk (no leverage by default)

## When to use
- Long-term accumulation (DCA)
- Grid trading in ranging markets
- Holding actual BTC/ETH/SOL
- Funding rate arb hedge leg
- Low-risk entry before adding futures leverage

## Key concepts
- **Base asset**: BTC in BTCUSDT
- **Quote asset**: USDT in BTCUSDT
- **Min order qty**: check `instruments-info`
- **Lot size filter**: qty must be multiple of `basePrecision`

## Core commands

```bash
# Market buy (spend USDT, receive BTC)
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Buy --orderType Market \
  --qty 0.001 --cap-usd 100 --yes

# Market sell
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Sell --orderType Market \
  --qty 0.001 --cap-usd 100 --yes

# Limit buy (GTC)
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Buy --orderType Limit \
  --price 58000 --qty 0.001 \
  --timeInForce GTC --cap-usd 100 --yes

# Limit sell with IOC
bybit-cli order create \
  --category spot --symbol BTCUSDT \
  --side Sell --orderType Limit \
  --price 72000 --qty 0.001 \
  --timeInForce IOC --cap-usd 100 --yes

# Cancel all spot orders
bybit-cli order cancel-all --category spot --symbol BTCUSDT --yes

# Open spot orders
bybit-cli order realtime --category spot --symbol BTCUSDT

# Spot balance (how much BTC/USDT you hold)
bybit-cli account wallet-balance --accountType SPOT

# All spot tickers
bybit-cli market tickers --category spot

# Instruments info (min qty, step size)
bybit-cli market instruments-info --category spot --symbol BTCUSDT
```

## Order types available on spot

| Type | CLI value | Notes |
|---|---|---|
| Market | `Market` | Fills immediately at best price |
| Limit | `Limit` | Requires `--price` |
| Limit Maker | `Limit` + `--timeInForce PostOnly` | Maker-only, rejected if crosses book |
| Stop Market | `MARKET` + `--triggerPrice` | Triggers at price |
| Stop Limit | `LIMIT` + `--triggerPrice` + `--price` | Trigger then limit |

## Spot strategies

```bash
# DCA
SYMBOL=BTCUSDT python3 strategies/dca_accumulation.py

# Grid
SYMBOL=BTCUSDT CATEGORY=spot python3 strategies/grid_trading.py

# Market making on spot
SYMBOL=BTCUSDT CATEGORY=spot python3 strategies/market_making.py
```

## Fees
- Maker: 0.1% | Taker: 0.1% (VIP discounts apply)
- Check your rate: `bybit-cli account fee-rate --category spot --symbol BTCUSDT`
