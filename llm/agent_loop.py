"""LLM Agent Loop — multi-symbol scan, regime detection, strategy filtering.

Workflow per tick:
  1. Scan WATCHLIST symbols → collect snapshots
  2. Run regime_detection per symbol → filter eligible strategies
  3. Score opportunities (RSI extremes, vol spike, funding, spread)
  4. Pick best symbol+strategy combo
  5. Ask LLM with full context (regime, strategies, snapshot)
  6. Validate JSON action (whitelist)
  7. Execute via core/engine.py
  8. Telegram notify

Usage:
    python llm/agent_loop.py --once
    python llm/agent_loop.py --interval 900
    python llm/agent_loop.py --dry-run --once
    python llm/agent_loop.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --once
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
# Watchlist & strategy registry
# ---------------------------------------------------------------------------

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "AVAXUSDT", "ADAUSDT", "LINKUSDT", "DOTUSDT",
]

# All 26 strategies mapped to their regime(s) and type
STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    "trend_follow":         {"regimes": ["bull", "bear"],              "type": "trend"},
    "mean_reversion":       {"regimes": ["sideways"],                  "type": "mean_revert"},
    "grid_trading":         {"regimes": ["sideways"],                  "type": "grid"},
    "scalping":             {"regimes": ["bull", "bear", "sideways"],  "type": "scalp"},
    "breakout":             {"regimes": ["volatile", "bull", "bear"],  "type": "breakout"},
    "funding_arb":          {"regimes": ["bull", "bear", "sideways", "volatile"], "type": "arb"},
    "kalman_filter":        {"regimes": ["bull", "bear"],              "type": "trend"},
    "regime_detection":     {"regimes": [],                            "type": "meta"},  # internal only
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

# Strategies the LLM is allowed to pick (all except internal meta)
ALLOWED_STRATEGIES = {k for k, v in STRATEGY_REGISTRY.items() if v["type"] != "meta"}

# Actions the LLM is allowed to emit
ALLOWED_ACTIONS = {"open_long", "open_short", "close_position", "reduce_size", "hold", "wait"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "SYSTEM_PROMPT.md"
BRIEFING_PATH      = Path(__file__).parent.parent / "agent" / "AGENT_BRIEFING.md"

# ---------------------------------------------------------------------------
# Regime detection (local, fast — no subprocess)
# ---------------------------------------------------------------------------

import statistics as _stats

TREND_THRESH   = float(os.getenv("TREND_THRESH",    "0.003"))
VOL_HIGH       = float(os.getenv("VOL_THRESH_HIGH", "0.02"))
VOL_LOW        = float(os.getenv("VOL_THRESH_LOW",  "0.008"))


def detect_regime_local(symbol: str, category: str = "linear") -> tuple[str, dict]:
    """Fast inline regime detection — no subprocess, no kill-switch side effects."""
    candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
    if len(candles) < 20:
        return "unknown", {}

    c   = closes(candles)
    ret = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
    mean_ret  = _stats.mean(ret[-50:])
    vol       = _stats.stdev(ret[-50:])
    rsi_val   = rsi(c)
    atr_val   = atr(candles)
    price     = c[-1]
    atr_pct   = atr_val / price if price else 0

    vols      = volumes(candles)
    vol_avg   = sum(vols[-20:]) / 20
    vol_ratio = vols[-1] / vol_avg if vol_avg > 0 else 1

    # Classify regime
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

    stats = {
        "regime":     regime,
        "mean_ret":   round(mean_ret, 6),
        "volatility": round(vol, 6),
        "rsi":        round(rsi_val, 2),
        "atr_pct":    round(atr_pct, 5),
        "vol_ratio":  round(vol_ratio, 2),
        "price":      price,
    }
    return regime, stats


def eligible_strategies(regime: str) -> list[str]:
    """Return strategies valid for this regime, sorted by type priority."""
    return [
        name for name, cfg in STRATEGY_REGISTRY.items()
        if regime in cfg["regimes"]
    ]


# ---------------------------------------------------------------------------
# Multi-symbol opportunity scanner
# ---------------------------------------------------------------------------

def score_opportunity(symbol: str, category: str = "linear") -> dict | None:
    """Score a symbol for trading opportunity. Returns None on fetch error."""
    try:
        candles = get_klines(interval="60", limit=100, symbol=symbol, category=category)
        if len(candles) < 20:
            return None
        ticker  = get_ticker(symbol, category)
        c       = closes(candles)
        price   = c[-1]

        rsi_val    = rsi(c)
        atr_val    = atr(candles)
        zs         = zscore(c) if len(c) >= 50 else 0.0
        ema20      = ema(c, 20)
        ema50      = ema(c, 50) if len(c) >= 50 else ema20
        funding    = float(ticker.get("fundingRate", 0))
        vol24h     = float(ticker.get("volume24h", 0))
        chg24h     = float(ticker.get("price24hPcnt", 0))
        bid        = float(ticker.get("bid1Price", price))
        ask        = float(ticker.get("ask1Price", price))
        spread_pct = (ask - bid) / price * 100 if price else 0

        vols     = volumes(candles)
        vol_avg  = sum(vols[-20:]) / 20
        vol_spike = vols[-1] / vol_avg if vol_avg > 0 else 1

        regime, regime_stats = detect_regime_local(symbol, category)
        strategies = eligible_strategies(regime)

        # Opportunity score (0–100)
        score = 0
        signals = []

        # RSI extremes → mean-reversion opportunity
        if rsi_val < 30:
            score += 25; signals.append(f"RSI oversold ({rsi_val:.0f})")
        elif rsi_val > 70:
            score += 25; signals.append(f"RSI overbought ({rsi_val:.0f})")

        # Z-score extremes → mean reversion
        if abs(zs) > 2.0:
            score += 20; signals.append(f"zscore={zs:.2f}")

        # Volume spike → breakout / momentum
        if vol_spike > 2.0:
            score += 20; signals.append(f"vol_spike x{vol_spike:.1f}")

        # Strong 24h move → trend opportunity
        if abs(chg24h) > 0.03:
            score += 15; signals.append(f"24h_chg={chg24h*100:.1f}%")

        # High funding (positive or negative) → funding arb
        if abs(funding) > 0.0005:
            score += 10; signals.append(f"funding={funding*100:.4f}%")

        # Tight spread → good execution
        if spread_pct < 0.05:
            score += 10; signals.append("tight_spread")

        return {
            "symbol":      symbol,
            "score":       score,
            "signals":     signals,
            "regime":      regime,
            "regime_stats": regime_stats,
            "strategies":  strategies,
            "price":       price,
            "rsi":         round(rsi_val, 2),
            "zscore":      round(zs, 3),
            "atr":         round(atr_val, 4),
            "funding":     funding,
            "vol_spike":   round(vol_spike, 2),
            "chg24h":      round(chg24h, 4),
            "spread_pct":  round(spread_pct, 4),
            "ema20":       round(ema20, 4),
            "ema50":       round(ema50, 4),
        }
    except Exception as e:
        log.warning(f"[scan] {symbol} error: {e}")
        return None


def scan_opportunities(watchlist: list[str], top_n: int = 3, category: str = "linear") -> list[dict]:
    """Scan all symbols, return top_n by opportunity score."""
    results = []
    for sym in watchlist:
        result = score_opportunity(sym, category)
        if result:
            results.append(result)
            log.info(f"[scan] {sym:12s} regime={result['regime']:8s} score={result['score']:3d} signals={result['signals']}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# LLM context builder
# ---------------------------------------------------------------------------

def load_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def build_user_message(
    opportunities: list[dict],
    balance: float,
    open_position: dict | None,
    briefing: str,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")

    # Strategy menu by regime
    strategy_menu = {}
    for name, cfg in STRATEGY_REGISTRY.items():
        if cfg["type"] == "meta":
            continue
        for r in cfg["regimes"]:
            strategy_menu.setdefault(r, []).append(name)

    parts = []

    if briefing:
        parts.append(f"## Agent Briefing (summary)\n{briefing[:800]}")

    parts.append(f"""## Account State ({ts})
