"""
Open Interest Spike Strategy
Market: Linear Futures
Logic: Large OI increases signal strong directional moves.
Combine with price direction: OI up + price up -> LONG, OI up + price down -> SHORT
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
OI_CHANGE_THRESH = 0.02  # 2% OI change

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def run():
    oi_data = cli("market", "open-interest", "--category", CATEGORY, "--symbol", SYMBOL, "--intervalTime", "5min", "--limit", "10")
    oi_list = oi_data["result"]["list"]
    oi_now  = float(oi_list[0]["openInterest"])
    oi_prev = float(oi_list[-1]["openInterest"])
    oi_change = (oi_now - oi_prev) / oi_prev

    ticker = cli("market", "tickers", "--category", CATEGORY, "--symbol", SYMBOL)
    price_change = float(ticker["result"]["list"][0]["price24hPcnt"])

    print(f"[OI] oi_change={oi_change:.4f} price_24h_pct={price_change:.4f}")

    if oi_change > OI_CHANGE_THRESH and price_change > 0:
        print("[OI] OI spike + rising price -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif oi_change > OI_CHANGE_THRESH and price_change < 0:
        print("[OI] OI spike + falling price -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[OI] No significant OI spike")

if __name__ == "__main__":
    run()
