"""人物看板：把一堆账号拼成「一个人」，并给出能直接读的结论。

输入是身份分析的结果（accounts / clusters / review），输出是：

* 数量关系：账号数、档案数、待确认对数——回答「注册了多少个」；
* 类别覆盖：这个人出现在开发 / 社交 / 创作 / 游戏哪几类，缺口在哪；
* 字段合并：昵称、头像、邮箱、IM、个人站点，多站投票，冲突并排显示；
* 可信度与一段自然语言摘要。

只做聚合与措辞，不再发请求。
"""

from __future__ import annotations

import re
from collections import Counter

from .identity import Account, Cluster, site_category

CATEGORY_LABELS = {
    "dev": "开发",
    "social": "社交",
    "creative": "创作",
    "game": "游戏",
    "other": "其他",
}

CATEGORY_ORDER = ("dev", "social", "creative", "game", "other")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/\s?#]+)")

IM_PATTERNS = (
    (re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{3,})", re.I), "Telegram"),
    (re.compile(r"(?:https?://)?wa\.me/(\d{6,})", re.I), "WhatsApp"),
    (re.compile(r"(?:https?://)?discord\.(?:gg|com/invite)/([A-Za-z0-9-]{3,})", re.I), "Discord"),
    (re.compile(r"@([A-Za-z0-9_]{3,})\s*(?:on|@)?\s*(?:telegram|tg)\b", re.I), "Telegram"),
)

# 这些域名只是「跳板」，本身不代表身份，统计个人站点时降权
LINK_HUBS = {
    "linktr.ee", "linkr.bio", "beacons.ai", "carrd.co", "bio.link",
    "t.me", "discord.gg", "twitter.com", "x.com", "instagram.com",
}


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


def _domain(url: str) -> str:
    match = DOMAIN_RE.match((url or "").strip())
    return match.group(1).lower() if match else ""


def _iter_text(account: Account) -> list[str]:
    out = [account.bio or "", account.display_name or ""]
    out.extend(account.links or [])
    out.extend(account.mentions or [])
    return out


def collect_fields(accounts: list[Account]) -> dict:
    """从所有账号的昵称/简介/外链里抽字段，并统计每个取值有几个来源。"""
    names: Counter[str] = Counter()
    emails: Counter[str] = Counter()
    ims: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    langs: Counter[str] = Counter()
    usernames: Counter[str] = Counter()

    for account in accounts:
        if account.username:
            usernames[account.username.strip()] += 1
        # 有些站的 og:title 直接就是站名（Spotify / Discord），不是人的昵称
        if account.display_name and _norm(account.display_name) != _norm(account.site):
            names[account.display_name.strip()] += 1
        if account.lang:
            langs[account.lang.lower()] += 1
        for text in _iter_text(account):
            if not text:
                continue
            for email in EMAIL_RE.findall(text):
                emails[email.lower()] += 1
            for pattern, kind in IM_PATTERNS:
                for handle in pattern.findall(text):
                    ims[f"{kind}: {handle}"] += 1
            if text.lower().startswith("http"):
                domain = _domain(text)
                if domain:
                    domains[domain] += 1

    personal = {d: n for d, n in domains.items() if d not in LINK_HUBS}
    if personal:
        domains = Counter(personal)

    return {
        "names": names,
        "emails": emails,
        "ims": ims,
        "domains": domains,
        "langs": langs,
        "usernames": usernames,
    }


def coverage(sites: list[str]) -> list[dict]:
    """按类别统计覆盖，返回固定顺序的列表（含空类别）。"""
    buckets: dict[str, list[str]] = {key: [] for key in CATEGORY_ORDER}
    for site in sorted(set(sites)):
        buckets[site_category(site)].append(site)
    return [
        {
            "key": key,
            "label": CATEGORY_LABELS[key],
            "sites": buckets[key],
            "count": len(buckets[key]),
        }
        for key in CATEGORY_ORDER
    ]


def _avatar_count(accounts: list[Account]) -> int:
    hashes = {
        (a.avatar_a, a.avatar_d)
        for a in accounts
        if a.avatar_a is not None and a.avatar_d is not None
    }
    return len(hashes)


