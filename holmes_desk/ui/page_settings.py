"""设置页：默认参数、数据目录、关于。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import __app_name_zh__, __version__
from .. import config as cfg
from ..paths import SITE_DATA_PATH
from . import theme

FORMATS = (("txt", "TXT"), ("csv", "CSV"), ("xlsx", "XLSX"), ("html", "HTML"), ("jsonl", "JSONL"))


class SettingsPage(ttk.Frame):
    def __init__(self, master: tk.Misc, shell) -> None:
        super().__init__(master, style="TFrame")
        self.shell = shell
        self.px = shell.px
        self.cfg = shell.cfg
        self._build()

    def _build(self) -> None:
        px = self.px

        card = ttk.Frame(self, style="Card.TFrame", padding=px(16))
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="检索默认值", style="Field.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, px(10))
        )

        ttk.Label(card, text="代理", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=(0, px(8)))
        self.ent_proxy = ttk.Entry(card)
        self.ent_proxy.grid(row=1, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_proxy.insert(0, self.cfg.get("proxy") or "")

        ttk.Label(card, text="超时（秒）", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, px(8)))
        self.spn_timeout = ttk.Spinbox(card, from_=5, to=120, increment=5, width=8)
        self.spn_timeout.grid(row=2, column=1, sticky="w", pady=(0, px(8)))
        self.spn_timeout.set(self.cfg.get("timeout") or 20)

        ttk.Label(card, text="结果目录", style="Field.TLabel").grid(row=3, column=0, sticky="w", pady=(0, px(8)))
        self.ent_out = ttk.Entry(card)
        self.ent_out.grid(row=3, column=1, sticky="ew", pady=(0, px(8)))
        self.ent_out.insert(0, self.cfg.get("out_dir") or str(Path.cwd() / "results"))
        ttk.Button(card, text="浏览…", style="Ghost.TButton", command=self._pick_dir).grid(
            row=3, column=2, padx=(px(6), 0), pady=(0, px(8))
        )

        ttk.Label(card, text="默认导出", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(0, px(8)))
        fmt_row = ttk.Frame(card, style="Card.TFrame")
        fmt_row.grid(row=4, column=1, sticky="w", pady=(0, px(8)))
        self.var_formats: dict[str, tk.BooleanVar] = {}
        for key, label in FORMATS:
            var = tk.BooleanVar(value=bool(self.cfg.get(f"export_{key}", key in ("txt", "csv"))))
            self.var_formats[key] = var
            ttk.Checkbutton(fmt_row, text=label, variable=var).pack(side="left", padx=(0, px(10)))

        switches = ttk.Frame(card, style="Card.TFrame")
        switches.grid(row=5, column=1, sticky="w", pady=(0, px(4)))
        self.var_nsfw = tk.BooleanVar(value=bool(self.cfg.get("include_nsfw")))
        self.var_showall = tk.BooleanVar(value=bool(self.cfg.get("show_all")))
        ttk.Checkbutton(switches, text="默认包含 NSFW 站点", variable=self.var_nsfw).pack(side="left")
        ttk.Checkbutton(switches, text="默认显示未注册结果", variable=self.var_showall).pack(
            side="left", padx=(px(14), 0)
        )

        ttk.Label(card, text="我的用户名", style="Field.TLabel").grid(
            row=6, column=0, sticky="w", pady=(px(6), px(8))
        )
        self.ent_self = ttk.Entry(card)
        self.ent_self.grid(row=6, column=1, sticky="ew", pady=(px(6), px(8)))
        self.ent_self.insert(0, self.cfg.get("self_usernames") or "")

        self.var_self_default = tk.BooleanVar(value=bool(self.cfg.get("self_only")))
        ttk.Checkbutton(
            card,
            text="检索页默认勾上「自查模式」：只查我自己的账号，看板里的邮箱 / IM / 个人站点打码",
            variable=self.var_self_default,
        ).grid(row=7, column=1, sticky="w")

        ttk.Button(card, text="保存设置", style="Accent.TButton", command=self._save).grid(
            row=8, column=1, sticky="e", pady=(px(12), 0)
        )

        data_card = ttk.Frame(self, style="Card.TFrame", padding=px(16))
        data_card.pack(fill="x", pady=(px(10), 0))
        ttk.Label(data_card, text="数据", style="Field.TLabel").pack(anchor="w", pady=(0, px(8)))
        ttk.Label(
            data_card,
            text=f"站点表：{SITE_DATA_PATH}\n用户配置：{self.shell.lib.user_path}\n历史库：{self.shell.hist.path}",
            style="Hint.TLabel", justify="left",
        ).pack(anchor="w", pady=(0, px(10)))

        buttons = ttk.Frame(data_card, style="Card.TFrame")
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="打开配置目录", style="Ghost.TButton", command=self.shell.open_config_dir).pack(
            side="left"
        )
        ttk.Button(buttons, text="清空历史", style="Danger.TButton", command=self._clear_history).pack(
            side="left", padx=px(8)
        )

        about = ttk.Frame(self, style="Card.TFrame", padding=px(16))
        about.pack(fill="both", expand=True, pady=(px(10), 0))
        ttk.Label(about, text="关于", style="Field.TLabel").pack(anchor="w", pady=(0, px(8)))
        ttk.Label(
            about,
            text=(
                f"{__app_name_zh__} v{__version__} —— 本地单机，一次装好，离线可用。\n"
                f"站点库现有 {self.shell.lib.count()} 个站点，全部内置，不联网更新。\n"
                "判定规则参考 sherlock-project/sherlock（MIT），站点表同源，本程序与其无运行依赖。\n"
                "只依赖 requests；导出 XLSX 时才需要 pandas + openpyxl。"
            ),
            style="Hint.TLabel", justify="left", wraplength=self.px(760),
        ).pack(anchor="w")

    def _pick_dir(self) -> None:
        current = self.ent_out.get().strip() or str(Path.cwd())
        chosen = filedialog.askdirectory(initialdir=current, title="选择结果目录")
        if chosen:
            self.ent_out.delete(0, "end")
            self.ent_out.insert(0, chosen)

    def _save(self) -> None:
        data = dict(self.cfg)
        data.update(
            {
                "proxy": self.ent_proxy.get(),
                "timeout": self.spn_timeout.get(),
                "out_dir": self.ent_out.get(),
                "include_nsfw": self.var_nsfw.get(),
                "show_all": self.var_showall.get(),
                "self_usernames": self.ent_self.get().strip(),
                "self_only": self.var_self_default.get(),
            }
        )
        for key, var in self.var_formats.items():
            data[f"export_{key}"] = var.get()
        self.shell.cfg.update(data)
        self.cfg = self.shell.cfg
        try:
            cfg.save(data)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc))
            return
        self.shell.status("设置已保存")

    def _clear_history(self) -> None:
        if not messagebox.askyesno("清空历史", "所有检索历史都会被删除，确定？"):
            return
        self.shell.hist.clear()
        page = self.shell.pages.get("history")
        if page is not None:
            page.refresh()
        self.shell.status("历史已清空")
