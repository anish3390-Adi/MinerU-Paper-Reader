#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
TRANSLATOR_DIR="$ROOT_DIR/external/md-translator"

cd "$ROOT_DIR"

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

if ! command -v uv >/dev/null 2>&1; then
  echo "uv 未安装，无法初始化 Python 环境。"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node 未安装，无法构建 md-translator。"
  exit 1
fi

if ! command -v corepack >/dev/null 2>&1; then
  echo "corepack 未安装，无法安装 md-translator 依赖。"
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  uv venv "$ROOT_DIR/.venv"
fi

uv pip install --python "$VENV_PYTHON" -r "$ROOT_DIR/requirements.txt"

cd "$TRANSLATOR_DIR"
corepack yarn install
LOCAL_API_SERVER=true corepack yarn build

echo
echo "初始化完成。"
echo "接下来请填写 $ROOT_DIR/.env 里的 API key，然后运行 ./scripts/start_macos.sh"
