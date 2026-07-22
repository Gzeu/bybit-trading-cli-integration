"""
Parabolic SAR Strategy
Market: Linear Futures
Logic: SAR flips signal direction.
Long when price crosses above SAR, Short when price crosses below SAR.
Step=0.02, Max=0.2
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
STEP = 0.02
MAX_AF = 0.2

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def compute_psar(candles):
    highs  = [float(c[2]) for c in candles]
    lows   = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    bull = True
    af = STEP
    ep = lows[0]
    sar = highs[0]
    sars = [sar]

    for i in range(1, len(closes)):
        if bull:
            sar = sar + af * (ep - sar)
            sar = min(sar, lows[i-1], lows[i-2] if i > 1 else lows[i-1])
            if lows[i] < sar:
                bull = False
                sar = ep
                ep = lows[i]
                af = STEP
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + STEP, MAX_AF)
        else:
            sar = sar + af * (ep - sar)
            sar = max(sar, highs[i-1], highs[i-2] if i > 1 else highs[i-1])
            if highs[i] > sar:
                bull = True
                sar = ep
                ep = highs[i]
                af = STEP
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + STEP, MAX_AF)
        sars.append(sar)
    return sars, bull

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "60")
    candles = data["result"]["list"]
    sars, is_bull = compute_psar(candles)
    price = float(candles[-1][4])
    sar_now = sars[-1]
    print(f"[PSAR] price={price:.2f} sar={sar_now:.2f} bull={is_bull}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if is_bull and side != "Buy":
        print("[PSAR] SAR bullish flip -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(sar_now, 2)), "--cap-usd", "500", "--yes")
    elif not is_bull and side != "Sell":
        print("[PSAR] SAR bearish flip -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(round(sar_now, 2)), "--cap-usd", "500", "--yes")

if __name__ == "__main__":
    run()
