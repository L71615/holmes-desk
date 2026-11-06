"""主窗口。"""

from __future__ import annotations

import queue
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from .. import __app_name_zh__, __version__
from .. import config as cfg
from ..engine import (
    QueryStatus,
    SearchCancelled,
    expand_usernames,
    load_sites,
    pick_sites,
    search,
)
from ..export import export_run
from ..paths import ICON_PATH, SITE_DATA_PATH
from ..presets import preset_names, preset_text
from ..platform_win import detect_system_proxy, enable_dpi_awareness, open_path
from . import theme

STATUS_TEXT: dict[QueryStatus, tuple[str, str]] = {
    QueryStatus.CLAIMED: ("已注册", "ok"),
    QueryStatus.AVAILABLE: ("未注册", "muted"),
    QueryStatus.UNKNOWN: ("未知", "warn"),
    QueryStatus.ILLEGAL: ("格式不符", "muted"),
    QueryStatus.WAF: ("被拦截", "warn"),
}

FORMATS = (("txt", "TXT"), ("csv", "CSV"), ("xlsx", "XLSX"), ("html", "HTML"), ("jsonl", "JSONL"))


class _QueueNotify:
    """把引擎回调转成队列消息；用户点「停止」时抛出 SearchCancelled 结束检索。"""

    def __init__(self, q: queue.Queue, username: str, cancel: threading.Event) -> None:
        self.queue = q
        self.username = username
        self.cancel = cancel

    def start(self, _name: str) -> None:  # 引擎开始检索某个用户名
        pass

    def update(self, result) -> None:
        self.queue.put(("result", self.username, result))
        if self.cancel.is_set():
            raise SearchCancelled()


