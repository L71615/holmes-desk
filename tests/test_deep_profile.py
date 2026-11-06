"""深入抓取（跟进主页里的同站链接）相关的测试：全部离线，不联网。"""

from __future__ import annotations

import unittest

from holmes_desk.graph import cluster_layout
from holmes_desk.identity import Account, Cluster
from holmes_desk.profile import _pick_links, _visible_text, fetch_one

MAIN_PAGE = """
<html lang="zh-CN"><head>
<title>L71615 · 主页</title>
<meta property="og:title" content="L71615">
<meta property="og:description" content="写代码，也写点别的">
</head>
<body>
<div class="user-bio">独立开发者，做过几个小工具</div>
<a href="/L71615/about">关于我</a>
<a href="/L71615/repos">仓库</a>
<a href="https://example.com/blog">博客</a>
</body></html>
"""

ABOUT_PAGE = """
<html><head><style>.x{color:red}</style><script>var a = 1;</script></head>
<body><h1>关于我</h1><p>我叫林，做后端和一点图形，常用邮箱 lin@example.com。
平时写 Go 和 Python，也折腾过一点点前端，偶尔在周报里记录踩坑。</p></body></html>
"""

REPOS_PAGE = """
<html><body><h1>仓库</h1>
<p>这里放我自己写的小工具：一个把身份证号打码的脚本，一个批量重命名照片的小程序，
还有一个用来自动整理下载目录的工具，代码都很短，加起来不到两千行。</p></body></html>
"""


class FakeResponse:
    def __init__(self, url: str, text: str, status: int = 200) -> None:
        self.url = url
        self.status_code = status
        self.encoding = "utf-8"
        self._body = text.encode("utf-8")

    def iter_content(self, chunk_size: int = 65536):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


class FakeSession:
    """按 URL 返回预置页面，并记录抓过哪些地址。"""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.calls.append(url)
        text = self.pages.get(url)
        if text is None:
            return FakeResponse(url, "", status=404)
        return FakeResponse(url, text)


class VisibleTextTest(unittest.TestCase):
    def test_strips_script_and_style(self) -> None:
        text = _visible_text(ABOUT_PAGE)
        self.assertIn("关于我", text)
        self.assertNotIn("var a = 1", text)
        self.assertNotIn("color:red", text)

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(_visible_text("<p>a   b</p>\n\n<p>c</p>"), "a b c")


class PickLinksTest(unittest.TestCase):
    def test_keeps_same_host_hrefs(self) -> None:
        _domains, _texts, hrefs = _pick_links(MAIN_PAGE, "https://x.test/L71615", "x.test")
        self.assertIn("https://x.test/L71615/about", hrefs)
        self.assertNotIn("https://example.com/blog", hrefs)

    def test_skips_anchors(self) -> None:
        page = '<a href="#top">top</a><a href="/a">a</a>'
        _domains, _texts, hrefs = _pick_links(page, "https://x.test/u", "x.test")
        self.assertEqual(hrefs, ["https://x.test/a"])


class FetchOneTest(unittest.TestCase):
    def test_deep_follows_same_host_links(self) -> None:
        session = FakeSession(
            {
                "https://x.test/L71615": MAIN_PAGE,
                "https://x.test/L71615/about": ABOUT_PAGE,
                "https://x.test/L71615/repos": REPOS_PAGE,
            }
        )
        profile = fetch_one(session, "L71615", "X", "https://x.test/L71615", deep=True, max_pages=2)
        self.assertTrue(profile.ok)
        self.assertEqual(
            profile.extra_pages,
            ["https://x.test/L71615/about", "https://x.test/L71615/repos"],
        )
        self.assertIn("写代码", profile.bio)
        self.assertIn("lin@example.com", profile.extra_text)

    def test_shallow_does_not_follow(self) -> None:
        session = FakeSession({"https://x.test/L71615": MAIN_PAGE})
        profile = fetch_one(session, "L71615", "X", "https://x.test/L71615")
        self.assertEqual(profile.extra_pages, [])
        self.assertEqual(len(session.calls), 1)

    def test_deep_respects_max_pages(self) -> None:
        session = FakeSession(
            {
                "https://x.test/L71615": MAIN_PAGE,
                "https://x.test/L71615/about": ABOUT_PAGE,
                "https://x.test/L71615/repos": REPOS_PAGE,
            }
        )
        profile = fetch_one(session, "L71615", "X", "https://x.test/L71615", deep=True, max_pages=1)
        self.assertEqual(len(profile.extra_pages), 1)

    def test_404_page_is_skipped(self) -> None:
        session = FakeSession({"https://x.test/L71615": MAIN_PAGE})
        profile = fetch_one(session, "L71615", "X", "https://x.test/L71615", deep=True, max_pages=2)
        self.assertEqual(profile.extra_pages, [])


class ClusterLayoutTest(unittest.TestCase):
    def _clusters(self) -> list[Cluster]:
        a1 = Account(username="L71615", site="GitHub", url="https://github.com/L71615")
        a2 = Account(username="L71615", site="GitLab", url="https://gitlab.com/L71615")
        b1 = Account(username="L71615", site="Reddit", url="https://reddit.com/user/L71615")
        c1 = Account(username="L71615", site="Keybase", url="https://keybase.io/L71615")
        return [
            Cluster(label="A", accounts=[a1, a2], score=0.7, evidence=["头像相似"]),
            Cluster(label="B", accounts=[b1], score=0.0, evidence=[]),
            Cluster(label="C", accounts=[c1], score=0.0, evidence=[]),
        ]

    def test_every_account_gets_a_point(self) -> None:
        pos = cluster_layout(self._clusters(), width=1000.0, height=700.0)
        self.assertEqual(len(pos), 4)

    def test_points_stay_inside_canvas(self) -> None:
        pos = cluster_layout(self._clusters(), width=1000.0, height=700.0)
        for x, y in pos.values():
            self.assertGreater(x, 0)
            self.assertLess(x, 1000)
            self.assertGreater(y, 0)
            self.assertLess(y, 700)

    def test_single_cluster_spreads_out(self) -> None:
        account = Account(username="L71615", site="GitHub", url="https://github.com/L71615")
        two = [account, Account(username="L71615", site="GitLab", url="https://gitlab.com/L71615")]
        pos = cluster_layout([Cluster(label="A", accounts=two, score=0.6, evidence=[])], 1000.0, 700.0)
        (x1, y1), (x2, y2) = pos["GitHub|L71615"], pos["GitLab|L71615"]
        self.assertGreater(abs(x1 - x2) + abs(y1 - y2), 50)

    def test_points_are_distinct(self) -> None:
        pos = cluster_layout(self._clusters(), width=1000.0, height=700.0)
        points = list(pos.values())
        for i, first in enumerate(points):
            for second in points[i + 1 :]:
                self.assertGreater(abs(first[0] - second[0]) + abs(first[1] - second[1]), 1.0)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(cluster_layout([], 1000.0, 700.0), {})


if __name__ == "__main__":
    unittest.main()
