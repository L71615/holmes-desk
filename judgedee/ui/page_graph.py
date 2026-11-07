"""图谱页：把档案画成可拖动的节点网络，并在这里做人工纠错。

交互：
- 拖动节点：按住拖，松手后位置固定（下次重新布局会还原）
- 滚轮：缩放；右键拖动：平移
- 点节点：右侧显示它的画像与证据
- 选中两个节点后可以「合并（同一人）」或「标记不同人」，写进 constraints.json
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from .. import i18n
from ..graph import (
    ANCHOR_REVIEW,
    ANCHOR_STRONG,
    Edge,
    account_key,
    anchor_layout,
    build_edges,
    cluster_layout,
    degrees,
    layout,
    node_radius,
)
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
        self.anchor_mode = False
        self.anchor: dict = {}
        self.focus_key: str | None = None
        self._avatar_cache: dict[str, object] = {}
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
            bar, text=i18n.t("重新布局"), style="Accent.TButton", command=self.relayout
        )
        self.btn_layout.pack(side="left")
        self.btn_strong = ttk.Button(
            bar, text=i18n.t("只看强证据"), style="Ghost.TButton", command=self.toggle_strong
        )
        self.btn_strong.pack(side="left", padx=px(8))
        self.btn_weak = ttk.Button(
            bar, text=i18n.t("隐藏弱证据"), style="Ghost.TButton", command=self.toggle_weak
        )
        self.btn_weak.pack(side="left", padx=(0, px(8)))
        self.btn_merge = ttk.Button(
            bar, text=i18n.t("合并为同一人"), style="Ghost.TButton", command=self.mark_same, state="disabled"
        )
        self.btn_merge.pack(side="left", padx=(0, px(8)))
        self.btn_split = ttk.Button(
            bar, text=i18n.t("标记为不同人"), style="Ghost.TButton", command=self.mark_different, state="disabled"
        )
        self.btn_split.pack(side="left", padx=(0, px(8)))
        self.btn_clear = ttk.Button(
            bar, text=i18n.t("清除该对约束"), style="Ghost.TButton", command=self.clear_selection_constraint
        )
        self.btn_clear.pack(side="left")

        self.btn_anchor = ttk.Button(
            bar, text=i18n.t("锚定视图"), style="Ghost.TButton", command=self.toggle_anchor
        )
        self.btn_anchor.pack(side="left", padx=(px(8), 0))
        self.btn_png = ttk.Button(
            bar, text=i18n.t("导出图片"), style="Ghost.TButton", command=self.export_image
        )
        self.btn_png.pack(side="left", padx=(px(8), 0))

        hint_row = ttk.Frame(self, style="TFrame")
        hint_row.pack(fill="x", pady=(0, px(6)))
        self.lbl_hint = ttk.Label(
            hint_row,
            text=i18n.t("底色＝同一档案 · 圈大＝证据强 · 深蓝实线＝强证据"),
            style="Hint.TLabel",
        )
        self.lbl_hint.pack(side="left")

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
        ttk.Label(side, text=i18n.t("选中节点"), style="Card.TLabel", font=(theme.FONT, 10, "bold")).pack(
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
        self.anchor = dict(getattr(self.shell, "anchor", {}) or {})
        if self.anchor and not self.anchor_mode:
            # 刚跑完基准扫描，直接切到锚定视图更有用
            self.anchor_mode = True
        self._sync_anchor_button()
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
        seed_key = str(self.anchor.get("seed") or "")
        raw: dict[str, tuple[float, float]] = {}
        if self.anchor_mode and seed_key in keys:
            # 锚定视图：种子固定在中心，候选按证据强度分三圈
            raw = anchor_layout(
                keys, seed_key, dict(self.anchor.get("scores") or {}), width=width, height=height
            )
        if not raw:
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

        if self.anchor_mode and seed_key in keys:
            # 锚定视图里颜色表示「证据等级」，比按档案上色更好读
            scores = dict(self.anchor.get("scores") or {})
            for key in keys:
                if key == seed_key:
                    self.color[key] = theme.ACCENT
                    continue
                score = float(scores.get(key, 0.0))
                if score >= ANCHOR_STRONG:
                    self.color[key] = theme.OK
                elif score >= ANCHOR_REVIEW:
                    self.color[key] = theme.WARN
                else:
                    self.color[key] = theme.GRAY

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

        # 锚定视图：先画三条参考圈，把「证据多硬」标出来
        if self.anchor_mode and str(self.anchor.get("seed") or "") in self.pos:
            cx, cy = to_screen((0.5, 0.5))
            base = min(width - 2 * margin_x, height - 2 * margin_y)
            for index, (radius_ratio, label) in enumerate((
                (0.18, "0.62+"),
                (0.30, "0.45–0.62"),
                (0.42, "<0.45"),
            )):
                r = base * radius_ratio * zoom
                canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    outline="#c9d3e3", dash=(4, 5), width=1,
                )
                # 三条圈各挑一个不同角度标数字，短文本 + 分开摆，不会互相压住
                angle = math.radians(196 + index * 34)
                canvas.create_text(
                    cx + r * math.cos(angle), cy + r * math.sin(angle),
                    text=label,
                    fill=theme.MUTED, font=(theme.FONT, 9, "bold"),
                )

        # 先铺档案底色：同一档案的点被一块浅色圆托住，一眼看出「几团人」
        # （锚定视图里已经用同心圈表达距离，再叠底色会糊成一片，所以跳过）
        for index, cluster in enumerate(self.clusters):
            if self.anchor_mode:
                break
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

        seed_key = str(self.anchor.get("seed") or "") if self.anchor_mode else ""
        focus = self.focus_key
        neighbours: set[str] = set()
        if focus:
            neighbours.add(focus)
            for edge in self.edges:
                if edge.a == focus:
                    neighbours.add(edge.b)
                elif edge.b == focus:
                    neighbours.add(edge.a)
        placed: list[tuple[float, float]] = []
        for account in self.accounts:
            key = account_key(account)
            if key not in self.pos:
                continue
            x, y = to_screen(self.pos[key])
            is_seed = key == seed_key
            r = max(6.0, self.radius.get(key, self.px(14)) * zoom)
            if is_seed:
                r = max(r, self.px(17))
            selected = key in self.selected
            base_color = self.color.get(key, theme.ACCENT)
            # 点了某个节点后，和它没关系的点淡下去，只看这一串
            muted = bool(focus) and key not in neighbours
            fill = _tint(base_color, 0.30) if muted else base_color
            canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=fill,
                outline=theme.INK if (selected or is_seed or key == focus) else "white",
                width=3 if (selected or is_seed or key == focus) else 1,
                tags=("node", f"n:{key}"),
            )
            self._draw_avatar(canvas, account, x, y, r * 0.78, muted)

            label = account.site if len(account.site) <= 18 else account.site[:17] + "…"
            if is_seed:
                label = f"{i18n.t('种子')} · {label}"
            # 标签避让：和已画过的标签靠太近就往下错一行，避免糊在一起
            label_y = y + r + self.px(8) * zoom
            for px_, py_ in placed:
                if abs(px_ - x) < self.px(56) and abs(py_ - label_y) < self.px(22):
                    label_y = py_ + self.px(17)
            placed.append((x, label_y))
            canvas.create_text(
                x, label_y,
                text=label,
                fill=theme.MUTED if muted else theme.INK,
                font=(theme.FONT, 9, "bold" if is_seed else "normal"),
                tags=("node", f"n:{key}"),
            )
            canvas.create_text(
                x, label_y + self.px(12),
                text=account.username[:24],
                fill="#93a1b5" if muted else theme.MUTED,
                font=(theme.FONT, 8),
                tags=("node", f"n:{key}"),
            )

        self._draw_legend(width)

    def _draw_avatar(self, canvas, account, x: float, y: float, radius: float, muted: bool) -> None:
        """有头像就把缩略图塞进节点里，没有就用首字母。"""
        key = account_key(account)
        size = max(8, int(radius * 2))
        photo = self._avatar_cache.get(key)
        if photo is None and account.avatar_path:
            photo = self._load_avatar(account.avatar_path, size)
            self._avatar_cache[key] = photo
        if photo is not None:
            canvas.create_image(x, y, image=photo, tags=("node", f"n:{key}"))
            return
        initial = (account.display_name or account.username or "?")[:1].upper()
        canvas.create_text(
            x, y, text=initial, fill="white",
            font=(theme.FONT, max(7, int(size / 3)), "bold"),
            tags=("node", f"n:{key}"),
        )

    def _load_avatar(self, path: str, size: int):
        try:
            from PIL import Image, ImageTk  # 头像比对本身就是可选依赖
        except Exception:  # noqa: BLE001
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image = image.resize((size, size))
            # 圆形遮罩：把四角切掉，看起来像头像而不是小方块
            mask = Image.new("L", (size, size), 0)
            from PIL import ImageDraw

            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            image.putalpha(mask)
            return ImageTk.PhotoImage(image, master=self.canvas)
        except Exception:  # noqa: BLE001
            return None

    def _draw_legend(self, width: float) -> None:
        """左下角放一行图例：颜色到底代表什么。"""
        if not self.anchor_mode:
            return
        canvas = self.canvas
        items = [
            (theme.ACCENT, i18n.t("种子")),
            (theme.OK, i18n.t("强 0.62+")),
            (theme.WARN, i18n.t("待确认 0.45–0.62")),
            (theme.GRAY, i18n.t("弱 <0.45")),
        ]
        x = self.px(12)
        y = self.px(12)
        try:
            from tkinter import font as tkfont

            measure = tkfont.Font(family=theme.FONT, size=9)
        except Exception:  # noqa: BLE001
            measure = None
        for color, text in items:
            canvas.create_oval(
                x, y - self.px(5), x + self.px(10), y + self.px(5),
                fill=color, outline="",
            )
            canvas.create_text(
                x + self.px(15), y, text=text, anchor="w",
                fill=theme.MUTED, font=(theme.FONT, 9),
            )
            advance = (measure.measure(text) if measure else len(text) * self.px(7)) + self.px(26)
            x += advance

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
                self.focus_key = None
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
            # 单击＝聚焦这一串：其余节点淡下去，双击仍然打开主页
            self.focus_key = None if self.focus_key == key else key
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
        self.btn_strong.configure(text=i18n.t("显示全部证据") if self.strong_only else "只看强证据")
        self.refresh()

    def export_image(self) -> None:
        """把画布这一块截下来存成 PNG，方便贴到报告或聊天里。"""
        if not self.accounts:
            self._write(i18n.t("还没有图可以导出。"))
            return
        try:
            from PIL import ImageGrab
        except Exception:  # noqa: BLE001
            self._write(i18n.t("导出图片需要 Pillow，先装一下：pip install pillow"))
            return
        self.canvas.update_idletasks()
        x = self.canvas.winfo_rootx()
        y = self.canvas.winfo_rooty()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 40 or h < 40:
            self._write(i18n.t("图谱还没显示出来，等窗口画好再点一次。"))
            return
        out_dir = Path(getattr(self.shell.cfg, "get", lambda *_: None)("out_dir") or "results")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / time.strftime("%Y%m%d-%H%M%S-graph.png")
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(target)
        except OSError as exc:
            self._write(f"{i18n.t('导出失败')}：{exc}")
            return
        self.shell.status(f"{i18n.t('图谱已导出')}：{target}")

    def toggle_weak(self) -> None:
        self.show_weak = not self.show_weak
        self.btn_weak.configure(text=i18n.t("显示弱证据") if not self.show_weak else "隐藏弱证据")
        self._draw()

    def _sync_anchor_button(self) -> None:
        if not hasattr(self, "btn_anchor"):
            return
        self.btn_anchor.configure(
            text=i18n.t("普通视图") if self.anchor_mode else i18n.t("锚定视图")
        )

    def toggle_anchor(self) -> None:
        """在「按档案分组」和「以基准账号为中心」两种摆法之间切换。"""
        seed_key = str(self.anchor.get("seed") or "")
        if not seed_key:
            self._write(
                i18n.t("还没有基准账号。先回「检索」页，在「基准账号」里填一个你确定的账号，再点「基准扫描」。")
            )
            return
        self.anchor_mode = not self.anchor_mode
        self._sync_anchor_button()
        self.relayout()

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
