# Strategy × Trading Type Matrix

Which strategies work with which trading type.

| Strategy | Spot | Linear | Inverse | Options | Margin |
|---|:---:|:---:|:---:|:---:|:---:|
| `trend_follow` | – | ✓ | ✓ | ✓ call/put | ✓ |
| `mean_reversion` | ✓ | ✓ | – | – | ✓ |
| `grid_trading` | ✓ | ✓ | – | – | ✓ |
| `scalping` | ✓ | ✓ | ✓ | – | – |
| `breakout` | ✓ | ✓ | ✓ | ✓ straddle | ✓ |
| `funding_arb` | ✓ hedge | ✓ short | ✓ short | – | ✓ |
| `kalman_filter` | – | ✓ | ✓ | – | ✓ |
| `regime_detection` | ✓ router | ✓ router | ✓ router | ✓ router | ✓ router |
| `bollinger_bands` | ✓ | ✓ | ✓ | – | ✓ |
| `rsi_divergence` | ✓ | ✓ | ✓ | ✓ timing | ✓ |
| `macd_signal` | ✓ | ✓ | ✓ | ✓ timing | ✓ |
| `vwap_reversion` | ✓ | ✓ | ✓ | – | ✓ |
| `ichimoku_cloud` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `supertrend` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `parabolic_sar` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `adx_trend_filter` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `turtle_trading` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `multi_timeframe` | – | ✓ | ✓ | – | ✓ |
| `pairs_trading` | ✓ | ✓ | – | – | ✓ |
| `market_making` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `dca_accumulation` | ✓ | – | – | ✓ sell put | ✓ |
| `volatility_targeting` | – | ✓ | ✓ | ✓ vega | ✓ |
| `open_interest_spike` | – | ✓ | ✓ | ✓ | – |
| `liquidation_hunt` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `stochastic_rsi` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `heikin_ashi_trend` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `cci_reversal` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `williams_r` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `momentum_roc` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `triple_ema` | ✓ | ✓ | ✓ | ✓ | ✓ |

## Risk ranking by type

| Type | Risk | Liquidation | Funding cost |
|---|---|---|---|
| Spot | Low | No | No |
| Margin | Medium | Yes (margin call) | Yes (borrow rate) |
| Inverse | High | Yes | Yes (every 8h) |
| Linear | High | Yes | Yes (every 8h) |
| Options (buyer) | Defined | No | No (theta decay) |
| Options (seller) | Very High | Yes | No |

## Category param per type

```bash
CATEGORY=spot       # Spot + Margin
CATEGORY=linear     # USDT-margined
CATEGORY=inverse    # Coin-margined
CATEGORY=option     # Options
```

## Override any strategy to a different type

```bash
# Run bollinger_bands on inverse instead of linear
SYMBOL=BTCUSD CATEGORY=inverse python3 strategies/bollinger_bands.py

# Run mean_reversion on spot
SYMBOL=BTCUSDT CATEGORY=spot python3 strategies/mean_reversion.py

# Run grid on margin (leveraged)
SYMBOL=BTCUSDT CATEGORY=spot python3 strategies/grid_trading.py
```
