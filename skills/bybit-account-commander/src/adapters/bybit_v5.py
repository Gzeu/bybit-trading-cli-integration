"""
bybit_v5.py — Bybit V5 API adapter

Thin wrapper around pybit.unified_trading.HTTP.
Exposes a consistent interface used by snapshot.py, router.py etc.

Usage:
    from adapters.bybit_v5 import BybitV5Client
    client = BybitV5Client(api_key=..., api_secret=..., testnet=False)

All methods return raw Bybit response dicts.
Rate-limit sleeps are handled in router.py, not here.
"""

from __future__ import annotations
from typing import Any

try:
    from pybit.unified_trading import HTTP
except ImportError:
    HTTP = None  # type: ignore


class BybitV5Client:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        if HTTP is None:
            raise ImportError("pybit not installed. Run: pip install pybit")
        self._session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )

    # ---- Market --------------------------------------------------------
    def get_server_time(self) -> dict:
        return self._session.get_server_time()

    def get_kline(self, category: str, symbol: str,
                  interval: str, limit: int = 200) -> dict:
        return self._session.get_kline(
            category=category, symbol=symbol, interval=interval, limit=limit
        )

    def get_orderbook(self, category: str, symbol: str, limit: int = 25) -> dict:
        return self._session.get_orderbook(
            category=category, symbol=symbol, limit=limit
        )

    def get_tickers(self, category: str, symbol: str = "") -> dict:
        return self._session.get_tickers(category=category, symbol=symbol)

    def get_instruments_info(self, category: str, symbol: str = "") -> dict:
        return self._session.get_instruments_info(
            category=category, symbol=symbol
        )

    # ---- Account -------------------------------------------------------
    def get_account_info(self) -> dict:
        return self._session.get_account_info()

    def get_wallet_balance(self, accountType: str = "UNIFIED") -> dict:
        return self._session.get_wallet_balance(accountType=accountType)

    def get_fee_rates(self, category: str, symbol: str = "") -> dict:
        return self._session.get_fee_rates(category=category, symbol=symbol)

    def get_collateral_info(self) -> dict:
        return self._session.get_collateral_info()

    def set_margin_mode(self, setMarginMode: str) -> dict:
        return self._session.set_margin_mode(setMarginMode=setMarginMode)

    def set_leverage(self, category: str, symbol: str,
                     buyLeverage: str, sellLeverage: str) -> dict:
        return self._session.set_leverage(
            category=category, symbol=symbol,
            buyLeverage=buyLeverage, sellLeverage=sellLeverage,
        )

    # ---- Spot margin ---------------------------------------------------
    def get_spot_margin_state(self) -> dict:
        return self._session.get_vip_margin_data()  # or spot_margin_trade endpoint

    def toggle_spot_margin(self, spotMarginMode: str) -> dict:
        return self._session.toggle_margin_trade(spotMarginMode=spotMarginMode)

    # ---- Positions & Orders --------------------------------------------
    def get_positions(self, category: str, settleCoin: str = "USDT") -> dict:
        return self._session.get_positions(
            category=category, settleCoin=settleCoin
        )

    def get_open_orders(self, category: str, symbol: str = "") -> dict:
        return self._session.get_open_orders(
            category=category, symbol=symbol
        )

    def place_order(self, **kwargs: Any) -> dict:
        return self._session.place_order(**kwargs)

    def amend_order(self, **kwargs: Any) -> dict:
        return self._session.amend_order(**kwargs)

    def cancel_order(self, category: str, symbol: str, orderId: str) -> dict:
        return self._session.cancel_order(
            category=category, symbol=symbol, orderId=orderId
        )

    def cancel_all_orders(self, category: str, symbol: str = "") -> dict:
        params: dict = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._session.cancel_all_orders(**params)

    def set_trading_stop(self, **kwargs: Any) -> dict:
        return self._session.set_trading_stop(**kwargs)

    # ---- Asset / Transfer ----------------------------------------------
    def create_internal_transfer(self, **kwargs: Any) -> dict:
        return self._session.create_internal_transfer(**kwargs)

    def get_coins_balance(self, accountType: str, coin: str = "") -> dict:
        return self._session.get_coins_balance(
            accountType=accountType, coin=coin
        )

    # ---- Execution history ---------------------------------------------
    def get_executions(self, category: str, symbol: str = "",
                       limit: int = 50) -> dict:
        return self._session.get_executions(
            category=category, symbol=symbol, limit=limit
        )
