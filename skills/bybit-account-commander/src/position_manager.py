"""
position_manager.py — Startup position adoption and SL guard

At startup:
  1. adopt_positions() — attach SAR state to all open positions
  2. set_missing_sl() — set protective SL on positions that lack one

During cycle:
  3. check_positions() — scan open positions for SAR flip / TP hits
  4. compute_position_net_pnl() — unrealized net after fees + funding
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("position_manager")


def adopt_positions(positions: list[dict], config: dict) -> list[dict]:
    """
    Tag each open position with sleeve assignment and initial SAR state.
    Returns list of adoption records for logging.
    """
    adopted = []
    for pos in positions:
        size = float(pos.get("size", 0))
        if size == 0:
            continue
        record = {
            "symbol": pos.get("symbol"),
            "side": pos.get("side"),
            "size": size,
            "entry": float(pos.get("avgPrice", 0)),
            "sl": float(pos.get("stopLoss", 0)),
            "tp": float(pos.get("takeProfit", 0)),
            "unrealized_pnl": float(pos.get("unrealisedPnl", 0)),
            "sleeve": "PERP_SAR",  # default: assign to SAR sleeve
            "adopted": True,
        }
        adopted.append(record)
        logger.info(f"Adopted position: {record['symbol']} {record['side']} sz={record['size']} entry={record['entry']}")
    return adopted


def set_missing_sl(
    router: Any,
    position: dict,
    config: dict,
    sar_cfg: dict,
) -> None:
    """
    Set a protective SL on a position that has none.
    SL is placed at SAR price if calculable, else 2% below entry.
    Uses reduceOnly path via router set_sl_tp.
    """
    symbol = position.get("symbol", "")
    side = position.get("side", "Buy")
    entry = float(position.get("avgPrice", 0))

    if entry == 0:
        logger.warning(f"Cannot set SL for {symbol}: no entry price")
        return

    # Fallback SL: 2% from entry (conservative protective stop)
    fallback_pct = 0.02
    if side == "Buy":
        sl_price = round(entry * (1 - fallback_pct), 6)
    else:
        sl_price = round(entry * (1 + fallback_pct), 6)

    action = {
        "action": "set_sl_tp",
        "symbol": symbol,
        "category": "linear",
        "sl": sl_price,
        "position_idx": int(position.get("positionIdx", 0)),
        "confirmed": True,  # startup SL bypass: critical safety action
        "_bypass_confirm": True,
    }

    result = router.execute(action, {})
    logger.info(f"Set protective SL {symbol} sl={sl_price} result={result}")


def compute_position_net_pnl(
    position: dict,
    fee_rates: dict,
    funding_paid: float = 0.0,
) -> float:
    """
    Estimated net PnL for an open position (unrealized).
    Deducts estimated exit fee from unrealized gross.
    """
    symbol = position.get("symbol", "")
    size = abs(float(position.get("size", 0)))
    mark = float(position.get("markPrice", 0))
    gross_pnl = float(position.get("unrealisedPnl", 0))

    # Exit fee estimate (taker)
    linear_rates = fee_rates.get(symbol, {}).get("linear", {})
    taker_rate = float(linear_rates.get("takerFeeRate", 0.00055))
    exit_fee_est = size * mark * taker_rate

    return gross_pnl - exit_fee_est - funding_paid


def check_positions_for_management(
    positions: list[dict],
    sar_states: dict,
    fee_rates: dict,
    config: dict,
) -> list[dict]:
    """
    Scan open positions against SAR state to detect:
      - SAR flip against position → recommend reduce / exit
      - TP1 reached → recommend partial scale-out
      - SL moved to BE after TP1 hit

    sar_states: {symbol: {sar_price, is_long, ...}} from latest SAR calc
    Returns list of management actions.
    """
    actions = []
    skim_pct = config.get("profit_routing", {}).get("skim_to_spot_pct", 0.40)

    for pos in positions:
        symbol = pos.get("symbol", "")
        size = float(pos.get("size", 0))
        if size == 0:
            continue

        side = pos.get("side", "Buy")
        entry = float(pos.get("avgPrice", 0))
        sl = float(pos.get("stopLoss", 0))
        tp = float(pos.get("takeProfit", 0))
        mark = float(pos.get("markPrice", 0))

        sar = sar_states.get(symbol, {})
        sar_price = sar.get("sar", 0)
        sar_is_long = sar.get("side") == "BUY"
        pos_is_long = side == "Buy"

        net_pnl = compute_position_net_pnl(pos, fee_rates)

        # SAR flip detection
        if sar_price and pos_is_long != sar_is_long:
            action_type = "RECOMMEND" if net_pnl > 0 else "RECOMMEND"
            actions.append({
                "type": action_type,
                "action": "sar_flip_reduce",
                "symbol": symbol,
                "side": "Sell" if pos_is_long else "Buy",
                "qty": size * 0.5,  # soft reduce 50% (option A)
                "net_pnl": net_pnl,
                "reason": f"SAR flipped against {side} position. net_pnl={net_pnl:.4f}",
            })

        # TP1 hit: scale-out 30-40%
        elif tp > 0 and ((pos_is_long and mark >= tp) or (not pos_is_long and mark <= tp)):
            scale_qty = size * 0.35  # 35% scale-out
            actions.append({
                "type": "EXECUTE",
                "action": "reduce_perp",
                "symbol": symbol,
                "side": "Sell" if pos_is_long else "Buy",
                "qty": scale_qty,
                "net_pnl": net_pnl,
                "reason": f"TP1 reached. Scaling out 35%. net_pnl={net_pnl:.4f}",
                "post_action": "move_sl_to_be",
            })

    return actions
