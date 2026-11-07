"""phone_setup 的测试：检测、vendor 路径、一键安装的成功与失败分支。

全部离线——真正调用 pip 的地方用 mock 替掉。
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from judgedee import config, phone_setup


class PhoneSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        for name, value in (("_DIR_CACHE", None), ("_DIR_ERROR", ""), ("_MIGRATED", True)):
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_vendor_dir_under_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"JUDGEDEE_HOME": tmp}):
                path = phone_setup.vendor_dir()
        self.assertEqual(path.name, phone_setup.VENDOR_NAME)
        self.assertEqual(path.parent.name, Path(tmp).name)

    def test_ensure_path_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vendor = Path(tmp) / phone_setup.VENDOR_NAME
            vendor.mkdir()
            with mock.patch.dict("os.environ", {"JUDGEDEE_HOME": tmp}):
                with mock.patch.object(phone_setup.sys, "path", list(phone_setup.sys.path)):
                    first = phone_setup.ensure_path()
                    second = phone_setup.ensure_path()
                    count = phone_setup.sys.path.count(str(first))
        self.assertEqual(first, vendor)
        self.assertEqual(second, vendor)
        self.assertEqual(count, 1)

    def test_available_false_when_module_missing(self) -> None:
        with mock.patch.object(phone_setup, "ensure_path", lambda: Path(".")):
            with mock.patch.dict("sys.modules", {"phonenumbers": None}):
                self.assertFalse(phone_setup.available())

    def test_install_success(self) -> None:
        completed = subprocess.CompletedProcess(args=["pip"], returncode=0, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"JUDGEDEE_HOME": tmp}):
                with mock.patch.object(phone_setup.subprocess, "run", return_value=completed) as run:
                    with mock.patch.object(phone_setup, "available", return_value=True):
                        ok, message = phone_setup.install()
        self.assertTrue(ok)
        self.assertEqual(message, "已安装")
        cmd = run.call_args[0][0]
        self.assertIn("--target", cmd)
        self.assertIn(phone_setup.REQUIREMENT, cmd)

    def test_install_reports_pip_failure(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["pip"], returncode=1, stdout="", stderr="ERROR: No matching distribution found"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"JUDGEDEE_HOME": tmp}):
                with mock.patch.object(phone_setup.subprocess, "run", return_value=completed):
                    ok, message = phone_setup.install()
        self.assertFalse(ok)
        self.assertIn("No matching distribution", message)

    def test_install_survives_subprocess_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"JUDGEDEE_HOME": tmp}):
                with mock.patch.object(
                    phone_setup.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 1)
                ):
                    ok, message = phone_setup.install()
        self.assertFalse(ok)
        self.assertIn("pip", message)


if __name__ == "__main__":
    unittest.main()
