"""身份档案窗口：把聚类结果和证据摊开给人看。

判断权始终在用户手里，所以这个窗口只做三件事：
1. 每个档案有哪些账号
2. 为什么把它们放在一起（逐条证据）
3. 哪些组合分数不够、需要人工确认
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from .. import i18n
from ..identity import Cluster, score_pair
from . import theme


class IdentityDialog(tk.Toplevel):
    def __init__(self, master, clusters: list[Cluster], review: list[dict], px) -> None:
        super().__init__(master)
        self.title("身份档案 · 证据视图")
        self.configure(bg=theme.BG)
        self.px = px
        self.clusters = clusters
        self.review = review
        self.transient(master)
        self.geometry(f"{px(1000)}x{px(640)}")
        self.minsize(px(760), px(520))

        header = tk.Frame(self, bg=theme.HEADER, height=px(56))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=i18n.t("身份档案"),
            bg=theme.HEADER,
            fg="white",
            font=(theme.FONT, 14, "bold"),
        ).pack(side="left", padx=px(18))
        tk.Label(
            header,
            text=f"{len(clusters)} 个档案 · {sum(c.size for c in clusters)} 个账号 · "
            f"{len(review)} 组待确认",
            bg=theme.HEADER,
            fg="#9fb0c8",
            font=(theme.FONT, 10),
        ).pack(side="left")

        body = ttk.Frame(self, style="TFrame", padding=px(14))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=4)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame", padding=px(10))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(10)))
        ttk.Label(left, text=i18n.t("档案与账号"), style="Card.TLabel", font=(theme.FONT, 10, "bold")).pack(
            anchor="w", pady=(0, px(6))
        )
        self.tree = ttk.Treeview(left, columns=("info",), show="tree headings", height=18)
        self.tree.heading("#0", text=i18n.t("档案 / 站点"))
        self.tree.heading("info", text=i18n.t("昵称"))
        self.tree.column("#0", width=self.px(240), anchor="w")
        self.tree.column("info", width=self.px(190), anchor="w")
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("cluster", font=(theme.FONT, 10, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._open_link)

        right = ttk.Frame(body, style="Card.TFrame", padding=px(10))
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text=i18n.t("证据"), style="Card.TLabel", font=(theme.FONT, 10, "bold")).pack(
            anchor="w", pady=(0, px(6))
        )
        self.txt = tk.Text(
            right,
            wrap="word",
            bg=theme.CARD,
            fg=theme.INK,
            relief="flat",
            font=(theme.FONT, 10),
            padx=px(6),
            pady=px(6),
            height=18,
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")

        self._fill()
        self._show_overview()
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

    def _fill(self) -> None:
        for cluster in self.clusters:
            node = self.tree.insert(
                "",
                "end",
                iid=f"c::{cluster.label}",
                text=f"档案 {cluster.label}（{cluster.size} 个）",
                values=(f"内部一致度 {cluster.score:.2f}" if cluster.size > 1 else "独立账号",),
                tags=("cluster",),
                open=cluster.size <= 4,
            )
            for account in cluster.accounts:
                self.tree.insert(
                    node,
                    "end",
                    iid=f"a::{cluster.label}::{account.site}",
                    text=f"  {account.site}",
                    values=(account.title,),
                )

    def _show_overview(self) -> None:
        lines = ["判断依据：用户名相同只是弱证据，头像 / 昵称 / 简介 / 互链才是主证据。", ""]
        for cluster in self.clusters:
            sites = "、".join(cluster.sites)
            lines.append(f"档案 {cluster.label}（{cluster.size} 个账号，一致度 {cluster.score:.2f}）")
            lines.append(f"  {sites}")
            if cluster.evidence:
                for item in cluster.evidence[:3]:
                    lines.append(f"  · {item}")
            else:
                lines.append("  · 没有足够证据与其它账号合并")
            lines.append("")
        if self.review:
            lines.append(f"待人工确认（{len(self.review)} 组，分数介于 0.45–0.62）：")
            for pair in self.review[:10]:
                lines.append(
                    f"  · {pair['a']} ↔ {pair['b']}（{pair['score']:.2f}）"
                    + ("：" + "；".join(pair["notes"][:2]) if pair.get("notes") else "")
                )
        self._write("\n".join(lines))

    def _write(self, text: str) -> None:
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self.txt.configure(state="disabled")

    def _pair_lines(self, cluster: Cluster) -> list[str]:
        """档案内部两两打分：让「为什么是一伙的」有具体数字可看。"""
        accounts = list(cluster.accounts)
        if len(accounts) < 2:
            return []
        lines: list[str] = []
        for i, first in enumerate(accounts):
            for second in accounts[i + 1 :]:
                pair = score_pair(first, second)
                notes = "；".join(pair.notes[:3]) or "无明显证据"
                lines.append(f"  {first.site} ↔ {second.site}：{pair.score:.2f} · {notes}")
        return lines

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        key = selection[0]
        if key.startswith("c::"):
            label = key.split("::", 1)[1]
            for cluster in self.clusters:
                if cluster.label == label:
                    lines = [f"档案 {label} · {cluster.size} 个账号 · 一致度 {cluster.score:.2f}", ""]
                    lines.append("账号：")
                    for account in cluster.accounts:
                        pages = f"（附带 {account.extra_pages} 页）" if account.extra_pages else ""
                        lines.append(f"  {account.site:<24} {account.title}{pages}")
                    lines.append("")
                    lines.append("证据：")
                    for item in cluster.evidence or ["（无）"]:
                        lines.append(f"  · {item}")
                    pairs = self._pair_lines(cluster)
                    if pairs:
                        lines.append("")
                        lines.append("两两对比：")
                        lines.extend(pairs)
                    self._write("\n".join(lines))
                    break
        else:
            parts = key.split("::")
            if len(parts) == 3:
                label, site = parts[1], parts[2]
                for cluster in self.clusters:
                    if cluster.label != label:
                        continue
                    for account in cluster.accounts:
                        if account.site != site:
                            continue
                        lines = [
                            f"{account.site}",
                            f"  用户名：{account.username}",
                            f"  昵称：{account.title}",
                            f"  简介：{(account.bio[:240] + '…') if len(account.bio) > 240 else (account.bio or '（无）')}",
                            f"  链接：{account.url}",
                            "",
                            "独立特征：",
                            f"  头像：{'已采集（' + account.avatar_path + '）' if account.avatar_path else ('有 URL 但未下载' if account.avatar_a is None else '已哈希')}",
                            f"  外链域名：{'、'.join(account.links[:6]) or '（无）'}",
                            f"  提及：{'、'.join('@' + m for m in account.mentions[:6]) or '（无）'}",
                        ]
                        if account.extra_pages:
                            lines.append(f"  附带抓取：{account.extra_pages} 页（已并入简介参与比对）")
                        self._write("\n".join(lines))
                        return

    def _open_link(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection or not selection[0].startswith("a::"):
            return
        parts = selection[0].split("::")
        if len(parts) != 3:
            return
        label, site = parts[1], parts[2]
        for cluster in self.clusters:
            if cluster.label != label:
                continue
            for account in cluster.accounts:
                if account.site == site and account.url:
                    webbrowser.open(account.url)
                    return
