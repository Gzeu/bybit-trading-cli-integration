# Trading Strategies

All strategies use `bybit-official-trading-cli` as the execution layer.
Every strategy is standalone — run directly or import into an orchestrator.

## Complete Strategy Index (30 total)

### Trend Following
| File | Indicator | Timeframe |
|---|---|---|
| `trend_follow.py` | EMA 9/21 crossover | 1h |
| `triple_ema.py` | TEMA(21) slope | 1h |
| `supertrend.py` | SuperTrend ATR(10,3) | 1h |
| `parabolic_sar.py` | Parabolic SAR (0.02/0.2) | 1h |
| `ichimoku_cloud.py` | Ichimoku TK cross + cloud | 1h |
| `adx_trend_filter.py` | ADX(14) + DI+/DI- | 1h |
| `heikin_ashi_trend.py` | Heikin Ashi consecutive | 1h |
| `turtle_trading.py` | Donchian 20/55 breakout | Daily |
| `multi_timeframe.py` | EMA confluence 4h/1h/15m | Multi |

### Mean Reversion / Oscillators
| File | Indicator | Timeframe |
|---|---|---|
| `mean_reversion.py` | Z-score(50) ±2.0 | 1h |
| `bollinger_bands.py` | BB(20,2) band touch | 1h |
| `vwap_reversion.py` | VWAP deviation 0.5% | 15m |
| `rsi_divergence.py` | RSI(14) divergence | 1h |
| `macd_signal.py` | MACD(12,26,9) cross | 1h |
| `stochastic_rsi.py` | StochRSI(14) 20/80 | 1h |
| `cci_reversal.py` | CCI(20) ±100 exit | 1h |
| `williams_r.py` | Williams %R(14) | 1h |
| `momentum_roc.py` | ROC(10) threshold | 1h |

### Breakout / Volatility
| File | Indicator | Timeframe |
|---|---|---|
| `breakout.py` | ATR(14) × 1.5 bands | 1h |
| `liquidation_hunt.py` | Wick ratio detection | 15m |
| `open_interest_spike.py` | OI change + price dir | 5m |

### Arbitrage / Market Neutral
| File | Logic | Market |
|---|---|---|
| `funding_arb.py` | Funding rate hedge | Futures + Spot |
| `pairs_trading.py` | Spread z-score BTC/ETH | Futures |

### Systematic / Structural
| File | Logic | Market |
|---|---|---|
| `grid_trading.py` | Price range grid | Spot |
| `scalping.py` | Orderbook imbalance | Futures |
| `market_making.py` | Bid/ask quote skew | Spot |
| `dca_accumulation.py` | DCA + dip multiplier | Spot |
| `volatility_targeting.py` | Vol-adjusted sizing | Futures |

### Meta / Routing
| File | Logic |
|---|---|
| `kalman_filter.py` | Adaptive trend filter |
| `regime_detection.py` | Bull/Bear/Sideways router |

## Usage

```bash
# Run any strategy
python strategies/multi_timeframe.py

# Override symbol and qty via env
SYMBOL=ETHUSDT QTY=0.1 python strategies/bollinger_bands.py

# Always test on testnet first
export BYBIT_ENV=testnet
python strategies/regime_detection.py
```

## Safety reminder

All strategies use `--cap-usd`, `--yes`, and `--stopLoss` where applicable.
Run `bybit-cli kill-switch` at any time to halt all trading.
