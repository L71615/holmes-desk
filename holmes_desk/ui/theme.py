"""配色与 ttk 样式。所有尺寸都乘一个缩放系数，200% 屏幕上不发虚。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#eef1f6"
CARD = "#ffffff"
INK = "#111827"
MUTED = "#6b7280"
LINE = "#e3e7ef"
HEADER = "#0b1220"
ACCENT = "#2563eb"
ACCENT_D = "#1d4ed8"
OK = "#16a34a"
WARN = "#d97706"
BAD = "#dc2626"
GRAY = "#9ca3af"

FONT = "Microsoft YaHei UI"


def apply_style(root: tk.Misc, px) -> None:
    """注册全局 ttk 样式。"""
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass

    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=INK, font=(FONT, 10))
    st.configure("Card.TLabel", background=CARD, foreground=INK, font=(FONT, 10))
    st.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
    st.configure("Field.TLabel", background=CARD, foreground="#374151", font=(FONT, 10, "bold"))

    st.configure(
        "TEntry", fieldbackground="white", bordercolor=LINE,
        lightcolor=LINE, darkcolor=LINE, insertcolor=INK, padding=px(6),
    )
    st.configure(
        "TCombobox", fieldbackground="white", background="white", bordercolor=LINE,
        lightcolor=LINE, darkcolor=LINE, arrowcolor=INK, padding=px(4),
    )
    st.configure(
        "TSpinbox", fieldbackground="white", bordercolor=LINE,
        lightcolor=LINE, darkcolor=LINE, arrowsize=px(13), padding=px(4),
    )
    st.configure("TCheckbutton", background=CARD, foreground=INK, font=(FONT, 10))
    st.map("TCheckbutton", background=[("active", CARD)])

    st.configure(
        "Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT,
        focusthickness=0, padding=(px(20), px(9)), font=(FONT, 10, "bold"),
    )
    st.map(
        "Accent.TButton",
        background=[("active", ACCENT_D), ("disabled", "#a9c0f4")],
        bordercolor=[("active", ACCENT_D), ("disabled", "#a9c0f4")],
    )
    st.configure(
        "Ghost.TButton", background=CARD, foreground=INK, bordercolor=LINE,
        focusthickness=0, padding=(px(14), px(8)), font=(FONT, 10),
    )
    st.map("Ghost.TButton", background=[("active", "#eef2f8")])

    st.configure(
        "Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
        rowheight=px(30), borderwidth=0, font=(FONT, 9),
    )
    st.configure(
        "Treeview.Heading", background="#f3f5f9", foreground="#374151",
        relief="flat", font=(FONT, 9, "bold"), padding=(px(8), px(7)),
    )
    st.map("Treeview.Heading", background=[("active", "#e9edf5")])
    st.map("Treeview", background=[("selected", "#dbe7ff")], foreground=[("selected", HEADER)])
    st.configure(
        "TProgressbar", background=ACCENT, troughcolor="#e6ebf5",
        bordercolor="#e6ebf5", lightcolor=ACCENT, darkcolor=ACCENT,
    )
