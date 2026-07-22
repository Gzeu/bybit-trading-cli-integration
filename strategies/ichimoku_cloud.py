"""
Ichimoku Cloud — Limit PostOnly, 15-min expiry, fee-aware sizing.
Bull: price above cloud + Tenkan > Kijun.
Bear: price below cloud + Tenkan < Kijun.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

TENKAN   = int(os.getenv("ICHI_TENKAN", "9"))
KIJUN    = int(os.getenv("ICHI_KIJUN", "26"))
SENKOU_B = int(os.getenv("ICHI_SENKOU_B", "52"))
RISK_PCT = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S = int(os.getenv("ICHI_EXPIRY_SEC", "900"))
ATR_MULT = float(os.getenv("ICHI_ATR_MULT", "1.5"))


def midpoint(vals): return (max(vals) + min(vals)) / 2


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=SENKOU_B+10, symbol=symbol, category=category)
    if len(candles) < SENKOU_B: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    h = [float(c[2]) for c in candles]
    l = [float(c[3]) for c in candles]
    tenkan   = midpoint(h[-TENKAN:]  + l[-TENKAN:])
    kijun    = midpoint(h[-KIJUN:]   + l[-KIJUN:])
    senkou_a = (tenkan + kijun) / 2
    senkou_b = midpoint(h[-SENKOU_B:] + l[-SENKOU_B:])
    cloud_top = max(senkou_a, senkou_b)
    cloud_bot = min(senkou_a, senkou_b)
    atr_v   = atr(candles)
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="ichimoku_cloud")
    min_move = net_min_move(price)
    sl_dist  = ATR_MULT * atr_v
    if sl_dist < min_move * 1.5: log_info(f"[ichi] stop < min_move — skip"); return
    if price > cloud_top and tenkan > kijun:
        side = "Buy"
    elif price < cloud_bot and tenkan < kijun:
        side = "Sell"
    else:
        log_info(f"[ichi] inside cloud or no TK cross — hold"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="ichimoku_cloud", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[ichi] {side} qty={op.qty} lp={lp} sl={sl} tp={tp} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason="ichimoku_cloud", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
