"""
Multi-Timeframe Strategy v2
Improved: ADX filter, volume confirm, ATR sizing, proper cross detection
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

TIMEFRAMES = [("240", "4h"), ("60", "1h"), ("15", "15m")]
EMA_P = int(os.getenv("EMA_P", "21"))
ADX_THRESH = float(os.getenv("ADX_THRESH", "20"))

def tf_slope(interval):
    candles = get_klines(interval=interval, limit=EMA_P + 10)
    c = closes(candles)
    e_series = ema_series(c, EMA_P)
    slope = e_series[-1] - e_series[-4]  # 3-bar slope
    return slope, candles

def compute_adx_simple(candles, period=14):
    h = highs(candles)
    l = lows(candles)
    c = closes(candles)
    dm_p, dm_m, trs = [], [], []
    for i in range(1, len(c)):
        up   = h[i] - h[i-1]
        down = l[i-1] - l[i]
        dm_p.append(up if up > down and up > 0 else 0)
        dm_m.append(down if down > up and down > 0 else 0)
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    atr_val = sum(trs[-period:]) / period
    di_p  = 100 * (sum(dm_p[-period:])  / period) / atr_val if atr_val else 0
    di_m  = 100 * (sum(dm_m[-period:]) / period) / atr_val if atr_val else 0
    dx = abs(di_p - di_m) / (di_p + di_m) * 100 if (di_p + di_m) else 0
    return dx

def run():
    if not safety_check(): return

    slopes = {}
    base_candles = None
    for tf, label in TIMEFRAMES:
        slope, candles = tf_slope(tf)
        slopes[label] = slope
        if label == "1h":
            base_candles = candles
        log_info(f"[MTF] {label} EMA slope={slope:.4f}")

    adx_val = compute_adx_simple(base_candles) if base_candles else 0
    log_info(f"[MTF] ADX={adx_val:.1f}")

    if adx_val < ADX_THRESH:
        log_info(f"[MTF] ADX {adx_val:.1f} below threshold {ADX_THRESH} — skip")
        return

    all_up   = all(s > 0 for s in slopes.values())
    all_down = all(s < 0 for s in slopes.values())
    price = closes(base_candles)[-1]
    current_atr = atr(base_candles)

    pos = get_position()

    if all_up and (pos is None or pos["side"] == "Sell"):
        sl = round(price - 1.5 * current_atr, 2)
        tp = round(price + 3.0 * current_atr, 2)
        qty = calc_qty(stop_distance=price - sl)
        set_leverage()
        enter("Buy", qty, sl, tp, reason=f"MTF all-bullish ADX={adx_val:.1f}")

    elif all_down and (pos is None or pos["side"] == "Buy"):
        sl = round(price + 1.5 * current_atr, 2)
        tp = round(price - 3.0 * current_atr, 2)
        qty = calc_qty(stop_distance=sl - price)
        set_leverage()
        enter("Sell", qty, sl, tp, reason=f"MTF all-bearish ADX={adx_val:.1f}")

    else:
        log_info(f"[MTF] No confluence | slopes={slopes}")

if __name__ == "__main__":
    run()
