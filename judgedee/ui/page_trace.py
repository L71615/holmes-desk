"""追踪页：IP 归属地 + 手机号归属地。

两块都是「填一个值 → 出一张字段表」，结果可双击复制、也可整表复制。
IP 要联网（公开接口），手机号完全离线（phonenumbers 号码库）。
两件事用 Notebook 分开，各自占满整宽，不再并排挤成两条窄表。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import phone_setup, trace
from . import theme

REGION_CHOICES = ("CN", "HK", "TW", "US", "GB", "JP", "SG", "DE", "AU")


class TracePage(ttk.Frame):
    def __init__(self, master, shell) -> None:
        super().__init__(master, style="TFrame")
        self.shell = shell
        self.px = shell.px
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.installing = False
        self.last_maps = ""
        self.last_e164 = ""
        self._build()

    # ---------- 界面 ----------

    def _build(self) -> None:
        px = self.px
        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, padx=px(12), pady=(px(4), px(10)))

        self.nb = ttk.Notebook(body)
        self.nb.pack(fill="both", expand=True)

        ip_tab = ttk.Frame(self.nb, style="Card.TFrame", padding=px(14))
        phone_tab = ttk.Frame(self.nb, style="Card.TFrame", padding=px(14))
        self.nb.add(ip_tab, text="  IP 归属地  ")
        self.nb.add(phone_tab, text="  手机号归属地  ")

        self._build_ip(ip_tab)
        self._build_phone(phone_tab)

    # -- IP --

    def _build_ip(self, tab) -> None:
        px = self.px
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        head = ttk.Frame(tab, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="IP 归属地", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text="IPv4 / IPv6 的国家、城市、经纬度、运营商与机房标记；不记录查询历史。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(px(2), 0))

        row = ttk.Frame(tab, style="Card.TFrame")
        row.grid(row=1, column=0, sticky="ew", pady=(px(12), px(6)))
        row.columnconfigure(0, weight=1)
        self.ent_ip = ttk.Entry(row)
        self.ent_ip.grid(row=0, column=0, sticky="ew", ipady=px(3))
        self.ent_ip.bind("<Return>", lambda _e: self.lookup_ip())
        self.btn_ip = ttk.Button(row, text="查询", style="Accent.TButton", command=self.lookup_ip)
        self.btn_ip.grid(row=0, column=1, padx=(px(8), 0))
        self.btn_my = ttk.Button(row, text="我的 IP", style="Ghost.TButton", command=self.lookup_my_ip)
        self.btn_my.grid(row=0, column=2, padx=(px(6), 0))

        self.lbl_ip = ttk.Label(tab, text="填一个 IP 回车，或点「我的 IP」查自己", style="Hint.TLabel")
        self.lbl_ip.grid(row=2, column=0, sticky="w", pady=(0, px(8)))

        self.tree_ip = self._make_table(tab, row=3)

        actions = ttk.Frame(tab, style="Card.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(px(10), 0))
        ttk.Button(actions, text="复制全部", style="Ghost.TButton", command=self._copy_ip).pack(side="right")
        ttk.Button(actions, text="打开地图", style="Ghost.TButton", command=self._open_map).pack(
            side="right", padx=(0, px(8))
        )

    # -- 手机号 --

    def _build_phone(self, tab) -> None:
        px = self.px
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

        head = ttk.Frame(tab, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="手机号归属地", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text="离线解析：归属地、运营商、时区、号码类型；号码不会发往任何服务器。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(px(2), 0))

        row = ttk.Frame(tab, style="Card.TFrame")
        row.grid(row=1, column=0, sticky="ew", pady=(px(12), px(6)))
        row.columnconfigure(0, weight=1)
        self.ent_phone = ttk.Entry(row)
        self.ent_phone.grid(row=0, column=0, sticky="ew", ipady=px(3))
        self.ent_phone.bind("<Return>", lambda _e: self.parse_phone())
        self.cmb_region = ttk.Combobox(row, values=REGION_CHOICES, width=5, state="readonly")
        self.cmb_region.set(trace.PHONE_DEFAULT_REGION)
        self.cmb_region.grid(row=0, column=1, padx=(px(8), 0))
        self.btn_phone = ttk.Button(row, text="解析", style="Accent.TButton", command=self.parse_phone)
        self.btn_phone.grid(row=0, column=2, padx=(px(6), 0))

        self.lbl_phone = ttk.Label(tab, text="带国家码更准，例如 +86 138 0013 8000", style="Hint.TLabel")
        self.lbl_phone.grid(row=2, column=0, sticky="w", pady=(0, px(8)))

        # 号码库缺失时显示的提示条（默认隐藏）
        self.dep_box = ttk.Frame(tab, style="Card.TFrame")
        self.dep_box.grid(row=3, column=0, sticky="ew", pady=(0, px(8)))
        self.dep_box.columnconfigure(0, weight=1)
        self.lbl_dep = ttk.Label(
            self.dep_box,
            text="",
            style="Hint.TLabel",
            justify="left",
            wraplength=self.px(760),
        )
        self.lbl_dep.grid(row=0, column=0, sticky="w")
        self.btn_dep = ttk.Button(
            self.dep_box, text="一键安装号码库（约 2.5 MB）", style="Accent.TButton", command=self.install_dep
        )
        self.btn_dep.grid(row=1, column=0, sticky="w", pady=(px(8), 0))

        self.tree_phone = self._make_table(tab, row=4)

        actions = ttk.Frame(tab, style="Card.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(px(10), 0))
        ttk.Button(actions, text="复制 E.164", style="Ghost.TButton", command=self._copy_e164).pack(
            side="right"
        )
        ttk.Button(actions, text="复制全部", style="Ghost.TButton", command=self._copy_phone).pack(
            side="right", padx=(0, px(8))
        )

        self._refresh_phone_ready()

    def _refresh_phone_ready(self) -> None:
        ready = phone_setup.available()
        if ready:
            self.dep_box.grid_remove()
            self.btn_phone.configure(state="normal")
        else:
            self.dep_box.grid()
            self.btn_phone.configure(state="disabled")
            self.lbl_dep.configure(
                text=(
                    "手机号解析需要本地号码库 phonenumbers（离线、不联网、约 2.5 MB）。\n"
                    "点下面的按钮装到程序配置目录里，不碰系统 Python，装完立刻能用。"
                )
            )

    def _make_table(self, parent, row: int) -> ttk.Treeview:
        px = self.px
        holder = ttk.Frame(parent, style="Card.TFrame")
        holder.grid(row=row, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        tree = ttk.Treeview(holder, columns=("field", "value"), show="headings")
        tree.heading("field", text="字段", anchor="w")
        tree.heading("value", text="值", anchor="w")
        tree.column("field", width=px(160), anchor="w", stretch=False)
        tree.column("value", width=px(420), anchor="w", stretch=True)
        tree.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=bar.set)
        tree.bind("<Double-1>", lambda _e: self._copy_selected(tree))
        return tree

    # ---------- 依赖安装 ----------

    def install_dep(self) -> None:
        if self.installing:
            return
        self.installing = True
        self.btn_dep.configure(state="disabled", text="安装中…")
        self.lbl_dep.configure(text="正在下载并安装 phonenumbers，稍等十几秒…")

        def runner() -> None:
            ok, message = phone_setup.install()
            self.queue.put(("dep", {"ok": ok, "message": message}))

        threading.Thread(target=runner, daemon=True).start()
        self.after(200, self._pump)

    def _apply_dep(self, payload: dict) -> None:
        self.installing = False
        if payload.get("ok"):
            self.btn_dep.configure(state="normal", text="一键安装号码库（约 2.5 MB）")
            self._refresh_phone_ready()
            self._set_phone_status("号码库已就绪，可以直接解析", bad=False)
            self.shell.status("phonenumbers 安装完成")
            return
        self.btn_dep.configure(state="normal", text="重试安装")
        self.lbl_dep.configure(text=f"安装失败：{payload.get('message')}")
        self.shell.status("号码库安装失败")

    # ---------- IP ----------

    def lookup_ip(self) -> None:
        text = self.ent_ip.get().strip()
        if not text:
            self._set_ip_status("先填一个 IP，或者点「我的 IP」", bad=True)
            return
        self._set_ip_status("查询中…")
        self._fill(self.tree_ip, [])
        self._start(lambda: trace.lookup_ip(text, proxy=self._proxy(), timeout=self._timeout()), "ip")

    def lookup_my_ip(self) -> None:
        self._set_ip_status("查询出口 IP…")
        self._fill(self.tree_ip, [])
        self._start(lambda: self._my_ip_then_lookup(), "ip")

    def _my_ip_then_lookup(self) -> dict:
        found = trace.my_ip(proxy=self._proxy())
        if not found.get("ok"):
            return {"ok": False, "error": f"取本机 IP 失败：{found.get('error')}", "fields": [], "maps": ""}
        ip = found.get("ip") or ""
        result = trace.lookup_ip(ip, proxy=self._proxy(), timeout=self._timeout())
        if result.get("ok"):
            result["fields"] = [("本机出口 IP", ip)] + list(result["fields"])
        return result

    def _start(self, work, kind: str) -> None:
        if self.busy:
            return
        self.busy = True
        self._toggle_buttons(False)

        def runner() -> None:
            try:
                payload = work()
            except Exception as exc:  # noqa: BLE001 - 交给界面显示
                payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "fields": []}
            self.queue.put((kind, payload))

        threading.Thread(target=runner, daemon=True).start()
        self.after(120, self._pump)

    def _pump(self) -> None:
        try:
            kind, payload = self.queue.get_nowait()
        except queue.Empty:
            self.after(120, self._pump)
            return
        if kind == "dep":
            self._apply_dep(payload)
            return
        self.busy = False
        self._toggle_buttons(True)
        if kind == "ip":
            self._apply_ip(payload)

    def _apply_ip(self, payload: dict) -> None:
        if not payload.get("ok"):
            self._set_ip_status(payload.get("error") or "查询失败", bad=True)
            self.shell.status("IP 查询失败")
            return
        self._fill(self.tree_ip, payload.get("fields") or [])
        self.last_maps = payload.get("maps") or ""
        source = payload.get("source") or ""
        self._set_ip_status(f"完成 · 数据源 {source}" if source else "完成")
        self.shell.status("IP 查询完成")

    def _open_map(self) -> None:
        if not self.last_maps:
            self._set_ip_status("先查一个 IP，才有坐标", bad=True)
            return
        webbrowser.open(self.last_maps)

    def _copy_ip(self) -> None:
        self._clipboard(self._rows_text(self.tree_ip))

    # ---------- 手机号 ----------

    def parse_phone(self) -> None:
        if not phone_setup.available():
            self._refresh_phone_ready()
            self._set_phone_status("先安装号码库（下面那个按钮）", bad=True)
            return
        text = self.ent_phone.get().strip()
        if not text:
            self._set_phone_status("先填一个号码，例如 +86 138 0013 8000", bad=True)
            return
        result = trace.parse_phone(text, region=self.cmb_region.get() or trace.PHONE_DEFAULT_REGION)
        if not result.get("ok"):
            self._fill(self.tree_phone, [])
            self._set_phone_status(result.get("error") or "解析失败", bad=True)
            self.shell.status("号码解析失败")
            return
        self._fill(self.tree_phone, result.get("fields") or [])
        self.last_e164 = result.get("e164") or ""
        where = result.get("location") or "—"
        operator = result.get("operator") or "—"
        self._set_phone_status(f"完成 · {where} · {operator}")
        self.shell.status("号码解析完成")

    def _copy_phone(self) -> None:
        self._clipboard(self._rows_text(self.tree_phone))

    def _copy_e164(self) -> None:
        if not self.last_e164:
            self._set_phone_status("先解析一个号码", bad=True)
            return
        self._clipboard(self.last_e164)

    # ---------- 公共 ----------

    def _proxy(self) -> str:
        return (self.shell.cfg.get("proxy") or "").strip()

    def _timeout(self) -> float:
        try:
            return float(self.shell.cfg.get("timeout") or trace.DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            return trace.DEFAULT_TIMEOUT

    def _toggle_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.btn_ip, self.btn_my):
            button.configure(state=state)

    def _fill(self, tree: ttk.Treeview, rows) -> None:
        tree.delete(*tree.get_children())
        for field, value in rows:
            tree.insert("", "end", values=(field, value))

    def _rows_text(self, tree: ttk.Treeview) -> str:
        lines = []
        for item in tree.get_children():
            field, value = tree.item(item, "values")
            lines.append(f"{field}: {value}")
        return "\n".join(lines)

    def _copy_selected(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            return
        _field, value = tree.item(selection[0], "values")
        self._clipboard(str(value))

    def _clipboard(self, text: str) -> None:
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.shell.status("已复制到剪贴板")

    def _set_ip_status(self, text: str, bad: bool = False) -> None:
        self.lbl_ip.configure(text=text, foreground=theme.BAD if bad else theme.MUTED)

    def _set_phone_status(self, text: str, bad: bool = False) -> None:
        self.lbl_phone.configure(text=text, foreground=theme.BAD if bad else theme.MUTED)
