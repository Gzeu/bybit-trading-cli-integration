#!/usr/bin/env python3
"""
journal_stats.py — Print trade journal stats from CSV

Usage:
    python scripts/journal_stats.py
    python scripts/journal_stats.py --journal logs/trade_journal.csv
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.bybit_account_commander.src.journal import TradeJournal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", default="logs/trade_journal.csv")
    args = parser.parse_args()

    log_dir = os.path.dirname(args.journal)
    journal = TradeJournal(log_dir=log_dir if log_dir else "logs")
    stats = journal.stats()

    if stats["total"] == 0:
        print("No trades recorded yet.")
        return

    print()
    print("=" * 50)
    print("  TRADE JOURNAL STATS")
    print("=" * 50)
    print(f"  Total trades   : {stats['total']}")
    print(f"  Wins / Losses  : {stats['wins']} / {stats['losses']}")
    print(f"  Win rate       : {stats['win_rate']*100:.1f}%")
    print(f"  Avg win        : +{stats['avg_win']:.4f} USDT")
    print(f"  Avg loss       : -{stats['avg_loss']:.4f} USDT")
    print(f"  Expectancy     : {stats['expectancy']:.4f} USDT/trade")
    print(f"  Total net PnL  : {stats['total_net_pnl']:.4f} USDT")
    print()
    print("  By grade:")
    for grade, data in stats.get("by_grade", {}).items():
        print(f"    {grade:5s} : {data['count']} trades, net={data['net_pnl']:.4f} USDT")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
