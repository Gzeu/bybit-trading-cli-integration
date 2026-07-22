"""
Ichimoku Cloud Strategy
Market: Linear Futures
Logic:
- Price above Kumo (cloud) + Tenkan > Kijun -> LONG
- Price below Kumo + Tenkan < Kijun -> SHORT
Periods: Tenkan=9, Kijun=26, Senkou B=52
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def mid(highs, lows, period):
    return (max(highs[-period:]) + min(lows[-period:])) / 2

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "110")
    candles = data["result"]["list"]
    highs = [float(c[2]) for c in candles]
    lows  = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    tenkan = mid(highs, lows, 9)
    kijun  = mid(highs, lows, 26)
    senkou_a = (tenkan + kijun) / 2
    senkou_b = mid(highs, lows, 52)
    kumo_top = max(senkou_a, senkou_b)
    kumo_bot = min(senkou_a, senkou_b)
    price = closes[-1]

    print(f"[ICHI] price={price:.2f} tenkan={tenkan:.2f} kijun={kijun:.2f} kumo={kumo_bot:.2f}-{kumo_top:.2f}")

    if price > kumo_top and tenkan > kijun:
        print("[ICHI] Above cloud, bullish TK -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(kumo_top * 0.997, 2)), "--cap-usd", "500", "--yes")
    elif price < kumo_bot and tenkan < kijun:
        print("[ICHI] Below cloud, bearish TK -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(kumo_bot * 1.003, 2)), "--cap-usd", "500", "--yes")
    else:
        print("[ICHI] Inside cloud or mixed signal — no trade")

if __name__ == "__main__":
    run()
