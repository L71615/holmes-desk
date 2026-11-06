"""检索历史，落地成 SQLite，关掉程序也留着。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from . import config

HISTORY_PATH = config.config_dir() / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    elapsed     REAL    NOT NULL DEFAULT 0,
    usernames   TEXT    NOT NULL,
    sites       INTEGER NOT NULL DEFAULT 0,
    hits        INTEGER NOT NULL DEFAULT 0,
    out_dir     TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    username  TEXT    NOT NULL,
    site      TEXT    NOT NULL,
    status    TEXT    NOT NULL,
    url       TEXT,
    http      INTEGER,
    elapsed   REAL
);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
"""

STATUS_TEXT = {
    "claimed": "已注册",
    "available": "未注册",
    "unknown": "未知",
    "illegal": "格式不符",
    "waf": "被拦截",
}

STATUS_KEYS = ("claimed", "available", "unknown", "illegal", "waf")


def status_key(value: object) -> str:
    """把 QueryStatus / 字符串统一成小写键。"""
    text = str(getattr(value, "value", value) or "").strip().lower()
    return text if text in STATUS_KEYS else "unknown"


class History:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else config.config_dir() / "history.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---------- 写入 ----------
    def add_run(
        self,
        usernames: Iterable[str],
        rows: Iterable[dict[str, Any]],
        elapsed: float = 0.0,
        out_dir: str = "",
    ) -> int:
        """rows: [{username, site, status, url, http, elapsed}]，status 用 claimed/available/..."""
        names = list(usernames)
        rows = list(rows)
        hits = sum(1 for row in rows if status_key(row.get("status")) == "claimed")
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO runs (created_at, elapsed, usernames, sites, hits, out_dir)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    float(elapsed),
                    ", ".join(names),
                    len(rows),
                    hits,
                    out_dir,
                ),
            )
            run_id = int(cur.lastrowid or 0)
            self._conn.executemany(
                "INSERT INTO results (run_id, username, site, status, url, http, elapsed)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        str(row.get("username") or ""),
                        str(row.get("site") or ""),
                        status_key(row.get("status")),
                        str(row.get("url") or ""),
                        int(row["http"]) if row.get("http") not in (None, "") else None,
                        float(row["elapsed"]) if row.get("elapsed") not in (None, "") else None,
                    )
                    for row in rows
                ],
            )
        return run_id

    # ---------- 读取 ----------
    def list_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, created_at, elapsed, usernames, sites, hits, out_dir"
            " FROM runs ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        return [dict(row) for row in cur.fetchall()]

    def run(self, run_id: int) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT * FROM runs WHERE id = ?", (int(run_id),))
        row = cur.fetchone()
        return dict(row) if row else None

    def results(self, run_id: int) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT username, site, status, url, http, elapsed FROM results"
            " WHERE run_id = ? ORDER BY id",
            (int(run_id),),
        )
        return [dict(row) for row in cur.fetchall()]

    def stats(self) -> dict[str, int]:
        cur = self._conn.execute("SELECT COUNT(*) AS runs FROM runs")
        runs = int(cur.fetchone()["runs"])
        cur = self._conn.execute("SELECT COUNT(*) AS rows FROM results")
        rows = int(cur.fetchone()["rows"])
        return {"runs": runs, "results": rows}

    def previous_run(self, run_id: int) -> dict[str, Any] | None:
        """同一次检索里、比它早的上一次（没指定用户名时取全局上一条）。"""
        current = self.run(run_id)
        if not current:
            return None
        cur = self._conn.execute(
            "SELECT * FROM runs WHERE id < ? AND usernames = ? ORDER BY id DESC LIMIT 1",
            (int(run_id), current["usernames"]),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        cur = self._conn.execute(
            "SELECT * FROM runs WHERE id < ? ORDER BY id DESC LIMIT 1", (int(run_id),)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def compare(self, run_id: int, other_id: int | None = None) -> dict[str, Any] | None:
        """对比两次检索：哪些账号这次新增、哪些消失、哪些还在。

        返回 {"left": 本次 run, "right": 基线 run, "added", "removed", "kept"}，
        added / removed / kept 都是 [{username, site, status, url}]。
        """
        left = self.run(run_id)
        if not left:
            return None
        right = self.run(other_id) if other_id else self.previous_run(run_id)
        if not right:
            return None

        def index(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
            return {(row["username"], row["site"]): row for row in rows}

        now = index(self.results(left["id"]))
        before = index(self.results(right["id"]))

        def claimed_only(items: dict[tuple[str, str], dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
            return {key: row for key, row in items.items() if status_key(row["status"]) == "claimed"}

        now_claimed = claimed_only(now)
        before_claimed = claimed_only(before)
        added = [now[key] for key in now_claimed if key not in before_claimed]
        removed = [before[key] for key in before_claimed if key not in now_claimed]
        kept = [now[key] for key in now_claimed if key in before_claimed]
        added.sort(key=lambda row: (row["username"], row["site"].lower()))
        removed.sort(key=lambda row: (row["username"], row["site"].lower()))
        kept.sort(key=lambda row: (row["username"], row["site"].lower()))
        return {
            "left": left,
            "right": right,
            "added": added,
            "removed": removed,
            "kept": kept,
        }

    # ---------- 删除 ----------
    def delete_run(self, run_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM results WHERE run_id = ?", (int(run_id),))
            self._conn.execute("DELETE FROM runs WHERE id = ?", (int(run_id),))

    def clear(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM results")
            self._conn.execute("DELETE FROM runs")
        self._conn.execute("VACUUM")

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
