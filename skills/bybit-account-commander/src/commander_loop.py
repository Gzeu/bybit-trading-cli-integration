"""
commander_loop.py — Main agent loop

Orchestrates every cycle:
  1. Build ACCOUNT_SNAPSHOT
  2. Build PORTFOLIO_MAP (sleeves)
  3. Compute SAR setups for watchlist
  4. Run allocator → ACTION_PLAN
  5. Check all risk gates per action
  6. Route to execution or recommendation
  7. Generate COMMANDER BRIEF
  8. Log structured JSON

Usage:
    from commander_loop import CommanderLoop
    loop = CommanderLoop(client, config)
    loop.run_once()
"""

from __future__ import annotations
import json
import logging
import time
from typing import Any

from .snapshot import build_snapshot
from .sleeves import PortfolioMap
from .allocator import run_allocator
from .sar_trend import grade_setup, compute_sar, compute_ema, compute_adx
from .gates import check_all_gates
from .fees import get_rt_fee
from .mmr_guard import check_mmr
from .brief import generate_brief

logger = logging.getLogger("commander")


class CommanderLoop:
    def __init__(self, client: Any, config: dict):
        self.client = client
        self.config = config
        self.autonomous = config.get("autonomous", False)

    def run_once(self) -> dict:
        """
        Single cycle of the commander loop.
        Returns the ACTION_PLAN and BRIEF.
        """
        # 1. Snapshot
        try:
            snapshot = build_snapshot(self.client, self.config)
        except RuntimeError as e:
            logger.error(f"Snapshot failed: {e}")
            return {"type": "HOLD", "reason": str(e)}

        # 2. Portfolio map
        portfolio = PortfolioMap(self.config, snapshot)

        # 3. SAR setups for watchlist
        sar_setups = []
        for symbol in self.config.get("watchlist", ["BTCUSDT"]):
            try:
                setup = self._get_sar_setup(snapshot, symbol)
                if setup:
                    sar_setups.append(setup)
            except Exception as e:
                logger.warning(f"SAR setup failed for {symbol}: {e}")

        # 4. Allocator
        action_plan = run_allocator(snapshot, self.config, sar_setups)

        # 5. Gate-check EXECUTE actions
        from .allocator import compute_free_risk_budget
        free_budget = compute_free_risk_budget(snapshot, self.config)
        for action in action_plan:
            if action.get("type") == "EXECUTE" and action.get("action") == "open_perp_sar":
                passed, reason = check_all_gates(action, snapshot, self.config, free_budget)
                if not passed:
                    action["type"] = "RECOMMEND"
                    action["gate_block"] = reason

        # 6. Execute or recommend
        for action in action_plan:
            if action.get("type") == "EXECUTE" and self.autonomous:
                self._execute_action(action, snapshot)

        # 7. COMMANDER BRIEF
        brief = generate_brief(snapshot, portfolio, action_plan, self.config)
        print(brief)

        # 8. Structured log
        log_entry = {
            "ts": snapshot.get("ts"),
            "equity": snapshot.get("total_equity"),
            "action_plan": action_plan,
        }
        logger.info(json.dumps(log_entry))

        return {"snapshot": snapshot, "plan": action_plan, "brief": brief}

    def _get_sar_setup(self, snapshot: dict, symbol: str) -> dict | None:
        """Fetch klines and compute SAR setup for symbol."""
        sar_cfg = self.config.get("sar", {})
        tf = sar_cfg.get("tf_primary", "5")

        klines = self.client.get_kline(
            category="linear", symbol=symbol, interval=tf, limit=200
        )
        bars = klines.get("result", {}).get("list", [])
        if len(bars) < 50:
            return None

        # Bybit returns newest first — reverse
        bars = list(reversed(bars))
        closes = [float(b[4]) for b in bars]
        highs = [float(b[2]) for b in bars]
        lows = [float(b[3]) for b in bars]

        sar_vals = compute_sar(
            highs, lows,
            af_start=sar_cfg.get("af_start", 0.02),
            af_step=sar_cfg.get("af_step", 0.02),
            af_max=sar_cfg.get("af_max", 0.20),
        )
        ema50 = compute_ema(closes, 50)
        adx_vals = compute_adx(highs, lows, closes, 14)

        # RT fee
        rt = get_rt_fee(
            snapshot.get("fee_rates", {}),
            symbol,
            category="linear",
            use_maker=self.config.get("fees", {}).get("prefer_postonly", True),
        )

        return grade_setup(sar_vals, ema50, adx_vals, closes, symbol, self.config, rt)

    def _execute_action(self, action: dict, snapshot: dict) -> None:
        """
        Route to execution adapter.
        TODO: implement via router.py
        """
        logger.info(f"EXECUTE: {action}")
        # from .router import execute_order
        # execute_order(self.client, action, snapshot, self.config)
        raise NotImplementedError("Execution router not yet wired — implement router.py")
