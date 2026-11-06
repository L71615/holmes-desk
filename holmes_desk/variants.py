"""用户名变体生成。

同一个人在不同站点往往不用同一个 ID：``alice`` / ``a_zhang`` / ``alicez`` /
``alice.zhang`` 可能是同一个人。第一次检索只知道一个字面量，这里负责把
「可能还是他」的其他写法列出来，交给第二轮检索去验证。

全部是本地字符串操作，不发任何请求、不依赖外部服务。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_RE = re.compile(r"^[a-z0-9._-]+$")
SPLIT_RE = re.compile(r"[\s._\-]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

SEPARATORS = ("", ".", "_", "-")
MIN_LEN = 3
MAX_LEN = 30


@dataclass(frozen=True)
class Variant:
    """一个待验证的用户名写法。"""

    username: str
    source: str  # 从哪个用户名 / 昵称派生出来
    reason: str  # 为什么觉得它可能是同一个人


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "", (text or "").strip().lower())


def _usable(candidate: str) -> bool:
    if not (MIN_LEN <= len(candidate) <= MAX_LEN):
        return False
    if not ALLOWED_RE.match(candidate):
        return False
    return any(ch.isalpha() for ch in candidate)


def _pieces(text: str) -> list[str]:
    return [p for p in SPLIT_RE.split((text or "").strip().lower()) if p]


def _join(parts: list[str], sep: str) -> str:
    return sep.join(p for p in parts if p)


def from_username(username: str) -> list[tuple[str, str]]:
    """从一个用户名派生出写法变体：换分隔符、去掉分隔符、缩写。"""
    out: list[tuple[str, str]] = []
    base = _clean(username)
    if not base:
        return out
    parts = _pieces(username)

    if len(parts) >= 2:
        for sep in SEPARATORS:
            out.append((_join(parts, sep), f"换分隔符「{sep or '无'}」"))
        # 名 + 姓首字母 / 姓 + 名首字母
        out.append((parts[0] + parts[1][0], "名字 + 姓氏首字母"))
        out.append((parts[0][0] + parts[1], "名字首字母 + 姓氏"))
        out.append((parts[1] + parts[0], "姓氏在前"))
    else:
        # 单个词：只做大小写无关的去重，不硬凑
        out.append((base, "统一小写"))

    return out


def from_display_name(name: str) -> list[tuple[str, str]]:
    """从昵称派生：常见「名.姓」「名姓」「首字母+姓」等组合。"""
    out: list[tuple[str, str]] = []
    if not name or CJK_RE.search(name):
        # 中文昵称没法可靠转拼音，直接跳过，等用户手动补
        return out
    parts = _pieces(name)
    if len(parts) < 2:
        if parts:
            out.append((parts[0], "昵称原文"))
        return out

    first, last = parts[0], parts[-1]
    for sep in SEPARATORS:
        out.append((_join([first, last], sep), "名 + 姓"))
    for sep in ("", ".", "_", "-"):
        out.append((_join([last, first], sep), "姓 + 名"))
    out.append((first[0] + last, "名字首字母 + 姓氏"))
    out.append((first + last[0], "名字 + 姓氏首字母"))
    out.append((first[0] + last[0], "双首字母"))
    if len(parts) > 2:  # 中间名参与
        out.append((_join(parts, ""), "去掉所有分隔符"))
    return out


def generate(
    usernames: list[str],
    display_names: list[str] | None = None,
    limit: int = 60,
) -> list[Variant]:
    """合成变体列表：去重、排除原始用户名、按长度排序（短的优先试）。"""
    originals = {_clean(u) for u in usernames if u}
    seen: dict[str, Variant] = {}

    def collect(pairs: list[tuple[str, str]], source: str) -> None:
        for raw, reason in pairs:
            candidate = _clean(raw)
            if not _usable(candidate) or candidate in originals or candidate in seen:
                continue
            seen[candidate] = Variant(candidate, source, reason)

    for username in usernames:
        if username:
            collect(from_username(username), username)
    for name in display_names or []:
        if name:
            collect(from_display_name(name), name)

    ordered = sorted(seen.values(), key=lambda v: (len(v.username), v.username))
    return ordered[: max(1, limit)]


def describe(variants: list[Variant]) -> str:
    """一句话概括，给状态栏用。"""
    if not variants:
        return "没有可尝试的变体"
    names = "、".join(v.username for v in variants[:4])
    more = f" 等 {len(variants)} 个" if len(variants) > 4 else ""
    return f"{names}{more}"
