"""
profit_skim.py — Profit routing: perp winners → SPOT_CORE

After a PERP_SAR exit with net_pnl > 0:
  1. Compute skim amount = net_profit * skim_to_spot_pct
  2. Place spot buy (BTC or ETH) at PostOnly limit
  3. Log cost basis
  4. Remainder stays in UNIFIED for perp book compound

Never skims on a net-negative exit.
Never triggers on every red candle (spot core = slow money).
"""

from __future__ import annotations
import logging

logger = logging.getLogger("profit_skim")


def should_skim(net_pnl: float, config: dict) -> bool:
    """Return True only if net_pnl positive and above min threshold."""
    if net_pnl <= 0:
        return False
    min_net = config.get("profit_routing", {}).get("trigger_min_net_usdt", 0.5)
    return net_pnl >= min_net


def compute_skim(
    net_pnl: float,
    config: dict,
    snapshot: dict,
) -> dict | None:
    """
    Compute skim action if conditions met.
    Returns action dict for router or None.
    """
    if not should_skim(net_pnl, config):
        return None

    pr = config.get("profit_routing", {})
    skim_pct = pr.get("skim_to_spot_pct", 0.40)
    spot_symbols = pr.get("spot_symbols", ["BTCUSDT"])

    skim_usdt = net_pnl * skim_pct
    symbol = spot_symbols[0]  # prefer first (BTC)

    # Get mark price for qty estimate
    tickers = snapshot.get("tickers", {})
    mark = float(tickers.get(symbol, {}).get("lastPrice", 0))

    if mark <= 0:
        logger.warning(f"Cannot skim: no mark price for {symbol}")
        return None

    qty_raw = skim_usdt / mark

    logger.info(
        f"SKIM: net_pnl={net_pnl:.4f} skim_pct={skim_pct} "
        f"skim_usdt={skim_usdt:.4f} symbol={symbol} qty_approx={qty_raw:.8f}"
    )

    return {
        "type": "EXECUTE",
        "action": "spot_buy",
        "symbol": symbol,
        "qty": qty_raw,
        "price": None,  # router will use PostOnly limit via entry_policy
        "reason": f"Profit skim {skim_pct*100:.0f}% of net_pnl={net_pnl:.4f} USDT",
        "cost_basis_usdt": skim_usdt,
        "confirmed": False,  # still needs confirm gate in router
    }
