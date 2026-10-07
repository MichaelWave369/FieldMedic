import unittest
from pathlib import Path


class InstallerContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.install = (
            self.root / "scripts" / "install-windows.ps1"
        ).read_text(encoding="utf-8")
        self.uninstall = (
            self.root / "scripts" / "uninstall-windows.ps1"
        ).read_text(encoding="utf-8")

    def test_installer_verifies_bundle_members_before_runtime_creation(self):
        self.assertIn("manifest.json", self.install)
        self.assertIn("Get-FileHash -Algorithm SHA256", self.install)
        self.assertIn("Bundle SHA-256 mismatch", self.install)

    def test_installer_does_not_require_admin_or_install_engines(self):
        lower = self.install.lower()
        self.assertNotIn("runas", lower)
        self.assertNotIn("start-process -verb runas", lower)
        self.assertNotIn("download", lower)
        self.assertNotIn("invoke-webrequest", lower)
        self.assertNotIn("install drivemedic", lower)
        self.assertNotIn("install netmedic", lower)

    def test_uninstall_preserves_data_by_default_and_requires_double_confirm(self):
        self.assertIn("-RemoveData", self.uninstall)
        self.assertIn("-ConfirmDataRemoval", self.uninstall)
        self.assertIn(
            "Local diagnostic data was preserved",
            self.uninstall,
        )

    def test_installer_rolls_back_config_launcher_and_path_on_failure(self):
        self.assertIn("$oldConfig", self.install)
        self.assertIn("$oldLauncher", self.install)
        self.assertIn("$oldDashboardLauncher", self.install)
        self.assertIn("if ($pathAdded)", self.install)
        self.assertIn("Remove-Item -Recurse -Force $runtimeRoot", self.install)

    def test_install_receipt_is_generated_by_installed_runtime(self):
        self.assertIn("'installation-receipt'", self.install)
        self.assertIn("'--uninstaller'", self.install)


if __name__ == "__main__":
    unittest.main()
