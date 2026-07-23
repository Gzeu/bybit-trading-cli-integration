"""
allocator.py — Capital sleeve allocator

Decides every cycle:
  - Is deleverage needed? (MMR / reserve breach)
  - Is there a valid PERP_SAR setup within risk budget?
  - Should idle USDT go to spot core or flexible earn?
  - Should perp profits be skimmed to spot?

Returns an ACTION_PLAN: list of {action, reason, size_usdt, symbol, ...}
"""

from __future__ import annotations
from typing import Any


def compute_sleeve_targets(snapshot: dict, config: dict) -> dict:
    """Compute target USDT amounts per sleeve from equity + config percentages."""
    equity = snapshot.get("total_equity", 0)
    sl = config.get("sleeves", {})
    return {
        "RESERVE":      equity * sl.get("reserve_pct", 0.30),
        "SPOT_CORE":    equity * sl.get("spot_core_pct", 0.30),
        "PERP_SAR":     equity * sl.get("perp_sar_pct", 0.25),
        "SPOT_MARGIN":  equity * sl.get("spot_margin_pct", 0.00),
        "EARN_FLEX":    equity * sl.get("earn_flex_pct", 0.15),
    }


def compute_free_risk_budget(snapshot: dict, config: dict) -> float:
    """
    free_risk_budget = max_total_risk% * equity - current_open_risk
    open_risk = sum of |entry - sl| * qty for all open positions
    """
    equity = snapshot.get("total_equity", 0)
    max_risk_pct = config.get("risk", {}).get("max_open_risk_pct", 0.025)
    max_risk_usdt = equity * max_risk_pct

    open_risk = 0.0
    for pos in snapshot.get("positions_linear", []):
        entry = float(pos.get("avgPrice", 0))
        sl_price = float(pos.get("stopLoss", 0))
        qty = abs(float(pos.get("size", 0)))
        if entry and sl_price and qty:
            open_risk += abs(entry - sl_price) * qty

    return max(0.0, max_risk_usdt - open_risk)


def run_allocator(snapshot: dict, config: dict, sar_setups: list[dict]) -> list[dict]:
    """
    Main allocator — returns ACTION_PLAN list.
    Each item: {type: EXECUTE|RECOMMEND|HOLD, action: str, reason: str, ...}
    """
    plan: list[dict] = []
    equity = snapshot.get("total_equity", 0)
    available = snapshot.get("available_balance", 0)
    risk_cfg = config.get("risk", {})

    # --- MMR guard check ---
    from .mmr_guard import check_mmr
    mmr_action = check_mmr(snapshot, config)
    if mmr_action:
        plan.append(mmr_action)
        return plan  # deleverage takes priority

    # --- Reserve floor check ---
    reserve_target = equity * config["sleeves"].get("reserve_pct", 0.30)
    if available < reserve_target * 0.8:  # 20% below reserve floor → warning
        plan.append({
            "type": "RECOMMEND",
            "action": "reserve_topup",
            "reason": f"Available {available:.2f} below reserve floor {reserve_target:.2f}",
            "need_usdt": reserve_target - available,
        })

    # --- Daily loss halt check ---
    # TODO: load daily PnL from execution log
    # if daily_net_pnl < -equity * daily_loss_halt_pct: return HOLD_ALL

    # --- PERP_SAR opportunity ---
    free_budget = compute_free_risk_budget(snapshot, config)
    for setup in sar_setups:
        if setup.get("grade") == "A+" and free_budget > 0:
            trade_risk = equity * risk_cfg.get("per_trade_pct", 0.0075)
            if trade_risk <= free_budget:
                plan.append({
                    "type": "EXECUTE" if config.get("autonomous") else "RECOMMEND",
                    "action": "open_perp_sar",
                    "symbol": setup["symbol"],
                    "side": setup["side"],
                    "risk_usdt": trade_risk,
                    "entry": setup["entry"],
                    "sl": setup["sl"],
                    "tp1": setup["tp1"],
                    "reason": f"SAR {setup['side']} A+ setup, RR={setup.get('rr', 0):.2f}",
                })
                break  # one trade per cycle

    # --- Idle USDT routing ---
    idle = available - reserve_target
    earn_threshold = config.get("earn", {}).get("min_idle_usdt_to_earn", 20)
    if idle > earn_threshold and not sar_setups:
        plan.append({
            "type": "RECOMMEND",
            "action": "idle_earn_or_spot",
            "idle_usdt": idle,
            "reason": "No SAR setup; idle USDT above threshold",
        })

    if not plan:
        plan.append({"type": "HOLD", "action": "no_action", "reason": "No qualifying setup or action"})

    return plan
