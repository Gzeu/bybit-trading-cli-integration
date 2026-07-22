"""
Breakout — ATR volatility breakout with Market urgency (no Limit fill risk).

Order logic:
  - Market IOC with urgency=True — breakout must fill immediately
  - Spread gate: skip if spread > 0.08% (too expensive for breakout)
  - Sizing: calc_qty_net with taker fee (market order)
  - SL: below breakout candle low/high (structural stop)
  - TP: 2x stop distance
  - Expiry: N/A (Market IOC)
"""
import sys, os, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, atr,
    enter, close_position, safety_check, log_info, LEVERAGE,
)
from core.order_utils import (
    calc_qty_net, net_min_move, choose_order_type,
)

ATR_MULT_BO    = float(os.getenv("BO_ATR_MULT",       "1.0"))  # breakout threshold
ATR_SL_MULT    = float(os.getenv("BO_ATR_SL_MULT",    "1.0"))  # stop below/above breakout candle
ATR_TP_MULT    = float(os.getenv("BO_ATR_TP_MULT",    "2.0"))  # 2:1 R:R
RISK_PCT       = float(os.getenv("MAX_RISK_PCT",       "0.01"))
MAX_SPREAD_PCT = float(os.getenv("BO_MAX_SPREAD_PCT",  "0.08"))
LOOKBACK       = int(os.getenv("BO_LOOKBACK",          "20"))


def run(symbol=None, category=None):
    if not safety_check():
        return

    candles  = get_klines(interval="60", limit=LOOKBACK + 10, symbol=symbol, category=category)
    if len(candles) < LOOKBACK:
        return

    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    bid      = float(ticker.get("bid1Price", price))
    ask      = float(ticker.get("ask1Price", price))
    spread   = (ask - bid) / price * 100 if price else 0

    if spread > MAX_SPREAD_PCT:
        log_info(f"[breakout] spread={spread:.4f}% > {MAX_SPREAD_PCT}% — skip")
        return

    c        = closes(candles)
    h        = highs(candles)
    l        = lows(candles)
    atr_val  = atr(candles)
    balance  = get_balance()
    free_mg  = get_free_margin()

    # Donchian breakout: close above N-period high or below N-period low
    highest  = max(h[-LOOKBACK-1:-1])
    lowest   = min(l[-LOOKBACK-1:-1])
    min_move = net_min_move(price, maker_entry=False, maker_exit=False)

    if c[-1] > highest + ATR_MULT_BO * atr_val:
        side = "Buy"
    elif c[-1] < lowest - ATR_MULT_BO * atr_val:
        side = "Sell"
    else:
        log_info(f"[breakout] no breakout — price={price} high={highest:.2f} low={lowest:.2f}")
        return

    # Breakout: always use Market IOC (urgency)
    order_type, tif = choose_order_type(spread, urgency=True)
    sl_dist  = ATR_SL_MULT * atr_val
    tp_dist  = ATR_TP_MULT * atr_val * 2

    if tp_dist < min_move * 2:
        log_info(f"[breakout] tp_dist={tp_dist:.4f} < 2x min_move={min_move:.4f} — skip")
        return

    qty = calc_qty_net(
        stop_distance=sl_dist, balance=balance,
        risk_pct=RISK_PCT, price=price, maker=False,
    )
    stop_loss   = round(price - sl_dist if side == "Buy" else price + sl_dist, 2)
    take_profit = round(price + tp_dist if side == "Buy" else price - tp_dist, 2)

    log_info(
        f"[breakout] {side} qty={qty} sl={stop_loss} tp={take_profit} "
        f"spread={spread:.4f}% order={order_type}/{tif} "
        f"min_move={min_move:.4f} free_margin={free_mg:.2f}"
    )

    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side:
            log_info(f"[breakout] already {side} — skip")
            return
        close_position(pos)

    enter(
        side=side, qty=qty,
        stop_loss=stop_loss, take_profit=take_profit,
        reason="breakout_donchian",
        order_type=order_type, time_in_force=tif,
        expiry_seconds=None,
        limit_price=None,
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",   default=None)
    p.add_argument("--category", default=None)
    args = p.parse_args()
    run(args.symbol, args.category)
