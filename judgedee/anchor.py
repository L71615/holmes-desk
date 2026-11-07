"""基准账号扫描：给一个确定的账号，顺着它去找同一个人。

和「检索」的区别：检索是「这个名字在哪些站存在」，这里多一个前提——**我知道其中一个是本人**。
于是可以把每个候选账号和种子账号做证据比对，得出一条可解释的结论：

    这个站上的 alice 和 github.com/alice 是同一个人（头像 0.96、昵称一致）

三个候选来源：
1. 同名：种子用户名在别的站点也存在；
2. 变体：从种子的昵称派生出用户名变体（Alice Zhang → alicezhang / a_zhang …）；
3. 外链：种子主页上指向的个人站点域名。

打分和身份图谱用同一套信号，但权重按「以谁为准」重新分配：头像 0.35、昵称 0.25、
简介 0.20、外链 0.20，另有负证据（头像明显不同 −0.40、昵称不同且简介为空 −0.15）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from . import engine, profile, variants
from .identity import (
    Account,
    avatar_similarity,
    bio_similarity,
    link_score,
    name_similarity,
)

STRONG = 0.62
REVIEW = 0.45
MAX_CANDIDATES = 60
MAX_FETCH = 40
MAX_VARIANTS = 6

WEIGHTS = {
    "avatar": 0.35,
    "name": 0.25,
    "bio": 0.20,
    "link": 0.20,
}

PENALTY_DIFFERENT_AVATAR = -0.40
PENALTY_EMPTY_BIO = -0.15

SOURCE_SAME = "同名"
SOURCE_VARIANT = "变体"
SOURCE_LINK = "外链"
SOURCE_SEED = "种子"


@dataclass
class Seed:
    """扫描的起点：一个已知是本人的账号。"""

    site: str
    username: str
    url: str
    account: Account | None = None

    def label(self) -> str:
        return f"{self.site} · {self.username}"


@dataclass
class Candidate:
    """一个候选账号，以及它为什么被选中。"""

    site: str
    username: str
    url: str
    source: str
    score: float = 0.0
    strong: bool = False
    notes: list[str] = field(default_factory=list)
    account: Account | None = None

    def label(self) -> str:
        return f"{self.site} · {self.username}"


# ---------------------------------------------------------------- 解析种子


def _site_by_host(host: str, site_data: Mapping[str, Mapping[str, Any]]) -> str | None:
    """把 URL 的域名对回站点表里的站名。"""
    host = host.lower().removeprefix("www.")
    for name, info in site_data.items():
        main = str(info.get("urlMain") or "")
        if not main:
            continue
        netloc = urlparse(main).netloc.lower().removeprefix("www.")
        if netloc and (host == netloc or host.endswith("." + netloc)):
            return name
    return None


def _site_by_name(text: str, site_data: Mapping[str, Mapping[str, Any]]) -> str | None:
    text = text.strip().lower()
    if not text:
        return None
    for name in site_data:
        if name.lower() == text:
            return name
    for name in site_data:
        if name.lower().replace(" ", "") == text.replace(" ", ""):
            return name
    return None


def parse_seed(text: str, site_data: Mapping[str, Mapping[str, Any]], default_site: str = "GitHub") -> Seed:
    """支持三种写法：完整 URL、`站点 用户名`、纯用户名。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("请先填一个基准账号，例如 github L71615 或 https://github.com/L71615")

    if raw.lower().startswith(("http://", "https://")):
        parsed = urlparse(raw)
        site = _site_by_host(parsed.netloc, site_data)
        parts = [part for part in parsed.path.split("/") if part]
        username = parts[-1] if parts else ""
        if not username:
            raise ValueError(f"这个链接里看不出用户名：{raw}")
        username = username.split("?")[0]
        if not site:
            raise ValueError(f"站点表里没有 {parsed.netloc}，请换一个链接或写「站点 用户名」")
        return Seed(site=site, username=username, url=raw)

    pieces = raw.split()
    if len(pieces) >= 2:
        site = _site_by_name(pieces[0], site_data)
        if not site:
            raise ValueError(f"站点表里没有「{pieces[0]}」这个站")
        username = pieces[1]
    else:
        site = _site_by_name(default_site, site_data) or default_site
        username = pieces[0]

    info = site_data.get(site) or {}
    template = str(info.get("url") or "")
    if template and "{}" in template:
        url = template.replace("{}", username)
    else:
        url = str(info.get("urlMain") or "")
    return Seed(site=site, username=username, url=url)


# ---------------------------------------------------------------- 打分


def _to_account(item: profile.Profile) -> Account:
    return Account(
        username=item.username,
        site=item.site,
        url=item.url,
        display_name=item.display_name,
        bio=item.bio,
        avatar_a=item.avatar_a,
        avatar_d=item.avatar_d,
        avatar_path=item.avatar_path,
        links=list(item.links or []),
        mentions=list(item.mentions or []),
        lang=item.lang,
        ok=item.ok,
        extra_pages=len(item.extra_pages or []),
    )


