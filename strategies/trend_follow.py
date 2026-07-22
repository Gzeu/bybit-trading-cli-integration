"""
Trend Following Strategy — EMA Crossover
Market: Linear Futures (USDT-margined)
Logic: Enter long on EMA fast > EMA slow cross, short on reverse
"""
import subprocess, json, os
from collections import deque

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
FAST = 9
SLOW = 21
LEVERAGE = 5
RISK_PCT = 0.01  # 1% per trade


def cli(*args):
    result = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(result.stdout)


def get_klines(interval="60", limit=100):
    data = cli("market", "kline",
               "--category", CATEGORY,
               "--symbol", SYMBOL,
               "--interval", interval,
               "--limit", str(limit))
    return [float(c[4]) for c in data["result"]["list"]]  # close prices


def ema(prices, period):
    k = 2 / (period + 1)
    e = prices[0]
    for p in prices[1:]:
        e = p * k + e * (1 - k)
    return e


def run():
    closes = get_klines()
    fast_ema = ema(closes[-FAST * 3:], FAST)
    slow_ema = ema(closes[-SLOW * 3:], SLOW)

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    current_side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if fast_ema > slow_ema and current_side != "Buy":
        print(f"[TREND] EMA cross UP — entering LONG")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market",
            "--qty", QTY, "--cap-usd", "500", "--yes")

    elif fast_ema < slow_ema and current_side != "Sell":
        print(f"[TREND] EMA cross DOWN — entering SHORT")
        cli("order", "create",
            "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market",
            "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print(f"[TREND] No signal. fast={fast_ema:.2f} slow={slow_ema:.2f}")


if __name__ == "__main__":
    run()
