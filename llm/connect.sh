#!/usr/bin/env bash
# llm/connect.sh — Quick LLM provider connectivity helper
# Usage:
#   bash llm/connect.sh              # test active provider
#   bash llm/connect.sh groq         # test specific provider
#   bash llm/connect.sh all          # test ALL providers
#   bash llm/connect.sh list         # list providers + active config
#   bash llm/connect.sh models groq  # list models for a provider

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -f .env ] && export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null || true

# ---- Colors ----------------------------------------------------------------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; WHT='\033[1;37m'; RST='\033[0m'
BOLD='\033[1m'

cmd="${1:-test}"
arg="${2:-}"

echo
echo -e "${BLU}╭────────────────────────────────────────────────────────╮${RST}"
echo -e "${BLU}│${RST}  ${BOLD}${WHT}LLM Provider Connect${RST}  —  ${CYN}${cmd}${RST} ${arg}             ${BLU}│${RST}"
echo -e "${BLU}╰────────────────────────────────────────────────────────╯${RST}"
echo

case "$cmd" in
  list)
    python -m llm.providers list
    ;;
  models)
    python -m llm.providers models "${arg:-}"
    ;;
  test)
    if [ -z "$arg" ]; then
      python -m llm.providers test
    else
      python -m llm.providers test "$arg"
    fi
    ;;
  all)
    echo -e "  ${YLW}Testing all providers — this may take ~30s ...${RST}\n"
    python -m llm.providers test all
    ;;
  *)
    echo -e "  ${RED}Unknown command: $cmd${RST}"
    echo -e "  Usage: bash llm/connect.sh ${WHT}[list | test [provider] | all | models [provider]]${RST}"
    exit 1
    ;;
esac
echo
