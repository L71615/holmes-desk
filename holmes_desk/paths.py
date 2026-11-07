"""资源定位：源码运行与 PyInstaller 打包后都能找到数据文件。"""

from __future__ import annotations

import sys
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """返回随程序分发的资源路径（assets / data）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "holmes_desk" / Path(*parts)
    return PKG_DIR / Path(*parts)


def app_dir() -> Path:
    """程序所在目录（打包后是 exe 目录，源码模式是仓库根目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PKG_DIR.parent


SITE_DATA_PATH = resource_path("data", "data.json")
ICON_PATH = resource_path("assets", "holmesdesk.ico")
EXE_ICON_PATH = resource_path("assets", "holmesdesk-app.ico")
