"""
llm/comms.py — Bidirectional communication for the trading agent
================================================================

Telegram (primary):
  Agent -> user : trade alerts, tick summaries, status replies
  User -> agent : /commands polled each tick from a thread-safe queue

Security: only chat IDs listed in TELEGRAM_ALLOWED_CHATS (or TELEGRAM_CHAT_ID
as fallback) can issue commands. Unauthorized senders are silently ignored.

Supported commands:
  /status         Reply with current balance, position, last action, regime
  /pnl            Reply with today's closed PnL
  /stop           Graceful shutdown after current tick
  /pause          Suspend trading (hold all decisions) until /resume
  /resume         Resume trading
  /dry [on|off]   Toggle dry-run mode
  /watchlist      Show current dynamic watchlist
  /force SYMBOL   Force next scan to include SYMBOL
  /help           List commands

CLI interactive mode (local dev/testing):
    python llm/comms.py --chat

Usage in agent_loop:
    from llm.comms import TelegramComms
    comms = TelegramComms()          # singleton; safe to call multiple times
    comms.poll_commands(cmd_queue)   # call at start of each tick
    comms.send_tick_summary(ctx, action, regime)
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("comms")

# ---------------------------------------------------------------------------
# Telegram allowlist — only these chat IDs can issue commands
# Set TELEGRAM_ALLOWED_CHATS as comma-separated IDs in .env
# Falls back to TELEGRAM_CHAT_ID if TELEGRAM_ALLOWED_CHATS is not set
# ---------------------------------------------------------------------------

ALLOWED_CHAT_IDS: frozenset[str] = frozenset(
    x.strip()
    for x in os.getenv(
        "TELEGRAM_ALLOWED_CHATS",
        os.getenv("TELEGRAM_CHAT_ID", ""),
    ).split(",")
    if x.strip()
)

# ---------------------------------------------------------------------------
# Command dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentCommand:
    """A command received from the user (via Telegram or CLI)."""
    source:  str          # "telegram" | "cli"
    user:    str          # username or "local"
    cmd:     str          # e.g. "pause"
    args:    list[str]    # extra tokens after command
    raw:     str          # original message text
    chat_id: int | None = None


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _tg_call(token: str, method: str, payload: dict, timeout: int = 8) -> dict:
    url  = TELEGRAM_API.format(token=token, method=method)
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.warning(f"Telegram {method} HTTP {e.code}: {e.read()[:200]}")
        return {}
    except Exception as e:
        log.warning(f"Telegram {method}: {e}")
        return {}


def _tg_send(token: str, chat_id: int | str, text: str,
             parse_mode: str = "Markdown") -> dict:
    return _tg_call(token, "sendMessage", {
        "chat_id":    chat_id,
        "text":       text[:4096],   # Telegram limit
        "parse_mode": parse_mode,
    })


def _tg_get_updates(token: str, offset: int, timeout: int = 2) -> list[dict]:
    resp = _tg_call(token, "getUpdates",
                    {"offset": offset, "timeout": timeout, "limit": 20},
                    timeout=timeout + 3)
    return resp.get("result", [])


# ---------------------------------------------------------------------------
# TelegramComms
# ---------------------------------------------------------------------------

class TelegramComms:
    """Bidirectional Telegram communication for the trading agent.

    Thread-safe: poll_commands() can be called from the main agent thread
    while a background thread continuously pulls updates.

    Instantiate once at agent startup:
        comms = TelegramComms()   # reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
    """

    _instance: "TelegramComms | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "TelegramComms":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._init()
                cls._instance = inst
        return cls._instance

    def _init(self) -> None:
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID",  "")
        self.enabled = bool(self.token and self.chat_id)
        self._offset  = 0
        self._q: queue.Queue[AgentCommand] = queue.Queue()
        self._poller: threading.Thread | None = None
        self._last_action:  str = "none"
        self._last_symbol:  str = ""
        self._last_regime:  str = ""
        self._last_send_ts: float = 0.0   # for send rate-limiting
        if self.enabled:
            self._start_poller()
            log.info(f"[comms] Telegram comms enabled | allowed_chats={ALLOWED_CHAT_IDS}")
        else:
            log.info("[comms] Telegram not configured — comms disabled")

    # --- background update poller ---

    def _start_poller(self) -> None:
        self._poller = threading.Thread(target=self._poll_loop,
                                        daemon=True, name="tg-poller")
        self._poller.start()

    def _poll_loop(self) -> None:
        while True:
            try:
                updates = _tg_get_updates(self.token, self._offset, timeout=2)
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    msg = upd.get("message") or upd.get("channel_post", {})
                    text = msg.get("text", "").strip()
                    if not text.startswith("/"):
                        continue
                    chat_id  = msg.get("chat", {}).get("id")
                    username = msg.get("from", {}).get("username", "?")

                    # --- SECURITY: reject unauthorized senders ---
                    if ALLOWED_CHAT_IDS and str(chat_id) not in ALLOWED_CHAT_IDS:
                        log.warning(
                            f"[comms] ignored cmd from unauthorized chat_id={chat_id} "
                            f"(@{username}): {text[:40]}"
                        )
                        continue

                    parts    = text.lstrip("/").split()
                    cmd_name = parts[0].lower().split("@")[0]  # handle /cmd@botname
                    cmd_args = parts[1:]
                    log.info(f"[comms] /{cmd_name} from @{username} chat={chat_id}")
                    self._q.put(AgentCommand(
                        source="telegram", user=username,
                        cmd=cmd_name, args=cmd_args,
                        raw=text, chat_id=chat_id,
                    ))
            except Exception as e:
                log.debug(f"[comms] poll error: {e}")
            time.sleep(0.5)

    # --- agent calls this each tick ---

    def poll_commands(self) -> list[AgentCommand]:
        """Drain the command queue and return all pending commands."""
        cmds: list[AgentCommand] = []
        while True:
            try:
                cmds.append(self._q.get_nowait())
            except queue.Empty:
                break
        return cmds

    # --- outbound messages ---

    def send(self, text: str, chat_id: int | str | None = None) -> None:
        if not self.enabled:
            log.info(f"[comms:local] {text}")
            return
        # Rate-limit: max 1 message per second (Telegram allows ~30/s, but be safe)
        elapsed = time.monotonic() - self._last_send_ts
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        cid = chat_id or self.chat_id
        _tg_send(self.token, cid, text)
        self._last_send_ts = time.monotonic()

    def reply(self, cmd: AgentCommand, text: str) -> None:
        """Reply to a specific command (uses cmd.chat_id if available)."""
        self.send(text, chat_id=cmd.chat_id or self.chat_id)

    def send_tick_summary(
        self,
        balance: float,
        free_margin: float,
        today_pnl: float,
        action: dict,
        regime: str,
        symbol: str,
        fetch_ms: int,
    ) -> None:
        """Send a concise tick summary after each agent decision."""
        self._last_action = action.get("action", "?")
        self._last_symbol = symbol
        self._last_regime = regime
        env  = os.getenv("BYBIT_ENV", "testnet").upper()
        ts   = datetime.now(timezone.utc).strftime("%H:%M UTC")
        act  = action.get("action", "?")
        icon = {"open_long": "🟢", "open_short": "🔴",
                "close_position": "🔒", "reduce_size": "✂️",
                "hold": "⏸", "wait": "⏳"}.get(act, "❓")
        text = (
            f"{icon} *{act.upper()}* | {env} | {ts}\n"
            f"Symbol: `{symbol}` | Regime: `{regime}`\n"
            f"Strategy: `{action.get('strategy', 'none')}`\n"
            f"Balance: `{balance:.2f}` USDT | Free: `{free_margin:.2f}`\n"
            f"PnL today: `{today_pnl:+.2f}` USDT\n"
            f"Reason: _{action.get('reason', '')}_ | ctx={fetch_ms}ms"
        )
        self.send(text)

    def send_order_result(
        self,
        action: str,
        symbol: str,
        qty: float,
        price: float,
        order_type: str,
        tif: str,
        sl: float,
        tp: float | None,
        commission: float,
        success: bool,
    ) -> None:
        icon = "✅" if success else "❌"
        text = (
            f"{icon} *{action.upper()}* `{symbol}`\n"
            f"qty=`{qty}` price=`{price:.2f}` "
            f"type=`{order_type}/{tif}`\n"
            f"SL=`{sl}` TP=`{tp or 'none'}`\n"
            f"Commission: `{commission:.4f}` USDT"
        )
        self.send(text)

    def build_status_message(
        self,
        balance: float,
        free_margin: float,
        today_pnl: float,
        open_positions: list[dict],
        open_orders: list[dict],
    ) -> str:
        env  = os.getenv("BYBIT_ENV", "testnet").upper()
        pos  = open_positions[0] if open_positions else None
        pos_str = "none"
        if pos:
            pos_str = (
                f"{pos.get('side')} {pos.get('symbol')} "
                f"size={pos.get('size')} "
                f"entry={pos.get('avgPrice')} "
                f"upnl={pos.get('unrealisedPnl')}"
            )
        oo_count = len(open_orders)
        return (
            f"📊 *Status* | {env}\n"
            f"Balance: `{balance:.2f}` USDT | Free: `{free_margin:.2f}`\n"
            f"PnL today: `{today_pnl:+.2f}` USDT\n"
            f"Position: `{pos_str}`\n"
            f"Open orders: `{oo_count}`\n"
            f"Last action: `{self._last_action}` on `{self._last_symbol}`\n"
            f"Last regime: `{self._last_regime}`"
        )


# ---------------------------------------------------------------------------
# CLI interactive mode
# ---------------------------------------------------------------------------

HELP_TEXT = """
Available commands:
  /status       — live account snapshot
  /pnl          — today's closed PnL
  /pause        — pause trading (hold all)
  /resume       — resume trading
  /dry [on|off] — toggle dry-run
  /stop         — graceful shutdown
  /watchlist    — current dynamic watchlist
  /force SYMBOL — include SYMBOL in next scan
  /help         — this help
