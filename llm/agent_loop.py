"""LLM Agent Loop v4

Workflow per tick:
  1. comms.poll_commands()      → process Telegram commands (/pause /status etc)
  2. collect_for_agent()        → parallel data collection (all symbols in one shot)
  3. scan_opportunities()       → score using pre-collected indicators (no extra API)
  4. top N to LLM               → with regime, eligible strategies, orderbook, pnl
  5. validate + execute         → in-process enter()/close_position()
  6. comms.send_tick_summary()  → Telegram summary after every decision

Usage:
    python llm/agent_loop.py --once
    python llm/agent_loop.py --interval 900
    python llm/agent_loop.py --dry-run --once
    python llm/agent_loop.py --symbols BTCUSDT,ETHUSDT
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import statistics as _stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.providers import chat_complete, parse_action
from llm.watchlist import build_watchlist, warm_cache
from llm.comms import TelegramComms, AgentCommand
from core.engine import (
    closes, highs, lows, volumes,
    rsi, atr, ema, zscore,
    enter, close_position, cli,
    SYMBOL, CATEGORY, LEVERAGE, CAP_USD,
    log_info, log_error,
)
from core.collector import collect_for_agent, AgentContext

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
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    "trend_follow":         {"regimes": ["bull", "bear"],             "type": "trend"},
    "mean_reversion":       {"regimes": ["sideways"],                 "type": "mean_revert"},
    "grid_trading":         {"regimes": ["sideways"],                 "type": "grid"},
    "scalping":             {"regimes": ["bull", "bear", "sideways"], "type": "scalp"},
    "breakout":             {"regimes": ["volatile", "bull", "bear"], "type": "breakout"},
    "funding_arb":          {"regimes": ["bull", "bear", "sideways", "volatile"], "type": "arb"},
    "kalman_filter":        {"regimes": ["bull", "bear"],             "type": "trend"},
    "bollinger_bands":      {"regimes": ["sideways"],                 "type": "mean_revert"},
    "macd_signal":          {"regimes": ["bull", "bear"],             "type": "trend"},
    "rsi_divergence":       {"regimes": ["sideways", "bull", "bear"], "type": "reversal"},
    "stochastic_rsi":       {"regimes": ["sideways"],                 "type": "oscillator"},
    "adx_trend_filter":     {"regimes": ["bull", "bear"],             "type": "trend"},
    "supertrend":           {"regimes": ["bull", "bear"],             "type": "trend"},
    "ichimoku_cloud":       {"regimes": ["bull", "bear"],             "type": "trend"},
    "heikin_ashi_trend":    {"regimes": ["bull", "bear"],             "type": "trend"},
    "parabolic_sar":        {"regimes": ["bull", "bear"],             "type": "trend"},
    "triple_ema":           {"regimes": ["bull", "bear"],             "type": "trend"},
    "turtle_trading":       {"regimes": ["bull", "bear", "volatile"], "type": "breakout"},
    "vwap_reversion":       {"regimes": ["sideways"],                 "type": "mean_revert"},
    "williams_r":           {"regimes": ["sideways", "bull", "bear"], "type": "oscillator"},
    "cci_reversal":         {"regimes": ["sideways"],                 "type": "reversal"},
    "momentum_roc":         {"regimes": ["bull", "bear"],             "type": "momentum"},
    "volatility_targeting": {"regimes": ["bull", "bear", "sideways", "volatile"], "type": "risk"},
    "market_making":        {"regimes": ["sideways"],                 "type": "mm"},
    "dca_accumulation":     {"regimes": ["sideways", "bull"],         "type": "dca"},
    "multi_timeframe":      {"regimes": ["bull", "bear"],             "type": "confluence"},
    "pairs_trading":        {"regimes": ["sideways", "volatile"],     "type": "stat_arb"},
    "open_interest_spike":  {"regimes": ["volatile", "bull", "bear"], "type": "flow"},
    "liquidation_hunt":     {"regimes": ["volatile"],                 "type": "flow"},
}

ALLOWED_STRATEGIES = set(STRATEGY_REGISTRY.keys())
ALLOWED_ACTIONS    = {"open_long", "open_short", "close_position", "reduce_size", "hold", "wait"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "SYSTEM_PROMPT.md"
BRIEFING_PATH      = Path(__file__).parent.parent / "agent" / "AGENT_BRIEFING.md"

# ---------------------------------------------------------------------------
# Global agent state — thread-safe via _state_lock (#7)
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_state = {
    "paused":    False,
    "dry_run":   os.getenv("DRY_RUN", "false").lower() == "true",
    "force_sym": None,
    "stop":      False,
}


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def _get_state(key: str, default=None):
    with _state_lock:
        return _state.get(key, default)


# ---------------------------------------------------------------------------
# Regime detection (uses pre-collected candles from ctx)
# ---------------------------------------------------------------------------

TREND_THRESH = float(os.getenv("TREND_THRESH",    "0.003"))
VOL_HIGH     = float(os.getenv("VOL_THRESH_HIGH", "0.02"))
VOL_LOW      = float(os.getenv("VOL_THRESH_LOW",  "0.008"))


def detect_regime_local(
    symbol: str,
    ctx: AgentContext,
) -> tuple[str, dict]:
    """Detect regime using pre-collected candles from AgentContext (zero extra API calls)."""
    candles = ctx.klines.get(symbol, [])
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
        "atr_pct": round(atr_pct, 5), "vol_ratio": round(vol_ratio, 2), "price": price,
    }


def eligible_strategies(regime: str) -> list[str]:
    return [n for n, cfg in STRATEGY_REGISTRY.items() if regime in cfg["regimes"]]


# ---------------------------------------------------------------------------
# Opportunity scanner  (uses AgentContext — no extra API calls)
# ---------------------------------------------------------------------------

def score_opportunity(symbol: str, ctx: AgentContext) -> dict | None:
    """Score a symbol using pre-collected data from AgentContext."""
    try:
        candles = ctx.klines.get(symbol, [])
        if len(candles) < 20:
            return None
        ticker  = ctx.ticker.get(symbol, {})
        ind     = ctx.indicators.get(symbol, {})
        price   = ctx.price(symbol)
        rsi_val = ind.get("rsi") or rsi(closes(candles))
        atr_val = ind.get("atr") or atr(candles)
        zs      = ind.get("zscore") or 0.0
        ema20   = ind.get("ema20") or price
        ema50   = ind.get("ema50") or price
        funding = float(ticker.get("fundingRate", 0))
        chg24h  = float(ticker.get("price24hPcnt", 0))
        spread  = ctx.spread_pct(symbol)
        vols    = volumes(candles)
        vol_avg = sum(vols[-20:]) / 20
        vol_spike = vols[-1] / vol_avg if vol_avg > 0 else 1

        regime, rstats = detect_regime_local(symbol, ctx)
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
            "orderbook":  ctx.orderbook.get(symbol, {}),
        }
    except Exception as e:
        log.warning(f"[scan] {symbol}: {e}")
        return None


def scan_opportunities(
    watchlist: list[str],
    ctx: AgentContext,
    top_n: int = 3,
) -> list[dict]:
    results = []
    for sym in watchlist:
        r = score_opportunity(sym, ctx)
        if r:
            results.append(r)
            log.info(
                f"[scan] {sym:14s} regime={r['regime']:8s} "
                f"score={r['score']:3d} {r['signals']}"
            )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# LLM context builder
# ---------------------------------------------------------------------------

def load_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def build_user_message(
    opportunities: list[dict],
    ctx: AgentContext,
    briefing: str,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")
    strategy_menu: dict[str, list[str]] = {}
    for name, cfg in STRATEGY_REGISTRY.items():
        for r in cfg["regimes"]:
            strategy_menu.setdefault(r, []).append(name)

    pos = ctx.open_positions[0] if ctx.open_positions else None

    parts: list[str] = []
    if briefing:
        parts.append(f"## Briefing\n{briefing[:600]}")

    parts.append(
        f"## Account ({ts})\n"
        f"- balance_usdt: {round(ctx.balance, 2)}\n"
        f"- free_margin: {round(ctx.free_margin, 2)}\n"
        f"- today_pnl: {ctx.today_pnl:+.4f} USDT ({ctx.today_pnl_pct:+.4f}%)\n"
        f"- open_position: {json.dumps(pos) if pos else 'none'}\n"
        f"- open_orders: {len(ctx.open_orders)}\n"
        f"- env: {os.getenv('BYBIT_ENV', 'testnet')}"
    )
    parts.append("## Strategy Menu (regime → eligible)\n" + json.dumps(strategy_menu, indent=2))
    parts.append(f"## Top Opportunities ({len(opportunities)} of dynamic Bybit watchlist)")

    for i, o in enumerate(opportunities, 1):
        ob = o.get("orderbook", {})
        parts.append(
            f"### #{i} {o['symbol']}  score={o['score']}/100\n"
            f"- regime={o['regime']}  rsi={o['rsi']}  zscore={o['zscore']}  atr={o['atr']}\n"
            f"- signals: {o['signals']}\n"
            f"- eligible_strategies: {o['strategies']}\n"
            f"- ema20={o['ema20']} ema50={o['ema50']}  funding={o['funding']}  "
            f"vol_spike={o['vol_spike']}\n"
            f"- chg24h={o['chg24h']*100:.2f}%  spread={o['spread_pct']}%  price={o['price']}\n"
            f"- orderbook: bid={ob.get('bid')} ask={ob.get('ask')} "
            f"bid_size={ob.get('bid_size')} ask_size={ob.get('ask_size')}"
        )

    parts.append(
        '## Decision\nEmit ONE JSON:\n'
        '{"action":"<open_long|open_short|close_position|reduce_size|hold|wait>",\n'
        ' "strategy":"<from eligible_strategies>","side":"<buy|sell|none>",\n'
        ' "symbol":"<symbol>","qty":<float>,"sl":<float>,"tp":<float>,\n'
        ' "reason":"<max 15 words>"}\n'
        'Rules: sl mandatory for open_long/open_short. No edge → hold.'
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validate + execute
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
        log.error("BLOCKED: open order missing sl")
        return False
    return True


def _reduce_position(
    symbol: str,
    category: str = "linear",
    reduce_pct: float = 0.5,
    ctx: AgentContext | None = None,
) -> dict:
    pos = ctx.position_for(symbol) if ctx else None
    if not pos:
        from core.engine import get_position
        pos = get_position(symbol, category)
    if not pos:
        return {"retCode": 0, "retMsg": "no_position"}
    full_size  = float(pos.get("size", 0))
    reduce_qty = round(full_size * reduce_pct, 3)
    if reduce_qty <= 0:
        return {"retCode": 0, "retMsg": "qty_zero"}
    close_side = "Sell" if pos["side"] == "Buy" else "Buy"
    return cli(
        "order", "create",
        "--category", category, "--symbol", symbol,
        "--side", close_side, "--orderType", "Market",
        "--timeInForce", "IOC",
        "--qty", str(reduce_qty), "--reduceOnly", "true",
        "--cap-usd", CAP_USD, "--yes",
    )


def execute_action(action: dict, dry_run: bool = False,
                   ctx: AgentContext | None = None) -> None:
    from core.order_utils import choose_order_type

    act    = action["action"]
    symbol = str(action.get("symbol", os.getenv("DEFAULT_SYMBOL", SYMBOL)))
    cat    = os.getenv("CATEGORY", CATEGORY)

    if act in {"hold", "wait"}:
        log.info(f"Decision: {act} — {action.get('reason', '')}")
        return

    if dry_run:
        log.info(f"[DRY-RUN] {json.dumps(action)}")
        return

    try:
        if act in {"open_long", "open_short"}:
            side = "Buy" if act == "open_long" else "Sell"
            spread = ctx.spread_pct(symbol) if ctx else 0.05
            otype, tif = choose_order_type(
                spread,
                urgency=False,
                strategy_hint=str(action.get("strategy", "")),
            )
            limit_px = None
            if otype == "Limit" and ctx:
                ob = ctx.orderbook.get(symbol, {})
                limit_px = float(ob.get("bid") or 0) if side == "Buy" \
                           else float(ob.get("ask") or 0)
                if not limit_px:
                    ticker = ctx.ticker.get(symbol, {})
                    limit_px = float(ticker.get("bid1Price" if side == "Buy" else "ask1Price", 0)) or None

            result = enter(
                side=side,
                qty=float(action.get("qty", 0)),
                stop_loss=float(action["sl"]),
                take_profit=float(action["tp"]) if action.get("tp") else None,
                reason=str(action.get("strategy", "")),
                order_type=otype,
                time_in_force=tif,
                limit_price=limit_px,
            )
        elif act == "close_position":
            result = close_position()
        elif act == "reduce_size":
            result = _reduce_position(symbol, cat, reduce_pct=0.5, ctx=ctx)
        else:
            log.error(f"Unhandled action: {act}")
            return

        ok = result.get("retCode", -1) == 0 if result else False
        if ok:
            log.info(f"Execute OK: {json.dumps(result)}")
        else:
            log.error(f"Execute failed: {json.dumps(result)}")
    except Exception as e:
        log.error(f"execute_action exception: {e}")


# ---------------------------------------------------------------------------
# Telegram command handler
# ---------------------------------------------------------------------------

def handle_command(
    cmd: AgentCommand,
    comms: TelegramComms,
    ctx: AgentContext,
    watchlist: list[str],
) -> None:
    c = cmd.cmd

    if c == "status":
        msg = comms.build_status_message(
            ctx.balance, ctx.free_margin, ctx.today_pnl,
            ctx.open_positions, ctx.open_orders,
        )
        comms.reply(cmd, msg)

    elif c == "pnl":
        comms.reply(cmd, f"PnL today: `{ctx.today_pnl:+.4f}` USDT "
                        f"({ctx.today_pnl_pct:+.4f}%)")

    elif c == "pause":
        _set_state(paused=True)
        comms.reply(cmd, "⏸ Trading *paused* — all decisions will be HOLD.")
        log.info("[comms] Agent paused via Telegram")

    elif c == "resume":
        _set_state(paused=False)
        comms.reply(cmd, "▶️ Trading *resumed*.")
        log.info("[comms] Agent resumed via Telegram")

    elif c == "dry":
        val = (cmd.args[0].lower() != "off") if cmd.args else True
        _set_state(dry_run=val)
        comms.reply(cmd, f"🧪 Dry-run: *{'ON' if val else 'OFF'}*")

    elif c == "watchlist":
        comms.reply(cmd, f"Watchlist: `{watchlist}`")

    elif c == "force":
        sym = cmd.args[0].upper() if cmd.args else ""
        if sym:
            _set_state(force_sym=sym)
            comms.reply(cmd, f"Next tick will force scan `{sym}`")
        else:
            comms.reply(cmd, "Usage: /force SYMBOL")

    elif c == "stop":
        comms.reply(cmd, "🛑 Stopping agent after this tick...")
        log.info("[comms] Stop requested via Telegram")
        _set_state(stop=True)

    elif c == "help":
        comms.reply(cmd,
            "🤖 *Commands*\n"
            "`/status` — account snapshot\n"
            "`/pnl` — today PnL\n"
            "`/pause` / `/resume` — toggle trading\n"
            "`/dry [on|off]` — toggle dry-run\n"
            "`/watchlist` — current symbols\n"
            "`/force SYMBOL` — force scan\n"
            "`/stop` — graceful shutdown"
        )


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

def run_once(
    manual_watchlist: list[str] | None = None,
    dry_run: bool = False,
    comms: TelegramComms | None = None,
) -> dict:
    t0 = time.time()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    log.info(f"=== Tick | {ts} ===")

    # 0. Process Telegram commands
    if comms:
        for cmd in comms.poll_commands():
            log.info(f"[comms] cmd=/{cmd.cmd} args={cmd.args} from={cmd.user}")
            if cmd.cmd in {"pause", "resume", "dry", "stop", "force", "help"}:
                handle_command(cmd, comms, AgentContext(), [])

    # 1. Watchlist
    if manual_watchlist:
        watchlist = manual_watchlist
    else:
        watchlist = build_watchlist()
        if _get_state("force_sym"):
            sym = None
            with _state_lock:
                sym = _state.pop("force_sym", None)
            if sym and sym not in watchlist:
                watchlist = [sym] + watchlist
                log.info(f"[comms] Forced {sym} into watchlist")
    log.info(f"Watchlist ({len(watchlist)}): {watchlist}")

    # Pause gate
    if _get_state("paused"):
        log.info("[state] Paused — skipping tick")
        return {"action": "hold", "reason": "paused"}

    # 2. Collect ALL data in parallel
    ctx = collect_for_agent(watchlist)
    log.info(f"[collector] {ctx.to_summary().splitlines()[0]} | fetch={ctx.fetch_ms}ms")
    if ctx.errors:
        log.warning(f"[collector] errors: {ctx.errors}")

    # 2b. Now handle commands that need ctx (/status, /pnl, /watchlist)
    if comms:
        for cmd in comms.poll_commands():
            handle_command(cmd, comms, ctx, watchlist)

    # 3. Scan
    top_n = int(os.getenv("SCAN_TOP_N", "3"))
    opps  = scan_opportunities(watchlist, ctx, top_n=top_n)
    if not opps:
        log.warning("No scoreable opportunities — holding")
        return {"action": "hold", "reason": "no_opportunities"}

    best = opps[0]
    log.info(f"Best: {best['symbol']} score={best['score']} "
             f"regime={best['regime']} strats={best['strategies']}")

    # 4. Build LLM context
    briefing = load_text(BRIEFING_PATH)
    system   = load_text(SYSTEM_PROMPT_PATH) or "Output only valid JSON."
    user_msg = build_user_message(opps, ctx, briefing)

    # 5. LLM
    effective_dry = dry_run or _get_state("dry_run")
    log.info(f"LLM → provider={os.getenv('LLM_PROVIDER','groq')} dry={effective_dry}")
    raw    = chat_complete(system=system, user=user_msg)
    action = parse_action(raw)
    if not action:
        log.error("Parse error — holding")
        return {"action": "hold", "reason": "parse_error"}
    log.info(f"LLM → {json.dumps(action)}")

    # 6. Validate + execute
    if not validate_action(action):
        return {"action": "hold", "reason": "validation_blocked"}
    execute_action(action, dry_run=effective_dry, ctx=ctx)

    # 7. Tick summary to Telegram
    if comms:
        comms.send_tick_summary(
            balance=ctx.balance,
            free_margin=ctx.free_margin,
            today_pnl=ctx.today_pnl,
            action=action,
            regime=best["regime"],
            symbol=best["symbol"],
            fetch_ms=ctx.fetch_ms,
        )

    log.info(f"Tick done in {time.time()-t0:.2f}s")
    return action


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",     action="store_true")
    parser.add_argument("--interval", type=int, default=900)
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--symbols",  type=str, default="")
    args = parser.parse_args()

    manual  = [s.strip() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
    dry_run = args.dry_run or _get_state("dry_run")
    comms   = TelegramComms()

    if dry_run:
        log.info("DRY-RUN — no real orders")

    # Warm watchlist cache
    if not manual:
        log.info("Warming watchlist cache ...")
        import llm.watchlist as _wl_mod
        _ready = threading.Event()
        _real_update = _wl_mod._cache.update

        def _patched_update(symbols, detail):
            _real_update(symbols, detail)
            _ready.set()

        _wl_mod._cache.update = _patched_update
        warm_cache()
        _ready.wait(timeout=5)
        _wl_mod._cache.update = _real_update
        log.info("Cache ready")

    if args.once:
        run_once(manual_watchlist=manual, dry_run=dry_run, comms=comms)
        return

    log.info(f"Loop every {args.interval}s")
    while True:
        try:
            run_once(manual_watchlist=manual, dry_run=dry_run, comms=comms)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error(f"Loop error: {e}")
        if _get_state("stop"):
            log.info("Stop requested — exiting.")
            comms.send("🛑 Agent stopped.")
            break
        log.info(f"Sleeping {args.interval}s")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