def anchor_score(seed: Account, other: Account) -> tuple[float, list[str], bool]:
    """返回 (分数, 证据说明, 是否强证据)。"""
    score = 0.0
    notes: list[str] = []
    strong = False

    avatar = avatar_similarity(seed, other)
    if avatar is not None:
        if avatar >= 0.80:
            score += WEIGHTS["avatar"] * avatar
            notes.append(f"头像一致 {avatar:.0%}")
            strong = True
        elif avatar <= 0.20:
            score += PENALTY_DIFFERENT_AVATAR
            notes.append("头像明显不同")
        else:
            score += WEIGHTS["avatar"] * avatar * 0.5
            notes.append(f"头像略像 {avatar:.0%}")

    names = name_similarity(seed.display_name or seed.username, other.display_name or other.username)
    if names >= 0.99:
        score += WEIGHTS["name"]
        notes.append(f"昵称一致：{other.display_name or other.username}")
    elif names > 0:
        score += WEIGHTS["name"] * names
        notes.append(f"昵称相近：{seed.display_name or seed.username} / {other.display_name or other.username}")

    bio = bio_similarity(seed.bio, other.bio)
    if bio is not None and bio > 0:
        score += WEIGHTS["bio"] * bio
        notes.append(f"简介重叠 {bio:.0%}")
    if not (seed.bio or "").strip() and not (other.bio or "").strip() and names < 0.5:
        score += PENALTY_EMPTY_BIO
        notes.append("昵称不同且两边简介都是空的")

    link, mutual, link_notes = link_score(seed, other)
    if link > 0:
        score += WEIGHTS["link"] * min(1.0, link)
        strong = strong or mutual
        notes.extend(link_notes[:2])

    return round(score, 3), notes, strong


# ---------------------------------------------------------------- 扫描


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _claimed_rows(result: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for site, item in result.items():
        status = item.get("status")
        if getattr(status, "status", None) == engine.QueryStatus.CLAIMED:
            rows.append(
                {
                    "site": site,
                    "url": item.get("url_user") or "",
                    "http": item.get("http_status"),
                }
            )
    return rows


def _dedupe(items: Iterable[Candidate], seen: set[tuple[str, str]]) -> list[Candidate]:
    out: list[Candidate] = []
    for item in items:
        key = (item.site.strip().lower(), item.username.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_candidates(
    seed: Seed,
    site_data: Mapping[str, Mapping[str, Any]],
    proxy: str | None = None,
    timeout: float = 20.0,
    deep: bool = True,
    on_progress: Callable[[str], None] | None = None,
    search_fn: Callable[..., Mapping[str, Mapping[str, Any]]] | None = None,
) -> list[Candidate]:
    """跑三轮：同名 → 变体 → 外链，返回带分数的候选（含种子自己）。"""
    say = on_progress or (lambda _msg: None)
    run = search_fn or engine.search

    say(f"1/3 查同名：{seed.username}")
    same = _claimed_rows(run(seed.username, site_data, proxy=proxy, timeout=timeout))

    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    seed_url = seed.url
    for row in same:
        key = (row["site"].lower(), seed.username.lower())
        if key in seen:
            continue
        seen.add(key)
        is_seed = row["site"].lower() == seed.site.lower()
        candidates.append(
            Candidate(
                site=row["site"],
                username=seed.username,
                url=row["url"] or seed_url,
                source=SOURCE_SEED if is_seed else SOURCE_SAME,
                score=1.0 if is_seed else 0.0,
                strong=is_seed,
            )
        )

    name_hint = ""
    if seed.account is not None:
        name_hint = seed.account.display_name or ""
    if name_hint:
        pairs = variants.from_display_name(name_hint)
        made = 0
        for variant_username, reason in pairs:
            if made >= MAX_VARIANTS:
                break
            if variant_username.strip().lower() == seed.username.strip().lower():
                continue
            say(f"2/3 查变体：{variant_username}（{reason}）")
            try:
                found = _claimed_rows(run(variant_username, site_data, proxy=proxy, timeout=timeout))
            except Exception:  # noqa: BLE001 - 单个变体失败不影响整体
                continue
            for row in found:
                key = (row["site"].lower(), variant_username.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    Candidate(
                        site=row["site"],
                        username=variant_username,
                        url=row["url"] or "",
                        source=f"{SOURCE_VARIANT} · {variant_username}",
                    )
                )
            made += 1

    if candidates:
        say(f"3/3 抓主页比对（最多 {MAX_FETCH} 个）")
        picked = candidates[:MAX_FETCH]
        infos = [
            (item.username, item.site, item.url) for item in picked if item.url
        ]
        if infos:
            fetched = profile.collect(
                infos,
                proxy=proxy,
                timeout=timeout,
                workers=8,
                deep=deep,
                max_pages=2,
            )
            by_key = {(p.site.lower(), p.username.lower()): p for p in fetched}
            for item in picked:
                found = by_key.get((item.site.lower(), item.username.lower()))
                if found:
                    item.account = _to_account(found)

    seed_account = seed.account
    if seed_account is not None:
        for item in candidates:
            if item.account is None:
                continue
            if item.site.lower() == seed.site.lower() and item.username.lower() == seed.username.lower():
                continue
            score, notes, strong = anchor_score(seed_account, item.account)
            item.score = score
            item.strong = strong
            item.notes = notes

    return candidates
