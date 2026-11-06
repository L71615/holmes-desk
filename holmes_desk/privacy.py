"""自查模式下的脱敏：把「关于我自己的」细节打码，只留结构。

自己做自查（查自己的账号）时，屏幕上、报告里不需要出现完整邮箱、IM 账号、
个人站点域名——知道「有几个、在哪一类」就够了。这里只做字符串遮蔽，
不改变任何统计口径，所以数量、档案、覆盖这些结论仍然是准的。
"""

from __future__ import annotations

import copy
import re

_EMAIL_RE = re.compile(r"^([^@]{1,2})[^@]*(@.*)$")

# 大厂邮箱域名保留，域名像 alexzhang.dev 这种自建域则连域名一起打码
KNOWN_PROVIDERS = {
    "gmail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com",
    "icloud.com", "qq.com", "163.com", "126.com", "foxmail.com", "proton.me",
    "protonmail.com", "gmx.com", "mail.ru", "yandex.ru",
}


def mask_email(value: str) -> str:
    match = _EMAIL_RE.match(value or "")
    if not match:
        return mask_token(value)
    domain = match.group(2).lstrip("@").lower()
    tail = match.group(2) if domain in KNOWN_PROVIDERS else "@" + mask_domain(domain)
    return f"{match.group(1)}***{tail}"


def mask_token(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    keep = 2 if len(text) > 6 else 1
    return text[:keep] + "***"


def mask_handle(value: str) -> str:
    """'Telegram: someone' → 'Telegram: so***'。"""
    if ":" not in value:
        return mask_token(value)
    kind, handle = value.split(":", 1)
    return f"{kind.strip()}: {mask_token(handle.strip())}"


def mask_domain(value: str) -> str:
    parts = (value or "").split(".")
    if len(parts) <= 1:
        return mask_token(value)
    head = parts[0]
    kept = head[:2] if len(head) > 3 else head[:1]
    return ".".join([kept + "***"] + parts[1:])


def _mask_pairs(pairs, masker) -> list[tuple[str, int]]:
    return [(masker(value), count) for value, count in pairs]


def redact_persona(persona: dict) -> dict:
    """返回脱敏后的副本：字段与冲突打码，统计数字原样保留。"""
    from .persona import summary_text

    masked = copy.deepcopy(persona)
    fields = masked.get("fields", {})
    fields["emails"] = _mask_pairs(fields.get("emails", []), mask_email)
    fields["ims"] = _mask_pairs(fields.get("ims", []), mask_handle)
    fields["domains"] = _mask_pairs(fields.get("domains", []), mask_domain)
    masked["fields"] = fields

    for item in masked.get("conflicts", []):
        if item.get("field") == "邮箱":
            item["values"] = [mask_email(value) for value in item["values"]]

    masked["redacted"] = True
    masked["summary"] = summary_text(masked)
    return masked
