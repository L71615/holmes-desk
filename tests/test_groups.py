"""自动分组与国内站点的单元测试（不联网）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judgedee import groups
from judgedee.paths import SITE_DATA_PATH
from judgedee.sitelib import SiteLibrary, validate_site


class ClassifyTest(unittest.TestCase):
    def test_cn_keywords(self) -> None:
        self.assertEqual(groups.classify("Bilibili", {"urlMain": "https://space.bilibili.com/"}), "国内站点")
        self.assertEqual(groups.classify("豆瓣", {"urlMain": "https://www.douban.com/"}), "国内站点")

    def test_cn_tld_fallback(self) -> None:
        self.assertEqual(groups.classify("SomeSite", {"urlMain": "https://www.somesite.com.cn/"}), "国内站点")

    def test_brand_table(self) -> None:
        self.assertEqual(groups.classify("Imgur", {"urlMain": "https://imgur.com/"}), "影音 / 创作")
        self.assertEqual(groups.classify("Pokemon Showdown", {}), "游戏")

    def test_keyword_rules(self) -> None:
        self.assertEqual(groups.classify("GitLab", {"urlMain": "https://gitlab.com/"}), "开发 / 代码")
        self.assertEqual(groups.classify("Steam", {"urlMain": "https://steamcommunity.com/"}), "游戏")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(groups.classify("Zzz Qqq", {"urlMain": "https://zzzqqq.example/"}))


class ApplyTest(unittest.TestCase):
    def _library(self, sites: dict) -> SiteLibrary:
        tmp = Path(tempfile.mkdtemp(prefix="jd-groups-"))
        base = tmp / "data.json"
        base.write_text(json.dumps(sites, ensure_ascii=False), encoding="utf-8")
        return SiteLibrary(base_path=base, user_path=tmp / "user.json")

    def test_apply_moves_sites_and_saves(self) -> None:
        lib = self._library(
            {
                "Cplusplus": {"urlMain": "https://cplusplus.com/", "url": "https://cplusplus.com/user/{}", "errorType": "status_code", "errorCode": 404},
                "Bilibili": {"urlMain": "https://space.bilibili.com/", "url": "https://space.bilibili.com/{}", "errorType": "status_code", "errorCode": 404},
                "Zzz Qqq": {"urlMain": "https://zzzqqq.example/", "url": "https://zzzqqq.example/{}", "errorType": "status_code", "errorCode": 404},
            }
        )
        counts = groups.apply(lib)
        self.assertEqual(sum(counts.values()), 2)
        self.assertIn("Cplusplus", lib.members("开发 / 代码"))
        self.assertEqual(lib.ungrouped(), ["Zzz Qqq"])
        # 落盘了：重新打开还能看到
        again = SiteLibrary(base_path=lib.base_path, user_path=lib.user_path)
        self.assertIn("Bilibili", again.members("国内站点"))

    def test_apply_is_idempotent(self) -> None:
        lib = self._library(
            {
                "Cplusplus": {"urlMain": "https://cplusplus.com/", "url": "https://cplusplus.com/user/{}", "errorType": "status_code", "errorCode": 404},
            }
        )
        first = groups.apply(lib)
        second = groups.apply(lib)
        self.assertEqual(sum(first.values()), 1)
        self.assertEqual(second, {})


class DataTest(unittest.TestCase):
    def test_cn_sites_are_valid(self) -> None:
        data = json.loads(Path(SITE_DATA_PATH).read_text(encoding="utf-8"))
        for name in ("Douban", "Bilibili", "Gitee", "V2EX", "Coolapk"):
            self.assertIn(name, data)
            self.assertEqual(validate_site(name, data[name]), [], name)

    def test_bilibili_uses_message_rule(self) -> None:
        data = json.loads(Path(SITE_DATA_PATH).read_text(encoding="utf-8"))
        info = data["Bilibili"]
        self.assertEqual(info["errorType"], "message")
        self.assertTrue(info["errorMsg"])


if __name__ == "__main__":
    unittest.main()
