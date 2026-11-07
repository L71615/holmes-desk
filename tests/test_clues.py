"""线索卡与报告整合的测试（离线）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judgedee import clues, export


def persona_stub() -> dict:
    return {
        "fields": {
            "names": [("Alice", 2)],
            "emails": [("alice@example.com", 2)],
            "ims": [("Telegram: alice", 1)],
            "domains": [("alice.dev", 1)],
        },
        "headline": "Alice",
        "summary": "一句话结论",
    }


IP_RESULT = {
    "ok": True,
    "fields": [
        ("IP", "8.8.8.8"),
        ("国家", "United States"),
        ("城市", "Ashburn"),
        ("ISP", "Google LLC"),
    ],
}

PHONE_RESULT = {"ok": True, "e164": "+8613800138000", "location": "北京市", "operator": "中国移动"}


class ClueTests(unittest.TestCase):
    def test_from_persona(self) -> None:
        items = clues.from_persona(persona_stub())
        kinds = [item["kind"] for item in items]
        self.assertEqual(kinds, ["email", "im", "domain"])
        self.assertEqual(items[0]["value"], "alice@example.com")
        self.assertEqual(items[0]["hits"], 2)
        self.assertEqual(items[0]["label"], "邮箱")

    def test_from_persona_empty(self) -> None:
        self.assertEqual(clues.from_persona(None), [])
        self.assertEqual(clues.from_persona({"fields": {}}), [])

    def test_ip_entry(self) -> None:
        entry = clues.ip_entry(IP_RESULT)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["kind"], "ip")
        self.assertEqual(entry["value"], "8.8.8.8")
        self.assertIn("United States", entry["note"])
        self.assertIn("Google LLC", entry["note"])

    def test_ip_entry_failed(self) -> None:
        self.assertIsNone(clues.ip_entry({"ok": False, "error": "boom"}))

    def test_phone_entry(self) -> None:
        entry = clues.phone_entry(PHONE_RESULT)
        assert entry is not None
        self.assertEqual(entry["value"], "+8613800138000")
        self.assertEqual(entry["kind"], "phone")

    def test_merge_sorts_and_dedupes(self) -> None:
        base = clues.from_persona(persona_stub())
        extra = [entry for entry in (clues.ip_entry(IP_RESULT), clues.phone_entry(PHONE_RESULT)) if entry]
        merged = clues.merge(base, extra)
        self.assertEqual([item["kind"] for item in merged], ["email", "im", "domain", "ip", "phone"])
        again = clues.merge(merged, base)
        self.assertEqual(len(again), len(merged))

    def test_summary_and_text(self) -> None:
        merged = clues.merge(clues.from_persona(persona_stub()), [clues.ip_entry(IP_RESULT)])
        self.assertIn("邮箱 1", clues.summary(merged))
        text = clues.to_text(merged)
        self.assertIn("alice@example.com", text)
        self.assertIn("8.8.8.8", text)


class ReportClueTests(unittest.TestCase):
    def test_html_contains_clue_table(self) -> None:
        rows = [
            {
                "username": "alice",
                "site": "GitHub",
                "group": "开发",
                "status": "已注册",
                "verdict": "复核通过",
                "url_user": "https://github.com/alice",
                "http_status": 200,
                "response_time_s": 1.2,
            }
        ]
        merged = clues.merge(clues.from_persona(persona_stub()), [clues.ip_entry(IP_RESULT)])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "r.html"
            export.write_report_html(target, "alice", rows, clues=merged)
            content = target.read_text(encoding="utf-8")
        self.assertIn("线索", content)
        self.assertIn("alice@example.com", content)
        self.assertIn("8.8.8.8", content)
        self.assertIn("<section class=\"clues\">", content)

    def test_html_without_clues(self) -> None:
        rows = [
            {
                "username": "alice",
                "site": "GitHub",
                "group": "开发",
                "status": "已注册",
                "verdict": "未判定",
                "url_user": "https://github.com/alice",
                "http_status": 200,
                "response_time_s": 1.0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "r.html"
            export.write_report_html(target, "alice", rows)
            content = target.read_text(encoding="utf-8")
        self.assertNotIn("<section class=\"clues\">", content)


if __name__ == "__main__":
    unittest.main()
