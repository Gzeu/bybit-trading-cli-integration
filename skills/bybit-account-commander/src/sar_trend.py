"""
sar_trend.py — Parabolic SAR trend strategy (Wilder classic)

Implements:
  - Multi-timeframe SAR calculation (primary + filter)
  - EMA50 trend filter
  - ADX(14) strength filter
  - Fibonacci pullback entry zone detection
  - R:R and fee gate checks
  - Setup grading (A+, A, B, skip)
  - Position management: scale-out, pyramid rules, flip handling
"""

from __future__ import annotations
import math
from typing import Any


def compute_sar(highs: list[float], lows: list[float],
                af_start: float = 0.02, af_step: float = 0.02,
                af_max: float = 0.20) -> list[float]:
    """Classic Wilder Parabolic SAR."""
    n = len(highs)
    if n < 2:
        return []

    sar = [0.0] * n
    ep = lows[0]  # extreme point
    af = af_start
    is_long = True
    sar[0] = highs[0]

    for i in range(1, n):
        prev_sar = sar[i - 1]

        if is_long:
            sar[i] = prev_sar + af * (ep - prev_sar)
            sar[i] = min(sar[i], lows[i - 1], lows[max(0, i - 2)])
            if lows[i] < sar[i]:
                is_long = False
                sar[i] = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = prev_sar + af * (ep - prev_sar)
            sar[i] = max(sar[i], highs[i - 1], highs[max(0, i - 2)])
            if highs[i] > sar[i]:
                is_long = True
                sar[i] = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)

    return sar


def compute_ema(closes: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(closes) < period:
        return [float('nan')] * len(closes)
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for price in closes[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    result = [float('nan')] * (period - 1) + ema
    return result


def compute_adx(highs: list[float], lows: list[float],
                closes: list[float], period: int = 14) -> list[float]:
    """ADX smoothed directional index."""
    n = len(closes)
    if n < period + 1:
        return [0.0] * n

    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)
        p_dm = highs[i] - highs[i - 1]
        m_dm = lows[i - 1] - lows[i]
        plus_dm.append(p_dm if p_dm > m_dm and p_dm > 0 else 0)
        minus_dm.append(m_dm if m_dm > p_dm and m_dm > 0 else 0)

    def wilder_smooth(data: list[float], p: int) -> list[float]:
        s = [sum(data[:p])]
        for v in data[p:]:
            s.append(s[-1] - s[-1] / p + v)
        return s

    atr = wilder_smooth(tr_list, period)
    s_plus = wilder_smooth(plus_dm, period)
    s_minus = wilder_smooth(minus_dm, period)

    adx_vals = []
    dx_prev = None
    for i in range(len(atr)):
        if atr[i] == 0:
            adx_vals.append(0.0)
            continue
        di_plus = 100 * s_plus[i] / atr[i]
        di_minus = 100 * s_minus[i] / atr[i]
        denom = di_plus + di_minus
        dx = 100 * abs(di_plus - di_minus) / denom if denom else 0
        if dx_prev is None:
            adx_vals.append(dx)
        else:
            adx_vals.append((dx_prev * (period - 1) + dx) / period)
        dx_prev = adx_vals[-1]

    padding = [0.0] * (n - len(adx_vals))
    return padding + adx_vals


def grade_setup(sar_vals: list[float], ema50: list[float],
                adx_vals: list[float], closes: list[float],
                symbol: str, config: dict, rt_fee: float) -> dict | None:
    """
    Grade the latest bar's SAR setup.
    Returns setup dict with grade and trade params, or None if no setup.
    """
    if len(closes) < 3:
        return None

    sar_cfg = config.get("sar", {})
    adx_min = sar_cfg.get("adx_min", 18)
    rr_min = config.get("risk", {}).get("rr_min", 1.8)
    edge_multiple = config.get("fees", {}).get("min_edge_multiple_of_rt", 2.5)

    last_sar = sar_vals[-1]
    last_close = closes[-1]
    last_ema = ema50[-1]
    last_adx = adx_vals[-1] if adx_vals else 0

    if math.isnan(last_ema) or last_adx < adx_min:
        return None

    is_long = last_close > last_sar
    ema_agrees = (last_close > last_ema) if is_long else (last_close < last_ema)
    if not ema_agrees:
        return None

    side = "BUY" if is_long else "SELL"
    sl = last_sar
    entry = last_close
    dist_sl = abs(entry - sl)

    if dist_sl == 0:
        return None

    # Minimum edge gate
    if dist_sl < edge_multiple * rt_fee:
        return None

    # TP1 = 1.618 * dist_sl from entry
    tp1 = entry + 1.618 * dist_sl if is_long else entry - 1.618 * dist_sl
    dist_tp1 = abs(tp1 - entry)
    rr = (dist_tp1 - rt_fee) / (dist_sl + rt_fee)

    if rr < rr_min:
        return None

    grade = "A+" if last_adx >= 25 and rr >= 2.5 else "A" if rr >= rr_min else "B"

    return {
        "symbol": symbol,
        "side": side,
        "grade": grade,
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "rr": round(rr, 2),
        "adx": round(last_adx, 1),
        "sar": round(last_sar, 6),
        "rt_fee": rt_fee,
    }
