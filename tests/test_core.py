"""离线单元测试：跑 `python -m unittest discover -s tests` 即可，不需要联网。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from holmes_desk.engine import (
    QueryResult,
    QueryStatus,
    expand_usernames,
    load_sites,
    pick_sites,
)
from holmes_desk.export import export_run
from holmes_desk.paths import SITE_DATA_PATH
from holmes_desk.presets import preset_names, preset_text


def _fake_results() -> dict:
    def make(site: str, status: QueryStatus, url: str, code: int) -> dict:
        return {
            "url_main": url,
            "url_user": url,
            "status": QueryResult("tester", site, url, status, 0.12, None, code),
            "http_status": code,
        }

    return {
        "GitHub": make("GitHub", QueryStatus.CLAIMED, "https://github.com/tester", 200),
        "Reddit": make("Reddit", QueryStatus.AVAILABLE, "https://reddit.com/user/tester", 404),
    }


class TestEngine(unittest.TestCase):
    def test_expand_usernames(self):
        self.assertEqual(expand_usernames("a b,c"), ["a", "b", "c"])
        self.assertEqual(expand_usernames("john{?}doe"), ["john_doe", "john-doe", "john.doe"])
        self.assertEqual(expand_usernames("，、 "), [])

    def test_site_table(self):
        sites = load_sites(SITE_DATA_PATH)
        self.assertGreater(len(sites), 400)
        self.assertIn("GitHub", sites)
        self.assertFalse(any(name.startswith("$") for name in sites))

    def test_pick_sites(self):
        sites = load_sites(SITE_DATA_PATH)
        chosen, missing = pick_sites(sites, ["github", "REDDIT"])
        self.assertEqual(sorted(chosen), ["GitHub", "Reddit"])
        self.assertEqual(missing, [])
        _, missing = pick_sites(sites, ["并没有这个站"])
        self.assertEqual(missing, ["并没有这个站"])

    def test_presets_exist(self):
        names = preset_names()
        self.assertEqual(names[0], "全部站点")
        self.assertGreaterEqual(len(names), 6)
        for name in names[1:]:
            self.assertTrue(preset_text(name).strip(), name)


class TestExport(unittest.TestCase):
    def test_all_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            written, errors = export_run(
                run_dir, "tester", _fake_results(), ["txt", "csv", "html", "jsonl"], show_all=True
            )
            self.assertEqual(errors, [])
            names = sorted(p.suffix for p in written)
            self.assertEqual(names, [".csv", ".html", ".jsonl", ".txt"])

            html = (run_dir / "tester.html").read_text(encoding="utf-8")
            self.assertIn("tester", html)
            self.assertIn("github.com/tester", html)

            rows = [json.loads(line) for line in (run_dir / "tester.jsonl").read_text("utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["exists"] for r in rows}, {"Claimed", "Available"})

    def test_only_claimed_when_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            written, _ = export_run(Path(tmp), "tester", _fake_results(), ["csv"], show_all=False)
            text = written[0].read_text(encoding="utf-8-sig")
            self.assertIn("GitHub", text)
            self.assertNotIn("Reddit", text)


if __name__ == "__main__":
    unittest.main()
