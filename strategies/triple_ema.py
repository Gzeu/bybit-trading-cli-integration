"""
Triple EMA (TEMA) Trend Strategy
Market: Linear Futures
Logic: TEMA = 3*EMA1 - 3*EMA2 + EMA3 (reduces lag significantly)
Enter long when TEMA slopes up, short when slopes down
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
PERIOD = 21

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def ema_series(prices, period):
    k = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result

def tema(prices, period):
    e1 = ema_series(prices, period)
    e2 = ema_series(e1, period)
    e3 = ema_series(e2, period)
    return [3*a - 3*b + c for a, b, c in zip(e1, e2, e3)]

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "100")
    closes = [float(c[4]) for c in data["result"]["list"]]
    t = tema(closes, PERIOD)

    slope = t[-1] - t[-3]  # 2-candle slope
    print(f"[TEMA] tema={t[-1]:.2f} slope={slope:.4f}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if slope > 0 and side != "Buy":
        print("[TEMA] Upslope -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif slope < 0 and side != "Sell":
        print("[TEMA] Downslope -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")

if __name__ == "__main__":
    run()
