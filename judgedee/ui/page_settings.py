"""设置页：默认参数、数据目录、关于。"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
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

        canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.body = ttk.Frame(canvas, style="TFrame")
        window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self._canvas = canvas

        card = ttk.Frame(self.body, style="Card.TFrame", padding=px(16))
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

        data_card = ttk.Frame(self.body, style="Card.TFrame", padding=px(16))
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

        about = ttk.Frame(self.body, style="Card.TFrame", padding=px(16))
        about.pack(fill="both", expand=True, pady=(px(10), 0))
        ttk.Label(about, text="关于", style="Field.TLabel").pack(anchor="w", pady=(0, px(8)))
        ttk.Label(
            about,
            text=f"{__app_name_zh__} v{__version__}",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            about,
            text=(
                "一个跑在自己电脑上的人物情报台：给一个用户名，把散落在各站的账号找出来，\n"
                "再用主页上的昵称、简介、头像、互链当证据，判断哪些账号其实是同一个人。"
            ),
            style="Hint.TLabel", justify="left", wraplength=self.px(760),
        ).pack(anchor="w", pady=(px(6), px(10)))

        ttk.Label(about, text="名字", style="Sub.TLabel").pack(anchor="w", pady=(px(4), px(2)))
        ttk.Label(
            about,
            text=(
                "名字取自唐代断案官狄仁杰：他断案不靠灵感，靠把证物一件件摆到桌上对照。\n"
                "英文名 Judge Dee 是荷兰汉学家高罗佩写「狄公案」系列时给这个人物起的英文名，\n"
                "短、能念、能拼，所以仓库名与包名都用 judgedee。只是借个人物，与影视、出版方无关。"
            ),
            style="Hint.TLabel", justify="left", wraplength=self.px(760),
        ).pack(anchor="w", pady=(0, px(8)))

        for title, body in (
            (
                "能做什么",
                f"· 账号检索：{self.shell.lib.count()} 个站点，按用户名并发查询，支持站点分组勾选\n"
                "· 人物重建：身份聚类、证据两两对比、图谱、人物看板、换名同人建议、变体扫查\n"
                "· 周边线索：IP 归属地（国家/城市/经纬度/ISP/ASN）与手机号离线解析\n"
                "· 留痕：本地历史、两次检索对比、TXT/CSV/XLSX/HTML/JSONL 导出（HTML 内嵌 SVG 图谱）",
            ),
            (
                "离线与依赖",
                "站点表、判定规则、图标随程序分发，检索不经过任何中转服务器。\n"
                "必装只有 requests；XLSX 导出需 pandas + openpyxl，头像比对需 Pillow，\n"
                "手机号解析需 phonenumbers（离线号码库，号码不出本机）。\n"
                "IP 查询会把被查 IP 发给 ip-api.com（失败时 ipinfo.io），除此之外没有外部请求。",
            ),
            (
                "隐私",
                "所有结果只写在本机配置目录；历史库是普通 SQLite 文件，可随时清空。\n"
                "自查模式下，人物看板里的邮箱 / IM / 个人站点会打码显示，账号数与结论不受影响。",
            ),
            (
                "来源与许可",
                "代码为本人独立实现，MIT 许可（见 LICENSE）。站点清单与判定思路整理自公开资料，\n"
                "第三方数据的归属声明见 NOTICE。项目地址：github.com/L71615/judgedee",
            ),
        ):
            ttk.Label(about, text=title, style="Sub.TLabel").pack(anchor="w", pady=(px(4), px(2)))
            ttk.Label(
                about, text=body, style="Hint.TLabel", justify="left", wraplength=self.px(760)
            ).pack(anchor="w", pady=(0, px(6)))

        links = ttk.Frame(about, style="Card.TFrame")
        links.pack(anchor="w", pady=(px(8), 0))
        ttk.Button(
            links, text="打开项目主页", style="Ghost.TButton", command=self._open_homepage
        ).pack(side="left")
        ttk.Button(links, text="查看许可", style="Ghost.TButton", command=self._open_license).pack(
            side="left", padx=px(8)
        )

    def _open_homepage(self) -> None:
        webbrowser.open("https://github.com/L71615/judgedee")

    def _open_license(self) -> None:
        from ..paths import PKG_DIR

        license_path = PKG_DIR.parent / "LICENSE"
        if license_path.exists():
            os.startfile(str(license_path))  # noqa: S606 - 打开本地文本，路径自控
        else:
            messagebox.showinfo("许可", "本项目使用 MIT 许可；仓库根目录的 LICENSE 是全文。")

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
