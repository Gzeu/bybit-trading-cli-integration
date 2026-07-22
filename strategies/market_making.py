"""
Market Making Strategy
Market: Spot or Linear Futures
Logic: Post limit buy and sell orders around mid-price.
Capture bid-ask spread. Skew quotes based on inventory.
NOTE: High frequency, monitor order count cap carefully.
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "spot")
QTY = os.getenv("QTY", "0.001")
SPREAD_PCT = float(os.getenv("SPREAD_PCT", "0.001"))  # 0.1%
INVENTORY_SKEW = float(os.getenv("INVENTORY_SKEW", "0.0002"))  # 0.02%

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    # Cancel existing MM orders first
    cli("order", "cancel-all", "--category", CATEGORY, "--symbol", SYMBOL, "--yes")

    ticker = cli("market", "tickers", "--category", CATEGORY, "--symbol", SYMBOL)
    mid = float(ticker["result"]["list"][0]["lastPrice"])

    bid = round(mid * (1 - SPREAD_PCT / 2 - INVENTORY_SKEW), 2)
    ask = round(mid * (1 + SPREAD_PCT / 2 + INVENTORY_SKEW), 2)

    print(f"[MM] mid={mid:.2f} bid={bid:.2f} ask={ask:.2f}")

    cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
        "--side", "Buy", "--orderType", "Limit", "--price", str(bid),
        "--qty", QTY, "--timeInForce", "GTC", "--cap-usd", "200", "--yes")

    cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
        "--side", "Sell", "--orderType", "Limit", "--price", str(ask),
        "--qty", QTY, "--timeInForce", "GTC", "--cap-usd", "200", "--yes")

if __name__ == "__main__":
    run()
