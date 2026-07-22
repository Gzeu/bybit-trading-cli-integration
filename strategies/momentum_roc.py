"""
Rate of Change (ROC) Momentum Strategy
Market: Linear Futures
Logic: ROC(10) = (close - close[10]) / close[10] * 100
Enter long on strong positive momentum, short on strong negative
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
ROC_P = 10
ROC_THRESH = 2.0  # % threshold

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "30")
    closes = [float(c[4]) for c in data["result"]["list"]]
    roc = (closes[-1] - closes[-ROC_P-1]) / closes[-ROC_P-1] * 100
    print(f"[ROC] roc={roc:.3f}%")

    if roc > ROC_THRESH:
        print("[ROC] Strong positive momentum -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif roc < -ROC_THRESH:
        print("[ROC] Strong negative momentum -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[ROC] Momentum below threshold — no trade")

if __name__ == "__main__":
    run()
