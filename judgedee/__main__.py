"""命令行入口：``python -m judgedee`` 或安装后的 ``judgedee``。"""

from __future__ import annotations

import argparse
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from . import __app_name__, __version__
from .paths import ICON_PATH, SITE_DATA_PATH


def _startup_log() -> Path | None:
    """双击启动时没有控制台，任何异常都得落到文件里，否则就是"点了没反应"。"""
    for base in (Path(__file__).resolve().parent.parent, Path(tempfile.gettempdir())):
        try:
            path = base / "judgedee-startup.log"
            path.touch(exist_ok=True)
            return path
        except OSError:
            continue
    return None


def _log(path: Path | None, text: str) -> None:
    if path is None:
        return
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%H:%M:%S}  {text}\n")
    except OSError:
        pass


def _run_gui(selftest: float | None) -> int:
    log = _startup_log()
    _log(log, f"start  argv={sys.argv[1:]}  python={sys.version.split()[0]}  cwd={os.getcwd()}")
    if log is not None:
        try:
            faulthandler.enable(log.open("a", encoding="utf-8"))
        except OSError:
            pass

    try:
        from .ui.app import main as gui_main

        _log(log, "import ui.app ok")
        code = gui_main(selftest)
        _log(log, f"exit   code={code}")
        return code
    except BaseException:
        _log(log, "crash:\n" + traceback.format_exc())
        raise


def _run_search(args: argparse.Namespace) -> int:
    from .engine import QueryStatus, load_sites, pick_sites, search

    site_data = load_sites(SITE_DATA_PATH)
    if args.sites:
        wanted = [s for chunk in args.sites for s in chunk.replace("，", ",").split(",")]
        site_data, missing = pick_sites(site_data, [s for s in wanted if s.strip()])
        if missing:
            print("没匹配到：" + "、".join(missing), file=sys.stderr)
    results = search(
        args.search,
        site_data,
        proxy=args.proxy or None,
        timeout=args.timeout,
        max_workers=args.workers,
    )
    hits = 0
    for site, item in sorted(results.items(), key=lambda kv: kv[0].lower()):
        status = item["status"]
        if status.status is not QueryStatus.CLAIMED and not args.all:
            continue
        if status.status is QueryStatus.CLAIMED:
            hits += 1
        print(f"{status.status.value:<10} {site:<30} {item['url_user']}")
    print(f"\n命中 {hits} 个站点 / 共检测 {len(results)} 个")
    return 0


def _install() -> int:
    from .platform_win import install_shortcut

    result = install_shortcut(ICON_PATH)
    if result["created"]:
        print("已创建快捷方式：")
        for path in result["created"]:
            print("  " + str(path))
        print("目标程序：" + str(result["target"]))
    if result["errors"]:
        print("失败：", file=sys.stderr)
        for error in result["errors"]:
            print("  " + error, file=sys.stderr)
    return 0 if result["ok"] else 1


def _uninstall() -> int:
    from .platform_win import remove_shortcut

    removed = remove_shortcut()
    if removed:
        for path in removed:
            print("已删除 " + path)
    else:
        print("没有找到快捷方式。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judgedee",
        description=f"{__app_name__} · 本地用户名检索工具（图形界面）",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} v{__version__}")
    parser.add_argument("--selftest", nargs="?", const=1.5, type=float, metavar="秒",
                        help="启动界面后自动关闭，用于检查是否能正常打开")
    parser.add_argument("--install-shortcut", action="store_true", help="在桌面和开始菜单创建快捷方式")
    parser.add_argument("--remove-shortcut", action="store_true", help="删除桌面和开始菜单里的快捷方式")
    parser.add_argument("--search", metavar="用户名", help="不开界面，直接在命令行检索一个用户名")
    parser.add_argument("--sites", nargs="*", help="配合 --search：站点名，逗号或空格分隔")
    parser.add_argument("--proxy", default="", help="配合 --search：代理地址，如 http://127.0.0.1:7897")
    parser.add_argument("--timeout", type=float, default=20.0, help="单站点超时秒数（默认 20）")
    parser.add_argument("--workers", type=int, default=20, help="并发线程数（默认 20）")
    parser.add_argument("--all", action="store_true", help="配合 --search：连未注册的站点也一起打印")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.install_shortcut:
        return _install()
    if args.remove_shortcut:
        return _uninstall()
    if args.search:
        return _run_search(args)
    return _run_gui(args.selftest)


if __name__ == "__main__":
    raise SystemExit(main())
