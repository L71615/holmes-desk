"""站点预设。

站点表里有 481 个站点，全量跑一轮既慢又吵。这里给出几组常用预设，
界面上的下拉框选一个就能把"站点"输入框填好，也可以自己再改。
"""

from __future__ import annotations

PRESETS: dict[str, list[str]] = {
    "常用（25 站）": [
        "GitHub", "GitLab", "Twitter", "Instagram", "Reddit", "Telegram", "Discord",
        "TikTok", "YouTube", "Pinterest", "LinkedIn", "Steam Community (User)",
        "Twitch", "Medium", "VK", "Bluesky", "Tumblr", "Snapchat", "HackerNews",
        "Keybase", "Gravatar", "Linktree", "About.me", "Spotify", "SoundCloud",
    ],
    "开发 / 代码": [
        "GitHub", "GitLab", "Gitee", "BitBucket", "Codeberg", "SourceForge",
        "Docker Hub", "npm", "PyPi", "Packagist", "RubyGems", "Hugging Face",
        "Kaggle", "LeetCode", "Codeforces", "Codechef", "Atcoder", "HackerRank",
        "HackerEarth", "Topcoder", "Codewars", "Replit.com", "CodeSandbox",
        "DEV Community", "Hashnode", "devRant", "Codepen", "GeeksforGeeks",
        "GitBook", "Wakatime", "Launchpad", "Arduino Forum",
    ],
    "安全 / CTF": [
        "HackTheBox", "TryHackMe", "HackerOne", "BugCrowd", "Intigriti",
        "HackenProof (Hackers)", "CryptoHack", "PentesterLab", "CyberDefenders",
        "VirusTotal", "HudsonRock", "Splits.io", "Hackaday", "HackerSploit",
    ],
    "社交 / 社区": [
        "Twitter", "Instagram", "Reddit", "Telegram", "Discord", "TikTok",
        "Snapchat", "Pinterest", "Tumblr", "VK", "Bluesky", "mastodon.social",
        "LemmyWorld", "HackerNews", "9GAG", "Clubhouse", "Vero", "SpaceHey",
        "MySpace", "About.me", "Linktree", "Carrd", "Substack", "Lobsters", "Slashdot",
    ],
    "游戏": [
        "Steam Community (User)", "Steam Community (Group)", "Roblox", "Minecraft",
        "osu!", "Xbox Gamertag", "PSNProfiles.com", "RuneScape", "Warframe Market",
        "Newgrounds", "Kongregate", "Chess", "Lichess", "Playstrategy", "FortniteTracker",
    ],
    "影音 / 创作": [
        "YouTube", "Vimeo", "SoundCloud", "Spotify", "Bandcamp", "MixCloud", "Flickr",
        "DeviantArt", "Behance", "Dribbble", "ArtStation", "Unsplash", "Wattpad",
        "Archive of Our Own", "Letterboxd", "last.fm", "Sketchfab", "LottieFiles",
    ],
}


def preset_text(name: str) -> str:
    """把预设转成站点输入框里的逗号分隔文本。"""
    return ", ".join(PRESETS.get(name, []))


def preset_names() -> list[str]:
    """下拉框选项（含一个"全部"）。"""
    return ["全部站点", *PRESETS.keys()]
