#!/usr/bin/env bash
# scripts/setup.sh — One-shot project setup
# Usage: bash scripts/setup.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ---- Colors ----------------------------------------------------------------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; WHT='\033[1;37m'; RST='\033[0m'
BOLD='\033[1m'

box()  { echo -e "${BLU}╭────────────────────────────────────────────────────────────╮${RST}"; }
boxb() { echo -e "${BLU}╰────────────────────────────────────────────────────────────╯${RST}"; }
step() { echo -e "\n${CYN}▶ ${BOLD}$*${RST}"; }
ok()   { echo -e "  ${GRN}✔${RST}  $*"; }
warn() { echo -e "  ${YLW}⚠${RST}  $*"; }
fail() { echo -e "  ${RED}✘${RST}  $*"; }
info() { echo -e "  ${WHT}   $*${RST}"; }

clear
box
echo -e "${BLU}│${RST}   ${BOLD}${WHT}bybit-trading-cli-integration${RST}  —  Setup                     ${BLU}│${RST}"
echo -e "${BLU}│${RST}   LLM Agent + Bybit CLI + 26 Strategies                    ${BLU}│${RST}"
boxb
echo

# 1. bybit-cli
step "[1/4] bybit-cli (npm)"
if command -v bybit-cli &>/dev/null; then
  ok "bybit-cli already installed"
else
  info "Installing bybit-official-trading-cli ..."
  npm i -g bybit-official-trading-cli@latest && ok "bybit-cli installed" || fail "npm install failed"
fi

# 2. Python deps
step "[2/4] Python dependencies"
if python -c 'import openai' 2>/dev/null; then
  VER=$(python -c 'import openai; print(openai.__version__)')
  ok "openai ${VER} already installed"
else
  info "Running: pip install -r requirements.txt"
  python -m pip install -q -r requirements.txt
  VER=$(python -c 'import openai; print(openai.__version__)')
  ok "openai ${VER} installed"
fi

# 3. .env
step "[3/4] Environment file"
if [ -f .env ]; then
  ok ".env already exists"
else
  cp .env.example .env
  ok ".env created from .env.example"
  warn "Edit .env and fill in: BYBIT_API_KEY, BYBIT_API_SECRET, GROQ_API_KEY"
  info "  nano .env   or   code .env"
fi

# Load .env
export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null || true

# 4. LLM connectivity
step "[4/4] LLM provider test (${LLM_PROVIDER:-groq})"
if python -m llm.providers test 2>&1 | grep -q '✅'; then
  ok "LLM provider ${LLM_PROVIDER:-groq} OK"
else
  warn "LLM provider test failed — check your API key in .env"
  info "  Run: bash llm/connect.sh list   (see all providers)"
  info "  Run: bash llm/connect.sh test all"
fi

# Done
echo
echo -e "${GRN}╭────────────────────────────────────────────────────────────╮${RST}"
echo -e "${GRN}│${RST}  ${BOLD}Setup complete! Next steps:${RST}                                ${GRN}│${RST}"
echo -e "${GRN}│${RST}                                                            ${GRN}│${RST}"
echo -e "${GRN}│${RST}  1. ${WHT}nano .env${RST}                    fill in your keys           ${GRN}│${RST}"
echo -e "${GRN}│${RST}  2. ${WHT}bash scripts/health_check.sh${RST}  full system check           ${GRN}│${RST}"
echo -e "${GRN}│${RST}  3. ${WHT}python llm/agent_loop.py --dry-run --once${RST}  first decision ${GRN}│${RST}"
echo -e "${GRN}│${RST}  4. ${WHT}python llm/agent_loop.py --interval 900${RST}  live loop       ${GRN}│${RST}"
echo -e "${GRN}╰────────────────────────────────────────────────────────────╯${RST}"
echo
