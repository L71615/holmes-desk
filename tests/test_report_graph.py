"""报告里的图谱与「换名同人」：不联网，全部合成数据。"""

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from judgedee.export import export_report, write_report_html
from judgedee.identity import REVIEW_THRESHOLD, Account, alias_candidates


def make(username, site, display_name="", bio="", avatar_a=None, avatar_d=None, links=None):
    return Account(
        username=username,
        site=site,
        url=f"https://{site.lower().replace(' ', '')}.example/{username}",
        display_name=display_name,
        bio=bio,
        avatar_a=avatar_a,
        avatar_d=avatar_d,
        links=list(links or []),
    )


def rows_for(accounts):
    return [
        {
            "username": account.username,
            "site": account.site,
            "group": "常用",
            "status": "已注册",
            "status_key": "claimed",
            "verdict": "复核通过",
            "url_user": account.url,
            "http_status": 200,
            "response_time_s": 1.2,
            "identity": "",
        }
        for account in accounts
    ]


class AliasTest(unittest.TestCase):
    def test_same_username_is_not_alias(self):
        a = make("alice", "GitHub", display_name="Alice", avatar_a=7, avatar_d=9)
        b = make("alice", "Reddit", display_name="Alice", avatar_a=7, avatar_d=9)
        self.assertEqual(alias_candidates([a, b]), [])

    def test_different_username_with_strong_evidence(self):
        a = make("alice", "GitHub", display_name="Alice Zhang", avatar_a=7, avatar_d=9)
        b = make("a.zhang", "Reddit", display_name="Alice Zhang", avatar_a=7, avatar_d=9)
        candidates = alias_candidates([a, b])
        self.assertEqual(len(candidates), 1)
        self.assertGreaterEqual(candidates[0]["score"], REVIEW_THRESHOLD)
        self.assertEqual(candidates[0]["a_username"], "alice")
        self.assertEqual(candidates[0]["b_username"], "a.zhang")

    def test_weak_pair_is_skipped(self):
        a = make("bob", "GitHub", display_name="Bob")
        b = make("bobby", "Reddit", display_name="Completely Different")
        self.assertEqual(alias_candidates([a, b]), [])


class ReportGraphTest(unittest.TestCase):
    def test_html_contains_svg_and_edges(self):
        accounts = [
            make("carol", "GitHub", display_name="Carol", avatar_a=3, avatar_d=5),
            make("carol", "Reddit", display_name="Carol", avatar_a=3, avatar_d=5),
            make("carol", "GitLab", display_name="Carol Q"),
        ]
        identity = {"accounts": accounts, "clusters": [], "review": []}

        # 直接用 identity 里的账号聚类，得到的档案用来上色
        from judgedee.identity import cluster_accounts

        clusters, review = cluster_accounts(accounts)
        identity["clusters"] = clusters
        identity["review"] = review

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.html"
            write_report_html(target, "carol", rows_for(accounts), identity=identity)
            text = target.read_text(encoding="utf-8")
            self.assertIn("<svg", text)
            self.assertIn("身份图谱", text)
            self.assertIn('class="edge strong"', text)
            self.assertIn("carol", text)

    def test_export_report_passes_identity_to_html_only(self):
        accounts = [
            make("dave", "GitHub", display_name="Dave", avatar_a=1, avatar_d=2),
            make("dave", "Reddit", display_name="Dave", avatar_a=1, avatar_d=2),
        ]
        from judgedee.identity import cluster_accounts

        clusters, review = cluster_accounts(accounts)
        identity = {"accounts": accounts, "clusters": clusters, "review": review}

        with tempfile.TemporaryDirectory() as tmp:
            written, errors = export_report(
                Path(tmp), "dave", rows_for(accounts), ["html", "csv"], identity=identity
            )
            self.assertEqual(errors, [])
            names = sorted(path.name for path in written)
            self.assertEqual(names, ["dave.csv", "dave.html"])
            html_text = (Path(tmp) / "dave.html").read_text(encoding="utf-8")
            self.assertIn("<svg", html_text)

    def test_svg_is_well_formed(self):
        accounts = [
            make("frank", "GitHub", display_name="Frank", avatar_a=11, avatar_d=13),
            make("frank", "Reddit", display_name="Frank", avatar_a=11, avatar_d=13),
            make("frank", "GitLab", display_name="Frank"),
        ]
        from judgedee.identity import cluster_accounts

        clusters, review = cluster_accounts(accounts)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ok.html"
            write_report_html(
                target,
                "frank",
                rows_for(accounts),
                identity={"accounts": accounts, "clusters": clusters, "review": review},
            )
            text = target.read_text(encoding="utf-8")

        start = text.index("<svg")
        end = text.index("</svg>") + len("</svg>")
        element = ElementTree.fromstring(text[start:end])
        ns = "{http://www.w3.org/2000/svg}"
        self.assertEqual(element.tag, f"{ns}svg")
        self.assertEqual(len(element.findall(f".//{ns}circle")), 3)
        self.assertGreaterEqual(len(element.findall(f".//{ns}line")), 1)
        self.assertEqual(len(element.findall(f".//{ns}text")), 3)

    def test_report_without_identity_has_no_svg(self):
        accounts = [make("erin", "GitHub", display_name="Erin")]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "plain.html"
            write_report_html(target, "erin", rows_for(accounts))
            self.assertNotIn("<svg", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
