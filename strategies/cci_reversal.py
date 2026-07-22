"""
CCI Reversal — Limit PostOnly, fee-aware, 5-min expiry.
Long when CCI < -100, Short when CCI > +100.
"""
import os, sys, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move

CCI_PERIOD = int(os.getenv("CCI_PERIOD", "20"))
CCI_THRESH = float(os.getenv("CCI_THRESH", "100"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("CCI_EXPIRY_SEC", "300"))
ATR_MULT   = float(os.getenv("CCI_ATR_MULT", "1.2"))


def compute_cci(candles, period):
    tp = [(float(c[2])+float(c[3])+float(c[4]))/3 for c in candles[-period:]]
    mean = statistics.mean(tp)
    mad  = statistics.mean([abs(x - mean) for x in tp])
    return (tp[-1] - mean) / (0.015 * mad) if mad else 0


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=CCI_PERIOD+10, symbol=symbol, category=category)
    if len(candles) < CCI_PERIOD: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    cci_val = compute_cci(candles, CCI_PERIOD)
    atr_v   = atr(candles)
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="cci_reversal")
    min_move = net_min_move(price)
    sl_dist  = ATR_MULT * atr_v
    if sl_dist < min_move * 1.5: log_info(f"[cci] stop < min_move — skip"); return
    if cci_val < -CCI_THRESH:
        side = "Buy"
    elif cci_val > CCI_THRESH:
        side = "Sell"
    else:
        log_info(f"[cci] CCI={cci_val:.1f} — hold"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="cci_reversal", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[cci] {side} CCI={cci_val:.1f} qty={op.qty} lp={lp} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason=f"cci_{cci_val:.0f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
