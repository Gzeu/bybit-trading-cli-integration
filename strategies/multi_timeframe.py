"""
Multi-Timeframe Confluence Strategy
Market: Linear Futures
Logic: Require trend alignment across 3 timeframes (4h, 1h, 15m).
All three must agree on direction (EMA slope) before entering.
'Never trade against the higher timeframe.'
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
TIMEFRAMES = [("240", "4h"), ("60", "1h"), ("15", "15m")]
EMA_P = 21

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def ema_slope(closes, period=21):
    k = 2 / (period + 1)
    e = closes[0]
    ema_vals = []
    for p in closes:
        e = p * k + e * (1 - k)
        ema_vals.append(e)
    return ema_vals[-1] - ema_vals[-3]  # 2-bar slope

def get_slope(interval):
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL,
               "--interval", interval, "--limit", str(EMA_P + 10))
    closes = [float(c[4]) for c in data["result"]["list"]]
    return ema_slope(closes, EMA_P)

def run():
    slopes = {}
    for tf, label in TIMEFRAMES:
        slopes[label] = get_slope(tf)
        print(f"[MTF] {label} slope={slopes[label]:.4f}")

    all_up   = all(s > 0 for s in slopes.values())
    all_down = all(s < 0 for s in slopes.values())

    if all_up:
        print("[MTF] All timeframes bullish -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif all_down:
        print("[MTF] All timeframes bearish -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[MTF] No confluence across timeframes — skip")

if __name__ == "__main__":
    run()
