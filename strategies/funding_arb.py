"""
Funding Rate Arbitrage v2
Improved: yield calculation, fee-aware, min threshold check, logging
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

FUNDING_THRESHOLD = float(os.getenv("FUNDING_THRESHOLD", "0.0001"))  # 0.01% per 8h
TAKER_FEE = 0.00055  # 0.055% per leg
MIN_YIELD = float(os.getenv("MIN_YIELD", "0.00005"))  # after fees

def run():
    if not safety_check(): return

    ticker = get_ticker()
    rate = float(ticker.get("fundingRate", 0))
    next_time = ticker.get("nextFundingTime", "unknown")

    # Net yield after 2 taker legs
    net_yield = abs(rate) - 2 * TAKER_FEE
    log_info(f"[FUNDING ARB] rate={rate:.6f} net_yield={net_yield:.6f} next={next_time}")

    if net_yield < MIN_YIELD:
        log_info(f"[FUNDING ARB] Net yield {net_yield:.6f} below min {MIN_YIELD} — skip")
        return

    candles = get_klines(limit=20)
    current_atr = atr(candles)
    price = closes(candles)[-1]

    qty_str = os.getenv("QTY", "0.01")
    qty = float(qty_str)

    if rate > FUNDING_THRESHOLD:
        log_info(f"[FUNDING ARB] Positive funding -> SHORT futures + BUY spot")
        sl_futures = round(price + 2 * current_atr, 2)
        enter("Sell", qty, sl_futures, reason=f"funding_arb rate={rate:.5f} yield={net_yield:.5f}")
        # Hedge leg on spot
        cli("order", "create", "--category", "spot", "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", qty_str,
            "--cap-usd", CAP_USD, "--yes")
        alert(f"💰 Funding arb: SHORT futures + LONG spot | rate={rate*100:.4f}% | yield={net_yield*100:.4f}% per 8h")

    elif rate < -FUNDING_THRESHOLD:
        log_info(f"[FUNDING ARB] Negative funding -> LONG futures + SELL spot")
        sl_futures = round(price - 2 * current_atr, 2)
        enter("Buy", qty, sl_futures, reason=f"funding_arb rate={rate:.5f} yield={net_yield:.5f}")
        cli("order", "create", "--category", "spot", "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", qty_str,
            "--cap-usd", CAP_USD, "--yes")
        alert(f"💰 Funding arb: LONG futures + SHORT spot | rate={rate*100:.4f}% | yield={net_yield*100:.4f}% per 8h")

    else:
        log_info(f"[FUNDING ARB] Rate below threshold — no trade")

if __name__ == "__main__":
    run()
