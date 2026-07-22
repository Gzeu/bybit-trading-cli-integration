"""
Liquidation Hunt / Stop Hunt Strategy
Market: Linear Futures
Logic: Identify key support/resistance levels where stops cluster.
After a wick through a major level and recovery, fade the move.
Uses recent highs/lows + ATR for zone detection.
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
WICK_MULT = 1.5  # wick must be > 1.5x body to signal hunt

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "15", "--limit", "20")
    candles = data["result"]["list"]
    last = candles[-1]
    o, h, l, c = float(last[1]), float(last[2]), float(last[3]), float(last[4])

    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    print(f"[LIQ] O={o} H={h} L={l} C={c} body={body:.2f} upper_wick={upper_wick:.2f} lower_wick={lower_wick:.2f}")

    if lower_wick > WICK_MULT * body and c > o:
        print("[LIQ] Lower wick hunt detected + bullish close -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(l * 0.998, 2)), "--cap-usd", "500", "--yes")
    elif upper_wick > WICK_MULT * body and c < o:
        print("[LIQ] Upper wick hunt detected + bearish close -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(h * 1.002, 2)), "--cap-usd", "500", "--yes")
    else:
        print("[LIQ] No hunt pattern detected")

if __name__ == "__main__":
    run()
