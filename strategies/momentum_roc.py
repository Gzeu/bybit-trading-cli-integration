"""
Momentum ROC — Limit PostOnly, 10-min expiry, fee-aware sizing.
Signal: Rate of Change > threshold (bullish) or < -threshold (bearish).
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

ROC_PERIOD  = int(os.getenv("ROC_PERIOD", "14"))
ROC_THRESH  = float(os.getenv("ROC_THRESH", "2.0"))  # %
RISK_PCT    = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S    = int(os.getenv("ROC_EXPIRY_SEC", "600"))
ATR_MULT    = float(os.getenv("ROC_ATR_MULT", "1.5"))


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=ROC_PERIOD+10, symbol=symbol, category=category)
    if len(candles) < ROC_PERIOD + 2: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    c       = closes(candles)
    roc     = (c[-1] - c[-ROC_PERIOD-1]) / c[-ROC_PERIOD-1] * 100
    atr_v   = atr(candles)
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="momentum_roc")
    min_move = net_min_move(price)
    sl_dist  = ATR_MULT * atr_v
    if sl_dist < min_move * 1.5: log_info(f"[roc] stop < min_move — skip"); return
    if roc > ROC_THRESH:
        side = "Buy"
    elif roc < -ROC_THRESH:
        side = "Sell"
    else:
        log_info(f"[roc] ROC={roc:.2f}% within +-{ROC_THRESH}% — hold"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="momentum_roc", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[roc] {side} ROC={roc:.2f}% qty={op.qty} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason=f"roc_{roc:.2f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
