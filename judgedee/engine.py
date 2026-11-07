"""检测引擎。

只做一件事：判断某个用户名在某个站点上是否存在。用的是线程池 + 普通
``requests.Session``，没有命令行界面，也不依赖 pandas。

判定按站点表的 ``errorType`` 分三种：

* ``status_code``   —— 先认为存在；状态码命中 ``errorCode`` 或非 2xx/3xx 则判为不存在
* ``message``       —— 在页面里找 ``errorMsg`` 文案；找到 = 不存在
* ``response_url``  —— 禁止跳转，2xx = 存在

另外识别 Cloudflare / AWS / PerimeterX 的挑战页，标记为 ``WAF`` 而不是硬判存在。
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import requests

_SPLIT_RE = re.compile(r"[,，、;；\s]+")  # 用户名分隔符：中英文逗号、顿号、分号、空白

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"
MAX_WORKERS = 20

# WAF 挑战页指纹：命中说明请求被拦了，结果不可信
WAF_SIGNATURES = (
    r".loading-spinner{visibility:hidden}body.no-js .challenge-running{display:none}",  # Cloudflare 2024-05-13
    r'<span id="challenge-error-text">',                                               # Cloudflare 2024-11-11
    r"AwsWafIntegration.forceRefreshToken",                                            # AWS CloudFront
    r'{return l.onPageView}}),Object.defineProperty(r,"perimeterxIdentifiers"',         # PerimeterX
)


class QueryStatus(str, Enum):
    """一次站点探测的结论。"""

    CLAIMED = "Claimed"
    AVAILABLE = "Available"
    UNKNOWN = "Unknown"
    ILLEGAL = "Illegal"
    WAF = "WAF"


@dataclass
class QueryResult:
    """单个站点的探测结果。"""

    username: str
    site_name: str
    site_url_user: str
    status: QueryStatus
    query_time: float | None = None
    context: str | None = None
    http_status: int | str | None = None


class SearchCancelled(Exception):
    """用户在检索过程中点了「停止」。"""


def load_sites(path: str | Path) -> dict[str, dict[str, Any]]:
    """读取站点表（JSON），去掉 ``$schema`` 这类元数据键。"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("$")}


def interpolate(obj: Any, username: str) -> Any:
    """把模板里的 ``{}`` 换成用户名，递归处理 dict / list。"""
    if isinstance(obj, str):
        return obj.replace("{}", username)
    if isinstance(obj, dict):
        return {k: interpolate(v, username) for k, v in obj.items()}
    if isinstance(obj, list):
        return [interpolate(i, username) for i in obj]
    return obj


def _classify(resp: requests.Response, info: dict[str, Any], error_types: list[str]) -> QueryStatus:
    """按站点声明的判定方式给出结论。"""
    try:
        text = resp.text
    except Exception:  # noqa: BLE001 - 编码异常时退化
        text = ""

    if any(sig in text for sig in WAF_SIGNATURES):
        return QueryStatus.WAF

    if any(t not in ("message", "status_code", "response_url") for t in error_types):
        return QueryStatus.UNKNOWN

    status: QueryStatus | None = None

    if "message" in error_types:
        errors = info.get("errorMsg")
        messages = [errors] if isinstance(errors, str) else list(errors or [])
        found = any(msg in text for msg in messages if msg)
        status = QueryStatus.AVAILABLE if found else QueryStatus.CLAIMED

    if "status_code" in error_types and status is not QueryStatus.AVAILABLE:
        status = QueryStatus.CLAIMED
        codes = info.get("errorCode")
        if isinstance(codes, int):
            codes = [codes]
        if codes is not None and resp.status_code in codes:
            status = QueryStatus.AVAILABLE
        elif resp.status_code >= 300 or resp.status_code < 200:
            status = QueryStatus.AVAILABLE

    if "response_url" in error_types and status is not QueryStatus.AVAILABLE:
        status = QueryStatus.CLAIMED if 200 <= resp.status_code < 300 else QueryStatus.AVAILABLE

    return status or QueryStatus.UNKNOWN


