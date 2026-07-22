"""
Heikin Ashi Trend Strategy
Market: Linear Futures
Logic: Convert candles to Heikin Ashi. Enter trend on consecutive HA candles
no lower wicks = strong uptrend, no upper wicks = strong downtrend
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
CONSEC = 3  # consecutive HA candles required

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def to_ha(candles):
    ha = []
    for i, c in enumerate(candles):
        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        ha_close = (o + h + l + cl) / 4
        ha_open = (ha[i-1][0] + ha[i-1][3]) / 2 if i > 0 else (o + cl) / 2
        ha_high = max(h, ha_open, ha_close)
        ha_low  = min(l, ha_open, ha_close)
        ha.append((ha_open, ha_high, ha_low, ha_close))
    return ha

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "30")
    ha = to_ha(data["result"]["list"])
    recent = ha[-CONSEC:]

    bullish = all(c[3] > c[0] for c in recent)  # close > open
    bearish = all(c[3] < c[0] for c in recent)
    no_lower_wick = all(c[2] == c[0] for c in recent)  # low == open (no lower wick)
    no_upper_wick = all(c[1] == c[3] for c in recent)  # high == close (no upper wick)

    print(f"[HA] bullish={bullish} bearish={bearish} no_low_wick={no_lower_wick} no_up_wick={no_upper_wick}")

    if bullish and no_lower_wick:
        print("[HA] Strong uptrend signal -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif bearish and no_upper_wick:
        print("[HA] Strong downtrend signal -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[HA] Weak/mixed HA signal — no trade")

if __name__ == "__main__":
    run()
