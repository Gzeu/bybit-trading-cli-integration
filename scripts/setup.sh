#!/usr/bin/env bash
# scripts/setup.sh — One-shot project setup
# Usage: bash scripts/setup.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> bybit-trading-cli-integration setup"
echo

# 1. Node CLI
if ! command -v bybit-cli &>/dev/null; then
  echo "[1/4] Installing bybit-official-trading-cli ..."
  npm i -g bybit-official-trading-cli@latest
else
  echo "[1/4] bybit-cli already installed: $(bybit-cli --version 2>/dev/null || echo ok)"
fi

# 2. Python deps
echo "[2/4] Installing Python requirements ..."
python -m pip install -q -r requirements.txt
echo "      openai: $(python -c 'import openai; print(openai.__version__)')"

# 3. Env file
if [ ! -f .env ]; then
  echo "[3/4] Creating .env from .env.example ..."
  cp .env.example .env
  echo "      ⚠️  Edit .env and fill in BYBIT_API_KEY, BYBIT_API_SECRET, GROQ_API_KEY"
else
  echo "[3/4] .env already exists — skipping"
fi

# 4. LLM provider connectivity test
echo "[4/4] Testing LLM provider connectivity ..."
if python -m llm.providers test 2>&1 | grep -q '✅'; then
  echo "      ✅ LLM provider OK"
else
  echo "      ⚠️  LLM provider test failed — check GROQ_API_KEY in .env"
  echo "      Run: bash llm/connect.sh list  (to see all providers)"
fi

echo
echo "==> Setup complete. Next steps:"
echo "    1. Edit .env with your keys"
echo "    2. bash llm/connect.sh test         # verify LLM"
echo "    3. python llm/agent_loop.py --dry-run --once  # first decision (no orders)"
echo "    4. python llm/agent_loop.py --once  # live decision on testnet"
