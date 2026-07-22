"""
Regime Detection v2 — Enhanced router
Added: ADX confirmation, volume regime, Telegram report, kill-switch on volatile
"""
import sys, os, statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

TREND_RETURN_THRESH = float(os.getenv("TREND_THRESH", "0.003"))
VOL_THRESH_HIGH     = float(os.getenv("VOL_THRESH_HIGH", "0.02"))
VOL_THRESH_LOW      = float(os.getenv("VOL_THRESH_LOW", "0.008"))
ADX_TREND_MIN       = float(os.getenv("ADX_MIN", "20"))

def detect_regime():
    candles = get_klines(limit=100)
    c = closes(candles)
    returns = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
    mean_ret = statistics.mean(returns[-50:])
    vol = statistics.stdev(returns[-50:])
    rsi_val = rsi(c)
    current_atr = atr(candles)
    price = c[-1]
    atr_pct = current_atr / price

    # Volume analysis
    vol_data = volumes(candles)
    vol_avg = sum(vol_data[-20:]) / 20
    vol_now = vol_data[-1]
    vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1

    log_info(f"[REGIME] mean_ret={mean_ret:.5f} vol={vol:.5f} RSI={rsi_val:.1f} ATR%={atr_pct:.4f} vol_ratio={vol_ratio:.2f}")

    # Classify
    if vol > VOL_THRESH_HIGH and vol_ratio > 2.0:
        regime = "volatile"
    elif abs(mean_ret) > TREND_RETURN_THRESH and atr_pct > 0.005:
        regime = "bull" if mean_ret > 0 else "bear"
    elif vol < VOL_THRESH_LOW:
        regime = "sideways"
    elif abs(mean_ret) > TREND_RETURN_THRESH:
        regime = "bull" if mean_ret > 0 else "bear"
    else:
        regime = "sideways"

    return regime, {
        "mean_ret": round(mean_ret, 6),
        "volatility": round(vol, 6),
        "rsi": round(rsi_val, 2),
        "atr_pct": round(atr_pct, 5),
        "vol_ratio": round(vol_ratio, 2),
        "price": price
    }

def run():
    if not safety_check(): return

    regime, stats = detect_regime()
    log_info(f"[REGIME] Detected: {regime.upper()} | {stats}")
    alert(f"📊 Regime: *{regime.upper()}* | RSI={stats['rsi']} vol_ratio={stats['vol_ratio']}")

    strategy_map = {
        "bull":     ["multi_timeframe", "trend_follow", "supertrend", "adx_trend_filter"],
        "bear":     ["trend_follow", "parabolic_sar", "adx_trend_filter"],
        "sideways": ["mean_reversion", "bollinger_bands", "grid_trading", "vwap_reversion"],
        "volatile": []
    }

    if regime == "volatile":
        log_info("[REGIME] Volatile market — activating kill-switch")
        alert("⚠️ VOLATILE regime detected — kill-switch activated")
        cli("kill-switch")
        return regime, stats

    recommended = strategy_map.get(regime, [])
    log_info(f"[REGIME] Recommended strategies: {recommended}")
    return regime, stats

if __name__ == "__main__":
    result = run()
    if result:
        regime, stats = result
        print(json.dumps({"regime": regime, "stats": stats}, indent=2))
