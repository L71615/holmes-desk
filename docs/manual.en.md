# JudgeDee · full manual (EN)

[← Back to README](../README.en.md) · [中文手册](manual.md)

This is the long version: every page, every field, every knob. If you only want to run the app, the
[README](../README.en.md) is enough.

---

## 1. What the app is made of

| Module | Responsibility |
|---|---|
| `judgedee/engine.py` | Concurrent site checking: builds the URL, sends the request, classifies the answer |
| `judgedee/profile.py` | Fetches a profile page: nickname, bio, avatar (+ aHash/dHash), outbound links, deep pages |
| `judgedee/identity.py` | Scores account pairs and clusters them into persons |
| `judgedee/graph.py` | Edge building and the deterministic clustered layout |
| `judgedee/clues.py` | Clue cards: emails, IM handles, domains, IP and phone results |
| `judgedee/variants.py` | Derives username variants from nicknames |
| `judgedee/trace.py` | IP geolocation and offline phone parsing |
| `judgedee/export.py` | TXT / CSV / XLSX / JSONL / HTML (with embedded SVG graph) |
| `judgedee/sitelib.py` | Site library: groups, labels, enable/disable, custom sites |
| `judgedee/history.py` | SQLite history: runs, results, comparison |
| `judgedee/verify.py` | Re-checks claimed rows to filter false positives |
| `judgedee/i18n.py` | Chinese → English dictionary, `t()` / `t_group()` |
| `judgedee/config.py` | Config file with fallbacks and legacy migration |
| `judgedee/ui/` | Tkinter UI: six pages plus four dialogs |

Everything except `requests` (and the optional extras) ships with the app: the 481-site table, the
classification rules, the icons. No update check, no telemetry.

## 2. Install details

### Prebuilt exe

1. Download `JudgeDee.exe` from Releases and put it in any folder (avoid `C:\Program Files` if you
   want the config next to the exe).
2. Double-click. The launcher looks for `pythonw.exe` (3.10–3.13), starts `python -m judgedee`, and
   writes `judgedee-launcher.log` with the result.

### From source

```bash
python -m pip install -e .
python -m judgedee
```

`pip install -e .` also registers two console scripts: `judgedee` and `judgedee-gui`.

### Optional dependencies

| Extra | Install | Enables |
|---|---|---|
| `export` | `pip install -e ".[export]"` | XLSX export |
| `profile` | `pip install -e ".[profile]"` | Avatar hashing and comparison |
| `phone` | `pip install -e ".[phone]"` | Offline phone parsing |
| `all` | `pip install -e ".[all]"` | Everything above |

If `phonenumbers` is missing, the Trace page offers a one-click install that puts the library in
`<config>/vendor`, so your system Python stays untouched.

### Where files live

| Item | Default location |
|---|---|
| Config | `%APPDATA%\JudgeDee\config.json` |
| Site library overrides | `%APPDATA%\JudgeDee\sites_user.json` |
| History | `%APPDATA%\JudgeDee\history.db` |
| Manual constraints | `%APPDATA%\JudgeDee\constraints.json` |
| Avatar cache | `%APPDATA%\JudgeDee\avatars\` |
| Installed phone library | `%APPDATA%\JudgeDee\vendor\` |

If `%APPDATA%` is not writable, the app tries `%LOCALAPPDATA%`, then the folder next to the program,
then a temp directory. Set `JUDGEDEE_HOME` to force a location (portable mode): both the config and
the history will live there.

## 3. The Search page

### Inputs

- **Usernames** — one per run, or several separated by spaces / commas. `{?}` expands into three runs
  with `_`, `-` and `.`.
- **Site preset** — six presets (Common / Dev / Security / Social / Games / Media) or "All sites".
- **Extra sites** — free text, comma separated, exact site names as they appear in the site library.
- **Left tree** — tick whole groups or single sites. If something is ticked, the tree wins over the
  preset. Disabled sites are skipped.
- **Proxy** — `http://127.0.0.1:7897`, `socks5://...`. Empty means direct. The detected system proxy is
  pre-filled but you can clear it.
