"""设置持久化：存到 %APPDATA%\\HolmesDesk\\config.json。

只存"下次打开还能用"的东西，不存检索结果（结果在 results 目录里）。
"""

from __future__ import annotations

import json
import os
import sys
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


def config_dir() -> Path:
    """配置目录；设了 HOLMES_DESK_HOME 就用它（便携模式/测试用）。"""
    override = os.environ.get("HOLMES_DESK_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "HolmesDesk"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "holmes-desk"


def config_path() -> Path:
    return config_dir() / "config.json"


CONFIG_PATH = config_path()


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
    """原子写入，避免中途退出留下半个 JSON。"""
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
