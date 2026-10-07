from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
import re
import shutil
import subprocess
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LocalModel:
    provider: str
    name: str
    size_bytes: int | None = None
    parameter_billions: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _billions_from_name(name: str) -> float | None:
    match = re.search(r"(?:^|[:._-])(\d+(?:\.\d+)?)b(?:$|[:._-])", name.lower())
    return float(match.group(1)) if match else None


def _from_ollama_api(timeout: float) -> list[LocalModel]:
    req = Request("http://127.0.0.1:11434/api/tags", headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models: list[LocalModel] = []
    for item in payload.get("models", []):
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name:
            continue
        raw_size = item.get("size")
        size = int(raw_size) if isinstance(raw_size, (int, float)) else None
        models.append(LocalModel(
            provider="ollama",
            name=name,
            size_bytes=size,
            parameter_billions=_billions_from_name(name),
        ))
    return models


def _from_ollama_cli() -> list[LocalModel]:
    binary = shutil.which("ollama")
    if not binary:
        return []
    cp = subprocess.run(
        [binary, "list"],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    if cp.returncode != 0:
        return []
    models: list[LocalModel] = []
    for line in cp.stdout.splitlines()[1:]:
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        models.append(LocalModel(
            provider="ollama",
            name=name,
            parameter_billions=_billions_from_name(name),
        ))
    return models


def discover_local_models(timeout: float = 0.35) -> list[LocalModel]:
    if os.environ.get("FIELDMEDIC_DISABLE_MODEL_DISCOVERY") == "1":
        return []
    try:
        found = _from_ollama_api(timeout)
        if found:
            return sorted(found, key=_cost_key)
    except Exception:
        pass
    try:
        return sorted(_from_ollama_cli(), key=_cost_key)
    except Exception:
        return []


def _cost_key(model: LocalModel) -> tuple[float, str]:
    if model.size_bytes is not None:
        return (float(model.size_bytes), model.name)
    if model.parameter_billions is not None:
        return (model.parameter_billions * 1_000_000_000, model.name)
    return (float("inf"), model.name)


def choose_model(models: list[LocalModel], tier: str) -> LocalModel | None:
    if not models or tier == "deterministic":
        return None
    ranked = sorted(models, key=_cost_key)
    if tier == "utility":
        return ranked[0]
    if tier == "specialist":
        return ranked[(len(ranked) - 1) // 2]
    return ranked[-1]
