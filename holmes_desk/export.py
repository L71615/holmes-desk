"""结果导出：TXT / CSV / XLSX / HTML / JSONL。

所有函数都只依赖标准库；XLSX 需要 pandas + openpyxl，缺了就返回错误信息，
不影响其它格式。
"""

from __future__ import annotations

import csv
import html
import json
import time
from pathlib import Path
from typing import Any, Iterable

from .engine import QueryStatus

FIELDS = ["username", "site", "url_main", "url_user", "exists", "http_status", "response_time_s"]


def _rows(username: str, results: dict[str, dict[str, Any]], show_all: bool) -> Iterable[list[Any]]:
    for site, item in sorted(results.items(), key=lambda kv: kv[0].lower()):
        status = item.get("status")
        if status is None:
            continue
        if not show_all and status.status is not QueryStatus.CLAIMED:
            continue
        yield [
            username,
            site,
            item.get("url_main", ""),
            item.get("url_user", ""),
            status.status.value,
            item.get("http_status", ""),
            "" if status.query_time is None else round(status.query_time, 3),
        ]


def write_txt(path: Path, username: str, results: dict, show_all: bool = False) -> int:
    rows = list(_rows(username, results, show_all))
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            if row[3]:
                fh.write(row[3] + "\n")
        fh.write(f"Total Websites Username Detected On : {len(rows)}\n")
    return len(rows)


def write_csv(path: Path, username: str, results: dict, show_all: bool = False) -> int:
    rows = list(_rows(username, results, show_all))
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return len(rows)


def write_jsonl(path: Path, username: str, results: dict, show_all: bool = False) -> int:
    rows = list(_rows(username, results, show_all))
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(zip(FIELDS, row)), ensure_ascii=False) + "\n")
    return len(rows)


