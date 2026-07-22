"""
Mean Reversion — Z-score with Limit PostOnly orders and fee break-even check.

Order logic:
  - Limit PostOnly (maker 0.020%) — mean-rev only makes sense with maker fee
  - Expiry: 5 minutes (300s) — if not filled, market has moved, skip
  - Sizing: fee-aware calc_qty_net
  - Skips if |zscore| < 2.0 (not far enough from mean to cover fees)
  - Entry at best bid/ask (passive), TP at mean (zscore~0), SL at 1.5x ATR
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr, ema, zscore,
    enter, close_position, safety_check, log_info, log_error, LEVERAGE,
)
from core.order_utils import (
    OrderParams, choose_order_type, net_min_move,
)

ZSCORE_ENTRY  = float(os.getenv("MR_ZSCORE_ENTRY",  "2.0"))
ZSCORE_EXIT   = float(os.getenv("MR_ZSCORE_EXIT",   "0.5"))
ATR_SL_MULT   = float(os.getenv("MR_ATR_SL_MULT",   "1.5"))
ATR_TP_MULT   = float(os.getenv("MR_ATR_TP_MULT",   "1.0"))
RISK_PCT      = float(os.getenv("MAX_RISK_PCT",      "0.01"))
EXPIRY_S      = int(os.getenv("MR_ORDER_EXPIRY_SEC", "300"))  # 5 min
LOOKBACK      = int(os.getenv("MR_LOOKBACK",         "50"))


def run(symbol=None, category=None):
    if not safety_check():
        return

    candles = get_klines(interval="60", limit=LOOKBACK + 20, symbol=symbol, category=category)
    if len(candles) < LOOKBACK:
        log_error(f"[mean_reversion] not enough candles")
        return

    ticker  = get_ticker(symbol, category)
    price   = float(ticker.get("lastPrice", 0))
    bid     = float(ticker.get("bid1Price", price))
    ask     = float(ticker.get("ask1Price", price))
    spread  = (ask - bid) / price * 100 if price else 0
    c       = closes(candles)
    zs      = zscore(c, LOOKBACK)
    atr_val = atr(candles)
    balance = get_balance()
    free_mg = get_free_margin()

    # mean_reversion only works with maker fee — enforce Limit
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="mean_reversion")
    maker = order_type == "Limit"
    min_move = net_min_move(price, maker_entry=maker, maker_exit=maker)

    # Direction
    if zs > ZSCORE_ENTRY:
        side = "Sell"  # price far above mean — fade up move
    elif zs < -ZSCORE_ENTRY:
        side = "Buy"   # price far below mean — fade down move
    else:
        log_info(f"[mean_reversion] zscore={zs:.2f} within [{-ZSCORE_ENTRY}, {ZSCORE_ENTRY}] — hold")
        return

    stop_dist   = ATR_SL_MULT * atr_val
    tp_dist     = ATR_TP_MULT * atr_val

    # TP must beat break-even
    if tp_dist < min_move * 2:
        log_info(f"[mean_reversion] tp_dist={tp_dist:.4f} < 2x min_move={min_move:.4f} — skip")
        return

    op          = OrderParams.build(
        side=side, price=price, spread_pct=spread,
        stop_distance=stop_dist, balance=balance,
        risk_pct=RISK_PCT, strategy_hint="mean_reversion",
        expiry_seconds=EXPIRY_S,
    )
    limit_price = round(bid if side == "Buy" else ask, 2)
    stop_loss   = round(price - stop_dist if side == "Buy" else price + stop_dist, 2)
    take_profit = round(price + tp_dist   if side == "Buy" else price - tp_dist,   2)

    log_info(
        f"[mean_reversion] {side} zscore={zs:.2f} qty={op.qty} "
        f"price={limit_price} sl={stop_loss} tp={take_profit} "
        f"order={order_type}/{tif} expiry={EXPIRY_S}s "
        f"comm={op.commission_usdt:.4f} free_margin={free_mg:.2f}"
    )

    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side:
            log_info(f"[mean_reversion] already {side} — skip")
            return
        close_position(pos)

    enter(
        side=side, qty=op.qty,
        stop_loss=stop_loss, take_profit=take_profit,
        reason=f"mean_rev_z{zs:.2f}",
        order_type=order_type, time_in_force=tif,
        expiry_seconds=EXPIRY_S,
        limit_price=limit_price,
    )


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",   default=None)
    p.add_argument("--category", default=None)
    args = p.parse_args()
    run(args.symbol, args.category)
