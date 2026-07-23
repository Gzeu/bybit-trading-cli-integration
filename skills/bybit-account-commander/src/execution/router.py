"""
router.py — Execution router

Routes ACTION_PLAN items to the correct Bybit V5 endpoint:
  - spot buy/sell
  - linear perp open/close/reduce
  - FUND → UNIFIED transfer
  - set leverage
  - set SL / TP (trading-stop)
  - cancel order(s)
  - spot margin toggle (CONFIRM only)

All mainnet writes require config.confirm.mainnet_writes == False
or explicit bypass flag. Never executes withdraw.

Rate limits enforced: GET >= 100ms, POST >= 300ms.
"""

from __future__ import annotations
import logging
import time
from typing import Any

from .entry_policy import decide_entry

logger = logging.getLogger("router")

# Minimum sleep between POST calls (ms → s)
POST_RATE_LIMIT_S = 0.30
GET_RATE_LIMIT_S = 0.10


class ExecutionRouter:
    def __init__(self, client: Any, config: dict):
        self.client = client
        self.config = config
        self.env = config.get("env", "mainnet")
        self.confirm_writes = config.get("confirm", {}).get("mainnet_writes", True)

    # ------------------------------------------------------------------ #
    #  Public dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: dict, snapshot: dict) -> dict:
        """
        Dispatch a single action dict to the correct handler.
        Returns result dict with {success, order_id?, reason}.
        """
        action_type = action.get("action")
        self._guard_mainnet(action)

        dispatch = {
            "open_perp_sar":    self._open_perp_sar,
            "close_perp":       self._close_perp,
            "reduce_perp":      self._reduce_perp,
            "set_sl_tp":        self._set_sl_tp,
            "cancel_order":     self._cancel_order,
            "cancel_all":       self._cancel_all,
            "spot_buy":         self._spot_buy,
            "spot_sell":        self._spot_sell,
            "transfer_to_unified": self._transfer_to_unified,
            "transfer_to_fund": self._transfer_to_fund,
            "set_leverage":     self._set_leverage,
        }

        handler = dispatch.get(action_type)
        if not handler:
            return {"success": False, "reason": f"Unknown action: {action_type}"}

        try:
            return handler(action, snapshot)
        except Exception as e:
            logger.error(f"Router error [{action_type}]: {e}")
            return {"success": False, "reason": str(e)}

    # ------------------------------------------------------------------ #
    #  Perp handlers                                                        #
    # ------------------------------------------------------------------ #

    def _open_perp_sar(self, action: dict, snapshot: dict) -> dict:
        """
        Open a new linear perp position for the SAR sleeve.
        Computes qty from risk_usdt / |entry - sl|.
        Uses entry_policy to decide Market vs Limit.
        """
        symbol = action["symbol"]
        side = action["side"]
        entry = action["entry"]
        sl = action["sl"]
        tp1 = action.get("tp1")
        risk_usdt = action["risk_usdt"]

        # Qty calculation
        dist_sl = abs(entry - sl)
        if dist_sl == 0:
            return {"success": False, "reason": "dist_sl=0, cannot compute qty"}

        # Get instruments info for lot size / minNotional
        inst = self._get_instruments_info(symbol, category="linear")
        qty_step = float(inst.get("lotSizeFilter", {}).get("qtyStep", 0.001))
        min_notional = float(inst.get("lotSizeFilter", {}).get("minNotionalValue", 1.0))

        raw_qty = risk_usdt / dist_sl
        qty = self._snap_to_lot(raw_qty, qty_step)

        notional = qty * entry
        if notional < min_notional:
            return {
                "success": False,
                "reason": f"Notional {notional:.4f} < minNotional {min_notional} for {symbol}",
            }

        # Set leverage first
        leverage = self.config.get("risk", {}).get("max_leverage_linear", 10)
        self._set_leverage({"symbol": symbol, "leverage": leverage,
                             "category": "linear"}, snapshot)

        # Entry policy: Market or Limit
        # NOTE: pass kline data if available; fallback to Market params
        entry_decision = {"order_type": "Limit", "price": entry,
                          "time_in_force": "PostOnly", "is_market": False}

        order_params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": entry_decision["order_type"],
            "qty": str(qty),
            "timeInForce": entry_decision["time_in_force"],
            "reduceOnly": False,
            "stopLoss": str(sl),
            "slTriggerBy": "MarkPrice",
        }

        if entry_decision["order_type"] == "Limit":
            order_params["price"] = str(entry_decision["price"] or entry)

        if tp1:
            order_params["takeProfit"] = str(tp1)
            order_params["tpTriggerBy"] = "MarkPrice"

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.place_order(**order_params)
        order_id = result.get("result", {}).get("orderId", "")

        logger.info(f"OPEN_PERP_SAR {symbol} {side} qty={qty} entry={entry} sl={sl} orderId={order_id}")
        return {"success": bool(order_id), "order_id": order_id,
                "qty": qty, "notional": notional}

    def _close_perp(self, action: dict, snapshot: dict) -> dict:
        """Full close a perp position (reduceOnly market)."""
        symbol = action["symbol"]
        side = action["side"]  # opposite of position side
        qty = action["qty"]

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",
            reduceOnly=True,
        )
        order_id = result.get("result", {}).get("orderId", "")
        logger.info(f"CLOSE_PERP {symbol} {side} qty={qty} orderId={order_id}")
        return {"success": bool(order_id), "order_id": order_id}

    def _reduce_perp(self, action: dict, snapshot: dict) -> dict:
        """Partial reduce a perp position (reduceOnly, PostOnly or Market)."""
        symbol = action["symbol"]
        side = action["side"]
        qty = action["qty"]
        price = action.get("price")  # None = market

        params = dict(
            category="linear",
            symbol=symbol,
            side=side,
            qty=str(qty),
            reduceOnly=True,
        )
        if price:
            params.update(orderType="Limit", price=str(price), timeInForce="PostOnly")
        else:
            params.update(orderType="Market", timeInForce="IOC")

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.place_order(**params)
        order_id = result.get("result", {}).get("orderId", "")
        logger.info(f"REDUCE_PERP {symbol} {side} qty={qty} orderId={order_id}")
        return {"success": bool(order_id), "order_id": order_id}

    def _set_sl_tp(self, action: dict, snapshot: dict) -> dict:
        """Update SL / TP on an open position via trading-stop."""
        params = {
            "category": action.get("category", "linear"),
            "symbol": action["symbol"],
            "positionIdx": action.get("position_idx", 0),
        }
        if action.get("sl"):
            params["stopLoss"] = str(action["sl"])
            params["slTriggerBy"] = "MarkPrice"
        if action.get("tp"):
            params["takeProfit"] = str(action["tp"])
            params["tpTriggerBy"] = "MarkPrice"

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.set_trading_stop(**params)
        ok = result.get("retCode") == 0
        logger.info(f"SET_SL_TP {action['symbol']} sl={action.get('sl')} tp={action.get('tp')} ok={ok}")
        return {"success": ok, "retCode": result.get("retCode"), "retMsg": result.get("retMsg")}

    # ------------------------------------------------------------------ #
    #  Order management                                                     #
    # ------------------------------------------------------------------ #

    def _cancel_order(self, action: dict, snapshot: dict) -> dict:
        """Cancel a specific order by orderId."""
        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.cancel_order(
            category=action.get("category", "linear"),
            symbol=action["symbol"],
            orderId=action["order_id"],
        )
        ok = result.get("retCode") == 0
        logger.info(f"CANCEL_ORDER {action['symbol']} {action['order_id']} ok={ok}")
        return {"success": ok}

    def _cancel_all(self, action: dict, snapshot: dict) -> dict:
        """Cancel all open orders for a symbol or all symbols."""
        symbol = action.get("symbol", "")
        for category in ["linear", "spot"]:
            time.sleep(POST_RATE_LIMIT_S)
            self.client.cancel_all_orders(
                category=category,
                symbol=symbol,
            )
        logger.info(f"CANCEL_ALL symbol={symbol or 'ALL'}")
        return {"success": True}

    # ------------------------------------------------------------------ #
    #  Spot handlers                                                        #
    # ------------------------------------------------------------------ #

    def _spot_buy(self, action: dict, snapshot: dict) -> dict:
        """Place a spot buy (PostOnly limit by default)."""
        symbol = action["symbol"]
        qty = action.get("qty")
        price = action.get("price")
        order_type = "Limit" if price else "Market"
        tif = "PostOnly" if order_type == "Limit" else "IOC"

        params = dict(
            category="spot",
            symbol=symbol,
            side="Buy",
            orderType=order_type,
            qty=str(qty),
            timeInForce=tif,
        )
        if price:
            params["price"] = str(price)

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.place_order(**params)
        order_id = result.get("result", {}).get("orderId", "")
        logger.info(f"SPOT_BUY {symbol} qty={qty} price={price} orderId={order_id}")
        return {"success": bool(order_id), "order_id": order_id}

    def _spot_sell(self, action: dict, snapshot: dict) -> dict:
        """Place a spot sell."""
        symbol = action["symbol"]
        qty = action.get("qty")
        price = action.get("price")
        order_type = "Limit" if price else "Market"
        tif = "PostOnly" if order_type == "Limit" else "IOC"

        params = dict(
            category="spot",
            symbol=symbol,
            side="Sell",
            orderType=order_type,
            qty=str(qty),
            timeInForce=tif,
        )
        if price:
            params["price"] = str(price)

        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.place_order(**params)
        order_id = result.get("result", {}).get("orderId", "")
        logger.info(f"SPOT_SELL {symbol} qty={qty} price={price} orderId={order_id}")
        return {"success": bool(order_id), "order_id": order_id}

    # ------------------------------------------------------------------ #
    #  Transfer handlers                                                    #
    # ------------------------------------------------------------------ #

    def _transfer_to_unified(self, action: dict, snapshot: dict) -> dict:
        """Transfer USDT from FUND to UNIFIED wallet."""
        amount = action["amount_usdt"]
        auto_cap = self.config.get("transfer_auto_cap_usdt", 20)
        if amount > auto_cap and not action.get("confirmed"):
            return {
                "success": False,
                "reason": f"Transfer {amount} USDT > auto_cap {auto_cap}. Requires CONFIRM.",
                "needs_confirm": True,
            }

        import uuid
        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.create_internal_transfer(
            transferId=str(uuid.uuid4()),
            coin="USDT",
            amount=str(amount),
            fromAccountType="FUND",
            toAccountType="UNIFIED",
        )
        ok = result.get("retCode") == 0
        logger.info(f"TRANSFER FUND->UNIFIED {amount} USDT ok={ok}")
        return {"success": ok, "amount": amount}

    def _transfer_to_fund(self, action: dict, snapshot: dict) -> dict:
        """Transfer USDT from UNIFIED to FUND wallet (skim)."""
        amount = action["amount_usdt"]

        import uuid
        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.create_internal_transfer(
            transferId=str(uuid.uuid4()),
            coin="USDT",
            amount=str(amount),
            fromAccountType="UNIFIED",
            toAccountType="FUND",
        )
        ok = result.get("retCode") == 0
        logger.info(f"TRANSFER UNIFIED->FUND {amount} USDT ok={ok}")
        return {"success": ok, "amount": amount}

    # ------------------------------------------------------------------ #
    #  Account settings                                                     #
    # ------------------------------------------------------------------ #

    def _set_leverage(self, action: dict, snapshot: dict) -> dict:
        """Set leverage for a linear symbol."""
        symbol = action["symbol"]
        leverage = str(action.get("leverage",
                       self.config.get("risk", {}).get("max_leverage_linear", 10)))
        time.sleep(POST_RATE_LIMIT_S)
        result = self.client.set_leverage(
            category=action.get("category", "linear"),
            symbol=symbol,
            buyLeverage=leverage,
            sellLeverage=leverage,
        )
        ok = result.get("retCode") in (0, 110043)  # 110043 = already set
        logger.info(f"SET_LEVERAGE {symbol} x{leverage} ok={ok}")
        return {"success": ok}

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _get_instruments_info(self, symbol: str, category: str = "linear") -> dict:
        """Fetch instruments-info for a single symbol."""
        time.sleep(GET_RATE_LIMIT_S)
        result = self.client.get_instruments_info(category=category, symbol=symbol)
        items = result.get("result", {}).get("list", [])
        return items[0] if items else {}

    def _snap_to_lot(self, qty: float, step: float) -> float:
        """Snap qty down to nearest lot step."""
        if step <= 0:
            return round(qty, 6)
        snapped = int(qty / step) * step
        # Round to avoid floating-point drift
        decimals = len(str(step).rstrip('0').split('.')[-1]) if '.' in str(step) else 0
        return round(snapped, decimals)

    def _guard_mainnet(self, action: dict) -> None:
        """Raise if mainnet writes are guarded and action is not pre-confirmed."""
        if self.env == "mainnet" and self.confirm_writes:
            if not action.get("confirmed") and not action.get("_bypass_confirm"):
                raise PermissionError(
                    f"Mainnet write blocked: action '{action.get('action')}' "
                    "needs confirmed=True or config.confirm.mainnet_writes=False"
                )
