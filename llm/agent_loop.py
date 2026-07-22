"""LLM Agent Loop — dynamic watchlist + multi-symbol scan + regime-filtered strategies.

Workflow per tick:
  1. build_watchlist()         ← dynamic from Bybit (vol, spread, funding, OI)
  2. scan_opportunities()      ← score each symbol (RSI, zscore, vol spike, ...)
  3. top_n best symbols        ← sent to LLM with full context
  4. LLM decides               ← symbol + strategy filtered by regime
  5. validate + execute

Usage:
    python llm/agent_loop.py --once
    python llm/agent_loop.py --interval 900
    python llm/agent_loop.py --dry-run --once
    python llm/agent_loop.py --symbols BTCUSDT,ETHUSDT  # manual override
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.providers import chat_complete, parse_action
from llm.watchlist import build_watchlist
from core.engine import (
    get_klines, get_ticker, get_balance, get_position,
    closes, highs, lows, volumes,
    rsi, atr, ema, zscore,
    log_info, log_error,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "llm_agent.log"),
    ],
)
log = logging.getLogger("llm_agent")

# ---------------------------------------------------------------------------
# Strategy registry  (26 strategies → regim)
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    "trend_follow":         {"regimes": ["bull", "bear"],              "type": "trend"},
    "mean_reversion":       {"regimes": ["sideways"],                  "type": "mean_revert"},
    "grid_trading":         {"regimes": ["sideways"],                  "type": "grid"},
    "scalping":             {"regimes": ["bull", "bear", "sideways"],  "type": "scalp"},
    "breakout":             {"regimes": ["volatile", "bull", "bear"],  "type": "breakout"},
    "funding_arb":          {"regimes": ["bull", "bear", "sideways", "volatile"], "type": "arb"},
    "kalman_filter":        {"regimes": ["bull", "bear"],              "type": "trend"},
    "bollinger_bands":      {"regimes": ["sideways"],                  "type": "mean_revert"},
    "macd_signal":          {"regimes": ["bull", "bear"],              "type": "trend"},
    "rsi_divergence":       {"regimes": ["sideways", "bull", "bear"],  "type": "reversal"},
    "stochastic_rsi":       {"regimes": ["sideways"],                  "type": "oscillator"},
    "adx_trend_filter":     {"regimes": ["bull", "bear"],              "type": "trend"},
    "supertrend":           {"regimes": ["bull", "bear"],              "type": "trend"},
    "ichimoku_cloud":       {"regimes": ["bull", "bear"],              "type": "trend"},
    "heikin_ashi_trend":    {"regimes": ["bull", "bear"],              "type": "trend"},
    "parabolic_sar":        {"regimes": ["bull", "bear"],              "type": "trend"},
    "triple_ema":           {"regimes": ["bull", "bear"],              "type": "trend"},
    "turtle_trading":       {"regimes": ["bull", "bear", "volatile"],  "type": "breakout"},
    "vwap_reversion":       {"regimes": ["sideways"],                  "type": "mean_revert"},
    "williams_r":           {"regimes": ["sideways", "bull", "bear"],  "type": "oscillator"},
    "cci_reversal":         {"regimes": ["sideways"],                  "type": "reversal"},
    "momentum_roc":         {"regimes": ["bull", "bear"],              "type": "momentum"},
    "volatility_targeting": {"regimes": ["bull", "bear", "sideways", "volatile"], "type": "risk"},
    "market_making":        {"regimes": ["sideways"],                  "type": "mm"},
    "dca_accumulation":     {"regimes": ["sideways", "bull"],          "type": "dca"},
    "multi_timeframe":      {"regimes": ["bull", "bear"],              "type": "confluence"},
    "pairs_trading":        {"regimes": ["sideways", "volatile"],      "type": "stat_arb"},
    "open_interest_spike":  {"regimes": ["volatile", "bull", "bear"],  "type": "flow"},
    "liquidation_hunt":     {"regimes": ["volatile"],                  "type": "flow"},
}

ALLOWED_STRATEGIES = set(STRATEGY_REGISTRY.keys())
ALLOWED_ACTIONS    = {"open_long", "open_short", "close_position", "reduce_size", "hold", "wait"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "SYSTEM_PROMPT.md"
BRIEFING_PATH      = Path(__file__).parent.parent / "agent" / "AGENT_BRIEFING.md"

# ---------------------------------------------------------------------------
# Inline regime detection (no subprocess)
# ---------------------------------------------------------------------------
import statistics as _stats

TREND_THRESH = float(os.getenv("TREND_THRESH",    "0.003"))
VOL_HIGH     = float(os.getenv("VOL_THRESH_HIGH", "0.02"))
VOL_LOW      = float(os.getenv("VOL_THRESH_LOW",  "0.008"))


def detect_regime_local(symbol: str, category: str = "linear") -> tuple[str, dict]:
    candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
    if len(candles) < 20:
        return "unknown", {}
    c         = closes(candles)
    ret       = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
    mean_ret  = _stats.mean(ret[-50:])
    vol       = _stats.stdev(ret[-50:])
    rsi_val   = rsi(c)
    atr_val   = atr(candles)
    price     = c[-1]
    atr_pct   = atr_val / price if price else 0
    vols      = volumes(candles)
    vol_avg   = sum(vols[-20:]) / 20
    vol_ratio = vols[-1] / vol_avg if vol_avg > 0 else 1

    if vol > VOL_HIGH and vol_ratio > 1.8:
        regime = "volatile"
    elif abs(mean_ret) > TREND_THRESH and atr_pct > 0.005:
        regime = "bull" if mean_ret > 0 else "bear"
    elif vol < VOL_LOW:
        regime = "sideways"
    elif abs(mean_ret) > TREND_THRESH:
        regime = "bull" if mean_ret > 0 else "bear"
    else:
        regime = "sideways"

    return regime, {
        "regime": regime, "mean_ret": round(mean_ret, 6),
        "volatility": round(vol, 6), "rsi": round(rsi_val, 2),
        "atr_pct": round(atr_pct, 5), "vol_ratio": round(vol_ratio, 2),
        "price": price,
    }


def eligible_strategies(regime: str) -> list[str]:
    return [n for n, cfg in STRATEGY_REGISTRY.items() if regime in cfg["regimes"]]


# ---------------------------------------------------------------------------
# Multi-symbol opportunity scanner
# ---------------------------------------------------------------------------

def score_opportunity(symbol: str, category: str = "linear") -> dict | None:
    try:
        candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
        if len(candles) < 20:
            return None
        ticker    = get_ticker(symbol, category)
        c         = closes(candles)
        price     = c[-1]
        rsi_val   = rsi(c)
        atr_val   = atr(candles)
        zs        = zscore(c) if len(c) >= 50 else 0.0
        ema20     = ema(c, 20)
        ema50     = ema(c, 50) if len(c) >= 50 else ema20
        funding   = float(ticker.get("fundingRate", 0))
        chg24h    = float(ticker.get("price24hPcnt", 0))
        bid       = float(ticker.get("bid1Price", price))
        ask       = float(ticker.get("ask1Price", price))
        spread    = (ask - bid) / price * 100 if price else 0
        vols      = volumes(candles)
        vol_avg   = sum(vols[-20:]) / 20
        vol_spike = vols[-1] / vol_avg if vol_avg > 0 else 1

        regime, rstats = detect_regime_local(symbol, category)
        strategies     = eligible_strategies(regime)

        score, signals = 0, []
        if rsi_val < 30:          score += 25; signals.append(f"RSI_oversold({rsi_val:.0f})")
        elif rsi_val > 70:        score += 25; signals.append(f"RSI_overbought({rsi_val:.0f})")
        if abs(zs) > 2.0:         score += 20; signals.append(f"zscore={zs:.2f}")
        if vol_spike > 2.0:       score += 20; signals.append(f"vol_spike_x{vol_spike:.1f}")
        if abs(chg24h) > 0.03:    score += 15; signals.append(f"chg24h={chg24h*100:.1f}%")
        if abs(funding) > 0.0005: score += 10; signals.append(f"funding={funding*100:.4f}%")
        if spread < 0.05:         score += 10; signals.append("tight_spread")

        return {
            "symbol": symbol, "score": score, "signals": signals,
            "regime": regime, "regime_stats": rstats, "strategies": strategies,
            "price": price, "rsi": round(rsi_val, 2), "zscore": round(zs, 3),
            "atr": round(atr_val, 4), "funding": funding,
            "vol_spike": round(vol_spike, 2), "chg24h": round(chg24h, 4),
            "spread_pct": round(spread, 4), "ema20": round(ema20, 4), "ema50": round(ema50, 4),
        }
    except Exception as e:
        log.warning(f"[scan] {symbol}: {e}")
        return None


def scan_opportunities(watchlist: list[str], top_n: int = 3, category: str = "linear") -> list[dict]:
    results = []
    for sym in watchlist:
        r = score_opportunity(sym, category)
        if r:
            results.append(r)
            log.info(f"[scan] {sym:14s} regime={r['regime']:8s} score={r['score']:3d} {r['signals']}")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# LLM context builder
# ---------------------------------------------------------------------------

def load_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def build_user_message(opportunities: list[dict], balance: float,
                        open_position: dict | None, briefing: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")
    strategy_menu = {}
    for name, cfg in STRATEGY_REGISTRY.items():
        for r in cfg["regimes"]:
            strategy_menu.setdefault(r, []).append(name)

    parts = []
    if briefing:
        parts.append(f"## Agent Briefing\n{briefing[:600]}")
    parts.append(f"""## Account ({ts})
