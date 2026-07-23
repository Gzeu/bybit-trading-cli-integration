"""
gates.py — Risk gates (pre-trade checklist)

All conditions that must pass before a new trade is allowed.
Returns (passed: bool, reason: str)
"""

from __future__ import annotations


def check_all_gates(setup: dict, snapshot: dict, config: dict,
                    free_risk_budget: float) -> tuple[bool, str]:
    """
    Run all pre-trade gates.
    Returns (True, 'ok') or (False, 'reason for block')
    """
    equity = snapshot.get("total_equity", 0)
    risk_cfg = config.get("risk", {})
    fee_cfg = config.get("fees", {})

    # 1. Minimum equity sanity
    if equity <= 0:
        return False, "equity is zero or negative"

    # 2. Free risk budget
    trade_risk = equity * risk_cfg.get("per_trade_pct", 0.0075)
    if trade_risk > free_risk_budget:
        return False, f"risk budget exhausted: need {trade_risk:.2f}, free {free_risk_budget:.2f}"

    # 3. Edge gate (fee multiple)
    rt_fee = setup.get("rt_fee", 0)
    entry = setup.get("entry", 0)
    tp1 = setup.get("tp1", 0)
    dist_tp1 = abs(tp1 - entry)
    rt_price = entry * rt_fee
    min_multiple = fee_cfg.get("min_edge_multiple_of_rt", 2.5)
    if dist_tp1 < min_multiple * rt_price:
        return False, f"edge < {min_multiple}x RT: dist_tp1={dist_tp1:.4f} RT_price={rt_price:.4f}"

    # 4. R:R minimum
    sl = setup.get("sl", 0)
    dist_sl = abs(entry - sl)
    rr = (dist_tp1 - rt_price) / (dist_sl + rt_price) if dist_sl else 0
    rr_min = risk_cfg.get("rr_min", 1.8)
    if rr < rr_min:
        return False, f"R:R {rr:.2f} < minimum {rr_min}"

    # 5. Daily loss halt
    # TODO: inject daily_pnl from execution log
    # daily_halt_pct = risk_cfg.get('daily_loss_halt_pct', 0.03)
    # if daily_pnl < -equity * daily_halt_pct: return False, 'daily loss halt'

    # 6. Max leverage check
    max_lev = risk_cfg.get("max_leverage_linear", 20)
    if setup.get("leverage", 1) > max_lev:
        return False, f"leverage {setup.get('leverage')} > max {max_lev}"

    # 7. Min notional (instruments-info)
    # TODO: inject instruments_info cache
    # min_notional = instruments_info[symbol].get('lotSizeFilter', {}).get('minNotionalValue', 0)
    # if proposed_notional < min_notional: return False, 'below min notional'

    return True, "ok"