def _confidence(clusters: list[Cluster], coverage_rows: list[dict]) -> int:
    """可信度：档案内部一致度占七成，类别覆盖占三成。

    单账号档案没有一致度可言，按 0.55 计——不是「不可信」，只是证据少。
    """
    if clusters:
        scores = [(c.score if len(c.accounts) > 1 else 0.55) for c in clusters]
        avg = sum(scores) / len(scores)
    else:
        avg = 0.0
    covered = sum(1 for row in coverage_rows if row["count"])
    ratio = covered / len(CATEGORY_ORDER)
    return max(5, min(99, round(100 * (0.7 * avg + 0.3 * ratio))))


def build_persona(
    accounts: list[Account],
    clusters: list[Cluster],
    review: list[dict] | None = None,
) -> dict:
    """把身份分析结果整理成一屏能看完的看板数据。"""
    review = review or []
    sites = [a.site for a in accounts]
    rows = coverage(sites)
    fields = collect_fields(accounts)

    names = [n for n, _ in fields["names"].most_common(3)]
    usernames = fields["usernames"]
    top_username, same_name_count = usernames.most_common(1)[0] if usernames else ("", 0)
    headline = names[0] if names else (top_username or "未知")

    conflicts = []
    if len(fields["names"]) > 1:
        conflicts.append(
            {"field": "昵称", "values": [n for n, _ in fields["names"].most_common(4)]}
        )
    if len(fields["emails"]) > 1:
        conflicts.append(
            {"field": "邮箱", "values": [e for e, _ in fields["emails"].most_common(4)]}
        )

    persona = {
        "headline": headline,
        "username": top_username,
        "same_name_count": same_name_count,
        "account_count": len(accounts),
        "cluster_count": len(clusters),
        "single_count": sum(1 for c in clusters if len(c.accounts) == 1),
        "multi_count": sum(1 for c in clusters if len(c.accounts) > 1),
        "review_count": len(review),
        "avatar_count": _avatar_count(accounts),
        "coverage": rows,
        "covered_categories": sum(1 for row in rows if row["count"]),
        "fields": {
            "names": fields["names"].most_common(5),
            "emails": fields["emails"].most_common(5),
            "ims": fields["ims"].most_common(5),
            "domains": fields["domains"].most_common(5),
            "langs": fields["langs"].most_common(3),
        },
        "conflicts": conflicts,
        "sites": sorted(set(sites)),
        "confidence": _confidence(clusters, rows),
    }
    persona["summary"] = summary_text(persona)
    return persona


def summary_text(persona: dict) -> str:
    """把看板数据写成一段话，放进报告或直接念给人听。"""
    accounts = persona["account_count"]
    clusters = persona["cluster_count"]
    if not accounts:
        return "没有已注册的账号，无法拼出人物。"

    parts = [f"共 {accounts} 个已注册账号，归并成 {clusters} 个档案"]
    username = persona.get("username") or ""
    same = persona.get("same_name_count") or 0
    if username and same > 1:
        parts[0] = f"共 {accounts} 个已注册账号（用户名 {username} 出现 {same} 次），归并成 {clusters} 个档案"
    if persona["multi_count"]:
        parts.append(f"其中 {persona['multi_count']} 个档案由多个账号合并而来")
    if persona["review_count"]:
        parts.append(f"另有 {persona['review_count']} 组证据不足、待人工确认")
    if same > 1 and clusters == accounts:
        parts.append("这些账号用户名相同但主页证据还不足以自动合并，可在图谱页确认后合并")

    covered = [row["label"] for row in persona["coverage"] if row["count"]]
    missing = [row["label"] for row in persona["coverage"] if not row["count"]]
    if covered:
        detail = "、".join(
            f"{row['label']} {row['count']} 个" for row in persona["coverage"] if row["count"]
        )
        parts.append(f"分布在{detail}")
    if missing:
        parts.append(f"{'、'.join(missing)}方向没有痕迹")

    names = [n for n, _ in persona["fields"]["names"][:2] if n]
    if names:
        parts.append(f"常用昵称「{'」「'.join(names)}」")
    if persona["avatar_count"] > 1:
        parts.append(f"抓到的头像有 {persona['avatar_count']} 种，说明至少换过头像")
    elif persona["avatar_count"] == 1 and accounts > 1:
        parts.append("多个站用的是同一张头像")

    emails = [e for e, _ in persona["fields"]["emails"][:2]]
    if emails:
        parts.append(f"公开邮箱 {'、'.join(emails)}")

    parts.append(f"可信度 {persona['confidence']}/100")
    return "；".join(parts) + "。"
