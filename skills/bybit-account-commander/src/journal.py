"""
journal.py — Trade journal: log every filled order with P&L

Writes to logs/trade_journal.csv:
  timestamp, symbol, side, qty, entry, exit, gross_pnl, fee_usdt,
  net_pnl, hold_minutes, grade, sleeve, notes

Also computes running stats:
  win_rate, avg_rr, expectancy, total_net_pnl
"""

from __future__ import annotations
import csv
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, fields
from typing import Optional

logger = logging.getLogger("journal")


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    side: str          # BUY | SELL
    qty: float
    entry: float
    exit_price: float
    gross_pnl: float
    fee_usdt: float
    net_pnl: float
    hold_minutes: float
    grade: str         # A+ | A | B | unknown
    sleeve: str        # PERP_SAR | SPOT_CORE | etc
    order_id: str
    notes: str = ""


COLUMNS = [f.name for f in fields(TradeRecord)]


class TradeJournal:
    def __init__(self, log_dir: str = "logs"):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, "trade_journal.csv")
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writeheader()

    def record(self, trade: TradeRecord) -> None:
        with open(self.path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writerow(asdict(trade))
        logger.info(f"Journal: {trade.symbol} {trade.side} net_pnl={trade.net_pnl:.4f} grade={trade.grade}")

    def record_from_execution(
        self,
        action: dict,
        result: dict,
        entry_price: float,
        exit_price: float,
        gross_pnl: float,
        fee_usdt: float,
        hold_minutes: float = 0.0,
    ) -> Optional[TradeRecord]:
        if not result.get("success"):
            return None

        net_pnl = gross_pnl - fee_usdt
        trade = TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=action.get("symbol", ""),
            side=action.get("side", ""),
            qty=action.get("qty", 0),
            entry=entry_price,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            fee_usdt=fee_usdt,
            net_pnl=net_pnl,
            hold_minutes=hold_minutes,
            grade=action.get("grade", "unknown"),
            sleeve=action.get("sleeve", "PERP_SAR"),
            order_id=result.get("order_id", ""),
            notes=action.get("reason", ""),
        )
        self.record(trade)
        return trade

    # ---- Stats --------------------------------------------------------

    def stats(self) -> dict:
        """Compute running stats from journal CSV."""
        trades = self._load_all()
        if not trades:
            return {"total": 0}

        net_pnls = [t["net_pnl"] for t in trades]
        wins = [p for p in net_pnls if p > 0]
        losses = [p for p in net_pnls if p <= 0]

        win_rate = len(wins) / len(net_pnls) if net_pnls else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        by_grade = {}
        for t in trades:
            g = t["grade"]
            by_grade.setdefault(g, {"count": 0, "net_pnl": 0.0})
            by_grade[g]["count"] += 1
            by_grade[g]["net_pnl"] += t["net_pnl"]

        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "expectancy": round(expectancy, 4),
            "total_net_pnl": round(sum(net_pnls), 4),
            "by_grade": by_grade,
        }

    def _load_all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                try:
                    row["net_pnl"] = float(row["net_pnl"])
                    row["gross_pnl"] = float(row["gross_pnl"])
                    rows.append(row)
                except (ValueError, KeyError):
                    pass
            return rows
