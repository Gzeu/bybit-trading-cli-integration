"""
notifier.py — Telegram notification for COMMANDER BRIEF and alerts

Sends:
  - COMMANDER BRIEF after each cycle (if configured)
  - EXECUTE confirmations
  - GATE_BLOCK alerts
  - DAILY_HALT alert
  - ERROR alerts

Config keys:
  telegram.bot_token   : str
  telegram.chat_id     : str | int
  telegram.send_brief  : bool  (default false — verbose)
  telegram.send_alerts : bool  (default true)
  telegram.brief_interval_cycles : int  (send brief every N cycles, default 12)
"""

from __future__ import annotations
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("notifier")

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore


class TelegramNotifier:
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, config: dict):
        tg = config.get("telegram", {})
        self.token = tg.get("bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
        self.chat_id = tg.get("chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))
        self.send_brief = tg.get("send_brief", False)
        self.send_alerts = tg.get("send_alerts", True)
        self.brief_interval = tg.get("brief_interval_cycles", 12)
        self._cycle_count = 0
        self._enabled = bool(self.token and self.chat_id)

    def on_cycle(self, brief: str, plan: list) -> None:
        """Called after each cycle. Sends brief every N cycles."""
        self._cycle_count += 1

        # Gate blocks
        if self.send_alerts:
            for action in plan:
                if action.get("gate_block"):
                    self.alert(f"⚠️ GATE BLOCK [{action.get('symbol','')}]\n{action['gate_block']}")

        # Brief every N cycles
        if self.send_brief and self._cycle_count % self.brief_interval == 0:
            # Truncate brief to 4000 chars (Telegram limit)
            self.send(brief[:4000])

    def on_execute(self, action: dict, result: dict) -> None:
        if not self.send_alerts:
            return
        symbol = action.get("symbol", "")
        act = action.get("action", "")
        ok = result.get("success", False)
        order_id = result.get("order_id", "")
        emoji = "✅" if ok else "❌"
        msg = f"{emoji} EXECUTE {act} {symbol}\norder_id: {order_id}\nresult: {json.dumps(result)}"
        self.alert(msg)

    def on_halt(self, daily_pnl: float, equity: float) -> None:
        if not self.send_alerts:
            return
        self.alert(f"🛑 DAILY HALT\nPnL: {daily_pnl:.4f} USDT\nEquity: {equity:.4f} USDT")

    def on_error(self, error: str) -> None:
        if not self.send_alerts:
            return
        self.alert(f"🚨 COMMANDER ERROR\n{error[:500]}")

    def alert(self, text: str) -> None:
        self.send(f"🤖 *COMMANDER*\n{text}")

    def send(self, text: str) -> bool:
        if not self._enabled:
            return False
        if _requests is None:
            logger.warning("requests not installed — Telegram notify disabled")
            return False
        try:
            url = self.BASE_URL.format(token=self.token)
            resp = _requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            ok = resp.status_code == 200
            if not ok:
                logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
            return ok
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False


# Null notifier for when Telegram is not configured
class NullNotifier:
    def on_cycle(self, brief, plan): pass
    def on_execute(self, action, result): pass
    def on_halt(self, daily_pnl, equity): pass
    def on_error(self, error): pass
    def alert(self, text): pass
    def send(self, text): return False


def build_notifier(config: dict) -> TelegramNotifier | NullNotifier:
    tg = config.get("telegram", {})
    if tg.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN"):
        return TelegramNotifier(config)
    return NullNotifier()
