"""
core/collector.py — Parallel data collector for the trading agent
=================================================================

Purpose:
  Run ALL bybit-cli data queries in parallel background threads and
  assemble a single AgentContext object that the agent reads from.
  No pybit SDK needed — pure subprocess calls, but parallelised so
  the total latency is max(slowest_call) instead of sum(all_calls).

Usage:
    from core.collector import collect_for_agent, AgentContext

    ctx = collect_for_agent(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    print(ctx.balance)           # float USDT
    print(ctx.ticker["BTCUSDT"]) # dict with bid/ask/funding/...
    print(ctx.klines["BTCUSDT"]) # list[candle]
    print(ctx.today_pnl)         # float closed PnL today
    print(ctx.open_orders)       # list[dict]

Cache:
  Each data type has its own TTL so frequent ticks reuse stale data
  when appropriate (tickers: 10s, klines: 60s, account: 5s).
  Call collect_for_agent(symbols, force_refresh=True) to bypass cache.
"""
from __future__ import annotations

import os
import threading
import time
import datetime
import json
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.engine import (
    cli, get_klines, get_ticker, get_balance, get_free_margin,
    get_position, closes, highs, lows, volumes, rsi, atr, ema, zscore,
    CATEGORY, LEVERAGE,
)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL: dict[str, float] = {
    "ticker":       10.0,
    "klines":       60.0,
    "account":       5.0,
    "positions":    10.0,
    "open_orders":  15.0,
    "closed_pnl":   30.0,
    "orderbook":    10.0,
    "funding":      60.0,
}

_cache_store: dict[str, tuple[float, Any]] = {}  # key -> (timestamp, value)
_cache_lock = threading.Lock()


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache_store.get(key)
        if entry is None:
            return None
        ts, val = entry
        ttl_key = key.split(":")[0]
        ttl = _CACHE_TTL.get(ttl_key, 15.0)
        if time.monotonic() - ts > ttl:
            return None
        return val


def _cache_set(key: str, val: Any) -> None:
    with _cache_lock:
        _cache_store[key] = (time.monotonic(), val)


