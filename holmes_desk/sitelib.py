"""站点库：分组、备注名、启用状态、自定义站点。

内置站点表（data.json）始终只读，用户的所有改动都落在
``%APPDATA%\\HolmesDesk\\sites_user.json``：

.. code-block:: json

    {
      "version": 1,
      "groups": {"常用": ["GitHub", "GitLab"]},
      "labels": {"GitHub": "代码托管"},
      "disabled": ["SomeSite"],
      "custom": {"我的站点": {"url": "https://x.com/{}", "errorType": "message", ...}}
    }

``custom`` 里的同名条目会覆盖内置站点，用来修正上游写错的判定规则。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from . import config
from .paths import SITE_DATA_PATH
from .presets import PRESETS

DEFAULT_GROUP = "未分组"

# 首次运行时的分组种子（站点名与 data.json 完全一致）
GROUP_SEEDS: dict[str, list[str]] = {
    "常用": list(PRESETS["常用（25 站）"]),
    "开发 / 代码": list(PRESETS["开发 / 代码"]),
    "安全 / CTF": list(PRESETS["安全 / CTF"]),
    "社交 / 社区": list(PRESETS["社交 / 社区"]),
    "游戏": list(PRESETS["游戏"]),
    "影音 / 创作": list(PRESETS["影音 / 创作"]),
}

ERROR_TYPES = ("status_code", "message", "response_url")
ERROR_TYPE_TEXT = {
    "status_code": "状态码",
    "message": "页面关键字",
    "response_url": "跳转地址",
}


def validate_site(name: str, info: dict[str, Any]) -> list[str]:
    """检查一条站点定义，返回问题列表（空 = 合法）。"""
    problems: list[str] = []
    if not name.strip():
        problems.append("站点名不能为空")
    if "," in name or "，" in name:
        problems.append("站点名不能带逗号（会破坏搜索框的解析）")
    url = str(info.get("url") or "").strip()
    if not url:
        problems.append("缺少 url 模板")
    elif "{}" not in url:
        problems.append("url 里要用 {} 占位符代表用户名")
    elif not url.lower().startswith(("http://", "https://")):
        problems.append("url 必须以 http:// 或 https:// 开头")
    error_type = str(info.get("errorType") or "status_code")
    if error_type not in ERROR_TYPES:
        problems.append(f"errorType 必须是 {'/'.join(ERROR_TYPES)} 之一")
    if error_type == "message" and not str(info.get("errorMsg") or "").strip():
        problems.append("关键字模式必须填写 errorMsg")
    if error_type in ("status_code", "response_url"):
        code = info.get("errorCode")
        if code not in (None, "") and error_type == "status_code":
            try:
                int(code)
            except (TypeError, ValueError):
                problems.append("errorCode 必须是整数状态码")
    return problems


class SiteLibrary:
    """内置站点表 + 用户改动的合并视图。"""

    def __init__(self, base_path: Path | str | None = None, user_path: Path | str | None = None) -> None:
        self.base_path = Path(base_path or SITE_DATA_PATH)
        self.user_path = Path(user_path) if user_path else config.config_dir() / "sites_user.json"
        self.base: dict[str, dict[str, Any]] = {}
        self.custom: dict[str, dict[str, Any]] = {}
        self.disabled: set[str] = set()
        self.labels: dict[str, str] = {}
        self.groups: dict[str, list[str]] = {}
        self.load()

    # ---------- 读写 ----------
    def load(self) -> None:
        self._load_base()
        raw: dict[str, Any] = {}
        if self.user_path.exists():
            try:
                raw = json.loads(self.user_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        if not isinstance(raw, dict):
            raw = {}

        custom = raw.get("custom")
        self.custom = {
            str(k): dict(v)
            for k, v in (custom or {}).items()
            if isinstance(v, dict) and str(k).strip()
        }

        disabled = raw.get("disabled")
        self.disabled = set(str(x) for x in (disabled or []) if str(x).strip())

        labels = raw.get("labels")
        self.labels = {
            str(k): str(v) for k, v in (labels or {}).items() if str(k).strip() and str(v).strip()
        }

        groups = raw.get("groups")
        if isinstance(groups, dict):
            self.groups = {
                str(name): [str(x) for x in (members or []) if str(x).strip()]
                for name, members in groups.items()
                if str(name).strip()
            }
        else:
            self.groups = {name: list(members) for name, members in GROUP_SEEDS.items()}

        self._tidy()

    def _load_base(self) -> None:
        data = json.loads(self.base_path.read_text(encoding="utf-8"))
        data.pop("$schema", None)
        self.base = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def save(self) -> None:
        payload = {
            "version": 1,
            "groups": {name: members for name, members in self.groups.items() if members},
            "labels": self.labels,
            "disabled": sorted(self.disabled),
            "custom": self.custom,
        }
        try:
            self.user_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.user_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.user_path)
        except OSError:
            # 站点库改动存不下来时不该炸掉界面，本次会话里照常生效即可
            pass

    def _tidy(self) -> None:
        """去掉失效的组成员和禁名单，避免 data.json 变动后留下垃圾。"""
        names = set(self.base) | set(self.custom)
        self.disabled &= names
        self.labels = {k: v for k, v in self.labels.items() if k in names}
        cleaned: dict[str, list[str]] = {}
        seen: set[str] = set()
        for group, members in self.groups.items():
            kept = []
            for name in members:
                if name in names and name not in seen:
                    kept.append(name)
                    seen.add(name)
            if kept:
                cleaned[group] = kept
        self.groups = cleaned

    # ---------- 查询 ----------
    @property
    def sites(self) -> dict[str, dict[str, Any]]:
        merged = dict(self.base)
        merged.update(self.custom)
        return merged

    def names(self) -> list[str]:
        return list(self.sites)

    def count(self) -> int:
        return len(self.sites)

    def info(self, name: str) -> dict[str, Any] | None:
        return self.sites.get(name)

    def label(self, name: str) -> str:
        return self.labels.get(name, name)

    def is_custom(self, name: str) -> bool:
        return name in self.custom

    def is_overridden(self, name: str) -> bool:
        return name in self.custom and name in self.base

    def is_enabled(self, name: str) -> bool:
        return name not in self.disabled

    def enabled_names(self) -> list[str]:
        return [n for n in self.names() if n not in self.disabled]

    def group_names(self) -> list[str]:
        """按显示顺序返回分组名，未分组永远在最后。"""
        groups = [g for g in self.groups if g != DEFAULT_GROUP]
        if DEFAULT_GROUP in self.groups or self.ungrouped():
            groups.append(DEFAULT_GROUP)
        return groups

    def members(self, group: str) -> list[str]:
        if group == DEFAULT_GROUP:
            return self.ungrouped()
        return list(self.groups.get(group, []))

    def ungrouped(self) -> list[str]:
        assigned = {name for members in self.groups.values() for name in members}
        return [n for n in self.names() if n not in assigned]

    def group_of(self, name: str) -> str:
        for group, members in self.groups.items():
            if name in members:
                return group
        return DEFAULT_GROUP

    def search(self, keyword: str) -> list[str]:
        key = keyword.strip().lower()
        if not key:
            return self.names()
        hits = []
        for name in self.names():
            info = self.sites[name]
            haystack = " ".join(
                [name, self.label(name), str(info.get("url") or ""), self.group_of(name)]
            ).lower()
            if key in haystack:
                hits.append(name)
        return hits

    # ---------- 分组 ----------
    def add_group(self, group: str) -> bool:
        group = group.strip()
        if not group or group == DEFAULT_GROUP or group in self.groups:
            return False
        self.groups[group] = []
        return True

    def remove_group(self, group: str) -> bool:
        if group == DEFAULT_GROUP or group not in self.groups:
            return False
        self.groups.pop(group, None)
        return True

    def rename_group(self, old: str, new: str) -> bool:
        new = new.strip()
        if old not in self.groups or not new or new in self.groups or new == DEFAULT_GROUP:
            return False
        self.groups = {(new if g == old else g): m for g, m in self.groups.items()}
        return True

    def set_group(self, name: str, group: str) -> None:
        """站点只归属一个分组：先从其它组摘掉，再加到目标组。"""
        if group != DEFAULT_GROUP:
            self.add_group(group)
        for members in self.groups.values():
            while name in members:
                members.remove(name)
        if group != DEFAULT_GROUP:
            self.groups.setdefault(group, []).append(name)
        self._drop_empty_groups()

    def _drop_empty_groups(self) -> None:
        for group in [g for g, m in self.groups.items() if not m]:
            if group != DEFAULT_GROUP:
                self.groups.pop(group, None)

    # ---------- 站点增删改 ----------
    def set_enabled(self, name: str, enabled: bool) -> None:
        if enabled:
            self.disabled.discard(name)
        else:
            self.disabled.add(name)

    def add_site(self, name: str, info: dict[str, Any], group: str = DEFAULT_GROUP) -> None:
        name = name.strip()
        problems = validate_site(name, info)
        if problems:
            raise ValueError("；".join(problems))
        self.custom[name] = dict(info)
        self.set_group(name, group)

    def update_site(self, name: str, info: dict[str, Any]) -> None:
        problems = validate_site(name, info)
        if problems:
            raise ValueError("；".join(problems))
        self.custom[name] = dict(info)

    def remove_site(self, name: str) -> None:
        """自定义站点直接删掉；内置站点只取消启用（不碰 data.json）。"""
        if name in self.custom:
            self.custom.pop(name, None)
            for members in self.groups.values():
                while name in members:
                    members.remove(name)
            self.disabled.discard(name)
            self.labels.pop(name, None)
            self._drop_empty_groups()
        else:
            self.disabled.add(name)

    def reset_site(self, name: str) -> None:
        """撤掉对内置站点的覆盖/禁用，恢复成 data.json 原样。"""
        self.custom.pop(name, None)
        self.disabled.discard(name)
        self.labels.pop(name, None)

    def set_label(self, name: str, label: str) -> None:
        label = label.strip()
        if label:
            self.labels[name] = label
        else:
            self.labels.pop(name, None)

    # ---------- 导入导出 ----------
    def export_to(self, path: Path | str) -> None:
        self.save()
        target = Path(path)
        target.write_text(self.user_path.read_text(encoding="utf-8"), encoding="utf-8")

    def import_from(self, path: Path | str) -> dict[str, int]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("文件内容不是站点库格式（需要一个 JSON 对象）")
        added_sites = updated_sites = added_groups = 0

        for name, info in (raw.get("custom") or {}).items():
            if not isinstance(info, dict):
                continue
            if validate_site(str(name), info):
                continue
            if str(name) in self.custom:
                updated_sites += 1
            else:
                added_sites += 1
            self.custom[str(name)] = dict(info)

        for group, members in (raw.get("groups") or {}).items():
            group = str(group).strip()
            if not group:
                continue
            if self.add_group(group):
                added_groups += 1
            for name in members or []:
                if name in self.sites:
                    self.set_group(str(name), group)

        for name, label in (raw.get("labels") or {}).items():
            if name in self.sites:
                self.set_label(str(name), str(label))

        self.disabled |= {str(x) for x in (raw.get("disabled") or []) if x in self.sites}
        self._tidy()
        return {"added_sites": added_sites, "updated_sites": updated_sites, "added_groups": added_groups}

    # ---------- 供检索使用 ----------
    def selection(self, groups: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
        """按分组取站点定义（只取启用的）。"""
        if not groups:
            chosen = self.enabled_names()
        else:
            chosen = []
            for group in groups:
                for name in self.members(group):
                    if name not in chosen and self.is_enabled(name):
                        chosen.append(name)
        return {name: self.sites[name] for name in chosen if name in self.sites}
