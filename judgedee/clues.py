"""线索卡：把「这个人」身上的可查信息收进一张表。

来源有两类：
1. 自动——人物看板里已经合并出来的邮箱、即时通讯、个人站点域名；
2. 手动——你把一个 IP 或手机号贴进来，用追踪页同款逻辑解析，结果记在这张卡上。

线索卡只是「展示 + 汇总」，判定权仍在人手里；它会被带进 HTML 报告，
方便一份报告里同时看到「是谁」和「在哪」。
"""

from __future__ import annotations

from typing import Any, Iterable

# 线索种类 -> 中文标签（顺序即展示顺序）
KIND_LABELS = {
    "email": "邮箱",
    "im": "即时通讯",
    "domain": "个人站点",
    "ip": "IP 归属地",
    "phone": "手机号归属地",
}

KIND_ORDER = ("email", "im", "domain", "ip", "phone")


def _entry(kind: str, value: str, note: str = "", hits: int = 1) -> dict[str, Any]:
    return {"kind": kind, "label": KIND_LABELS[kind], "value": value, "note": note, "hits": hits}


def from_persona(persona: dict | None) -> list[dict[str, Any]]:
    """把人物看板里合并好的字段转成线索条目。"""
    if not persona:
        return []
    fields = persona.get("fields") or {}
    out: list[dict[str, Any]] = []

    for value, hits in (fields.get("emails") or []):
        out.append(_entry("email", value, "主页公开", int(hits)))
    for value, hits in (fields.get("ims") or []):
        out.append(_entry("im", value, "主页公开", int(hits)))
    for value, hits in (fields.get("domains") or []):
        out.append(_entry("domain", value, "主页外链", int(hits)))
    return out


def ip_entry(result: dict[str, Any]) -> dict[str, Any] | None:
    """把 trace.lookup_ip 的结果压成一条线索。"""
    if not result or not result.get("ok"):
        return None
    fields = {name: value for name, value in (result.get("fields") or [])}
    ip = fields.get("IP") or ""
    if not ip:
        return None
    parts = [
        fields.get("国家") or "",
        fields.get("城市") or fields.get("地区") or "",
        fields.get("ISP") or fields.get("组织") or "",
    ]
    note = " · ".join(part for part in parts if part) or "无归属信息"
    return _entry("ip", ip, note)


def phone_entry(result: dict[str, Any]) -> dict[str, Any] | None:
    """把 trace.parse_phone 的结果压成一条线索。"""
    if not result or not result.get("ok"):
        return None
    number = result.get("e164") or ""
    if not number:
        return None
    parts = [result.get("location") or "", result.get("operator") or ""]
    note = " · ".join(part for part in parts if part) or "无归属信息"
    return _entry("phone", number, note)


def merge(entries: Iterable[dict[str, Any]], extra: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并线索，按种类排序，同种类内保持出现顺序，重复值只留第一条。"""
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in list(entries) + list(extra):
        key = (item.get("kind", ""), item.get("value", ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(item)
    rank = {kind: index for index, kind in enumerate(KIND_ORDER)}
    result.sort(key=lambda item: rank.get(item.get("kind", ""), len(rank)))
    return result


def summary(items: list[dict[str, Any]]) -> str:
    """一行话：各类线索各有几条。"""
    if not items:
        return "没有可用线索"
    counts: dict[str, int] = {}
    for item in items:
        label = item.get("label") or item.get("kind") or "?"
        counts[label] = counts.get(label, 0) + 1
    parts = [f"{label} {count}" for label, count in counts.items()]
    return " · ".join(parts)


def to_text(items: list[dict[str, Any]]) -> str:
    """给复制按钮用的纯文本。"""
    lines = []
    for item in items:
        note = item.get("note") or ""
        lines.append(f"{item['label']}: {item['value']}" + (f"（{note}）" if note else ""))
    return "\n".join(lines)
