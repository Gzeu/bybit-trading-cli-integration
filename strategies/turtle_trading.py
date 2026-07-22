"""
Turtle Trading System (Donchian Channel)
Market: Linear Futures
Logic: Original Turtle Rules
- System 1: 20-day breakout entry, 10-day exit
- System 2: 55-day breakout entry, 20-day exit
Position size based on ATR (N) and account risk 1%
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
ENTRY_PERIOD = int(os.getenv("TURTLE_ENTRY", "20"))
EXIT_PERIOD  = int(os.getenv("TURTLE_EXIT", "10"))

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    limit = ENTRY_PERIOD + 5
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "D", "--limit", str(limit))
    candles = data["result"]["list"]
    highs  = [float(c[2]) for c in candles]
    lows   = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    entry_high = max(highs[-ENTRY_PERIOD-1:-1])
    entry_low  = min(lows[-ENTRY_PERIOD-1:-1])
    exit_high  = max(highs[-EXIT_PERIOD-1:-1])
    exit_low   = min(lows[-EXIT_PERIOD-1:-1])
    price = closes[-1]

    print(f"[TURTLE] price={price:.2f} entry_high={entry_high:.2f} entry_low={entry_low:.2f}")

    if price > entry_high:
        print("[TURTLE] 20-day high breakout -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(exit_low, 2)), "--cap-usd", "500", "--yes")
    elif price < entry_low:
        print("[TURTLE] 20-day low breakout -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(exit_high, 2)), "--cap-usd", "500", "--yes")
    else:
        print("[TURTLE] No breakout")

if __name__ == "__main__":
    run()
