"""
DCA Accumulation — Limit GTC orders at fixed intervals below current price.
Fee-aware: only places if DCA step > break-even move.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, atr,
    enter, safety_check, log_info, cli, CATEGORY, SYMBOL, CAP_USD,
)
from core.order_utils import calc_qty_balance, net_min_move, order_expiry_args

DCA_STEPS     = int(os.getenv("DCA_STEPS", "3"))
DCA_STEP_PCT  = float(os.getenv("DCA_STEP_PCT", "0.005"))  # 0.5% drop per level
DCA_ALLOC_PCT = float(os.getenv("DCA_ALLOC_PCT", "0.30"))  # 30% free margin per step
EXPIRY_S      = int(os.getenv("DCA_EXPIRY_SEC", "3600"))   # 1-hour GTC
LEVERAGE      = int(os.getenv("LEVERAGE", "1"))


def run(symbol=None, category=None):
    if not safety_check(): return
    candles = get_klines(interval="60", limit=50, symbol=symbol, category=category)
    if len(candles) < 20: return
    ticker   = get_ticker(symbol, category)
    price    = float(ticker.get("lastPrice", 0))
    balance  = get_balance()
    free_mg  = get_free_margin()
    min_move = net_min_move(price, maker_entry=True, maker_exit=True)
    step_move = price * DCA_STEP_PCT
    if step_move < min_move * 1.5:
        log_info(f"[dca] step_move={step_move:.4f} < min_move — skip"); return
    alloc_per_step = free_mg * DCA_ALLOC_PCT / DCA_STEPS
    for i in range(1, DCA_STEPS + 1):
        level_price = round(price * (1 - DCA_STEP_PCT * i), 2)
        qty = calc_qty_balance(level_price, alloc_per_step, alloc_pct=0.95, leverage=LEVERAGE)
        extra = order_expiry_args("Limit", "GTC", EXPIRY_S)
        args = [
            "order", "create",
            "--category", category or CATEGORY,
            "--symbol", symbol or SYMBOL,
            "--side", "Buy", "--orderType", "Limit",
            "--price", str(level_price),
            "--qty", str(qty),
            "--cap-usd", CAP_USD, "--yes",
        ] + extra
        result = cli(*args)
        log_info(f"[dca] level={i} price={level_price} qty={qty} "
                 f"alloc={alloc_per_step:.2f} retCode={result.get('retCode')}")
    log_info(f"[dca] {DCA_STEPS} limit orders placed | free_margin={free_mg:.2f}")

if __name__ == "__main__":
    import argparse; p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None); p.add_argument("--category", default=None)
    a = p.parse_args(); run(a.symbol, a.category)
