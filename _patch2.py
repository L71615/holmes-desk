"""补 app.py / page_search.py 的动态文案。"""

from __future__ import annotations

from pathlib import Path

app_path = Path("judgedee/ui/app.py")
app_text = app_path.read_text(encoding="utf-8")
app_old = 'header, text=__app_name_zh__, bg=theme.HEADER, fg="white",'
app_new = 'header, text=i18n.t(__app_name_zh__), bg=theme.HEADER, fg="white",'
assert app_old in app_text
app_path.write_text(app_text.replace(app_old, app_new), encoding="utf-8")

path = Path("judgedee/ui/page_search.py")
text = path.read_text(encoding="utf-8")
pairs = [
    (
        "self.tree.heading(key, text=label, anchor=anchor)",
        "self.tree.heading(key, text=i18n.t(label), anchor=anchor)",
    ),
    (
        'text=f"{mark} {group}（{picked}/{len(members)}）",',
        'text=f"{mark} {i18n.t_group(group)}（{picked}/{len(members)}）",',
    ),
    (
        'self.lbl_checked.configure(text=f"已选 {len(self.checked)} 站")',
        'self.lbl_checked.configure(text=f"{i18n.t(\'已选\')} {len(self.checked)} {i18n.t(\'站\')}")',
    ),
]
for old, new in pairs:
    assert old in text, old
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("patched app.py + page_search.py")
