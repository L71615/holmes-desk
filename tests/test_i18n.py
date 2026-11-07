"""i18n 单元测试：词表、回落、切换、分组名。"""

from __future__ import annotations

import unittest

from judgedee import i18n


class I18nTests(unittest.TestCase):
    def setUp(self) -> None:
        i18n.set_language("zh")

    def tearDown(self) -> None:
        i18n.set_language("zh")

    def test_default_is_chinese(self) -> None:
        self.assertEqual(i18n.current(), "zh")
        self.assertFalse(i18n.is_en())

    def test_t_returns_source_in_chinese(self) -> None:
        self.assertEqual(i18n.t("开始检索"), "开始检索")

    def test_t_translates_in_english(self) -> None:
        i18n.set_language("en")
        self.assertTrue(i18n.is_en())
        self.assertEqual(i18n.t("开始检索"), "Start")
        self.assertEqual(i18n.t("站点"), "Site")

    def test_unknown_text_passes_through(self) -> None:
        i18n.set_language("en")
        self.assertEqual(i18n.t("这句没有翻译"), "这句没有翻译")

    def test_empty_text(self) -> None:
        self.assertEqual(i18n.t(""), "")

    def test_t_group(self) -> None:
        self.assertEqual(i18n.t_group("常用"), "常用")
        i18n.set_language("en")
        self.assertEqual(i18n.t_group("常用"), "Common")
        self.assertEqual(i18n.t_group("不存在的组"), "不存在的组")

    def test_catalog_covers_core_labels(self) -> None:
        required = ["开始检索", "停止", "用户名", "导出报告", "身份分析", "图谱", "追踪", "站点库"]
        missing = [item for item in required if item not in i18n.CATALOG]
        self.assertEqual(missing, [])

    def test_set_language_ignores_unknown(self) -> None:
        i18n.set_language("fr")
        self.assertEqual(i18n.current(), "zh")


if __name__ == "__main__":
    unittest.main()
