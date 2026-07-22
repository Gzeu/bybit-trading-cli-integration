"""
Heikin Ashi Trend — Limit PostOnly, 10-min expiry, fee-aware sizing.
Signal: 3 consecutive HA candles of same color.
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

HA_CONFIRM = int(os.getenv("HA_CONFIRM", "3"))
RISK_PCT   = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S   = int(os.getenv("HA_EXPIRY_SEC", "600"))
ATR_MULT   = float(os.getenv("HA_ATR_MULT", "1.5"))


def heikin_ashi(candles):
    ha = []
    for i, c in enumerate(candles):
        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        ha_close = (o + h + l + cl) / 4
        ha_open  = (ha[i-1][0] + ha[i-1][3]) / 2 if i > 0 else (o + cl) / 2
        ha_high  = max(h, ha_open, ha_close)
        ha_low   = min(l, ha_open, ha_close)
        ha.append((ha_open, ha_high, ha_low, ha_close))
    return ha


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=50, symbol=symbol, category=category)
    if len(candles) < HA_CONFIRM + 5: return
    ticker = get_ticker(symbol, category)
    price  = float(ticker.get("lastPrice", 0))
    bid    = float(ticker.get("bid1Price", price))
    ask    = float(ticker.get("ask1Price", price))
    spread = (ask - bid) / price * 100 if price else 0
    ha     = heikin_ashi(candles)
    recent = ha[-HA_CONFIRM:]
    bull   = all(c[3] > c[0] for c in recent)  # close > open
    bear   = all(c[3] < c[0] for c in recent)
    if not bull and not bear: log_info(f"[ha] no {HA_CONFIRM}-bar streak"); return
    side   = "Buy" if bull else "Sell"
    atr_v  = atr(candles)
    sl_dist = ATR_MULT * atr_v
    balance = get_balance(); free_mg = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="heikin_ashi_trend")
    min_move = net_min_move(price)
    if sl_dist < min_move * 1.5: log_info(f"[ha] stop < min_move — skip"); return
    op = OrderParams.build(side=side, price=price, spread_pct=spread,
        stop_distance=sl_dist, balance=balance, risk_pct=RISK_PCT,
        strategy_hint="heikin_ashi_trend", expiry_seconds=EXPIRY_S)
    lp = round(bid if side=="Buy" else ask, 2)
    sl = round(price - sl_dist if side=="Buy" else price + sl_dist, 2)
    tp = round(pr