"""
Mean Reversion Strategy v2 — Z-score
Improved: ATR stop, dynamic sizing, RSI filter, volume filter, logging
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

LOOKBACK   = int(os.getenv("LOOKBACK", "50"))
ENTRY_Z    = float(os.getenv("ENTRY_Z", "2.0"))
EXIT_Z     = float(os.getenv("EXIT_Z", "0.5"))
ATR_MULT   = float(os.getenv("ATR_MULT", "1.0"))
RSI_FILTER = True  # only enter if RSI confirms

def run():
    if not safety_check(): return

    candles = get_klines(limit=200)
    c = closes(candles)
    z = zscore(c, LOOKBACK)
    current_atr = atr(candles)
    price = c[-1]
    rsi_val = rsi(c)
    vol = volumes(candles)
    avg_vol = sum(vol[-20:]) / 20
    high_vol = vol[-1] > avg_vol * 0.8  # at least 80% avg volume

    log_info(f"[MEAN-REV] price={price:.2f} z={z:.3f} RSI={rsi_val:.1f} vol_ok={high_vol}")

    pos = get_position()

    if z < -ENTRY_Z and (not RSI_FILTER or rsi_val < 45) and high_vol:
        if pos is None or pos["side"] == "Sell":
            sl = round(price - ATR_MULT * current_atr, 2)
            tp = round(price + abs(z) * current_atr, 2)  # TP scales with z-score
            qty = calc_qty(stop_distance=price - sl)
            enter("Buy", qty, sl, tp, reason=f"Z={z:.2f} RSI={rsi_val:.1f} oversold")

    elif z > ENTRY_Z and (not RSI_FILTER or rsi_val > 55) and high_vol:
        if pos is None or pos["side"] == "Buy":
            sl = round(price + ATR_MULT * current_atr, 2)
            tp = round(price - abs(z) * current_atr, 2)
            qty = calc_qty(stop_distance=sl - price)
            enter("Sell", qty, sl, tp, reason=f"Z={z:.2f} RSI={rsi_val:.1f} overbought")

    elif abs(z) < EXIT_Z and pos:
        log_info(f"[MEAN-REV] Z near 0 — closing {pos['side']}")
        close_position(pos)
        alert(f"⏹ Closed {pos['side']} {SYMBOL} | Z returned to {z:.2f}")

    else:
        log_info(f"[MEAN-REV] No signal")

if __name__ == "__main__":
    run()
