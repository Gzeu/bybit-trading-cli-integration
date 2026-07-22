"""
Open Interest Spike — Market IOC (urgency) on OI spike + price confirmation.
Spread gate: skip if > 0.06%. Fee check: tp > 2x taker round-trip.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr,
    enter, close_position, safety_check, log_info, cli, CATEGORY, SYMBOL,
)
from core.order_utils import calc_qty_net, net_min_move, choose_order_type

OI_SPIKE_PCT   = float(os.getenv("OI_SPIKE_PCT", "0.05"))  # 5% OI jump
MAX_SPREAD     = float(os.getenv("OI_MAX_SPREAD_PCT", "0.06"))
RISK_PCT       = float(os.getenv("MAX_RISK_PCT", "0.01"))
ATR_MULT       = float(os.getenv("OI_ATR_MULT", "1.2"))


def get_open_interest(symbol, category):
    data = cli("market", "open-interest",
               "--category", category or CATEGORY,
               "--symbol", symbol or SYMBOL,
               "--intervalTime", "5min", "--limit", "5")
    items = data.get("result", {}).get("list", [])
    if len(items) < 2: return 0, 0
    return float(items[0].get("openInterest", 0)), float(items[1].get("openInterest", 0))


def run(symbol=None, category=None):
    if not safety_check(): return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    if spread > MAX_SPREAD: log_info(f"[oi] spread={spread:.4f}% — skip"); return
    oi_now, oi_prev = get_open_interest(symbol, category)
    if oi_prev == 0: return
    oi_chg = (oi_now - oi_prev) / oi_prev
    if abs(oi_chg) < OI_SPIKE_PCT: log_info(f"[oi] OI chg={oi_chg:.4f} — hold"); return
    candles  = get_klines(interval="5", limit=30, symbol=symbol, category=category)
    c        = closes(candles)
    atr_v    = atr(candles)
    balance  = get_balance(); free_mg = get_free_margin()
    side     = "Buy" if c[-1] > c[-2] else "Sell"  # price direction confirms OI
    order_type, tif = choose_order_type(spread, urgency=True)
    sl_dist  = ATR_MULT * atr_v
    tp_dist  = 2 * sl_dist
    min_move = net_min_move(price, maker_entry=False, maker_exit=False)
    if tp_dist < min_move * 2: log_info(f"[oi] tp < min_move — skip"); return
    qty = calc_qty_net(sl_dist, balance, RISK_PCT, price, maker=False)
    sl  = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp  = round(price + tp_dist  if side=="Buy" else price - tp_dist,  2)
    log_info(f"[oi] {side} OI_chg={oi_chg:.4f} qty={qty} spread={spread:.4f}% free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=qty, stop_loss=sl, take_profit=tp,
          reason=f"oi_spike_{oi_chg:.4f}", order_type=order_type, time_in_force=tif,
          expiry_seconds=None, limit_price=None)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
