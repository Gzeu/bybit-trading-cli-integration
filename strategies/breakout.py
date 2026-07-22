"""
Breakout Strategy v2 — ATR-based + volume confirmation
Improved: volume filter, multi-candle confirmation, R:R >= 2, dynamic sizing
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

ATR_MULT   = float(os.getenv("ATR_MULT", "1.5"))
RR_RATIO   = float(os.getenv("RR_RATIO", "2.0"))  # min reward:risk
CONFIRM_CANDLES = int(os.getenv("CONFIRM_CANDLES", "2"))  # candles must close beyond band

def run():
    if not safety_check(): return

    candles = get_klines(limit=100)
    c = closes(candles)
    current_atr = atr(candles)
    price = c[-1]
    prev_close = c[-2]

    upper_band = prev_close + ATR_MULT * current_atr
    lower_band = prev_close - ATR_MULT * current_atr

    # Volume confirmation
    vol = volumes(candles)
    avg_vol = sum(vol[-20:]) / 20
    vol_ok = vol[-1] > avg_vol * 1.2  # breakout needs 20%+ above avg volume

    # Multi-candle confirmation
    above_band = all(c[-(i+1)] > upper_band for i in range(CONFIRM_CANDLES))
    below_band = all(c[-(i+1)] < lower_band for i in range(CONFIRM_CANDLES))

    log_info(f"[BREAKOUT] price={price:.2f} upper={upper_band:.2f} lower={lower_band:.2f} ATR={current_atr:.2f} vol_ok={vol_ok}")

    pos = get_position()

    if above_band and vol_ok and (pos is None or pos["side"] == "Sell"):
        sl = round(price - current_atr, 2)
        stop_dist = price - sl
        tp = round(price + stop_dist * RR_RATIO, 2)
        qty = calc_qty(stop_distance=stop_dist)
        enter("Buy", qty, sl, tp, reason=f"Upside breakout ATR={current_atr:.0f} vol={vol[-1]:.0f}")

    elif below_band and vol_ok and (pos is None or pos["side"] == "Buy"):
        sl = round(price + current_atr, 2)
        stop_dist = sl - price
        tp = round(price - stop_dist * RR_RATIO, 2)
        qty = calc_qty(stop_distance=stop_dist)
        enter("Sell", qty, sl, tp, reason=f"Downside breakout ATR={current_atr:.0f} vol={vol[-1]:.0f}")

    else:
        log_info(f"[BREAKOUT] No confirmed breakout (vol_ok={vol_ok})")

if __name__ == "__main__":
    run()
