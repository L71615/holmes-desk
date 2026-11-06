"""站点库 / 历史 / 复核 的离线测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from holmes_desk.engine import QueryStatus
from holmes_desk.history import History
from holmes_desk.paths import SITE_DATA_PATH
from holmes_desk.sitelib import DEFAULT_GROUP, SiteLibrary, validate_site

GOOD_SITE = {
    "url": "https://example.com/{}",
    "urlMain": "https://example.com",
    "errorType": "status_code",
    "errorCode": 404,
}


class TestSiteLibrary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.user_path = Path(self._tmp.name) / "sites_user.json"
        self.lib = SiteLibrary(SITE_DATA_PATH, self.user_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_seed_groups(self):
        groups = self.lib.group_names()
        self.assertIn("常用", groups)
        self.assertIn("GitHub", self.lib.members("常用"))
        self.assertEqual(self.lib.group_of("GitHub"), "常用")
        self.assertEqual(len(self.lib.sites), self.lib.count())

    def test_group_move(self):
        self.lib.set_group("GitHub", "我的组")
        self.assertEqual(self.lib.group_of("GitHub"), "我的组")
        self.assertNotIn("GitHub", self.lib.members("常用"))
        self.lib.set_group("GitHub", DEFAULT_GROUP)
        self.assertEqual(self.lib.group_of("GitHub"), DEFAULT_GROUP)
        self.assertIn("GitHub", self.lib.ungrouped())
        self.assertNotIn("我的组", self.lib.group_names())

    def test_custom_site_and_validation(self):
        self.lib.add_site("我的站", GOOD_SITE, "自定义")
        self.assertIn("我的站", self.lib.sites)
        self.assertTrue(self.lib.is_custom("我的站"))
        self.assertEqual(self.lib.group_of("我的站"), "自定义")

        with self.assertRaises(ValueError):
            self.lib.add_site("坏站", {"url": "https://x.com/", "errorType": "status_code"})
        with self.assertRaises(ValueError):
            self.lib.add_site("坏,站", GOOD_SITE)
        with self.assertRaises(ValueError):
            self.lib.add_site("关键字站", {"url": "https://x.com/{}", "errorType": "message"})

    def test_disable_and_reset(self):
        self.lib.set_enabled("GitHub", False)
        self.assertNotIn("GitHub", self.lib.enabled_names())
        self.assertNotIn("GitHub", self.lib.selection())
        self.lib.set_enabled("GitHub", True)
        self.assertIn("GitHub", self.lib.enabled_names())

        self.lib.remove_site("GitHub")
        self.assertIn("GitHub", self.lib.sites)  # 内置站点不删，只禁用
        self.assertFalse(self.lib.is_enabled("GitHub"))
        self.lib.reset_site("GitHub")
        self.assertTrue(self.lib.is_enabled("GitHub"))

    def test_export_import_roundtrip(self):
        self.lib.add_site("我的站", GOOD_SITE, "自定义")
        self.lib.set_label("GitHub", "代码托管")
        self.lib.set_enabled("Reddit", False)
        self.lib.save()

        blob = Path(self._tmp.name) / "backup.json"
        self.lib.export_to(blob)
        self.assertTrue(blob.exists())

        other = SiteLibrary(SITE_DATA_PATH, Path(self._tmp.name) / "other.json")
        stats = other.import_from(blob)
        self.assertEqual(stats["added_sites"], 1)
        self.assertIn("我的站", other.sites)
        self.assertEqual(other.label("GitHub"), "代码托管")
        self.assertFalse(other.is_enabled("Reddit"))

    def test_search_and_selection(self):
        self.assertIn("GitHub", self.lib.search("github"))
        picked = self.lib.selection(["常用"])
        self.assertIn("GitHub", picked)
        self.assertLess(len(picked), self.lib.count())


class TestHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hist = History(Path(self._tmp.name) / "history.db")

    def tearDown(self):
        self.hist.close()
        self._tmp.cleanup()

    def test_add_list_delete(self):
        rows = [
            {"username": "tester", "site": "GitHub", "status": "claimed",
             "url": "https://github.com/tester", "http": 200, "elapsed": 0.3},
            {"username": "tester", "site": "Reddit", "status": "available",
             "url": "https://reddit.com/user/tester", "http": 404, "elapsed": 0.4},
        ]
        run_id = self.hist.add_run(["tester"], rows, elapsed=1.2, out_dir="results/1")
        self.assertGreater(run_id, 0)

        runs = self.hist.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["hits"], 1)
        self.assertEqual(runs[0]["usernames"], "tester")

        detail = self.hist.results(run_id)
        self.assertEqual(len(detail), 2)
        self.assertEqual(detail[0]["site"], "GitHub")

        self.hist.delete_run(run_id)
        self.assertEqual(self.hist.list_runs(), [])
        self.assertEqual(self.hist.stats()["runs"], 0)

    def test_clear(self):
        self.hist.add_run(["a"], [{"username": "a", "site": "GitHub", "status": "claimed"}])
        self.hist.clear()
        self.assertEqual(self.hist.stats(), {"runs": 0, "results": 0})


class TestVerify(unittest.TestCase):
    def test_skips_unknown_sites(self):
        from holmes_desk.verify import verify_claimed

        self.assertEqual(verify_claimed([("u", "不存在")], {}), [])
        self.assertEqual(verify_claimed([], {}), [])

    def test_verdict_mapping(self):
        from holmes_desk.verify import verify_claimed

        fake = [
            {"username": "u", "site": "GitHub", "verdict": "confirmed", "status": QueryStatus.CLAIMED,
             "http": 200, "elapsed": 0.1, "message": ""},
            {"username": "u", "site": "Reddit", "verdict": "suspect", "status": QueryStatus.AVAILABLE,
             "http": 404, "elapsed": 0.1, "message": ""},
        ]
        with mock.patch("holmes_desk.verify.verify_one", side_effect=fake):
            out = verify_claimed(
                [("u", "GitHub"), ("u", "Reddit")],
                {"GitHub": GOOD_SITE, "Reddit": GOOD_SITE},
            )
        self.assertEqual(len(out), 2)
        self.assertEqual({item["verdict"] for item in out}, {"confirmed", "suspect"})


class TestValidate(unittest.TestCase):
    def test_validate_site(self):
        self.assertEqual(validate_site("ok", GOOD_SITE), [])
        self.assertTrue(validate_site("", GOOD_SITE))
        self.assertTrue(validate_site("x", {"url": "https://x.com/{}", "errorType": "nope"}))
        self.assertTrue(validate_site("x", {"url": "x.com/{}", "errorType": "status_code"}))


if __name__ == "__main__":
    unittest.main()
