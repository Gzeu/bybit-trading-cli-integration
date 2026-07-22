"""
Dynamic Watchlist Builder
=========================
Extracts the best trading symbols directly from Bybit at runtime,
filtered and ranked on real criteria:

  1. Minimum 24h volume (liquidity floor)
  2. Maximum spread % (execution quality)
  3. Minimum 24h price change (something is moving)
  4. Funding rate signal (|funding| threshold for arb)
  5. Volatility bucket (optional: high / medium / low)
  6. Blacklist exclusion (stablecoins, wrapped tokens, etc.)

Ranking score per symbol:
  vol_score   = log10(volume_24h)           — liquidity
  change_score = abs(price_24h_pct) * 100   — movement
  funding_score = abs(funding_rate) * 10000 — arb edge
  spread_penalty = spread_pct * -20          — penalize wide spreads

  total = vol_score + change_score + funding_score + spread_penalty

Usage:
    # In agent_loop.py (automatic, refreshed every N ticks)
    from llm.watchlist import build_watchlist
    symbols = build_watchlist()         # returns list[str], e.g. ["SOLUSDT", "BTCUSDT", ...]

    # Standalone test
    python llm/watchlist.py
    python llm/watchlist.py --top 20 --min-vol 5000000 --category linear
    python llm/watchlist.py --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import cli, log_info, log_error

# ---------------------------------------------------------------------------
# Defaults (all overridable via .env)
# ---------------------------------------------------------------------------

DEFAULT_CATEGORY   = os.getenv("WATCHLIST_CATEGORY",   "linear")  # linear | spot | inverse
DEFAULT_TOP_N       = int(os.getenv("WATCHLIST_TOP_N",  "15"))
DEFAULT_MIN_VOL     = float(os.getenv("WATCHLIST_MIN_VOL_USD",  "10000000"))  # 10M USDT 24h
DEFAULT_MAX_SPREAD  = float(os.getenv("WATCHLIST_MAX_SPREAD_PCT", "0.1"))     # 0.1%
DEFAULT_MIN_CHANGE  = float(os.getenv("WATCHLIST_MIN_CHANGE_PCT", "0.5"))     # 0.5% move
DEFAULT_MIN_FUNDING = float(os.getenv("WATCHLIST_MIN_FUNDING",    "0.0"))     # 0 = no filter
DEFAULT_QUOTE       = os.getenv("WATCHLIST_QUOTE",  "USDT")                   # quote currency

# Symbols to always exclude
BLACKLIST: set[str] = {
    # Stablecoins
    "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "USDTUSDT", "DAIUSDT", "FRAXUSDT",
    # Wrapped / rebasing
    "WBTCUSDT", "WETHUSDT", "STETHUSDT", "CBETHUSDT",
    # Leverage tokens
    "BTC3LUSDT", "BTC3SUSDT", "ETH3LUSDT", "ETH3SUSDT",
    "SOL3LUSDT", "SOL3SUSDT",
}

# Hard-include: always in watchlist regardless of score
ALWAYS_INCLUDE: set[str] = {
    sym.strip()
    for sym in os.getenv("WATCHLIST_ALWAYS_INCLUDE", "BTCUSDT,ETHUSDT").split(",")
    if sym.strip()
}

# Cache: avoid re-fetching on every single call within same process run
_cache: dict[str, Any] = {"symbols": [], "ts": 0.0}
CACHE_TTL = int(os.getenv("WATCHLIST_CACHE_TTL_SEC", "300"))  # 5 min default


# ---------------------------------------------------------------------------
# Fetch all tickers from Bybit
# ---------------------------------------------------------------------------

def fetch_all_tickers(category: str = DEFAULT_CATEGORY) -> list[dict]:
    """Fetch all tickers for a category (no symbol filter)."""
    data = cli("market", "tickers", "--category", category)
    items = data.get("result", {}).get("list", [])
    log_info(f"[watchlist] fetched {len(items)} tickers from Bybit ({category})")
    return items


# ---------------------------------------------------------------------------
# Filtering & scoring
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def score_ticker(t: dict, category: str) -> dict | None:
    """
    Score a single ticker. Returns None if it fails any hard filter.
    """
    symbol    = t.get("symbol", "")
    quote     = DEFAULT_QUOTE

    # Must end with quote currency
    if not symbol.endswith(quote):
        return None

    # Blacklist
    if symbol in BLACKLIST:
        return None

    price      = _safe_float(t.get("lastPrice"))
    vol_24h    = _safe_float(t.get("volume24h"))   # volume in base asset
    turnover   = _safe_float(t.get("turnover24h")) # volume in quote (USDT)
    chg_pct    = _safe_float(t.get("price24hPcnt"))  # e.g. 0.032 = 3.2%
    bid        = _safe_float(t.get("bid1Price"))
    ask        = _safe_float(t.get("ask1Price"))
    funding    = _safe_float(t.get("fundingRate"))   # linear futures only
    oi         = _safe_float(t.get("openInterestValue"))  # USDT, linear only

    if price <= 0:
        return None

    spread_pct = (ask - bid) / price * 100 if bid > 0 and ask > 0 else 999.0

    # Use turnover (USDT) for volume floor; fallback to vol * price
    vol_usd = turnover if turnover > 0 else vol_24h * price

    # ---- Hard filters ----
    if vol_usd < DEFAULT_MIN_VOL:
        return None
    if spread_pct > DEFAULT_MAX_SPREAD:
        return None
    if abs(chg_pct) * 100 < DEFAULT_MIN_CHANGE and symbol not in ALWAYS_INCLUDE:
        return None

    # ---- Scoring ----
    vol_score     = math.log10(max(vol_usd, 1))
    change_score  = abs(chg_pct) * 100          # e.g. 3.2% → 3.2
    funding_score = abs(funding) * 10_000        # 0.001 → 10
    spread_pen    = spread_pct * -20             # tighter = better
    oi_score      = math.log10(max(oi, 1)) * 0.5 if oi > 0 else 0

    total = vol_score + change_score + funding_score + spread_pen + oi_score

    return {
        "symbol":       symbol,
        "score":        round(total, 3),
        "price":        price,
        "vol_usd_24h":  round(vol_usd),
        "chg_24h_pct":  round(chg_pct * 100, 3),
        "spread_pct":   round(spread_pct, 4),
        "funding_rate": round(funding, 6),
        "open_interest": round(oi),
        "score_breakdown": {
            "vol":     round(vol_score, 3),
            "change":  round(change_score, 3),
            "funding": round(funding_score, 3),
            "spread":  round(spread_pen, 3),
            "oi":      round(oi_score, 3),
        },
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_watchlist(
    top_n:    int   = DEFAULT_TOP_N,
    category: str   = DEFAULT_CATEGORY,
    force:    bool  = False,
) -> list[str]:
    """
    Returns a ranked list of symbol strings, max top_n.
    Results are cached for CACHE_TTL seconds to avoid re-fetching on every call.
    """
    now = time.time()
    if not force and _cache["symbols"] and (now - _cache["ts"]) < CACHE_TTL:
        log_info(f"[watchlist] using cache ({len(_cache['symbols'])} symbols, "
                 f"age={(now - _cache['ts']):.0f}s)")
        return _cache["symbols"][:top_n]

    tickers = fetch_all_tickers(category)
    if not tickers:
        log_error("[watchlist] empty ticker response — returning ALWAYS_INCLUDE")
        return list(ALWAYS_INCLUDE)

    scored = []
    for t in tickers:
        result = score_ticker(t, category)
        if result:
            scored.append(result)

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Build final list: always_include first (if not already in top), then top_n
    final_syms = [s["symbol"] for s in scored[:top_n]]
    for sym in ALWAYS_INCLUDE:
        if sym not in final_syms:
            final_syms.append(sym)

    log_info(f"[watchlist] selected {len(final_syms)} symbols: {final_syms}")

    # Update cache
    _cache["symbols"] = final_syms
    _cache["ts"]      = now
    _cache["detail"]  = scored  # keep full scored list for debug

    return final_syms


def get_detail() -> list[dict]:
    """Return full scored list from last build_watchlist() call."""
    return _cache.get("detail", [])


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def _print_table(scored: list[dict]) -> None:
    header = f"{'#':>3}  {'Symbol':<14} {'Score':>7}  {'Vol_USD_24h':>14}  {'Chg%':>7}  {'Spread%':>8}  {'Funding':>9}  {'OI_USD':>14}"
    sep    = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for i, s in enumerate(scored, 1):
        print(
            f"{i:>3}  {s['symbol']:<14} {s['score']:>7.2f}  "
            f"{s['vol_usd_24h']:>14,.0f}  {s['chg_24h_pct']:>7.2f}%  "
            f"{s['spread_pct']:>8.4f}%  {s['funding_rate']:>9.6f}  "
            f"{s['open_interest']:>14,.0f}"
        )
    print(sep)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bybit dynamic watchlist builder")
    parser.add_argument("--top",        type=int,   default=DEFAULT_TOP_N,     help="Max symbols to return")
    parser.add_argument("--category",   type=str,   default=DEFAULT_CATEGORY,  help="linear | spot | inverse")
    parser.add_argument("--min-vol",    type=float, default=DEFAULT_MIN_VOL,   help="Min 24h volume USDT")
    parser.add_argument("--max-spread", type=float, default=DEFAULT_MAX_SPREAD,help="Max spread %")
    parser.add_argument("--min-change", type=float, default=DEFAULT_MIN_CHANGE,help="Min 24h change %")
    parser.add_argument("--json",       action="store_true", help="JSON output")
    parser.add_argument("--force",      action="store_true", help="Bypass cache")
    args = parser.parse_args()

    # Override env defaults from CLI args
    DEFAULT_MIN_VOL    = args.min_vol
    DEFAULT_MAX_SPREAD = args.max_spread
    DEFAULT_MIN_CHANGE = args.min_change

    build_watchlist(top_n=args.top, category=args.category, force=args.force)
    detail = get_detail()
    selected = [s["symbol"] for s in detail[:args.top]]

    if args.json:
        print(json.dumps({"symbols": selected, "detail": detail[:args.top]}, indent=2))
    else:
        print(f"\nDynamic Watchlist  [{args.category}]  —  top {args.top} by score\n")
        _print_table(detail[:args.top])
        print(f"\nSelected: {selected}\n")
