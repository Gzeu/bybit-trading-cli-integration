"""
Funding Rate Arbitrage
Market: Linear Futures (short) + Spot (hedge)
Logic: When funding rate is high positive, short perp + buy spot to collect funding
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
QTY = os.getenv("QTY", "0.01")
FUNDING_THRESHOLD = 0.0001  # 0.01% per 8h


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def get_funding_rate():
    data = cli("market", "tickers", "--category", "linear", "--symbol", SYMBOL)
    return float(data["result"]["list"][0]["fundingRate"])


def run():
    rate = get_funding_rate()
    print(f"[FUNDING ARB] Current rate={rate:.6f} (threshold={FUNDING_THRESHOLD})")

    if rate > FUNDING_THRESHOLD:
        print("[FUNDING ARB] High positive funding — SHORT futures + BUY spot")
        # Short the perpetual
        cli("order", "create",
            "--category", "linear", "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")
        # Hedge on spot
        cli("order", "create",
            "--category", "spot", "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")
        print(f"[FUNDING ARB] Collecting ~{rate * 100:.4f}% every 8h")

    elif rate < -FUNDING_THRESHOLD:
        print("[FUNDING ARB] High negative funding — LONG futures + SELL spot")
        cli("order", "create",
            "--category", "linear", "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")
        cli("order", "create",
            "--category", "spot", "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")
    else:
        print("[FUNDING ARB] Rate below threshold — no trade")


if __name__ == "__main__":
    run()
