import re
from pathlib import Path

for name in ("page_search", "page_trace", "page_graph", "page_settings", "page_sites", "page_history"):
    path = Path("judgedee/ui") / f"{name}.py"
    text = path.read_text(encoding="utf-8")
    values = sorted(set(re.findall(r'text="([^"]+)"', text)))
    print(f"=== {name} ({len(values)})")
    for value in values:
        print("   ", value)
