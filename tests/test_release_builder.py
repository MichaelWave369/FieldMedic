import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from fieldmedic import __version__
from fieldmedic.hashutil import sha256_json
from fieldmedic.release_builder import (
    ReleaseBuildError,
    _is_prerelease,
    _validate_windows_bundle,
    build_release,
)


READY = {
    "status": "READY_FOR_STABLE_PACKAGING",
    "engine_discovery": {
        "drivemedic": {"version": "DriveMedic 1.0.0-rc13"},
        "netmedic": {"version": "Parallax NetMedic v0.34.0"},
    },
    "gates": {
        "windows_install_smoke": {
            "status": "QUALIFIED_BY_LOCAL_RECEIPT",
            "receipt_sha256": "1" * 64,
        },
        "windows_repair_qualification": {
            "status": "QUALIFIED_BY_LOCAL_RECEIPT",
            "receipt_sha256": "2" * 64,
        },
        "drivemedic_lifecycle": {
            "status": "QUALIFIED_BY_IMPORTED_EVIDENCE",
            "record_sha256": "3" * 64,
            "source_artifact_sha256": "4" * 64,
        },
        "netmedic_field": {
            "status": "QUALIFIED_BY_IMPORTED_EVIDENCE",
            "record_sha256": "5" * 64,
            "source_artifact_sha256": "6" * 64,
        },
        "netmedic_license": {
            "status": "QUALIFIED_BY_IMPORTED_EVIDENCE",
            "record_sha256": "7" * 64,
            "source_artifact_sha256": "8" * 64,
        },
    },
}


def make_windows_bundle(path: Path):
    body = {
        "schema": "field-medic-windows-bundle-v1",
        "fieldmedic_version": __version__,
        "build_time_policy": "deterministic-no-wall-clock",
        "files": [],
        "bundles_drivemedic": False,
        "bundles_netmedic": False,
        "engine_handoff": "paths-only",
        "default_uninstall_preserves_data": True,
    }
    manifest = {**body, "manifest_sha256": sha256_json(body)}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
    return manifest


class ReleaseBuilderTests(unittest.TestCase):
    def test_prerelease_detection(self):
        self.assertTrue(_is_prerelease("0.7.0rc5"))
        self.assertTrue(_is_prerelease("1.0.0dev2"))
        self.assertFalse(_is_prerelease("0.7.0"))

    def test_windows_bundle_validation_rejects_vendored_engine(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "windows.zip"
            body = {
                "schema": "field-medic-windows-bundle-v1",
                "fieldmedic_version": __version__,
                "build_time_policy": "deterministic-no-wall-clock",
                "files": [],
                "bundles_drivemedic": True,
                "bundles_netmedic": False,
                "engine_handoff": "paths-only",
                "default_uninstall_preserves_data": True,
            }
            manifest = {**body, "manifest_sha256": sha256_json(body)}
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaises(ReleaseBuildError):
                _validate_windows_bundle(path)

    def test_blocked_promotion_prevents_any_release_build(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_builder.build_promotion_candidate",
            return_value={
                "status": "BLOCKED",
                "blocking_gates": [{"gate": "windows_install_smoke"}],
            },
        ):
            with self.assertRaises(ReleaseBuildError):
                build_release(
                    home=Path(td) / "home",
                    repo_root=Path(td) / "repo",
                    output_dir=Path(td) / "out",
                    channel="candidate",
                )

    def test_stable_channel_refuses_current_prerelease_version(self):
        with tempfile.TemporaryDirectory() as td, patch(
            "fieldmedic.release_builder._require_promotion_ready",
            return_value=READY,
        ):
            with self.assertRaises(ReleaseBuildError):
                build_release(
                    home=Path(td) / "home",
                    repo_root=Path(td) / "repo",
                    output_dir=Path(td) / "out",
                    channel="stable",
                )

    def test_candidate_build_locks_source_gates_and_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            repo.mkdir()
            (repo / "LICENSE").write_text("MIT", encoding="utf-8")

            def wheel(repo_root, stage, epoch):
                path = stage / f"fieldmedic-{__version__}-py3-none-any.whl"
                path.write_bytes(b"wheel")
                return path

            def source(repo_root, stage, *, head):
                path = stage / f"FieldMedic-{__version__}-source.zip"
                path.write_bytes(b"source")
                return path

            def windows(*, wheel, repository_root, output):
                make_windows_bundle(output)
                return {"output": str(output)}

            with patch(
                "fieldmedic.release_builder._require_promotion_ready",
                return_value=READY,
            ), patch(
                "fieldmedic.release_builder._require_clean_repo",
                return_value=("a" * 40, "b" * 40, 1700000000),
            ), patch(
                "fieldmedic.release_builder._build_wheel",
                side_effect=wheel,
            ), patch(
                "fieldmedic.release_builder._build_source_archive",
                side_effect=source,
            ), patch(
                "fieldmedic.release_builder.build_windows_bundle",
                side_effect=windows,
            ), patch(
                "fieldmedic.release_builder.build_release_receipt",
                return_value={
                    "schema": "field-medic-release-receipt-v1",
                    "receipt_sha256": "c" * 64,
                },
            ):
                result = build_release(
                    home=root / "home",
                    repo_root=repo,
                    output_dir=root / "out",
                    channel="candidate",
                )

            self.assertEqual(result["source_commit"], "a" * 40)
            self.assertTrue(Path(result["release_packet"]["path"]).is_file())
            lock_path = Path(result["release_lock"]["path"])
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(lock["source"]["git_tree"], "b" * 40)
            self.assertEqual(
                lock["promotion_gates"]["netmedic_license"][
                    "source_artifact_sha256"
                ],
                "8" * 64,
            )
            self.assertEqual(len(lock["artifacts"]), 3)
            self.assertTrue(Path(result["sha256sums"]).is_file())


if __name__ == "__main__":
    unittest.main()
