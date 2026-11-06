"""主窗口外壳：顶栏 + 左侧导航 + 内容区 + 状态栏。"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .. import __app_name_zh__, __version__
from .. import config as cfg
from ..constraints import Constraints
from ..history import History
from ..paths import ICON_PATH
from ..platform_win import enable_dpi_awareness, open_path
from ..sitelib import SiteLibrary
from . import theme

NAV_ITEMS = (
    ("search", "检索"),
    ("graph", "图谱"),
    ("sites", "站点库"),
    ("history", "历史"),
    ("settings", "设置"),
)


class Shell(tk.Tk):
    """页面容器。各页面通过 self.shell 访问配置、站点库、历史与状态栏。"""

    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()

        self.cfg = cfg.load()
        self.s = self.winfo_fpixels("1i") / 96.0
        self.lib = SiteLibrary()
        self.hist = History()
        self.constraints = Constraints()
        self.identity: dict = {}
        self.pages: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.current = ""

        self.title(f"{__app_name_zh__} · 本地版 v{__version__}")
        try:
            if ICON_PATH.exists():
                self.iconbitmap(default=str(ICON_PATH))
        except tk.TclError:
            pass

        theme.apply_style(self, self.px)
        self._build()
        self._place_window()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda _e: self.refresh_current())
        self.show("search")

    # ---------- 尺寸 ----------
    def px(self, value: float) -> int:
        return int(round(value * self.s))

    def _place_window(self) -> None:
        width, height = self.px(1240), self.px(820)
        self.minsize(self.px(1000), self.px(640))
        geometry = self.cfg.get("geometry") or ""
        if geometry:
            try:
                self.geometry(geometry)
                return
            except tk.TclError:
                pass
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 4)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ---------- 界面 ----------
    def _build(self) -> None:
        px = self.px

        header = tk.Frame(self, bg=theme.HEADER, height=px(74))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text=__app_name_zh__, bg=theme.HEADER, fg="white",
            font=(theme.FONT, 16, "bold"),
        ).pack(side="left", padx=px(24))
        tk.Label(
            header, text=f"本地单机 · v{__version__}", bg=theme.HEADER, fg="#93a4c4",
            font=(theme.FONT, 9),
        ).pack(side="left", pady=(px(8), 0))

        status = ttk.Frame(self, style="Status.TFrame")
        status.pack(side="bottom", fill="x")
        self.lbl_status = ttk.Label(status, text="就绪", style="Status.TLabel")
        self.lbl_status.pack(side="left", padx=px(16), pady=px(5))
        self.lbl_sites = ttk.Label(status, text="", style="Status.TLabel")
        self.lbl_sites.pack(side="right", padx=px(16), pady=px(5))

        outer = ttk.Frame(self, style="TFrame")
        outer.pack(fill="both", expand=True)

        side = ttk.Frame(outer, style="Side.TFrame", width=px(176))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        for key, label in NAV_ITEMS:
            button = ttk.Button(
                side, text=label, style="Nav.TButton", command=lambda k=key: self.show(k)
            )
            button.pack(fill="x", padx=px(10), pady=px(3))
            self.nav_buttons[key] = button

        self.content = ttk.Frame(outer, style="TFrame")
        self.content.pack(side="left", fill="both", expand=True, padx=px(4), pady=px(10))

        self.refresh_site_count()

    # ---------- 页面切换 ----------
    def show(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            page = self._create_page(key)
            if page is None:
                return
            self.pages[key] = page
        if self.current and self.current in self.pages:
            self.pages[self.current].pack_forget()
        page.pack(fill="both", expand=True)
        self.current = key
        for name, button in self.nav_buttons.items():
            button.configure(style="NavActive.TButton" if name == key else "Nav.TButton")
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def _create_page(self, key: str) -> ttk.Frame | None:
        if key == "search":
            from .page_search import SearchPage

            return SearchPage(self.content, self)
        if key == "graph":
            from .page_graph import GraphPage

            return GraphPage(self.content, self)
        if key == "sites":
            from .page_sites import SitesPage

            return SitesPage(self.content, self)
        if key == "history":
            from .page_history import HistoryPage

            return HistoryPage(self.content, self)
        if key == "settings":
            from .page_settings import SettingsPage

            return SettingsPage(self.content, self)
        return None

    def refresh_current(self) -> None:
        page = self.pages.get(self.current)
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    # ---------- 共享 ----------
    def status(self, text: str) -> None:
        self.lbl_status.configure(text=text)

    def refresh_site_count(self) -> None:
        total = self.lib.count()
        enabled = len(self.lib.enabled_names())
        if enabled == total:
            self.lbl_sites.configure(text=f"站点库：{total} 个")
        else:
            self.lbl_sites.configure(text=f"站点库：{enabled}/{total} 个启用")

    def library_changed(self) -> None:
        self.refresh_site_count()
        self.refresh_current()

    def open_config_dir(self) -> None:
        target = Path(self.lib.user_path).parent
        target.mkdir(parents=True, exist_ok=True)
        open_path(target)

    # ---------- 收尾 ----------
    def _on_close(self) -> None:
        search_page = self.pages.get("search")
        if search_page is not None and getattr(search_page, "busy", False):
            if not messagebox.askyesno("还在检索", "检索还没结束，确定退出？"):
                return
            search_page.cancel_event.set()

        data = dict(self.cfg)
        data["geometry"] = self.winfo_geometry()
        for page in self.pages.values():
            save = getattr(page, "save_state", None)
            if callable(save):
                save(data)
        try:
            cfg.save(data)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.hist.close()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def main(selftest_seconds: float | None = None) -> int:
    try:
        app = Shell()
    except Exception as exc:  # noqa: BLE001 - 双击启动时没有控制台，必须弹窗
        import tkinter as _tk
        from tkinter import messagebox as _mb

        root = _tk.Tk()
        root.withdraw()
        _mb.showerror(
            "HolmesDesk 启动失败",
            f"{type(exc).__name__}: {exc}\n\n"
            "常见原因：配置目录没有写权限。\n"
            "可以设一个环境变量 HOLMES_DESK_HOME 指向一个能写的目录再试。",
        )
        root.destroy()
        return 1
    note = cfg.config_dir_error()
    if note:
        app.status(note)
    if selftest_seconds:
        app.after(int(selftest_seconds * 1000), app.destroy)
    app.mainloop()
    return 0
