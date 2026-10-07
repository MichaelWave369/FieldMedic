from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile
from typing import Any

from .hashutil import sha256_json


class CaseBundleError(RuntimeError):
    pass


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_FILES = 4096


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_rel(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise CaseBundleError(f"unsafe case path: {rel}")
    return rel


def _case_id(case_dir: Path) -> str:
    case_file = case_dir / "case.json"
    if not case_file.exists():
        raise CaseBundleError(f"missing case.json: {case_file}")
    value = json.loads(case_file.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not str(value.get("case_id", "")).strip():
        raise CaseBundleError("case.json does not contain a valid case_id")
    return str(value["case_id"])


def export_case(case_dir: Path, output: Path) -> dict[str, Any]:
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise CaseBundleError(f"case directory not found: {case_dir}")
    case_id = _case_id(case_dir)

    files: list[dict[str, Any]] = []
    payloads: list[tuple[str, bytes]] = []
    for path in sorted(case_dir.rglob("*")):
        if path.is_symlink():
            raise CaseBundleError(f"symlink not permitted in case bundle: {path}")
        if not path.is_file():
            continue
        rel = _safe_rel(path, case_dir)
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise CaseBundleError(f"case file exceeds size limit: {rel}")
        payloads.append((rel, data))
        files.append({
            "path": rel,
            "size_bytes": len(data),
            "sha256": _sha256_bytes(data),
        })
        if len(files) > MAX_BUNDLE_FILES:
            raise CaseBundleError("case bundle contains too many files")

    manifest_body = {
        "schema": "field-medic-case-bundle-v1",
        "case_id": case_id,
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": files,
    }
    manifest = {
        **manifest_body,
        "manifest_sha256": sha256_json(manifest_body),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel, data in payloads:
            info = zipfile.ZipInfo(f"case/{rel}", date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, data)
        info = zipfile.ZipInfo("manifest.json", date_time=fixed_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        zf.writestr(
            info,
            json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    bundle_sha256 = _sha256_bytes(output.read_bytes())
    return {
        "schema": "field-medic-case-export-v1",
        "case_id": case_id,
        "path": str(output),
        "file_count": len(files),
        "manifest_sha256": manifest["manifest_sha256"],
        "bundle_sha256": bundle_sha256,
    }


def _validate_member(name: str) -> PurePosixPath:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise CaseBundleError(f"unsafe bundle member: {name}")
    return pure


def import_case(bundle: Path, cases_root: Path) -> dict[str, Any]:
    if not bundle.is_file():
        raise CaseBundleError(f"case bundle not found: {bundle}")
    with zipfile.ZipFile(bundle, "r") as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise CaseBundleError("case bundle is missing manifest.json")
        if len(names) > MAX_BUNDLE_FILES + 1:
            raise CaseBundleError("case bundle contains too many members")
        for name in names:
            _validate_member(name)
        manifest = json.loads(zf.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise CaseBundleError("case manifest root must be an object")
        body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        if manifest.get("manifest_sha256") != sha256_json(body):
            raise CaseBundleError("case manifest fingerprint mismatch")
        if manifest.get("schema") != "field-medic-case-bundle-v1":
            raise CaseBundleError("unsupported case bundle schema")
        case_id = str(manifest.get("case_id", "")).strip()
        if not case_id or any(ch in case_id for ch in "/\\"):
            raise CaseBundleError("invalid case_id in bundle")

        destination = cases_root / case_id
        if destination.exists():
            raise CaseBundleError(
                f"case already exists; import never overwrites: {destination}"
            )

        expected = {
            str(item["path"]): item
            for item in manifest.get("files", [])
            if isinstance(item, dict) and item.get("path")
        }
        actual_names = {
            name[len("case/"):]
            for name in names
            if name.startswith("case/") and not name.endswith("/")
        }
        if set(expected) != actual_names:
            raise CaseBundleError("bundle members do not match manifest")

        staged: list[tuple[str, bytes]] = []
        for rel, item in expected.items():
            _validate_member(rel)
            data = zf.read(f"case/{rel}")
            if len(data) != int(item["size_bytes"]):
                raise CaseBundleError(f"size mismatch for {rel}")
            if _sha256_bytes(data) != item["sha256"]:
                raise CaseBundleError(f"SHA-256 mismatch for {rel}")
            staged.append((rel, data))

    destination.mkdir(parents=True, exist_ok=False)
    try:
        for rel, data in staged:
            target = destination.joinpath(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        imported_id = _case_id(destination)
        if imported_id != case_id:
            raise CaseBundleError(
                f"case_id mismatch after import: {imported_id} != {case_id}"
            )
    except Exception:
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise

    return {
        "schema": "field-medic-case-import-v1",
        "case_id": case_id,
        "destination": str(destination),
        "file_count": len(staged),
        "manifest_sha256": manifest["manifest_sha256"],
        "bundle_sha256": _sha256_bytes(bundle.read_bytes()),
    }
