from __future__ import annotations
import json
import tempfile
from pathlib import Path
from typing import Any

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

    def freeze_protocol(self, proposal: Any) -> dict:
        with tempfile.TemporaryDirectory(prefix="fieldmedic-freeze-") as td:
            output = Path(td) / "protocol-freeze.json"
            args = [
                "--protocol-freeze", str(proposal.netmedic_case),
                "--protocol-name", proposal.name,
                "--design-key", proposal.design_key,
                "--design-a", proposal.arm_a,
                "--design-b", proposal.arm_b,
                "--design-test", proposal.test_label,
                "--design-trials", str(proposal.trials),
                "--design-window-minutes", str(proposal.window_minutes),
            ]
            for key, value in proposal.controls:
                args.extend(["--design-control", f"{key}={value}"])
            args.extend(["--protocol-freeze-output", str(output)])
            run_tool(self.binary, args, timeout=180)
            return self._read_json(output)

    def preflight_protocol(
        self,
        *,
        case: str,
        protocol_fingerprint: str,
        control_keys: list[str],
        output_path: Path,
        confirm_arm: bool,
        confirm_machine_stable: bool,
        confirm_test_context: bool,
    ) -> dict:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        drift = output_path.with_name(output_path.stem + "-resume-drift.json")
        args = [
            "--preflight-case", str(case),
            "--protocol", protocol_fingerprint,
            "--preflight-output", str(output_path),
            "--resume-drift-output", str(drift),
        ]
        if confirm_arm:
            args.append("--confirm-arm")
        if confirm_machine_stable:
            args.append("--confirm-machine-stable")
        if confirm_test_context:
            args.append("--confirm-test-context")
        for key in control_keys:
            args.extend(["--confirm-control", key])
        run_tool(self.binary, args, timeout=180)
        payload = self._read_json(output_path)
        payload["_local_receipt_path"] = str(output_path)
        if drift.exists():
            payload["_resume_drift"] = self._read_json(drift)
        return payload

    def execute_protocol(
        self,
        *,
        case: str,
        protocol_fingerprint: str,
        preflight_receipt: str | Path,
        output_path: Path,
    ) -> dict:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        run_tool(self.binary, [
            "--execute-case", str(case),
            "--protocol", protocol_fingerprint,
            "--require-preflight", str(preflight_receipt),
            "--execute-output", str(output_path),
        ], timeout=300)
        return self._read_json(output_path)

    def matched_protocol(
        self,
        *,
        case: str,
        protocol_fingerprint: str,
        output_path: Path,
    ) -> dict:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        run_tool(self.binary, [
            "--matched-case", str(case),
            "--protocol", protocol_fingerprint,
            "--matched-output", str(output_path),
        ], timeout=180)
        return self._read_json(output_path)
