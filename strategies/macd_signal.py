"""
MACD Signal Line Crossover Strategy
Market: Linear Futures
Logic: MACD(12,26,9) — enter on MACD line crossing signal line
Long when MACD crosses above signal, Short when crosses below
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def ema(prices, period):
    k = 2 / (period + 1)
    e = prices[0]
    for p in prices[1:]:
        e = p * k + e * (1 - k)
    return e

def macd_line(closes):
    return ema(closes, 12) - ema(closes, 26)

def signal_line(macd_values, period=9):
    return ema(macd_values, period)

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "100")
    closes = [float(c[4]) for c in data["result"]["list"]]

    macd_values = [macd_line(closes[:i+1]) for i in range(26, len(closes))]
    sig = signal_line(macd_values)

    macd_now = macd_values[-1]
    macd_prev = macd_values[-2]
    sig_now = signal_line(macd_values[:-1])

    cross_up = macd_prev < sig_now and macd_now > sig
    cross_down = macd_prev > sig_now and macd_now < sig

    print(f"[MACD] macd={macd_now:.4f} signal={sig:.4f} cross_up={cross_up} cross_down={cross_down}")

    if cross_up:
        print("[MACD] Bullish cross -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif cross_down:
        print("[MACD] Bearish cross -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[MACD] No cross signal")

if __name__ == "__main__":
    run()
