"""底线：基准账号解析 + 打分逻辑（不联网）。"""

from __future__ import annotations

import unittest

from judgedee import anchor
from judgedee.identity import Account

SITES = {
    "GitHub": {"urlMain": "https://github.com/", "url": "https://github.com/{}"},
    "GitLab": {"urlMain": "https://gitlab.com/", "url": "https://gitlab.com/{}"},
    "Reddit": {"urlMain": "https://www.reddit.com/", "url": "https://www.reddit.com/user/{}"},
}


def account(site: str, username: str, name: str = "", bio: str = "", avatar: int | None = None) -> Account:
    return Account(
        username=username,
        site=site,
        url=f"https://{site.lower()}.com/{username}",
        display_name=name,
        bio=bio,
        avatar_a=avatar,
        avatar_d=avatar,
        links=[],
    )


class ParseSeedTests(unittest.TestCase):
    def test_url_form(self) -> None:
        seed = anchor.parse_seed("https://github.com/L71615", SITES)
        self.assertEqual((seed.site, seed.username), ("GitHub", "L71615"))

    def test_url_form_with_www(self) -> None:
        seed = anchor.parse_seed("https://www.reddit.com/user/L71615", SITES)
        self.assertEqual((seed.site, seed.username), ("Reddit", "L71615"))

    def test_site_plus_username(self) -> None:
        seed = anchor.parse_seed("gitlab L71615", SITES)
        self.assertEqual((seed.site, seed.username), ("GitLab", "L71615"))
        self.assertEqual(seed.url, "https://gitlab.com/L71615")

    def test_bare_username_defaults_to_github(self) -> None:
        seed = anchor.parse_seed("L71615", SITES)
        self.assertEqual((seed.site, seed.username), ("GitHub", "L71615"))

    def test_unknown_site_raises(self) -> None:
        with self.assertRaises(ValueError):
            anchor.parse_seed("myspace L71615", SITES)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            anchor.parse_seed("   ", SITES)

    def test_url_without_site_raises(self) -> None:
        with self.assertRaises(ValueError):
            anchor.parse_seed("https://example.org/L71615", SITES)


class ScoreTests(unittest.TestCase):
    def test_identical_accounts_score_high(self) -> None:
        bio = "software engineer, writes go and python tools, weekend photographer"
        a = account("GitHub", "L71615", "Alex Zhang", bio, 0x0F0F)
        b = account("GitLab", "L71615", "Alex Zhang", bio, 0x0F0F)
        score, notes, strong = anchor.anchor_score(a, b)
        self.assertGreaterEqual(score, anchor.STRONG)
        self.assertTrue(strong)
        self.assertTrue(any("头像" in note for note in notes))

    def test_different_people_score_low(self) -> None:
        a = account("GitHub", "alice", "Alice", "摄影", 0x0000)
        b = account("Reddit", "bob", "Bob", "做饭", 0xFFFF)
        score, _notes, _strong = anchor.anchor_score(a, b)
        self.assertLess(score, anchor.REVIEW)

    def test_same_name_only_is_weak(self) -> None:
        a = account("GitHub", "alice", "Alice")
        b = account("Reddit", "alice", "Alice")
        score, _notes, strong = anchor.anchor_score(a, b)
        self.assertLess(score, anchor.STRONG)

    def test_same_username_counts_nothing_extra(self) -> None:
        a = account("GitHub", "alice")
        b = account("Reddit", "alice")
        score, _notes, _strong = anchor.anchor_score(a, b)
        self.assertLess(score, anchor.REVIEW)


class CandidateTests(unittest.TestCase):
    def test_dedupe_keeps_first(self) -> None:
        first = anchor.Candidate("GitHub", "L71615", "u1", anchor.SOURCE_SAME)
        second = anchor.Candidate("github ", "l71615", "u2", anchor.SOURCE_SAME)
        kept = anchor._dedupe([first, second], set())
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].url, "u1")

    def test_collect_candidates_with_fake_search(self) -> None:
        from judgedee.engine import QueryResult, QueryStatus

        def fake_search(username, site_data, **kwargs):
            if username == "L71615":
                return {
                    "GitHub": {
                        "status": QueryResult(
                            username=username, site_name="GitHub", site_url_user="https://github.com/L71615",
                            status=QueryStatus.CLAIMED,
                        ),
                        "url_user": "https://github.com/L71615",
                        "http_status": 200,
                    }
                }
            return {}

        seed = anchor.Seed("GitHub", "L71615", "https://github.com/L71615")
        candidates = anchor.collect_candidates(
            seed, SITES, on_progress=lambda _m: None, search_fn=fake_search
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source, anchor.SOURCE_SEED)
        self.assertEqual(candidates[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()
