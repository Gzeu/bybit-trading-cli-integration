"""
entry_policy.py — Market vs Limit entry decision

Rules (from SKILL.md §4.3):
  MARKET if ALL:
    - Confirmed SAR flip/breakout
    - Body >= 0.6 * ATR
    - Volume >= 1.3 * SMA20_volume
    - Invalidation distance <= 0.4 * ATR
    - Slip cost <= 0.25 * RT
  Otherwise: PostOnly LIMIT at bid/ask±fib-sar buffer

Returns: {order_type, price, time_in_force, reduce_only}
"""

from __future__ import annotations
import statistics


def compute_atr(highs: list[float], lows: list[float],
                closes: list[float], period: int = 14) -> float:
    """Average True Range."""
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if not trs:
        return 0.0
    recent = trs[-period:]
    return sum(recent) / len(recent)


def compute_volume_sma(volumes: list[float], period: int = 20) -> float:
    """Simple moving average of volume."""
    recent = volumes[-period:]
    return sum(recent) / len(recent) if recent else 0.0


def decide_entry(
    side: str,
    entry_price: float,
    sar_price: float,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    rt_fee_rate: float,
    slip_estimate: float = 0.0,
    config: dict | None = None,
) -> dict:
    """
    Decide between MARKET and PostOnly LIMIT order.

    Returns dict:
      {
        order_type: 'Market' | 'Limit',
        price: float | None,   # None for Market
        time_in_force: 'IOC' | 'PostOnly',
        is_market: bool,
        reason: str,
      }
    """
    cfg = config or {}
    prefer_postonly = cfg.get("fees", {}).get("prefer_postonly", True)

    atr = compute_atr(highs, lows, closes, period=14)
    if atr == 0:
        return _limit_order(side, entry_price, sar_price, reason="ATR=0, default to limit")

    # Last bar body size
    last_body = abs(closes[-1] - closes[-2]) if len(closes) >= 2 else 0.0
    body_ratio = last_body / atr

    # Volume check
    vol_sma = compute_volume_sma(volumes, period=20)
    last_vol = volumes[-1] if volumes else 0.0
    vol_ratio = (last_vol / vol_sma) if vol_sma else 0.0

    # Invalidation distance (entry to SAR)
    invalidation_dist = abs(entry_price - sar_price)
    inv_ratio = invalidation_dist / atr

    # Slip cost vs RT
    slip_rt_ratio = (slip_estimate / rt_fee_rate) if rt_fee_rate else 0.0

    # Market conditions (all must pass)
    market_conditions = {
        "body_ge_0.6_atr": body_ratio >= 0.6,
        "vol_ge_1.3_sma": vol_ratio >= 1.3,
        "inv_le_0.4_atr": inv_ratio <= 0.4,
        "slip_le_0.25_rt": slip_rt_ratio <= 0.25,
    }

    all_pass = all(market_conditions.values())
    failed = [k for k, v in market_conditions.items() if not v]

    if all_pass and not prefer_postonly:
        return {
            "order_type": "Market",
            "price": None,
            "time_in_force": "IOC",
            "is_market": True,
            "reason": "All market conditions passed",
            "conditions": market_conditions,
        }
    else:
        limit_price = _compute_limit_price(side, entry_price, sar_price, atr)
        return {
            "order_type": "Limit",
            "price": limit_price,
            "time_in_force": "PostOnly",
            "is_market": False,
            "reason": f"Limit/PostOnly — failed: {failed}" if failed else "PostOnly preferred",
            "conditions": market_conditions,
        }


def _compute_limit_price(side: str, entry: float,
                          sar: float, atr: float) -> float:
    """
    PostOnly limit price: bid/ask with small SAR buffer.
    BUY  → entry slightly below current ask (bid side)
    SELL → entry slightly above current bid (ask side)
    Buffer = 0.1 * ATR
    """
    buffer = 0.1 * atr
    if side == "BUY":
        return round(entry - buffer, 6)
    else:
        return round(entry + buffer, 6)


def _limit_order(side: str, entry: float, sar: float,
                 reason: str = "") -> dict:
    """Default limit order fallback."""
    return {
        "order_type": "Limit",
        "price": entry,
        "time_in_force": "PostOnly",
        "is_market": False,
        "reason": reason or "Default limit",
        "conditions": {},
    }
