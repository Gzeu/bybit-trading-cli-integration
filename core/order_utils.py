"""
core/order_utils.py — Order type selection, fee-aware sizing, expiry helpers
============================================================================

All trading decisions about HOW to place an order live here:
  - Which order type (Limit / Market)
  - Which timeInForce (PostOnly / GTC / IOC / FOK)
  - Expiry logic (orderLinkId + GoodTillDate via expirySeconds)
  - Fee-aware position sizing (commission deducted from risk budget)

Import from anywhere:
    from core.order_utils import (
        calc_qty_net, calc_qty_balance,
        choose_order_type, order_expiry_args,
        commission_cost, net_min_move,
    )

Bybit V5 linear futures fee schedule (as of 2025):
  Maker (Limit + PostOnly): 0.020%   <- we target this always
  Taker (Market / IOC fill): 0.055%
  Round-trip target:         0.040%  (maker+maker, both sides limit)
  Round-trip worst-case:     0.110%  (market+market)
"""
from __future__ import annotations

import os
import uuid
import time
from typing import Literal

# ---------------------------------------------------------------------------
# Fee constants  (override via .env for VIP tiers)
# ---------------------------------------------------------------------------

FEE_MAKER   = float(os.getenv("FEE_MAKER",  "0.0002"))   # 0.020% Bybit linear maker
FEE_TAKER   = float(os.getenv("FEE_TAKER",  "0.00055"))  # 0.055% Bybit linear taker
FEE_RT_BEST = FEE_MAKER * 2                               # 0.040% round-trip maker+maker
FEE_RT_WORST= FEE_TAKER * 2                               # 0.110% round-trip taker+taker

# Minimum spread (%) below which we attempt PostOnly limit orders
LIMIT_SPREAD_THRESHOLD = float(os.getenv("LIMIT_SPREAD_THRESHOLD", "0.05"))  # 0.05%

# ---------------------------------------------------------------------------
# Fee calculations
# ---------------------------------------------------------------------------

def commission_cost(
    qty: float,
    price: float,
    maker: bool = True,
    sides: int = 2,
) -> float:
    """Return total commission in USDT for a position.

    Args:
        qty:   position size in base asset (e.g. 0.01 BTC)
        price: entry price in USDT
        maker: True = maker fee (limit), False = taker fee (market)
        sides: 1 = entry only, 2 = round-trip (entry + exit)
    """
    rate = FEE_MAKER if maker else FEE_TAKER
    notional = qty * price
    return round(notional * rate * sides, 6)


def net_min_move(
    price: float,
    maker_entry: bool = True,
    maker_exit:  bool = True,
) -> float:
    """Minimum price move (in USDT) to break even after round-trip fees.

    A trade is worth taking only if expected_move > net_min_move().
    """
    fee_entry = FEE_MAKER if maker_entry else FEE_TAKER
    fee_exit  = FEE_MAKER if maker_exit  else FEE_TAKER
    return round(price * (fee_entry + fee_exit), 6)


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def calc_qty_net(
    stop_distance: float,
    balance: float,
    risk_pct: float,
    price: float,
    maker: bool = True,
) -> float:
    """Fixed-fractional sizing with commission deducted from risk budget.

    risk_budget  = balance * risk_pct
    commission   = qty * price * fee_rate * 2   (entry + exit, same type)
    net_budget   = risk_budget - commission  ->  solve for qty:

        qty = (balance * risk_pct) / (stop_distance + price * fee_rt)

    This ensures the actual money at risk (including fees) never exceeds
    balance * risk_pct.
    """
    if stop_distance <= 0 or balance <= 0 or price <= 0:
        return float(os.getenv("QTY", "0.001"))
    fee_rt = (FEE_MAKER if maker else FEE_TAKER) * 2
    qty = (balance * risk_pct) / (stop_distance + price * fee_rt)
    return max(round(qty, 3), 0.001)


def calc_qty_balance(
    price: float,
    balance_free: float,
    alloc_pct: float = 0.95,
    leverage: int = 1,
) -> float:
    """Size based on available free balance (total equity minus margin in use).

    Use when you want to allocate X% of free capital rather than risk a fixed
    % of total balance per trade.

        qty = (balance_free * alloc_pct * leverage) / price

    alloc_pct defaults to 0.95 (95% of free margin) to leave buffer for fees.
    """
    if price <= 0 or balance_free <= 0:
        return 0.001
    qty = (balance_free * alloc_pct * leverage) / price
    return max(round(qty, 3), 0.001)


# ---------------------------------------------------------------------------
# Order type selection
# ---------------------------------------------------------------------------

OrderType = Literal["Limit", "Market"]
TIF       = Literal["PostOnly", "GTC", "IOC", "FOK"]


