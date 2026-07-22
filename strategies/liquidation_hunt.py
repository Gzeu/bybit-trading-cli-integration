"""
Liquidation Hunt — Market IOC (urgency). Spread gate: skip if > 0.05%.
Trades in direction of liquidation cascade after spike detected.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, volumes, atr,
    enter, close_position, safety_check, log_info,
)
from core.order_utils import calc_qty_net, net_min_move, choose_order_type

VOL_MULT       = float(os.getenv("LIQ_VOL_MULT", "3.0"))
PRICE_SPIKE_PCT= float(os.getenv("LIQ_PRICE_SPIKE_PCT", "0.003"))  # 0.3%
MAX_SPREAD     = float(os.getenv("LIQ_MAX_SPREAD_PCT", "0.05"))
RISK_PCT       = float(os.getenv("MAX_RISK_PCT", "0.005"))
ATR_MULT       = float(os.getenv("LIQ_ATR_MULT", "0.8"))


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="1", limit=50, symbol=symbol, category=category)
    if len(candles) < 20: return
    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    if spread > MAX_SPREAD:
        log_info(f"[liq] spread={spread:.4f}% > {MAX_SPREAD}% — skip"); return
    c    = closes(candles)
    vols = volumes(candles)
    avg_vol = sum(vols[-20:-1]) / 19
    last_vol_spike = vols[-1] > avg_vol * VOL_MULT
    price_spike_up   = (c[-1] - c[-2]) / c[-2] > PRICE_SPIKE_PCT
    price_spike_down = (c[-2] - c[-1]) / c[-2] > PRICE_SPIKE_PCT
    if not last_vol_spike or (not price_spike_up and not price_spike_down):
        log_info(f"[liq] no liquidation spike detected"); return
    side    = "Buy" if price_spike_up else "Sell"  # fade the cascade direction
    order_type, tif = choose_order_type(spread, urgency=True, strategy_hint="liquidation_hunt")
    atr_v   = atr(candles)
    sl_dist = ATR_MULT * atr_v
    balance = get_balance(); free_mg = get_free_margin()
    min_move = net_min_move(price, maker_entry=False, maker_exit=False)
    tp_dist  = 2 * sl_dist
    if tp_dist < min_move * 2: log_info(f"[liq] tp < min_move — skip"); return
    qty = calc_qty_net(sl_dist, balance, RISK_PCT, price, maker=False)
    sl  = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp  = round(price + tp_dist  if side=="Buy" else price - tp_dist,  2)
    log_info(f"[liq] {side} qty={qty} sl={sl} tp={tp} spread={spread:.4f}% free={free_mg:.2f}")
    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side: return
        close_position(pos)
    enter(side=side, qty=qty, stop_loss=sl, take_profit=tp,
          reason="liquidation_hunt", order_type=order_type, time_in_force=tif,
          expiry_seconds=None, limit_price=None)

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