- **Timeout** — per request, 5–120 s, default 20.
- **Include NSFW** / **Show unregistered** — the second one keeps "available" rows in the table.
- **Self-check** — replaces the username with the one saved in Settings and masks personal fields on
  the persona board.
- **Deep profile** — follow up to 2 same-site links of each claimed profile and fold the text into the
  bio used for comparison.
- **Output folder** — where exports go; defaults to `results\` under the program folder.

### Actions

| Button | When it is enabled | What it does |
|---|---|---|
| Start | always | Runs the search |
| Stop | while running | Cancels; the queue is drained, no orphan threads |
| Open folder | after a run | Opens the export folder |
| Export report | after a run | Writes the report bundle |
| Re-verify | after claimed rows exist | Re-checks claimed rows with a fresh session |
| Analyze identity | after claimed rows exist | Fetches profiles, clusters accounts |
| Graph | after analysis | Switches to the Graph page |
| Aliases | when suggestions exist | Opens the rename dialog |
| Variant sweep | after analysis | Derives variants and runs another pass |
| Persona | after analysis | Opens the persona board |

### Status column

| Status | Rule |
|---|---|
| Claimed | HTTP 2xx/3xx and the page does not match the "not found" rule |
| Available | Matches the "not found" rule |
| Unknown | Neither rule matched (for example a redirect to a login page) |
| Illegal | The username is not allowed by that site's regex |
| WAF | A known firewall / captcha fingerprint was found in the response |

Three rule families are supported per site: `status_code` (with an `errorCode`), `message` (with an
`errorMsg` substring) and `response_url` (with an `errorUrl`).

## 4. Identity analysis

### What gets collected

For every claimed account the app fetches the profile page and tries, in order:

1. `og:title`, `og:description`, `og:image` meta tags;
2. `<title>`, first `<h1>`;
3. common bio containers (`<div class="bio">`, `[data-bio]`, `<meta name="description">`);
4. the largest near-square `<img>` on the page, for the avatar.

With **Deep profile** on, it also follows up to 2 same-site links (preferring paths that contain the
username, skipping navigation pages) and keeps up to 3000 characters of visible text per account.

### How pairs are scored

| Signal | Weight |
|---|---|
| Avatar similarity (aHash + dHash, Hamming distance) | 0.35 |
| Nickname similarity (normalised token overlap) | 0.20 |
| Bio overlap (Jaccard over words) | 0.20 |
| One-way link between profiles | 0.20 |
| Mutual links | 0.25 |
| Site affinity prior (dev/social/creative/game buckets) | 0.10 |
| Same username | 0.05–0.20, scaled by uniqueness |

Negative evidence: two different avatars (distance beyond the threshold) −0.40; different nicknames
with at least one empty bio −0.15.

### Clustering

1. Merge every must-link constraint from `constraints.json`.
2. Then repeatedly merge the highest-scoring pair, but only if that pair carries at least one strong
   signal (avatar ≥ 0.80, or mutual links, or a full one-way link). Average linkage — no chaining.
3. Pairs scoring 0.45–0.62 are listed in the review tab; they are never merged automatically.

### Manual corrections

On the Graph page, Ctrl-click two nodes, then choose **merge as same person** or **mark as different**.
The decision goes to `constraints.json` and the clustering is re-run immediately. **Clear this pair**
removes it.

## 5. The Graph page

- Nodes: accounts. Colour: person. Pale circle behind a group: one person, labelled "Person A · 2 accounts".
- Node radius grows with the consistency of the group.
- Edges: solid navy (strong), grey solid (0.45–0.62), faint dashed (weak). **Hide weak edges** hides
  everything below 0.45.
- Interaction: drag a node, wheel to zoom (0.4×–3.0×), right-drag to pan, double-click to open the
  profile, Ctrl-click for multi-select.
- Right panel: for the selection, the profile fields plus the pairwise scores with the evidence lines.

## 6. The Trace page

Two tabs.

**IP geolocation** — `ip-api.com` first (fields: status, message, query, country, countryCode, region,
regionName, city, zip, lat, lon, timezone, isp, org, as, mobile, proxy, hosting), falling back to
`ipinfo.io`. Invalid input is rejected locally with `ipaddress.ip_address`, so nothing leaves your
machine for a malformed IP.

**Phone number** — `phonenumbers` in offline mode. Output: number type, validity, format validity,
country, location, carrier, timezone, international format, national format, E.164, country code,
national number. Nine common default regions are offered; the default is CN.

**My IP** asks `api.ipify.org`, then immediately looks the answer up, so one click gives you both.

Neither tab writes to the history database.

## 7. Clues and the persona board

The persona board shows: account count, person count (and how many groups were merged), pending
confirmations, avatar count, category coverage (dev / social / creative / game / other), merged fields
(nicknames, emails, IM handles, personal domains), conflicting values, and a confidence score.

Confidence = 0.7 × average cluster consistency + 0.3 × category coverage, clamped to 5–99.

The **Clues** card lets you paste an IP or a phone number; the result is appended to the clue list and
also to the HTML report (`<section class="clues">`).

## 8. Exports

Each run writes into `results\<timestamp>\`:

| File | Content |
|---|---|
| `*.txt` | One line per hit |
| `*.csv` | `username, site, url_main, url_user, check_url, status, http_status, elapsed` |
| `*.jsonl` | One JSON object per result |
| `*.xlsx` | Same columns, needs pandas + openpyxl |
| `<ts>-report/*.html` | Report: summary cards, table, SVG graph, rename table, clue table |

The report fields are a superset of the run fields: `username, site, group, status, verdict, url_user,
http_status, response_time_s`, plus the person label.

## 9. Reviews and diffs

**Re-verify** re-checks only claimed rows; verdicts are `confirmed` (still claimed), `suspect` (now
available or illegal) and `unknown`. The verdict shows up in its own column.

**History → compare with the previous run** shows added / removed / still-there rows for claimed
accounts. Both ways are kept in the local SQLite database; deleting a run deletes its rows.

## 10. The site table

Each entry:

```json
{
  "GitHub": {
    "urlMain": "https://www.github.com/",
    "url": "https://www.github.com/{}",
    "urlProbe": "https://github.com/{}",
    "errorType": "status_code",
    "errorCode": 404,
    "regexCheck": "^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$",
    "isNSFW": false
  }
}
```

`url` must contain `{}`; `errorType` is one of `status_code`, `message`, `response_url`; for `message`
you need `errorMsg`, for `status_code` you may give an integer `errorCode`. Validation runs before a
custom site is saved, and errors are shown in the dialog.

## 11. Packaging

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

PyInstaller one-file build with `--add-data` for the site table and icons, `--collect-submodules
phonenumbers` and `--hidden-import phonenumbers` so phone parsing works out of the box. Result:
`dist\JudgeDee.exe`.

## 12. Command line

```bash
python -m judgedee                  # GUI
python -m judgedee --selftest       # start, then close after 1.5 s (smoke test)
python -m judgedee --version
python -m judgedee --install-shortcut
python -m judgedee --remove-shortcut
```

`--install-shortcut` compiles a small launcher with `csc.exe` (so the icon is embedded in the exe) and
creates a desktop shortcut plus a Start-menu entry.

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Double-click does nothing | Read `judgedee-launcher.log`; usually the config directory is not writable or Python is missing |
| Old UI opens | The shortcut points to an old exe; delete it and re-create from the current release |
| `PermissionError` at startup | Config fallback should handle it; if not, set `JUDGEDEE_HOME` to a writable folder |
| Phone tab says the library is missing | Click **install the phone library** on that tab |
| All rows "Unknown" | The site changed its page; use Sites → edit the rule, or re-verify |
| Graph looks empty | Only weak evidence exists; clear the filters or run Deep profile |

## 14. Limitations

- Avatar comparison needs Pillow; without it, only nicknames / bios / links are used.
- The site table is a snapshot; sites change their rules and the table ages.
- Clustering is evidence-based, not certain: always read the pairwise notes before trusting a merge.
- Proxy support is per-request; a broken proxy makes everything fail rather than falling back silently.

## 15. License

MIT — see [LICENSE](../LICENSE). Third-party data and its attribution live in [NOTICE](../NOTICE).
