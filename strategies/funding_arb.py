"""
Funding Rate Arb — Limit PostOnly when funding extreme, Market IOC near settlement.
Fee-aware: trade only if |funding| covers round-trip commission.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import OrderParams, choose_order_type, net_min_move, FEE_RT_WORST

FUNDING_THRESH = float(os.getenv("FUNDING_THRESH", "0.0005"))  # 0.05% per 8h
RISK_PCT       = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S       = int(os.getenv("FUNDING_EXPIRY_SEC", "600"))
ATR_MULT       = float(os.getenv("FUNDING_ATR_MULT", "1.5"))


def run(symbol=None, category=None):
    if not safety_check(): return
    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    bid      = float(ticker.get("bid1Price", price))
    ask      = float(ticker.get("ask1Price", price))
    funding  = float(ticker.get("fundingRate", 0))
    spread   = (ask - bid) / price * 100 if price else 0
    candles  = get_klines(interval="60", limit=50, symbol=symbol, category=category)
    atr_v    = atr(candles)
    balance  = get_balance(); free_mg = get_free_margin()
    # Fee gate: funding must exceed round-trip taker fee to be worth it
    if abs(funding) < FEE_RT_WORST:
        log_info(f"[funding_arb] funding={funding:.6f} < fee_rt={FEE_RT_WORST:.6f} — skip"); return
    if abs(funding) < FUNDING_THRESH:
        log_info(f"[funding_arb] funding={funding:.6f} below threshold — hold"); return
    # Counter-trade the funding direction
    side = "Sell" if funding > 0 else "Buy"
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="funding_arb")
    sl_dist  = ATR_MULT * atr_v
    min_move = net_min_move(price)
    if sl_dist < min_move * 1.5: log_info(f"[funding_arb] stop < min_move — skip"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="funding_arb", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(price + 2*sl_dist if side=="Buy" else price - 2*sl_dist, 2)
    log_info(f"[funding_arb] {side} funding={funding:.6f} qty={op.qty} "
             f"order={order_type}/{tif} comm={op.commission_usdt:.4f} free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=op.qty, stop_loss=sl, take_profit=tp,
          reason=f"funding_arb_{funding:.6f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=EXPIRY_S, limit_price=lp)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
