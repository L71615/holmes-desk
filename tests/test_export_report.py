"""报告导出（带复核结论与分组）的测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from holmes_desk.export import export_report, write_report_html, write_report_txt

ROWS = [
    {
        "username": "alice",
        "site": "GitHub",
        "group": "常用",
        "status": "已注册",
        "verdict": "复核通过",
        "url_user": "https://github.com/alice",
        "http": 200,
        "time": "0.42s",
    },
    {
        "username": "alice",
        "site": "Reddit",
        "group": "社交 / 社区",
        "status": "已注册",
        "verdict": "存疑",
        "url_user": "https://www.reddit.com/user/alice",
        "http": 403,
        "time": "1.10s",
    },
    {
        "username": "alice",
        "site": "PyPi",
        "group": "开发 / 代码",
        "status": "未注册",
        "verdict": "",
        "url_user": "https://pypi.org/user/alice",
        "http": 404,
        "time": "0.30s",
    },
]


class ReportTest(unittest.TestCase):
    def test_html_has_verdict_and_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "alice.html"
            count = write_report_html(target, "alice", ROWS)
            text = target.read_text(encoding="utf-8")
        self.assertEqual(count, 3)
        self.assertIn("复核通过", text)
        self.assertIn("存疑", text)
        # 分组标题：常用 / 开发 / 社交 各一段
        for group in ("常用", "开发 / 代码", "社交 / 社区"):
            self.assertIn(group, text)
        # 统计卡：1 条复核通过、1 条存疑
        self.assertIn("<b>1</b><span>复核通过</span>", text)
        self.assertIn("<b>1</b><span>存疑（可能误报）</span>", text)

    def test_txt_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "alice.txt"
            write_report_txt(target, "alice", ROWS)
            lines = target.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 4)  # 3 条 + 合计行
        self.assertIn("[复核通过]", lines[0] + lines[1] + lines[2])
        self.assertTrue(lines[-1].startswith("Total Websites"))

    def test_export_report_all_formats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written, errors = export_report(Path(tmp) / "run", "alice", ROWS, ["txt", "csv", "html", "jsonl"])
            self.assertEqual(errors, [])
            self.assertEqual({p.suffix for p in written}, {".txt", ".csv", ".html", ".jsonl"})
            csv_text = next(p for p in written if p.suffix == ".csv").read_text(encoding="utf-8-sig")
        self.assertIn("verdict", csv_text.splitlines()[0])
        self.assertIn("复核通过", csv_text)

    def test_empty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written, errors = export_report(Path(tmp) / "run", "bob", [], ["html"])
            self.assertEqual(errors, [])
            self.assertEqual(len(written), 1)


if __name__ == "__main__":
    unittest.main()
