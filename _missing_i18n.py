import re
from pathlib import Path

from judgedee.i18n import CATALOG

missing: dict[str, set[str]] = {}
pattern = re.compile(r'i18n\.t\(\s*"([^"]+)"')
pattern_multi = re.compile(r'i18n\.t\(\s*\n\s*"([^"]+)"')

for path in sorted(Path("judgedee").rglob("*.py")):
    text = path.read_text(encoding="utf-8")
    keys = set(pattern.findall(text)) | set(pattern_multi.findall(text))
    miss = {k for k in keys if k not in CATALOG}
    if miss:
        missing[str(path)] = miss

total = 0
for path, keys in missing.items():
    print(f"=== {path}")
    for key in sorted(keys):
        print("   ", key)
    total += len(keys)
print("TOTAL MISSING", total)
