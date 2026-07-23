"""
commander_loop.py — Main agent loop (fully wired)

Orchestrates every cycle:
  1. Build ACCOUNT_SNAPSHOT
  2. Build PORTFOLIO_MAP (sleeves)
  3. Compute SAR setups for watchlist (primary + filter TF)
  4. Run allocator → ACTION_PLAN
  5. Check all risk gates per EXECUTE action
  6. Route to ExecutionRouter or emit RECOMMEND
  7. Post-exit: profit_skim if net_pnl > 0
  8. Adopt existing positions at startup (set SL if missing)
  9. Generate COMMANDER BRIEF
 10. Log structured JSON to logs/commander.jsonl
"""

from __future__ import annotations
import json
import logging
import logging.handlers
import time
import os
from datetime import datetime, timezone
from typing import Any

from .snapshot import build_snapshot
from .sleeves import PortfolioMap
from .allocator import run_allocator, compute_free_risk_budget
from .sar_trend import grade_setup, compute_sar, compute_ema, compute_adx
from .gates import check_all_gates
from .fees import get_rt_fee, compute_net_pnl
from .mmr_guard import check_mmr
from .brief import generate_brief
from .execution.router import ExecutionRouter
from .execution.profit_skim import compute_skim, should_skim
from .position_manager import adopt_positions, set_missing_sl

logger = logging.getLogger("commander")


