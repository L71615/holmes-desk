"""设置持久化。

默认存到 ``%APPDATA%\\HolmesDesk\\config.json``；如果那里写不进去（企业策略、
Defender 受控文件夹访问、只读配置盘……），会依次退到 ``%LOCALAPPDATA%``、
程序目录下的 ``.holmesdesk``、临时目录，最后用系统临时目录兜底。

原则：**配置存哪里都不该阻断启动**，所以这里不抛异常。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "usernames": "",
    "sites": "",
    "preset": "全部站点",
    "proxy": "",
    "timeout": 20,
    "include_nsfw": False,
    "show_all": False,
    "local_sites": True,
    "self_usernames": "L71615",
    "self_only": False,
    "export_txt": True,
    "export_csv": True,
    "export_xlsx": False,
    "export_html": False,
    "export_jsonl": False,
    "out_dir": "",
    "geometry": "",
}


def _candidates() -> list[Path]:
    """按优先级列出配置目录候选。"""
    override = os.environ.get("HOLMES_DESK_HOME")
    if override:
        return [Path(override).expanduser()]

    if sys.platform == "win32":
        bases = [
            os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"),
            os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"),
        ]
    else:
        bases = [os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")), "/tmp"]

    dirs = [Path(base) / "HolmesDesk" for base in bases]
    # 程序目录（解压到哪就在哪放一份，用户可见、基本一定可写）
    dirs.append(Path(__file__).resolve().parent.parent / ".holmesdesk")
    # 系统临时目录（最后手段，重启会清）
    dirs.append(Path(tempfile.gettempdir()) / "HolmesDesk")
    return dirs


_DIR_CACHE: Path | None = None
_DIR_ERROR = ""


def _usable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def config_dir() -> Path:
    """配置目录；第一个能写的候选胜出。

    全都不行时返回一个新建的临时目录 —— 宁可这次运行不记住设置，也不要打不开界面。
    """
    global _DIR_CACHE, _DIR_ERROR
    if _DIR_CACHE is not None:
        return _DIR_CACHE

    errors: list[str] = []
    for candidate in _candidates():
        if _usable(candidate):
            if errors:
                _DIR_ERROR = "配置目录不可写，已改用 " + str(candidate)
            _DIR_CACHE = candidate
            return candidate
        errors.append(str(candidate))

    try:
        fallback = Path(tempfile.mkdtemp(prefix="holmesdesk-"))
        _DIR_ERROR = "配置目录全部不可写，本次使用临时目录 " + str(fallback)
        _DIR_CACHE = fallback
        return fallback
    except OSError:  # 兜到底还是不行，也只能给个占位路径
        home = Path.home() / ".holmesdesk"
        _DIR_ERROR = "配置目录不可写，设置将不会保存（" + "；".join(errors) + "）"
        _DIR_CACHE = home
        return home


def config_path() -> Path:
    return config_dir() / "config.json"


def config_dir_error() -> str:
    """如果换了目录，这里有一句人类可读的原因；正常情况是空串。"""
    config_dir()
    return _DIR_ERROR


def load() -> dict[str, Any]:
    """读取配置；文件不存在或损坏时退回默认值。"""
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data.update(json.load(fh))
    except Exception:  # noqa: BLE001 - 配置坏了不该阻断启动
        pass
    return data


def save(data: dict[str, Any]) -> None:
    """原子写入；写失败只忽略，不弹错（设置丢了比程序崩了好）。"""
    try:
        target = config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError:
        pass