"""


def _cli_repl() -> None:
    """Interactive CLI for local testing without Telegram."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.engine import get_balance, get_free_margin, get_position
    from core.collector import collect_for_agent

    print("Trading Agent CLI 🤖  (type /help for commands, Ctrl+C to quit)")
    symbol = os.getenv("SYMBOL", "BTCUSDT")
    state  = {"paused": False, "dry_run": False}

    while True:
        try:
            line = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not line:
            continue
        parts = line.lstrip("/").split()
        cmd   = parts[0].lower() if parts else ""
        args  = parts[1:]

        if cmd == "help":
            print(HELP_TEXT)

        elif cmd == "status":
            print("Fetching ...")
            ctx = collect_for_agent([symbol])
            pos = ctx.position_for(symbol)
            print(f"Balance:    {ctx.balance:.2f} USDT")
            print(f"Free margin:{ctx.free_margin:.2f} USDT")
            print(f"PnL today:  {ctx.today_pnl:+.2f} USDT ({ctx.today_pnl_pct:+.4f}%)")
            print(f"Position:   {pos}")
            print(f"Open orders:{len(ctx.open_orders)}")
            print(f"Fetched in: {ctx.fetch_ms}ms")

        elif cmd == "pnl":
            ctx = collect_for_agent([symbol])
            print(f"Today PnL: {ctx.today_pnl:+.2f} USDT ({ctx.today_pnl_pct:+.4f}%)")

        elif cmd == "pause":
            state["paused"] = True
            print("⏸ Trading paused")

        elif cmd == "resume":
            state["paused"] = False
            print("▶ Trading resumed")

        elif cmd == "dry":
            val = args[0].lower() if args else "on"
            state["dry_run"] = val != "off"
            print(f"🧪 Dry-run: {'ON' if state['dry_run'] else 'OFF'}")

        elif cmd == "watchlist":
            try:
                from llm.watchlist import build_watchlist
                wl = build_watchlist()
                print(f"Watchlist ({len(wl)}): {wl}")
            except Exception as e:
                print(f"Error: {e}")

        elif cmd == "force":
            sym = args[0].upper() if args else ""
            if sym:
                print(f"Next scan will include {sym}")
            else:
                print("Usage: /force SYMBOL")

        elif cmd == "stop":
            print("Stopping agent ...")
            break

        elif cmd == "snapshot":
            syms = [a.upper() for a in args] if args else [symbol]
            print(f"Fetching snapshot for {syms} ...")
            ctx = collect_for_agent(syms)
            print(ctx.to_summary())

        elif cmd == "orders":
            ctx = collect_for_agent([symbol])
            print(json.dumps(ctx.open_orders, indent=2))

        elif cmd == "positions":
            ctx = collect_for_agent([symbol])
            print(json.dumps(ctx.open_positions, indent=2))

        else:
            print(f"Unknown command: /{cmd}  (type /help)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--chat", action="store_true", help="Start interactive CLI")
    a = p.parse_args()
    if a.chat:
        _cli_repl()
    else:
        p.print_help()
