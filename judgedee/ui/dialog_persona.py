"""人物看板：把账号拼成一个人，一屏看完。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..persona import CATEGORY_ORDER
from . import theme


class PersonaDialog(tk.Toplevel):
    def __init__(self, master, persona: dict, px) -> None:
        super().__init__(master)
        self.title("人物看板")
        self.configure(bg=theme.BG)
        self.px = px
        self.persona = persona
        self.transient(master)
        self.geometry(f"{px(940)}x{px(780)}")
        self.minsize(px(760), px(600))

        header = tk.Frame(self, bg=theme.HEADER, height=px(76))
        header.pack(fill="x")
        header.pack_propagate(False)
        box = tk.Frame(header, bg=theme.HEADER)
        box.pack(side="left", padx=px(20))
        tk.Label(
            box,
            text=persona["headline"] or "未命名档案",
            bg=theme.HEADER,
            fg="white",
            font=(theme.FONT, 16, "bold"),
            anchor="w",
        ).pack(anchor="w")
        subtitle = f"人物看板 · 可信度 {persona['confidence']}/100"
        if persona.get("username"):
            subtitle = f"用户名 {persona['username']} · " + subtitle
        if persona.get("redacted"):
            subtitle = "自查模式 · 邮箱/IM/站点已打码 · " + subtitle
        tk.Label(
            box,
            text=subtitle,
            bg=theme.HEADER,
            fg="#9fb0c8",
            font=(theme.FONT, 10),
            anchor="w",
        ).pack(anchor="w")

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(side="bottom", fill="x", padx=px(16), pady=(px(2), px(14)))
        ttk.Button(bar, text="复制摘要", style="Accent.TButton", command=self._copy).pack(side="left")
        ttk.Button(bar, text="关闭", command=self.destroy).pack(side="right")
        self.lbl_copied = ttk.Label(bar, text="", style="Hint.TLabel")
        self.lbl_copied.pack(side="left", padx=px(10))

        body = ttk.Frame(self, style="TFrame", padding=px(16))
        body.pack(fill="both", expand=True)

        # 统计卡
        stats = ttk.Frame(body, style="TFrame")
        stats.pack(fill="x")
        for label, value, hint in (
            ("账号", persona["account_count"], "已注册"),
            ("档案", persona["cluster_count"], f"合并 {persona['multi_count']} 组"),
            ("待确认", persona["review_count"], "证据不足"),
            ("头像", persona["avatar_count"], "不同头像"),
        ):
            card = ttk.Frame(stats, style="Card.TFrame", padding=(px(16), px(10)))
            card.pack(side="left", padx=(0, px(10)))
            ttk.Label(
                card, text=str(value), style="Card.TLabel", font=(theme.FONT, 18, "bold")
            ).pack(anchor="w")
            ttk.Label(
                card, text=f"{label} · {hint}", style="Hint.TLabel"
            ).pack(anchor="w")

        # 摘要
        summary = ttk.Frame(body, style="Card.TFrame", padding=px(12))
        summary.pack(fill="x", pady=(px(10), 0))
        ttk.Label(summary, text="一句话结论", style="Field.TLabel").pack(anchor="w")
        ttk.Label(
            summary,
            text=persona["summary"],
            style="Card.TLabel",
            wraplength=self.px(860),
            justify="left",
        ).pack(anchor="w", pady=(px(4), 0))

        # 类别覆盖
        cover = ttk.Frame(body, style="Card.TFrame", padding=px(12))
        cover.pack(fill="x", pady=(px(10), 0))
        ttk.Label(
            cover,
            text=f"类别覆盖 · 命中 {persona['covered_categories']}/{len(CATEGORY_ORDER)} 类",
            style="Field.TLabel",
        ).pack(anchor="w")
        peak = max([row["count"] for row in persona["coverage"]] + [1])
        for row in persona["coverage"]:
            line = ttk.Frame(cover, style="Card.TFrame")
            line.pack(fill="x", pady=(px(4), 0))
            ttk.Label(line, text=row["label"], style="Card.TLabel", width=4).pack(side="left")
            progress = ttk.Progressbar(
                line, mode="determinate", maximum=peak, value=row["count"], length=self.px(180)
            )
            progress.pack(side="left", padx=px(8))
            detail = "、".join(row["sites"][:6]) + ("…" if len(row["sites"]) > 6 else "")
            ttk.Label(
                line,
                text=f"{row['count']} 个" + (f" · {detail}" if detail else ""),
                style="Hint.TLabel",
            ).pack(side="left")

        # 字段合并
        fields = ttk.Frame(body, style="TFrame")
        fields.pack(fill="x", pady=(px(10), 0))
        for index, (title, items) in enumerate(
            (
                ("昵称", persona["fields"]["names"]),
                ("邮箱", persona["fields"]["emails"]),
                ("即时通讯", persona["fields"]["ims"]),
                ("个人站点", persona["fields"]["domains"]),
            )
        ):
            card = ttk.Frame(fields, style="Card.TFrame", padding=px(10))
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else px(8), 0))
            fields.columnconfigure(index, weight=1, uniform="f")
            ttk.Label(card, text=title, style="Field.TLabel").pack(anchor="w")
            if items:
                for value, count in items[:5]:
                    ttk.Label(
                        card,
                        text=f"{value}（{count} 处）" if count > 1 else value,
                        style="Card.TLabel",
                    ).pack(anchor="w", pady=(px(2), 0))
            else:
                ttk.Label(card, text="—", style="Hint.TLabel").pack(anchor="w")

        # 冲突
        if persona["conflicts"]:
            conflict = ttk.Frame(body, style="Card.TFrame", padding=px(12))
            conflict.pack(fill="x", pady=(px(10), 0))
            ttk.Label(conflict, text="各站说法不一致", style="Field.TLabel").pack(anchor="w")
            for item in persona["conflicts"]:
                ttk.Label(
                    conflict,
                    text=f"{item['field']}：" + " / ".join(item["values"]),
                    style="Card.TLabel",
                    foreground=theme.WARN,
                ).pack(anchor="w", pady=(px(2), 0))

        self.update_idletasks()
        self._center(master)
        self.grab_set()

    def _center(self, master) -> None:
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 4
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.persona["summary"])
            self.lbl_copied.configure(text="已复制到剪贴板")
        except Exception:  # noqa: BLE001
            self.lbl_copied.configure(text="复制失败")
