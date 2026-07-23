"""
snapshot.py — ACCOUNT_SNAPSHOT builder

Calls Bybit V5 API to build a full picture of:
  - UNIFIED wallet balance
  - FUND wallet balance
  - Open positions (linear, inverse if enabled)
  - Open orders (spot + linear)
  - Fee rates per symbol
  - Spot margin state
  - Borrow/liability summary
  - instruments-info cache (tick, lot, minNotional)

Output: ACCOUNT_SNAPSHOT dict used by allocator.py and risk modules.
"""

from __future__ import annotations
import time
from typing import Any


def build_snapshot(client: Any, config: dict) -> dict:
    """
    Build full ACCOUNT_SNAPSHOT.
    client: pybit UnifiedHTTP or equivalent
    config: loaded config.yaml dict
    Returns: snapshot dict
    """
    snapshot: dict = {
        "ts": int(time.time() * 1000),
        "env": config.get("env", "mainnet"),
    }

    # --- Clock skew check ---
    server_time = client.get_server_time()
    snapshot["server_ts"] = server_time.get("time", 0)
    skew_ms = abs(snapshot["ts"] - snapshot["server_ts"])
    if skew_ms > 5000:
        raise RuntimeError(f"Clock skew too large: {skew_ms}ms — sync system clock")

    # --- Account info ---
    acct_info = client.get_account_info()
    snapshot["unified_margin_status"] = acct_info.get("result", {}).get("unifiedMarginStatus")
    snapshot["margin_mode"] = acct_info.get("result", {}).get("marginMode")
    snapshot["dcp_status"] = acct_info.get("result", {}).get("dcpStatus")

    # --- UNIFIED wallet ---
    unified = client.get_wallet_balance(accountType="UNIFIED")
    snapshot["unified_wallet"] = unified.get("result", {}).get("list", [{}])[0]
    snapshot["total_equity"] = float(
        snapshot["unified_wallet"].get("totalEquity", 0)
    )
    snapshot["available_balance"] = float(
        snapshot["unified_wallet"].get("totalAvailableBalance", 0)
    )

    # --- FUND wallet ---
    # TODO: call GET /v5/asset/transfer/query-account-coins-balance
    snapshot["fund_wallet"] = {}
    snapshot["fund_usdt"] = 0.0  # populate via asset module

    # --- Open positions ---
    pos_linear = client.get_positions(category="linear", settleCoin="USDT")
    snapshot["positions_linear"] = pos_linear.get("result", {}).get("list", [])
    snapshot["positions_inverse"] = []  # populate if ENABLE_INVERSE

    # --- Open orders ---
    orders_linear = client.get_open_orders(category="linear")
    orders_spot = client.get_open_orders(category="spot")
    snapshot["open_orders_linear"] = orders_linear.get("result", {}).get("list", [])
    snapshot["open_orders_spot"] = orders_spot.get("result", {}).get("list", [])

    # --- Spot margin state ---
    margin_state = client.get_spot_margin_state()
    snapshot["spot_margin_mode"] = margin_state.get("result", {}).get("spotMarginMode", "0")
    snapshot["spot_leverage"] = margin_state.get("result", {}).get("leverage", "1")

    # --- Fee rates (active symbols) ---
    snapshot["fee_rates"] = {}
    for symbol in config.get("watchlist", ["BTCUSDT"]):
        rate_linear = client.get_fee_rates(category="linear", symbol=symbol)
        rate_spot = client.get_fee_rates(category="spot", symbol=symbol)
        snapshot["fee_rates"][symbol] = {
            "linear": rate_linear.get("result", {}).get("list", [{}])[0],
            "spot": rate_spot.get("result", {}).get("list", [{}])[0],
        }

    # --- Borrow / liability ---
    # TODO: GET /v5/account/borrow-history
    snapshot["borrow_liabilities"] = []
    snapshot["total_borrow_usdt"] = 0.0

    return snapshot


def compute_imr_mmr(snapshot: dict) -> tuple[float, float]:
    """Compute aggregate IMR and MMR from positions."""
    total_im = sum(
        float(p.get("positionIM", 0))
        for p in snapshot.get("positions_linear", [])
    )
    total_mm = sum(
        float(p.get("positionMM", 0))
        for p in snapshot.get("positions_linear", [])
    )
    equity = snapshot.get("total_equity", 1)
    imr = (total_im / equity * 100) if equity else 0
    mmr = (total_mm / equity * 100) if equity else 0
    return round(imr, 2), round(mmr, 2)
