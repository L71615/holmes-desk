"""人物看板：把账号拼成一个人，一屏看完。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from .. import i18n
from .. import clues as clue_mod
from .. import trace
from ..persona import CATEGORY_ORDER
from . import theme


class PersonaDialog(tk.Toplevel):
    def __init__(self, master, persona: dict, px, on_clues=None) -> None:
        super().__init__(master)
        self.title("人物看板")
        self.configure(bg=theme.BG)
        self.px = px
        self.persona = persona
        self.on_clues = on_clues
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.extra_clues: list[dict] = []
        self.transient(master)
        self.geometry(f"{px(940)}x{px(880)}")
        self.minsize(px(760), px(640))

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
        ttk.Button(bar, text=i18n.t("复制摘要"), style="Accent.TButton", command=self._copy).pack(side="left")
        ttk.Button(bar, text=i18n.t("关闭"), command=self.destroy).pack(side="right")
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
        ttk.Label(summary, text=i18n.t("一句话结论"), style="Field.TLabel").pack(anchor="w")
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
                ttk.Label(card, text=i18n.t("—"), style="Hint.TLabel").pack(anchor="w")

        # 冲突
        if persona["conflicts"]:
            conflict = ttk.Frame(body, style="Card.TFrame", padding=px(12))
            conflict.pack(fill="x", pady=(px(10), 0))
            ttk.Label(conflict, text=i18n.t("各站说法不一致"), style="Field.TLabel").pack(anchor="w")
            for item in persona["conflicts"]:
                ttk.Label(
                    conflict,
                    text=f"{item['field']}：" + " / ".join(item["values"]),
                    style="Card.TLabel",
                    foreground=theme.WARN,
                ).pack(anchor="w", pady=(px(2), 0))

        # 线索卡：把「在哪儿」这一层接在人物后面
        self._build_clues(body)

        self.update_idletasks()
        self._center(master)
        self.grab_set()

    # ---------- 线索卡 ----------

    def _build_clues(self, body) -> None:
        px = self.px
        card = ttk.Frame(body, style="Card.TFrame", padding=px(12))
        card.pack(fill="x", pady=(px(10), 0))

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=i18n.t("线索"), style="Field.TLabel").pack(side="left")
        self.lbl_clue_counts = ttk.Label(head, text="", style="Hint.TLabel")
        self.lbl_clue_counts.pack(side="left", padx=(px(10), 0))

        self.lbl_clues = ttk.Label(
            card, text="", style="Card.TLabel", justify="left", wraplength=px(820)
        )
        self.lbl_clues.pack(anchor="w", pady=(px(6), px(8)))

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        self.ent_clue = ttk.Entry(row)
        self.ent_clue.grid(row=0, column=0, sticky="ew", ipady=px(3))
        self.ent_clue.bind("<Return>", lambda _e: self.add_clue())
        self.btn_clue = ttk.Button(
            row, text=i18n.t("查一下并加入"), style="Accent.TButton", command=self.add_clue
        )
        self.btn_clue.grid(row=0, column=1, padx=(px(8), 0))
        ttk.Button(row, text=i18n.t("复制线索"), style="Ghost.TButton", command=self._copy_clues).grid(
            row=0, column=2, padx=(px(6), 0)
        )

        self.lbl_clue_hint = ttk.Label(
            card,
            text=i18n.t("贴一个 IP 或手机号（带 +86 更准），解析结果会记在这张卡上，也会进报告。"),
            style="Hint.TLabel",
        )
        self.lbl_clue_hint.pack(anchor="w", pady=(px(6), 0))

        self._refresh_clues()

    def _clue_items(self) -> list[dict]:
        return clue_mod.merge(clue_mod.from_persona(self.persona), self.extra_clues)

    def _refresh_clues(self) -> None:
        items = self._clue_items()
        self.lbl_clue_counts.configure(text=clue_mod.summary(items))
        if not items:
            self.lbl_clues.configure(text=i18n.t("还没有可对外核实的线索（主页没公开邮箱 / IM / 外链）"))
            return
        lines = []
        for item in items:
            note = f"· {item['note']}" if item.get("note") else ""
            lines.append(f"{item['label']}：{item['value']}  {note}".rstrip())
        self.lbl_clues.configure(text=i18n.t("\n").join(lines))

    def add_clue(self) -> None:
        if self.busy:
            return
        text = self.ent_clue.get().strip()
        if not text:
            self.lbl_clue_hint.configure(text=i18n.t("先贴一个 IP 或手机号"), foreground=theme.BAD)
            return
        self.busy = True
        self.btn_clue.configure(state="disabled", text=i18n.t("解析中…"))
        self.lbl_clue_hint.configure(text=f"正在解析 {text} …", foreground=theme.MUTED)

        def runner() -> None:
            payload = {"ok": False, "error": "无法识别"}
            try:
                if "." in text or ":" in text:
                    payload = trace.lookup_ip(text)
                    payload["_kind"] = "ip"
                else:
                    payload = trace.parse_phone(text)
                    payload["_kind"] = "phone"
            except Exception as exc:  # noqa: BLE001
                payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            self.queue.put(payload)

        threading.Thread(target=runner, daemon=True).start()
        self.after(150, self._pump_clue)

    def _pump_clue(self) -> None:
        try:
            payload = self.queue.get_nowait()
        except queue.Empty:
            self.after(150, self._pump_clue)
            return
        self.busy = False
        self.btn_clue.configure(state="normal", text=i18n.t("查一下并加入"))
        entry = None
        if payload.get("_kind") == "ip":
            entry = clue_mod.ip_entry(payload)
        elif payload.get("_kind") == "phone":
            entry = clue_mod.phone_entry(payload)
        if not entry:
            reason = payload.get("error") or "没有拿到归属信息"
            self.lbl_clue_hint.configure(text=f"没加上：{reason}", foreground=theme.BAD)
            return
        self.extra_clues.append(entry)
        self.ent_clue.delete(0, "end")
        self.lbl_clue_hint.configure(
            text=f"已加入：{entry['label']} {entry['value']}", foreground=theme.MUTED
        )
        if self.on_clues is not None:
            try:
                self.on_clues(list(self.extra_clues))
            except Exception:  # noqa: BLE001 - 回调失败不该影响界面
                pass
        self._refresh_clues()

    def _copy_clues(self) -> None:
        text = clue_mod.to_text(self._clue_items())
        if not text:
            self.lbl_clue_hint.configure(text=i18n.t("还没有线索可复制"), foreground=theme.BAD)
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.lbl_clue_hint.configure(text=i18n.t("线索已复制到剪贴板"), foreground=theme.MUTED)
        except Exception:  # noqa: BLE001
            pass

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
            self.lbl_copied.configure(text=i18n.t("已复制到剪贴板"))
        except Exception:  # noqa: BLE001
            self.lbl_copied.configure(text=i18n.t("复制失败"))
