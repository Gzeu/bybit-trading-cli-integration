"""
Market Making — Dual Limit PostOnly orders (bid + ask) around mid price.
Fee: maker 0.020%; spread must be > 2x maker fee to be profitable.
Expiry: 5 minutes per quote cycle.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_ticker, get_balance, get_free_margin,
    safety_check, log_info, cli, CATEGORY, SYMBOL, CAP_USD,
)
from core.order_utils import calc_qty_balance, net_min_move, FEE_MAKER, order_expiry_args

QUOTE_SPREAD_PCT = float(os.getenv("MM_QUOTE_SPREAD_PCT", "0.002"))  # 0.2% our spread
ALLOC_PCT        = float(os.getenv("MM_ALLOC_PCT", "0.20"))          # 20% free margin each side
EXPIRY_S         = int(os.getenv("MM_EXPIRY_SEC", "300"))
LEVERAGE         = int(os.getenv("LEVERAGE", "1"))
MIN_SPREAD_MULT  = 2.1  # our spread must be > 2.1x maker fee rt


def run(symbol=None, category=None):
    if not safety_check(): return
    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    free_mg  = get_free_margin()
    min_move = net_min_move(price, maker_entry=True, maker_exit=True)
    # Profitability gate: our quoted spread must exceed round-trip maker fee
    our_spread_abs = price * QUOTE_SPREAD_PCT
    if our_spread_abs < min_move * MIN_SPREAD_MULT:
        log_info(f"[mm] spread={our_spread_abs:.4f} < {MIN_SPREAD_MULT}x min_move={min_move:.4f} — skip")
        return
    half = price * QUOTE_SPREAD_PCT / 2
    bid_price  = round(price - half, 2)
    ask_price  = round(price + half, 2)
    qty = calc_qty_balance(price, free_mg * ALLOC_PCT, alloc_pct=0.95, leverage=LEVERAGE)
    extra = order_expiry_args("Limit", "PostOnly", EXPIRY_S)
    for side, lp in [("Buy", bid_price), ("Sell", ask_price)]:
        args = [
            "order", "create",
            "--category", category or CATEGORY, "--symbol", symbol or SYMBOL,
            "--side", side, "--orderType", "Limit",
            "--price", str(lp), "--qty", str(qty),
            "--cap-usd", CAP_USD, "--yes",
        ] + extra
        result = cli(*args)
        log_info(f"[mm] {side} price={lp} qty={qty} retCode={result.get('retCode')}")
    log_info(f"[mm] quotes placed bid={bid_price} ask={ask_price} spread_abs={our_spread_abs:.4f} free={free_mg:.2f}")

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
