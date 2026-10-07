import json
import tempfile
import unittest
from pathlib import Path

from fieldmedic.settings import (
    engine_config_path,
    load_engine_config,
    write_engine_config,
)


class SettingsTests(unittest.TestCase):
    def test_default_home_preserves_legacy_location_without_override(self):
        from unittest.mock import patch
        from fieldmedic.settings import default_home
        with patch.dict(
            "os.environ",
            {"FIELDMEDIC_HOME": ""},
            clear=False,
        ):
            self.assertEqual(default_home(), Path.home() / ".fieldmedic")

    def test_round_trip_config_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drive = root / "drivemedic.exe"
            net = root / "netmedic.exe"
            drive.write_bytes(b"drive")
            net.write_bytes(b"net")

            written = write_engine_config(
                home=root / "home",
                drivemedic=str(drive),
                netmedic=str(net),
            )
            loaded = load_engine_config(root / "home")
            self.assertEqual(loaded["status"], "CONFIGURED")
            self.assertEqual(loaded["drivemedic"], str(drive.resolve()))
            self.assertEqual(loaded["netmedic"], str(net.resolve()))
            self.assertEqual(
                Path(written["path"]),
                engine_config_path(root / "home"),
            )

    def test_updating_one_engine_preserves_the_other(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            drive1 = root / "drive1.exe"
            drive2 = root / "drive2.exe"
            net = root / "net.exe"
            for path in (drive1, drive2, net):
                path.write_bytes(b"x")
            write_engine_config(
                home=home,
                drivemedic=str(drive1),
                netmedic=str(net),
            )
            write_engine_config(
                home=home,
                drivemedic=str(drive2),
            )
            loaded = load_engine_config(home)
            self.assertEqual(loaded["drivemedic"], str(drive2.resolve()))
            self.assertEqual(loaded["netmedic"], str(net.resolve()))

    def test_tampered_config_is_not_used(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            target = engine_config_path(home)
            target.parent.mkdir(parents=True)
            target.write_text(
                json.dumps({
                    "schema": "field-medic-engine-config-v1",
                    "updated_at": "2026-10-07T00:00:00Z",
                    "drivemedic": "C:/tampered.exe",
                    "netmedic": None,
                    "config_sha256": "0" * 64,
                }),
                encoding="utf-8",
            )
            loaded = load_engine_config(home)
            self.assertEqual(loaded["status"], "INVALID")
            self.assertIsNone(loaded["drivemedic"])

    def test_missing_binary_is_rejected_at_write(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                write_engine_config(
                    home=Path(td),
                    drivemedic=str(Path(td) / "missing.exe"),
                )


if __name__ == "__main__":
    unittest.main()
