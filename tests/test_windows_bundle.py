import tempfile
import unittest
from pathlib import Path
import zipfile

from fieldmedic import __version__
from fieldmedic.windows_bundle import (
    WindowsBundleError,
    build_windows_bundle,
)


class WindowsBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_does_not_vendor_engines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            scripts = repo / "scripts"
            docs = repo / "docs"
            scripts.mkdir(parents=True)
            docs.mkdir(parents=True)
            (scripts / "install-windows.ps1").write_text("install", encoding="utf-8")
            (scripts / "uninstall-windows.ps1").write_text("uninstall", encoding="utf-8")
            (scripts / "smoke-windows-install.ps1").write_text("smoke", encoding="utf-8")
            (scripts / "write-install-smoke-receipt.py").write_text("writer", encoding="utf-8")
            (docs / "WINDOWS_INSTALL.txt").write_text("readme", encoding="utf-8")
            (repo / "LICENSE").write_text("MIT", encoding="utf-8")
            wheel = root / f"fieldmedic-{__version__}-py3-none-any.whl"
            wheel.write_bytes(b"wheel")

            first = root / "first.zip"
            second = root / "second.zip"
            a = build_windows_bundle(
                wheel=wheel,
                repository_root=repo,
                output=first,
            )
            b = build_windows_bundle(
                wheel=wheel,
                repository_root=repo,
                output=second,
            )
            self.assertEqual(a["bundle_sha256"], b["bundle_sha256"])
            manifest = a["manifest"]
            self.assertFalse(manifest["bundles_drivemedic"])
            self.assertFalse(manifest["bundles_netmedic"])
            self.assertEqual(manifest["engine_handoff"], "paths-only")
            self.assertTrue(manifest["default_uninstall_preserves_data"])

            with zipfile.ZipFile(first, "r") as zf:
                names = set(zf.namelist())
            self.assertIn("install.ps1", names)
            self.assertIn("uninstall.ps1", names)
            self.assertIn("smoke-windows-install.ps1", names)
            self.assertIn("write-install-smoke-receipt.py", names)
            self.assertIn(f"packages/{wheel.name}", names)
            self.assertFalse(any("drivemedic" in name.lower() for name in names))
            self.assertFalse(any("netmedic" in name.lower() for name in names))

    def test_wrong_version_wheel_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wheel = root / "fieldmedic-0.0.0-py3-none-any.whl"
            wheel.write_bytes(b"wheel")
            with self.assertRaises(WindowsBundleError):
                build_windows_bundle(
                    wheel=wheel,
                    repository_root=root,
                    output=root / "bundle.zip",
                )


if __name__ == "__main__":
    unittest.main()
