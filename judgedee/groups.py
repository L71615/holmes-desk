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

# 第二批：按站点名逐个人工归的（仍在扩充）
BRANDS_MORE: dict[str, str] = {
    "1337x": "影音 / 创作",
    "2Dimensions": "影音 / 创作",
    "APClips": "成人内容",
    "AWS Skills Profile": "开发 / 代码",
    "AdmireMe.Vip": "成人内容",
    "Airliners": "生活 / 服务",
    "All Things Worn": "成人内容",
    "AllMyLinks": "社交 / 社区",
    "Apple Discussions": "开发 / 代码",
    "Audiojungle": "购物 / 交易",
    "Avizo": "生活 / 服务",
    "Bezuzyteczna": "社交 / 社区",
    "BongaCams": "成人内容",
    "BuzzFeed": "影音 / 创作",
    "CGTrader": "购物 / 交易",
    "CNET": "影音 / 创作",
    "Championat": "生活 / 服务",
    "Chatujme.cz": "社交 / 社区",
    "ChaturBate": "成人内容",
    "Codolio": "开发 / 代码",
    "Coinvote": "金融 / 加密",
    "Contently": "影音 / 创作",
    "Cults3D": "购物 / 交易",
    "DailyMotion": "影音 / 创作",
    "Dealabs": "购物 / 交易",
    "Empretienda AR": "购物 / 交易",
    "Erome": "成人内容",
    "F3.cool": "社交 / 社区",
    "Finanzfrage": "金融 / 加密",
    "Freesound": "影音 / 创作",
    "Genius (Users)": "影音 / 创作",
    "Heavy-R": "成人内容",
    "HotUKdeals": "购物 / 交易",
    "HubPages": "社交 / 社区",
    "Hubski": "社交 / 社区",
    "IFTTT": "生活 / 服务",
    "IRC-Galleria": "社交 / 社区",
    "Image Fap": "成人内容",
    "ImgUp.cz": "影音 / 创作",
    "Instapaper": "学习 / 学术",
    "Jellyfin Weblate": "开发 / 代码",
    "Jimdo": "开发 / 代码",
    "Kick": "影音 / 创作",
    "Kik": "社交 / 社区",
    "LushStories": "成人内容",
    "Mamot": "社交 / 社区",
    "Motherless": "成人内容",
    "Mydealz": "购物 / 交易",
    "NationStates Nation": "游戏",
    "NationStates Region": "游戏",
    "NitroType": "游戏",
    "OurDJTalk": "影音 / 创作",
    "Outgress": "游戏",
    "Patched": "开发 / 代码",
    "Patreon": "购物 / 交易",
    "Pepperdeals": "购物 / 交易",
    "PepperealsUS": "购物 / 交易",
    "Polarsteps": "生活 / 服务",
    "Polygon": "影音 / 创作",
    "Pornhub": "成人内容",
    "Preisjaeger": "购物 / 交易",
    "ProductHunt": "社交 / 社区",
    "PromoDJ": "影音 / 创作",
    "Promodescuentos": "购物 / 交易",
    "Pronouns.page": "社交 / 社区",
    "Pychess": "游戏",
    "Rajce.net": "影音 / 创作",
    "Rarible": "金融 / 加密",
    "Realmeye": "游戏",
    "RedTube": "成人内容",
    "Redbubble": "购物 / 交易",
    "Reisefrage": "生活 / 服务",
    "ReverbNation": "影音 / 创作",
    "RocketTube": "成人内容",
    "RoyalCams": "成人内容",
    "Rumble": "影音 / 创作",
    "SOOP": "影音 / 创作",
    "SWAPD": "购物 / 交易",
    "Sbazar.cz": "购物 / 交易",
    "Scribd": "学习 / 学术",
    "Shelf": "学习 / 学术",
    "ShitpostBot5000": "社交 / 社区",
    "Slack": "开发 / 代码",
    "Slant": "学习 / 学术",
    "SlideShare": "学习 / 学术",
    "Slides": "学习 / 学术",
    "SmugMug": "影音 / 创作",
    "Smule": "影音 / 创作",
    "SoylentNews": "社交 / 社区",
    "SpeakerDeck": "学习 / 学术",
    "Spells8": "生活 / 服务",
    "Splice": "影音 / 创作",
    "Sporcle": "学习 / 学术",
    "Sportlerfrage": "生活 / 服务",
    "SportsRU": "生活 / 服务",
    "Star Citizen": "游戏",
    "Status Cafe": "社交 / 社区",
    "TRAKTRAIN": "购物 / 交易",
    "Tellonym.me": "社交 / 社区",
    "Tenor": "影音 / 创作",
    "ThemeForest": "购物 / 交易",
    "Tiendanube": "购物 / 交易",
    "TrashboxRU": "开发 / 代码",
    "Trawelling": "生活 / 服务",
    "Trello": "生活 / 服务",
    "Trovo": "影音 / 创作",
    "Tuna": "影音 / 创作",
    "Tweakers": "社交 / 社区",
    "Typeracer": "学习 / 学术",
    "Ultimate-Guitar": "影音 / 创作",
    "VLR": "游戏",
    "VSCO": "影音 / 创作",
    "Venmo": "金融 / 加密",
    "Vjudge": "开发 / 代码",
    "WebNode": "开发 / 代码",
    "Weblate": "开发 / 代码",
    "Weebly": "开发 / 代码",
    "Wikidot": "学习 / 学术",
    "Wikipedia": "学习 / 学术",
    "Windy": "生活 / 服务",
    "WordPress": "开发 / 代码",
    "WordPressOrg": "开发 / 代码",
    "Wordnik": "学习 / 学术",
    "Wowhead": "游戏",
    "Write.as": "社交 / 社区",
    "write.as": "社交 / 社区",
    "Wykop": "社交 / 社区",
    "YouNow": "影音 / 创作",
    "YouPic": "影音 / 创作",
    "YouPorn": "成人内容",
    "akniga": "影音 / 创作",
    "authorSTREAM": "学习 / 学术",
    "couchsurfing": "生活 / 服务",
    "d3RU": "开发 / 代码",
    "dailykos": "社交 / 社区",
    "datingRU": "社交 / 社区",
    "dcinside": "社交 / 社区",
    "drive2": "生活 / 服务",
    "eintracht": "生活 / 服务",
    "exophase": "游戏",
    "fixya": "生活 / 服务",
    "fl": "购物 / 交易",
    "furaffinity": "影音 / 创作",
    "geocaching": "生活 / 服务",
    "habr": "开发 / 代码",
    "hunting": "生活 / 服务",
    "imood": "社交 / 社区",
    "interpals": "社交 / 社区",
    "irecommend": "购物 / 交易",
    "jbzd.com.pl": "社交 / 社区",
    "kaskus": "社交 / 社区",
    "kofi": "购物 / 交易",
    "kwork": "购物 / 交易",
    "livelib": "学习 / 学术",
    "mercadolivre": "购物 / 交易",
    "minds": "社交 / 社区",
    "moikrug": "生活 / 服务",
    "nairaland.com": "社交 / 社区",
    "nnRU": "生活 / 服务",
    "note": "社交 / 社区",
    "opennet": "开发 / 代码",
    "phpRU": "开发 / 代码",
    "pikabu": "社交 / 社区",
    "pr0gramm": "社交 / 社区",
    "prog.hu": "开发 / 代码",
    "satsisRU": "影音 / 创作",
    "sessionize": "开发 / 代码",
    "spletnik": "社交 / 社区",
    "tistory": "社交 / 社区",
    "toster": "开发 / 代码",
    "xHamster": "成人内容",
    "znanylekarz.pl": "生活 / 服务",
}
BRANDS.update(BRANDS_MORE)

CN_TLDS = ('.cn', '.com.cn', '.net.cn', '.org.cn')

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
