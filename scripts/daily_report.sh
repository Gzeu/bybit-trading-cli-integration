#!/bin/bash
# Generate and send daily PnL report via Telegram

REPORT=$(bybit-cli position closed-pnl --category linear --limit 50 2>/dev/null | python3 -c "
import sys, json, datetime
try:
    d = json.load(sys.stdin)
    trades = d['result']['list']
    today = datetime.date.today().strftime('%Y%m%d')
    today_trades = [t for t in trades if t.get('updatedTime','')[:8] == today]
    total_pnl = sum(float(t['closedPnl']) for t in today_trades)
    wins = len([t for t in today_trades if float(t['closedPnl']) > 0])
    losses = len([t for t in today_trades if float(t['closedPnl']) <= 0])
    win_rate = wins/(wins+losses)*100 if (wins+losses) > 0 else 0
    print(f'Trades: {len(today_trades)} | Wins: {wins} | Losses: {losses} | Win rate: {win_rate:.1f}% | PnL: {total_pnl:.4f} USDT')
except Exception as e:
    print(f'Error: {e}')
")

echo "Daily Report: $REPORT"
./scripts/telegram_alert.sh "Daily Report: $REPORT"
