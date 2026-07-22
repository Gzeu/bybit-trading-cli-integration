"""
SuperTrend Strategy
Market: Linear Futures
Logic: SuperTrend indicator (ATR-based trailing stop)
Long when price > SuperTrend, Short when price < SuperTrend
Period=10, Multiplier=3
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
ATR_P = 10
ATR_M = 3.0

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def compute_supertrend(candles):
    highs = [float(c[2]) for c in candles]
    lows  = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    atr = sum(trs[-ATR_P:]) / ATR_P

    src = [(highs[i] + lows[i]) / 2 for i in range(len(candles))]
    upper = src[-1] + ATR_M * atr
    lower = src[-1] - ATR_M * atr

    price = closes[-1]
    trend = "up" if price > lower else "down"
    return trend, lower, upper, price

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "50")
    trend, lower, upper, price = compute_supertrend(data["result"]["list"])
    print(f"[SUPERTREND] trend={trend} price={price:.2f} lower={lower:.2f} upper={upper:.2f}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if trend == "up" and side != "Buy":
        print("[SUPERTREND] Uptrend -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(lower, 2)), "--cap-usd", "500", "--yes")
    elif trend == "down" and side != "Sell":
        print("[SUPERTREND] Downtrend -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(upper, 2)), "--cap-usd", "500", "--yes")

if __name__ == "__main__":
    run()
