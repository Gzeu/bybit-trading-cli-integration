#!/usr/bin/env bash
# llm/connect.sh — Quick provider connectivity helper
# Usage:
#   bash llm/connect.sh              # test active provider
#   bash llm/connect.sh groq         # test specific provider
#   bash llm/connect.sh all          # test all providers
#   bash llm/connect.sh list         # list providers + active config
#   bash llm/connect.sh models groq  # list models for a provider

set -euo pipefail
CD="$(cd "$(dirname "$0")/.." && pwd)"

cmd="${1:-test}"
arg="${2:-}"

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
    python -m llm.providers test all
    ;;
  *)
    echo "Usage: bash llm/connect.sh [list|test [provider]|all|models [provider]]"
    exit 1
    ;;
esac
