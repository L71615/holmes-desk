"""误报复核。

「已注册」的判定完全基于各站的报错规则，站点改版后容易出现假命中。
复核的做法很简单：换一个干净的会话再查一次同一个链接，看结论是否稳定——
仍然命中就是「复核通过」，变成未注册就是「疑似误报」。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, Iterable

import requests

from .engine import USER_AGENT, QueryStatus, check_site

VERDICT_CONFIRMED = "confirmed"
VERDICT_SUSPECT = "suspect"
VERDICT_UNKNOWN = "unknown"

VERDICT_TEXT = {
    VERDICT_CONFIRMED: "复核通过",
    VERDICT_SUSPECT: "疑似误报",
    VERDICT_UNKNOWN: "无法确认",
}


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def verify_one(
    username: str,
    site_name: str,
    info: dict[str, Any],
    proxy: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """再查一次，返回 {site, username, verdict, http, elapsed, message}。"""
    with _new_session() as session:
        result = check_site(session, username, site_name, info, proxy=proxy, timeout=timeout)

    if result.status is QueryStatus.CLAIMED:
        verdict, message = VERDICT_CONFIRMED, "第二次仍然命中"
    elif result.status is QueryStatus.AVAILABLE:
        verdict, message = VERDICT_SUSPECT, "第二次变成未注册"
    elif result.status is QueryStatus.ILLEGAL:
        verdict, message = VERDICT_SUSPECT, "用户名格式不符"
    else:
        verdict, message = VERDICT_UNKNOWN, str(result.context or "请求失败或页面异常")

    return {
        "username": username,
        "site": site_name,
        "verdict": verdict,
        "status": result.status,
        "http": result.http_status,
        "elapsed": result.query_time,
        "message": message,
    }


def verify_claimed(
    claimed: Iterable[tuple[str, str]],
    site_data: dict[str, dict[str, Any]],
    proxy: str | None = None,
    timeout: float = 15.0,
    workers: int = 10,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """claimed: [(username, site_name), ...]，返回每个条目的复核结果。"""
    tasks: list[tuple[str, str, dict[str, Any]]] = []
    for username, site_name in claimed:
        info = site_data.get(site_name)
        if isinstance(info, dict):
            tasks.append((username, site_name, info))
    if not tasks:
        return []

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tasks)))) as pool:
        futures = {
            pool.submit(verify_one, user, site, info, proxy, timeout): (user, site)
            for user, site, info in tasks
        }
        pending = set(futures)
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when="FIRST_COMPLETED")
            for future in done:
                user, site = futures[future]
                try:
                    payload = future.result()
                except Exception as exc:  # noqa: BLE001
                    payload = {
                        "username": user,
                        "site": site,
                        "verdict": VERDICT_UNKNOWN,
                        "status": QueryStatus.UNKNOWN,
                        "http": None,
                        "elapsed": None,
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                results.append(payload)
                if on_result is not None:
                    on_result(payload)
    return results
