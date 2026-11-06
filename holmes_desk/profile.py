"""主页画像采集：命中之后，补一层「这个账号长什么样」。

只用 requests 抓页面，用正则从 HTML 里抠 Open Graph / meta / 标题 / 简介 /
头像 / 外链；头像解码和感知哈希需要 Pillow，没装就退化成「只有头像 URL」。

刻意不做的事：不存页面全文，只留结构化字段和 128px 头像缩略图。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0"
)
MAX_HTML_BYTES = 1_500_000
MAX_AVATAR_BYTES = 1_200_000
AVATAR_PX = 128

_META_RE = re.compile(
    r"""<meta\b[^>]*?(?:property|name)\s*=\s*["']([^"']+)["'][^>]*?content\s*=\s*["']([^"']*)["']""",
    re.I,
)
_META_RE_REV = re.compile(
    r"""<meta\b[^>]*?content\s*=\s*["']([^"']*)["'][^>]*?(?:property|name)\s*=\s*["']([^"']+)["']""",
    re.I,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"""(\w[\w-]*)\s*=\s*["']([^"']*)["']""")
_A_RE = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_MENTION_RE = re.compile(r"(?<![\w@/])@([A-Za-z0-9_.\-]{2,30})")

# 简介容器：先按站点特化的选择器，失败再退到「页头里最长的文本块」
BIO_HINTS = (
    r'<div[^>]+class="[^"]*(?:user-bio|profile-bio|bio|about|description)[^"]*"[^>]*>(.*?)</div>',
    r'<p[^>]+class="[^"]*(?:bio|about|description|note)[^"]*"[^>]*>(.*?)</p>',
    r'<div[^>]+data-testid="[^"]*bio[^"]*"[^>]*>(.*?)</div>',
)


@dataclass
class Profile:
    """一个账号的公开画像。"""

    username: str
    site: str
    url: str
    ok: bool = False
    error: str = ""
    display_name: str = ""
    bio: str = ""
    avatar_url: str = ""
    avatar_path: str = ""
    avatar_a: int | None = None
    avatar_d: int | None = None
    links: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    lang: str = ""
    http_status: int | None = None


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text or "")
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def _meta_map(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _META_RE.findall(page):
        out.setdefault(key.strip().lower(), value)
    for value, key in _META_RE_REV.findall(page):
        out.setdefault(key.strip().lower(), value)
    return out


def _pick_avatar(page: str, meta: dict[str, str], base_url: str) -> str:
    for key in ("og:image", "twitter:image", "og:image:url", "thumbnail"):
        if meta.get(key):
            return urljoin(base_url, meta[key].strip())
    best = ""
    best_area = 0
    for tag in _IMG_RE.findall(page):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(tag)}
        src = attrs.get("src") or attrs.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        try:
            width = int(float(attrs.get("width", "0") or 0))
            height = int(float(attrs.get("height", "0") or 0))
        except ValueError:
            continue
        if width < 48 or height < 48:
            continue
        if width * height <= best_area:
            continue
        best, best_area = urljoin(base_url, src), width * height
    return best


def _pick_bio(page: str, meta: dict[str, str]) -> str:
    for key in ("og:description", "twitter:description", "description"):
        if meta.get(key):
            text = _clean(meta[key])
            if len(text) >= 4:
                return text[:400]
    for pattern in BIO_HINTS:
        match = re.search(pattern, page, re.I | re.S)
        if match:
            text = _clean(match.group(1))
            if len(text) >= 4:
                return text[:400]
    return ""


def _pick_links(page: str, base_url: str, site_domain: str) -> tuple[list[str], list[str]]:
    domains: list[str] = []
    texts: list[str] = []
    for href, label in _A_RE.findall(page)[:400]:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if not host:
            continue
        texts.append(_clean(label))
        if site_domain and (host == site_domain or host.endswith("." + site_domain)):
            continue
        if host in domains:
            continue
        domains.append(host)
    return domains[:20], texts


def parse_profile(page: str, url: str, site_domain: str = "") -> dict[str, Any]:
    """从一页 HTML 里抽画像字段；纯函数，方便测试。"""
    meta = _meta_map(page)
    title = _clean(_TITLE_RE.search(page).group(1)) if _TITLE_RE.search(page) else ""
    h1 = _clean(_H1_RE.search(page).group(1)) if _H1_RE.search(page) else ""
    display = _clean(meta.get("og:title", "")) or title or h1
    # 很多站点把标题写成 "Name (@handle) · Instagram"，去掉尾巴
    display = re.split(r"\s+[|·\-–—]\s+", display)[0].strip()
    domains, texts = _pick_links(page, url, site_domain)
    bio = _pick_bio(page, meta)
    mentions = []
    for text in texts[:60] + [bio]:
        for name in _MENTION_RE.findall(text or ""):
            if name.lower() not in {m.lower() for m in mentions}:
                mentions.append(name)
    lang_match = re.search(r"""<html[^>]+lang\s*=\s*["']([^"']+)["']""", page, re.I)
    return {
        "display_name": display[:120],
        "bio": bio,
        "avatar_url": _pick_avatar(page, meta, url),
        "links": domains,
        "mentions": mentions[:12],
        "lang": (lang_match.group(1) if lang_match else "").split("-")[0].lower(),
    }


# ------------------------------------------------------------------ 头像哈希
def _popcount(value: int) -> int:
    return bin(value).count("1")


def image_hashes(data: bytes) -> tuple[int, int, bytes] | None:
    """返回 (aHash, dHash, 缩略图 PNG bytes)；没有 Pillow 或解码失败就返回 None。"""
    try:
        from io import BytesIO

        from PIL import Image
    except Exception:  # noqa: BLE001 - Pillow 是可选依赖
        return None
    try:
        image = Image.open(BytesIO(data))
        image = image.convert("RGB")
        thumb = image.copy()
        thumb.thumbnail((AVATAR_PX, AVATAR_PX), Image.LANCZOS)
        buffer = BytesIO()
        thumb.save(buffer, format="PNG", optimize=True)
        thumb_png = buffer.getvalue()

        gray = image.convert("L").resize((8, 8), Image.LANCZOS)
        values = list(gray.getdata())
        avg = sum(values) / len(values)
        a_hash = 0
        for value in values:
            a_hash = (a_hash << 1) | (1 if value >= avg else 0)

        grad = image.convert("L").resize((9, 8), Image.LANCZOS)
        pixels = list(grad.getdata())
        d_hash = 0
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                d_hash = (d_hash << 1) | (1 if left > right else 0)
        return a_hash, d_hash, thumb_png
    except Exception:  # noqa: BLE001
        return None


def hash_distance(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return _popcount(a ^ b)


def avatar_similarity(a: Profile, b: Profile) -> float | None:
    """两个头像的相似度 0..1；任一方没头像就返回 None（表示证据缺失）。"""
    if a.avatar_a is None or b.avatar_a is None:
        return None
    d_a = hash_distance(a.avatar_a, b.avatar_a)
    d_d = hash_distance(a.avatar_d, b.avatar_d)
    if d_a is None or d_d is None:
        return None
    distance = (d_a + d_d) / 2.0
    return max(0.0, 1.0 - distance / 32.0)


# ------------------------------------------------------------------ 抓取
def _make_session(proxy: str | None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def fetch_one(
    session: requests.Session,
    username: str,
    site: str,
    url: str,
    timeout: float = 15.0,
    avatar_dir: Path | None = None,
) -> Profile:
    profile = Profile(username=username, site=site, url=url)
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        profile.http_status = response.status_code
        raw = b""
        for chunk in response.iter_content(65536):
            raw += chunk
            if len(raw) >= MAX_HTML_BYTES:
                break
        encoding = response.encoding or "utf-8"
        page = raw[:MAX_HTML_BYTES].decode(encoding, errors="ignore")
        domain = urlparse(url).hostname or ""
        parsed = parse_profile(page, response.url or url, domain)
        profile.display_name = parsed["display_name"]
        profile.bio = parsed["bio"]
        profile.avatar_url = parsed["avatar_url"]
        profile.links = parsed["links"]
        profile.mentions = parsed["mentions"]
        profile.lang = parsed["lang"]
        profile.ok = True

        if avatar_dir is not None and profile.avatar_url:
            _attach_avatar(session, profile, timeout, avatar_dir)
    except Exception as exc:  # noqa: BLE001 - 抓失败只影响证据强度
        profile.error = f"{type(exc).__name__}: {exc}"
    return profile


def _attach_avatar(
    session: requests.Session, profile: Profile, timeout: float, avatar_dir: Path
) -> None:
    try:
        response = session.get(profile.avatar_url, timeout=timeout, stream=True)
        if response.status_code >= 400:
            return
        data = b""
        for chunk in response.iter_content(65536):
            data += chunk
            if len(data) >= MAX_AVATAR_BYTES:
                break
        hashed = image_hashes(data)
        if not hashed:
            return
        a_hash, d_hash, thumb = hashed
        avatar_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(f"{profile.site}|{profile.username}".encode("utf-8")).hexdigest()[:16]
        target = avatar_dir / f"{key}.png"
        target.write_bytes(thumb)
        profile.avatar_path = str(target)
        profile.avatar_a = a_hash
        profile.avatar_d = d_hash
    except Exception:  # noqa: BLE001
        return


def collect(
    accounts: Iterable[tuple[str, str, str]],
    proxy: str | None = None,
    timeout: float = 15.0,
    workers: int = 8,
    avatar_dir: Path | None = None,
    on_progress: Callable[[int, int, Profile], None] | None = None,
) -> list[Profile]:
    """并发抓一批账号的主页；accounts 是 (username, site, url)。"""
    from concurrent.futures import ThreadPoolExecutor

    items = [item for item in accounts if item[2]]
    session = _make_session(proxy)
    total = len(items)
    done = 0
    results: list[Profile] = []

    def work(item: tuple[str, str, str]) -> Profile:
        return fetch_one(session, item[0], item[1], item[2], timeout, avatar_dir)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
        for profile in pool.map(work, items):
            results.append(profile)
            done += 1
            if on_progress:
                on_progress(done, total, profile)
    return results
