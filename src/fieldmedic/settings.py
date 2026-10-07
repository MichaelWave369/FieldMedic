from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .hashutil import sha256_json


CONFIG_SCHEMA = "field-medic-engine-config-v1"


def default_home() -> Path:
    env = os.environ.get("FIELDMEDIC_HOME")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "FieldMedic"
    return Path.home() / ".fieldmedic"


def engine_config_path(home: Path | None = None) -> Path:
    root = home or default_home()
    return root / "config" / "engines.json"


def _validate_optional_binary(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_file():
        raise ValueError(f"{name} binary not found: {path}")
    return str(path.resolve())


def write_engine_config(
    *,
    home: Path | None = None,
    drivemedic: str | None = None,
    netmedic: str | None = None,
) -> dict[str, Any]:
    root = home or default_home()
    drive = _validate_optional_binary(drivemedic, name="DriveMedic")
    net = _validate_optional_binary(netmedic, name="NetMedic")
    body = {
        "schema": CONFIG_SCHEMA,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "drivemedic": drive,
        "netmedic": net,
    }
    payload = {**body, "config_sha256": sha256_json(body)}
    path = engine_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "path": str(path),
        "config": payload,
    }


def load_engine_config(home: Path | None = None) -> dict[str, Any]:
    path = engine_config_path(home)
    if not path.exists():
        return {
            "status": "NOT_CONFIGURED",
            "path": str(path),
            "drivemedic": None,
            "netmedic": None,
            "errors": [],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("config root must be an object")
        if value.get("schema") != CONFIG_SCHEMA:
            raise ValueError("unsupported engine config schema")
        body = {
            key: item
            for key, item in value.items()
            if key != "config_sha256"
        }
        if value.get("config_sha256") != sha256_json(body):
            raise ValueError("engine config fingerprint mismatch")
        return {
            "status": "CONFIGURED",
            "path": str(path),
            "drivemedic": value.get("drivemedic"),
            "netmedic": value.get("netmedic"),
            "updated_at": value.get("updated_at"),
            "config_sha256": value.get("config_sha256"),
            "errors": [],
        }
    except Exception as exc:
        return {
            "status": "INVALID",
            "path": str(path),
            "drivemedic": None,
            "netmedic": None,
            "errors": [str(exc)],
        }
