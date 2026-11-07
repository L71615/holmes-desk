"""图谱页：把档案画成可拖动的节点网络，并在这里做人工纠错。

交互：
- 拖动节点：按住拖，松手后位置固定（下次重新布局会还原）
- 滚轮：缩放；右键拖动：平移
- 点节点：右侧显示它的画像与证据
- 选中两个节点后可以「合并（同一人）」或「标记不同人」，写进 constraints.json
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from ..graph import Edge, account_key, build_edges, cluster_layout, degrees, layout, node_radius
from ..identity import REVIEW_THRESHOLD, Account, Cluster, score_pair
from . import theme


def _tint(color: str, factor: float) -> str:
    """把调色板颜色往白色方向调，factor 越小越淡（0=白，1=原色）。"""
    color = color.lstrip("#")
    if len(color) != 6:
        return "#eef1f6"
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    out = []
    for value in (r, g, b):
        mixed = int(round(255 - (255 - value) * factor))
        out.append(max(0, min(255, mixed)))
    return "#%02x%02x%02x" % tuple(out)

PALETTE = [
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#9333ea",
    "#0891b2",
    "#dc2626",
    "#65a30d",
    "#db2777",
    "#4f46e5",
    "#0d9488",
    "#b45309",
    "#7c3aed",
]


class GraphPage(ttk.Frame):
    def __init__(self, master, shell) -> None:
        super().__init__(master, style="TFrame", padding=(0, 0, 0, 0))
        self.shell = shell
        self.px = shell.px
        self.accounts: list[Account] = []
        self.clusters: list[Cluster] = []
        self.edges: list[Edge] = []
        self.pos: dict[str, tuple[float, float]] = {}
        self.radius: dict[str, float] = {}
        self.color: dict[str, str] = {}
        self.selected: list[str] = []
        self.strong_only = False
        self.show_weak = True
        self.cluster_of: dict[str, Cluster] = {}
        self.zoom = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self.drag_key: str | None = None
        self.drag_start = (0.0, 0.0)
        self._build()

    # ---------- 界面 ----------
    def _build(self) -> None:
        px = self.px
        bar = ttk.Frame(self, style="TFrame")
        bar.pack(fill="x", pady=(0, px(8)))

        self.btn_layout = ttk.Button(
            bar, text="重新布局", style="Accent.TButton", command=self.relayout
        )
        self.btn_layout.pack(side="left")
        self.btn_strong = ttk.Button(
            bar, text="只看强证据", style="Ghost.TButton", command=self.toggle_strong
        )
        self.btn_strong.pack(side="left", padx=px(8))
        self.btn_weak = ttk.Button(
            bar, text="隐藏弱证据", style="Ghost.TButton", command=self.toggle_weak
        )
        self.btn_weak.pack(side="left", padx=(0, px(8)))
        self.btn_merge = ttk.Button(
            bar, text="合并为同一人", style="Ghost.TButton", command=self.mark_same, state="disabled"
        )
        self.btn_merge.pack(side="left", padx=(0, px(8)))
        self.btn_split = ttk.Button(
            bar, text="标记为不同人", style="Ghost.TButton", command=self.mark_different, state="disabled"
        )
        self.btn_split.pack(side="left", padx=(0, px(8)))
        self.btn_clear = ttk.Button(
            bar, text="清除该对约束", style="Ghost.TButton", command=self.clear_selection_constraint
        )
        self.btn_clear.pack(side="left")

        self.lbl_hint = ttk.Label(
            bar,
            text="底色＝同一档案 · 圈大＝证据强 · 深蓝实线＝强证据",
            style="Hint.TLabel",
        )
        self.lbl_hint.pack(side="right")

        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)

        card = ttk.Frame(body, style="Card.TFrame", padding=px(6))
        card.grid(row=0, column=0, sticky="nsew", padx=(0, px(10)))
        self.canvas = tk.Canvas(
            card, background=theme.CARD, highlightthickness=0, bd=0, cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._on_resize())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-1>", self._on_double)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-3>", self._on_pan_start)
        self.canvas.bind("<B3-Motion>", self._on_pan)

        side = ttk.Frame(body, style="Card.TFrame", padding=px(10), width=px(300))
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_propagate(False)
        ttk.Label(side, text="选中节点", style="Card.TLabel", font=(theme.FONT, 10, "bold")).pack(
            anchor="w"
        )
        self.txt = tk.Text(
            side,
            wrap="word",
            bg=theme.CARD,
            fg=theme.INK,
            relief="flat",
            font=(theme.FONT, 9),
            height=26,
            padx=px(4),
            pady=px(4),
        )
        self.txt.pack(fill="both", expand=True, pady=(px(6), 0))
        self.txt.configure(state="disabled")

    # ---------- 数据 ----------
    def refresh(self) -> None:
        state = getattr(self.shell, "identity", {})
        self.accounts = list(state.get("accounts") or [])
        self.clusters = list(state.get("clusters") or [])
        if not self.accounts:
            self.canvas.delete("all")
            self._write("还没有做身份分析。\n\n先去「检索」页跑一次检索，再点「身份分析」，\n这里就会出现账号之间的关系图。")
            return
        self.edges = build_edges(self.accounts, strong_only=self.strong_only)
        self.relayout()
        self._update_selected_text()

    def relayout(self) -> None:
        if not self.accounts:
            return
        width = 1000.0
        height = 700.0
        keys = [account_key(account) for account in self.accounts]
        # 分簇环形布局：每个档案自成一组，不再让力导向把它们挤成一坨
        raw = cluster_layout(self.clusters, width=width, height=height)
        if not raw:
            raw = layout(keys, self.edges, width=width, height=height)
        self.pos = {key: (raw[key][0] / width, raw[key][1] / height) for key in keys if key in raw}
        degree = degrees(keys, self.edges)
        max_degree = max(degree.values()) if degree else 0.0
        _ = max_degree  # 度数不再决定大小，保留统计以便后续扩展

        self.cluster_of = {}
        for cluster in self.clusters:
            for account in cluster.accounts:
                self.cluster_of[account_key(account)] = cluster

        base = self.px(9)
        span = self.px(11)
        self.radius = {}
        for key in keys:
            cluster = self.cluster_of.get(key)
            if cluster is None:
                self.radius[key] = base
                continue
            conf = 0.0
            try:
                conf = max(0.0, min(1.0, float(getattr(cluster, "score", 0.0) or 0.0)))
            except (TypeError, ValueError):
                conf = 0.0
            if len(cluster.accounts) == 1:
                conf = min(conf, 0.5)
            self.radius[key] = base + span * conf
        self.color = {}
        for index, cluster in enumerate(self.clusters):
            for account in cluster.accounts:
                self.color[account_key(account)] = PALETTE[index % len(PALETTE)]
        self._draw()

    def _draw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        if not self.accounts:
            return
        zoom = self.zoom
        ox, oy = self.ox, self.oy
        width = max(canvas.winfo_width(), 240)
        height = max(canvas.winfo_height(), 200)
        margin_x = width * 0.08
        margin_y = height * 0.10

        def to_screen(point: tuple[float, float]) -> tuple[float, float]:
            x = margin_x + point[0] * (width - 2 * margin_x)
            y = margin_y + point[1] * (height - 2 * margin_y)
            return x * zoom + ox, y * zoom + oy

        # 先铺档案底色：同一档案的点被一块浅色圆托住，一眼看出「几团人」
        for index, cluster in enumerate(self.clusters):
            points = [
                to_screen(self.pos[account_key(account)])
                for account in cluster.accounts
                if account_key(account) in self.pos
            ]
            if not points:
                continue
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            spread = max((((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 for p in points), default=0.0)
            radius = spread + max(
                (self.radius.get(account_key(a), self.px(9)) for a in cluster.accounts), default=0.0
            ) * zoom + self.px(20) * zoom
            tint = _tint(PALETTE[index % len(PALETTE)], 0.16)
            canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                fill=tint,
                outline=_tint(PALETTE[index % len(PALETTE)], 0.28),
                width=1,
            )
            canvas.create_text(
                cx,
                cy - radius - self.px(8) * zoom,
                text=f"档案 {cluster.label} · {len(cluster.accounts)} 个账号",
                fill=_tint(PALETTE[index % len(PALETTE)], 0.85),
                font=(theme.FONT, 9, "bold"),
            )

        for edge in self.edges:
            if edge.a not in self.pos or edge.b not in self.pos:
                continue
            if not self.show_weak and not edge.strong and edge.score < REVIEW_THRESHOLD:
                continue
            x1, y1 = to_screen(self.pos[edge.a])
            x2, y2 = to_screen(self.pos[edge.b])
            if edge.strong:
                canvas.create_line(
                    x1, y1, x2, y2, fill=theme.ACCENT, width=max(1, int(2.4 * zoom)), smooth=True
                )
            elif edge.score >= REVIEW_THRESHOLD:
                canvas.create_line(
                    x1, y1, x2, y2, fill="#8fa0b8", width=max(1, int(1.5 * zoom)), smooth=True
                )
            else:
                canvas.create_line(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill="#b7c2d4",
                    width=max(1, int(1.2 * zoom)),
                    dash=(3, 4),
                )

        for account in self.accounts:
            key = account_key(account)
            if key not in self.pos:
                continue
            x, y = to_screen(self.pos[key])
            r = max(6.0, self.radius.get(key, self.px(14)) * zoom)
            selected = key in self.selected
            canvas.create_oval(
                x - r,
                y - r,
                x + r,
                y + r,
                fill=self.color.get(key, theme.ACCENT),
                outline=theme.INK if selected else "white",
                width=3 if selected else 1,
            )
            canvas.create_text(
                x,
                y + r + self.px(9) * zoom,
                text=account.site[:22],
                fill=theme.INK,
                font=(theme.FONT, 9),
            )

    def _screen_of(self, point: tuple[float, float]) -> tuple[float, float]:
        width = max(self.canvas.winfo_width(), 240)
        height = max(self.canvas.winfo_height(), 200)
        margin_x = width * 0.08
        margin_y = height * 0.10
        x = margin_x + point[0] * (width - 2 * margin_x)
        y = margin_y + point[1] * (height - 2 * margin_y)
        return x * self.zoom + self.ox, y * self.zoom + self.oy

    def _hit(self, x: float, y: float) -> str | None:
        for key, point in self.pos.items():
            sx, sy = self._screen_of(point)
            r = self.radius.get(key, self.px(14)) * self.zoom
            if (x - sx) ** 2 + (y - sy) ** 2 <= (r + 4) ** 2:
                return key
        return None

    # ---------- 交互 ----------
    def _on_press(self, event) -> None:
        key = self._hit(event.x, event.y)
        ctrl = bool(event.state & 0x0004)
        if key is None:
            if not ctrl:
                self.selected = []
                self._draw()
                self._update_selected_text()
            return
        if ctrl:
            if key in self.selected:
                self.selected.remove(key)
            else:
                self.selected.append(key)
        else:
            if key not in self.selected:
                self.selected = [key]
        self.drag_key = key
        self.drag_start = (event.x, event.y)
        self._draw()
        self._update_selected_text()

    def _on_drag(self, event) -> None:
        if not self.drag_key or self.drag_key not in self.pos:
            return
        width = max(self.canvas.winfo_width(), 240)
        height = max(self.canvas.winfo_height(), 200)
        span_x = max(width * 0.84, 1.0)
        span_y = max(height * 0.80, 1.0)
        dx = (event.x - self.drag_start[0]) / self.zoom / span_x
        dy = (event.y - self.drag_start[1]) / self.zoom / span_y
        x, y = self.pos[self.drag_key]
        self.pos[self.drag_key] = (x + dx, y + dy)
        self.drag_start = (event.x, event.y)
        self._draw()

    def _on_release(self, _event) -> None:
        self.drag_key = None
        self._update_buttons()

    def _on_double(self, event) -> None:
        key = self._hit(event.x, event.y)
        if not key:
            return
        for account in self.accounts:
            if account_key(account) == key and account.url:
                webbrowser.open(account.url)
                return

    def _on_wheel(self, event) -> None:
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        new_zoom = min(3.0, max(0.4, self.zoom * factor))
        if new_zoom == self.zoom:
            return
        # 以鼠标位置为锚点缩放
        cx = (event.x - self.ox) / self.zoom
        cy = (event.y - self.oy) / self.zoom
        self.zoom = new_zoom
        self.ox = event.x - cx * self.zoom
        self.oy = event.y - cy * self.zoom
        self._draw()

    def _on_pan_start(self, event) -> None:
        self._pan = (event.x, event.y)

    def _on_pan(self, event) -> None:
        if not hasattr(self, "_pan"):
            return
        dx = event.x - self._pan[0]
        dy = event.y - self._pan[1]
        self.ox += dx
        self.oy += dy
        self._pan = (event.x, event.y)
        self._draw()

    def _on_resize(self) -> None:
        if self.accounts and self.pos:
            self._draw()

    def toggle_strong(self) -> None:
        self.strong_only = not self.strong_only
        self.btn_strong.configure(text="显示全部证据" if self.strong_only else "只看强证据")
        self.refresh()

    def toggle_weak(self) -> None:
        self.show_weak = not self.show_weak
        self.btn_weak.configure(text="显示弱证据" if not self.show_weak else "隐藏弱证据")
        self._draw()

    # ---------- 纠错 ----------
    def _update_buttons(self) -> None:
        state = "normal" if len(self.selected) == 2 else "disabled"
        self.btn_merge.configure(state=state)
        self.btn_split.configure(state=state)

    def _update_selected_text(self) -> None:
        self._update_buttons()
        if not self.selected:
            lines = ["没有选中节点。", "", f"账号 {len(self.accounts)} 个 · 有证据的连线 {len(self.edges)} 条"]
            constraints = getattr(self.shell, "constraints", None)
            if constraints is not None and len(constraints):
                lines += ["", "已记录的人工判断："]
                lines += ["  " + item for item in constraints.describe()[:12]]
            self._write("\n".join(lines))
            return

        lines: list[str] = []
        for key in self.selected:
            account = next((a for a in self.accounts if account_key(a) == key), None)
            if not account:
                continue
            cluster_label = next(
                (c.label for c in self.clusters if any(account_key(a) == key for a in c.accounts)), "?"
            )
            lines.append(f"{account.site} · 档案 {cluster_label}")
            lines.append(f"  用户名：{account.username}")
            lines.append(f"  昵称：{account.title}")
            lines.append(f"  简介：{account.bio or '（无）'}")
            lines.append(f"  链接：{account.url}")
            lines.append("")

        if len(self.selected) == 2:
            left = next((a for a in self.accounts if account_key(a) == self.selected[0]), None)
            right = next((a for a in self.accounts if account_key(a) == self.selected[1]), None)
            if left and right:
                pair = score_pair(left, right)
                lines.append(f"这两个账号的综合分：{pair.score:.2f}" + ("（强证据）" if pair.strong else ""))
                for note in pair.notes or ["（没有可解释的证据）"]:
                    lines.append(f"  · {note}")
        self._write("\n".join(lines))

    def _write(self, text: str) -> None:
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.configure(state="disabled")

    def _selected_pair(self) -> tuple[str, str] | None:
        if len(self.selected) != 2:
            return None
        return self.selected[0], self.selected[1]

    def mark_same(self) -> None:
        pair = self._selected_pair()
        if not pair:
            return
        self.shell.constraints.add_must(*pair)
        self._recluster()

    def mark_different(self) -> None:
        pair = self._selected_pair()
        if not pair:
            return
        self.shell.constraints.add_cannot(*pair)
        self._recluster()

    def clear_selection_constraint(self) -> None:
        pair = self._selected_pair()
        if not pair:
            messagebox.showinfo("先选中两个节点", "按住 Ctrl 点两个节点，再清除它们之间的约束。")
            return
        self.shell.constraints.remove(*pair)
        self._recluster()

    def _recluster(self) -> None:
        from ..identity import cluster_accounts

        accounts = self.accounts
        if not accounts:
            return
        clusters, review = cluster_accounts(
            accounts,
            must=self.shell.constraints.must,
            cannot=self.shell.constraints.cannot,
        )
        self.clusters = clusters
        self.shell.identity["clusters"] = clusters
        self.shell.identity["review"] = review
        self.edges = build_edges(accounts, strong_only=self.strong_only)
        self.relayout()
        self._update_selected_text()
        self.shell.status(f"已按人工判断重新聚类 · {len(clusters)} 个档案")
