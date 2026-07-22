#!/bin/bash
# Usage: ./scripts/telegram_alert.sh "Your message here"
# Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars

MESSAGE=${1:-"Bybit agent ping"}
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
  echo "[SKIP] Telegram not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)"
  exit 0
fi

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d parse_mode="Markdown" \
  -d text="*[BYBIT AGENT]* ${TIMESTAMP}%0A${MESSAGE}" > /dev/null

echo "[SENT] Telegram: $MESSAGE"
