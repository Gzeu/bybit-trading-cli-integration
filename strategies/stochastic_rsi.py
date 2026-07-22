"""
Stochastic RSI Strategy
Market: Linear Futures
Logic: StochRSI(14,14,3,3) — enter on overbought/oversold crossovers
Long when StochRSI crosses above 20 from below
Short when StochRSI crosses below 80 from above
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
RSI_P = 14
STOCH_P = 14

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def rsi_series(closes, period=14):
    result = []
    for i in range(period, len(closes)):
        window = closes[i-period:i+1]
        gains = [max(window[j]-window[j-1],0) for j in range(1,len(window))]
        losses = [max(window[j-1]-window[j],0) for j in range(1,len(window))]
        ag = sum(gains)/period
        al = sum(losses)/period
        rs = ag/al if al > 0 else 100
        result.append(100 - 100/(1+rs))
    return result

def stoch_rsi(rsi_vals, period=14):
    result = []
    for i in range(period, len(rsi_vals)):
        window = rsi_vals[i-period:i+1]
        lo, hi = min(window), max(window)
        result.append((rsi_vals[i] - lo) / (hi - lo) * 100 if hi != lo else 50)
    return result

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "100")
    closes = [float(c[4]) for c in data["result"]["list"]]
    rsi_vals = rsi_series(closes)
    srsi = stoch_rsi(rsi_vals)

    if len(srsi) < 2:
        print("[STOCH RSI] Not enough data")
        return

    curr, prev = srsi[-1], srsi[-2]
    print(f"[STOCH RSI] curr={curr:.2f} prev={prev:.2f}")

    if prev < 20 and curr >= 20:
        print("[STOCH RSI] Cross above 20 -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif prev > 80 and curr <= 80:
        print("[STOCH RSI] Cross below 80 -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[STOCH RSI] No signal")

if __name__ == "__main__":
    run()
