"""检索页：左边勾站点分组，右边填参数、看结果。"""

from __future__ import annotations

import queue
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..engine import QueryStatus, SearchCancelled, expand_usernames, pick_sites, search
from ..export import export_report, export_run
from ..history import status_key
from ..identity import MERGE_THRESHOLD, Account, cluster_accounts
from ..presets import preset_names, preset_text
from ..profile import collect as collect_profiles
from ..verify import VERDICT_TEXT, verify_claimed
from . import theme
from .dialog_identity import IdentityDialog

STATUS_TEXT: dict[QueryStatus, tuple[str, str]] = {
    QueryStatus.CLAIMED: ("已注册", "ok"),
    QueryStatus.AVAILABLE: ("未注册", "muted"),
    QueryStatus.UNKNOWN: ("未知", "warn"),
    QueryStatus.ILLEGAL: ("格式不符", "muted"),
    QueryStatus.WAF: ("被拦截", "warn"),
}

FORMATS = (("txt", "TXT"), ("csv", "CSV"), ("xlsx", "XLSX"), ("html", "HTML"), ("jsonl", "JSONL"))

# 状态筛选下拉：显示文字 → 内部 status_key（None 表示不过滤）
STATUS_FILTERS = {
    "全部": None,
    "已注册": "claimed",
    "未注册": "available",
    "未知": "unknown",
    "格式不符": "illegal",
    "被拦截": "waf",
}

CHECKED = "☑"
UNCHECKED = "☐"


class _QueueNotify:
    """把引擎回调转成队列消息；点「停止」时抛出 SearchCancelled 结束检索。"""

    def __init__(self, q: queue.Queue, username: str, cancel: threading.Event) -> None:
        self.queue = q
        self.username = username
        self.cancel = cancel

    def start(self, _name: str) -> None:
        pass

    def update(self, result) -> None:
        self.queue.put(("result", self.username, result))
        if self.cancel.is_set():
            raise SearchCancelled()


