#!/bin/bash
# Health check: verify CLI, auth, balance, positions
# Run before any trading session

echo "====================================="
echo " Bybit Health Check"
echo "====================================="

# 1. CLI installed?
if ! command -v bybit-cli &> /dev/null; then
  echo "[FAIL] bybit-cli not installed"
  echo "  Fix: npm i -g bybit-official-trading-cli@latest"
  exit 1
fi
echo "[OK] bybit-cli installed: $(bybit-cli --version 2>/dev/null || echo 'version unknown')"

# 2. Env set?
if [ -z "$BYBIT_API_KEY" ]; then
  echo "[FAIL] BYBIT_API_KEY not set"
  exit 1
fi
echo "[OK] BYBIT_API_KEY set (${BYBIT_API_KEY:0:8}...)"

# 3. Environment
echo "[OK] BYBIT_ENV=${BYBIT_ENV:-mainnet}"

# 4. Integrity check
echo "[..] Running bybit-cli verify..."
bybit-cli verify > /dev/null 2>&1 && echo "[OK] Integrity check passed" || echo "[WARN] Integrity check failed"

# 5. Balance
echo "[..] Checking wallet balance..."
bybit-cli account wallet-balance --accountType UNIFIED 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    bal = d['result']['list'][0]['totalEquity']
    print(f'[OK] Balance: {bal} USDT')
except:
    print('[WARN] Could not fetch balance (check API key permissions)')
"

# 6. Open positions
echo "[..] Checking open positions..."
bybit-cli position info --category linear 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    positions = [p for p in d['result']['list'] if float(p.get('size','0')) > 0]
    print(f'[OK] Open positions: {len(positions)}')
    for p in positions:
        print(f'     {p[\"symbol\"]} {p[\"side\"]} size={p[\"size\"]} pnl={p[\"unrealisedPnl\"]}')
except:
    print('[WARN] Could not fetch positions')
"

echo "====================================="
echo " Health check complete"
echo "====================================="
