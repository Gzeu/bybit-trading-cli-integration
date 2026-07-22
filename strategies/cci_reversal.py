"""
CCI Reversal Strategy
Market: Linear Futures / Spot
Logic: CCI(20) — enter reversal when CCI exits extreme zones
Long when CCI crosses above -100 (oversold exit)
Short when CCI crosses below +100 (overbought exit)
"""
import subprocess, json, os, statistics

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
CCI_P = 20

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def cci(candles, period=20):
    typicals = [(float(c[2])+float(c[3])+float(c[4]))/3 for c in candles]
    window = typicals[-period:]
    mean = statistics.mean(window)
    mad = statistics.mean([abs(x - mean) for x in window])
    return (typicals[-1] - mean) / (0.015 * mad) if mad > 0 else 0

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "60")
    candles = data["result"]["list"]
    cci_now = cci(candles)
    cci_prev = cci(candles[:-1])

    print(f"[CCI] cci_now={cci_now:.2f} cci_prev={cci_prev:.2f}")

    if cci_prev < -100 and cci_now >= -100:
        print("[CCI] Exiting oversold -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif cci_prev > 100 and cci_now <= 100:
        print("[CCI] Exiting overbought -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[CCI] No reversal signal")

if __name__ == "__main__":
    run()
