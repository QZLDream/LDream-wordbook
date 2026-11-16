"""启动入口：python -m shici

    python -m shici             打开桌面窗口
    python -m shici --browser   不用桌面窗口，在默认浏览器里打开（没装 PySide6 时会自动这样做）
    python -m shici --data DIR  把学习记录放在指定文件夹
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from . import APP_NAME, __version__
from .core import Core
from .server import Server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shici", description=f"{APP_NAME} {__version__}：基于 FSRS 遗忘曲线的背单词程序")
    ap.add_argument("--browser", action="store_true", help="在默认浏览器里打开，而不是桌面窗口")
    ap.add_argument("--port", type=int, default=0, help="本机端口，默认自动选择")
    ap.add_argument("--data", help="学习记录所在文件夹")
    ap.add_argument("--no-open", action="store_true", help="配合 --browser：只打印地址，不自动打开")
    a = ap.parse_args(argv)

    core = Core(a.data)
    server = Server(core, port=a.port)
    server.start()
    try:
        if not a.browser:
            try:
                from .desktop import run
            except ImportError as e:
                print(f"没有找到 PySide6（{e}），改为在浏览器里打开。安装：pip install PySide6", file=sys.stderr)
            else:
                return run(core, server)
        print(f"{APP_NAME} 正在运行：{server.url}\n按 Ctrl+C 退出。", flush=True)
        if not a.no_open:
            webbrowser.open(server.url)
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()
        core.close()


if __name__ == "__main__":
    sys.exit(main())
