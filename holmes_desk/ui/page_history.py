"""历史页：每次检索都记一笔，点开能看当时的命中。"""

from __future__ import annotations

from pathlib import Path
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from ..history import STATUS_TEXT
from ..platform_win import open_path
from . import theme
from .dialog_compare import CompareDialog


class HistoryPage(ttk.Frame):
    def __init__(self, master: tk.Misc, shell) -> None:
        super().__init__(master, style="TFrame")
        self.shell = shell
        self.px = shell.px
        self._build()
        self.refresh()

    def _build(self) -> None:
        px = self.px

        actions = ttk.Frame(self, style="TFrame")
        actions.pack(fill="x", pady=(0, px(8)))
        ttk.Button(actions, text="刷新", style="Ghost.TButton", command=self.refresh).pack(side="left")
        ttk.Button(actions, text="删除选中", style="Danger.TButton", command=self._delete).pack(
            side="left", padx=px(8)
        )
        ttk.Button(actions, text="清空历史", style="Ghost.TButton", command=self._clear).pack(side="left")
        ttk.Button(actions, text="和上一次对比", style="Ghost.TButton", command=self._compare).pack(
            side="left", padx=(px(8), 0)
        )
        ttk.Button(actions, text="打开结果目录", style="Ghost.TButton", command=self._open_dir).pack(
            side="left", padx=px(8)
        )
        self.lbl_info = ttk.Label(actions, text="", style="TLabel", foreground=theme.MUTED)
        self.lbl_info.pack(side="right")

        runs_card = ttk.Frame(self, style="Card.TFrame", padding=px(10))
        runs_card.pack(fill="both", expand=True)

        columns = (
            ("time", "时间", 170, "w"),
            ("users", "用户名", 200, "w"),
            ("hits", "命中", 70, "center"),
            ("sites", "站点数", 80, "center"),
            ("elapsed", "用时", 90, "center"),
            ("dir", "导出目录", 380, "w"),
        )
        self.tree = ttk.Treeview(runs_card, columns=[c[0] for c in columns], show="headings")
        for key, label, width, anchor in columns:
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=key == "dir")

        vsb = ttk.Scrollbar(runs_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_card = ttk.Frame(self, style="Card.TFrame", padding=px(10))
        detail_card.pack(fill="both", expand=True, pady=(px(8), 0))

        ttk.Label(detail_card, text="这次的结果", style="Field.TLabel").pack(anchor="w", pady=(0, px(6)))

        columns2 = (
            ("user", "用户名", 160, "w"),
            ("site", "站点", 200, "w"),
            ("status", "状态", 90, "w"),
            ("url", "链接", 500, "w"),
        )
        self.tree_detail = ttk.Treeview(detail_card, columns=[c[0] for c in columns2], show="headings")
        for key, label, width, anchor in columns2:
            self.tree_detail.heading(key, text=label, anchor=anchor)
            self.tree_detail.column(key, width=self.px(width), anchor=anchor, stretch=key == "url")

        vsb2 = ttk.Scrollbar(detail_card, orient="vertical", command=self.tree_detail.yview)
        self.tree_detail.configure(yscrollcommand=vsb2.set)
        self.tree_detail.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")
        self.tree_detail.tag_configure("ok", foreground=theme.OK)
        self.tree_detail.tag_configure("muted", foreground=theme.GRAY)
        self.tree_detail.bind("<Double-1>", self._open_link)

    # ---------- 数据 ----------
    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        runs = self.shell.hist.list_runs(limit=300)
        for run in runs:
            self.tree.insert(
                "", "end", iid=str(run["id"]),
                values=(
                    run["created_at"],
                    run["usernames"],
                    run["hits"],
                    run["sites"],
                    f"{run['elapsed']:.1f}s",
                    run["out_dir"] or "—",
                ),
            )
        stats = self.shell.hist.stats()
        self.lbl_info.configure(text=f"共 {stats['runs']} 次检索 · {stats['results']} 条结果")
        if runs:
            first = str(runs[0]["id"])
            self.tree.selection_set(first)
            self._load_detail(int(first))
        else:
            self.tree_detail.delete(*self.tree_detail.get_children())

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection:
            self._load_detail(int(selection[0]))

    def _load_detail(self, run_id: int) -> None:
        self.tree_detail.delete(*self.tree_detail.get_children())
        for row in self.shell.hist.results(run_id):
            key = str(row.get("status") or "unknown")
            self.tree_detail.insert(
                "", "end",
                values=(row["username"], row["site"], STATUS_TEXT.get(key, "未知"), row["url"] or "—"),
                tags=("ok" if key == "claimed" else "muted",),
            )

    # ---------- 操作 ----------
    def _delete(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("先选一条", "先在列表里点一次检索记录。")
            return
        if not messagebox.askyesno("确认删除", f"删掉这 {len(selection)} 条记录？"):
            return
        for run_id in selection:
            self.shell.hist.delete_run(int(run_id))
        self.refresh()

    def _clear(self) -> None:
        if not messagebox.askyesno("清空历史", "所有检索历史都会被删除，确定？"):
            return
        self.shell.hist.clear()
        self.refresh()

    def _open_dir(self) -> None:
        selection = self.tree.selection()
        if selection:
            run = self.shell.hist.run(int(selection[0]))
            target = (run or {}).get("out_dir")
        else:
            target = ""
        if not target or not Path(target).exists():
            messagebox.showinfo("没有目录", "这条记录没有关联的导出目录。")
            return
        open_path(Path(target))

    def _open_link(self, _event=None) -> None:
        selection = self.tree_detail.selection()
        if not selection:
            return
        url = self.tree_detail.item(selection[0], "values")[3]
        if url and url.startswith("http"):
            webbrowser.open(url)

    def _compare(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("先选一条", "先选一条检索记录，再和它上一次比。")
            return
        run_id = int(selection[0])
        diff = self.shell.hist.compare(run_id)
        if not diff:
            messagebox.showinfo(
                "没有可比的记录",
                "这条记录之前没有同用户名的检索，也没有更早的记录可以比。",
            )
            return
        CompareDialog(self.winfo_toplevel(), diff, self.px)
