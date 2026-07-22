"""
Dynamic Watchlist Builder v2
============================
Key changes vs v1:
  - Cache TTL: 30s default (was 300s) — crypto moves fast
  - Refresh trigger: time-based (elapsed > TTL), NOT tick-count based
  - Background prefetch: ticker fetch runs on a daemon thread so it never
    blocks the LLM decision. The agent always gets the freshest available
    list without waiting for a network round-trip.
  - Stale-while-revalidate: if cache is stale but prefetch is in flight,
    return stale data immediately and let the background thread update it.

Usage:
    from llm.watchlist import build_watchlist, warm_cache
    warm_cache()          # call once at startup to prefetch in background
    symbols = build_watchlist()   # always instant (returns cached)

    # Standalone
    python llm/watchlist.py
    python llm/watchlist.py --top 20 --min-vol 5000000 --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import cli, log_info, log_error

# ---------------------------------------------------------------------------
# Config  (all overridable via .env)
# ---------------------------------------------------------------------------

DEFAULT_CATEGORY  = os.getenv("WATCHLIST_CATEGORY",      "linear")
DEFAULT_TOP_N     = int(os.getenv("WATCHLIST_TOP_N",     "15"))
DEFAULT_MIN_VOL   = float(os.getenv("WATCHLIST_MIN_VOL_USD",    "10000000"))  # 10M USDT
DEFAULT_MAX_SPREAD= float(os.getenv("WATCHLIST_MAX_SPREAD_PCT",  "0.1"))      # 0.1%
DEFAULT_MIN_CHANGE= float(os.getenv("WATCHLIST_MIN_CHANGE_PCT",  "0.5"))      # 0.5% 24h move
DEFAULT_QUOTE     = os.getenv("WATCHLIST_QUOTE", "USDT")

# 30s default — one refresh per agent tick at 30s intervals.
# Set lower (e.g. 15) for scalping loops, higher (60) for 15-min loops.
CACHE_TTL         = int(os.getenv("WATCHLIST_CACHE_TTL_SEC", "30"))

BLACKLIST: set[str] = {
    "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "USDTUSDT", "DAIUSDT", "FRAXUSDT",
    "WBTCUSDT", "WETHUSDT", "STETHUSDT", "CBETHUSDT",
    "BTC3LUSDT", "BTC3SUSDT", "ETH3LUSDT", "ETH3SUSDT",
    "SOL3LUSDT", "SOL3SUSDT",
}

ALWAYS_INCLUDE: set[str] = {
    sym.strip()
    for sym in os.getenv("WATCHLIST_ALWAYS_INCLUDE", "BTCUSDT,ETHUSDT").split(",")
    if sym.strip()
}

# ---------------------------------------------------------------------------
# Cache  (thread-safe via lock)
# ---------------------------------------------------------------------------

class _WatchlistCache:
    def __init__(self) -> None:
        self._lock     = threading.Lock()
        self._symbols: list[str]  = []
        self._detail:  list[dict] = []
        self._ts:      float      = 0.0          # last successful fetch
        self._fetching: bool      = False        # prefetch in flight?

    # -- readers (always instant) --

    def get(self, top_n: int) -> list[str]:
        with self._lock:
            return list(self._symbols[:top_n])

    def get_detail(self) -> list[dict]:
        with self._lock:
            return list(self._detail)

    def age(self) -> float:
        with self._lock:
            return time.time() - self._ts if self._ts else float("inf")

    def is_stale(self) -> bool:
        return self.age() >= CACHE_TTL

    def has_data(self) -> bool:
        with self._lock:
            return bool(self._symbols)

    def is_fetching(self) -> bool:
        with self._lock:
            return self._fetching

    # -- writer --

    def update(self, symbols: list[str], detail: list[dict]) -> None:
        with self._lock:
            self._symbols  = symbols
            self._detail   = detail
            self._ts       = time.time()
            self._fetching = False
        log_info(f"[watchlist] cache updated — {len(symbols)} symbols  "
                 f"top3={symbols[:3]}")

    def set_fetching(self, v: bool) -> None:
        with self._lock:
            self._fetching = v


_cache = _WatchlistCache()


# ---------------------------------------------------------------------------
# Core: fetch + score
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fetch_and_score(
    category: str,
    top_n: int,
    min_vol: float    = DEFAULT_MIN_VOL,
    max_spread: float = DEFAULT_MAX_SPREAD,
    min_change: float = DEFAULT_MIN_CHANGE,
) -> tuple[list[str], list[dict]]:
    """Fetch all tickers from Bybit, filter + score, return (symbols, detail).

    Filter thresholds are explicit parameters — module-level DEFAULT_* globals
    are never mutated.  This makes the function safe to call from tests or
    CLI without polluting the shared module state.
    """
    data  = cli("market", "tickers", "--category", category)
    items = data.get("result", {}).get("list", [])
    log_info(f"[watchlist] fetched {len(items)} tickers ({category})")

    scored: list[dict] = []
    for t in items:
        s = _score_ticker(t, min_vol=min_vol, max_spread=max_spread, min_change=min_change)
        if s:
            scored.append(s)

    scored.sort(key=lambda x: x["score"], reverse=True)

    symbols = [s["symbol"] for s in scored[:top_n]]
    for sym in ALWAYS_INCLUDE:
        if sym not in symbols:
            symbols.append(sym)

    return symbols, scored


def _score_ticker(
    t: dict,
    min_vol: float    = DEFAULT_MIN_VOL,
    max_spread: float = DEFAULT_MAX_SPREAD,
    min_change: float = DEFAULT_MIN_CHANGE,
) -> dict | None:
    symbol  = t.get("symbol", "")
    if not symbol.endswith(DEFAULT_QUOTE):  return None
    if symbol in BLACKLIST:                 return None

    price   = _safe_float(t.get("lastPrice"))
    if price <= 0: return None

    turnover  = _safe_float(t.get("turnover24h"))
    vol_24h   = _safe_float(t.get("volume24h"))
    vol_usd   = turnover if turnover > 0 else vol_24h * price
    chg_pct   = _safe_float(t.get("price24hPcnt"))   # 0.032 = 3.2%
    bid       = _safe_float(t.get("bid1Price"))
    ask       = _safe_float(t.get("ask1Price"))
    funding   = _safe_float(t.get("fundingRate"))
    oi        = _safe_float(t.get("openInterestValue"))
    spread    = (ask - bid) / price * 100 if bid > 0 and ask > 0 else 999.0

    # Hard filters (use explicit params, NOT module globals)
    if vol_usd < min_vol:                                          return None
    if spread  > max_spread:                                       return None
    if abs(chg_pct) * 100 < min_change \
       and symbol not in ALWAYS_INCLUDE:                           return None

    # Score
    vol_s  = math.log10(max(vol_usd, 1))
    chg_s  = abs(chg_pct) * 100
    fund_s = abs(funding) * 10_000
    spr_s  = spread * -20
    oi_s   = math.log10(max(oi, 1)) * 0.5 if oi > 0 else 0
    total  = vol_s + chg_s + fund_s + spr_s + oi_s

    return {
        "symbol":        symbol,
        "score":         round(total, 3),
        "price":         price,
        "vol_usd_24h":   round(vol_usd),
        "chg_24h_pct":   round(chg_pct * 100, 3),
        "spread_pct":    round(spread, 4),
        "funding_rate":  round(funding, 6),
        "open_interest": round(oi),
        "score_breakdown": {
            "vol": round(vol_s, 3), "change": round(chg_s, 3),
            "funding": round(fund_s, 3), "spread": round(spr_s, 3),
            "oi": round(oi_s, 3),
        },
    }


# ---------------------------------------------------------------------------
# Background prefetch
# ---------------------------------------------------------------------------

def _prefetch_worker(category: str, top_n: int) -> None:
    """Runs on a daemon thread. Updates cache when done."""
    try:
        symbols, detail = _fetch_and_score(category, top_n)
        _cache.update(symbols, detail)
    except Exception as e:
        log_error(f"[watchlist] background fetch failed: {e}")
        _cache.set_fetching(False)   # release lock so next call retries


def _trigger_prefetch(category: str, top_n: int) -> None:
    """Spawns background fetch thread (idempotent — won't double-spawn)."""
    if _cache.is_fetching():
        return
    _cache.set_fetching(True)
    t = threading.Thread(
        target=_prefetch_worker, args=(category, top_n),
        daemon=True, name="watchlist-prefetch"
    )
    t.start()
    log_info("[watchlist] background prefetch started")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def warm_cache(category: str = DEFAULT_CATEGORY, top_n: int = DEFAULT_TOP_N) -> None:
    """
    Call once at agent startup to pre-populate the cache in the background.
    The first build_watchlist() call will return ALWAYS_INCLUDE until the
    background fetch completes (usually < 2s).
    """
    _trigger_prefetch(category, top_n)


def build_watchlist(
    top_n:    int  = DEFAULT_TOP_N,
    category: str  = DEFAULT_CATEGORY,
    force:    bool = False,
) -> list[str]:
    """
    Returns cached watchlist (always instant, never blocks).

    Stale-while-revalidate strategy:
      - If cache is fresh (age < TTL)  → return immediately
      - If cache is stale              → return stale + trigger background refresh
      - If cache is empty              → block once (first startup only)
    """
    stale = _cache.is_stale()
    has   = _cache.has_data()

    if force or (stale and not has):
        # First call ever OR forced: fetch synchronously so we have data
        log_info(f"[watchlist] sync fetch (force={force}, has_data={has})")
        try:
            symbols, detail = _fetch_and_score(category, top_n)
            _cache.update(symbols, detail)
        except Exception as e:
            log_error(f"[watchlist] sync fetch failed: {e}")
            return list(ALWAYS_INCLUDE)
    elif stale and has:
        # Stale but we have old data — return old, refresh in background
        log_info(f"[watchlist] stale (age={_cache.age():.0f}s) — serving cache, "
                 f"triggering background refresh")
        _trigger_prefetch(category, top_n)
    else:
        log_info(f"[watchlist] cache fresh (age={_cache.age():.0f}s / TTL={CACHE_TTL}s)")

    result = _cache.get(top_n)
    # Safety: always include anchor symbols
    for sym in ALWAYS_INCLUDE:
        if sym not in result:
            result.append(sym)
    return result


def get_detail() -> list[dict]:
    return _cache.get_detail()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_table(scored: list[dict]) -> None:
    hdr = f"{'#':>3}  {'Symbol':<14} {'Score':>7}  {'Vol_USD_24h':>14}  "\
          f"{'Chg%':>7}  {'Spread%':>8}  {'Funding':>9}  {'OI_USD':>14}"
    sep = "-" * len(hdr)
    print(sep); print(hdr); print(sep)
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
    parser.add_argument("--top",        type=int,   default=DEFAULT_TOP_N)
    parser.add_argument("--category",   type=str,   default=DEFAULT_CATEGORY)
    parser.add_argument("--min-vol",    type=float, default=DEFAULT_MIN_VOL)
    parser.add_argument("--max-spread", type=float, default=DEFAULT_MAX_SPREAD)
    parser.add_argument("--min-change", type=float, default=DEFAULT_MIN_CHANGE)
    parser.add_argument("--json",       action="store_true")
    parser.add_argument("--force",      action="store_true")
    args = parser.parse_args()

    # FIX #3: pass CLI args explicitly — do NOT overwrite module-level globals.
    # This keeps DEFAULT_* safe if watchlist.py is imported in the same process.
    symbols, detail = _fetch_and_score(
        category=args.category,
        top_n=args.top,
        min_vol=args.min_vol,
        max_spread=args.max_spread,
        min_change=args.min_change,
    )
    # Inject ALWAYS_INCLUDE anchors
    for sym in ALWAYS_INCLUDE:
        if sym not in symbols:
            symbols.append(sym)

    if args.json:
        print(json.dumps({"symbols": symbols, "detail": detail[:args.top]}, indent=2))
    else:
        print(f"\nDynamic Watchlist [{args.category}] — top {args.top} "
              f"(TTL={CACHE_TTL}s, age={_cache.age():.0f}s)\n")
        _print_table(detail[:args.top])
        print(f"\nSelected ({len(symbols)}): {symbols}\n")
