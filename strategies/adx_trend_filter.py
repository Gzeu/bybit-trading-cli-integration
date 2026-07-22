"""
ADX Trend Filter — Limit PostOnly, fee-aware sizing, 10-min expiry.
Logic: ADX>25 + DI+/DI- crossover for direction.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, atr,
    enter, close_position, safety_check, log_info, LEVERAGE,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

ADX_THRESH = float(os.getenv("ADX_THRESH", "25"))
ADX_PERIOD = int(os.getenv("ADX_PERIOD", "14"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("ADX_EXPIRY_SEC", "600"))
ATR_MULT   = float(os.getenv("ADX_ATR_MULT", "1.5"))


def compute_adx(candles, period=14):
    h = [float(c[2]) for c in candles]
    l = [float(c[3]) for c in candles]
    c = [float(c[4]) for c in candles]
    dm_p, dm_m, trs = [], [], []
    for i in range(1, len(c)):
        up   = h[i] - h[i-1]
        down = l[i-1] - l[i]
        dm_p.append(up   if up > down and up > 0   else 0)
        dm_m.append(down if down > up and down > 0 else 0)
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    atr_v  = sum(trs[-period:]) / period
    di_p   = 100 * (sum(dm_p[-period:]) / period) / atr_v if atr_v else 0
    di_m   = 100 * (sum(dm_m[-period:]) / period) / atr_v if atr_v else 0
    dx     = abs(di_p - di_m) / (di_p + di_m) * 100 if (di_p + di_m) > 0 else 0
    return di_p, di_m, dx


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=60, symbol=symbol, category=category)
    if len(candles) < 30: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    di_p, di_m, adx = compute_adx(candles, ADX_PERIOD)
    log_info(f"[adx] DI+={di_p:.2f} DI-={di_m:.2f} ADX={adx:.2f}")
    if adx <= ADX_THRESH:
        log_info(f"[adx] weak trend ({adx:.2f}) — hold"); return
    side    = "Buy" if di_p > di_m else "Sell"
    atr_v   = atr(candles)
    sl_dist = ATR_MULT * atr_v
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="adx_trend_filter")
    min_move = net_min_move(price)
    if sl_dist < min_move * 1.5: log_info(f"[adx] stop < min_move — skip"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="adx_trend_filter", expiry_seconds=EXPIRY_S)
    lp  = round(bid if side=="Buy" else ask, 2)
    sl  = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp  = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[adx] {side} qty={op.qty} lp={lp} sl={sl} tp={tp} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: log_info(f"[adx] already {side}"); return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason="adx_trend", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
