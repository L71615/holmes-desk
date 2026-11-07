"""把状态筛选与提示行接进 i18n（中文原文当键）。"""

from __future__ import annotations

from pathlib import Path

path = Path("judgedee/ui/page_search.py")
text = path.read_text(encoding="utf-8")

pairs = [
    (
        "values=list(STATUS_FILTERS)",
        "values=[i18n.t(name) for name in STATUS_FILTERS]",
    ),
    ('self.cmb_status.set("全部")', "self.cmb_status.current(0)"),
    (
        'wanted = STATUS_FILTERS.get(self.cmb_status.get(), None)',
        "index = self.cmb_status.current()\n"
        "        wanted = list(STATUS_FILTERS.values())[index] if index >= 0 else None",
    ),
    (
        'card, text="多个用户名用空格或逗号分隔；填 {?} 会自动展开成 _ - . 三种变体",',
        'card, text=i18n.t("多个用户名用空格或逗号分隔；填 {?} 会自动展开成 _ - . 三种变体"),',
    ),
]

for old, new in pairs:
    if old not in text:
        raise SystemExit(f"missing: {old[:60]}")
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("patched status filter + hint")
