from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

from . import __version__
from .hashutil import sha256_json
from .promotion import build_promotion_candidate
from .release_receipt import build_release_receipt
from .windows_bundle import build_windows_bundle


LOCK_SCHEMA = "field-medic-release-lock-v1"


class ReleaseBuildError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise ReleaseBuildError(
            f"git {' '.join(args)} failed: {cp.stderr.strip() or cp.stdout.strip()}"
        )
    return cp.stdout.strip()


def _require_clean_repo(repo_root: Path) -> tuple[str, str, int]:
    if not (repo_root / ".git").exists():
        raise ReleaseBuildError("release build must run from a Git checkout")
    dirty = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ReleaseBuildError(
            "release build requires a clean Git worktree; commit or remove local changes"
        )
    head = _git(repo_root, "rev-parse", "HEAD")
    tree = _git(repo_root, "rev-parse", "HEAD^{tree}")
    try:
        epoch = int(_git(repo_root, "show", "-s", "--format=%ct", "HEAD"))
    except ValueError as exc:
        raise ReleaseBuildError("could not parse Git commit timestamp") from exc
    return head, tree, epoch


def _is_prerelease(version: str) -> bool:
    return bool(re.search(r"(?:a|b|rc|dev)\d*$", version.lower()))


def _require_promotion_ready(home: Path) -> dict[str, Any]:
    candidate = build_promotion_candidate(home)
    if candidate.get("status") != "READY_FOR_STABLE_PACKAGING":
        blockers = candidate.get("blocking_gates", [])
        raise ReleaseBuildError(
            "stable packaging is blocked by release evidence gates: "
            + json.dumps(blockers, sort_keys=True)
        )
    return candidate


def _gate_lock(candidate: dict[str, Any]) -> dict[str, Any]:
    locked: dict[str, Any] = {}
    for name, gate in sorted(candidate.get("gates", {}).items()):
        if not isinstance(gate, dict):
            raise ReleaseBuildError(f"invalid promotion gate payload: {name}")
        locked[name] = {
            "status": gate.get("status"),
            "receipt_sha256": gate.get("receipt_sha256"),
            "record_sha256": gate.get("record_sha256"),
            "source_artifact_sha256": gate.get("source_artifact_sha256"),
        }
    return locked


