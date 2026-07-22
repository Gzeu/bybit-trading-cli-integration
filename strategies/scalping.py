"""
Scalping — High-frequency with Market IOC only when spread is tight.

Order logic:
  - Market IOC (taker 0.055%) — needs immediate fill for scalp to work
  - Hard gate: skip if spread >= 0.03% (fees eat the entire scalp move)
  - Sizing: calc_qty_net with taker=True so fee is correctly priced in
  - Very tight SL (0.5x ATR) — scalp lives or dies fast
  - No expiry: IOC fills what it can immediately, remainder cancelled
  - Min move check: tp_dist must be > 2x round-trip taker fee
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, atr, rsi,
    enter, close_position, safety_check, log_info, LEVERAGE,
)
from core.order_utils import (
    calc_qty_net, net_min_move, FEE_TAKER,
)

MAX_SPREAD_PCT = float(os.getenv("SCALP_MAX_SPREAD_PCT", "0.03"))  # hard gate
ATR_SL_MULT    = float(os.getenv("SCALP_ATR_SL_MULT",   "0.5"))
ATR_TP_MULT    = float(os.getenv("SCALP_ATR_TP_MULT",   "1.0"))
RISK_PCT       = float(os.getenv("MAX_RISK_PCT",         "0.005"))  # 0.5% — tight
RSI_LOW        = float(os.getenv("SCALP_RSI_LOW",        "35"))
RSI_HIGH       = float(os.getenv("SCALP_RSI_HIGH",       "65"))


def run(symbol=None, category=None):
    if not safety_check():
        return

    candles  = get_klines(interval="1", limit=50, symbol=symbol, category=category)
    if len(candles) < 20:
        return

    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    bid      = float(ticker.get("bid1Price", price))
    ask      = float(ticker.get("ask1Price", price))
    spread   = (ask - bid) / price * 100 if price else 0

    # Hard gate: spread must be tight enough for scalp to be profitable
    if spread >= MAX_SPREAD_PCT:
        log_info(f"[scalping] spread={spread:.4f}% >= {MAX_SPREAD_PCT}% — skip (fee gate)")
        return

    c        = closes(candles)
    rsi_val  = rsi(c)
    atr_val  = atr(candles)
    balance  = get_balance()
    free_mg  = get_free_margin()

    # Market IOC — taker fee
    min_move = net_min_move(price, maker_entry=False, maker_exit=False)
    tp_dist  = ATR_TP_MULT * atr_val
    sl_dist  = ATR_SL_MULT * atr_val

    if tp_dist < min_move * 2:
        log_info(f"[scalping] tp_dist={tp_dist:.4f} < 2x min_move={min_move:.4f} — skip")
        return

    # Signal
    if rsi_val < RSI_LOW and c[-1] > c[-2]:   # oversold + uptick
        side = "Buy"
    elif rsi_val > RSI_HIGH and c[-1] < c[-2]: # overbought + downtick
        side = "Sell"
    else:
        log_info(f"[scalping] RSI={rsi_val:.1f} no signal")
        return

    qty = calc_qty_net(
        stop_distance=sl_dist, balance=balance,
        risk_pct=RISK_PCT, price=price, maker=False,  # taker sizing
    )
    stop_loss   = round(price - sl_dist if side == "Buy" else price + sl_dist, 2)
    take_profit = round(price + tp_dist if side == "Buy" else price - tp_dist, 2)

    log_info(
        f"[scalping] {side} qty={qty} sl={stop_loss} tp={take_profit} "
        f"spread={spread:.4f}% RSI={rsi_val:.1f} "
        f"min_move={min_move:.4f} free_margin={free_mg:.2f}"
    )

    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side:
            log_info(f"[scalping] already {side} — skip")
            return
        close_position(pos)

    enter(
        side=side, qty=qty,
        stop_loss=stop_loss, take_profit=take_profit,
        reason="scalp_rsi",
        order_type="Market", time_in_force="IOC",
        expiry_seconds=None,   # IOC handles it
        limit_price=None,
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",   default=None)
    p.add_argument("--category", default=None)
    args = p.parse_args()
    run(args.symbol, args.category)
