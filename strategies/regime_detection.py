"""
Regime Detection Strategy — HMM-inspired (simplified)
Market: Any
Logic: Classify market into Bull / Bear / Sideways using returns + volatility.
Route to appropriate strategy module per regime.
"""
import subprocess, json, os, statistics

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "linear")
LOOKBACK = 50

# Thresholds
TREND_RETURN_THRESH = 0.003   # 0.3% mean return to call trending
VOL_THRESH = 0.015            # 1.5% std to call high volatility


def cli(*args):
    r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
    return json.loads(r.stdout)


def detect_regime():
    data = cli("market", "kline", "--category", CATEGORY,
               "--symbol", SYMBOL, "--interval", "60", "--limit", str(LOOKBACK + 1))
    closes = [float(c[4]) for c in data["result"]["list"]]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

    mean_ret = statistics.mean(returns)
    vol = statistics.stdev(returns)

    print(f"[REGIME] mean_return={mean_ret:.5f} volatility={vol:.5f}")

    if abs(mean_ret) > TREND_RETURN_THRESH:
        regime = "bull" if mean_ret > 0 else "bear"
    elif vol < VOL_THRESH:
        regime = "sideways"
    else:
        regime = "volatile"  # high vol, no clear direction — stay flat

    return regime, mean_ret, vol


def run():
    regime, mean_ret, vol = detect_regime()
    print(f"[REGIME] Detected: {regime.upper()}")

    if regime == "bull":
        print("[REGIME] → Run: strategies/trend_follow.py or kalman_filter.py")
    elif regime == "bear":
        print("[REGIME] → Run: strategies/trend_follow.py (short bias) or kalman_filter.py")
    elif regime == "sideways":
        print("[REGIME] → Run: strategies/mean_reversion.py or grid_trading.py")
    elif regime == "volatile":
        print("[REGIME] → No trade. High vol, no clear trend. Consider kill-switch.")
        os.system("bybit-cli kill-switch")

    return regime


if __name__ == "__main__":
    run()
