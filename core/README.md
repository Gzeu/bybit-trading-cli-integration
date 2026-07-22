# core/engine.py — Shared Trading Engine

All strategies import from `core.engine`. Never duplicate logic in individual strategy files.

## What engine provides

| Function | Description |
|---|---|
| `cli(*args)` | CLI wrapper with retry + error logging |
| `get_klines(interval, limit)` | Fetch OHLCV candles |
| `get_ticker()` | Current price, funding rate, 24h data |
| `get_balance()` | UNIFIED wallet equity |
| `get_position()` | Current open position (None if flat) |
| `get_funding_rate()` | Current funding rate |
| `closes/highs/lows/volumes(candles)` | Extract price series from candles |
| `ema(prices, period)` | EMA value |
| `ema_series(prices, period)` | Full EMA series |
| `atr(candles, period)` | ATR(14) |
| `rsi(closes, period)` | RSI(14) |
| `zscore(prices, lookback)` | Z-score |
| `calc_qty(stop_distance)` | Dynamic position sizing (fixed fractional) |
| `calc_atr_stop(candles, side)` | ATR-based stop level |
| `set_leverage(leverage)` | Set leverage before entry |
| `close_position(pos)` | Market close existing position |
| `enter(side, qty, sl, tp, reason)` | Full entry: close opposite + order + log + alert |
| `log_info/log_error(msg)` | Timestamped log to file + stdout |
| `log_trade(...)` | Append trade record to `logs/trades.jsonl` |
| `alert(msg)` | Telegram notification (silent if not configured) |
| `safety_check()` | Daily loss limit + kill-switch activation |

## Environment variables

```bash
SYMBOL=BTCUSDT          # trading pair
CATEGORY=linear          # spot | linear | inverse | option
BYBIT_ENV=testnet        # testnet | mainnet
CAP_USD=500              # per-order USD cap
MAX_RISK_PCT=0.01        # 1% of balance per trade
LEVERAGE=5               # default leverage
LOG_DIR=logs             # log directory
TELEGRAM_BOT_TOKEN=...   # optional
TELEGRAM_CHAT_ID=...     # optional
```

## Usage in a strategy

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

def run():
    if not safety_check(): return  # daily loss limit

    candles = get_klines(limit=200)
    price = closes(candles)[-1]
    current_atr = atr(candles)

    sl = round(price - 1.5 * current_atr, 2)
    tp = round(price + 3.0 * current_atr, 2)
    qty = calc_qty(stop_distance=price - sl)

    enter("Buy", qty, sl, tp, reason="my signal")
```
