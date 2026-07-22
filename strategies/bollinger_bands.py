"""
Bollinger Bands Strategy
Market: Linear Futures / Spot
Logic: Enter long on price touching lower band, short on upper band
Band squeeze detection for breakout confirmation
"""
import subprocess, json, os, statistics

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "linear")
QTY = os.getenv("QTY", "0.01")
PERIOD = 20
STD_DEV = 2.0

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def bollinger(closes, period=20, mult=2.0):
    window = closes[-period:]
    mid = statistics.mean(window)
    std = statistics.stdev(window)
    return mid - mult * std, mid, mid + mult * std

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "60")
    closes = [float(c[4]) for c in data["result"]["list"]]

    lower, mid, upper = bollinger(closes, PERIOD, STD_DEV)
    price = closes[-1]
    bandwidth = (upper - lower) / mid

    print(f"[BB] price={price:.2f} lower={lower:.2f} mid={mid:.2f} upper={upper:.2f} bw={bandwidth:.4f}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if price <= lower and side != "Buy":
        print("[BB] Price at lower band -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--takeProfit", str(round(mid, 2)), "--stopLoss", str(round(lower * 0.995, 2)),
            "--cap-usd", "500", "--yes")
    elif price >= upper and side != "Sell":
        print("[BB] Price at upper band -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--takeProfit", str(round(mid, 2)), "--stopLoss", str(round(upper * 1.005, 2)),
            "--cap-usd", "500", "--yes")
    else:
        print("[BB] Price within bands — no trade")

if __name__ == "__main__":
    run()