class App(tk.Tk):
    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()

        self.cfg = cfg.load()
        self.s = self.winfo_fpixels("1i") / 96.0  # 200% 屏幕上 = 2.0
        try:
            self.site_total = len(load_sites(SITE_DATA_PATH))
        except Exception:  # noqa: BLE001
            self.site_total = 0
        self.show_all = bool(self.cfg.get("show_all"))

        self.title(f"{__app_name_zh__} · 本地版 v{__version__}")
        try:
            if ICON_PATH.exists():
                self.iconbitmap(default=str(ICON_PATH))
        except tk.TclError:
            pass

        theme.apply_style(self, self.px)
        self._build_ui()
        self._place_window()

        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.rows: dict[str, dict] = {}
        self.total = 0
        self.done = 0
        self.started_at = 0.0

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-Return>", lambda _e: self.start_search())
        self.bind("<Escape>", lambda _e: self.stop_search())
        self.after(80, self._pump)

    # ---------- 尺寸 ----------
    def px(self, value: float) -> int:
        return int(round(value * self.s))

    def _place_window(self) -> None:
        width, height = self.px(1120), self.px(780)
        self.minsize(self.px(940), self.px(620))
        geometry = self.cfg.get("geometry") or ""
        if geometry:
            try:
                self.geometry(geometry)
                return
            except tk.TclError:
                pass
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ---------- 界面 ----------
    def _build_ui(self) -> None:
        px = self.px

        header = tk.Frame(self, bg=theme.HEADER, height=px(74))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text=__app_name_zh__, bg=theme.HEADER, fg="white",
            font=(theme.FONT, 16, "bold"),
        ).pack(side="left", padx=px(24))
        tk.Label(
            header, text=f"本地单机 · {self.site_total} 站点 · v{__version__}",
            bg=theme.HEADER, fg="#93a4c4", font=(theme.FONT, 9),
        ).pack(side="left", pady=(px(8), 0))

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, padx=px(16), pady=px(12))

        card = ttk.Frame(body, style="Card.TFrame", padding=px(16))
        card.pack(fill="x")

        # 第一行：用户名 / 预设 / 站点（标签一行、输入框一行，水平对齐）
        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill="x")
        row1.columnconfigure(0, weight=3)
        row1.columnconfigure(1, weight=2)
        row1.columnconfigure(2, weight=4)

        ttk.Label(row1, text="用户名", style="Field.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, px(4))
        )
        ttk.Label(row1, text="站点预设", style="Field.TLabel").grid(
            row=0, column=1, sticky="w", padx=(px(12), 0), pady=(0, px(4))
        )
        ttk.Label(row1, text="站点（留空 = 全部站点，可手填）", style="Field.TLabel").grid(
            row=0, column=2, sticky="w", padx=(px(12), 0), pady=(0, px(4))
        )

        self.ent_users = ttk.Entry(row1)
        self.ent_users.grid(row=1, column=0, sticky="ew")
        self.cmb_preset = ttk.Combobox(row1, values=preset_names(), state="readonly")
        self.cmb_preset.grid(row=1, column=1, sticky="ew", padx=(px(12), 0))
        self.cmb_preset.set(self.cfg.get("preset") or "全部站点")
        self.cmb_preset.bind("<<ComboboxSelected>>", self._on_preset_change)
        self.ent_sites = ttk.Entry(row1)
        self.ent_sites.grid(row=1, column=2, sticky="ew", padx=(px(12), 0))

        ttk.Label(
            card, text="多个用户名用空格或逗号分隔；填 {?} 会自动展开成 _ - . 三种变体",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(px(6), px(10)))

        # 第二行：代理 / 超时 / 开关
        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x")
        row2.columnconfigure(1, weight=1)

        ttk.Label(row2, text="代理", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, px(8)))
        self.ent_proxy = ttk.Entry(row2)
        self.ent_proxy.grid(row=0, column=1, sticky="ew", padx=(0, px(16)))
        proxy = self.cfg.get("proxy") or ""
        if not proxy:
            proxy = detect_system_proxy()
        self.ent_proxy.insert(0, proxy)

        ttk.Label(row2, text="超时（秒）", style="Field.TLabel").grid(row=0, column=2, sticky="w")
        self.spn_timeout = ttk.Spinbox(row2, from_=5, to=120, increment=5, width=6)
        self.spn_timeout.set(self.cfg.get("timeout") or 20)
        self.spn_timeout.grid(row=0, column=3, sticky="w", padx=(px(6), px(18)))

        self.var_nsfw = tk.BooleanVar(value=bool(self.cfg.get("include_nsfw")))
        self.var_showall = tk.BooleanVar(value=bool(self.cfg.get("show_all")))
        ttk.Checkbutton(row2, text="包含 NSFW 站点", variable=self.var_nsfw).grid(
            row=0, column=4, padx=(0, px(14))
        )
        ttk.Checkbutton(row2, text="结果里显示未注册", variable=self.var_showall).grid(row=0, column=5)

        # 第三行：导出
        row3 = ttk.Frame(card, style="Card.TFrame")
        row3.pack(fill="x", pady=(px(10), 0))
        row3.columnconfigure(8, weight=1)

        ttk.Label(row3, text="导出", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, px(8)))
        self.var_formats: dict[str, tk.BooleanVar] = {}
        for index, (key, label) in enumerate(FORMATS):
            var = tk.BooleanVar(value=bool(self.cfg.get(f"export_{key}", key in ("txt", "csv"))))
            self.var_formats[key] = var
            ttk.Checkbutton(row3, text=label, variable=var).grid(row=0, column=1 + index, padx=(0, px(10)))

        ttk.Label(row3, text="目录", style="Field.TLabel").grid(row=0, column=7, padx=(px(8), px(6)))
        self.ent_out = ttk.Entry(row3)
        self.ent_out.grid(row=0, column=8, sticky="ew")
        self.ent_out.insert(0, self.cfg.get("out_dir") or str(Path.cwd() / "results"))
        ttk.Button(row3, text="浏览…", style="Ghost.TButton", command=self._pick_dir).grid(
            row=0, column=9, padx=(px(6), 0)
        )

        # 操作行
        actions = ttk.Frame(body, style="TFrame")
        actions.pack(fill="x", pady=(px(10), px(8)))

        self.btn_start = ttk.Button(actions, text="开始检索", style="Accent.TButton", command=self.start_search)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(actions, text="停止", style="Ghost.TButton", command=self.stop_search, state="disabled")
        self.btn_stop.pack(side="left", padx=px(8))
        self.btn_open = ttk.Button(actions, text="打开结果目录", style="Ghost.TButton", command=self._open_out)
        self.btn_open.pack(side="left")

        self.lbl_status = ttk.Label(actions, text="就绪", style="TLabel", foreground=theme.MUTED)
        self.lbl_status.pack(side="right")

        self.progress = ttk.Progressbar(body, mode="determinate", maximum=1)
        self.progress.pack(fill="x")

        # 结果区
        result_card = ttk.Frame(body, style="Card.TFrame", padding=px(12))
        result_card.pack(fill="both", expand=True, pady=(px(8), 0))

        toolbar = ttk.Frame(result_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, px(8)))
        self.lbl_count = ttk.Label(toolbar, text="命中 0 个", style="Card.TLabel", font=(theme.FONT, 10, "bold"))
        self.lbl_count.pack(side="left")
        ttk.Label(toolbar, text="筛选", style="Hint.TLabel").pack(side="left", padx=(px(16), px(6)))
        self.ent_filter = ttk.Entry(toolbar, width=22)
        self.ent_filter.pack(side="left")
        self.ent_filter.bind("<KeyRelease>", lambda _e: self._render())
        ttk.Button(toolbar, text="清空", style="Ghost.TButton", command=self.clear_results).pack(side="right")

        table = ttk.Frame(result_card, style="Card.TFrame")
        table.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(table, columns=("site", "status", "link", "http", "time"), show="headings")
        for key, label, width, anchor in (
            ("site", "站点", 220, "w"),
            ("status", "状态", 90, "w"),
            ("link", "链接", 520, "w"),
            ("http", "HTTP", 70, "center"),
            ("time", "耗时", 80, "center"),
        ):
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=key in ("link", "site"))

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("ok", foreground=theme.OK)
        self.tree.tag_configure("warn", foreground=theme.WARN)
        self.tree.tag_configure("muted", foreground=theme.GRAY)
        self.tree.bind("<Double-1>", self._open_selected)

    # ---------- 交互 ----------
    def _on_preset_change(self, _event=None) -> None:
        text = preset_text(self.cmb_preset.get())
        self.ent_sites.delete(0, "end")
        self.ent_sites.insert(0, text)

    def _pick_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.ent_out.get() or str(Path.cwd()))
        if chosen:
            self.ent_out.delete(0, "end")
            self.ent_out.insert(0, chosen)

    def _out_dir(self) -> Path:
        raw = self.ent_out.get().strip() or str(Path.cwd() / "results")
        return Path(raw).expanduser()

    def _open_out(self) -> None:
        target = self._out_dir()
        target.mkdir(parents=True, exist_ok=True)
        open_path(target)

    def _open_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        url = self.rows.get(selection[0], {}).get("url_user")
        if url:
            webbrowser.open(url)

    def clear_results(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.lbl_count.configure(text="命中 0 个")

    # ---------- 检索 ----------
    def start_search(self) -> None:
        if self.busy:
            return
        usernames = expand_usernames(self.ent_users.get())
        if not usernames:
            messagebox.showinfo("提示", "先填一个用户名，比如 sherlock")
            return

        try:
            site_data = load_sites(SITE_DATA_PATH)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("读取站点表失败", str(exc))
            return

        raw_sites = self.ent_sites.get().replace("，", ",").strip()
        # 有逗号就按逗号切（站点名可能带空格，如 "Steam Community (User)"）
        wanted = [w.strip() for w in raw_sites.split(",") if w.strip()] if "," in raw_sites else raw_sites.split()
        selected, missing = pick_sites(site_data, wanted)
        if not selected:
            messagebox.showerror("没有可用站点", "站点名一个都没匹配上，检查一下拼写。")
            return
        if missing:
            messagebox.showwarning("部分站点没找到", "这些名字没匹配上：\n" + "、".join(missing[:12]))

        if not self.var_nsfw.get():
            selected = {k: v for k, v in selected.items() if not v.get("isNSFW")}
        if not selected:
            messagebox.showerror("没有可用站点", "过滤掉 NSFW 之后一个站点都不剩了。")
            return

        self.clear_results()
        self.busy = True
        self.cancel_event.clear()
        self.total = len(usernames) * len(selected)
        self.done = 0
        self.started_at = time.time()
        self.progress.configure(maximum=max(1, self.total), value=0)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._status(f"检索中 · 0/{self.total}")

        show_all = bool(self.var_showall.get())
        self.show_all = show_all
        proxy = self.ent_proxy.get().strip() or None
        timeout = float(self.spn_timeout.get() or 20)
        out_dir = self._out_dir()
        formats = [key for key, var in self.var_formats.items() if var.get()]

        self.worker = threading.Thread(
            target=self._worker,
            args=(usernames, selected, proxy, timeout, out_dir, formats, show_all),
            daemon=True,
        )
        self.worker.start()

    def stop_search(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self._status("正在停止…")

    def _worker(
        self,
        usernames: list[str],
        site_data: dict,
        proxy: str | None,
        timeout: float,
        out_dir: Path,
        formats: list[str],
        show_all: bool,
    ) -> None:
        try:
            for index, username in enumerate(usernames, start=1):
                if self.cancel_event.is_set():
                    raise SearchCancelled()

                self.queue.put(("user", username, index, len(usernames)))
                results = search(
                    username,
                    site_data,
                    notify=_QueueNotify(self.queue, username, self.cancel_event),
                    proxy=proxy,
                    timeout=timeout,
                    cancel=self.cancel_event,
                )

                written: list[Path] = []
                errors: list[str] = []
                if formats:
                    run_dir = out_dir / time.strftime("%Y%m%d-%H%M%S")
                    written, errors = export_run(run_dir, username, results, formats, show_all)

                self.queue.put(("user_done", username, written, errors, sum(
                    1 for item in results.values()
                    if item["status"].status is QueryStatus.CLAIMED
                )))
        except SearchCancelled:
            self.queue.put(("cancelled",))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            self.queue.put(("done",))

    # ---------- 队列 ----------
    def _pump(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                kind = message[0]
                if kind == "result":
                    self._add_result(message[1], message[2])
                elif kind == "user":
                    _, username, index, count = message
                    self._status(f"检索 {username}（第 {index}/{count} 个） · {self.done}/{self.total}")
                elif kind == "user_done":
                    _, username, written, errors, hits = message
                    self._finish_user(username, written, errors, hits)
                elif kind == "cancelled":
                    self._status("已停止")
                elif kind == "error":
                    self._status("出错了")
                    messagebox.showerror("出错", message[1])
                elif kind == "done":
                    self._done()
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def _add_result(self, username: str, result) -> None:
        self.done += 1
        self.progress.configure(value=self.done)

        if not self.show_all and result.status is not QueryStatus.CLAIMED:
            self._status(f"检索中 · {self.done}/{self.total}")
            return

        label, tag = STATUS_TEXT.get(result.status, ("未知", "muted"))
        item_id = f"{username}|{result.site_name}"
        self.rows[item_id] = {
            "username": username,
            "site": result.site_name,
            "url_user": result.site_url_user,
            "status": label,
            "http": result.http_status if result.http_status is not None else "—",
            "time": "" if result.query_time is None else f"{result.query_time:.2f}s",
            "tag": tag,
        }
        if self.ent_filter.get().strip():
            self._render()
        else:
            self._insert_row(item_id)
            self.lbl_count.configure(text=f"命中 {len(self.rows)} 个 · 显示 {len(self.rows)} 条")
        self._status(f"检索中 · {self.done}/{self.total}")

    def _insert_row(self, item_id: str) -> None:
        row = self.rows[item_id]
        self.tree.insert(
            "",
            "end",
            iid=item_id,
            values=(row["site"], row["status"], row["url_user"] or "—", row["http"], row["time"]),
            tags=(row["tag"],),
        )

    def _render(self) -> None:
        """按筛选词重建结果表（行数最多几百，重建比增量隐藏简单可靠）。"""
        keyword = self.ent_filter.get().strip().lower()
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        shown = 0
        for item_id, row in self.rows.items():
            haystack = f"{row['site']} {row['url_user']}".lower()
            if keyword and keyword not in haystack:
                continue
            self._insert_row(item_id)
            shown += 1
        self.lbl_count.configure(text=f"命中 {len(self.rows)} 个 · 显示 {shown} 条")

    def _finish_user(self, username: str, written: list[Path], errors: list[str], hits: int) -> None:
        detail = f"{username}：命中 {hits} 个站点"
        if written:
            detail += f"，已导出到 {written[0].parent}"
        if errors:
            detail += "；" + "；".join(errors)
        self._status(detail)

    def _done(self) -> None:
        self.busy = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if self.cancel_event.is_set():
            return
        elapsed = time.time() - self.started_at
        self._status(f"完成 · {len(self.rows)} 个命中 · 用时 {elapsed:.1f} 秒")

    def _status(self, text: str) -> None:
        self.lbl_status.configure(text=text)

    # ---------- 收尾 ----------
    def _on_close(self) -> None:
        if self.busy and not messagebox.askyesno("还在检索", "检索还没结束，确定退出？"):
            return
        self.cancel_event.set()
        data = dict(self.cfg)
        data.update(
            {
                "usernames": self.ent_users.get(),
                "sites": self.ent_sites.get(),
                "preset": self.cmb_preset.get(),
                "proxy": self.ent_proxy.get(),
                "timeout": self.spn_timeout.get(),
                "include_nsfw": self.var_nsfw.get(),
                "show_all": self.var_showall.get(),
                "out_dir": self.ent_out.get(),
                "geometry": self.winfo_geometry(),
            }
        )
        for key in self.var_formats:
            data[f"export_{key}"] = self.var_formats[key].get()
        try:
            cfg.save(data)
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def main(selftest_seconds: float | None = None) -> int:
    app = App()
    if selftest_seconds:
        app.after(int(selftest_seconds * 1000), app.destroy)
    app.mainloop()
    return 0
