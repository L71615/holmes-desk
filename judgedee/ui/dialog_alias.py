"""换名同人建议窗口：把「用户名不同但证据很像」的一对列出来，点一下就合并成同一档案。

合并本质上是往 constraints.json 写一条 must-link，所以下次聚类也会记得这个判断。
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .. import i18n
from . import theme


class AliasDialog(tk.Toplevel):
    def __init__(self, master, aliases: list[dict], px, on_merge) -> None:
        super().__init__(master)
        self.title("换名同人建议")
        self.configure(bg=theme.BG)
        self.px = px
        self.aliases = aliases
        self.on_merge = on_merge
        self.transient(master)
        self.geometry(f"{px(1040)}x{px(470)}")
        self.minsize(px(720), px(400))

        header = tk.Frame(self, bg=theme.HEADER, height=px(56))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=i18n.t("换名同人建议"),
            bg=theme.HEADER,
            fg="white",
            font=(theme.FONT, 14, "bold"),
        ).pack(side="left", padx=px(18))
        tk.Label(
            header,
            text=f"{len(aliases)} 组 · 用户名不同但证据分 ≥ 0.45",
            bg=theme.HEADER,
            fg="#9fb0c8",
            font=(theme.FONT, 10),
        ).pack(side="left")

        # 按钮条先 pack 到底部，保证任何窗口高度下都看得见
        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(side="bottom", fill="x", padx=px(14), pady=(px(2), px(14)))
        ttk.Button(bar, text=i18n.t("合并为同一人"), style="Accent.TButton", command=self._merge).pack(
            side="left"
        )
        ttk.Button(bar, text=i18n.t("打开账号 A"), command=lambda: self._open(0)).pack(
            side="left", padx=(px(8), 0)
        )
        ttk.Button(bar, text=i18n.t("打开账号 B"), command=lambda: self._open(1)).pack(
            side="left", padx=(px(8), 0)
        )
        ttk.Button(bar, text=i18n.t("关闭"), command=self.destroy).pack(side="right")

        body = ttk.Frame(self, style="TFrame", padding=px(14))
        body.pack(fill="both", expand=True)

        hint = ttk.Label(
            body,
            text=i18n.t(
                "聚类以「用户名相同」为前提，所以不同名字之间再像也不会被自动并档。"
                "选中一行点「合并为同一人」，会写进 constraints.json 并立即重新聚类。"
            ),
            style="Hint.TLabel",
            wraplength=self.px(840),
            justify="left",
        )
        hint.pack(anchor="w", pady=(0, px(8)))

        card = ttk.Frame(body, style="Card.TFrame", padding=px(8))
        card.pack(fill="both", expand=True)

        columns = ("a", "b", "score", "why")
        self.tree = ttk.Treeview(card, columns=columns, show="headings", height=10)
        for key, text, width, anchor in (
            ("a", "账号 A", 190, "w"),
            ("b", "账号 B", 190, "w"),
            ("score", "证据分", 70, "center"),
            ("why", "理由", 380, "w"),
        ):
            self.tree.heading(key, text=text, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=key == "why")
        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._merge())

        for index, item in enumerate(aliases):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{item['a']} · {item['a_username']}",
                    f"{item['b']} · {item['b_username']}",
                    f"{item['score']:.2f}",
                    "；".join(item.get("notes") or []) or "—",
                ),
            )

        self.update_idletasks()
        self._center(master)
        self.grab_set()

    # ---------- 内部 ----------
    def _center(self, master) -> None:
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:  # noqa: BLE001
            pass

    def _current(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("先选一组", "请先在列表里选中一组建议。", parent=self)
            return None
        try:
            return self.aliases[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def _open(self, which: int) -> None:
        item = self._current()
        if not item:
            return
        url = item["a_url"] if which == 0 else item["b_url"]
        if url:
            webbrowser.open(url)

    def _merge(self) -> None:
        item = self._current()
        if not item:
            return
        name_a = f"{item['a']} · {item['a_username']}"
        name_b = f"{item['b']} · {item['b_username']}"
        if not messagebox.askyesno(
            "合并为同一人",
            f"把下面两个账号当同一个人？\n\n{name_a}\n{name_b}\n\n证据分 {item['score']:.2f}",
            parent=self,
        ):
            return
        self.on_merge(item)
        index = self.tree.selection()[0]
        if self.tree.exists(index):
            self.tree.delete(index)
