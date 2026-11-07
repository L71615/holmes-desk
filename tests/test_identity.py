"""身份聚类的单元测试：全部用合成数据，不联网。"""

import unittest

from judgedee.identity import (
    MERGE_THRESHOLD,
    Account,
    bio_similarity,
    cluster_accounts,
    name_similarity,
    normalize_name,
    score_pair,
    uniqueness,
)


def acct(site, username="alex", **kwargs):
    base = dict(username=username, site=site, url=f"https://{site.lower()}.example/{username}")
    base.update(kwargs)
    return Account(**base)


class UniquenessTest(unittest.TestCase):
    def test_common_name_is_weak(self):
        self.assertLess(uniqueness("alex"), uniqueness("alex_kovacs_1993"))

    def test_bounds(self):
        for name in ("", "a", "x" * 40, "A_b-9.x"):
            value = uniqueness(name)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class NameSimilarityTest(unittest.TestCase):
    def test_normalize_strips_emoji_and_case(self):
        self.assertEqual(normalize_name("Alex 🚀 K."), "alex k")

    def test_identical(self):
        self.assertAlmostEqual(name_similarity("Alex Kovacs", "alex kovacs"), 1.0)

    def test_containment(self):
        self.assertGreater(name_similarity("alex", "alex kovacs"), 0.5)

    def test_unrelated(self):
        self.assertLess(name_similarity("alex", "zzq"), 0.3)


class BioSimilarityTest(unittest.TestCase):
    def test_overlap(self):
        left = "backend engineer building databases and distributed systems"
        right = "backend engineer; likes distributed systems and databases"
        self.assertGreater(bio_similarity(left, right), 0.4)

    def test_too_short_returns_none(self):
        self.assertIsNone(bio_similarity("hi", "there friend"))


class ScorePairTest(unittest.TestCase):
    def test_same_username_alone_does_not_merge(self):
        left = acct("GitHub")
        right = acct("Reddit")
        pair = score_pair(left, right)
        self.assertLess(pair.score, MERGE_THRESHOLD)
        self.assertFalse(pair.strong)

    def test_same_avatar_merges(self):
        left = acct("GitHub", display_name="Alex K", avatar_a=0b1010_1010_1010_1010, avatar_d=0x00FF)
        right = acct("Reddit", display_name="Alex K", avatar_a=0b1010_1010_1010_1010, avatar_d=0x00FF)
        pair = score_pair(left, right)
        self.assertGreaterEqual(pair.score, MERGE_THRESHOLD)
        self.assertTrue(pair.strong)

    def test_different_avatar_is_negative_evidence(self):
        left = acct("GitHub", display_name="Alex", avatar_a=0xFFFF_FFFF_FFFF_FFFF, avatar_d=0xFFFF)
        right = acct("Reddit", display_name="Alex", avatar_a=0, avatar_d=0)
        pair = score_pair(left, right)
        self.assertLess(pair.score, 0.3)

    def test_mutual_mention_scores_high(self):
        left = acct("GitHub", "alex", bio="also at reddit", mentions=["alex_r"])
        right = acct("Reddit", "alex_r", bio="github: alex", mentions=["alex"])
        pair = score_pair(left, right)
        self.assertGreater(pair.score, MERGE_THRESHOLD)
        self.assertTrue(pair.strong)


class ClusterTest(unittest.TestCase):
    def test_avatar_splits_two_people(self):
        same_a, same_d = 0b1111_0000_1111_0000, 0x00FF
        other_a, other_d = 0b0000_1111_0000_1111, 0xFF00
        accounts = [
            acct("GitHub", "alex", display_name="Alex K", avatar_a=same_a, avatar_d=same_d),
            acct("Reddit", "alex", display_name="Alex K", avatar_a=same_a, avatar_d=same_d),
            acct("TikTok", "alex", display_name="Sam", avatar_a=other_a, avatar_d=other_d),
        ]
        clusters, review = cluster_accounts(accounts)
        self.assertEqual(len(clusters), 2)
        sizes = sorted(c.size for c in clusters)
        self.assertEqual(sizes, [1, 2])
        self.assertEqual(clusters[0].label, "A")
        self.assertTrue(clusters[0].evidence)
        self.assertIsInstance(review, list)

    def test_single_account(self):
        clusters, review = cluster_accounts([acct("GitHub")])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].label, "A")
        self.assertEqual(review, [])

    def test_empty(self):
        self.assertEqual(cluster_accounts([]), ([], []))


if __name__ == "__main__":
    unittest.main()