def _setup_logging(log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "commander.jsonl"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger("commander")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
        root.addHandler(logging.StreamHandler())  # also print to console


class CommanderLoop:
    def __init__(self, client: Any, config: dict, log_dir: str = "logs"):
        self.client = client
        self.config = config
        self.autonomous = config.get("autonomous", False)
        self.router = ExecutionRouter(client, config)
        self._daily_pnl: float = 0.0
        self._daily_date: str = ""
        self._startup_done: bool = False
        _setup_logging(log_dir)

    # ------------------------------------------------------------------ #
    #  Main cycle                                                           #
    # ------------------------------------------------------------------ #

    def run_once(self) -> dict:
        """Single cycle. Returns {snapshot, plan, brief}."""
        cycle_ts = int(time.time() * 1000)

        # 1. ACCOUNT_SNAPSHOT
        try:
            snapshot = build_snapshot(self.client, self.config)
        except RuntimeError as e:
            logger.error(json.dumps({"event": "snapshot_failed", "reason": str(e), "ts": cycle_ts}))
            return {"type": "HOLD", "reason": str(e)}

        # 2. Daily PnL tracker reset
        self._tick_daily_pnl(snapshot)
        snapshot["daily_pnl"] = self._daily_pnl

        # 3. Daily loss halt check
        equity = snapshot.get("total_equity", 0)
        halt_pct = self.config.get("risk", {}).get("daily_loss_halt_pct", 0.03)
        if equity > 0 and self._daily_pnl < -(equity * halt_pct):
            brief_halt = f"[HALT] Daily loss {self._daily_pnl:.4f} USDT exceeded -{halt_pct*100:.1f}% of equity. No new risk."
            logger.info(json.dumps({"event": "daily_halt", "daily_pnl": self._daily_pnl, "equity": equity}))
            print(brief_halt)
            return {"type": "HALT", "reason": brief_halt, "daily_pnl": self._daily_pnl}

        # 4. Startup: adopt positions, set missing SLs
        if not self._startup_done:
            self._do_startup(snapshot)
            self._startup_done = True

        # 5. Portfolio map
        portfolio = PortfolioMap(self.config, snapshot)

        # 6. SAR setups for watchlist
        sar_setups = self._scan_sar_setups(snapshot)

        # 7. Allocator → ACTION_PLAN
        action_plan = run_allocator(snapshot, self.config, sar_setups)

        # 8. Gate-check all EXECUTE actions
        free_budget = compute_free_risk_budget(snapshot, self.config)
        for action in action_plan:
            if action.get("type") == "EXECUTE":
                passed, reason = check_all_gates(action, snapshot, self.config, free_budget)
                if not passed:
                    action["type"] = "RECOMMEND"
                    action["gate_block"] = reason
                    logger.info(json.dumps({"event": "gate_block", "action": action.get("action"), "reason": reason}))

        # 9. Execute or collect recommendations
        executed, recommended = [], []
        for action in action_plan:
            if action.get("type") == "EXECUTE" and self.autonomous:
                result = self._execute_action(action, snapshot)
                action["result"] = result
                executed.append(action)
                # Post-exit profit skim
                if action.get("action") in ("close_perp", "reduce_perp"):
                    self._maybe_skim(action, snapshot)
            else:
                recommended.append(action)

        # 10. COMMANDER BRIEF
        brief = generate_brief(snapshot, portfolio, action_plan, self.config)
        print(brief)

        # 11. Structured JSON log
        self._log_cycle(snapshot, action_plan, executed, recommended)

        return {"snapshot": snapshot, "plan": action_plan, "brief": brief,
                "executed": executed, "recommended": recommended}

    def run_loop(self, interval_seconds: int = 300) -> None:
        """
        Continuous loop. Runs run_once() every interval_seconds.
        Ctrl+C to stop.
        """
        logger.info(json.dumps({"event": "loop_start", "interval_s": interval_seconds,
                                 "autonomous": self.autonomous,
                                 "env": self.config.get("env", "mainnet")}))
        print(f"[COMMANDER] Loop started. Interval={interval_seconds}s  Autonomous={self.autonomous}")
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                print("\n[COMMANDER] Loop stopped by user.")
                break
            except Exception as e:
                logger.error(json.dumps({"event": "loop_error", "error": str(e)}))
                print(f"[COMMANDER] Cycle error: {e} — holding, retry in {interval_seconds}s")
            time.sleep(interval_seconds)

    # ------------------------------------------------------------------ #
    #  Startup: adopt + SL guard                                           #
    # ------------------------------------------------------------------ #

    def _do_startup(self, snapshot: dict) -> None:
        """Adopt existing positions; set SL on any position that lacks one."""
        positions = snapshot.get("positions_linear", [])
        missing_sl = [p for p in positions
                      if float(p.get("stopLoss", 0)) == 0 and float(p.get("size", 0)) != 0]

        if missing_sl:
            logger.info(json.dumps({"event": "startup_missing_sl",
                                     "count": len(missing_sl),
                                     "symbols": [p["symbol"] for p in missing_sl]}))
            print(f"[STARTUP] {len(missing_sl)} position(s) missing SL — setting protective SL...")
            sar_cfg = self.config.get("sar", {})
            for pos in missing_sl:
                try:
                    set_missing_sl(self.router, pos, self.config, sar_cfg)
                except Exception as e:
                    logger.warning(json.dumps({"event": "set_sl_failed",
                                               "symbol": pos.get("symbol"), "error": str(e)}))

        adopted = adopt_positions(positions, self.config)
        logger.info(json.dumps({"event": "startup_adopt", "positions": adopted}))
        print(f"[STARTUP] Adopted {len(positions)} position(s). SAR tracking active.")

    # ------------------------------------------------------------------ #
    #  SAR scanner                                                          #
    # ------------------------------------------------------------------ #

    def _scan_sar_setups(self, snapshot: dict) -> list[dict]:
        """Scan all watchlist symbols for SAR setups. Returns graded setup list."""
        setups = []
        for symbol in self.config.get("watchlist", ["BTCUSDT"]):
            try:
                setup = self._get_sar_setup(snapshot, symbol)
                if setup:
                    setups.append(setup)
                    logger.info(json.dumps({"event": "sar_setup", **setup}))
            except Exception as e:
                logger.warning(json.dumps({"event": "sar_scan_failed",
                                           "symbol": symbol, "error": str(e)}))
        # Sort by grade then RR descending
        grade_order = {"A+": 0, "A": 1, "B": 2}
        setups.sort(key=lambda s: (grade_order.get(s.get("grade", "B"), 2),
                                   -s.get("rr", 0)))
        return setups

    def _get_sar_setup(self, snapshot: dict, symbol: str) -> dict | None:
        """Fetch klines (primary + filter TF) and compute SAR setup."""
        sar_cfg = self.config.get("sar", {})
        tf_primary = sar_cfg.get("tf_primary", "5")
        tf_filter = sar_cfg.get("tf_filter", "60")

        def fetch_bars(tf: str, limit: int = 200) -> tuple:
            klines = self.client.get_kline(
                category="linear", symbol=symbol, interval=tf, limit=limit
            )
            bars = list(reversed(klines.get("result", {}).get("list", [])))
            c = [float(b[4]) for b in bars]
            h = [float(b[2]) for b in bars]
            lo = [float(b[3]) for b in bars]
            v = [float(b[5]) for b in bars]
            return h, lo, c, v

        # Primary TF
        highs, lows, closes, volumes = fetch_bars(tf_primary)
        if len(closes) < 55:
            return None

        # Filter TF: check SAR direction agrees
        h_f, l_f, c_f, _ = fetch_bars(tf_filter, limit=60)
        sar_filter = compute_sar(
            h_f, l_f,
            af_start=sar_cfg.get("af_start", 0.02),
            af_step=sar_cfg.get("af_step", 0.02),
            af_max=sar_cfg.get("af_max", 0.20),
        )
        filter_is_long = c_f[-1] > sar_filter[-1] if sar_filter else None

        # Primary indicators
        sar_vals = compute_sar(
            highs, lows,
            af_start=sar_cfg.get("af_start", 0.02),
            af_step=sar_cfg.get("af_step", 0.02),
            af_max=sar_cfg.get("af_max", 0.20),
        )
        ema50 = compute_ema(closes, 50)
        adx_vals = compute_adx(highs, lows, closes, 14)

        rt = get_rt_fee(
            snapshot.get("fee_rates", {}), symbol,
            category="linear",
            use_maker=self.config.get("fees", {}).get("prefer_postonly", True),
        )

        setup = grade_setup(sar_vals, ema50, adx_vals, closes, symbol, self.config, rt)
        if setup is None:
            return None

        # MTF filter: primary side must match filter TF SAR side
        if filter_is_long is not None:
            primary_is_long = setup["side"] == "BUY"
            if primary_is_long != filter_is_long:
                logger.info(json.dumps({"event": "mtf_filter_reject",
                                        "symbol": symbol,
                                        "primary_side": setup["side"],
                                        "filter_long": filter_is_long}))
                return None

        # Attach volume data for entry_policy
        setup["volumes"] = volumes
        setup["highs"] = highs
        setup["lows"] = lows
        setup["closes"] = closes
        return setup

    # ------------------------------------------------------------------ #
    #  Execution                                                            #
    # ------------------------------------------------------------------ #

    def _execute_action(self, action: dict, snapshot: dict) -> dict:
        """Route action to ExecutionRouter. Returns result dict."""
        env = self.config.get("env", "mainnet")
        logger.info(json.dumps({"event": "execute", "env": env,
                                 "action": action.get("action"),
                                 "symbol": action.get("symbol"),
                                 "type": action.get("type")}))
        try:
            result = self.router.execute(action, snapshot)
            logger.info(json.dumps({"event": "execute_result", "result": result}))
            return result
        except PermissionError as e:
            # Mainnet write blocked — downgrade to RECOMMEND
            action["type"] = "RECOMMEND"
            action["gate_block"] = str(e)
            logger.warning(json.dumps({"event": "mainnet_guard", "reason": str(e)}))
            return {"success": False, "reason": str(e), "needs_confirm": True}
        except Exception as e:
            logger.error(json.dumps({"event": "execute_error", "error": str(e)}))
            # API failure — HOLD, never blind-close
            return {"success": False, "reason": str(e), "hold": True}

    def _maybe_skim(self, action: dict, snapshot: dict) -> None:
        """After a perp exit, compute skim and execute spot buy if conditions met."""
        result = action.get("result", {})
        if not result.get("success"):
            return

        net_pnl = action.get("net_pnl", 0.0)
        if not should_skim(net_pnl, self.config):
            return

        skim_action = compute_skim(net_pnl, self.config, snapshot)
        if skim_action is None:
            return

        logger.info(json.dumps({"event": "profit_skim", "net_pnl": net_pnl,
                                 "skim_action": skim_action}))
        if self.autonomous:
            skim_result = self.router.execute(skim_action, snapshot)
            logger.info(json.dumps({"event": "skim_result", "result": skim_result}))

    # ------------------------------------------------------------------ #
    #  Daily PnL tracking                                                   #
    # ------------------------------------------------------------------ #

    def _tick_daily_pnl(self, snapshot: dict) -> None:
        """Reset daily PnL counter at UTC midnight."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_date:
            self._daily_pnl = 0.0
            self._daily_date = today
            logger.info(json.dumps({"event": "daily_reset", "date": today}))

    def update_daily_pnl(self, pnl_delta: float) -> None:
        """Call after each realized trade to update daily PnL accumulator."""
        self._daily_pnl += pnl_delta
        logger.info(json.dumps({"event": "daily_pnl_update",
                                 "delta": pnl_delta, "total": self._daily_pnl}))

    # ------------------------------------------------------------------ #
    #  Structured logging                                                   #
    # ------------------------------------------------------------------ #

    def _log_cycle(self, snapshot: dict, plan: list,
                   executed: list, recommended: list) -> None:
        entry = {
            "event": "cycle",
            "ts": snapshot.get("ts"),
            "env": snapshot.get("env"),
            "equity": snapshot.get("total_equity"),
            "available": snapshot.get("available_balance"),
            "daily_pnl": self._daily_pnl,
            "positions_count": len(snapshot.get("positions_linear", [])),
            "executed_count": len(executed),
            "recommended_count": len(recommended),
            "plan_summary": [{"type": a.get("type"), "action": a.get("action"),
                               "symbol": a.get("symbol", "")} for a in plan],
        }
        logger.info(json.dumps(entry))
