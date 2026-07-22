"""
Grid Trading Strategy
Market: Spot (can adapt to linear)
Logic: Place buy/sell limit orders at equal price intervals within a defined range
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "spot")
GRID_LOWER = float(os.getenv("GRID_LOWER", "55000"))
GRID_UPPER = float(os.getenv("GRID_UPPER", "70000"))
GRID_LEVELS = int(os.getenv("GRID_LEVELS", "10"))
QTY_PER_GRID = os.getenv("QTY_PER_GRID", "0.001")


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def place_grid():
    step = (GRID_UPPER - GRID_LOWER) / GRID_LEVELS
    levels = [round(GRID_LOWER + i * step, 2) for i in range(GRID_LEVELS + 1)]

    ticker = cli("market", "tickers", "--category", CATEGORY, "--symbol", SYMBOL)
    mid = float(ticker["result"]["list"][0]["lastPrice"])
    print(f"[GRID] Mid price: {mid} | Levels: {len(levels)}")

    for price in levels:
        side = "Buy" if price < mid else "Sell"
        result = cli("order", "create",
                     "--category", CATEGORY, "--symbol", SYMBOL,
                     "--side", side, "--orderType", "Limit",
                     "--price", str(price), "--qty", QTY_PER_GRID,
                     "--timeInForce", "GTC",
                     "--cap-usd", "200", "--yes")
        status = result.get("retCode", -1)
        print(f"  [{side}] {price} — {'OK' if status == 0 else 'ERR: ' + result.get('retMsg', '')}")


if __name__ == "__main__":
    place_grid()