def check_site(
    session: requests.Session,
    username: str,
    site_name: str,
    info: dict[str, Any],
    proxy: str | None = None,
    timeout: float = 20.0,
) -> QueryResult:
    """探测单个站点。"""
    url = interpolate(info["url"], username.replace(" ", "%20"))

    # 站点对用户名有格式要求时先本地判断，不浪费一次请求
    regex = info.get("regexCheck")
    if regex and re.search(regex, username) is None:
        return QueryResult(username, site_name, "", QueryStatus.ILLEGAL, 0.0, "用户名格式不符合该站规则")

    error_type = info.get("errorType") or "status_code"
    error_types = [error_type] if isinstance(error_type, str) else list(error_type)

    method = (info.get("request_method") or "").upper()
    if not method:
        method = "HEAD" if "status_code" in error_types else "GET"

    probe_url = interpolate(info.get("urlProbe") or url, username)
    payload = info.get("request_payload")
    if payload is not None:
        payload = interpolate(payload, username)

    headers = {"User-Agent": USER_AGENT}
    headers.update(info.get("headers") or {})

    kwargs: dict[str, Any] = {
        "headers": headers,
        "allow_redirects": "response_url" not in error_types,
        "timeout": timeout,
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    if payload is not None:
        kwargs["json"] = payload

    started = time.perf_counter()
    try:
        resp = session.request(method, probe_url, **kwargs)
    except requests.exceptions.RequestException as exc:
        return QueryResult(
            username, site_name, url, QueryStatus.UNKNOWN, None, f"{type(exc).__name__}: {exc}"
        )
    elapsed = time.perf_counter() - started
    return QueryResult(username, site_name, url, _classify(resp, info, error_types), elapsed, None, resp.status_code)


def search(
    username: str,
    site_data: dict[str, dict[str, Any]],
    notify: Any | None = None,
    proxy: str | None = None,
    timeout: float = 20.0,
    max_workers: int = MAX_WORKERS,
    cancel: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """检索一个用户名在全部站点上的情况。

    ``notify`` 需要提供 ``start(username)`` 与 ``update(result)`` 两个方法，
    每得到一个结论就会回调一次（界面据此实时显示进度）。

    ``cancel`` 传一个 ``threading.Event``，置位后最多等一个轮询间隔就抛
    ``SearchCancelled``；已经在飞的请求无法打断，但会立刻放弃等待。
    """
    if notify is not None:
        notify.start(username)

    workers = max(1, min(max_workers, len(site_data) or 1))
    results: dict[str, dict[str, Any]] = {}
    pool = ThreadPoolExecutor(max_workers=workers)

    try:
        with requests.Session() as session:
            futures = {
                pool.submit(check_site, session, username, name, info, proxy, timeout): (name, info)
                for name, info in site_data.items()
            }
            pending = set(futures)
            while pending:
                if cancel is not None and cancel.is_set():
                    raise SearchCancelled()
                done, pending = wait(pending, timeout=0.3, return_when=FIRST_COMPLETED)
                for future in done:
                    name, info = futures[future]
                    result = future.result()
                    if notify is not None:
                        notify.update(result)
                    results[name] = {
                        "url_main": info.get("urlMain"),
                        "url_user": result.site_url_user,
                        "status": result,
                        "http_status": result.http_status,
                    }
    except SearchCancelled:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=False)

    return results


def expand_usernames(raw: str) -> list[str]:
    """把输入框内容拆成用户名列表，``{?}`` 展开成 ``_ - .`` 三种变体。"""
    out: list[str] = []
    for token in _SPLIT_RE.split(raw.strip()):
        if not token:
            continue
        if "{?}" in token:
            out.extend(token.replace("{?}", symbol) for symbol in ("_", "-", "."))
        else:
            out.append(token)
    return out


def pick_sites(site_data: dict[str, dict[str, Any]], wanted: Iterable[str]) -> tuple[dict, list[str]]:
    """按名字挑选站点（大小写不敏感），返回 (选中站点, 未找到的名字)。"""
    wanted = [w.strip() for w in wanted if w and w.strip()]
    if not wanted:
        return dict(site_data), []

    lookup = {name.lower(): name for name in site_data}
    chosen: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for want in wanted:
        real = lookup.get(want.lower())
        if real is None:
            missing.append(want)
        else:
            chosen[real] = site_data[real]
    return chosen, missing
