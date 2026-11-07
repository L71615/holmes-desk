"""站点库页：看全部站点，改分组/备注/判定规则，加自定义站点。"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import i18n
from ..sitelib import DEFAULT_GROUP, ERROR_TYPES, ERROR_TYPE_TEXT, validate_site
from . import theme

TYPE_LABEL = {ERROR_TYPE_TEXT[key]: key for key in ERROR_TYPES}


class SiteDialog(tk.Toplevel):
    """新增 / 编辑单个站点。"""

    def __init__(self, master: tk.Misc, shell, name: str = "", info: dict | None = None,
                 group: str = DEFAULT_GROUP, label: str = "") -> None:
        super().__init__(master)
        self.shell = shell
        self.px = shell.px
        self.lib = shell.lib
        self.original = name
        self.result: tuple[str, dict, str, str] | None = None

        self.title("编辑站点" if name else "新增站点")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())

        info = dict(info or {"url": "", "errorType": "status_code", "errorCode": 404})
        px = self.px
        card = ttk.Frame(self, style="Card.TFrame", padding=px(18))
        card.pack(fill="both", expand=True, padx=px(12), pady=px(12))
        card.columnconfigure(1, weight=1)

        row = 0

        def field(text: str) -> None:
            ttk.Label(card, text=text, style="Field.TLabel").grid(
                row=row, column=0, sticky="w", pady=(0, px(8)), padx=(0, px(12))
            )

        field("站点名")
        self.ent_name = ttk.Entry(card, width=42)
        self.ent_name.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_name.insert(0, name)
        if name:
            self.ent_name.configure(state="readonly")
        row += 1

        field("显示名（可选）")
        self.ent_label = ttk.Entry(card)
        self.ent_label.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_label.insert(0, label)
        row += 1

        field("分组")
        self.cmb_group = ttk.Combobox(card, values=self.lib.group_names() or [DEFAULT_GROUP])
        self.cmb_group.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.cmb_group.set(group)
        row += 1

        field("URL 模板")
        self.ent_url = ttk.Entry(card)
        self.ent_url.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_url.insert(0, str(info.get("url") or ""))
        row += 1

        ttk.Label(
            card, text="用 {} 代表用户名，例如 https://example.com/user/{}",
            style="Hint.TLabel",
        ).grid(row=row, column=1, sticky="w", pady=(0, px(10)))
        row += 1

        field("判定方式")
        self.cmb_type = ttk.Combobox(
            card, values=[ERROR_TYPE_TEXT[t] for t in ERROR_TYPES], state="readonly"
        )
        self.cmb_type.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.cmb_type.set(ERROR_TYPE_TEXT.get(str(info.get("errorType") or "status_code"), "状态码"))
        self.cmb_type.bind("<<ComboboxSelected>>", lambda _e: self._sync_type())
        row += 1

        field("未注册时的状态码")
        self.ent_code = ttk.Entry(card)
        self.ent_code.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_code.insert(0, str(info.get("errorCode") or ""))
        self.row_code = row
        row += 1

        field("未注册时的关键字")
        self.ent_msg = ttk.Entry(card)
        self.ent_msg.grid(row=row, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_msg.insert(0, str(info.get("errorMsg") or ""))
        self.row_msg = row
        row += 1

        self.var_nsfw = tk.BooleanVar(value=bool(info.get("isNSFW")))
        self.var_enabled = tk.BooleanVar(value=self.lib.is_enabled(name) if name else True)
        checks = ttk.Frame(card, style="Card.TFrame")
        checks.grid(row=row, column=1, sticky="w", pady=(0, px(4)))
        ttk.Checkbutton(checks, text=i18n.t("NSFW 站点"), variable=self.var_nsfw).pack(side="left")
        ttk.Checkbutton(checks, text=i18n.t("启用"), variable=self.var_enabled).pack(side="left", padx=(px(14), 0))
        row += 1

        if name and name in self.lib.base:
            ttk.Label(
                card, text=i18n.t("这是内置站点：改动会作为覆盖保存在用户配置里，可随时「恢复内置」。"),
                style="Hint.TLabel", wraplength=px(420),
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(px(6), 0))

        buttons = ttk.Frame(self, style="TFrame")
        buttons.pack(fill="x", padx=px(12), pady=(0, px(12)))
        ttk.Button(buttons, text=i18n.t("保存"), style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(buttons, text=i18n.t("取消"), style="Ghost.TButton", command=self.destroy).pack(
            side="right", padx=(0, px(8))
        )

        self._sync_type()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        self._center(master)
        self.grab_set()
        self.ent_name.focus_set() if not name else self.ent_url.focus_set()

    def _center(self, master: tk.Misc) -> None:
        top = master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_width()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _sync_type(self) -> None:
        kind = TYPE_LABEL.get(self.cmb_type.get(), "status_code")
        for widget, show in ((self.ent_code, kind == "status_code"), (self.ent_msg, kind == "message")):
            state = "normal" if show else "disabled"
            widget.configure(state=state)

    def _save(self) -> None:
        name = self.ent_name.get().strip()
        if not name:
            messagebox.showwarning("还差一点", "站点名不能为空", parent=self)
            return

        kind = TYPE_LABEL.get(self.cmb_type.get(), "status_code")
        info: dict = {
            "url": self.ent_url.get().strip(),
            "errorType": kind,
            "urlMain": self.ent_url.get().strip().split("{}")[0].rstrip("/"),
        }
        if kind == "status_code":
            code = self.ent_code.get().strip()
            if code:
                info["errorCode"] = int(code) if code.isdigit() else code
        if kind == "message":
            info["errorMsg"] = self.ent_msg.get().strip()
        if self.var_nsfw.get():
            info["isNSFW"] = True

        problems = validate_site(name, info)
        if problems:
            messagebox.showwarning("检查一下", "\n".join(problems), parent=self)
            return

        group = self.cmb_group.get().strip() or DEFAULT_GROUP
        if name != self.original:
            # 改名：删掉旧的自定义项，避免留下重复条目
            if self.original and self.original in self.lib.custom:
                self.lib.remove_site(self.original)
            self.lib.add_site(name, info, group)
        else:
            self.lib.add_site(name, info, group)
        self.lib.set_enabled(name, self.var_enabled.get())
        self.lib.set_label(name, self.ent_label.get().strip())
        self.result = (name, info, group, self.ent_label.get().strip())
        self.destroy()


class SitesPage(ttk.Frame):
    def __init__(self, master: tk.Misc, shell) -> None:
        super().__init__(master, style="TFrame")
        self.shell = shell
        self.px = shell.px
        self.lib = shell.lib
        self._build()
        self.refresh()

    def _build(self) -> None:
        px = self.px

        top = ttk.Frame(self, style="Card.TFrame", padding=px(12))
        top.pack(fill="x")

        ttk.Label(top, text=i18n.t("站点库"), style="Field.TLabel").pack(side="left", padx=(0, px(12)))
        self.ent_search = ttk.Entry(top, width=24)
        self.ent_search.pack(side="left")
        self.ent_search.bind("<KeyRelease>", lambda _e: self.refresh())

        ttk.Label(top, text=i18n.t("分组"), style="Hint.TLabel").pack(side="left", padx=(px(12), px(6)))
        self.cmb_group = ttk.Combobox(top, width=14, state="readonly")
        self.cmb_group.pack(side="left")
        self.cmb_group.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(top, text=i18n.t("导出…"), style="Ghost.TButton", command=self._export).pack(side="right")
        ttk.Button(top, text=i18n.t("导入…"), style="Ghost.TButton", command=self._import).pack(
            side="right", padx=(0, px(8))
        )
        ttk.Button(top, text=i18n.t("新增站点"), style="Accent.TButton", command=self._add).pack(
            side="right", padx=(0, px(8))
        )

        actions = ttk.Frame(self, style="TFrame")
        actions.pack(fill="x", pady=(px(8), px(6)))
        ttk.Button(actions, text=i18n.t("编辑"), style="Ghost.TButton", command=self._edit).pack(side="left")
        ttk.Button(actions, text=i18n.t("启用 / 禁用"), style="Ghost.TButton", command=self._toggle).pack(
            side="left", padx=px(8)
        )
        ttk.Button(actions, text=i18n.t("恢复内置"), style="Ghost.TButton", command=self._reset).pack(side="left")
        ttk.Button(actions, text=i18n.t("删除自定义站点"), style="Danger.TButton", command=self._delete).pack(
            side="left", padx=px(8)
        )
        self.lbl_info = ttk.Label(actions, text="", style="TLabel", foreground=theme.MUTED)
        self.lbl_info.pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame", padding=px(10))
        card.pack(fill="both", expand=True)

        columns = (
            ("site", "站点", 220, "w", True),
            ("label", "备注", 140, "w", False),
            ("group", "分组", 130, "w", False),
            ("state", "状态", 80, "center", False),
            ("url", "URL 模板", 380, "w", True),
        )
        self.tree = ttk.Treeview(card, columns=[c[0] for c in columns], show="headings")
        for key, label, width, anchor, stretch in columns:
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.px(width), anchor=anchor, stretch=stretch)

        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("off", foreground=theme.GRAY)
        self.tree.tag_configure("custom", foreground=theme.ACCENT)
        self.tree.bind("<Double-1>", lambda _e: self._edit())
        self.tree.bind("<Button-3>", self._context_menu)

    # ---------- 数据 ----------
    def refresh(self) -> None:
        groups = ["全部", *self.lib.group_names()]
        current = self.cmb_group.get() or "全部"
        self.cmb_group.configure(values=groups)
        if current not in groups:
            current = "全部"
        self.cmb_group.set(current)

        keyword = self.ent_search.get().strip().lower()
        self.tree.delete(*self.tree.get_children())

        names = self.lib.search(keyword)
        if current != "全部":
            names = [n for n in names if self.lib.group_of(n) == current]

        for name in names:
            info = self.lib.info(name) or {}
            state = "启用" if self.lib.is_enabled(name) else "禁用"
            label = self.lib.label(name)
            if label == name:  # 没起中文名就不重复显示一遍
                label = ""
            tags = []
            if not self.lib.is_enabled(name):
                tags.append("off")
            elif self.lib.is_custom(name):
                tags.append("custom")
            self.tree.insert(
                "", "end", iid=name,
                values=(name, label, self.lib.group_of(name), state,
                        str(info.get("url") or "")),
                tags=tuple(tags),
            )
        self.lbl_info.configure(
            text=f"显示 {len(names)} / 共 {self.lib.count()} 站"
            f"（启用 {len(self.lib.enabled_names())}，自定义 {len(self.lib.custom)}）"
        )
        self.shell.refresh_site_count()

    def _selected(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _need_one(self) -> str | None:
        name = self._selected()
        if not name:
            messagebox.showinfo("先选一个", "先在列表里点一个站点。")
        return name

    # ---------- 操作 ----------
    def _edit(self) -> None:
        name = self._need_one()
        if not name:
            return
        info = self.lib.info(name) or {}
        dialog = SiteDialog(
            self, self.shell, name=name, info=info,
            group=self.lib.group_of(name), label=self.lib.label(name),
        )
        self.wait_window(dialog)
        if dialog.result:
            self.lib.save()
            self.refresh()
            self.shell.status(f"已更新 {name}")

    def _add(self) -> None:
        dialog = SiteDialog(self, self.shell, group=self.cmb_group.get() if self.cmb_group.get() != "全部" else DEFAULT_GROUP)
        self.wait_window(dialog)
        if dialog.result:
            name, _info, _group, _label = dialog.result
            self.lib.save()
            self.refresh()
            self.shell.status(f"已新增 {name}")

    def _toggle(self) -> None:
        name = self._need_one()
        if not name:
            return
        self.lib.set_enabled(name, not self.lib.is_enabled(name))
        self.lib.save()
        self.refresh()

    def _reset(self) -> None:
        name = self._need_one()
        if not name:
            return
        self.lib.reset_site(name)
        self.lib.save()
        self.refresh()
        self.shell.status(f"{name} 已恢复成内置定义")

    def _delete(self) -> None:
        name = self._need_one()
        if not name:
            return
        if not self.lib.is_custom(name):
            messagebox.showinfo("内置站点", "内置站点不能删，只能禁用（用「启用 / 禁用」）。")
            return
        if not messagebox.askyesno("确认删除", f"删掉自定义站点「{name}」？"):
            return
        self.lib.remove_site(name)
        self.lib.save()
        self.refresh()
        self.shell.status(f"已删除 {name}")

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            title="导出站点库",
            defaultextension=".json",
            initialfile="judgedee-sites.json",
            filetypes=[("JSON 文件", "*.json")],
        )
        if not path:
            return
        try:
            self.lib.export_to(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", str(exc))
            return
        self.shell.status(f"已导出到 {path}")

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="导入站点库", filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            stats = self.lib.import_from(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导入失败", str(exc))
            return
        self.lib.save()
        self.refresh()
        messagebox.showinfo(
            "导入完成",
            f"新增站点 {stats['added_sites']} 个，覆盖 {stats['updated_sites']} 个，"
            f"新建分组 {stats['added_groups']} 个。",
        )

    def _context_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="编辑", command=self._edit)
        menu.add_command(label="启用 / 禁用", command=self._toggle)
        menu.add_command(label="恢复内置", command=self._reset)
        menu.add_separator()
        menu.add_command(label="删除自定义站点", command=self._delete)
        menu.tk_popup(event.x_root, event.y_root)
