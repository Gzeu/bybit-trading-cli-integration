"""
Kalman Filter Mean Reversion — Limit PostOnly, 5-min expiry.
Estimates true price with Kalman; trades when residual exceeds 1.5 std.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

Q        = float(os.getenv("KALMAN_Q", "1e-5"))
R        = float(os.getenv("KALMAN_R", "1e-2"))
RESID_TH = float(os.getenv("KALMAN_RESID_TH", "1.5"))
RISK_PCT = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S = int(os.getenv("KALMAN_EXPIRY_SEC", "300"))
ATR_MULT = float(os.getenv("KALMAN_ATR_MULT", "1.2"))


def kalman_estimate(prices, Q=1e-5, R=1e-2):
    x, p = prices[0], 1.0
    residuals = []
    for z in prices[1:]:
        p += Q
        K  = p / (p + R)
        residuals.append(z - x)
        x += K * (z - x)
        p *= (1 - K)
    return x, residuals


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
    if len(candles) < 50: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    c       = closes(candles)
    est, residuals = kalman_estimate(c, Q, R)
    import statistics as st
    std  = st.stdev(residuals[-30:]) if len(residuals) >= 2 else 1
    last_resid = residuals[-1]
    atr_v   = atr(candles)
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="kalman_filter")
    min_move = net_min_move(price)
    sl_dist  = ATR_MULT * atr_v
    if sl_dist < min_move * 1.5: log_info(f"[kalman] stop < min_move — skip"); return
    if last_resid > RESID_TH * std:
        side = "Sell"  # price above estimate
    elif last_resid < -RESID_TH * std:
        side = "Buy"
    else:
        log_info(f"[kalman] resid={last_resid:.4f} within {RESID_TH}*std={RESID_TH*std:.4f} — hold"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="kalman_filter", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[kalman] {side} resid={last_resid:.4f} qty={op.qty} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason=f"kalman_resid_{last_resid:.4f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