- balance_usdt: {round(balance, 2)}
- open_position: {json.dumps(open_position) if open_position else 'none'}
- env: {os.getenv('BYBIT_ENV', 'testnet')}
""")
    parts.append("## Strategy Menu (regime → eligible strategies)\n" + json.dumps(strategy_menu, indent=2))
    parts.append(f"## Top Opportunities ({len(opportunities)} symbols scanned from dynamic Bybit watchlist)")
    for i, o in enumerate(opportunities, 1):
        parts.append(f"""### #{i} {o['symbol']}  score={o['score']}/100
- regime={o['regime']}  rsi={o['rsi']}  zscore={o['zscore']}  atr={o['atr']}
- signals: {o['signals']}
- eligible_strategies: {o['strategies']}
- ema20={o['ema20']} ema50={o['ema50']}  funding={o['funding']}  vol_spike={o['vol_spike']}
- chg24h={o['chg24h']*100:.2f}%  spread={o['spread_pct']}%  price={o['price']}
""")
    parts.append("""## Decision
Emit ONE JSON:
{"action":"<open_long|open_short|close_position|reduce_size|hold|wait>",
 "strategy":"<from eligible_strategies>","side":"<buy|sell|none>",
 "symbol":"<symbol>","qty":<float>,"sl":<float>,"tp":<float>,
 "reason":"<max 15 words>"}
