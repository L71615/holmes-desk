"""phonenumbers（手机号解析）这个可选依赖的检测与一键安装。

手机号解析本身是纯离线的，但依赖一个 2.5 MB 的号码库。为了「打开即用」，
这里做了三件事：

1. 启动时把「随程序分发」的 vendor 目录加进 sys.path（打包版会带上它）；
2. 检测不到时，界面上给一个按钮，pip 装到配置目录下的 vendor 子目录，
   不碰系统 Python、不需要管理员权限；
3. 装完立刻生效，不用重启。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import config

REQUIREMENT = "phonenumbers>=8.13"
VENDOR_NAME = "vendor"


def vendor_dir() -> Path:
    return Path(config.config_dir()) / VENDOR_NAME


def ensure_path() -> Path:
    """把 vendor 目录塞进 sys.path（幂等）。"""
    path = vendor_dir()
    if path.is_dir():
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    return path


def available() -> bool:
    ensure_path()
    try:
        importlib.import_module("phonenumbers")
    except Exception:  # noqa: BLE001 - 装坏了也当作没装
        return False
    return True


def install(on_line: Callable[[str], None] | None = None, timeout: int = 300) -> tuple[bool, str]:
    """把 phonenumbers 装到 vendor 目录，返回 (成功, 说明)。"""
    target = vendor_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"建不了目录 {target}：{exc}"

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(target),
        REQUIREMENT,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"调用 pip 失败：{exc}"

    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if on_line is not None:
        for line in out.splitlines()[-6:]:
            on_line(line)
    if proc.returncode != 0:
        return False, out.splitlines()[-1] if out else f"pip 退出码 {proc.returncode}"

    ensure_path()
    # 新装进去的包要被 import 看到，清一下导入缓存
    importlib.invalidate_caches()
    if not available():
        return False, "安装命令成功，但仍导入不了 phonenumbers"
    return True, "已安装"
