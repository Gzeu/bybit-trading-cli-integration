"""
Williams %R Strategy
Market: Linear Futures
Logic: Williams %R(14) oscillator momentum
Long when %R crosses above -80 (oversold reversal)
Short when %R crosses below -20 (overbought reversal)
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
PERIOD = 14

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def williams_r(candles, period=14):
    highs  = [float(c[2]) for c in candles[-period:]]
    lows   = [float(c[3]) for c in candles[-period:]]
    close  = float(candles[-1][4])
    hh, ll = max(highs), min(lows)
    return ((hh - close) / (hh - ll)) * -100 if hh != ll else -50

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "50")
    candles = data["result"]["list"]
    wr_now  = williams_r(candles)
    wr_prev = williams_r(candles[:-1])

    print(f"[WR] wr_now={wr_now:.2f} wr_prev={wr_prev:.2f}")

    if wr_prev < -80 and wr_now >= -80:
        print("[WR] Oversold reversal -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif wr_prev > -20 and wr_now <= -20:
        print("[WR] Overbought reversal -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[WR] No reversal signal")

if __name__ == "__main__":
    run()