def _artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReleaseBuildError(f"release artifact not found: {path}")
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _validate_windows_bundle(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
    except Exception as exc:
        raise ReleaseBuildError(f"invalid Windows bundle: {exc}") from exc
    if manifest.get("schema") != "field-medic-windows-bundle-v1":
        raise ReleaseBuildError("Windows bundle manifest schema mismatch")
    if manifest.get("fieldmedic_version") != __version__:
        raise ReleaseBuildError("Windows bundle version does not match FieldMedic")
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if manifest.get("manifest_sha256") != sha256_json(body):
        raise ReleaseBuildError("Windows bundle manifest fingerprint mismatch")
    if manifest.get("bundles_drivemedic") is not False:
        raise ReleaseBuildError("stable FieldMedic bundle must not vendor DriveMedic")
    if manifest.get("bundles_netmedic") is not False:
        raise ReleaseBuildError("stable FieldMedic bundle must not vendor NetMedic")
    return manifest


def _copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def _build_wheel(repo_root: Path, stage: Path, epoch: int) -> Path:
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    cp = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(repo_root),
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(stage),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if cp.returncode != 0:
        raise ReleaseBuildError(
            f"wheel build failed: {cp.stderr.strip() or cp.stdout.strip()}"
        )
    wheels = list(stage.glob("fieldmedic-*.whl"))
    if len(wheels) != 1:
        raise ReleaseBuildError(
            f"expected exactly one FieldMedic wheel, found {len(wheels)}"
        )
    if f"-{__version__}-" not in wheels[0].name:
        raise ReleaseBuildError("built wheel version does not match FieldMedic")
    return wheels[0]


def _build_source_archive(
    repo_root: Path,
    stage: Path,
    *,
    head: str,
) -> Path:
    output = stage / f"FieldMedic-{__version__}-source.zip"
    cp = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "archive",
            "--format=zip",
            f"--prefix=FieldMedic-{__version__}/",
            "-o",
            str(output),
            head,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise ReleaseBuildError(
            f"source archive build failed: {cp.stderr.strip() or cp.stdout.strip()}"
        )
    return output


def _write_release_packet(
    output: Path,
    *,
    artifacts: list[Path],
    release_lock: Path,
    sha256sums: Path,
    license_file: Path,
) -> Path:
    fixed_time = (1980, 1, 1, 0, 0, 0)
    entries = [
        *(("artifacts/" + item.name, item.read_bytes()) for item in artifacts),
        ("release-lock.json", release_lock.read_bytes()),
        ("SHA256SUMS", sha256sums.read_bytes()),
        ("LICENSE", license_file.read_bytes()),
    ]
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return output


def build_release(
    *,
    home: Path,
    repo_root: Path,
    output_dir: Path,
    channel: str,
) -> dict[str, Any]:
    if channel not in {"candidate", "stable"}:
        raise ReleaseBuildError("channel must be candidate or stable")
    if channel == "stable" and _is_prerelease(__version__):
        raise ReleaseBuildError(
            f"stable channel refuses prerelease version {__version__}"
        )

    promotion = _require_promotion_ready(home)
    head, tree, epoch = _require_clean_repo(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fieldmedic-release-") as td:
        stage = Path(td)
        wheel_stage = _build_wheel(repo_root, stage, epoch)
        source_stage = _build_source_archive(repo_root, stage, head=head)
        windows_stage = stage / f"FieldMedic-{__version__}-Windows.zip"
        build_windows_bundle(
            wheel=wheel_stage,
            repository_root=repo_root,
            output=windows_stage,
        )
        windows_manifest = _validate_windows_bundle(windows_stage)

        wheel = _copy(wheel_stage, output_dir / wheel_stage.name)
        source = _copy(source_stage, output_dir / source_stage.name)
        windows = _copy(windows_stage, output_dir / windows_stage.name)

    artifact_rows = [_artifact(item) for item in (wheel, source, windows)]
    lock_body = {
        "schema": LOCK_SCHEMA,
        "fieldmedic_version": __version__,
        "channel": channel,
        "source": {
            "git_commit": head,
            "git_tree": tree,
            "source_date_epoch": epoch,
        },
        "engines": {
            "drivemedic": promotion.get("engine_discovery", {})
                .get("drivemedic", {}).get("version"),
            "netmedic": promotion.get("engine_discovery", {})
                .get("netmedic", {}).get("version"),
        },
        "promotion_gates": _gate_lock(promotion),
        "windows_bundle_manifest_sha256": windows_manifest.get("manifest_sha256"),
        "artifacts": artifact_rows,
        "claim_boundary": (
            "This lock identifies the exact source commit, engine versions, qualifying "
            "gate hashes, and release artifacts used for this package. It does not "
            "replace the underlying qualification evidence."
        ),
    }
    lock = {**lock_body, "lock_sha256": sha256_json(lock_body)}
    lock_path = output_dir / f"FieldMedic-{__version__}-release-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")

    sums_path = output_dir / "SHA256SUMS"
    sum_rows = [
        *artifact_rows,
        _artifact(lock_path),
    ]
    sums_path.write_text(
        "".join(f"{row['sha256']}  {row['name']}\n" for row in sum_rows),
        encoding="utf-8",
    )

    packet = output_dir / f"FieldMedic-{__version__}-release.zip"
    _write_release_packet(
        packet,
        artifacts=[wheel, source, windows],
        release_lock=lock_path,
        sha256sums=sums_path,
        license_file=repo_root / "LICENSE",
    )

    receipt = build_release_receipt(home=home)
    receipt_path = output_dir / f"FieldMedic-{__version__}-release-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    return {
        "schema": "field-medic-release-build-v1",
        "fieldmedic_version": __version__,
        "channel": channel,
        "source_commit": head,
        "release_lock": {
            "path": str(lock_path),
            "sha256": _sha256(lock_path),
            "lock_sha256": lock["lock_sha256"],
        },
        "release_packet": {
            "path": str(packet),
            "sha256": _sha256(packet),
        },
        "release_receipt": {
            "path": str(receipt_path),
            "sha256": _sha256(receipt_path),
            "receipt_sha256": receipt["receipt_sha256"],
        },
        "sha256sums": str(sums_path),
        "artifacts": artifact_rows,
    }
