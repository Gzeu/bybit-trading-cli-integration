"""
VWAP Reversion Strategy
Market: Linear Futures
Logic: Enter when price deviates significantly from VWAP.
Mean-revert back toward VWAP. Best on intraday (15m/1h).
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
DEV_THRESHOLD = 0.005  # 0.5% from VWAP

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def compute_vwap(candles):
    cum_pv, cum_vol = 0, 0
    for c in candles:
        typical = (float(c[2]) + float(c[3]) + float(c[4])) / 3  # (H+L+C)/3
        vol = float(c[5])
        cum_pv += typical * vol
        cum_vol += vol
    return cum_pv / cum_vol if cum_vol > 0 else 0

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "15", "--limit", "96")
    candles = data["result"]["list"]
    vwap = compute_vwap(candles)
    price = float(candles[-1][4])
    dev = (price - vwap) / vwap

    print(f"[VWAP] price={price:.2f} vwap={vwap:.2f} deviation={dev:.4f}")

    if dev > DEV_THRESHOLD:
        print("[VWAP] Price above VWAP -> SHORT reversion")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--takeProfit", str(round(vwap, 2)), "--cap-usd", "500", "--yes")
    elif dev < -DEV_THRESHOLD:
        print("[VWAP] Price below VWAP -> LONG reversion")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--takeProfit", str(round(vwap, 2)), "--cap-usd", "500", "--yes")
    else:
        print("[VWAP] Near VWAP — no trade")

if __name__ == "__main__":
    run()
