"""
DCA (Dollar Cost Averaging) Accumulation Strategy
Market: Spot
Logic: Buy fixed USD amount at each interval regardless of price.
Increase buy size when price drops by a defined % from last buy.
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "spot"
BASE_USDT = float(os.getenv("DCA_AMOUNT", "50"))  # $50 base buy
DROP_MULT  = float(os.getenv("DCA_DROP_MULT", "1.5"))  # 1.5x on dip
DIP_THRESH = float(os.getenv("DCA_DIP", "0.03"))  # 3% dip
LAST_BUY_PRICE_FILE = "/tmp/bybit_dca_last_price.txt"

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    ticker = cli("market", "tickers", "--category", CATEGORY, "--symbol", SYMBOL)
    price = float(ticker["result"]["list"][0]["lastPrice"])

    try:
        with open(LAST_BUY_PRICE_FILE) as f:
            last_price = float(f.read().strip())
    except:
        last_price = price

    dip = (last_price - price) / last_price
    buy_usdt = BASE_USDT * DROP_MULT if dip >= DIP_THRESH else BASE_USDT
    qty = round(buy_usdt / price, 6)

    print(f"[DCA] price={price:.2f} last_buy={last_price:.2f} dip={dip:.3f} buy={buy_usdt} qty={qty}")

    cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
        "--side", "Buy", "--orderType", "Market", "--qty", str(qty),
        "--cap-usd", str(int(buy_usdt * 1.1)), "--yes")

    with open(LAST_BUY_PRICE_FILE, "w") as f:
        f.write(str(price))

if __name__ == "__main__":
    run()
