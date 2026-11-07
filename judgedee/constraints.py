"""人工纠正记录：把「这两个是同一个人 / 不是同一个人」记住。

账号用 `站点|用户名` 作为键，存成 must（必须合并）与 cannot（必须分开）两组。
下一次聚类会先按 must 强行并组、并拒绝任何触碰 cannot 的合并；换台机器把
这个 json 拷过去也一样生效。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def key_of(site: str, username: str) -> str:
    return f"{site}|{username}"


def _pair(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


class Constraints:
    """must-link / cannot-link 约束集合。"""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from .config import config_dir

            path = Path(config_dir()) / "constraints.json"
        self.path = Path(path)
        self.must: set[frozenset[str]] = set()
        self.cannot: set[frozenset[str]] = set()
        self.load()

    # ---------- 持久化 ----------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.must = {frozenset(pair) for pair in raw.get("must", []) if len(pair) == 2}
        self.cannot = {frozenset(pair) for pair in raw.get("cannot", []) if len(pair) == 2}
        self.must = {p for p in self.must if len(p) == 2}

    def save(self) -> None:
        data = {
            "version": 1,
            "must": [sorted(pair) for pair in self.must if len(pair) == 2],
            "cannot": [sorted(pair) for pair in self.cannot if len(pair) == 2],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---------- 编辑 ----------
    def add_must(self, a: str, b: str) -> None:
        if a == b:
            return
        pair = _pair(a, b)
        self.cannot.discard(pair)
        self.must.add(pair)
        self.save()

    def add_cannot(self, a: str, b: str) -> None:
        if a == b:
            return
        pair = _pair(a, b)
        self.must.discard(pair)
        self.cannot.add(pair)
        self.save()

    def remove(self, a: str, b: str) -> None:
        pair = _pair(a, b)
        self.must.discard(pair)
        self.cannot.discard(pair)
        self.save()

    def clear(self) -> None:
        self.must.clear()
        self.cannot.clear()
        self.save()

    # ---------- 查询 ----------
    def for_key(self, key: str) -> tuple[list[str], list[str]]:
        must_partners = sorted(other for pair in self.must if key in pair for other in pair if other != key)
        cannot_partners = sorted(
            other for pair in self.cannot if key in pair for other in pair if other != key
        )
        return must_partners, cannot_partners

    def describe(self) -> list[str]:
        lines: list[str] = []
        for pair in sorted(self.must, key=sorted):
            left, right = sorted(pair)
            lines.append(f"同一人：{left} ↔ {right}")
        for pair in sorted(self.cannot, key=sorted):
            left, right = sorted(pair)
            lines.append(f"不同人：{left} ↔ {right}")
        return lines

    def __len__(self) -> int:
        return len(self.must) + len(self.cannot)
