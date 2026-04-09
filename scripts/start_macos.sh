#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
TRANSLATOR_ENTRY="$ROOT_DIR/external/md-translator/.next/standalone/server.js"

cd "$ROOT_DIR"

export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

if [ ! -x "$VENV_PYTHON" ]; then
  echo "未找到 Python 虚拟环境。请先运行 ./scripts/setup_macos.sh"
  exit 1
fi

if [ ! -f "$TRANSLATOR_ENTRY" ]; then
  echo "未找到 md-translator 的 standalone 构建产物。请先运行 ./scripts/setup_macos.sh"
  exit 1
fi

exec "$VENV_PYTHON" -m streamlit run "$ROOT_DIR/app.py" \
  --server.headless=true \
  --server.address=127.0.0.1 \
  --server.port=8501
