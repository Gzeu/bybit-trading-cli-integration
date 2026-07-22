"""
Breakout Strategy — ATR-based
Market: Linear Futures
Logic: Enter on confirmed candle close beyond ATR bands
"""
import subprocess, json, os, math

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
ATR_PERIOD = 14
ATR_MULT = 1.5


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def compute_atr(candles):
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = float(candles[i][2]), float(candles[i][3]), float(candles[i-1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD
    return atr


def run():
    data = cli("market", "kline", "--category", CATEGORY,
               "--symbol", SYMBOL, "--interval", "60", "--limit", "50")
    candles = data["result"]["list"]
    atr = compute_atr(candles)
    last_close = float(candles[-1][4])
    prev_close = float(candles[-2][4])

    upper = prev_close + ATR_MULT * atr
    lower = prev_close - ATR_MULT * atr
    print(f"[BREAKOUT] close={last_close} upper={upper:.2f} lower={lower:.2f} ATR={atr:.2f}")

    if last_close > upper:
        sl = round(last_close - atr, 2)
        tp = round(last_close + atr * 2, 2)
        print(f"[BREAKOUT] Upside breakout — LONG | SL={sl} TP={tp}")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(sl), "--takeProfit", str(tp),
            "--cap-usd", "500", "--yes")

    elif last_close < lower:
        sl = round(last_close + atr, 2)
        tp = round(last_close - atr * 2, 2)
        print(f"[BREAKOUT] Downside breakout — SHORT | SL={sl} TP={tp}")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--stopLoss", str(sl), "--takeProfit", str(tp),
            "--cap-usd", "500", "--yes")
    else:
        print("[BREAKOUT] No breakout confirmed")


if __name__ == "__main__":
    run()
