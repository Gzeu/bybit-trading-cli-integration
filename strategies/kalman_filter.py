"""
Kalman Filter Trend Strategy
Market: Linear Futures
Logic: Use Kalman filter as adaptive trend estimator.
Enter long when price > filter + noise_band, short when price < filter - noise_band.
"""
import subprocess, json, os

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = "linear"
QTY = os.getenv("QTY", "0.01")

# Kalman parameters
Q = 1e-5   # process noise — higher = faster adaptation
R = 0.01   # measurement noise — higher = smoother
NOISE_BAND = 0.003  # 0.3% deviation to trigger signal


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def kalman_filter(prices):
    x = prices[0]  # initial state
    p = 1.0        # initial error covariance
    estimates = []
    for z in prices:
        p = p + Q
        k = p / (p + R)
        x = x + k * (z - x)
        p = (1 - k) * p
        estimates.append(x)
    return estimates


def run():
    data = cli("market", "kline", "--category", CATEGORY,
               "--symbol", SYMBOL, "--interval", "60", "--limit", "100")
    closes = [float(c[4]) for c in data["result"]["list"]]
    estimates = kalman_filter(closes)

    price = closes[-1]
    kf_val = estimates[-1]
    deviation = (price - kf_val) / kf_val
    print(f"[KALMAN] price={price:.2f} filter={kf_val:.2f} deviation={deviation:.4f}")

    pos = cli("position", "info", "--category", CATEGORY, "--symbol", SYMBOL)
    side = pos["result"]["list"][0]["side"] if pos["result"]["list"] else "None"

    if deviation > NOISE_BAND and side != "Buy":
        print("[KALMAN] Price above filter — LONG")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Buy", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")

    elif deviation < -NOISE_BAND and side != "Sell":
        print("[KALMAN] Price below filter — SHORT")
        cli("order", "create", "--category", CATEGORY, "--symbol", SYMBOL,
            "--side", "Sell", "--orderType", "Market", "--qty", QTY,
            "--cap-usd", "500", "--yes")
    else:
        print("[KALMAN] Within noise band — no trade")


if __name__ == "__main__":
    run()
