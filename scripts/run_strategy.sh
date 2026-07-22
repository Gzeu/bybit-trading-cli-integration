#!/bin/bash
# Usage: ./scripts/run_strategy.sh <strategy_name> [SYMBOL] [QTY]
# Example: ./scripts/run_strategy.sh trend_follow BTCUSDT 0.01

STRATEGY=${1:-"regime_detection"}
SYMBOL=${2:-"BTCUSDT"}
QTY=${3:-"0.01"}
ENV=${BYBIT_ENV:-"testnet"}

echo "====================================="
echo " Bybit Strategy Runner"
echo "====================================="
echo " Strategy : $STRATEGY"
echo " Symbol   : $SYMBOL"
echo " Qty      : $QTY"
echo " Env      : $ENV"
echo "====================================="

# Safety check
if [ "$ENV" = "mainnet" ]; then
  echo "WARNING: Running on MAINNET"
  read -p "Are you sure? (yes/no): " confirm
  if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
  fi
fi

# Verify CLI
if ! command -v bybit-cli &> /dev/null; then
  echo "ERROR: bybit-cli not found. Run: npm i -g bybit-official-trading-cli@latest"
  exit 1
fi

# Run strategy
SYMBOL=$SYMBOL QTY=$QTY BYBIT_ENV=$ENV python3 strategies/${STRATEGY}.py 2>&1 | tee -a logs/strategy_$(date +%Y%m%d).log

echo "Done. Log saved to logs/strategy_$(date +%Y%m%d).log"
