"""
Grid Trading — Limit GTC orders at fixed grid levels, fee-aware spacing.
Grid step must be > break-even move; otherwise grid is unprofitable.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    closes, atr, safety_check, log_info, cli, CATEGORY, SYMBOL, CAP_USD,
)
from core.order_utils import calc_qty_balance, net_min_move, order_expiry_args

GRID_LEVELS   = int(os.getenv("GRID_LEVELS",   "5"))
GRID_STEP_PCT = float(os.getenv("GRID_STEP_PCT", "0.003"))  # 0.3% per level
GRID_ALLOC    = float(os.getenv("GRID_ALLOC",   "0.15"))    # 15% free margin per level
EXPIRY_S      = int(os.getenv("GRID_EXPIRY_SEC", "7200"))   # 2h
LEVERAGE      = int(os.getenv("LEVERAGE", "1"))


def run(symbol=None, category=None):
    if not safety_check(): return
    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    free_mg  = get_free_margin()
    min_move = net_min_move(price, maker_entry=True, maker_exit=True)
    step_move = price * GRID_STEP_PCT
    if step_move < min_move * 1.5:
        log_info(f"[grid] step_move={step_move:.4f} < min_move={min_move:.4f} — skip"); return
    alloc_per = free_mg * GRID_ALLOC
    for i in range(1, GRID_LEVELS + 1):
        buy_price  = round(price * (1 - GRID_STEP_PCT * i), 2)
        sell_price = round(price * (1 + GRID_STEP_PCT * i), 2)
        qty = calc_qty_balance(buy_price, alloc_per, alloc_pct=0.95, leverage=LEVERAGE)
        extra = order_expiry_args("Limit", "GTC", EXPIRY_S)
        for side, lp in [("Buy", buy_price), ("Sell", sell_price)]:
            args = [
                "order", "create",
                "--category", category or CATEGORY,
                "--symbol",   symbol or SYMBOL,
                "--side", side, "--orderType", "Limit",
                "--price", str(lp),
                "--qty", str(qty),
                "--cap-usd", CAP_USD, "--yes",
            ] + extra
            result = cli(*args)
            log_info(f"[grid] {side} level={i} price={lp} qty={qty} "
                     f"retCode={result.get('retCode')}")
    log_info(f"[grid] {GRID_LEVELS*2} orders placed | free_margin={free_mg:.2f}")

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
