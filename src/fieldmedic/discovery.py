from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .settings import load_engine_config


@dataclass(frozen=True)
class EngineProbe:
    engine: str
    path: str | None
    discovered_by: str | None
    present: bool
    version: str | None
    healthy: bool | None
    details: dict[str, Any]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(path: Path, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _candidate_paths(
    engine: str,
    *,
    home: Path | None = None,
) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    env_name = "DRIVEMEDIC_BIN" if engine == "drivemedic" else "NETMEDIC_BIN"
    env_value = os.environ.get(env_name)
    if env_value:
        candidates.append((Path(env_value).expanduser(), f"env:{env_name}"))

    config = load_engine_config(home)
    if config.get("status") == "CONFIGURED":
        configured = config.get(engine)
        if configured:
            candidates.append((Path(str(configured)), "config:engines.json"))

    executable = "drivemedic.exe" if os.name == "nt" and engine == "drivemedic" else (
        "netmedic.exe" if os.name == "nt" else engine
    )
    if engine == "drivemedic" and os.name != "nt":
        executable = "drivemedic"
    found = shutil.which(executable)
    if found:
        candidates.append((Path(found), "PATH"))

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        if engine == "drivemedic":
            if local:
                candidates.append((
                    Path(local) / "Programs" / "DriveMedic" / "drivemedic.exe",
                    "known-install:localappdata",
                ))
            if program_files:
                candidates.append((
                    Path(program_files) / "DriveMedic" / "drivemedic.exe",
                    "known-install:programfiles",
                ))
        else:
            if local:
                candidates.append((
                    Path(local) / "Programs" / "NetMedic" / "netmedic.exe",
                    "known-install:localappdata",
                ))
            candidates.append((Path("C:/Tools/netmedic.exe"), "known-install:c-tools"))

    seen: set[str] = set()
    unique: list[tuple[Path, str]] = []
    for path, source in candidates:
        key = str(path.resolve(strict=False)).lower() if os.name == "nt" else str(path.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append((path, source))
    return unique


def _select(
    engine: str,
    explicit: str | None = None,
    *,
    home: Path | None = None,
) -> tuple[Path | None, str | None]:
    if explicit:
        path = Path(explicit).expanduser()
        return (path, "explicit")
    for path, source in _candidate_paths(engine, home=home):
        if path.is_file():
            return path, source
    return None, None


def probe_drivemedic(
    explicit: str | None = None,
    *,
    home: Path | None = None,
) -> EngineProbe:
    path, source = _select("drivemedic", explicit, home=home)
    if path is None or not path.is_file():
        return EngineProbe(
            engine="drivemedic",
            path=str(path) if path else None,
            discovered_by=source,
            present=False,
            version=None,
            healthy=None,
            details={},
            errors=("DriveMedic binary not found",),
        )
    errors: list[str] = []
    version: str | None = None
    healthy: bool | None = None
    details: dict[str, Any] = {}
    try:
        cp = _run(path, ["version"])
        if cp.returncode == 0:
            version = cp.stdout.strip() or cp.stderr.strip() or None
        else:
            errors.append(f"version exited {cp.returncode}")
    except Exception as exc:
        errors.append(f"version probe failed: {exc}")

    try:
        cp = _run(path, ["self-check-json"])
        if cp.returncode != 0:
            errors.append(f"self-check-json exited {cp.returncode}")
        else:
            value = json.loads(cp.stdout)
            if isinstance(value, dict):
                details["self_check"] = value
                if "ok" in value:
                    healthy = bool(value["ok"])
                elif "passed" in value:
                    healthy = bool(value["passed"])
                else:
                    checks = value.get("checks")
                    if isinstance(checks, list):
                        healthy = all(bool(item.get("ok")) for item in checks if isinstance(item, dict))
            else:
                errors.append("self-check-json root was not an object")
    except Exception as exc:
        errors.append(f"self-check probe failed: {exc}")

    return EngineProbe(
        engine="drivemedic",
        path=str(path.resolve()),
        discovered_by=source,
        present=True,
        version=version,
        healthy=healthy,
        details=details,
        errors=tuple(errors),
    )


def probe_netmedic(
    explicit: str | None = None,
    *,
    home: Path | None = None,
) -> EngineProbe:
    path, source = _select("netmedic", explicit, home=home)
    if path is None or not path.is_file():
        return EngineProbe(
            engine="netmedic",
            path=str(path) if path else None,
            discovered_by=source,
            present=False,
            version=None,
            healthy=None,
            details={},
            errors=("NetMedic binary not found",),
        )
    errors: list[str] = []
    version: str | None = None
    details: dict[str, Any] = {}
    healthy: bool | None = None
    try:
        cp = _run(path, ["--version"])
        if cp.returncode == 0:
            version = cp.stdout.strip() or cp.stderr.strip() or None
            healthy = True
        else:
            errors.append(f"--version exited {cp.returncode}")
            healthy = False
    except Exception as exc:
        errors.append(f"version probe failed: {exc}")
        healthy = False

    try:
        cp = _run(path, ["--crypto-status"])
        details["crypto_status"] = {
            "returncode": cp.returncode,
            "stdout": cp.stdout.strip(),
            "stderr": cp.stderr.strip(),
        }
    except Exception as exc:
        errors.append(f"crypto-status probe failed: {exc}")

    return EngineProbe(
        engine="netmedic",
        path=str(path.resolve()),
        discovered_by=source,
        present=True,
        version=version,
        healthy=healthy,
        details=details,
        errors=tuple(errors),
    )


def discover_engines(
    *,
    drivemedic: str | None = None,
    netmedic: str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    config = load_engine_config(home)
    drive = probe_drivemedic(drivemedic, home=home)
    net = probe_netmedic(netmedic, home=home)
    return {
        "schema": "field-medic-engine-discovery-v1",
        "drivemedic": drive.to_dict(),
        "netmedic": net.to_dict(),
        "engine_config": config,
        "ready_for_diagnostics": bool(
            drive.present and net.present
            and drive.healthy is not False
            and net.healthy is not False
        ),
    }
