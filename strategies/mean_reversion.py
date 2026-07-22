"""
Mean Reversion Strategy — Z-score
Market: Spot or Linear Futures
Logic: Enter when z-score > 2 (short) or < -2 (long), exit near 0
"""
import subprocess, json, os, statistics

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "linear")
QTY = os.getenv("QTY", "0.01")
LOOKBACK = 50
ENTRY_Z = 2.0
EXIT_Z = 0.5


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def get_closes(limit=100):
    data = cli("market", "kline", "--category", CATEGORY,
               "--symbol", SYMBOL, "--interval", "60", "--limit", str(limit))
    return [float(c[4]) for c in data["result"]["list"]]


def zscore(prices):
    window = prices[-LOOKBACK:]
    mean = statistics.mean(window)
    std = statistics.stdev(window)
    return (prices[-1] - mean) / std if std > 0 else 0


def run():
    closes = get_closes()
    z = zscore(closes)
    print(f"[MEAN-REV] z-score={z:.3f}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if z > ENTRY_Z and side != "Sell":
        print("[MEAN-REV] Overbought — SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")

    elif z < -ENTRY_Z and side != "Buy":
        print("[MEAN-REV] Oversold — LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")

    elif abs(z) < EXIT_Z and side in ("Buy", "Sell"):
        close_side = "Sell" if side == "Buy" else "Buy"
        print(f"[MEAN-REV] z near 0 — closing {side}")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", close_side, "--orderType", "Market", "--qty", QTY,
            "--reduceOnly", "true", "--yes")


if __name__ == "__main__":
    run()
