"""
brief.py — COMMANDER BRIEF generator

Produces the human-readable account summary printed every turn.
Format from SKILL.md §11.
"""

from __future__ import annotations
from .snapshot import compute_imr_mmr


def generate_brief(snapshot: dict, portfolio_map: object,
                   action_plan: list[dict], config: dict) -> str:
    """
    Generate COMMANDER BRIEF string.
    """
    env = snapshot.get("env", "mainnet").upper()
    margin_mode = snapshot.get("margin_mode", "UNKNOWN")
    uta_status = snapshot.get("unified_margin_status", "?")
    equity = snapshot.get("total_equity", 0.0)
    available = snapshot.get("available_balance", 0.0)
    fund_usdt = snapshot.get("fund_usdt", 0.0)
    imr, mmr = compute_imr_mmr(snapshot)

    risk_cfg = config.get("risk", {})
    max_open_risk_pct = risk_cfg.get("max_open_risk_pct", 0.025)
    reserve_floor = equity * config.get("sleeves", {}).get("reserve_pct", 0.30)

    # Fee rates for BTC
    btc_fees = snapshot.get("fee_rates", {}).get("BTCUSDT", {})
    linear_fees = btc_fees.get("linear", {})
    spot_fees = btc_fees.get("spot", {})
    l_maker = linear_fees.get("makerFeeRate", "?")
    l_taker = linear_fees.get("takerFeeRate", "?")
    s_maker = spot_fees.get("makerFeeRate", "?")
    s_taker = spot_fees.get("takerFeeRate", "?")
    try:
        rt_btc = float(l_maker) + float(l_maker)
    except (TypeError, ValueError):
        rt_btc = "?"

    # Spot margin
    sm_mode = "ON" if snapshot.get("spot_margin_mode") == "1" else "OFF"
    sm_lev = snapshot.get("spot_leverage", "1")

    # Determine action type
    action_types = [p.get("type", "HOLD") for p in action_plan]
    if "EXECUTE" in action_types:
        action_type = "EXECUTE"
    elif "RECOMMEND" in action_types:
        action_type = "RECOMMEND"
    else:
        action_type = "HOLD"

    lines = [
        f"{'='*60}",
        f"[{env}] ACCOUNT COMMANDER | mode=UTA_{uta_status} margin={margin_mode}",
        f"Equity={equity:.4f} USDT | Avail={available:.4f} | FUND={fund_usdt:.4f} | Reserve floor={reserve_floor:.4f}",
        f"MMR={mmr:.1f}% IMR={imr:.1f}% | Risk used=?/{max_open_risk_pct*100:.1f}%",
        f"Fees: spot m/t={s_maker}/{s_taker}  linear m/t={l_maker}/{l_taker} | RT_btc={rt_btc}",
        "Sleeves:",
    ]

    if hasattr(portfolio_map, "all_sleeves"):
        for s in portfolio_map.all_sleeves():
            lines.append(
                f"  {s.name:<14} {s.target_pct*100:.0f}%  target={s.target_usdt:.2f} USDT"
            )

    lines += [
        f"Spot margin: {sm_mode}  leverage={sm_lev}",
        f"Action type: {action_type}",
        "Plan:",
    ]

    for item in action_plan:
        lines.append(f"  - [{item.get('type','?')}] {item.get('action','?')}: {item.get('reason','')}")
        if item.get("need_usdt"):
            lines.append(f"    NEED: {item['need_usdt']:.2f} USDT")

    lines.append(f"{'='*60}")
    return "\n".join(lines)
