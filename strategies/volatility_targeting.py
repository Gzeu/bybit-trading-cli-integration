"""
Volatility Targeting / Risk Parity Strategy
Market: Linear Futures
Logic: Adjust position size dynamically to target constant portfolio volatility.
Target vol = 1% daily. If realized vol is high, reduce size; if low, increase.
"""
import subprocess, json, os, statistics, math

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
TARGET_VOL = float(os.getenv("TARGET_VOL", "0.01"))  # 1% daily
BASE_QTY   = float(os.getenv("BASE_QTY", "0.01"))
LOOKBACK   = 20  # days

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "D", "--limit", str(LOOKBACK + 1))
    closes = [float(c[4]) for c in data["result"]["list"]]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    realized_vol = statistics.stdev(returns)

    scale = TARGET_VOL / realized_vol if realized_vol > 0 else 1.0
    adj_qty = round(BASE_QTY * scale, 4)
    adj_qty = max(0.001, min(adj_qty, BASE_QTY * 3))  # cap at 3x base

    print(f"[VOL TARGET] realized_vol={realized_vol:.4f} scale={scale:.3f} adj_qty={adj_qty}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    # Simple: enter long with vol-adjusted size
    if side == "None":
        print(f"[VOL TARGET] No position — entering LONG with vol-adjusted qty={adj_qty}")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", str(adj_qty),
            "--cap-usd", "500", "--yes")
    else:
        print(f"[VOL TARGET] Position exists ({side}). Adjust manually if needed.")

if __name__ == "__main__":
    run()
