#!/usr/bin/env python3
"""
main.py — Bybit Account Commander entry point

Usage:
    # Testnet dry-run (recommended first run)
    cp skills/bybit-account-commander/config.default.yaml config.yaml
    # Edit config.yaml: env: testnet, autonomous: false
    python main.py --config config.yaml

    # Single cycle (no loop)
    python main.py --config config.yaml --once

    # Production loop (autonomous: true in config.yaml)
    python main.py --config config.yaml --interval 300

Environment variables (override config.yaml):
    BYBIT_API_KEY      — required
    BYBIT_API_SECRET   — required
    BYBIT_ENV          — mainnet | testnet (overrides config)
    AUTONOMOUS         — true | false (overrides config)
"""

from __future__ import annotations
import argparse
import os
import sys
import yaml


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    # Environment variable overrides
    if os.getenv("BYBIT_ENV"):
        cfg["env"] = os.getenv("BYBIT_ENV")
    if os.getenv("AUTONOMOUS"):
        cfg["autonomous"] = os.getenv("AUTONOMOUS", "").lower() == "true"

    return cfg


def build_client(config: dict):
    """Build BybitV5Client from env vars + config."""
    api_key = os.getenv("BYBIT_API_KEY", "")
    api_secret = os.getenv("BYBIT_API_SECRET", "")

    if not api_key or not api_secret:
        print("[ERROR] BYBIT_API_KEY and BYBIT_API_SECRET must be set as environment variables.")
        sys.exit(1)

    testnet = config.get("env", "mainnet") == "testnet"

    try:
        from skills.bybit_account_commander.src.adapters.bybit_v5 import BybitV5Client
    except ImportError:
        # Fallback for flat src/ usage
        from src.adapters.bybit_v5 import BybitV5Client  # type: ignore

    return BybitV5Client(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )


def print_banner(config: dict) -> None:
    env = config.get("env", "mainnet").upper()
    autonomous = config.get("autonomous", False)
    symbols = config.get("watchlist", [])
    print()
    print("=" * 60)
    print(f"  BYBIT ACCOUNT COMMANDER v2.0.0")
    print(f"  ENV          : {env}")
    print(f"  AUTONOMOUS   : {autonomous}")
    print(f"  WATCHLIST    : {', '.join(symbols)}")
    print(f"  SAR TF       : {config.get('sar', {}).get('tf_primary', '5')}m "
          f"filter {config.get('sar', {}).get('tf_filter', '60')}m")
    print(f"  RISK/TRADE   : {config.get('risk', {}).get('per_trade_pct', 0)*100:.2f}%")
    print(f"  MAX OPEN RISK: {config.get('risk', {}).get('max_open_risk_pct', 0)*100:.2f}%")
    print(f"  DAILY HALT   : {config.get('risk', {}).get('daily_loss_halt_pct', 0)*100:.2f}%")
    if env == "MAINNET" and autonomous:
        print()
        print("  ⚠  WARNING: MAINNET + AUTONOMOUS = REAL MONEY")
    print("=" * 60)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit Account Commander")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single cycle then exit")
    parser.add_argument("--interval", type=int, default=300,
                        help="Loop interval in seconds (default: 300 = 5m)")
    parser.add_argument("--log-dir", default="logs",
                        help="Log directory (default: logs/)")
    args = parser.parse_args()

    # Load config
    if not os.path.exists(args.config):
        print(f"[ERROR] Config file not found: {args.config}")
        print(f"  Hint: cp skills/bybit-account-commander/config.default.yaml config.yaml")
        sys.exit(1)

    config = load_config(args.config)
    print_banner(config)

    # Safety check: warn loudly if mainnet + autonomous
    if config.get("env") == "mainnet" and config.get("autonomous"):
        confirm = input("  Type 'YES I UNDERSTAND' to proceed on MAINNET AUTONOMOUS: ")
        if confirm.strip() != "YES I UNDERSTAND":
            print("Aborted.")
            sys.exit(0)

    # Build client
    client = build_client(config)

    # Build commander loop
    try:
        from skills.bybit_account_commander.src.commander_loop import CommanderLoop
    except ImportError:
        from src.commander_loop import CommanderLoop  # type: ignore

    loop = CommanderLoop(client, config, log_dir=args.log_dir)

    if args.once:
        print("[COMMANDER] Running single cycle...")
        result = loop.run_once()
        print(f"\n[COMMANDER] Cycle complete. Plan items: {len(result.get('plan', []))}")
    else:
        loop.run_loop(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
