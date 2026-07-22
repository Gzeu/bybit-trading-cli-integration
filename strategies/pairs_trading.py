"""
Pairs Trading — Limit PostOnly on spread reversion between two symbols.
Fee-aware: spread z-score must be > 2.5 to cover dual-leg commission.
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

SYMBOL_A   = os.getenv("PAIRS_SYMBOL_A", "BTCUSDT")
SYMBOL_B   = os.getenv("PAIRS_SYMBOL_B", "ETHUSDT")
ZSCORE_TH  = float(os.getenv("PAIRS_ZSCORE_TH", "2.5"))
LOOKBACK   = int(os.getenv("PAIRS_LOOKBACK", "60"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.008"))
EXPIRY_S   = int(os.getenv("PAIRS_EXPIRY_SEC", "600"))
ATR_MULT   = float(os.getenv("PAIRS_ATR_MULT", "1.2"))


def run(symbol=None, category=None):
    if not safety_check(): return
    cat = category or "linear"
    ca = closes(get_klines(interval="60", limit=LOOKBACK+5, symbol=SYMBOL_A, category=cat))
    cb = closes(get_klines(interval="60", limit=LOOKBACK+5, symbol=SYMBOL_B, category=cat))
    n  = min(len(ca), len(cb), LOOKBACK)
    if n < 20: return
    ratio  = [a/b for a, b in zip(ca[-n:], cb[-n:])]
    mean   = statistics.mean(ratio)
    std    = statistics.stdev(ratio)
    zscore = (ratio[-1] - mean) / std if std > 0 else 0
    ta = get_ticker(SYMBOL_A, cat); tb = get_ticker(SYMBOL_B, cat)
    pa = float(ta.get("lastPrice", 0)); pb = float(tb.get("lastPrice", 0))
    bid_a = float(ta.get("bid1Price", pa)); ask_a = float(ta.get("ask1Price", pa))
    bid_b = float(tb.get("bid1Price", pb)); ask_b = float(tb.get("ask1Price", pb))
    spread_a = (ask_a - bid_a) / pa * 100 if pa else 0
    spread_b = (ask_b - bid_b) / pb * 100 if pb else 0
    # Need both spreads tight for pairs to be profitable
    if spread_a > 0.05 or spread_b > 0.05:
        log_info(f"[pairs] spread too wide a={spread_a:.3f}% b={spread_b:.3f}%"); return
    if abs(zscore) < ZSCORE_TH: log_info(f"[pairs] zscore={zscore:.2f} — hold"); return
    # ratio > mean: A expensive vs B -> sell A, buy B
    side_a = "Sell" if zscore > 0 else "Buy"
    side_b = "Buy"  if zscore > 0 else "Sell"
    balance = get_balance(); free_mg = get_free_margin()
    can_a = get_klines(interval="60", limit=20, symbol=SYMBOL_A, category=cat)
    atr_a = atr(can_a)
    sl_dist_a = ATR_MULT * atr_a
    min_move_a = net_min_move(pa)
    if sl_dist_a < min_move_a * 1.5: log_info(f"[pairs] stop_a < min_move — skip"); return
    order_type, tif = choose_order_type(spread_a, urgency=False, strategy_hint="pairs_trading")
    op_a = OrderParams.build(side=side_a, price=pa, spread_pct=spread_a,
        stop_distance=sl_dist_a, balance=balance * 0.5, risk_pct=RISK_PCT,
        strategy_hint="pairs_trading", expiry_seconds=EXPIRY_S)
    lp_a = round(bid_a if side_a=="Buy" else ask_a, 2)
    sl_a = round(pa - sl_dist_a if side_a=="Buy" else pa + sl_dist_a, 2)
    log_info(f"[pairs] zscore={zscore:.2f} | A:{side_a} qty={op_a.qty} lp={lp_a} "
             f"B:{side_b} | order={order_type}/{tif} free={free_mg:.2f}")
    pos_a = get_position(SYMBOL_A, cat)
    if pos_a:
        if pos_a["side"] == side_a: log_info(f"[pairs] already {side_a} on {SYMBOL_A}"); return
        close_position(pos_a)
    enter(side=side_a, qty=op_a.qty, stop_loss=sl_a, take_profit=None,
          reason=f"pairs_z{zscore:.2f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp_a)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
