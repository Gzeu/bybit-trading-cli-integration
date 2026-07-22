"""
Trend Following Strategy v2 — EMA Crossover
Improved: dynamic sizing, ATR stop, close opposite, logging, Telegram, safety check
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

FAST = int(os.getenv("EMA_FAST", "9"))
SLOW = int(os.getenv("EMA_SLOW", "21"))
ATR_MULT_SL = float(os.getenv("ATR_MULT_SL", "1.5"))
ATR_MULT_TP = float(os.getenv("ATR_MULT_TP", "3.0"))

def run():
    if not safety_check(): return

    candles = get_klines(limit=200)
    if not candles:
        log_error("[TREND] No candle data")
        return

    c = closes(candles)
    fast_ema = ema(c, FAST)
    slow_ema = ema(c, SLOW)
    fast_prev = ema(c[:-1], FAST)
    slow_prev = ema(c[:-1], SLOW)
    price = c[-1]
    current_atr = atr(candles)

    # Require actual cross (not just above/below)
    cross_up   = fast_prev <= slow_prev and fast_ema > slow_ema
    cross_down = fast_prev >= slow_prev and fast_ema < slow_ema

    log_info(f"[TREND] price={price:.2f} fast={fast_ema:.2f} slow={slow_ema:.2f} ATR={current_atr:.2f} cross_up={cross_up} cross_down={cross_down}")

    pos = get_position()

    if cross_up and (pos is None or pos["side"] == "Sell"):
        sl = round(price - ATR_MULT_SL * current_atr, 2)
        tp = round(price + ATR_MULT_TP * current_atr, 2)
        qty = calc_qty(stop_distance=price - sl)
        set_leverage()
        enter("Buy", qty, sl, tp, reason=f"EMA cross UP fast={fast_ema:.0f} slow={slow_ema:.0f}")

    elif cross_down and (pos is None or pos["side"] == "Buy"):
        sl = round(price + ATR_MULT_SL * current_atr, 2)
        tp = round(price - ATR_MULT_TP * current_atr, 2)
        qty = calc_qty(stop_distance=sl - price)
        set_leverage()
        enter("Sell", qty, sl, tp, reason=f"EMA cross DOWN fast={fast_ema:.0f} slow={slow_ema:.0f}")

    else:
        log_info(f"[TREND] No cross signal")

if __name__ == "__main__":
    run()
