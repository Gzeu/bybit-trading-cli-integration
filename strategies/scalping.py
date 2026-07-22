"""
Scalping Strategy — Orderbook Imbalance
Market: Linear Futures
Logic: Enter based on bid/ask volume imbalance at top of book
Warning: High frequency — monitor --max-orders-per-hour cap
"""
import subprocess, json, os, time

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
IMBALANCE_THRESHOLD = 1.5  # bid_vol / ask_vol ratio
SL_PCT = 0.002  # 0.2% stop-loss
TP_PCT = 0.003  # 0.3% take-profit


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def get_imbalance():
    ob = cli("market", "orderbook", "--category", CATEGORY, "--symbol", SYMBOL, "--limit", "10")
    bids = sum(float(b[1]) for b in ob["result"]["b"][:5])
    asks = sum(float(a[1]) for a in ob["result"]["a"][:5])
    return bids / asks if asks > 0 else 1.0, ob["result"]["b"][0][0]  # ratio, best_bid


def run():
    ratio, best_bid = get_imbalance()
    mid = float(best_bid)
    print(f"[SCALP] Imbalance ratio={ratio:.3f}")

    if ratio > IMBALANCE_THRESHOLD:
        tp = round(mid * (1 + TP_PCT), 2)
        sl = round(mid * (1 - SL_PCT), 2)
        print(f"[SCALP] Strong bid — LONG | TP={tp} SL={sl}")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market",
            "--qty", QTY,
            "--takeProfit", str(tp),
            "--stopLoss", str(sl),
            "--cap-usd", "300", "--yes")

    elif ratio < (1 / IMBALANCE_THRESHOLD):
        tp = round(mid * (1 - TP_PCT), 2)
        sl = round(mid * (1 + SL_PCT), 2)
        print(f"[SCALP] Strong ask — SHORT | TP={tp} SL={sl}")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market",
            "--qty", QTY,
            "--takeProfit", str(tp),
            "--stopLoss", str(sl),
            "--cap-usd", "300", "--yes")
    else:
        print("[SCALP] No imbalance signal")


if __name__ == "__main__":
    run()
