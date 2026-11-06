"""跨次对比：新增 / 消失 / 仍在。"""

import tempfile
import unittest
from pathlib import Path

from holmes_desk.history import History


def rows(sites, status="claimed"):
    return [
        {"username": "alice", "site": site, "status": status, "url": f"https://{site}.example/alice"}
        for site in sites
    ]


class CompareTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hist = History(Path(self._tmp.name) / "history.db")

    def tearDown(self):
        self.hist.close()
        self._tmp.cleanup()

    def test_added_and_removed(self):
        first = self.hist.add_run(["alice"], rows(["GitHub", "Reddit"]), elapsed=1.0)
        second = self.hist.add_run(["alice"], rows(["GitHub", "GitLab"]), elapsed=1.2)
        diff = self.hist.compare(second)
        self.assertIsNotNone(diff)
        self.assertEqual(diff["right"]["id"], first)
        self.assertEqual([row["site"] for row in diff["added"]], ["GitLab"])
        self.assertEqual([row["site"] for row in diff["removed"]], ["Reddit"])
        self.assertEqual([row["site"] for row in diff["kept"]], ["GitHub"])

    def test_available_rows_do_not_count(self):
        self.hist.add_run(["bob"], rows(["GitHub"]))
        second = self.hist.add_run(
            ["bob"],
            rows(["GitHub"], status="available") + rows(["GitLab"]),
            elapsed=0.5,
        )
        diff = self.hist.compare(second)
        self.assertEqual([row["site"] for row in diff["added"]], ["GitLab"])
        self.assertEqual([row["site"] for row in diff["removed"]], ["GitHub"])

    def test_previous_run_prefers_same_usernames(self):
        self.hist.add_run(["carol"], rows(["GitHub"]))
        other = self.hist.add_run(["dave"], rows(["Reddit"]))
        latest = self.hist.add_run(["carol"], rows(["GitHub", "GitLab"]))
        prev = self.hist.previous_run(latest)
        self.assertEqual(prev["usernames"], "carol")
        self.assertNotEqual(prev["id"], other)

    def test_first_run_has_nothing_to_compare(self):
        only = self.hist.add_run(["erin"], rows(["GitHub"]))
        self.assertIsNone(self.hist.compare(only))

    def test_explicit_baseline(self):
        first = self.hist.add_run(["frank"], rows(["GitHub"]))
        self.hist.add_run(["frank"], rows(["GitHub", "Reddit"]))
        third = self.hist.add_run(["frank"], rows(["GitLab"]))
        diff = self.hist.compare(third, first)
        self.assertEqual([row["site"] for row in diff["added"]], ["GitLab"])
        self.assertEqual([row["site"] for row in diff["removed"]], ["GitHub"])


if __name__ == "__main__":
    unittest.main()
