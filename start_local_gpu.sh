#!/usr/bin/env bash
# ============================================================================
# WorldForge · 本地 RTX 4090 (24GB) / RTX 5090 (32GB) 一键直连启动脚本
# 无需安装 google-colab-cli，直接在本地 Linux / WSL2 / 局域网 GPU 主机上运行
# ============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORLDFORGE_ROOT="${WORLDFORGE_ROOT:-$HOME/worldforge_data}"
export FORGE_HOST="${FORGE_HOST:-0.0.0.0}"
export FORGE_PORT="${FORGE_PORT:-17860}"

mkdir -p "$WORLDFORGE_ROOT"

echo "============================================================"
echo " ⚡ WorldForge Local GPU Mode (RTX 4090 24GB / RTX 5090 32GB)"
echo " 📂 数据与模型目录: $WORLDFORGE_ROOT"
echo " 🌐 监听地址:       http://$FORGE_HOST:$FORGE_PORT"
echo "============================================================"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
fi

# 检查基础依赖 fastapi / uvicorn
if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "📦 正在安装基础服务依赖 (fastapi, uvicorn, huggingface_hub)..."
  python3 -m pip install -q fastapi uvicorn huggingface_hub hf_transfer safetensors
fi

echo "🚀 正在启动 WorldForge GPU 推理后端 (--local)..."
echo "💡 启动后，在本机运行 'python3 forge.py --open' 或在 Mac 上运行:"
echo "   python3 forge.py --gpu-url http://<本机局域网IP>:$FORGE_PORT --open"
echo "------------------------------------------------------------"

exec python3 "$ROOT_DIR/remote/forge_server.py" --local --host "$FORGE_HOST" --port "$FORGE_PORT" "$@"
