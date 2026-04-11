#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
RUNS_DIR="$ROOT_DIR/temp/runs"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "未找到 Python 虚拟环境。请先运行 ./scripts/setup_macos.sh"
  exit 1
fi

if [ $# -gt 0 ]; then
  TARGET="$1"
  if [ -d "$TARGET" ]; then
    RUN_ROOT="$TARGET"
  elif [ -f "$TARGET" ]; then
    RUN_ROOT="$(cd "$(dirname "$TARGET")/.." && pwd)"
  else
    echo "找不到指定路径: $TARGET"
    exit 1
  fi
else
  LATEST_FULL_MD="$(find "$RUNS_DIR" -path '*/output/full.md' -type f | sort | tail -n 1)"
  if [ -z "$LATEST_FULL_MD" ]; then
    echo "没有找到可续跑的 full.md"
    exit 1
  fi
  RUN_ROOT="$(cd "$(dirname "$LATEST_FULL_MD")/.." && pwd)"
fi

FULL_MD="$RUN_ROOT/output/full.md"
ZH_MD="$RUN_ROOT/output/zh.md"
TRANSLATOR_LOG="$RUN_ROOT/logs/translator.log"

if [ ! -f "$FULL_MD" ]; then
  echo "未找到英文 Markdown: $FULL_MD"
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -c "from pathlib import Path; from utils.translator import translator; run_root=Path('$RUN_ROOT'); print(translator.translate(run_root/'output'/'full.md', run_root/'output'/'zh.md', run_root=run_root, log_path=run_root/'logs'/'translator.log'))"
