"""
MACD Signal — Limit PostOnly, 10-min expiry, fee-aware sizing.
Signal: MACD line crosses signal line.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr, ema_series,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

MACD_FAST  = int(os.getenv("MACD_FAST", "12"))
MACD_SLOW  = int(os.getenv("MACD_SLOW", "26"))
MACD_SIG   = int(os.getenv("MACD_SIGNAL", "9"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("MACD_EXPIRY_SEC", "600"))
ATR_MULT   = float(os.getenv("MACD_ATR_MULT", "1.5"))


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
    if len(candles) < MACD_SLOW + MACD_SIG + 5: return
    ticker = get_ticker(symbol, category)
    price  = float(ticker.get("lastPrice", 0))
    bid    = float(ticker.get("bid1Price", price))
    ask    = float(ticker.get("ask1Price", price))
    spread = (ask - bid) / price * 100 if price else 0
    c      = closes(candles)
    fast_s = ema_series(c, MACD_FAST)
    slow_s = ema_series(c, MACD_SLOW)
    macd   = [f - s for f, s in zip(fast_s, slow_s)]
    sig    = ema_series(macd, MACD_SIG)
    cross_up   = macd[-2] <= sig[-2] and macd[-1] > sig[-1]
    cross_down = macd[-2] >= sig[-2] and macd[-1] < sig[-1]
    if not cross_up and not cross_down: log_info(f"[macd] no crossover"); return
    side   = "Buy" if cross_up else "Sell"
    atr_v  = atr(candles)
    sl_dist = ATR_MULT * atr_v
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="macd_signal")
    min_move = net_min_move(price)
    if sl_dist < min_move * 1.5: log_info(f"[macd] stop < min_move — skip"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="macd_signal", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[macd] {side} macd={macd[-1]:.4f} sig={sig[-1]:.4f} qty={op.qty} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason="macd_cross", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
