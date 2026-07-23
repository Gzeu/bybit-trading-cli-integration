"""
fees.py — Fee model and round-trip cost calculator

All fee logic is centralized here.
Never hardcode rates — always use live rates from snapshot.
"""

from __future__ import annotations


def get_rt_fee(fee_rates: dict, symbol: str, category: str = "linear",
               use_maker: bool = True) -> float:
    """
    Round-trip fee as fraction of notional.
    RT = entry_fee_rate + exit_fee_rate
    """
    rates = fee_rates.get(symbol, {}).get(category, {})
    if use_maker:
        entry_rate = float(rates.get("makerFeeRate", 0.0002))
        exit_rate = float(rates.get("makerFeeRate", 0.0002))
    else:
        entry_rate = float(rates.get("takerFeeRate", 0.00055))
        exit_rate = float(rates.get("takerFeeRate", 0.00055))
    return entry_rate + exit_rate


def compute_net_pnl(gross_pnl: float, entry_notional: float, exit_notional: float,
                    entry_fee_rate: float, exit_fee_rate: float,
                    funding_paid: float = 0.0,
                    borrow_interest: float = 0.0) -> float:
    """Net PnL after all costs."""
    entry_fee = entry_notional * entry_fee_rate
    exit_fee = exit_notional * exit_fee_rate
    return gross_pnl - entry_fee - exit_fee - funding_paid - borrow_interest


def compute_breakeven_price(side: str, entry_price: float,
                            rt_fee_rate: float,
                            funding_est: float = 0.0) -> float:
    """
    Break-even price: entry + all costs.
    side: 'BUY' or 'SELL'
    """
    cost_fraction = rt_fee_rate + funding_est
    if side == "BUY":
        return entry_price * (1 + cost_fraction)
    else:
        return entry_price * (1 - cost_fraction)


def check_edge_gate(dist_to_tp1: float, rt_fee_price: float,
                    min_multiple: float = 2.5) -> bool:
    """
    Returns True if the setup has enough edge.
    dist_to_tp1: price distance to TP1
    rt_fee_price: round-trip cost in price units (entry * RT_rate)
    min_multiple: from config fees.min_edge_multiple_of_rt
    """
    return dist_to_tp1 >= min_multiple * rt_fee_price


def log_decision(action: str, symbol: str, entry: float, size: float,
                 entry_fee: float, exit_fee_est: float,
                 funding_est: float, borrow: float, net_pnl_est: float) -> dict:
    """Structured decision log entry."""
    return {
        "action": action,
        "symbol": symbol,
        "entry": entry,
        "size": size,
        "entry_fee": round(entry_fee, 6),
        "exit_fee_est": round(exit_fee_est, 6),
        "funding_est": round(funding_est, 6),
        "borrow": round(borrow, 6),
        "net_pnl_est": round(net_pnl_est, 6),
    }
