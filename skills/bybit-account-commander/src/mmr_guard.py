"""
mmr_guard.py — MMR/IMR guard and deleverage trigger

Monitors margin maintenance ratio.
If MMR exceeds warn/critical thresholds → triggers deleverage actions.
"""

from __future__ import annotations
from .snapshot import compute_imr_mmr


def check_mmr(snapshot: dict, config: dict) -> dict | None:
    """
    Check MMR levels and return an action if threshold exceeded.
    Returns None if all clear.
    Returns action dict if deleverage needed.
    """
    guard = config.get("mmr_guard", {})
    warn_pct = guard.get("warn_pct", 60)
    critical_pct = guard.get("critical_pct", 80)

    imr, mmr = compute_imr_mmr(snapshot)

    if mmr >= critical_pct:
        return {
            "type": "EXECUTE",
            "action": "deleverage_critical",
            "mmr": mmr,
            "imr": imr,
            "reason": f"CRITICAL: MMR={mmr:.1f}% >= {critical_pct}% — auto deleverage highest-risk sleeve",
            "priority": "URGENT",
        }
    elif mmr >= warn_pct:
        return {
            "type": "RECOMMEND",
            "action": "deleverage_warn",
            "mmr": mmr,
            "imr": imr,
            "reason": f"WARNING: MMR={mmr:.1f}% >= {warn_pct}% — stop new risk, consider deleverage",
            "priority": "HIGH",
        }

    return None  # all clear


def deleverage_order(positions: list[dict]) -> list[dict]:
    """
    Sort positions for deleverage order:
    1. Nearest to liquidation (worst liq_distance)
    2. Worst funding rate
    Returns sorted list of positions to reduce first.
    """
    def liq_distance(pos: dict) -> float:
        mark = float(pos.get("markPrice", 0))
        liq = float(pos.get("liqPrice", 0))
        if mark and liq:
            return abs(mark - liq) / mark
        return float("inf")

    return sorted(positions, key=liq_distance)
