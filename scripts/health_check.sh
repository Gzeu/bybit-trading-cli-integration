#!/usr/bin/env bash
# scripts/health_check.sh — Full system health check
# Checks: bybit-cli, Python, .env, LLM provider, bybit API connectivity
# Usage: bash scripts/health_check.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Load .env if present
[ -f .env ] && export $(grep -v '^#' .env | grep -v '^$' | xargs)

PASS=0; FAIL=0
ok()   { echo "  ✅  $*"; PASS=$((PASS+1)); }
fail() { echo "  ❌  $*"; FAIL=$((FAIL+1)); }
warn() { echo "  ⚠️  $*"; }

echo
echo "=== bybit-trading-cli-integration health check ==="
echo

# --- bybit-cli ---
echo "[1] bybit-cli"
if command -v bybit-cli &>/dev/null; then
  ok "bybit-cli found: $(bybit-cli --version 2>/dev/null || echo installed)"
else
  fail "bybit-cli not found. Run: npm i -g bybit-official-trading-cli@latest"
fi

# --- Python ---
echo "[2] Python + deps"
if python -c 'import openai' 2>/dev/null; then
  VER=$(python -c 'import openai; print(openai.__version__)')
  ok "openai $VER installed"
else
  fail "openai not installed. Run: pip install -r requirements.txt"
fi

# --- .env ---
echo "[3] Environment"
[ -n "${BYBIT_API_KEY:-}" ]    && ok "BYBIT_API_KEY set"    || fail "BYBIT_API_KEY missing"
[ -n "${BYBIT_API_SECRET:-}" ] && ok "BYBIT_API_SECRET set" || fail "BYBIT_API_SECRET missing"
[ "${BYBIT_ENV:-}" = "testnet" ] && warn "BYBIT_ENV=testnet (safe)" || warn "BYBIT_ENV=${BYBIT_ENV:-unset}"

# --- LLM provider ---
echo "[4] LLM provider (${LLM_PROVIDER:-groq})"
if python -m llm.providers test 2>&1 | grep -q '✅'; then
  MODEL=$(python -m llm.providers test 2>&1 | grep 'model:' | head -1 | awk '{print $2}')
  ok "LLM provider OK — model: ${MODEL:-default}"
else
  RAW=$(python -m llm.providers test 2>&1 | grep -E 'error:|fix:' | head -2 || true)
  fail "LLM provider failed. $RAW"
  warn "  Run: bash llm/connect.sh list  (see all providers)"
  warn "  Run: bash llm/connect.sh test all  (test every provider)"
fi

# --- Bybit API ping (snapshot) ---
echo "[5] Bybit API"
SNAP=$(python -m core.engine --snapshot --json 2>/dev/null || echo "")
if echo "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); exit(0 if d.get("price",0)>0 else 1)' 2>/dev/null; then
  PRICE=$(echo "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d["price"])')
  BAL=$(echo "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d["balance_usdt"])')
  ok "Bybit API OK — price=${PRICE} balance=${BAL} USDT"
else
  fail "Bybit API snapshot failed — check BYBIT_API_KEY / BYBIT_ENV"
fi

# --- Summary ---
echo
echo "=== Summary: $PASS passed, $FAIL failed ==="
if [ $FAIL -gt 0 ]; then
  echo "    Fix issues above, then re-run: bash scripts/health_check.sh"
  exit 1
else
  echo "    All systems go. Run: python llm/agent_loop.py --dry-run --once"
fi
echo
