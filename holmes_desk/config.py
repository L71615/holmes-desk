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


def _candidates() -> list[Path]:
    """按优先级列出配置目录候选：APPDATA → LOCALAPPDATA → 临时目录。"""
    override = os.environ.get("HOLMES_DESK_HOME")
    if override:
        return [Path(override).expanduser()]
    if sys.platform == "win32":
        bases = [
            os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"),
            os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"),
            os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home()),
        ]
        return [Path(base) / "HolmesDesk" for base in bases]
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [base / "holmes-desk", Path(os.environ.get("TMPDIR", "/tmp")) / "holmes-desk"]


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
    """配置目录；第一个能写的候选胜出，全都不行才抛错。

    设了 HOLMES_DESK_HOME 就只用它（便携模式/测试用）。
    """
    global _DIR_CACHE, _DIR_ERROR
    if _DIR_CACHE is not None:
        return _DIR_CACHE
    errors: list[str] = []
    fallback = None
    for candidate in _candidates():
        if fallback is None:
            fallback = candidate
        if _usable(candidate):
            if errors:
                _DIR_ERROR = "配置目录不可写，已改用 " + str(candidate) + "（" + "；".join(errors) + "）"
            _DIR_CACHE = candidate
            return candidate
        errors.append(f"{candidate}: 拒绝访问")
    raise RuntimeError(
        "找不到可写的配置目录：" + ("；".join(errors) or "无候选") + f"（已尝试 {fallback}）"
    )


def config_path() -> Path:
    return config_dir() / "config.json"


def config_dir_error() -> str:
    """如果换了目录，这里有一句人类可读的原因；正常情况是空串。"""
    return _DIR_ERROR


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