# ---------------------------------------------------------------------------
# AgentContext dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """All market + account data the agent needs, assembled in one object."""
    collected_at:  str = ""
    symbols:       list[str] = field(default_factory=list)

    # Account
    balance:       float = 0.0
    free_margin:   float = 0.0
    today_pnl:     float = 0.0
    today_pnl_pct: float = 0.0   # today_pnl / balance * 100

    # Per-symbol market data
    ticker:        dict[str, dict]       = field(default_factory=dict)  # sym -> ticker dict
    klines:        dict[str, list]       = field(default_factory=dict)  # sym -> candles
    indicators:    dict[str, dict]       = field(default_factory=dict)  # sym -> {rsi, atr, ...}
    orderbook:     dict[str, dict]       = field(default_factory=dict)  # sym -> {bids, asks, spread}

    # Positions & orders
    open_positions: list[dict]           = field(default_factory=list)
    open_orders:    list[dict]           = field(default_factory=list)

    # Meta
    fetch_ms:      int = 0   # total wall-clock time for collection in ms
    errors:        list[str] = field(default_factory=list)

    def position_for(self, symbol: str) -> dict | None:
        """Return open position for symbol, or None."""
        for p in self.open_positions:
            if p.get("symbol") == symbol and float(p.get("size", 0)) > 0:
                return p
        return None

    def spread_pct(self, symbol: str) -> float:
        ob = self.orderbook.get(symbol, {})
        return ob.get("spread_pct", 0.0)

    def price(self, symbol: str) -> float:
        t = self.ticker.get(symbol, {})
        return float(t.get("lastPrice", 0))

    def bid(self, symbol: str) -> float:
        t = self.ticker.get(symbol, {})
        return float(t.get("bid1Price", self.price(symbol)))

    def ask(self, symbol: str) -> float:
        t = self.ticker.get(symbol, {})
        return float(t.get("ask1Price", self.price(symbol)))

    def to_summary(self) -> str:
        """One-line summary per symbol for logging."""
        lines = [f"AgentContext @ {self.collected_at} | balance={self.balance:.2f} "
                 f"free={self.free_margin:.2f} pnl_today={self.today_pnl:+.2f}"]
        for sym in self.symbols:
            ind = self.indicators.get(sym, {})
            t   = self.ticker.get(sym, {})
            lines.append(
                f"  {sym}: price={self.price(sym):.4f} "
                f"rsi={ind.get('rsi','?')} zscore={ind.get('zscore','?')} "
                f"spread={self.spread_pct(sym):.4f}% "
                f"funding={float(t.get('fundingRate',0))*100:.4f}%"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual fetchers
# ---------------------------------------------------------------------------

def _fetch_account() -> tuple[float, float]:
    """Returns (balance, free_margin)."""
    cached = _cache_get("account:main")
    if cached: return cached
    b  = get_balance()
    fm = get_free_margin()
    _cache_set("account:main", (b, fm))
    return b, fm


def _fetch_closed_pnl_today(balance: float) -> tuple[float, float]:
    cached = _cache_get("closed_pnl:today")
    if cached: return cached
    try:
        data   = cli("position", "closed-pnl", "--category", CATEGORY, "--limit", "50")
        trades = data.get("result", {}).get("list", [])
        today  = datetime.date.today().strftime("%Y%m%d")
        pnl    = sum(float(t["closedPnl"]) for t in trades
                     if str(t.get("updatedTime", ""))[:8] == today)
        pct    = round(pnl / balance * 100, 4) if balance > 0 else 0
        result = (round(pnl, 4), pct)
        _cache_set("closed_pnl:today", result)
        return result
    except Exception as e:
        return 0.0, 0.0


def _fetch_ticker(symbol: str) -> dict:
    cached = _cache_get(f"ticker:{symbol}")
    if cached: return cached
    t = get_ticker(symbol, CATEGORY)
    _cache_set(f"ticker:{symbol}", t)
    return t


def _fetch_klines(symbol: str, interval: str = "60", limit: int = 100) -> list:
    key = f"klines:{symbol}:{interval}"
    cached = _cache_get(key)
    if cached: return cached
    k = get_klines(interval=interval, limit=limit, symbol=symbol, category=CATEGORY)
    _cache_set(key, k)
    return k


def _compute_indicators(symbol: str, candles: list) -> dict:
    if not candles or len(candles) < 20:
        return {}
    c   = closes(candles)
    return {
        "rsi":     round(rsi(c),       2) if len(c) >= 15 else None,
        "atr":     round(atr(candles), 6) if len(candles) >= 15 else None,
        "ema20":   round(ema(c, 20),   4) if len(c) >= 20 else None,
        "ema50":   round(ema(c, 50),   4) if len(c) >= 50 else None,
        "zscore":  round(zscore(c),    4) if len(c) >= 50 else None,
    }


def _fetch_orderbook(symbol: str) -> dict:
    """Fetch level-1 orderbook and compute effective spread."""
    cached = _cache_get(f"orderbook:{symbol}")
    if cached: return cached
    try:
        data = cli("market", "orderbook",
                   "--category", CATEGORY, "--symbol", symbol, "--limit", "1")
        ob   = data.get("result", {})
        bids = ob.get("b", [])
        asks = ob.get("a", [])
        bid1 = float(bids[0][0]) if bids else 0
        ask1 = float(asks[0][0]) if asks else 0
        mid  = (bid1 + ask1) / 2 if bid1 and ask1 else 0
        spread_pct = round((ask1 - bid1) / mid * 100, 5) if mid else 0
        result = {
            "bid":        bid1, "ask": ask1,
            "spread_pct": spread_pct,
            "bid_size":   float(bids[0][1]) if bids else 0,
            "ask_size":   float(asks[0][1]) if asks else 0,
        }
        _cache_set(f"orderbook:{symbol}", result)
        return result
    except Exception:
        return {"bid": 0, "ask": 0, "spread_pct": 0}


def _fetch_open_orders(symbol: str | None = None) -> list[dict]:
    cached = _cache_get("open_orders:all")
    if cached: return cached
    try:
        args = ["order", "realtime", "--category", CATEGORY]
        if symbol:
            args += ["--symbol", symbol]
        data   = cli(*args)
        orders = data.get("result", {}).get("list", [])
        _cache_set("open_orders:all", orders)
        return orders
    except Exception:
        return []


def _fetch_open_positions() -> list[dict]:
    cached = _cache_get("positions:all")
    if cached: return cached
    try:
        data  = cli("position", "info", "--category", CATEGORY, "--settleCoin", "USDT")
        items = data.get("result", {}).get("list", [])
        open_ = [p for p in items if float(p.get("size", 0)) > 0]
        _cache_set("positions:all", open_)
        return open_
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

def collect_for_agent(
    symbols: list[str],
    klines_interval: str = "60",
    klines_limit: int = 100,
    force_refresh: bool = False,
) -> AgentContext:
    """Collect all market + account data in parallel.

    Spawns one thread per data type per symbol.  Total wall-clock time
    equals the slowest single call (~200-400ms) instead of N*latency.

    Args:
        symbols:         list of symbols to scan (e.g. ["BTCUSDT", "ETHUSDT"])
        klines_interval: candle interval (default "60" = 1h)
        klines_limit:    number of candles per symbol (default 100)
        force_refresh:   bypass all cached data

    Returns:
        AgentContext with all fields populated
    """
    if force_refresh:
        with _cache_lock:
            _cache_store.clear()

    t0  = time.monotonic()
    ctx = AgentContext(
        collected_at=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        symbols=symbols,
    )
    errors: list[str] = []

    # --- submit all tasks in parallel ---
    futures: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=min(32, len(symbols) * 4 + 6)) as pool:

        # Account (shared)
        futures["account"]      = pool.submit(_fetch_account)
        futures["positions"]    = pool.submit(_fetch_open_positions)
        futures["open_orders"]  = pool.submit(_fetch_open_orders)

        # Per-symbol
        for sym in symbols:
            futures[f"ticker:{sym}"]   = pool.submit(_fetch_ticker, sym)
            futures[f"klines:{sym}"]   = pool.submit(_fetch_klines, sym,
                                                     klines_interval, klines_limit)
            futures[f"orderbook:{sym}"] = pool.submit(_fetch_orderbook, sym)

        # Collect results
        for key, fut in futures.items():
            try:
                val = fut.result(timeout=8)
                if key == "account":
                    ctx.balance, ctx.free_margin = val
                elif key == "positions":
                    ctx.open_positions = val
                elif key == "open_orders":
                    ctx.open_orders = val
                elif key.startswith("ticker:"):
                    sym = key.split(":", 1)[1]
                    ctx.ticker[sym] = val
                elif key.startswith("klines:"):
                    sym = key.split(":", 1)[1]
                    ctx.klines[sym] = val
                    ctx.indicators[sym] = _compute_indicators(sym, val)
                elif key.startswith("orderbook:"):
                    sym = key.split(":", 1)[1]
                    ctx.orderbook[sym] = val
            except Exception as e:
                err = f"{key}: {e}"
                errors.append(err)

    # Closed PnL (uses balance, do after account)
    try:
        ctx.today_pnl, ctx.today_pnl_pct = _fetch_closed_pnl_today(ctx.balance)
    except Exception as e:
        errors.append(f"closed_pnl: {e}")

    ctx.errors   = errors
    ctx.fetch_ms = int((time.monotonic() - t0) * 1000)
    return ctx


