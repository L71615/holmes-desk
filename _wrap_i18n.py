"""把 UI 里的中文 text="..." 包成 i18n.t(...)，并补齐中文文件头 import。"""

from __future__ import annotations

import re
from pathlib import Path

TARGETS = [
    "page_search",
    "page_trace",
    "page_graph",
    "page_settings",
    "page_sites",
    "page_history",
    "dialog_identity",
    "dialog_persona",
    "dialog_alias",
    "dialog_compare",
]

PATTERN = re.compile(r'(text=)"([^"{}]+)"')

for name in TARGETS:
    path = Path("judgedee/ui") / f"{name}.py"
    text = path.read_text(encoding="utf-8")
    if "i18n.t(" in text:
        print(f"skip (already wrapped): {name}")
        continue
    new_text, count = PATTERN.subn(r'\1i18n.t("\2")', text)
    if count == 0:
        print(f"no text= found: {name}")
        continue
    if "from .. import i18n" not in new_text and "from ..i18n" not in new_text:
        # 插到第一个 "from .." 之前，保证相对导入顺序不乱
        match = re.search(r"^from \.\..*$", new_text, re.M)
        if match:
            new_text = (
                new_text[: match.start()] + "from .. import i18n\n" + new_text[match.start() :]
            )
        else:
            match = re.search(r"^from \.\s.*$", new_text, re.M)
            new_text = (
                new_text[: match.start()] + "from .. import i18n\n" + new_text[match.start() :]
                if match
                else new_text
            )
    path.write_text(new_text, encoding="utf-8")
    print(f"{name}: wrapped {count} strings")
