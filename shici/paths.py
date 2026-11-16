"""程序资源目录和用户数据目录。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import DATA_DIR_NAME


def resource_dir() -> Path:
    """随程序分发的只读文件（界面、词典）所在目录，兼容 PyInstaller 打包。"""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "shici" if base else Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """学习记录存放位置。可用环境变量 SHICI_DATA 指定别的目录。"""
    override = os.environ.get("SHICI_DATA")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / DATA_DIR_NAME
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / DATA_DIR_NAME
    else:
        p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / DATA_DIR_NAME.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p