# ---------------------------------------------------------------------------
# CLI entrypoint — useful as standalone subprocess too
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Collect agent context snapshot")
    parser.add_argument("--symbols", default=os.getenv("SYMBOL", "BTCUSDT"),
                        help="Comma-separated symbols")
    parser.add_argument("--interval", default="60")
    parser.add_argument("--limit",    type=int, default=100)
    parser.add_argument("--json",     action="store_true")
    parser.add_argument("--force",    action="store_true", help="Bypass cache")
    args = parser.parse_args()

    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    ctx  = collect_for_agent(syms, args.interval, args.limit, force_refresh=args.force)

    if args.json:
        # Machine-readable output for subprocess consumers
        out = {
            "collected_at":   ctx.collected_at,
            "fetch_ms":       ctx.fetch_ms,
            "balance":        ctx.balance,
            "free_margin":    ctx.free_margin,
            "today_pnl":      ctx.today_pnl,
            "today_pnl_pct":  ctx.today_pnl_pct,
            "ticker":         ctx.ticker,
            "indicators":     ctx.indicators,
            "orderbook":      ctx.orderbook,
            "open_positions": ctx.open_positions,
            "open_orders":    ctx.open_orders,
            "errors":         ctx.errors,
        }
        print(json.dumps(out, indent=2))
    else:
        print(ctx.to_summary())
        if ctx.errors:
            print(f"\nErrors: {ctx.errors}")
        print(f"\nFetched in {ctx.fetch_ms}ms")
