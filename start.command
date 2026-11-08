#!/bin/bash
# WorldForge 世界工坊 — 双击启动
cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:7788"

PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  echo "未找到 python3，请先安装：brew install python"
  read -n 1 -s -r -p "按任意键关闭…"
  exit 1
fi

open_ui() {
  open -na "Google Chrome" --args --app="$URL" 2>/dev/null || open "$URL"
}

# 已在运行：直接打开界面
if curl -s -m 2 "$URL/api/local/state" >/dev/null 2>&1; then
  echo "WorldForge 已在运行，打开界面…"
  open_ui
  exit 0
fi

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# 后台等待服务就绪后打开界面
(
  for i in $(seq 1 50); do
    if curl -s -m 1 "$URL/api/local/state" >/dev/null 2>&1; then open_ui; exit 0; fi
    sleep 0.2
  done
  open "$URL"
) &

exec "$PY" forge.py "$@"
