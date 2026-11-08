#!/usr/bin/env python3
"""WorldForge 世界工坊 — Mac 本地服务入口。

    python3 forge.py [--port 7788] [--open]

仅依赖 Python 3 标准库。
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forge_local import VERSION, config  # noqa: E402
from forge_local.app import App  # noqa: E402
from forge_local.server import make_server  # noqa: E402


def open_browser(url):
    """优先以 Chrome App 模式打开（无地址栏的独立窗口），否则用默认浏览器。"""
    r = subprocess.run(["open", "-na", "Google Chrome", "--args", "--app=" + url],
                       capture_output=True)
    if r.returncode != 0:
        subprocess.run(["open", url])


def main():
    ap = argparse.ArgumentParser(description="WorldForge 世界工坊 本地服务")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    ap.add_argument("--no-auto-tunnel", action="store_true", help="启动时不自动连接已存在的会话")
    args = ap.parse_args()

    app = App()
    app.auto_tunnel = not args.no_auto_tunnel
    try:
        httpd = make_server(app, args.host, args.port)
    except OSError as e:
        url = "http://%s:%d" % (args.host, args.port)
        print("✗ 无法监听 %s：%s（可能已有一个 WorldForge 在运行）" % (url, e))
        if args.open:
            open_browser(url)
        sys.exit(1)

    url = "http://%s:%d" % (args.host, args.port)
    print("""
  ╦ ╦┌─┐┬─┐┬  ┌┬┐╔═╗┌─┐┬─┐┌─┐┌─┐   世界工坊 v%s
  ║║║│ │├┬┘│   ││╠╣ │ │├┬┘│ ┬├┤
  ╚╩╝└─┘┴└─┴─┘─┴┘╚  └─┘┴└─└─┘└─┘   %s

  作品目录: %s
  设置文件: %s
  按 Ctrl+C 退出
""" % (VERSION, url, app.settings.get("output_dir"), config.SETTINGS_FILE))

    app.start()

    def stop(*_):
        print("\n正在退出 …")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)

    if args.open:
        threading.Timer(0.6, open_browser, [url]).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        app.shutdown()
        httpd.server_close()
        time.sleep(0.2)
        print("已退出。远端 Colab 会话保持运行（空闲看门狗不再生效，请记得在不用时释放）。")


if __name__ == "__main__":
    main()
