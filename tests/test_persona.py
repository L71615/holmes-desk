"""人物看板：数量关系、类别覆盖、字段合并、摘要。"""

import unittest

from judgedee.identity import Account, Cluster
from judgedee.persona import build_persona, coverage


def account(site, username="alice", **kwargs):
    return Account(username=username, site=site, url=f"https://{site}/alice", **kwargs)


class CoverageTest(unittest.TestCase):
    def test_categories_are_ordered_and_complete(self):
        rows = coverage(["GitHub", "Reddit", "Steam Community (User)", "SomeUnknownSite"])
        self.assertEqual([r["label"] for r in rows], ["开发", "社交", "创作", "游戏", "其他"])
        self.assertEqual(rows[0]["sites"], ["GitHub"])
        self.assertEqual(rows[3]["count"], 1)
        self.assertEqual(rows[2]["count"], 0)


class PersonaTest(unittest.TestCase):
    def setUp(self):
        a = account("GitHub", display_name="Alice Zhang", bio="dev, mail alice@example.com", lang="en")
        b = account(
            "Reddit",
            display_name="Alice Z",
            links=["https://t.me/alicez", "https://alicezhang.dev"],
        )
        c = account("Steam Community (User)", display_name="Alice Zhang")
        self.accounts = [a, b, c]
        self.clusters = [
            Cluster(label="A", accounts=[a, c], score=0.72, evidence=["头像一致"]),
            Cluster(label="B", accounts=[b], score=0.55, evidence=[]),
        ]

    def test_counts(self):
        persona = build_persona(self.accounts, self.clusters)
        self.assertEqual(persona["account_count"], 3)
        self.assertEqual(persona["cluster_count"], 2)
        self.assertEqual(persona["multi_count"], 1)
        self.assertEqual(persona["single_count"], 1)
        self.assertEqual(persona["review_count"], 0)

    def test_headline_is_most_common_name(self):
        persona = build_persona(self.accounts, self.clusters)
        self.assertEqual(persona["headline"], "Alice Zhang")

    def test_fields_extracted(self):
        persona = build_persona(self.accounts, self.clusters)
        emails = [e for e, _ in persona["fields"]["emails"]]
        self.assertIn("alice@example.com", emails)
        ims = [i for i, _ in persona["fields"]["ims"]]
        self.assertTrue(any("alicez" in item for item in ims))
        domains = [d for d, _ in persona["fields"]["domains"]]
        self.assertIn("alicezhang.dev", domains)

    def test_conflicts_listed(self):
        persona = build_persona(self.accounts, self.clusters)
        fields = {item["field"] for item in persona["conflicts"]}
        self.assertIn("昵称", fields)  # Alice Zhang / Alice Z 不一致

    def test_confidence_in_range_and_summary(self):
        persona = build_persona(self.accounts, self.clusters)
        self.assertGreaterEqual(persona["confidence"], 5)
        self.assertLessEqual(persona["confidence"], 99)
        self.assertIn("3 个已注册账号", persona["summary"])
        self.assertIn("开发", persona["summary"])

    def test_empty(self):
        persona = build_persona([], [])
        self.assertEqual(persona["account_count"], 0)
        self.assertIn("没有已注册的账号", persona["summary"])


if __name__ == "__main__":
    unittest.main()
