"""LLM Agent Loop — reads market snapshot, asks LLM, routes to engine/CLI.

Usage:
    python llm/agent_loop.py --once          # single decision
    python llm/agent_loop.py --interval 900  # every 15 min
    python llm/agent_loop.py --dry-run       # no orders, log only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.providers import chat_complete, parse_action

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "llm_agent.log"),
    ],
)
log = logging.getLogger("llm_agent")

# ---------------------------------------------------------------------------
# Whitelisted actions the LLM is allowed to emit
# ---------------------------------------------------------------------------
ALLOWED_ACTIONS = {"open_long", "open_short", "close_position", "reduce_size", "hold", "wait"}
ALLOWED_STRATEGIES = {"scalp", "trend", "mean_revert", "grid", "none"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "SYSTEM_PROMPT.md"
BRIEFING_PATH = Path(__file__).parent.parent / "agent" / "AGENT_BRIEFING.md"


def load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text()
    return "You are a trading decision agent. Output only valid JSON."


def load_briefing() -> str:
    if BRIEFING_PATH.exists():
        return BRIEFING_PATH.read_text()
    return ""


def get_market_snapshot() -> str:
    """Call bybit-cli (or a thin wrapper) to get current market state as text."""
    try:
        result = subprocess.run(
            ["python", "-m", "core.engine", "--snapshot", "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).parent.parent),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        log.warning(f"Snapshot via engine failed: {e}")

    # Fallback — minimal placeholder so LLM can still reason
    return json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "snapshot unavailable — engine did not return data",
        "action_required": "hold",
    })


def build_user_message(snapshot: str, briefing: str) -> str:
    parts = []
    if briefing:
        parts.append(f"## Agent Briefing\n{briefing}")
    parts.append(f"## Market Snapshot (UTC {datetime.now(timezone.utc).strftime('%H:%M')})\n{snapshot}")
    parts.append(
        "Based on the above, emit a single JSON action with keys: "
        "action, strategy, side, symbol, qty, sl, tp, reason."
    )
    return "\n\n".join(parts)


def validate_action(action: dict) -> bool:
    """Hard whitelist check — rejects anything outside allowed actions."""
    if action.get("action") not in ALLOWED_ACTIONS:
        log.error(f"LLM emitted unknown action: {action.get('action')} — BLOCKED")
        return False
    if action.get("strategy") and action["strategy"] not in ALLOWED_STRATEGIES:
        log.warning(f"Unknown strategy '{action['strategy']}' — defaulting to none")
        action["strategy"] = "none"
    return True


def execute_action(action: dict, dry_run: bool = False) -> None:
    """Route validated action to core/engine or bybit-cli."""
    if action["action"] in {"hold", "wait"}:
        log.info(f"LLM decided to {action['action']}. Reason: {action.get('reason', '')}")
        return

    if dry_run:
        log.info(f"[DRY-RUN] Would execute: {json.dumps(action)}")
        return

    # Build engine call
    cmd = [
        "python", "-m", "core.engine",
        "--action", action["action"],
        "--symbol", str(action.get("symbol", os.getenv("DEFAULT_SYMBOL", "BTCUSDT"))),
        "--qty", str(action.get("qty", 0)),
        "--strategy", str(action.get("strategy", "none")),
    ]
    if action.get("sl"):
        cmd += ["--sl", str(action["sl"])]
    if action.get("tp"):
        cmd += ["--tp", str(action["tp"])]

    log.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(Path(__file__).parent.parent))
    if result.returncode != 0:
        log.error(f"Engine error: {result.stderr}")
    else:
        log.info(f"Engine output: {result.stdout.strip()}")

    # Telegram notification (optional)
    _notify_telegram(action, result.returncode == 0)


def _notify_telegram(action: dict, success: bool) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        import urllib.request
        status = "✅" if success else "❌"
        text = (
            f"{status} LLM Action: {action.get('action')} {action.get('side','')} "
            f"{action.get('symbol','')} qty={action.get('qty','')}\n"
            f"Strategy: {action.get('strategy','')} | Reason: {action.get('reason','')}"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning(f"Telegram notify failed: {e}")


def run_once(dry_run: bool = False) -> dict:
    system = load_system_prompt()
    briefing = load_briefing()
    snapshot = get_market_snapshot()
    user_msg = build_user_message(snapshot, briefing)

    log.info(f"Calling LLM (provider={os.getenv('LLM_PROVIDER','groq')}, "
             f"model={os.getenv('LLM_MODEL','default')}) ...")

    raw = chat_complete(system=system, user=user_msg)
    log.debug(f"LLM raw response: {raw}")

    action = parse_action(raw)
    if not action:
        log.error("LLM returned unparseable response — holding.")
        return {"action": "hold", "reason": "parse_error"}

    log.info(f"LLM action: {json.dumps(action)}")

    if not validate_action(action):
        return {"action": "hold", "reason": "validation_blocked"}

    execute_action(action, dry_run=dry_run)
    return action


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Agent Loop for bybit-trading-cli")
    parser.add_argument("--once", action="store_true", help="Single decision then exit")
    parser.add_argument("--interval", type=int, default=900,
                        help="Loop interval in seconds (default 900 = 15 min)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyse only, no orders sent")
    args = parser.parse_args()

    if args.dry_run:
        log.info("DRY-RUN mode — no orders will be placed.")

    if args.once:
        run_once(dry_run=args.dry_run)
        return

    log.info(f"Starting LLM agent loop every {args.interval}s ...")
    while True:
        try:
            run_once(dry_run=args.dry_run)
        except KeyboardInterrupt:
            log.info("Agent loop stopped by user.")
            break
        except Exception as e:
            log.error(f"Unhandled error in agent loop: {e}")
        log.info(f"Sleeping {args.interval}s ...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
