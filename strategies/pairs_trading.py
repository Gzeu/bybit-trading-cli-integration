"""
Pairs / Spread Trading Strategy
Market: Linear Futures (two correlated assets)
Logic: Track spread = price_A - beta * price_B.
When spread deviates > 2 std, mean-revert:
  spread too high -> short A, long B
  spread too low  -> long A, short B
Default pair: BTCUSDT / ETHUSDT
"""
import subprocess, json, os, statistics

SYMBOL_A = os.getenv("SYMBOL_A", "BTCUSDT")
SYMBOL_B = os.getenv("SYMBOL_B", "ETHUSDT")
CATEGORY = "linear"
QTY_A = os.getenv("QTY_A", "0.001")
QTY_B = os.getenv("QTY_B", "0.01")
BETA = float(os.getenv("BETA", "15.0"))  # approximate BTC/ETH price ratio hedge
LOOKBACK = 30
Z_THRESH = 2.0

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def get_closes(symbol, limit=50):
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", symbol, "--interval", "60", "--limit", str(limit))
    return [float(c[4]) for c in data["result"]["list"]]

def run():
    closes_a = get_closes(SYMBOL_A)
    closes_b = get_closes(SYMBOL_B)
    n = min(len(closes_a), len(closes_b))
    spreads = [closes_a[i] - BETA * closes_b[i] for i in range(n)]

    mean = statistics.mean(spreads[-LOOKBACK:])
    std  = statistics.stdev(spreads[-LOOKBACK:])
    z = (spreads[-1] - mean) / std if std > 0 else 0
    print(f"[PAIRS] spread={spreads[-1]:.2f} mean={mean:.2f} z={z:.3f}")

    if z > Z_THRESH:
        print("[PAIRS] Spread too high -> SHORT A, LONG B")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL_A,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY_A, "--cap-usd", "500", "--yes")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL_B,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY_B, "--cap-usd", "500", "--yes")
    elif z < -Z_THRESH:
        print("[PAIRS] Spread too low -> LONG A, SHORT B")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL_A,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY_A, "--cap-usd", "500", "--yes")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL_B,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY_B, "--cap-usd", "500", "--yes")
    else:
        print("[PAIRS] Spread within bounds — no trade")

if __name__ == "__main__":
    run()
