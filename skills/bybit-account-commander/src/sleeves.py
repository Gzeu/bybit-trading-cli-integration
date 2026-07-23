"""
sleeves.py — Sleeve state tracker

Maintains live state of each capital sleeve:
  RESERVE / SPOT_CORE / PERP_SAR / SPOT_MARGIN / EARN_FLEX / HEDGE

Updated every cycle from snapshot + execution log.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SleeveState:
    name: str
    target_pct: float = 0.0
    current_usdt: float = 0.0
    target_usdt: float = 0.0
    assets: list[dict] = field(default_factory=list)  # for SPOT_CORE
    positions: list[dict] = field(default_factory=list)  # for PERP_SAR
    debt_usdt: float = 0.0  # for SPOT_MARGIN
    leverage: float = 1.0  # for SPOT_MARGIN
    earn_usdt: float = 0.0  # for EARN_FLEX

    @property
    def delta_usdt(self) -> float:
        """Positive = needs funding; negative = excess."""
        return self.target_usdt - self.current_usdt


class PortfolioMap:
    """Container for all sleeves."""

    def __init__(self, config: dict, snapshot: dict):
        equity = snapshot.get("total_equity", 0)
        sl = config.get("sleeves", {})

        self.reserve = SleeveState(
            name="RESERVE",
            target_pct=sl.get("reserve_pct", 0.30),
            target_usdt=equity * sl.get("reserve_pct", 0.30),
        )
        self.spot_core = SleeveState(
            name="SPOT_CORE",
            target_pct=sl.get("spot_core_pct", 0.30),
            target_usdt=equity * sl.get("spot_core_pct", 0.30),
        )
        self.perp_sar = SleeveState(
            name="PERP_SAR",
            target_pct=sl.get("perp_sar_pct", 0.25),
            target_usdt=equity * sl.get("perp_sar_pct", 0.25),
            positions=snapshot.get("positions_linear", []),
        )
        self.spot_margin = SleeveState(
            name="SPOT_MARGIN",
            target_pct=sl.get("spot_margin_pct", 0.00),
            target_usdt=equity * sl.get("spot_margin_pct", 0.00),
        )
        self.earn_flex = SleeveState(
            name="EARN_FLEX",
            target_pct=sl.get("earn_flex_pct", 0.15),
            target_usdt=equity * sl.get("earn_flex_pct", 0.15),
        )

    def all_sleeves(self) -> list[SleeveState]:
        return [self.reserve, self.spot_core, self.perp_sar,
                self.spot_margin, self.earn_flex]

    def summary(self) -> str:
        lines = []
        for s in self.all_sleeves():
            lines.append(
                f"  {s.name:<14} target={s.target_pct*100:.0f}%"
                f"  target_usdt={s.target_usdt:.2f}"
                f"  current_usdt={s.current_usdt:.2f}"
                f"  delta={s.delta_usdt:+.2f}"
            )
        return "\n".join(lines)