Rules: sl mandatory for open_long/open_short. If no edge, emit hold.""")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validation + execution
# ---------------------------------------------------------------------------

def validate_action(action: dict) -> bool:
    if action.get("action") not in ALLOWED_ACTIONS:
        log.error(f"BLOCKED unknown action: {action.get('action')}")
        return False
    strat = action.get("strategy", "none")
    if strat and strat != "none" and strat not in ALLOWED_STRATEGIES:
        log.warning(f"Unknown strategy '{strat}' — resetting to none")
        action["strategy"] = "none"
    if action["action"] in {"open_long", "open_short"} and not action.get("sl"):
        log.error("BLOCKED: missing sl")
        return False
    return True


def execute_action(action: dict, dry_run: bool = False) -> None:
    import subprocess
    if action["action"] in {"hold", "wait"}:
        log.info(f"Decision: {action['action']} — {action.get('reason', '')}")
        return
    if dry_run:
        log.info(f"[DRY-RUN] {json.dumps(action)}")
        _notify_telegram(action, success=True, dry_run=True)
        return
    cmd = [
        "python", "-m", "core.engine",
        "--action", action["action"],
        "--symbol", str(action.get("symbol", os.getenv("DEFAULT_SYMBOL", "BTCUSDT"))),
        "--qty",    str(action.get("qty", 0)),
        "--strategy", str(action.get("strategy", "none")),
    ]
    if action.get("sl"): cmd += ["--sl", str(action["sl"])]
    if action.get("tp"): cmd += ["--tp", str(action["tp"])]
    log.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(Path(__file__).parent.parent))
    ok = result.returncode == 0
    log.info(result.stdout.strip()) if ok else log.error(result.stderr.strip())
    _notify_telegram(action, success=ok)


def _notify_telegram(action: dict, success: bool, dry_run: bool = False) -> None:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        prefix = "🧪 DRY" if dry_run else ("✅" if success else "❌")
        text   = (
            f"{prefix} {action.get('action','?').upper()} {action.get('side','')} "
            f"{action.get('symbol','')} qty={action.get('qty','')}\n"
            f"Strat: {action.get('strategy','')} | {action.get('reason','')}"
        )
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning(f"Telegram: {e}")


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

WATCHLIST_REFRESH_TICKS = int(os.getenv("WATCHLIST_REFRESH_TICKS", "4"))  # refresh every 4 ticks
_tick_count = 0


def run_once(manual_watchlist: list[str] | None = None, dry_run: bool = False) -> dict:
    global _tick_count
    _tick_count += 1

    log.info(f"=== Tick #{_tick_count} | {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M UTC')} ===")

    # 1. Watchlist: dynamic from Bybit OR manual override
    if manual_watchlist:
        watchlist = manual_watchlist
        log.info(f"Using manual watchlist: {watchlist}")
    else:
        force_refresh = (_tick_count % WATCHLIST_REFRESH_TICKS == 1)
        watchlist = build_watchlist(force=force_refresh)
        log.info(f"Dynamic watchlist ({len(watchlist)} symbols): {watchlist}")

    # 2. Scan opportunities
    top_n = int(os.getenv("SCAN_TOP_N", "3"))
    opportunities = scan_opportunities(watchlist, top_n=top_n)
    if not opportunities:
        log.warning("No scoreable opportunities — holding")
        return {"action": "hold", "reason": "no_opportunities"}

    # 3. Account state
    balance       = get_balance()
    open_position = get_position(opportunities[0]["symbol"])

    # 4. Build LLM context
    briefing = load_text(BRIEFING_PATH)
    system   = load_text(SYSTEM_PROMPT_PATH) or "You are a trading decision agent. Output only valid JSON."
    user_msg = build_user_message(opportunities, balance, open_position, briefing)

    best = opportunities[0]
    log.info(f"Best: {best['symbol']} score={best['score']} regime={best['regime']} strategies={best['strategies']}")

    # 5. LLM call
    log.info(f"LLM call — provider={os.getenv('LLM_PROVIDER','groq')} model={os.getenv('LLM_MODEL','?')}")
    raw = chat_complete(system=system, user=user_msg)

    # 6. Parse
    action = parse_action(raw)
    if not action:
        log.error("LLM parse error — holding")
        return {"action": "hold", "reason": "parse_error"}
    log.info(f"LLM → {json.dumps(action)}")

    # 7. Validate
    if not validate_action(action):
        return {"action": "hold", "reason": "validation_blocked"}

    # 8. Execute
    execute_action(action, dry_run=dry_run)
    return action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",     action="store_true")
    parser.add_argument("--interval", type=int, default=900)
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--symbols",  type=str, default="",
                        help="Comma-separated manual watchlist override")
    args = parser.parse_args()

    manual = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    if args.dry_run:
        log.info("DRY-RUN — no real orders")

    if args.once:
        run_once(manual_watchlist=manual, dry_run=args.dry_run)
        return

    log.info(f"Loop every {args.interval}s (watchlist refresh every {WATCHLIST_REFRESH_TICKS} ticks)")
    while True:
        try:
            run_once(manual_watchlist=manual, dry_run=args.dry_run)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error(f"Loop error: {e}")
        log.info(f"Sleeping {args.interval}s")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
