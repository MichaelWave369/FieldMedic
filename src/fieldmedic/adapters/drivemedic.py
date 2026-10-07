from __future__ import annotations
import json
from . import __name__ as _pkg_marker
from ..runner import run_tool, ToolError


class DriveMedicAdapter:
    def __init__(self, binary: str):
        self.binary = binary

    def _json_stdout(self, *args: str) -> dict:
        result = run_tool(self.binary, list(args))
        text = result.stdout.strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError(f"DriveMedic did not return JSON for {' '.join(args)}: {exc}") from exc
        if not isinstance(value, dict):
            raise ToolError("DriveMedic JSON root must be an object")
        return value

    def status(self) -> dict:
        return self._json_stdout("status-json")

    def timeline(self, hours: int = 6, max_points: int = 720) -> dict:
        return self._json_stdout("timeline-json", str(hours), str(max_points))

    def self_check(self) -> dict:
        return self._json_stdout("self-check-json")
