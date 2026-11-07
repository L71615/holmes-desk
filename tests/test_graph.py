"""图谱与人工约束的测试：不联网，全部用合成数据。"""

import tempfile
import unittest
from pathlib import Path

from judgedee import graph
from judgedee.constraints import Constraints
from judgedee.identity import Account, MERGE_THRESHOLD, cluster_accounts


def make(username, site, display_name="", bio="", avatar_a=None, avatar_d=None, links=None, mentions=None):
    return Account(
        username=username,
        site=site,
        url=f"https://{site.lower().replace(' ', '')}.example/{username}",
        display_name=display_name,
        bio=bio,
        avatar_a=avatar_a,
        avatar_d=avatar_d,
        links=list(links or []),
        mentions=list(mentions or []),
    )


class ConstraintsTest(unittest.TestCase):
    def test_roundtrip_and_mutual_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "constraints.json"
            store = Constraints(path)
            store.add_must("GitHub|alice", "Reddit|alice")
            store.add_cannot("GitHub|alice", "Twitter|alice")
            store.save()

            again = Constraints(path)
            self.assertEqual(len(again), 2)
            self.assertIn(frozenset(("GitHub|alice", "Reddit|alice")), again.must)
            self.assertIn(frozenset(("GitHub|alice", "Twitter|alice")), again.cannot)

            # 同一对不能既是 must 又是 cannot
            again.add_must("GitHub|alice", "Twitter|alice")
            self.assertNotIn(frozenset(("GitHub|alice", "Twitter|alice")), again.cannot)
            self.assertIn(frozenset(("GitHub|alice", "Twitter|alice")), again.must)

    def test_remove_and_describe(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Constraints(Path(tmp) / "c.json")
            store.add_must("A|x", "B|x")
            self.assertEqual(len(store), 1)
            self.assertTrue(store.describe())
            store.remove("A|x", "B|x")
            self.assertEqual(len(store), 0)


class ClusterConstraintTest(unittest.TestCase):
    def test_must_link_forces_merge(self):
        a = make("alice", "GitHub", display_name="Alice")
        b = make("alice", "Reddit", display_name="Someone Else")
        # 默认不该合并：昵称不同、没有头像、没有互指
        clusters, _ = cluster_accounts([a, b])
        self.assertEqual(len(clusters), 2)

        clusters, _ = cluster_accounts([a, b], must={frozenset(("GitHub|alice", "Reddit|alice"))})
        self.assertEqual(len(clusters), 1)
        self.assertTrue(any("人工" in line for line in clusters[0].evidence))

    def test_cannot_link_blocks_merge(self):
        a = make("bob", "GitHub", display_name="Bob", avatar_a=0b1010, avatar_d=0b1111_0000)
        b = make("bob", "Reddit", display_name="Bob", avatar_a=0b1010, avatar_d=0b1111_0000)
        # 头像一致，正常会合并
        clusters, _ = cluster_accounts([a, b])
        self.assertEqual(len(clusters), 1)

        clusters, _ = cluster_accounts(
            [a, b], cannot={frozenset(("GitHub|bob", "Reddit|bob"))}
        )
        self.assertEqual(len(clusters), 2)


class GraphTest(unittest.TestCase):
    def test_build_edges_filters_weak(self):
        accounts = [
            make("carol", "GitHub", display_name="Carol"),
            make("carol", "Reddit", display_name="Totally Different"),
            make("dave", "GitHub", display_name="Dave", avatar_a=1, avatar_d=2),
        ]
        self.assertEqual(graph.build_edges(accounts), [])
        edges = graph.build_edges(accounts, min_score=0.0)
        self.assertEqual(len(edges), 3)

    def test_layout_deterministic_and_bounded(self):
        accounts = [
            make("eve", "GitHub", display_name="Eve", avatar_a=1, avatar_d=2),
            make("eve", "Reddit", display_name="Eve", avatar_a=1, avatar_d=2),
            make("eve", "GitLab", display_name="Eve"),
        ]
        edges = graph.build_edges(accounts, min_score=0.0)
        keys = [graph.account_key(account) for account in accounts]
        first = graph.layout(keys, edges, width=600, height=400, iterations=60)
        second = graph.layout(keys, edges, width=600, height=400, iterations=60)
        self.assertEqual(first, second)
        for x, y in first.values():
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x, 600)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y, 400)

    def test_single_node(self):
        keys = ["GitHub|solo"]
        pos = graph.layout(keys, [], width=400, height=300)
        self.assertIn("GitHub|solo", pos)
        self.assertEqual(graph.degrees(keys, [])["GitHub|solo"], 0.0)


if __name__ == "__main__":
    unittest.main()