- balance_usdt: {round(balance, 2)}
- open_position: {json.dumps(open_position) if open_position else 'none'}
- max_risk_pct: {os.getenv('MAX_RISK_PCT', '0.01')}
- env: {os.getenv('BYBIT_ENV', 'testnet')}
""")

    parts.append("""## Strategy Menu (regime → valid strategies)
""" + json.dumps(strategy_menu, indent=2))

    parts.append(f"## Top Opportunities Scanned ({len(opportunities)} symbols)")
    for i, opp in enumerate(opportunities, 1):
        parts.append(f"""
### Opportunity #{i}: {opp['symbol']}  (score={opp['score']}/100)
- regime: {opp['regime']}
- regime_stats: {json.dumps(opp['regime_stats'])}
- signals: {opp['signals']}
- eligible_strategies: {opp['strategies']}
- price: {opp['price']}
- rsi: {opp['rsi']}  zscore: {opp['zscore']}  atr: {opp['atr']}
- funding: {opp['funding']}  vol_spike: {opp['vol_spike']}  chg24h: {opp['chg24h']*100:.2f}%
- ema20: {opp['ema20']}  ema50: {opp['ema50']}
""")

    parts.append("""## Your Task
Choose the best opportunity and emit ONE JSON action:
{
  "action": "<open_long|open_short|close_position|reduce_size|hold|wait>",
  "strategy": "<strategy_name from eligible_strategies above>",
  "side": "<buy|sell|none>",
  "symbol": "<symbol>",
  "qty": <float>,
  "sl": <float>,
  "tp": <float>,
  "reason": "<max 15 words>"
}
Rules: action+strategy MUST be from whitelist. sl mandatory for open_long/open_short.
If no clear opportunity, emit hold.
""")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_action(action: dict) -> bool:
    if action.get("action") not in ALLOWED_ACTIONS:
        log.error(f"BLOCKED: unknown action '{action.get('action')}'")
        return False
    strat = action.get("strategy", "none")
    if strat and strat != "none" and strat not in ALLOWED_STRATEGIES:
        log.warning(f"Unknown strategy '{strat}' — setting to none")
        action["strategy"] = "none"
    if action["action"] in {"open_long", "open_short"} and not action.get("sl"):
        log.error("BLOCKED: open action missing sl")
        return False
    return True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

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
        "--action",   action["action"],
        "--symbol",   str(action.get("symbol", os.getenv("DEFAULT_SYMBOL", "BTCUSDT"))),
        "--qty",      str(action.get("qty", 0)),
        "--strategy", str(action.get("strategy", "none")),
    ]
    if action.get("sl"): cmd += ["--sl", str(action["sl"])]
    if action.get("tp"): cmd += ["--tp", str(action["tp"])]

    log.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent)
    )
    ok = result.returncode == 0
    if ok:
        log.info(f"Engine: {result.stdout.strip()}")
    else:
        log.error(f"Engine error: {result.stderr.strip()}")
    _notify_telegram(action, success=ok)


def _notify_telegram(action: dict, success: bool, dry_run: bool = False) -> None:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        prefix = "🧪 DRY-RUN" if dry_run else ("✅" if success else "❌")
        text = (
            f"{prefix} {action.get('action','?').upper()} {action.get('side','')} "
            f"{action.get('symbol','')} qty={action.get('qty','')}\n"
            f"Strategy: {action.get('strategy','')} | {action.get('reason','')}"
        )
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning(f"Telegram failed: {e}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once(watchlist: list[str], dry_run: bool = False) -> dict:
    log.info(f"=== Agent tick | {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M UTC')} ===")
    log.info(f"Scanning {len(watchlist)} symbols: {watchlist}")

    # 1. Scan opportunities
    opportunities = scan_opportunities(watchlist, top_n=int(os.getenv("SCAN_TOP_N", "3")))
    if not opportunities:
        log.warning("No opportunities found — holding")
        return {"action": "hold", "reason": "no_opportunities"}

    # 2. Account state
    balance       = get_balance()
    primary_sym   = opportunities[0]["symbol"]
    open_position = get_position(primary_sym)

    # 3. Build LLM context
    briefing = load_text(BRIEFING_PATH)
    system   = load_text(SYSTEM_PROMPT_PATH) or "You are a trading decision agent. Output only valid JSON."
    user_msg = build_user_message(opportunities, balance, open_position, briefing)

    log.info(f"Top opportunity: {primary_sym} score={opportunities[0]['score']} "
             f"regime={opportunities[0]['regime']} strategies={opportunities[0]['strategies']}")

    # 4. Ask LLM
    provider = os.getenv("LLM_PROVIDER", "groq")
    model    = os.getenv("LLM_MODEL", "default")
    log.info(f"Calling LLM provider={provider} model={model} ...")
    raw = chat_complete(system=system, user=user_msg)
    log.debug(f"LLM raw: {raw}")

    # 5. Parse
    action = parse_action(raw)
    if not action:
        log.error("LLM returned unparseable JSON — holding")
        return {"action": "hold", "reason": "parse_error"}

    log.info(f"LLM action: {json.dumps(action)}")

    # 6. Validate
    if not validate_action(action):
        return {"action": "hold", "reason": "validation_blocked"}

    # 7. Execute
    execute_action(action, dry_run=dry_run)
    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Agent Loop — multi-symbol, regime-aware")
    parser.add_argument("--once",     action="store_true",  help="Single tick then exit")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval seconds (default 900)")
    parser.add_argument("--dry-run",  action="store_true",  help="No orders, log + Telegram only")
    parser.add_argument("--symbols",  type=str, default="",  help="Comma-separated symbol override")
    args = parser.parse_args()

    raw_list = os.getenv("WATCHLIST", ",".join(DEFAULT_WATCHLIST))
    watchlist = [s.strip() for s in (args.symbols or raw_list).split(",") if s.strip()]

    if args.dry_run:
        log.info("DRY-RUN mode — no real orders.")
    log.info(f"Watchlist: {watchlist}")

    if args.once:
        run_once(watchlist, dry_run=args.dry_run)
        return

    log.info(f"Starting loop every {args.interval}s ...")
    while True:
        try:
            run_once(watchlist, dry_run=args.dry_run)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error(f"Loop error: {e}")
        log.info(f"Sleeping {args.interval}s ...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
