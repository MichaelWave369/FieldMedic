from __future__ import annotations
import json
import tempfile
from pathlib import Path
from ..runner import run_tool, ToolError


class NetMedicAdapter:
    def __init__(self, binary: str):
        self.binary = binary

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolError(f"NetMedic report is not readable JSON: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ToolError("NetMedic JSON root must be an object")
        return value

    def snapshot(self, samples: int = 3, dns_samples: int = 2) -> dict:
        with tempfile.TemporaryDirectory(prefix="fieldmedic-net-") as td:
            report = Path(td) / "snapshot.json"
            run_tool(self.binary, [
                "--report", str(report),
                "--samples", str(samples),
                "--dns-samples", str(dns_samples),
                "--redact-report",
                "--omit-raw-evidence",
            ], timeout=180)
            return self._read_json(report)

    def crypto_status_text(self) -> str:
        return run_tool(self.binary, ["--crypto-status"]).stdout.strip()
