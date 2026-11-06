"""身份聚类：把「同名账号」拆成「可能同一个人」的档案。

核心假设：用户名相同只是弱证据。真正能连起来的是头像、昵称、简介互引、
外链域名这些独立信息源。同名只在用户名本身很独特时才值得加权。

设计要点（也是和上游工具最大的区别）：
- 所有证据加权求和，缺证据不给分（宁可分开，不要错并）
- 层次聚类 + 平均连接，禁止 A-B、B-C 就推出 A-C 的链式传染
- 每次合并必须存在「强证据」（头像几乎相同 / 互相提及 / 共同稀有域名）
- 合并太勉强的边界组合会被列进「待确认」，交给人判断
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

# 权重表：用户可读，也方便以后做设置项
WEIGHTS = {
    "avatar": 0.35,
    "name": 0.20,
    "bio": 0.20,
    "link": 0.20,
    "site": 0.10,
    "username": 0.20,  # 上限，实际按独特性打折
    "mutual": 0.25,  # 双向互指：A 的简介提到 B、B 的简介提到 A
}

MERGE_THRESHOLD = 0.62
REVIEW_THRESHOLD = 0.45

STRONG_AVATAR = 0.80  # 头像相似度到这就当强证据
RARE_DOMAIN_MIN_LEN = 6

# 这些域名太常见，共有没有信息量
COMMON_DOMAINS = {
    "twitter.com",
    "x.com",
    "github.com",
    "youtube.com",
    "instagram.com",
    "facebook.com",
    "t.me",
    "discord.gg",
    "linktr.ee",
    "google.com",
    "patreon.com",
    "twitch.tv",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "all",
    "are", "was", "his", "her", "him", "she", "they", "them", "their", "have",
    "has", "had", "not", "but", "out", "who", "what", "when", "where", "how",
    "about", "into", "over", "just", "more", "than", "then", "there", "here",
    "will", "would", "can", "could", "should", "also", "very", "some", "any",
    "our", "its", "it's", "i'm", "don't", "http", "https", "www", "com",
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一个",
}

_SITE_CATEGORY = {
    "dev": {
        "GitHub", "GitLab", "BitBucket", "Gitee", "SourceForge", "PyPi",
        "npm", "Docker Hub", "Stack Overflow", "HackerNews", "Dev.to", "Replit.com",
        "Codeberg", "HackerOne", "HackenProof (Hackers)", "BugCrowd", "TryHackMe",
        "HackTheBox", "Keybase", "Kaggle", "LeetCode", "Codecademy",
    },
    "social": {
        "Twitter", "X", "Instagram", "Facebook", "Reddit", "Telegram", "Discord",
        "TikTok", "YouTube", "Pinterest", "LinkedIn", "Mastodon", "Bluesky",
        "Threads", "Tumblr", "VK", "Weibo", "Douban", "Zhihu", "Snapchat",
    },
    "creative": {
        "Behance", "Dribbble", "ArtStation", "DeviantArt", "Figma", "SoundCloud",
        "Spotify", "Bandcamp", "Vimeo", "Medium", "Substack", "Patreon",
        "Ko-fi", "BuyMeACoffee", "Notion", "Flickr",
    },
    "game": {
        "Steam Community (User)", "Steam", "Xbox Gamertag", "PlayStation Network",
        "Epic Games", "Roblox", "Twitch", "itch.io", "Nintendo", "Minecraft",
    },
}

_AFFINITY = {
    ("dev", "dev"): 1.0,
    ("dev", "social"): 0.45,
    ("dev", "creative"): 0.55,
    ("dev", "game"): 0.35,
    ("social", "social"): 1.0,
    ("social", "creative"): 0.75,
    ("social", "game"): 0.65,
    ("creative", "creative"): 1.0,
    ("creative", "game"): 0.6,
    ("game", "game"): 1.0,
}

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F]+"
)
_WORD_RE = re.compile(r"[a-z0-9_]{3,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class Account:
    """参与聚类的一个账号。"""

    username: str
    site: str
    url: str
    display_name: str = ""
    bio: str = ""
    avatar_a: int | None = None
    avatar_d: int | None = None
    avatar_path: str = ""
    links: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    lang: str = ""
    ok: bool = True
    extra_pages: int = 0

    @property
    def title(self) -> str:
        return self.display_name or self.username


@dataclass
class Cluster:
    """一个档案：被认为属于同一个人（或明确只有一条记录）。"""

    label: str
    accounts: list[Account]
    score: float
    evidence: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.accounts)

    @property
    def sites(self) -> list[str]:
        return [a.site for a in self.accounts]


@dataclass
class PairScore:
    score: float
    strong: bool
    parts: dict[str, float]
    notes: list[str]


# ------------------------------------------------------------------ 基础特征
def normalize_name(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def uniqueness(username: str) -> float:
    """用户名本身的「可识别度」0..1：越长、字符越杂、越不像常见词，同名的信息量越大。"""
    name = (username or "").strip()
    if not name:
        return 0.0
    length = min(len(name) / 20.0, 1.0)
    has_digit = 1.0 if any(ch.isdigit() for ch in name) else 0.0
    has_sep = 1.0 if any(ch in "_-." for ch in name) else 0.0
    mixed = 1.0 if (any(ch.isupper() for ch in name) and any(ch.islower() for ch in name)) else 0.0
    entropy = 0.0
    if name:
        counts: dict[str, int] = {}
        for ch in name.lower():
            counts[ch] = counts.get(ch, 0) + 1
        total = len(name)
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values()) / 3.5
    return max(0.0, min(1.0, 0.35 * length + 0.2 * has_digit + 0.2 * has_sep + 0.1 * mixed + 0.15 * entropy))


def name_similarity(a: str, b: str) -> float:
    left, right = normalize_name(a), normalize_name(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        short, long_ = sorted((len(left), len(right)))
        return 0.85 if short / max(long_, 1) >= 0.5 else 0.6
    return SequenceMatcher(None, left, right).ratio()


def bio_tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    tokens = {w for w in _WORD_RE.findall(text) if w not in STOPWORDS}
    tokens |= {w for w in _CJK_RE.findall(text) if w not in STOPWORDS}
    return tokens


def bio_similarity(a: str, b: str) -> float | None:
    left, right = bio_tokens(a), bio_tokens(b)
    if len(left) < 3 or len(right) < 3:
        return None
    inter = len(left & right)
    union = len(left | right)
    return inter / union if union else None


def site_category(site: str) -> str:
    for category, names in _SITE_CATEGORY.items():
        if site in names:
            return category
    return "other"


def site_affinity(site_a: str, site_b: str) -> float:
    cat_a, cat_b = site_category(site_a), site_category(site_b)
    if cat_a == "other" or cat_b == "other":
        return 0.4
    if cat_a == cat_b:
        return _AFFINITY.get((cat_a, cat_b), 0.8)
    return _AFFINITY.get((cat_a, cat_b), _AFFINITY.get((cat_b, cat_a), 0.4))


def link_score(a: Account, b: Account) -> tuple[float, bool, list[str]]:
    """外链域名重叠 + 互相提及。返回 (链接分, 是否双向互指, 说明)。"""
    notes: list[str] = []
    rare_a = {d for d in a.links if len(d) >= RARE_DOMAIN_MIN_LEN and d not in COMMON_DOMAINS}
    rare_b = {d for d in b.links if len(d) >= RARE_DOMAIN_MIN_LEN and d not in COMMON_DOMAINS}
    shared = rare_a & rare_b
    score = 0.0
    if shared:
        score = 1.0
        notes.append("共同外链：" + "、".join(sorted(shared)[:3]))

    a_to_b = bool(b.username) and b.username.lower() in {m.lower() for m in a.mentions}
    b_to_a = bool(a.username) and a.username.lower() in {m.lower() for m in b.mentions}
    if a_to_b:
        notes.append(f"{a.site} 的简介提到 @{b.username}")
    if b_to_a:
        notes.append(f"{b.site} 的简介提到 @{a.username}")
    mutual = a_to_b and b_to_a
    if a_to_b or b_to_a:
        score = max(score, 1.0)
    if mutual:
        notes.append("双向互指（强证据）")
    return score, mutual, notes


def avatar_similarity(a: Account, b: Account) -> float | None:
    from .profile import hash_distance

    if a.avatar_a is None or b.avatar_a is None:
        return None
    d_a = hash_distance(a.avatar_a, b.avatar_a)
    d_d = hash_distance(a.avatar_d, b.avatar_d)
    if d_a is None or d_d is None:
        return None
    return max(0.0, 1.0 - ((d_a + d_d) / 2.0) / 32.0)


def score_pair(a: Account, b: Account) -> PairScore:
    notes: list[str] = []
    parts: dict[str, float] = {}

    avatar = avatar_similarity(a, b)
    if avatar is not None:
        parts["avatar"] = avatar * WEIGHTS["avatar"]
        if avatar >= STRONG_AVATAR:
            notes.append(f"头像高度相似（{avatar:.0%}）")
        elif avatar >= 0.5:
            notes.append(f"头像接近（{avatar:.0%}）")

    name = name_similarity(a.title, b.title)
    parts["name"] = name * WEIGHTS["name"]
    if name >= 0.85:
        notes.append(f"昵称一致：「{a.title}」")

    bio = bio_similarity(a.bio, b.bio)
    if bio is not None:
        parts["bio"] = bio * WEIGHTS["bio"]
        if bio >= 0.5:
            notes.append(f"简介用词重叠 {bio:.0%}")

    link, mutual, link_notes = link_score(a, b)
    notes.extend(link_notes)
    parts["link"] = link * WEIGHTS["link"]
    if mutual:
        parts["mutual"] = WEIGHTS["mutual"]

    aff = site_affinity(a.site, b.site)
    parts["site"] = aff * WEIGHTS["site"]

    same_name = a.username.strip().lower() == b.username.strip().lower()
    if same_name:
        prior = 0.05 + 0.15 * uniqueness(a.username)
        parts["username"] = prior
        notes.append(f"用户名相同（独特性 {uniqueness(a.username):.0%}，仅作弱证据）")

    score = sum(parts.values())

    # 负证据：头像明显不同、昵称也不同且没有简介
    if avatar is not None and avatar < 0.35:
        score -= 0.40
        notes.append("头像明显不同")
    if name < 0.3 and not bio and not a.bio and not b.bio:
        score -= 0.15

    score = max(0.0, min(1.0, score))
    strong = (avatar is not None and avatar >= STRONG_AVATAR) or link >= 1.0 or mutual
    return PairScore(score=score, strong=strong, parts=parts, notes=notes)


# ------------------------------------------------------------------ 聚类
def _average_link(pairs: list[PairScore]) -> float:
    if not pairs:
        return 0.0
    return sum(p.score for p in pairs) / len(pairs)


def account_key(account: Account) -> str:
    """约束文件里的键：站点|用户名。"""
    return f"{account.site}|{account.username}"


def cluster_accounts(
    accounts: list[Account],
    merge: float = MERGE_THRESHOLD,
    review: float = REVIEW_THRESHOLD,
    must: Iterable[frozenset[str]] | None = None,
    cannot: Iterable[frozenset[str]] | None = None,
) -> tuple[list[Cluster], list[dict]]:
    """层次聚类。返回 (档案列表, 待确认组合)。

    must / cannot 是人工给的约束（键形如 "GitHub|alex"）：
    must 里的账号先强行并组，cannot 里的任何一对永远不许合并。
    """
    n = len(accounts)
    if n == 0:
        return [], []

    key_of_index = {i: account_key(account) for i, account in enumerate(accounts)}
    must_keys = {frozenset(pair) for pair in (must or ()) if len(pair) == 2}
    cannot_keys = {frozenset(pair) for pair in (cannot or ()) if len(pair) == 2}

    # must-link 用并查集先并起来
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    index_by_key = {key: i for i, key in key_of_index.items()}
    for pair in must_keys:
        left, right = tuple(pair)
        if left in index_by_key and right in index_by_key:
            union(index_by_key[left], index_by_key[right])

    scores: dict[tuple[int, int], PairScore] = {}
    for i in range(n):
        for j in range(i + 1, n):
            scores[(i, j)] = score_pair(accounts[i], accounts[j])

    def get(i: int, j: int) -> PairScore:
        return scores[(i, j)] if i < j else scores[(j, i)]

    grouped: dict[int, list[int]] = {}
    for i in range(n):
        grouped.setdefault(find(i), []).append(i)
    groups: list[list[int]] = [members for _, members in sorted(grouped.items())]

    while True:
        best: tuple[float, int, int, bool] | None = None
        for gi in range(len(groups)):
            for gj in range(gi + 1, len(groups)):
                blocked = any(
                    frozenset((key_of_index[x], key_of_index[y])) in cannot_keys
                    for x in groups[gi]
                    for y in groups[gj]
                )
                if blocked:
                    continue
                pairs = [get(x, y) for x in groups[gi] for y in groups[gj]]
                avg = _average_link(pairs)
                if avg < merge:
                    continue
                strong = any(p.strong for p in pairs if p.score >= merge)
                if not strong:
                    continue
                if best is None or avg > best[0]:
                    best = (avg, gi, gj, strong)
        if best is None:
            break
        _, gi, gj, _ = best
        groups[gi].extend(groups[gj])
        groups.pop(gj)

    groups.sort(key=lambda g: (-len(g), accounts[g[0]].site))

    clusters: list[Cluster] = []
    for index, group in enumerate(groups):
        label = chr(ord("A") + index) if index < 26 else f"P{index + 1}"
        if len(group) == 1:
            clusters.append(Cluster(label=label, accounts=[accounts[group[0]]], score=1.0, evidence=["独立账号（无足够证据与他人合并）"]))
            continue
        internal = [_average_link([get(x, y) for k, x in enumerate(group) for y in group[k + 1:]])]
        evidence: list[str] = []
        for k, x in enumerate(group):
            for y in group[k + 1:]:
                pair = get(x, y)
                if pair.score >= merge and pair.notes:
                    for note in pair.notes[:2]:
                        line = f"{accounts[x].site} ↔ {accounts[y].site}：{note}"
                        if line not in evidence:
                            evidence.append(line)
        forced = [
            f"{key_of_index[x]} ↔ {key_of_index[y]}"
            for k, x in enumerate(group)
            for y in group[k + 1:]
            if frozenset((key_of_index[x], key_of_index[y])) in must_keys
        ]
        if forced:
            evidence.insert(0, "人工指定为同一人：" + "；".join(forced[:3]))
        clusters.append(
            Cluster(
                label=label,
                accounts=[accounts[i] for i in group],
                score=round(internal[0], 3),
                evidence=evidence[:12],
            )
        )

    review_pairs: list[dict] = []
    for (i, j), pair in scores.items():
        if review <= pair.score < merge:
            review_pairs.append(
                {
                    "a": accounts[i].site,
                    "b": accounts[j].site,
                    "a_username": accounts[i].username,
                    "b_username": accounts[j].username,
                    "score": round(pair.score, 3),
                    "notes": pair.notes,
                }
            )
    review_pairs.sort(key=lambda item: -item["score"])
    return clusters, review_pairs[:50]


def alias_candidates(
    accounts: list[Account], threshold: float = REVIEW_THRESHOLD, limit: int = 20
) -> list[dict]:
    """换名同人的候选：用户名不同、但证据分已经到「值得看一眼」的一对。

    聚类以「用户名相同」为前提组织，所以不同名字之间即使头像一样也不会被并进
    同一个档案——这里单独列出来，交给人工判断。
    """
    out: list[dict] = []
    for i in range(len(accounts)):
        for j in range(i + 1, len(accounts)):
            left, right = accounts[i], accounts[j]
            if left.username.lower() == right.username.lower():
                continue
            pair = score_pair(left, right)
            if pair.score < threshold:
                continue
            out.append(
                {
                    "a": left.site,
                    "a_username": left.username,
                    "a_url": left.url,
                    "b": right.site,
                    "b_username": right.username,
                    "b_url": right.url,
                    "score": round(pair.score, 3),
                    "strong": pair.strong,
                    "notes": pair.notes,
                }
            )
    out.sort(key=lambda item: -item["score"])
    return out[:limit]
