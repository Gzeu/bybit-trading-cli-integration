#!/usr/bin/env python3
"""
watchdog.py — Process watchdog for commander loop

Monitors the commander process and restarts it if:
  - Process dies
  - No log activity for > max_silence_minutes (default 15)
  - log/commander.jsonl last line is older than threshold

Usage:
    python scripts/watchdog.py --config config.yaml

Runs as a separate process alongside main.py.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

MAX_RESTARTS = 10
CHECK_INTERVAL_S = 30
MAX_SILENCE_S = 15 * 60  # 15 minutes


def last_log_age(log_path: str) -> float:
    """Return seconds since last line was written to log file."""
    if not os.path.exists(log_path):
        return float("inf")
    mtime = os.path.getmtime(log_path)
    return time.time() - mtime


def start_commander(config: str, interval: int) -> subprocess.Popen:
    cmd = [sys.executable, "main.py", "--config", config,
           "--interval", str(interval)]
    print(f"[WATCHDOG] Starting: {' '.join(cmd)}")
    return subprocess.Popen(cmd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--log", default="logs/commander.jsonl")
    args = parser.parse_args()

    restarts = 0
    proc = start_commander(args.config, args.interval)

    while True:
        time.sleep(CHECK_INTERVAL_S)

        alive = proc.poll() is None
        silence = last_log_age(args.log)

        if not alive:
            print(f"[WATCHDOG] Process died (code={proc.returncode}). Restarting...")
        elif silence > MAX_SILENCE_S:
            print(f"[WATCHDOG] No log activity for {silence:.0f}s. Killing + restarting...")
            proc.kill()
        else:
            continue

        restarts += 1
        if restarts > MAX_RESTARTS:
            print(f"[WATCHDOG] {MAX_RESTARTS} restarts exceeded. Giving up.")
            sys.exit(1)

        time.sleep(5)
        proc = start_commander(args.config, args.interval)
        print(f"[WATCHDOG] Restart #{restarts}")


if __name__ == "__main__":
    main()
