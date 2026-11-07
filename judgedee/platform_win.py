"""Windows 相关的小工具：DPI 感知、系统代理、桌面快捷方式。"""

from __future__ import annotations

import ctypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import app_dir

SHORTCUT_NAME = "JudgeDee 人物情报.lnk"


def enable_dpi_awareness() -> None:
    """按真实像素渲染，避免 200% 缩放屏上整窗被位图拉伸发虚。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def detect_system_proxy() -> str:
    """读取 Windows 系统代理；端口探活成功才返回，避免填一个死地址。"""
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if not enabled or not server:
            return ""
        host, _, port = server.partition(":")
        host = host or "127.0.0.1"
        port = int(port or 80)
        with socket.create_connection((host, port), timeout=0.4):
            return f"http://{host}:{port}"
    except Exception:  # noqa: BLE001
        return ""


def open_path(path: str | Path) -> None:
    """在资源管理器里打开目录（跨平台兜底）。"""
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


def pythonw_path() -> str:
    """找到 pythonw.exe，避免启动时弹黑框。"""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else str(exe)


def _csc_path() -> str | None:
    root = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for rel in (r"Microsoft.NET\Framework64\v4.0.30319\csc.exe", r"Microsoft.NET\Framework\v4.0.30319\csc.exe"):
        candidate = root / rel
        if candidate.exists():
            return str(candidate)
    return shutil.which("csc")


def build_launcher(icon: Path, out_exe: Path) -> Path | None:
    """用 csc 把 build/launcher.cs 编译成带图标的 exe 启动器。

    Windows 对 .lnk 的图标覆盖并不可靠（只认目标 exe 内嵌的资源），
    所以源码模式下也编译一个 exe 出来，快捷方式指向它才有正常图标。
    """
    csc = _csc_path()
    source = app_dir() / "build" / "launcher.cs"
    if not csc or not source.exists():
        return None
    try:
        subprocess.run(
            [
                csc,
                "/nologo",
                "/target:winexe",
                "/r:System.Windows.Forms.dll",
                f"/win32icon:{icon}",
                f"/out:{out_exe}",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception:  # noqa: BLE001
        return None
    return out_exe if out_exe.exists() else None


def _start_menu_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", "")) / "Desktop"


_PS_TEMPLATE = """
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut("{lnk}")
$link.TargetPath = "{target}"
$link.Arguments = "{args}"
$link.WorkingDirectory = "{workdir}"
$link.IconLocation = "{icon}"
$link.Description = "JudgeDee 用户名检索"
$link.Save()
"""


def _make_lnk(lnk: Path, target: str, args: str, workdir: str, icon: str) -> None:
    script = _PS_TEMPLATE.format(
        lnk=str(lnk).replace('"', "'"),
        target=target.replace('"', "'"),
        args=args.replace('"', "'"),
        workdir=workdir.replace('"', "'"),
        icon=icon.replace('"', "'"),
    )
    # 必须带 BOM：Windows PowerShell 5.1 默认按 ANSI 读 .ps1，中文路径会乱码
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ps1", delete=False, encoding="utf-8-sig"
    ) as fh:
        fh.write(script)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or f"powershell 退出码 {proc.returncode}")
    finally:
        Path(tmp).unlink(missing_ok=True)


def install_shortcut(icon: Path, name: str = SHORTCUT_NAME) -> dict[str, object]:
    """在桌面和开始菜单创建快捷方式。

    打包模式下直接指向 JudgeDee.exe；源码模式编译一个带图标的启动器 exe，
    失败才退回 pythonw.exe + .lnk 图标（图标可能显示为通用图标）。
    """
    workdir = str(app_dir())
    if getattr(sys, "frozen", False):
        target, args, icon_ref = sys.executable, "", sys.executable + ",0"
    else:
        launcher = build_launcher(icon, app_dir() / "JudgeDee.exe")
        if launcher is not None:
            target, args, icon_ref = str(launcher), "", str(launcher) + ",0"
        else:
            target, args, icon_ref = pythonw_path(), "-m judgedee", str(icon) + ",0"

    created: list[str] = []
    errors: list[str] = []
    for folder in {_desktop_dir(), _start_menu_dir()}:
        if not folder.exists():
            continue
        lnk = folder / name
        try:
            _make_lnk(lnk, target, args, workdir, icon_ref)
            created.append(str(lnk))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{lnk}: {exc}")

    return {"ok": bool(created), "target": target, "created": created, "errors": errors}


def remove_shortcut(name: str = SHORTCUT_NAME) -> list[str]:
    """删除桌面和开始菜单里的快捷方式。"""
    removed: list[str] = []
    for folder in {_desktop_dir(), _start_menu_dir()}:
        lnk = folder / name
        if lnk.exists():
            try:
                lnk.unlink()
                removed.append(str(lnk))
            except OSError:
                pass
    return removed
