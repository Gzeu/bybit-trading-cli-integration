# Options Trading

**Category**: `option`  
**Margin**: USDT (buyer pays premium, seller posts margin)  
**Settlement**: USDT  
**Style**: European (exercise at expiry only)  
**Underlying**: BTC, ETH

## When to use
- Buy call: bullish, limited downside (max loss = premium)
- Buy put: bearish hedge, limited downside
- Sell covered call: generate yield on BTC holdings
- Straddle: profit from volatility spike (buy call + put same strike)
- Defined-risk strategies when IV is low

## Key concepts

| Term | Meaning |
|---|---|
| IV (Implied Volatility) | Market’s expected volatility, drives premium |
| Delta | Price sensitivity to underlying move |
| Gamma | Rate of delta change |
| Theta | Time decay (options lose value daily) |
| Vega | Sensitivity to IV changes |
| Strike | Exercise price |
| Expiry | Settlement date (always Friday 08:00 UTC) |
| OTM | Out of the money — cheaper, higher leverage |
| ATM | At the money — highest theta decay |
| ITM | In the money — highest delta |

## Symbol format

```
BTC-26JUL24-60000-C   (BTC, expiry Jul 26 2024, strike $60k, Call)
BTC-26JUL24-60000-P   (BTC, expiry Jul 26 2024, strike $60k, Put)
```

## Core commands

```bash
# List available BTC options (tickers)
bybit-cli market tickers --category option --baseCoin BTC

# Get instruments (strikes + expiries)
bybit-cli market instruments-info --category option --baseCoin BTC

# Get orderbook for specific option
bybit-cli market orderbook --category option --symbol BTC-26JUL24-60000-C

# Buy a call (long bullish)
bybit-cli order create \
  --category option \
  --symbol BTC-26JUL24-65000-C \
  --side Buy --orderType Market \
  --qty 0.1 --yes

# Buy a put (hedge)
bybit-cli order create \
  --category option \
  --symbol BTC-26JUL24-55000-P \
  --side Buy --orderType Market \
  --qty 0.1 --yes

# Sell a covered call (generate yield)
bybit-cli order create \
  --category option \
  --symbol BTC-26JUL24-70000-C \
  --side Sell --orderType Limit \
  --price 500 --qty 0.1 --yes

# Open option positions
bybit-cli position info --category option --baseCoin BTC

# Option Greeks (from ticker)
bybit-cli market tickers --category option --symbol BTC-26JUL24-60000-C | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d['result']['list'][0]
print(f\"IV: {float(t.get('iv','0'))*100:.1f}% | Delta: {t.get('delta')} | Theta: {t.get('theta')} | Vega: {t.get('vega')}\")
"
```

## Strategies

### Straddle (profit from big move either direction)
```bash
# Buy ATM call + ATM put same expiry
bybit-cli order create --category option --symbol BTC-26JUL24-60000-C --side Buy --orderType Market --qty 0.1 --yes
bybit-cli order create --category option --symbol BTC-26JUL24-60000-P --side Buy --orderType Market --qty 0.1 --yes
```

### Protective put (hedge spot holdings)
```bash
# Hold 1 BTC spot, buy 1 put
bybit-cli order create --category option --symbol BTC-26JUL24-55000-P --side Buy --orderType Market --qty 1 --yes
```

### Bull call spread (reduce premium cost)
```bash
# Buy lower strike call, sell higher strike call
bybit-cli order create --category option --symbol BTC-26JUL24-60000-C --side Buy --orderType Market --qty 0.1 --yes
bybit-cli order create --category option --symbol BTC-26JUL24-65000-C --side Sell --orderType Market --qty 0.1 --yes
```

## Risk rules for options
- **Buying**: max loss = premium paid. No liquidation.
- **Selling naked**: unlimited risk. Always set max loss budget.
- **IV crush**: after news events, IV drops and option value collapses even if price moves right direction.
- Check theta decay daily — options lose value every day even if price stays flat.
