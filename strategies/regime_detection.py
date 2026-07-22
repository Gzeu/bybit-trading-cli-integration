"""
Regime Detection v3 — returns regime without side effects.
Fix: volatile regime NO LONGER activates kill-switch.
     Kill-switch is a manual/safety-check decision, not automatic.
     Volatile regime now routes to breakout/liquidation_hunt strategies.
"""
import sys, os, statistics, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.engine import *

TREND_THRESH   = float(os.getenv("TREND_THRESH",    "0.003"))
VOL_HIGH       = float(os.getenv("VOL_THRESH_HIGH", "0.02"))
VOL_LOW        = float(os.getenv("VOL_THRESH_LOW",  "0.008"))

STRATEGY_MAP = {
    "bull":     ["multi_timeframe", "trend_follow", "supertrend", "adx_trend_filter",
                 "triple_ema", "kalman_filter", "macd_signal", "turtle_trading"],
    "bear":     ["trend_follow", "parabolic_sar", "adx_trend_filter",
                 "supertrend", "macd_signal", "kalman_filter"],
    "sideways": ["mean_reversion", "bollinger_bands", "grid_trading", "vwap_reversion",
                 "stochastic_rsi", "cci_reversal", "market_making", "williams_r"],
    "volatile": ["breakout", "liquidation_hunt", "open_interest_spike",
                 "turtle_trading", "funding_arb"],  # NO kill-switch — these thrive on volatility
}


def detect_regime(symbol=None, category=None):
    sym = symbol or SYMBOL
    cat = category or CATEGORY
    candles = get_klines(interval="60", limit=100, symbol=sym, category=cat)
    c = closes(candles)
    returns = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
    mean_ret = statistics.mean(returns[-50:])
    vol      = statistics.stdev(returns[-50:])
    rsi_val  = rsi(c)
    atr_val  = atr(candles)
    price    = c[-1]
    atr_pct  = atr_val / price if price else 0

    vol_data  = volumes(candles)
    vol_avg   = sum(vol_data[-20:]) / 20
    vol_ratio = vol_data[-1] / vol_avg if vol_avg > 0 else 1

    log_info(f"[REGIME] {sym} mean_ret={mean_ret:.5f} vol={vol:.5f} RSI={rsi_val:.1f} "
             f"ATR%={atr_pct:.4f} vol_ratio={vol_ratio:.2f}")

    # Classify
    if vol > VOL_HIGH and vol_ratio > 1.8:
        regime = "volatile"
    elif abs(mean_ret) > TREND_THRESH and atr_pct > 0.005:
        regime = "bull" if mean_ret > 0 else "bear"
    elif vol < VOL_LOW:
        regime = "sideways"
    elif abs(mean_ret) > TREND_THRESH:
        regime = "bull" if mean_ret > 0 else "bear"
    else:
        regime = "sideways"

    stats = {
        "mean_ret":   round(mean_ret, 6),
        "volatility": round(vol, 6),
        "rsi":        round(rsi_val, 2),
        "atr_pct":    round(atr_pct, 5),
        "vol_ratio":  round(vol_ratio, 2),
        "price":      price,
    }
    return regime, stats


def run(symbol=None, category=None):
    if not safety_check(): return None, {}

    regime, stats = detect_regime(symbol, category)
    recommended = STRATEGY_MAP.get(regime, [])

    log_info(f"[REGIME] {symbol or SYMBOL}: {regime.upper()} → {recommended}")
    alert(f"📊 Regime *{regime.upper()}* {symbol or SYMBOL} | RSI={stats['rsi']} vol_ratio={stats['vol_ratio']}")

    # Volatile: log warning but DO NOT activate kill-switch
    if regime == "volatile":
        log_info("[REGIME] Volatile — routing to breakout strategies (no kill-switch)")
        alert("⚠️ Volatile regime — using breakout/liquidation strategies")

    return regime, stats


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol",   default=None)
    p.add_argument("--category", default=None)
    p.add_argument("--json",     action="store_true")
    args = p.parse_args()

    regime, stats = run(args.symbol, args.category)
    if regime:
        out = {"regime": regime, "stats": stats, "strategies": STRATEGY_MAP.get(regime, [])}
        print(json.dumps(out, indent=2 if not args.json else None))
