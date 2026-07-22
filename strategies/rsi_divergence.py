"""
RSI Divergence Strategy
Market: Linear Futures
Logic: Detect bullish/bearish divergence between price and RSI(14)
Bullish div: price makes lower low, RSI makes higher low -> LONG
Bearish div: price makes higher high, RSI makes lower high -> SHORT
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")
RSI_PERIOD = 14
LOOKBACK = 5  # candles to check divergence

def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)

def compute_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def run():
    data = cli("market", "kline", "--category", CATEGORY, "--symbol", SYMBOL, "--interval", "60", "--limit", "60")
    candles = data["result"]["list"]
    closes = [float(c[4]) for c in candles]

    rsi_series = [compute_rsi(closes[:i+1]) for i in range(RSI_PERIOD, len(closes))]
    prices = closes[RSI_PERIOD:]

    # Check last LOOKBACK candles for divergence
    p_slice = prices[-LOOKBACK:]
    r_slice = rsi_series[-LOOKBACK:]

    bullish_div = (p_slice[-1] < p_slice[0]) and (r_slice[-1] > r_slice[0])
    bearish_div = (p_slice[-1] > p_slice[0]) and (r_slice[-1] < r_slice[0])

    rsi_now = rsi_series[-1]
    print(f"[RSI DIV] RSI={rsi_now:.2f} bullish_div={bullish_div} bearish_div={bearish_div}")

    if bullish_div and rsi_now < 45:
        print("[RSI DIV] Bullish divergence -> LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    elif bearish_div and rsi_now > 55:
        print("[RSI DIV] Bearish divergence -> SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY, "--cap-usd", "500", "--yes")
    else:
        print("[RSI DIV] No divergence signal")

if __name__ == "__main__":
    run()
