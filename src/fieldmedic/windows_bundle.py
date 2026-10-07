from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile
from typing import Any

from . import __version__
from .hashutil import sha256_json


BUNDLE_SCHEMA = "field-medic-windows-bundle-v1"


class WindowsBundleError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> bytes:
    if not path.is_file():
        raise WindowsBundleError(f"bundle input not found: {path}")
    return path.read_bytes()


def build_windows_bundle(
    *,
    wheel: Path,
    repository_root: Path,
    output: Path,
) -> dict[str, Any]:
    token = f"-{__version__}-"
    if token.lower() not in wheel.name.lower():
        raise WindowsBundleError(
            f"wheel version does not match FieldMedic {__version__}: {wheel.name}"
        )

    inputs = [
        (f"packages/{wheel.name}", _read(wheel)),
        ("install.ps1", _read(repository_root / "scripts" / "install-windows.ps1")),
        ("uninstall.ps1", _read(repository_root / "scripts" / "uninstall-windows.ps1")),
        ("smoke-windows-install.ps1", _read(repository_root / "scripts" / "smoke-windows-install.ps1")),
        ("write-install-smoke-receipt.py", _read(repository_root / "scripts" / "write-install-smoke-receipt.py")),
        ("README.txt", _read(repository_root / "docs" / "WINDOWS_INSTALL.txt")),
        ("LICENSE", _read(repository_root / "LICENSE")),
    ]
    files = [
        {
            "path": name,
            "size_bytes": len(data),
            "sha256": _sha256(data),
        }
        for name, data in inputs
    ]
    manifest_body = {
        "schema": BUNDLE_SCHEMA,
        "fieldmedic_version": __version__,
        "build_time_policy": "deterministic-no-wall-clock",
        "files": files,
        "bundles_drivemedic": False,
        "bundles_netmedic": False,
        "engine_handoff": "paths-only",
        "default_uninstall_preserves_data": True,
    }
    manifest = {
        **manifest_body,
        "manifest_sha256": sha256_json(manifest_body),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, data in inputs:
            info = zipfile.ZipInfo(name, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
        info = zipfile.ZipInfo("manifest.json", date_time=fixed_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        archive.writestr(
            info,
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    return {
        "schema": "field-medic-windows-bundle-build-v1",
        "fieldmedic_version": __version__,
        "output": str(output),
        "bundle_sha256": _sha256(output.read_bytes()),
        "manifest": manifest,
    }
