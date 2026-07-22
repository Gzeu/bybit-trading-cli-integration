#!/usr/bin/env bash
# scripts/health_check.sh — Full system health check
# Usage: bash scripts/health_check.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Load .env
[ -f .env ] && export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null || true

# ---- Colors ----------------------------------------------------------------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; WHT='\033[1;37m'; RST='\033[0m'
BOLD='\033[1m'

PASS=0; FAIL=0; WARN=0
ok()   { echo -e "  ${GRN}✔${RST}  $*";           PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✘${RST}  ${RED}$*${RST}"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YLW}⚠${RST}  ${YLW}$*${RST}"; WARN=$((WARN+1)); }
info() { echo -e "      ${WHT}$*${RST}"; }
sect() { echo -e "\n${CYN}▶ ${BOLD}$*${RST}"; }

clear
echo -e "${BLU}╭────────────────────────────────────────────────────────────╮${RST}"
echo -e "${BLU}│${RST}   ${BOLD}${WHT}bybit-trading-cli-integration${RST}  —  Health Check              ${BLU}│${RST}"
echo -e "${BLU}╰────────────────────────────────────────────────────────────╯${RST}"

# [1] bybit-cli
sect "[1/5] bybit-cli"
if command -v bybit-cli &>/dev/null; then
  ok "bybit-cli found"
else
  fail "bybit-cli not found"
  info "Fix: npm i -g bybit-official-trading-cli@latest"
fi

# [2] Python + openai
sect "[2/5] Python + dependencies"
if python -c 'import openai' 2>/dev/null; then
  VER=$(python -c 'import openai; print(openai.__version__)')
  ok "openai ${VER} installed"
else
  fail "openai not installed"
  info "Fix: pip install -r requirements.txt"
fi

# [3] .env keys
sect "[3/5] Environment variables"
[ -n "${BYBIT_API_KEY:-}" ]     && ok "BYBIT_API_KEY       set"   || fail "BYBIT_API_KEY       missing — edit .env"
[ -n "${BYBIT_API_SECRET:-}" ]  && ok "BYBIT_API_SECRET    set"   || fail "BYBIT_API_SECRET    missing — edit .env"
if [ "${BYBIT_ENV:-testnet}" = "testnet" ]; then
  warn "BYBIT_ENV = testnet  (safe mode — no real money)"
else
  warn "BYBIT_ENV = ${BYBIT_ENV}  ⚠️ MAINNET — real money!"
fi
[ -n "${GROQ_API_KEY:-}" ]      && ok "GROQ_API_KEY        set"   || warn "GROQ_API_KEY        not set (check LLM_PROVIDER in .env)"

# [4] LLM provider
sect "[4/5] LLM provider  (${LLM_PROVIDER:-groq})"
LLM_OUT=$(python -m llm.providers test 2>&1 || true)
if echo "$LLM_OUT" | grep -q '✅'; then
  MODEL=$(echo "$LLM_OUT" | grep 'model:' | head -1 | sed 's/.*model: //')
  LAT=$(echo   "$LLM_OUT" | grep 'latency' | head -1 | sed 's/.*latency_ms: //')
  ok "${LLM_PROVIDER:-groq} responsive — model: ${MODEL:-?}  latency: ${LAT:-?}ms"
else
  ERR=$(echo "$LLM_OUT" | grep 'error:' | head -1 | sed 's/.*error: //' || true)
  FIX=$(echo "$LLM_OUT" | grep 'fix:'   | head -1 | sed 's/.*fix: //'   || true)
  fail "LLM provider failed: ${ERR:-unknown error}"
  [ -n "${FIX:-}" ] && info "Fix: ${FIX}"
  info "Try: bash llm/connect.sh list"
  info "Try: bash llm/connect.sh test all"
fi

# [5] Bybit API snapshot
sect "[5/5] Bybit API  (${BYBIT_ENV:-testnet})"
SNAP=$(python -m core.engine --snapshot --json 2>/dev/null || echo "{}")
PRICE=$(echo "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("price",0))' 2>/dev/null || echo 0)
BAL=$(echo   "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("balance_usdt",0))' 2>/dev/null || echo 0)
SYM=$(echo   "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("symbol","?"))' 2>/dev/null || echo "?")
REGIME=$(echo "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("indicators",{}).get("regime","?"))' 2>/dev/null || echo "?")
RSI=$(echo    "$SNAP" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("indicators",{}).get("rsi_14","?"))' 2>/dev/null || echo "?")
if [ "$(echo $PRICE | python -c 'import sys; v=float(sys.stdin.read()); exit(0 if v>0 else 1)' 2>/dev/null; echo $?)" = "0" ]; then
  ok "Bybit API OK"
  info "Symbol   : ${SYM}"
  info "Price    : ${PRICE} USDT"
  info "Balance  : ${BAL} USDT"
  info "RSI(14)  : ${RSI}"
  info "Regime   : ${REGIME}"
else
  fail "Bybit API snapshot returned no price"
  info "Check: BYBIT_API_KEY / BYBIT_API_SECRET / BYBIT_ENV in .env"
fi

# ---- Summary ---------------------------------------------------------------
echo
if [ $FAIL -eq 0 ] && [ $WARN -le 1 ]; then
  echo -e "${GRN}╭────────────────────────────────────────────────────────────╮${RST}"
  echo -e "${GRN}│${RST}  ${BOLD}${GRN}✔ All systems go${RST}  —  ${PASS} passed, ${WARN} warnings, 0 failed    ${GRN}│${RST}"
  echo -e "${GRN}│${RST}                                                            ${GRN}│${RST}"
  echo -e "${GRN}│${RST}  ${WHT}python llm/agent_loop.py --dry-run --once${RST}               ${GRN}│${RST}"
  echo -e "${GRN}╰────────────────────────────────────────────────────────────╯${RST}"
else
  echo -e "${RED}╭────────────────────────────────────────────────────────────╮${RST}"
  echo -e "${RED}│${RST}  ${BOLD}${RED}✘ ${FAIL} failed${RST}, ${YLW}${WARN} warnings${RST}, ${GRN}${PASS} passed${RST}                      ${RED}│${RST}"
  echo -e "${RED}│${RST}  Fix issues above, then re-run: ${WHT}bash scripts/health_check.sh${RST}   ${RED}│${RST}"
  echo -e "${RED}╰────────────────────────────────────────────────────────────╯${RST}"
  exit 1
fi
echo