def choose_order_type(
    spread_pct: float,
    urgency: bool = False,
    strategy_hint: str = "",
) -> tuple[OrderType, TIF]:
    """Decide order type and timeInForce.

    Rules (in priority order):
      1. urgency=True                 → Market  / IOC   (breakout, liquidation)
      2. spread > LIMIT_SPREAD_THRESHOLD → Market / GTC  (spread too wide for limit)
      3. strategy_hint == 'scalping'  → Market  / IOC   (need immediate fill)
      4. strategy_hint == 'mean_reversion' / 'bollinger' / 'vwap' → Limit / PostOnly
      5. default                      → Limit   / PostOnly

    Returns (order_type, time_in_force)
    """
    if urgency:
        return "Market", "IOC"
    if spread_pct > LIMIT_SPREAD_THRESHOLD:
        return "Market", "GTC"
    if strategy_hint in {"scalping", "liquidation_hunt"}:
        return "Market", "IOC"
    # Everything else: try maker limit
    return "Limit", "PostOnly"


# ---------------------------------------------------------------------------
# Expiry / timeInForce helpers
# ---------------------------------------------------------------------------

def order_expiry_args(
    order_type: OrderType,
    time_in_force: TIF,
    expiry_seconds: int | None = None,
) -> list[str]:
    """Build the extra CLI args for timeInForce and optional expiry.

    Bybit supports:
      - PostOnly  : maker-only limit; rejected if would match immediately
      - GTC       : Good Till Cancel (default)
      - IOC       : Immediate Or Cancel  (fill what's available, cancel rest)
      - FOK       : Fill Or Kill         (all or nothing)
      - GoodTillDate: cancel after timestamp (pass via orderFilter + expiryDate)

    For Limit + PostOnly this returns:
        ["--timeInForce", "PostOnly", "--orderLinkId", "<uuid>"]

    For expiry_seconds (e.g. 300 = cancel after 5 min):
        also appends ["--timeInForce", "GoodTillDate", "--orderExpiry", "<ts_ms>"]

    The orderLinkId is a per-order UUID so we can cancel by linkId if needed.
    """
    args: list[str] = []
    link_id = f"bot_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    args += ["--orderLinkId", link_id]

    if expiry_seconds and order_type == "Limit":
        # GoodTillDate — absolute timestamp in milliseconds
        expiry_ms = str(int((time.time() + expiry_seconds) * 1000))
        args += ["--timeInForce", "GoodTillDate", "--orderExpiry", expiry_ms]
    else:
        args += ["--timeInForce", time_in_force]

    return args


# ---------------------------------------------------------------------------
# Convenience: full order param builder
# ---------------------------------------------------------------------------

class OrderParams:
    """Collect all order parameters in one place before passing to engine.enter().

    Usage in a strategy:
        from core.order_utils import OrderParams
        op = OrderParams.build(
            side="Buy", price=price, spread_pct=spread,
            stop_distance=stop_dist, balance=balance, risk_pct=0.01,
            strategy_hint="trend_follow", expiry_seconds=600,
        )
        enter(side=op.side, qty=op.qty, stop_loss=op.sl_price,
              order_type=op.order_type, time_in_force=op.tif,
              expiry_seconds=op.expiry_seconds)
    """
    __slots__ = (
        "side", "qty", "sl_price", "order_type", "tif",
        "expiry_seconds", "commission_usdt", "min_move",
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    @classmethod
    def build(
        cls,
        side: str,
        price: float,
        spread_pct: float,
        stop_distance: float,
        balance: float,
        risk_pct: float,
        strategy_hint: str = "",
        urgency: bool = False,
        expiry_seconds: int | None = None,
        leverage: int = 1,
    ) -> "OrderParams":
        order_type, tif = choose_order_type(spread_pct, urgency, strategy_hint)
        maker = order_type == "Limit"
        qty   = calc_qty_net(stop_distance, balance, risk_pct, price, maker=maker)
        comm  = commission_cost(qty, price, maker=maker, sides=2)
        mmove = net_min_move(price, maker_entry=maker, maker_exit=maker)
        sl_pct= stop_distance / price
        # Reject if stop < break-even (fees eat the whole stop)
        if stop_distance < mmove * 1.5:
            import warnings
            warnings.warn(
                f"stop_distance={stop_distance:.4f} < 1.5x min_move={mmove:.4f} — "
                "trade has negative expected value after fees",
                stacklevel=2,
            )
        return cls(
            side=side, qty=qty, sl_price=price - stop_distance if side=="Buy" else price + stop_distance,
            order_type=order_type, tif=tif,
            expiry_seconds=expiry_seconds,
            commission_usdt=comm, min_move=mmove,
        )
