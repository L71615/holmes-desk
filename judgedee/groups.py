"""站点自动分组：按域名与站点名里的关键词，把没人管的站点归到大致类别。

不想用「智能分类」那种黑盒：这里就是一张关键词表，从上往下匹配，第一条命中即采用。
匹配不到就留在「未分组」，人工再拖。规则集中在 RULES 里，想改直接改这张表。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# 顺序很重要：越具体的规则放越前面（比如「安全 / CTF」在「开发 / 代码」之前）
RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "安全 / CTF",
        (
            "hack", "ctf", "exploit", "bugcrowd", "hackerone", "tryhackme",
            "security", "pentest", "vuln", "crack", "reverse",
        ),
    ),
    (
        "国内站点",
        (
            "zhihu", "douban", "bilibili", "weibo", "gitee", "juejin", "jianshu",
            "csdn", "cnblogs", "v2ex", "ximalaya", "coolapk", "sspai", "36kr",
            "taobao", "tmall", "jd.com", "aliyun", "tencent", "qq.com", "163.com",
            "sina", "sohu", "ifeng", "baidu", "xiaohongshu", "douyin", "kuaishou",
        ),
    ),
    (
        "游戏",
        (
            "steam", "xbox", "playstation", "psn", "epicgames", "battle.net",
            "riot", "minecraft", "roblox", "itch.io", "speedrun", "game",
            "nintendo", "ubisoft", "gog.com", "twitch",
        ),
    ),
    (
        "金融 / 加密",
        (
            "coinbase", "binance", "kraken", "tradingview", "blockchain",
            "etherscan", "opensea", "bitcoin", "crypto", "wallet", "okx",
            "bybit", "kucoin", "finance", "stock", "invest",
        ),
    ),
    (
        "购物 / 交易",
        (
            "etsy", "ebay", "amazon", "aliexpress", "shopify", "poshmark",
            "depop", "vinted", "grailed", "shop", "store", "market", "buy",
        ),
    ),
    (
        "学习 / 学术",
        (
            "researchgate", "academia", "orcid", "scholar", "coursera",
            "udemy", "khanacademy", "duolingo", "university", "edu",
            "learn", "study", "course",
        ),
    ),
    (
        "影音 / 创作",
        (
            "youtube", "soundcloud", "spotify", "bandcamp", "vimeo", "netflix",
            "last.fm", "deviantart", "behance", "dribbble", "artstation",
            "pixiv", "flickr", "500px", "music", "movie", "film", "video",
            "photo", "art", "podcast",
        ),
    ),
    (
        "开发 / 代码",
        (
            "github", "gitlab", "bitbucket", "gitee", "stackoverflow", "npmjs",
            "pypi", "docker", "codepen", "replit", "sourceforge", "codewars",
            "hackerrank", "leetcode", "dev.to", "hashnode", "huggingface",
            "kaggle", "git", "code", "dev", "api", "python", "rust", "npm",
        ),
    ),
    (
        "社交 / 社区",
        (
            "twitter", "x.com", "facebook", "instagram", "tiktok", "reddit",
            "discord", "telegram", "vk.com", "mastodon", "bluesky", "threads",
            "snapchat", "pinterest", "tumblr", "linkedin", "quora", "forum",
            "community", "social", "blog", "medium",
        ),
    ),
    (
        "生活 / 服务",
        (
            "strava", "goodreads", "letterboxd", "untappd", "airbnb", "booking",
            "map", "travel", "food", "health", "fit", "run", "book",
        ),
    ),
]

# 关键词认不出的品牌站，直接点名归类（只收常见的，剩下的留给人工）
BRANDS: dict[str, str] = {
    # 影音 / 创作
    "Anilist": "影音 / 创作", "MyAnimeList": "影音 / 创作", "Mydramalist": "影音 / 创作",
    "AniWorld": "影音 / 创作", "Aparat": "影音 / 创作", "Odysee": "影音 / 创作",
    "Discogs": "影音 / 创作", "MuseScore": "影音 / 创作", "Giphy": "影音 / 创作",
    "Imgur": "影音 / 创作", "Exposure": "影音 / 创作", "EyeEm": "影音 / 创作",
    "Blipfoto": "影音 / 创作", "ColourLovers": "影音 / 创作", "Coroflot": "影音 / 创作",
    "Crevado": "影音 / 创作", "Issuu": "影音 / 创作", "Carbonmade": "影音 / 创作",
    "Nyaa.si": "影音 / 创作", "PocketStars": "影音 / 创作",
    # 社交 / 社区
    "7Cups": "社交 / 社区", "Disqus": "社交 / 社区", "Fosstodon": "社交 / 社区",
    "GaiaOnline": "社交 / 社区", "LiveJournal": "社交 / 社区", "Myspace": "社交 / 社区",
    "Naver": "社交 / 社区", "Plurk": "社交 / 社区", "Fandom": "社交 / 社区",
    "Fanpop": "社交 / 社区", "Ifunny": "社交 / 社区", "LessWrong": "社交 / 社区",
    "Listed": "社交 / 社区", "BabyRu": "社交 / 社区", "Diskusjon.no": "社交 / 社区",
    "LinuxFR.org": "社交 / 社区", "Gutefrage": "社交 / 社区",
    "Gesundheitsfrage": "社交 / 社区", "Motorradfrage": "社交 / 社区",
    "Autofrage": "社交 / 社区", "Discuss.Elastic.co": "社交 / 社区",
    "Flipboard": "社交 / 社区", "Clapper": "社交 / 社区",
    # 开发 / 代码
    "Asciinema": "开发 / 代码", "Ask Fedora": "开发 / 代码", "Cplusplus": "开发 / 代码",
    "Crowdin": "开发 / 代码", "CTAN": "开发 / 代码", "DMOJ": "开发 / 代码",
    "Gradle": "开发 / 代码", "Laracast": "开发 / 代码", "NotABug.org": "开发 / 代码",
    "ObservableHQ": "开发 / 代码", "Opensource": "开发 / 代码", "Pastebin": "开发 / 代码",
    "Career.habr": "开发 / 代码", "Needrom": "开发 / 代码", "Archive.org": "开发 / 代码",
    # 游戏
    "CurseForge": "游戏", "Pokemon Showdown": "游戏", "Ninja Kiwi": "游戏",
    "Blitz Tactics": "游戏", "Giant Bomb": "游戏", "LOR": "游戏",
    # 购物 / 交易
    "BOOTH": "购物 / 交易", "Fameswap": "购物 / 交易", "Freelancer": "购物 / 交易",
    "Gumroad": "购物 / 交易", "Chollometro": "购物 / 交易", "PepperNL": "购物 / 交易",
    "PepperPL": "购物 / 交易", "Bazar.cz": "购物 / 交易", "MyMiniFactory": "购物 / 交易",
    "Houzz": "购物 / 交易",
    # 学习 / 学术
    "Credly": "学习 / 学术", "Memrise": "学习 / 学术", "Monkeytype": "学习 / 学术",
    "Platzi": "学习 / 学术", "GetMyUni": "学习 / 学术", "Clozemaster": "学习 / 学术",
    "Instructables": "学习 / 学术",
    # 金融 / 加密
    "BiggerPockets": "金融 / 加密", "CashApp": "金融 / 加密", "Open Collective": "金融 / 加密",
    # 生活 / 服务
    "Flightradar24": "生活 / 服务", "Pinkbike": "生活 / 服务", "LibraryThing": "生活 / 服务",
    "Football": "生活 / 服务", "Airbit": "生活 / 服务",
}

CN_TLDS = (".cn", ".com.cn", ".net.cn", ".org.cn")

# 认不出具体站点时，再用域名/名字里的通用词兜一层（顺序同上）
FALLBACK: list[tuple[str, tuple[str, ...]]] = [
    ("游戏", ("game", "play", "arena", "chess", "gaming", "esport", "quest")),
    ("影音 / 创作", ("music", "movie", "film", "video", "photo", "pic", "art", "design", "draw", "paint", "sound", "audio", "tv", "stream")),
    ("开发 / 代码", ("hub", "code", "dev", "git", "build", "script", "stack", "lab", "io")),
    ("社交 / 社区", ("social", "chat", "forum", "talk", "post", "blog", "feed", "link", "connect", "meet", "friend")),
    ("购物 / 交易", ("shop", "store", "market", "sell", "buy", "trade", "deal", "cart", "gift")),
    ("学习 / 学术", ("learn", "school", "study", "academy", "edu", "course", "class", "book", "read", "wiki")),
    ("金融 / 加密", ("coin", "trade", "fin", "bank", "pay", "wallet", "stock", "invest", "crypto")),
    ("生活 / 服务", ("travel", "food", "fit", "health", "run", "ride", "map", "home", "life", "news")),
]


def classify(name: str, info: dict[str, Any] | None = None) -> str | None:
    """返回建议的分组名；认不出来返回 None。"""
    info = info or {}
    raw = str(info.get("urlMain") or "").lower()
    host = urlparse(raw).netloc or raw
    if host.startswith("www."):
        host = host[4:]
    brand = BRANDS.get(name)
    if brand:
        return brand
    haystack = f"{name.lower()} {host}"
    words = set(re.split(r"[^a-z0-9]+", haystack))
    for group, keywords in RULES:
        if any(keyword in haystack for keyword in keywords):
            return group
    if host.endswith(CN_TLDS):
        return "国内站点"
    for group, keywords in FALLBACK:
        if words & set(keywords):
            return group
    return None


def plan(lib) -> dict[str, list[str]]:
    """算出「哪些站点会进哪个组」，不改动任何东西（给预览和确认用）。"""
    result: dict[str, list[str]] = {}
    for name in lib.ungrouped():
        info = lib.info(name) or {}
        group = classify(name, info)
        if not group:
            continue
        result.setdefault(group, []).append(name)
    return result


def apply(lib) -> dict[str, int]:
    """真的写进去：返回每个组新收了多少站。"""
    counts: dict[str, int] = {}
    for group, names in plan(lib).items():
        lib.add_group(group)
        for name in names:
            lib.set_group(name, group)
            counts[group] = counts.get(group, 0) + 1
    if counts:
        lib.save()
    return counts
