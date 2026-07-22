"""
Bollinger Bands Mean Reversion — Limit PostOnly, 5-min expiry.
Long when price < lower band, Short when price > upper band.
"""
import os, sys, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

BB_PERIOD  = int(os.getenv("BB_PERIOD", "20"))
BB_STD     = float(os.getenv("BB_STD", "2.0"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("BB_EXPIRY_SEC", "300"))
ATR_MULT   = float(os.getenv("BB_ATR_MULT", "1.2"))


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=BB_PERIOD+10, symbol=symbol, category=category)
    if len(candles) < BB_PERIOD: return
    ticker = get_ticker(symbol, category)
    price  = float(ticker.get("lastPrice", 0))
    bid    = float(ticker.get("bid1Price", price))
    ask    = float(ticker.get("ask1Price", price))
    spread = (ask - bid) / price * 100 if price else 0
    c = closes(candles)[-BB_PERIOD:]
    mean   = statistics.mean(c)
    std    = statistics.stdev(c)
    upper  = mean + BB_STD * std
    lower  = mean - BB_STD * std
    atr_v  = atr(candles)
    balance= get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="bollinger_bands")
    min_move = net_min_move(price)
    sl_dist  = ATR_MULT * atr_v
    tp_dist  = std  # revert to mean
    if tp_dist < min_move * 1.5: log_info(f"[bb] tp < min_move — skip"); return
    if price < lower:
        side = "Buy"
    elif price > upper:
        side = "Sell"
    else:
        log_info(f"[bb] price={price:.2f} inside bands [{lower:.2f},{upper:.2f}]"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="bollinger_bands", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + tp_dist if side=="Buy" else price - tp_dist, 2)
    log_info(f"[bb] {side} qty={op.qty} lp={lp} sl={sl} tp={tp} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason="bb_reversion", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
