"""
Trend Follow — EMA crossover with fee-aware sizing and Limit PostOnly orders.

Order logic:
  - Uses Limit PostOnly (maker fee 0.020%) unless spread > threshold
  - GTC with 10-minute expiry: if not filled in 600s, cancels automatically
  - Sizing: calc_qty_net deducts round-trip commission from risk budget
  - Skips if expected move < 1.5x break-even (fees kill profitability)
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr, ema, calc_atr_stop,
    enter, close_position, safety_check, log_info, log_error, LEVERAGE,
)
from core.order_utils import (
    OrderParams, choose_order_type, net_min_move, commission_cost,
)

EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
ATR_MULT = float(os.getenv("ATR_MULT", "1.5"))
RISK_PCT = float(os.getenv("MAX_RISK_PCT", "0.01"))
EXPIRY_S = int(os.getenv("TREND_ORDER_EXPIRY_SEC", "600"))  # 10 min


def run(symbol=None, category=None):
    if not safety_check():
        return

    candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
    if len(candles) < INEED := max(EMA_FAST, EMA_SLOW) + 5:
        log_error(f"[trend_follow] not enough candles ({len(candles)} < {INEED})")
        return

    ticker = get_ticker(symbol, category)
    price  = float(ticker.get("lastPrice", 0))
    bid    = float(ticker.get("bid1Price", price))
    ask    = float(ticker.get("ask1Price", price))
    spread = (ask - bid) / price * 100 if price else 0
    c      = closes(candles)
    fast   = ema(c, EMA_FAST)
    slow   = ema(c, EMA_SLOW)
    prev_fast = ema(c[:-1], EMA_FAST)
    prev_slow = ema(c[:-1], EMA_SLOW)
    atr_val   = atr(candles)

    cross_up   = prev_fast <= prev_slow and fast > slow
    cross_down = prev_fast >= prev_slow and fast < slow

    if not cross_up and not cross_down:
        log_info(f"[trend_follow] no crossover — hold")
        return

    side          = "Buy" if cross_up else "Sell"
    stop_dist     = ATR_MULT * atr_val
    balance       = get_balance()
    free_margin   = get_free_margin()
    order_type, tif = choose_order_type(spread, urgency=False, strategy_hint="trend_follow")
    maker         = order_type == "Limit"
    min_move      = net_min_move(price, maker_entry=maker, maker_exit=maker)

    # Reject if stop too tight vs fees
    if stop_dist < min_move * 1.5:
        log_info(f"[trend_follow] stop={stop_dist:.4f} < 1.5x min_move={min_move:.4f} — skip")
        return

    op = OrderParams.build(
        side=side, price=price, spread_pct=spread,
        stop_distance=stop_dist, balance=balance,
        risk_pct=RISK_PCT, strategy_hint="trend_follow",
        expiry_seconds=EXPIRY_S,
    )
    limit_price = round(bid if side == "Buy" else ask, 2)
    stop_loss   = round(price - stop_dist if side == "Buy" else price + stop_dist, 2)
    take_profit = round(price + 2 * stop_dist if side == "Buy" else price - 2 * stop_dist, 2)

    log_info(
        f"[trend_follow] {side} qty={op.qty} price={limit_price} "
        f"sl={stop_loss} tp={take_profit} "
        f"order={order_type}/{tif} expiry={EXPIRY_S}s "
        f"commission={op.commission_usdt:.4f} USDT "
        f"free_margin={free_margin:.2f}"
    )

    pos = get_position(symbol, category)
    if pos:
        if pos["side"] == side:
            log_info(f"[trend_follow] already {side} — skip")
            return
        close_position(pos)

    enter(
        side=side, qty=op.qty,
        stop_loss=stop_loss, take_profit=take_profit,
        reason="trend_follow_ema_cross",
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