class SearchPage(ttk.Frame):
    def __init__(self, master: tk.Misc, shell) -> None:
        super().__init__(master, style="TFrame")
        self.shell = shell
        self.px = shell.px
        self.cfg = shell.cfg

        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel_event = threading.Event()
        self.rows: dict[str, dict] = {}
        self.run_rows: list[dict] = []
        self.checked: set[str] = set()
        self.total = 0
        self.done = 0
        self.started_at = 0.0
        self.last_out_dir = ""
        self.clusters: list = []
        self.review_pairs: list = []
        self.busy_identity = False

        self._build()
        self._load_state()

        self.bind("<Control-Return>", lambda _e: self.start_search())
        self.bind("<Escape>", lambda _e: self.stop_search())
        self.after(80, self._pump)

    # ---------- 界面 ----------
    def _build(self) -> None:
        px = self.px
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # 左：站点范围
        left = ttk.Frame(self, style="Card.TFrame", padding=px(10))
        left.grid(row=0, column=0, sticky="nsew")
        left.configure(width=px(240))

        ttk.Label(left, text="站点范围", style="Field.TLabel").pack(anchor="w")
        ttk.Label(
            left, text="勾选分组或单个站点；一个都不勾 = 用右边的站点框",
            style="Hint.TLabel", wraplength=px(215),
        ).pack(anchor="w", pady=(px(2), px(8)))

        self.ent_site_filter = ttk.Entry(left)
        self.ent_site_filter.pack(fill="x")
        self.ent_site_filter.bind("<KeyRelease>", lambda _e: self._fill_tree())

        row = ttk.Frame(left, style="Card.TFrame")
        row.pack(fill="x", pady=(px(8), px(6)))
        ttk.Button(row, text="全选", style="Ghost.TButton", command=self._check_all).pack(
            side="left", expand=True, fill="x"
        )
        ttk.Button(row, text="清空", style="Ghost.TButton", command=self._uncheck_all).pack(
            side="left", expand=True, fill="x", padx=(px(6), 0)
        )

        tree_wrap = ttk.Frame(left, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        self.tree_sites = ttk.Treeview(tree_wrap, show="tree", selectmode="none")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree_sites.yview)
        self.tree_sites.configure(yscrollcommand=scroll.set)
        self.tree_sites.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree_sites.tag_configure("group", font=(theme.FONT, 9, "bold"))
        self.tree_sites.bind("<Button-1>", self._on_tree_click)

        self.lbl_checked = ttk.Label(left, text="已选 0 站", style="Hint.TLabel")
        self.lbl_checked.pack(anchor="w", pady=(px(6), 0))

        # 右：表单 + 结果
        right = ttk.Frame(self, style="TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(px(10), 0))

        card = ttk.Frame(right, style="Card.TFrame", padding=px(14))
        card.pack(fill="x")

        row1 = ttk.Frame(card, style="Card.TFrame")
        row1.pack(fill="x")
        row1.columnconfigure(0, weight=3)
        row1.columnconfigure(1, weight=2)
        row1.columnconfigure(2, weight=4)

        ttk.Label(row1, text="用户名", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, px(4)))
        ttk.Label(row1, text="站点预设", style="Field.TLabel").grid(
            row=0, column=1, sticky="w", padx=(px(12), 0), pady=(0, px(4))
        )
        ttk.Label(row1, text="附加站点（可选，逗号分隔）", style="Field.TLabel").grid(
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
        ).pack(anchor="w", pady=(px(6), px(8)))

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x")
        row2.columnconfigure(1, weight=1)

        ttk.Label(row2, text="代理", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, px(8)))
        self.ent_proxy = ttk.Entry(row2)
        self.ent_proxy.grid(row=0, column=1, sticky="ew", padx=(0, px(16)))
        self.ent_proxy.insert(0, self.cfg.get("proxy") or "")

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

        row3 = ttk.Frame(card, style="Card.TFrame")
        row3.pack(fill="x", pady=(px(10), 0))

        ttk.Label(row3, text="导出", style="Field.TLabel").pack(side="left", padx=(0, px(8)))
        self.var_formats: dict[str, tk.BooleanVar] = {}
        for key, label in FORMATS:
            var = tk.BooleanVar(value=bool(self.cfg.get(f"export_{key}", key in ("txt", "csv"))))
            self.var_formats[key] = var
            ttk.Checkbutton(row3, text=label, variable=var).pack(side="left", padx=(0, px(10)))

        row4 = ttk.Frame(card, style="Card.TFrame")
        row4.pack(fill="x", pady=(px(8), 0))
        row4.columnconfigure(1, weight=1)

        ttk.Label(row4, text="结果目录", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, px(8)))
        self.ent_out = ttk.Entry(row4)
        self.ent_out.grid(row=0, column=1, sticky="ew")
        self.ent_out.insert(0, self.cfg.get("out_dir") or str(Path.cwd() / "results"))
        ttk.Button(row4, text="浏览…", style="Ghost.TButton", command=self._pick_dir).grid(
            row=0, column=2, padx=(px(6), 0)
        )

        actions = ttk.Frame(right, style="TFrame")
        actions.pack(fill="x", pady=(px(10), px(6)))

        self.btn_start = ttk.Button(actions, text="开始检索", style="Accent.TButton", command=self.start_search)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(
            actions, text="停止", style="Ghost.TButton", command=self.stop_search, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=px(8))
        self.btn_verify = ttk.Button(
            actions, text="复核已注册", style="Ghost.TButton", command=self.verify_rows, state="disabled"
        )
        self.btn_verify.pack(side="left", padx=(0, px(8)))
        self.btn_identity = ttk.Button(
            actions,
            text="身份分析",
            style="Ghost.TButton",
            command=self.analyze_identity,
            state="disabled",
        )
        self.btn_identity.pack(side="left", padx=(0, px(8)))
        self.btn_open = ttk.Button(actions, text="打开结果目录", style="Ghost.TButton", command=self._open_out)
        self.btn_open.pack(side="left", padx=(0, px(8)))
        self.btn_report = ttk.Button(
            actions, text="导出报告", style="Ghost.TButton", command=self.export_report_clicked, state="disabled"
        )
        self.btn_report.pack(side="left")

        status_row = ttk.Frame(right, style="TFrame")
        status_row.pack(fill="x", pady=(0, px(6)))
        self.lbl_status = ttk.Label(
            status_row, text="就绪", style="TLabel", foreground=theme.MUTED, anchor="e"
        )
        self.lbl_status.pack(side="right")

        self.progress = ttk.Progressbar(right, mode="determinate", maximum=1)
        self.progress.pack(fill="x")

        result_card = ttk.Frame(right, style="Card.TFrame", padding=px(12))
        result_card.pack(fill="both", expand=True, pady=(px(8), 0))

        toolbar = ttk.Frame(result_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, px(8)))
        self.lbl_count = ttk.Label(toolbar, text="命中 0 个", style="Card.TLabel", font=(theme.FONT, 10, "bold"))
        self.lbl_count.pack(side="left")
        ttk.Label(toolbar, text="筛选", style="Hint.TLabel").pack(side="left", padx=(px(16), px(6)))
        self.ent_filter = ttk.Entry(toolbar, width=18)
        self.ent_filter.pack(side="left")
        self.ent_filter.bind("<KeyRelease>", lambda _e: self._render())

        self.cmb_status = ttk.Combobox(
            toolbar, state="readonly", width=8, values=list(STATUS_FILTERS)
        )
        self.cmb_status.set("全部")
        self.cmb_status.pack(side="left", padx=(px(10), 0))
        self.cmb_status.bind("<<ComboboxSelected>>", lambda _e: self._render())

        ttk.Button(toolbar, text="清空", style="Ghost.TButton", command=self.clear_results).pack(side="right")

        table = ttk.Frame(result_card, style="Card.TFrame")
        table.pack(fill="both", expand=True)

        columns = (
            ("site", "站点", 180, "w", True),
            ("status", "状态", 80, "w", False),
            ("identity", "档案", 60, "center", False),
            ("verdict", "复核", 90, "w", False),
            ("link", "链接", 380, "w", True),
            ("http", "HTTP", 60, "center", False),
            ("time", "耗时", 70, "center", False),
        )
        self.tree = ttk.Treeview(table, columns=[c[0] for c in columns], show="headings")
        for key, label, width, anchor, stretch in columns:
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=stretch)

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("ok", foreground=theme.OK)
        self.tree.tag_configure("warn", foreground=theme.WARN)
        self.tree.tag_configure("muted", foreground=theme.GRAY)
        self.tree.tag_configure("bad", foreground=theme.BAD)
        self.tree.bind("<Double-1>", self._open_selected)

    # ---------- 站点树 ----------
    def _load_state(self) -> None:
        self.ent_users.insert(0, self.cfg.get("usernames") or "")
        self.ent_sites.insert(0, self.cfg.get("sites") or "")
        checked = self.cfg.get("checked_sites")
        if isinstance(checked, list):
            self.checked = {str(name) for name in checked}
        self._fill_tree()

    def _match(self, name: str, keyword: str) -> bool:
        if not keyword:
            return True
        label = self.shell.lib.label(name).lower()
        return keyword in name.lower() or keyword in label

    def _fill_tree(self) -> None:
        tree = self.tree_sites
        tree.delete(*tree.get_children())
        lib = self.shell.lib
        keyword = self.ent_site_filter.get().strip().lower()

        for group in lib.group_names():
            members = [n for n in lib.members(group) if self._match(n, keyword)]
            if not members:
                continue
            picked = sum(1 for n in members if n in self.checked)
            mark = CHECKED if picked == len(members) else (f"{CHECKED}" if picked else UNCHECKED)
            tree.insert(
                "", "end", iid=f"g::{group}",
                text=f"{mark} {group}（{picked}/{len(members)}）",
                open=bool(keyword) or any(n in self.checked for n in members),
                tags=("group",),
            )
            for name in members:
                label = lib.label(name)
                if lib.is_enabled(name):
                    text = f"{CHECKED if name in self.checked else UNCHECKED} {label}"
                else:
                    text = f"· {label}（已禁用）"
                tree.insert(f"g::{group}", "end", iid=f"s::{name}", text=text)
        self._update_checked_label()

    def _update_checked_label(self) -> None:
        self.lbl_checked.configure(text=f"已选 {len(self.checked)} 站")

    def _on_tree_click(self, event) -> None:
        iid = self.tree_sites.identify_row(event.y)
        if not iid:
            return
        lib = self.shell.lib
        keyword = self.ent_site_filter.get().strip().lower()
        if iid.startswith("g::"):
            group = iid[3:]
            members = [n for n in lib.members(group) if self._match(n, keyword) and lib.is_enabled(n)]
            target = all(n in self.checked for n in members)
            for name in members:
                if target:
                    self.checked.discard(name)
                else:
                    self.checked.add(name)
        else:
            name = iid[3:]
            if not lib.is_enabled(name):
                return
            if name in self.checked:
                self.checked.discard(name)
            else:
                self.checked.add(name)
        self._fill_tree()

    def _check_all(self) -> None:
        keyword = self.ent_site_filter.get().strip().lower()
        self.checked = {n for n in self.shell.lib.enabled_names() if self._match(n, keyword)}
        self._fill_tree()

    def _uncheck_all(self) -> None:
        self.checked.clear()
        self._fill_tree()

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
        target = Path(self.last_out_dir) if self.last_out_dir else self._out_dir()
        target.mkdir(parents=True, exist_ok=True)
        from ..platform_win import open_path

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
        self.run_rows.clear()
        self.lbl_count.configure(text="命中 0 个")
        self.btn_verify.configure(state="disabled")
        self.btn_identity.configure(state="disabled")
        self.btn_report.configure(state="disabled")
        self.clusters = []
        self.review_pairs = []

    def export_report_clicked(self) -> None:
        if not self.rows:
            messagebox.showinfo("没有结果", "先跑一次检索，再来导出报告。")
            return
        formats = [key for key, var in self.var_formats.items() if var.get()]
        if not formats:
            messagebox.showinfo("没有选择格式", "至少勾选一种导出格式。")
            return
        usernames = sorted({row["username"] for row in self.rows.values()})
        if len(usernames) == 1:
            name = usernames[0]
        elif len(usernames) <= 3:
            name = "-".join(usernames)
        else:
            name = f"{usernames[0]}-等{len(usernames)}人"
        out_dir = Path(self.ent_out.get().strip() or "results")
        run_dir = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-report"
        written, errors = export_report(run_dir, name, self.rows.values(), formats)
        if written:
            self.last_out_dir = str(run_dir)
            self._status(f"报告已导出到 {run_dir}")
        if errors:
            messagebox.showwarning("部分格式失败", "\n".join(errors))

    # ---------- 检索 ----------
    def _resolve_sites(self) -> tuple[dict, list[str]]:
        lib = self.shell.lib
        raw_sites = self.ent_sites.get().replace("，", ",").strip()
        wanted = [w.strip() for w in raw_sites.split(",") if w.strip()] if "," in raw_sites else raw_sites.split()

        if self.checked:
            selected = {n: lib.sites[n] for n in lib.names() if n in self.checked and lib.is_enabled(n)}
            missing: list[str] = []
        elif wanted:
            selected, missing = pick_sites(lib.sites, wanted)
            selected = {k: v for k, v in selected.items() if lib.is_enabled(k)}
        else:
            selected, missing = lib.selection(), []
        return selected, missing

    def start_search(self) -> None:
        if self.busy:
            return
        usernames = expand_usernames(self.ent_users.get())
        if not usernames:
            messagebox.showinfo("提示", "先填一个用户名，比如 sherlock")
            return

        selected, missing = self._resolve_sites()
        if not selected:
            messagebox.showerror("没有可用站点", "站点一个都没选上，检查一下勾选或右侧的站点框。")
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
        proxy = self.ent_proxy.get().strip() or None
        timeout = float(self.spn_timeout.get() or 20)
        out_dir = self._out_dir()
        formats = [key for key, var in self.var_formats.items() if var.get()]

        threading.Thread(
            target=self._worker,
            args=(usernames, selected, proxy, timeout, out_dir, formats, show_all),
            daemon=True,
        ).start()

    def stop_search(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self._status("正在停止…")

    def _worker(self, usernames, site_data, proxy, timeout, out_dir, formats, show_all) -> None:
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

                hits = sum(1 for item in results.values() if item["status"].status is QueryStatus.CLAIMED)
                self.queue.put(("user_done", username, written, errors, hits))
        except SearchCancelled:
            self.queue.put(("cancelled",))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            self.queue.put(("done",))

    # ---------- 复核 ----------
    def verify_rows(self) -> None:
        claimed = [
            (row["username"], row["site"])
            for row in self.rows.values()
            if row["status_key"] == "claimed"
        ]
        for row in self.rows.values():
            if row["status_key"] == "claimed":
                row["verdict"] = "复核中…"
                row["verdict_tag"] = ""
        self._render()
        if not claimed:
            messagebox.showinfo("没有可复核的", "当前结果里没有「已注册」的条目。")
            return

        self.btn_verify.configure(state="disabled")
        proxy = self.ent_proxy.get().strip() or None
        timeout = float(self.spn_timeout.get() or 20)
        site_data = self.shell.lib.sites

        def on_result(payload: dict) -> None:
            self.queue.put(("verdict", payload))

        threading.Thread(
            target=lambda: verify_claimed(
                claimed, site_data, proxy=proxy, timeout=timeout, on_result=on_result
            ),
            daemon=True,
        ).start()

    # ---------- 身份分析 ----------
    def analyze_identity(self) -> None:
        if self.busy_identity:
            return
        claimed = [row for row in self.rows.values() if row["status_key"] == "claimed"]
        if not claimed:
            messagebox.showinfo("没有可分析的", "当前结果里没有「已注册」的条目。")
            return

        self.busy_identity = True
        self.btn_identity.configure(state="disabled")
        self._status(f"身份分析 · 正在抓取 {len(claimed)} 个主页…")
        proxy = self.ent_proxy.get().strip() or None
        timeout = max(8.0, float(self.spn_timeout.get() or 20))
        threading.Thread(
            target=self._identity_worker,
            args=(list(claimed), proxy, timeout),
            daemon=True,
        ).start()

    def _identity_worker(self, rows: list[dict], proxy, timeout: float) -> None:
        try:
            from ..config import config_dir

            avatar_dir = Path(config_dir()) / "avatars"
            pairs = [(row["username"], row["site"], row["url_user"]) for row in rows if row["url_user"]]

            def on_progress(done: int, total: int, _profile) -> None:
                self.queue.put(("identity_progress", done, total))

            profiles = collect_profiles(
                pairs,
                proxy=proxy,
                timeout=timeout,
                workers=8,
                avatar_dir=avatar_dir,
                on_progress=on_progress,
            )
            accounts = [
                Account(
                    username=p.username,
                    site=p.site,
                    url=p.url,
                    display_name=p.display_name,
                    bio=p.bio,
                    avatar_a=p.avatar_a,
                    avatar_d=p.avatar_d,
                    avatar_path=p.avatar_path,
                    links=list(p.links),
                    mentions=list(p.mentions),
                    lang=p.lang,
                    ok=p.ok,
                )
                for p in profiles
            ]
            clusters, review = cluster_accounts(accounts)
            self.queue.put(("identity_done", clusters, review))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("identity_error", f"{type(exc).__name__}: {exc}"))

    def _apply_identity(self, clusters, review) -> None:
        self.busy_identity = False
        self.btn_identity.configure(state="normal")
        self.clusters = clusters
        self.review_pairs = review
        for cluster in clusters:
            for account in cluster.accounts:
                row = self.rows.get(f"{account.username}|{account.site}")
                if row:
                    row["identity"] = cluster.label
        self._render()
        merged = [c for c in clusters if c.size > 1]
        self._status(
            f"身份分析完成 · {len(clusters)} 个档案 · {len(merged)} 个合并组 · {len(review)} 组待确认"
        )
        IdentityDialog(self.winfo_toplevel(), clusters, review, self.px)

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
                elif kind == "verdict":
                    self._apply_verdict(message[1])
                elif kind == "identity_progress":
                    _, done, total = message
                    self._status(f"身份分析 · 抓取主页 {done}/{total}")
                elif kind == "identity_done":
                    self._apply_identity(message[1], message[2])
                elif kind == "identity_error":
                    self.busy_identity = False
                    self.btn_identity.configure(state="normal")
                    self._status("身份分析失败")
                    messagebox.showerror("身份分析失败", message[1])
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

        if not self.var_showall.get() and result.status is not QueryStatus.CLAIMED:
            self._status(f"检索中 · {self.done}/{self.total}")
            return

        label, tag = STATUS_TEXT.get(result.status, ("未知", "muted"))
        item_id = f"{username}|{result.site_name}"
        key = status_key(result.status)
        row = {
            "username": username,
            "site": result.site_name,
            "group": self.shell.lib.group_of(result.site_name),
            "url_user": result.site_url_user,
            "status": label,
            "status_key": key,
            "verdict": "",
            "verdict_tag": "",
            "identity": "",
            "http": result.http_status if result.http_status is not None else "—",
            "time": "" if result.query_time is None else f"{result.query_time:.2f}s",
            "tag": tag,
        }
        self.rows[item_id] = row
        self.run_rows.append(
            {
                "username": username,
                "site": result.site_name,
                "status": key,
                "url": result.site_url_user,
                "http": result.http_status,
                "elapsed": result.query_time,
            }
        )

        if self.ent_filter.get().strip():
            self._render()
        else:
            self._insert_row(item_id)
            self.lbl_count.configure(text=f"命中 {len(self.rows)} 个 · 显示 {len(self.rows)} 条")
        if key == "claimed":
            self.btn_verify.configure(state="normal")
            self.btn_identity.configure(state="normal")
        self.btn_report.configure(state="normal")
        self._status(f"检索中 · {self.done}/{self.total}")

    def _apply_verdict(self, payload: dict) -> None:
        item_id = f"{payload['username']}|{payload['site']}"
        row = self.rows.get(item_id)
        if not row:
            return
        verdict = payload.get("verdict", "unknown")
        row["verdict"] = VERDICT_TEXT.get(verdict, "无法确认")
        row["verdict_tag"] = {"confirmed": "ok", "suspect": "bad", "unknown": "warn"}.get(verdict, "warn")
        if self.rows and all(r.get("verdict") not in ("", "复核中…") for r in self.rows.values() if r["status_key"] == "claimed"):
            self.btn_verify.configure(state="normal")
        self._render()

    def _insert_row(self, item_id: str) -> None:
        row = self.rows[item_id]
        tags = [row["tag"]]
        if row.get("verdict_tag"):
            tags = [row["verdict_tag"]]
        self.tree.insert(
            "",
            "end",
            iid=item_id,
            values=(
                row["site"],
                row["status"],
                row.get("identity") or "—",
                row.get("verdict") or "—",
                row["url_user"] or "—",
                row["http"],
                row["time"],
            ),
            tags=tags,
        )

    def _render(self) -> None:
        keyword = self.ent_filter.get().strip().lower()
        wanted = STATUS_FILTERS.get(self.cmb_status.get(), None)
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        shown = 0
        for item_id, row in self.rows.items():
            if wanted and row["status_key"] != wanted:
                continue
            haystack = f"{row['site']} {row['url_user']}".lower()
            if keyword and keyword not in haystack:
                continue
            self._insert_row(item_id)
            shown += 1
        self.lbl_count.configure(text=f"命中 {len(self.rows)} 个 · 显示 {shown} 条")

    def _finish_user(self, username: str, written: list[Path], errors: list[str], hits: int) -> None:
        detail = f"{username}：命中 {hits} 个站点"
        if written:
            self.last_out_dir = str(written[0].parent)
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
        if self.run_rows:
            try:
                self.shell.hist.add_run(
                    sorted({row["username"] for row in self.run_rows}),
                    self.run_rows,
                    elapsed=elapsed,
                    out_dir=self.last_out_dir,
                )
            except Exception:  # noqa: BLE001
                pass

    def _status(self, text: str) -> None:
        self.lbl_status.configure(text=text)

    # ---------- 状态 ----------
    def refresh(self) -> None:
        self._fill_tree()

    def save_state(self, data: dict) -> None:
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
                "checked_sites": sorted(self.checked),
            }
        )
        for key, var in self.var_formats.items():
            data[f"export_{key}"] = var.get()