def write_xlsx(path: Path, username: str, results: dict, show_all: bool = False) -> int:
    import pandas as pd  # 延迟导入：没装 pandas 时其它格式照常可用

    rows = list(_rows(username, results, show_all))
    frame = pd.DataFrame(rows, columns=FIELDS)
    frame.to_excel(path, sheet_name="holmes-desk", index=False)
    return len(rows)


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{username} 的用户名检索报告</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 40px 24px; background: #eef1f6; color: #111827;
         font: 15px/1.6 "Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif; }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  header {{ background: #0b1220; color: #fff; border-radius: 14px; padding: 26px 28px; }}
  header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  header p {{ margin: 0; color: #93a4c4; font-size: 13px; }}
  .stats {{ display: flex; gap: 14px; margin: 18px 0; flex-wrap: wrap; }}
  .stat {{ flex: 1 1 160px; background: #fff; border-radius: 12px; padding: 16px 18px; }}
  .stat b {{ display: block; font-size: 24px; color: #2563eb; }}
  .stat span {{ color: #6b7280; font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #e3e7ef; font-size: 13px; }}
  th {{ background: #f3f5f9; color: #374151; font-weight: 600; }}
  tr:last-child td {{ border-bottom: none; }}
  td a {{ color: #2563eb; text-decoration: none; word-break: break-all; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; }}
  .ok {{ background: #dcfce7; color: #166534; }}
  .warn {{ background: #fef3c7; color: #92400e; }}
  .muted {{ background: #f1f5f9; color: #475569; }}
  footer {{ margin-top: 18px; color: #6b7280; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{username}</h1>
    <p>HolmesDesk 用户名检索报告 · 生成于 {generated}</p>
  </header>
  <div class="stats">
    <div class="stat"><b>{claimed}</b><span>已注册站点</span></div>
    <div class="stat"><b>{checked}</b><span>参与检测站点</span></div>
    <div class="stat"><b>{elapsed}</b><span>本页耗时（秒）</span></div>
  </div>
  <table>
    <thead><tr><th>站点</th><th>状态</th><th>链接</th><th>HTTP</th><th>耗时</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <footer>本报告由 HolmesDesk 在本机生成，不含任何云端上传。</footer>
</div>
</body>
</html>
"""


def write_html(path: Path, username: str, results: dict, show_all: bool = False) -> int:
    rows_data = list(_rows(username, results, show_all))
    tr_parts = []
    total_time = 0.0
    for user, site, url_main, url_user, exists, http_status, seconds in rows_data:
        if isinstance(seconds, float):
            total_time += seconds
        css = "ok" if exists == QueryStatus.CLAIMED.value else (
            "warn" if exists in (QueryStatus.UNKNOWN.value, QueryStatus.WAF.value) else "muted"
        )
        link = (
            f'<a href="{html.escape(url_user, quote=True)}">{html.escape(url_user)}</a>'
            if url_user else '<span style="color:#9ca3af">—</span>'
        )
        tr_parts.append(
            f"      <tr><td>{html.escape(site)}</td>"
            f'<td><span class="tag {css}">{html.escape(exists)}</span></td>'
            f"<td>{link}</td><td>{http_status}</td><td>{seconds}s</td></tr>"
        )

    claimed = sum(1 for r in rows_data if r[4] == QueryStatus.CLAIMED.value)
    content = HTML_TEMPLATE.format(
        username=html.escape(username),
        generated=time.strftime("%Y-%m-%d %H:%M:%S"),
        claimed=claimed,
        checked=len(results),
        elapsed=f"{total_time:.1f}",
        rows="\n".join(tr_parts) or '      <tr><td colspan="5">没有命中</td></tr>',
    )
    path.write_text(content, encoding="utf-8")
    return len(rows_data)


WRITERS = {
    "txt": (".txt", write_txt),
    "csv": (".csv", write_csv),
    "xlsx": (".xlsx", write_xlsx),
    "html": (".html", write_html),
    "jsonl": (".jsonl", write_jsonl),
}


def export_run(
    run_dir: Path,
    username: str,
    results: dict,
    formats: Iterable[str],
    show_all: bool = False,
) -> tuple[list[Path], list[str]]:
    """按选定格式导出一次检索结果，返回 (写出的文件, 错误信息)。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    errors: list[str] = []
    for fmt in formats:
        suffix, writer = WRITERS[fmt]
        target = run_dir / f"{username}{suffix}"
        try:
            writer(target, username, results, show_all)
            written.append(target)
        except Exception as exc:  # noqa: BLE001 - 单个格式失败不影响其它
            errors.append(f"{fmt.upper()} 导出失败：{exc}")
    return written, errors


# ---------------------------------------------------------------- 报告导出
# 与上面 export_run 的区别：这里导的是界面上「当前这一份结果」，包含复核结论
# 和分组，用于检索完、复核完之后再出一份报告。

REPORT_FIELDS = [
    "username",
    "site",
    "group",
    "status",
    "verdict",
    "url_user",
    "http_status",
    "response_time_s",
]


def _report_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        seconds = row.get("time") or ""
        if isinstance(seconds, str):
            seconds = seconds.rstrip("s")
        out.append(
            {
                "username": row.get("username") or "",
                "site": row.get("site") or "",
                "group": row.get("group") or "",
                "status": row.get("status") or "",
                "verdict": row.get("verdict") or "",
                "url_user": row.get("url_user") or "",
                "http_status": "" if row.get("http") in (None, "—") else row.get("http"),
                "response_time_s": seconds,
            }
        )
    out.sort(key=lambda r: (r["group"], r["site"].lower()))
    return out


REPORT_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{username} 的用户名检索报告</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 40px 24px; background: #eef1f6; color: #111827;
         font: 15px/1.6 "Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; }}
  header {{ background: #0b1220; color: #fff; border-radius: 14px; padding: 26px 28px; }}
  header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  header p {{ margin: 0; color: #93a4c4; font-size: 13px; }}
  .stats {{ display: flex; gap: 14px; margin: 18px 0; flex-wrap: wrap; }}
  .stat {{ flex: 1 1 150px; background: #fff; border-radius: 12px; padding: 16px 18px; }}
  .stat b {{ display: block; font-size: 24px; color: #2563eb; }}
  .stat span {{ color: #6b7280; font-size: 12px; }}
  .stat.bad b {{ color: #b45309; }}
  .stat.warn b {{ color: #dc2626; }}
  h2 {{ font-size: 15px; color: #374151; margin: 26px 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #e3e7ef; font-size: 13px; }}
  th {{ background: #f3f5f9; color: #374151; font-weight: 600; }}
  tr:last-child td {{ border-bottom: none; }}
  td a {{ color: #2563eb; text-decoration: none; word-break: break-all; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; }}
  .ok {{ background: #dcfce7; color: #166534; }}
  .warn {{ background: #fef3c7; color: #92400e; }}
  .bad {{ background: #fee2e2; color: #991b1b; }}
  .muted {{ background: #f1f5f9; color: #475569; }}
  footer {{ margin-top: 18px; color: #6b7280; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{username}</h1>
    <p>HolmesDesk 用户名检索报告 · 生成于 {generated}</p>
  </header>
  <div class="stats">
    <div class="stat"><b>{claimed}</b><span>已注册</span></div>
    <div class="stat"><b>{verified}</b><span>复核通过</span></div>
    <div class="stat bad"><b>{suspect}</b><span>存疑（可能误报）</span></div>
    <div class="stat"><b>{total}</b><span>本报告条目</span></div>
  </div>
{sections}
  <footer>本报告由 HolmesDesk 在本机生成，不含任何云端上传。</footer>
</div>
</body>
</html>
"""


def write_report_html(path: Path, username: str, rows: Iterable[dict[str, Any]]) -> int:
    data = _report_rows(rows)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        buckets.setdefault(item["group"] or "未分组", []).append(item)

    def cell(item: dict[str, Any]) -> str:
        status = item["status"]
        css = {
            "已注册": "ok",
            "未知": "warn",
            "被拦截": "warn",
            "格式不符": "muted",
        }.get(status, "muted")
        verdict = item["verdict"]
        vcss = {"复核通过": "ok", "存疑": "bad", "未判定": "warn"}.get(verdict, "muted")
        link = (
            f'<a href="{html.escape(item["url_user"], quote=True)}">{html.escape(item["url_user"])}</a>'
            if item["url_user"] else '<span style="color:#9ca3af">—</span>'
        )
        return (
            "      <tr>"
            f"<td>{html.escape(item['site'])}</td>"
            f'<td><span class="tag {css}">{html.escape(status)}</span></td>'
            f'<td><span class="tag {vcss}">{html.escape(verdict or "—")}</span></td>'
            f"<td>{link}</td>"
            f"<td>{html.escape(str(item['http_status']))}</td>"
            f"<td>{html.escape(str(item['response_time_s']))}</td>"
            "</tr>"
        )

    sections = []
    for group in sorted(buckets, key=lambda g: (g == "未分组", g)):
        items = buckets[group]
        body = "\n".join(cell(item) for item in items)
        sections.append(
            f"  <h2>{html.escape(group)}（{len(items)}）</h2>\n"
            "  <table>\n"
            "    <thead><tr><th>站点</th><th>状态</th><th>复核</th><th>链接</th><th>HTTP</th><th>耗时</th></tr></thead>\n"
            f"    <tbody>\n{body}\n    </tbody>\n"
            "  </table>"
        )

    content = REPORT_HTML.format(
        username=html.escape(username),
        generated=time.strftime("%Y-%m-%d %H:%M:%S"),
        claimed=sum(1 for item in data if item["status"] == "已注册"),
        verified=sum(1 for item in data if item["verdict"] == "复核通过"),
        suspect=sum(1 for item in data if item["verdict"] == "存疑"),
        total=len(data),
        sections="\n".join(sections) or '  <p style="color:#6b7280">没有条目。</p>',
    )
    path.write_text(content, encoding="utf-8")
    return len(data)


def write_report_txt(path: Path, username: str, rows: Iterable[dict[str, Any]]) -> int:
    data = _report_rows(rows)
    with open(path, "w", encoding="utf-8") as fh:
        for item in data:
            line = item["url_user"] or item["site"]
            if item["verdict"]:
                line += f"  [{item['verdict']}]"
            fh.write(line + "\n")
        fh.write(f"Total Websites Username Detected On : {len(data)}\n")
    return len(data)


def write_report_csv(path: Path, username: str, rows: Iterable[dict[str, Any]]) -> int:
    data = _report_rows(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(data)
    return len(data)


def write_report_jsonl(path: Path, username: str, rows: Iterable[dict[str, Any]]) -> int:
    data = _report_rows(rows)
    with open(path, "w", encoding="utf-8") as fh:
        for item in data:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(data)


def write_report_xlsx(path: Path, username: str, rows: Iterable[dict[str, Any]]) -> int:
    import pandas as pd  # 延迟导入：没装 pandas 时其它格式照常可用

    data = _report_rows(rows)
    pd.DataFrame(data, columns=REPORT_FIELDS).to_excel(path, sheet_name="holmes-desk", index=False)
    return len(data)


REPORT_WRITERS = {
    "txt": (".txt", write_report_txt),
    "csv": (".csv", write_report_csv),
    "xlsx": (".xlsx", write_report_xlsx),
    "html": (".html", write_report_html),
    "jsonl": (".jsonl", write_report_jsonl),
}


def export_report(
    run_dir: Path,
    username: str,
    rows: Iterable[dict[str, Any]],
    formats: Iterable[str],
) -> tuple[list[Path], list[str]]:
    """导出界面上的当前结果（含复核结论与分组）。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    errors: list[str] = []
    for fmt in formats:
        suffix, writer = REPORT_WRITERS[fmt]
        target = run_dir / f"{username}{suffix}"
        try:
            writer(target, username, rows)
            written.append(target)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fmt.upper()} 导出失败：{exc}")
    return written, errors
