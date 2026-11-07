"""两次检索的对比窗口：这次多了哪些账号、少了哪些、哪些一直都在。"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import i18n
from ..history import STATUS_TEXT
from . import theme

KIND_TEXT = {"added": "新增", "removed": "消失", "kept": "仍在"}


class CompareDialog(tk.Toplevel):
    def __init__(self, master, diff: dict, px) -> None:
        super().__init__(master)
        self.title("两次检索对比")
        self.configure(bg=theme.BG)
        self.px = px
        self.diff = diff
        self.transient(master)
        self.geometry(f"{px(920)}x{px(560)}")
        self.minsize(px(720), px(420))

        left = diff["left"]
        right = diff["right"]

        header = tk.Frame(self, bg=theme.HEADER, height=px(64))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=i18n.t("两次检索对比"),
            bg=theme.HEADER,
            fg="white",
            font=(theme.FONT, 14, "bold"),
        ).pack(side="left", padx=px(18))
        tk.Label(
            header,
            text=f"本次 #{left['id']} {left['created_at']}　←　基线 #{right['id']} {right['created_at']}",
            bg=theme.HEADER,
            fg="#9fb0c8",
            font=(theme.FONT, 10),
        ).pack(side="left")

        body = ttk.Frame(self, style="TFrame", padding=px(14))
        body.pack(fill="both", expand=True)

        added, removed, kept = diff["added"], diff["removed"], diff["kept"]
        stats = ttk.Frame(body, style="TFrame")
        stats.pack(fill="x", pady=(0, px(8)))
        for label, value, color in (
            ("新增", len(added), theme.OK),
            ("消失", len(removed), theme.BAD),
            ("仍在", len(kept), theme.MUTED),
        ):
            chip = ttk.Frame(stats, style="Card.TFrame", padding=(px(14), px(8)))
            chip.pack(side="left", padx=(0, px(10)))
            ttk.Label(
                chip,
                text=f"{value}  {label}",
                style="Card.TLabel",
                foreground=color,
                font=(theme.FONT, 11, "bold"),
            ).pack()

        hint = ttk.Label(
            body,
            text=f"对比的是「已注册」账号：本次 {left['hits']} 个命中，基线 {right['hits']} 个命中。"
            "双击一行打开主页。",
            style="Hint.TLabel",
        )
        hint.pack(anchor="w", pady=(0, px(8)))

        bar = ttk.Frame(body, style="TFrame")
        bar.pack(side="bottom", fill="x", pady=(px(10), 0))
        ttk.Button(bar, text=i18n.t("打开链接"), style="Ghost.TButton", command=self._open).pack(side="left")
        ttk.Button(bar, text=i18n.t("关闭"), command=self.destroy).pack(side="right")

        card = ttk.Frame(body, style="Card.TFrame", padding=px(8))
        card.pack(fill="both", expand=True)

        columns = (
            ("kind", "变化", 70, "center"),
            ("user", "用户名", 150, "w"),
            ("site", "站点", 200, "w"),
            ("status", "状态", 90, "w"),
            ("url", "链接", 360, "w"),
        )
        self.tree = ttk.Treeview(card, columns=[c[0] for c in columns], show="headings", height=14)
        for key, label, width, anchor in columns:
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=key == "url")
        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("added", foreground=theme.OK)
        self.tree.tag_configure("removed", foreground=theme.BAD)
        self.tree.tag_configure("kept", foreground=theme.MUTED)

        index = 0
        for kind, items in (("added", added), ("removed", removed), ("kept", kept)):
            for row in items:
                status = STATUS_TEXT.get(str(row.get("status") or ""), "")
                self.tree.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(
                        KIND_TEXT[kind],
                        row.get("username") or "",
                        row.get("site") or "",
                        status,
                        row.get("url") or "—",
                    ),
                    tags=(kind,),
                )
                index += 1

        self.tree.bind("<Double-1>", self._open)

        self.update_idletasks()
        self._center(master)
        self.grab_set()

    def _center(self, master) -> None:
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass

    def _open(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        url = self.tree.item(selection[0], "values")[4]
        if url and str(url).startswith("http"):
            webbrowser.open(str(url))
