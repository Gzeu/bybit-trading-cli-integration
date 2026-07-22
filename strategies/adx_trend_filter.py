"""
ADX Trend Filter Strategy
Market: Linear Futures
Logic: Only trade when ADX > 25 (strong trend).
Combine with DI+/DI- crossover for direction.
+DI > -DI + ADX > 25 -> LONG
-DI > +DI + ADX > 25 -> SHORT
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
ADX_P = 14
ADX_THRESH = 25

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def compute_adx(candles, period=14):
    highs  = [float(c[2]) for c in candles]
    lows   = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]
    dm_plus, dm_minus, trs = [], [], []
    for i in range(1, len(closes)):
        up   = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        dm_plus.append(up if up > down and up > 0 else 0)
        dm_minus.append(down if down > up and down > 0 else 0)
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = sum(trs[-period:]) / period
    di_plus  = 100 * (sum(dm_plus[-period:])  / period) / atr if atr else 0
    di_minus = 100 * (sum(dm_minus[-period:]) / period) / atr if atr else 0
    dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
    return di_plus, di_minus, dx  # simplified ADX = DX for last bar

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "60")
    candles = data["result"]["list"]
    di_p, di_m, adx = compute_adx(candles)
    print(f"[ADX] DI+={di_p:.2f} DI-={di_m:.2f} ADX={adx:.2f}")

    if adx > ADX_THRESH:
        if di_p > di_m:
            print("[ADX] Strong uptrend -> LONG")
            cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
                "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
        else:
            print("[ADX] Strong downtrend -> SHORT")
            cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
                "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print(f"[ADX] Weak trend (ADX={adx:.2f}) — skip")

if __name__ == "__main__":
    run()
