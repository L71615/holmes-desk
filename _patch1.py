from pathlib import Path

p = Path("judgedee/ui/app.py")
t = p.read_text(encoding="utf-8")
pairs = [
    (
        'text=f"本地单机 · v{__version__}"',
        'text=f"{i18n.t(\'本地单机\')} · v{__version__}"',
    ),
    (
        'self.lbl_status = ttk.Label(status, text="就绪", style="Status.TLabel")',
        'self.lbl_status = ttk.Label(status, text=i18n.t("就绪"), style="Status.TLabel")',
    ),
    (
        'side, text=label, style="Nav.TButton"',
        'side, text=nav_label(key, label), style="Nav.TButton"',
    ),
]
for old, new in pairs:
    assert old in t, old
    t = t.replace(old, new)
p.write_text(t, encoding="utf-8")
print("app.py patched")
