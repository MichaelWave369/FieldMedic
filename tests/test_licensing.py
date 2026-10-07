import tempfile
import unittest
from pathlib import Path

from fieldmedic.licensing import (
    LicenseGateError,
    import_netmedic_mit_license,
    netmedic_license_gate_from_home,
    validate_netmedic_mit_source,
)


MIT = """MIT License

Copyright (c) 2026 Michael Hughes / Parallax

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""


def source(root: Path, license_text: str):
    (root / "src" / "core").mkdir(parents=True)
    (root / "LICENSE").write_text(license_text, encoding="utf-8")
    (root / "src" / "core" / "AppVersion.h").write_text(
        '#define NETMEDIC_VERSION "0.34.0"\n#define NETMEDIC_NAME "Parallax NetMedic"\n',
        encoding="utf-8",
    )


class LicensingTests(unittest.TestCase):
    def test_mit_netmedic_source_can_be_imported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "net"
            source(src, MIT)
            result = validate_netmedic_mit_source(src)
            self.assertEqual(result["license_spdx"], "MIT")
            import_netmedic_mit_license(root / "home", src)
            gate = netmedic_license_gate_from_home(root / "home")
            self.assertEqual(
                gate["status"],
                "PUBLIC_MIT_LICENSE_VERIFIED_BY_SOURCE_HANDOFF",
            )

    def test_current_private_style_license_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "net"
            source(
                src,
                "Copyright (c) 2026\nAll rights reserved.\n"
                "This private development snapshot is not licensed for redistribution.",
            )
            with self.assertRaises(LicenseGateError):
                validate_netmedic_mit_source(src)

    def test_license_evidence_tamper_invalidates_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "net"
            source(src, MIT)
            receipt = import_netmedic_mit_license(root / "home", src)
            Path(receipt["stored_license"]).write_text(
                "All rights reserved.",
                encoding="utf-8",
            )
            gate = netmedic_license_gate_from_home(root / "home")
            self.assertEqual(gate["status"], "INVALID_LOCAL_RECEIPT")


if __name__ == "__main__":
    unittest.main()
