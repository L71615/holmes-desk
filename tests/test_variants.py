"""用户名变体生成。"""

import unittest

from holmes_desk import variants


class VariantTest(unittest.TestCase):
    def test_split_username_variants(self):
        out = {v.username for v in variants.generate(["alice_zhang"])}
        self.assertIn("alicezhang", out)
        self.assertIn("alice.zhang", out)
        self.assertIn("alice-zhang", out)
        self.assertNotIn("alice_zhang", out)  # 原始用户名不重复出现

    def test_display_name_variants(self):
        out = {v.username for v in variants.generate([], ["Alice Zhang"])}
        self.assertIn("azhang", out)
        self.assertIn("alicez", out)
        self.assertIn("zhangalice", out)

    def test_chinese_name_is_skipped(self):
        self.assertEqual(variants.generate([], ["张小明"]), [])

    def test_dedupes_and_honours_limit(self):
        out = variants.generate(["alice_zhang", "alicezhang"], limit=5)
        self.assertLessEqual(len(out), 5)
        names = [v.username for v in out]
        self.assertEqual(len(names), len(set(names)))

    def test_rejects_too_short_and_odd(self):
        names = {v.username for v in variants.generate(["ab"])}
        self.assertTrue(all(len(n) >= 3 for n in names))

    def test_describe(self):
        got = variants.describe([])
        self.assertIn("没有", got)
        text = variants.describe(variants.generate(["alice_zhang"]))
        self.assertIn("alice", text)


if __name__ == "__main__":
    unittest.main()
