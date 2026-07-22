"""
Multi-Timeframe — Limit PostOnly, 15-min expiry, fee-aware sizing.
Requires alignment: 4H trend + 1H entry signal (EMA crossover both TFs).
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr, ema,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

EMA_FAST   = int(os.getenv("MTF_EMA_FAST", "9"))
EMA_SLOW   = int(os.getenv("MTF_EMA_SLOW", "21"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("MTF_EXPIRY_SEC", "900"))
ATR_MULT   = float(os.getenv("MTF_ATR_MULT", "1.5"))


def run(symbol=None, category=None):
    if not safety_check(): return
    # Higher timeframe trend (4H)
    c4h = closes(get_klines(interval="240", limit=50, symbol=symbol, category=category))
    if len(c4h) < EMA_SLOW + 5: return
    trend_bull = ema(c4h, EMA_FAST) > ema(c4h, EMA_SLOW)
    trend_bear = ema(c4h, EMA_FAST) < ema(c4h, EMA_SLOW)
    # Entry timeframe signal (1H)
    candles1h = get_klines(interval="60", limit=50, symbol=symbol, category=category)
    if len(candles1h) < EMA_SLOW + 5: return
    c1h = closes(candles1h)
    fast1h = ema(c1h, EMA_FAST); slow1h = ema(c1h, EMA_SLOW)
    prev_fast = ema(c1h[:-1], EMA_FAST); prev_slow = ema(c1h[:-1], EMA_SLOW)
    cross_up   = prev_fast <= prev_slow and fast1h > slow1h
    cross_down = prev_fast >= prev_slow and fast1h < slow1h
    if (trend_bull and cross_up):
        side = "Buy"
    elif (trend_bear and cross_down):
        side = "Sell"
    else:
        log_info(f"[mtf] no aligned signal"); return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    atr_v   = atr(candles1h)
    sl_dist = ATR_MULT * atr_v
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="multi_timeframe")
    min_move = net_min_move(price)
    if sl_dist < min_move * 1.5: log_info(f"[mtf] stop < min_move — skip"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="multi_timeframe", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[mtf] {side} qty={op.qty} lp={lp} sl={sl} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason="mtf_aligned", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
