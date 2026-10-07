from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
import shutil
import subprocess
from typing import Any, Protocol

from .hashutil import sha256_json


class RepairExecutorError(RuntimeError):
    pass


class RepairBackend(Protocol):
    def inspect_interface_metric(self, interface_index: int, address_family: str) -> dict[str, Any]: ...
    def set_interface_metric(
        self,
        interface_index: int,
        address_family: str,
        *,
        automatic_metric: bool,
        metric: int | None,
    ) -> dict[str, Any]: ...
    def inspect_process_priority(self, pid: int) -> dict[str, Any]: ...
    def set_process_priority(
        self,
        pid: int,
        *,
        expected_start_ticks: int,
        priority: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RepairActionSpec:
    action_key: str
    title: str
    domain: str
    description: str
    risk: str
    required_source: str
    reversible: bool
    parameters: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SPECS: dict[str, RepairActionSpec] = {
    "windows.interface.metric": RepairActionSpec(
        action_key="windows.interface.metric",
        title="Set Windows interface metric",
        domain="network",
        description=(
            "Temporarily set one IPv4/IPv6 interface to a specific manual metric. "
            "The previous automatic/manual metric state is captured for exact rollback."
        ),
        risk="medium",
        required_source="netmedic",
        reversible=True,
        parameters=("interface_index", "address_family", "metric"),
    ),
    "windows.process.priority": RepairActionSpec(
        action_key="windows.process.priority",
        title="Set Windows process priority",
        domain="host",
        description=(
            "Set one existing process to Normal or BelowNormal priority. "
            "PID reuse is blocked by a captured process-start identity and the prior "
            "priority class is preserved for rollback."
        ),
        risk="low",
        required_source="drivemedic",
        reversible=True,
        parameters=("pid", "priority"),
    ),
}


def list_repair_actions() -> list[dict[str, Any]]:
    return [SPECS[key].to_dict() for key in sorted(SPECS)]


def _only_keys(params: dict[str, Any], allowed: set[str]) -> None:
    extra = sorted(set(params) - allowed)
    if extra:
        raise RepairExecutorError(f"unsupported repair parameters: {extra}")


def normalize_params(action_key: str, params: dict[str, Any]) -> dict[str, Any]:
    if action_key == "windows.interface.metric":
        _only_keys(params, {"interface_index", "address_family", "metric"})
        try:
            index = int(params["interface_index"])
            metric = int(params["metric"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RepairExecutorError(
                "windows.interface.metric requires integer interface_index and metric"
            ) from exc
        family = str(params.get("address_family", "")).strip()
        if index <= 0:
            raise RepairExecutorError("interface_index must be positive")
        if family not in {"IPv4", "IPv6"}:
            raise RepairExecutorError("address_family must be IPv4 or IPv6")
        if not 1 <= metric <= 9999:
            raise RepairExecutorError("metric must be between 1 and 9999")
        return {
            "interface_index": index,
            "address_family": family,
            "metric": metric,
        }

    if action_key == "windows.process.priority":
        _only_keys(params, {"pid", "priority"})
        try:
            pid = int(params["pid"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RepairExecutorError(
                "windows.process.priority requires integer pid"
            ) from exc
        priority = str(params.get("priority", "")).strip()
        if pid <= 0:
            raise RepairExecutorError("pid must be positive")
        if priority not in {"BelowNormal", "Normal"}:
            raise RepairExecutorError(
                "priority is intentionally bounded to BelowNormal or Normal"
            )
        return {"pid": pid, "priority": priority}

    raise RepairExecutorError(f"unknown bounded repair action: {action_key}")


class WindowsPowerShellBackend:
    def __init__(self, binary: str | None = None):
        self.binary = binary or shutil.which("powershell") or shutil.which("pwsh")
        if not self.binary:
            raise RepairExecutorError("PowerShell is required for Windows repair executors")

    def _json(self, script: str, args: list[str], timeout: int = 30) -> dict[str, Any]:
        if os.name != "nt":
            raise RepairExecutorError(
                "built-in Windows repair executors are available only on Windows"
            )
        cp = subprocess.run(
            [
                self.binary,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if cp.returncode != 0:
            raise RepairExecutorError(
                f"PowerShell repair backend failed ({cp.returncode}): "
                f"{cp.stderr.strip() or cp.stdout.strip()}"
            )
        try:
            value = json.loads(cp.stdout.strip())
        except json.JSONDecodeError as exc:
            raise RepairExecutorError(
                f"PowerShell repair backend returned invalid JSON: {cp.stdout!r}"
            ) from exc
        if not isinstance(value, dict):
            raise RepairExecutorError("repair backend JSON root must be an object")
        return value

    def inspect_interface_metric(
        self,
        interface_index: int,
        address_family: str,
    ) -> dict[str, Any]:
        script = r'''
param([int]$I, [string]$F)
$x = Get-NetIPInterface -InterfaceIndex $I -AddressFamily $F -ErrorAction Stop |
     Select-Object -First 1
if ($null -eq $x) { throw "interface not found" }
[pscustomobject]@{
  interface_index = [int]$x.InterfaceIndex
  address_family = [string]$x.AddressFamily
  interface_alias = [string]$x.InterfaceAlias
  automatic_metric = ([string]$x.AutomaticMetric -eq "Enabled")
  interface_metric = [int]$x.InterfaceMetric
} | ConvertTo-Json -Compress
'''
        raw = self._json(script, [str(interface_index), address_family])
        return {
            "interface_index": int(raw["interface_index"]),
            "address_family": str(raw["address_family"]),
            "interface_alias": str(raw["interface_alias"]),
            "automatic_metric": bool(raw["automatic_metric"]),
            "interface_metric": (
                None if bool(raw["automatic_metric"])
                else int(raw["interface_metric"])
            ),
        }

    def set_interface_metric(
        self,
        interface_index: int,
        address_family: str,
        *,
        automatic_metric: bool,
        metric: int | None,
    ) -> dict[str, Any]:
        if automatic_metric:
            script = r'''
param([int]$I, [string]$F)
Set-NetIPInterface -InterfaceIndex $I -AddressFamily $F -AutomaticMetric Enabled -Confirm:$false -ErrorAction Stop
$x = Get-NetIPInterface -InterfaceIndex $I -AddressFamily $F -ErrorAction Stop | Select-Object -First 1
[pscustomobject]@{
  interface_index = [int]$x.InterfaceIndex
  address_family = [string]$x.AddressFamily
  interface_alias = [string]$x.InterfaceAlias
  automatic_metric = ([string]$x.AutomaticMetric -eq "Enabled")
  interface_metric = [int]$x.InterfaceMetric
} | ConvertTo-Json -Compress
'''
            raw = self._json(script, [str(interface_index), address_family])
        else:
            if metric is None:
                raise RepairExecutorError("manual interface metric requires a metric")
            script = r'''
param([int]$I, [string]$F, [int]$M)
Set-NetIPInterface -InterfaceIndex $I -AddressFamily $F -AutomaticMetric Disabled -InterfaceMetric $M -Confirm:$false -ErrorAction Stop
$x = Get-NetIPInterface -InterfaceIndex $I -AddressFamily $F -ErrorAction Stop | Select-Object -First 1
[pscustomobject]@{
  interface_index = [int]$x.InterfaceIndex
  address_family = [string]$x.AddressFamily
  interface_alias = [string]$x.InterfaceAlias
  automatic_metric = ([string]$x.AutomaticMetric -eq "Enabled")
  interface_metric = [int]$x.InterfaceMetric
} | ConvertTo-Json -Compress
'''
            raw = self._json(
                script,
                [str(interface_index), address_family, str(metric)],
            )
        return {
            "interface_index": int(raw["interface_index"]),
            "address_family": str(raw["address_family"]),
            "interface_alias": str(raw["interface_alias"]),
            "automatic_metric": bool(raw["automatic_metric"]),
            "interface_metric": (
                None if bool(raw["automatic_metric"])
                else int(raw["interface_metric"])
            ),
        }

    def inspect_process_priority(self, pid: int) -> dict[str, Any]:
        script = r'''
param([int]$P)
$x = Get-Process -Id $P -ErrorAction Stop
[pscustomobject]@{
  pid = [int]$x.Id
  process_name = [string]$x.ProcessName
  start_time_utc_ticks = [long]$x.StartTime.ToUniversalTime().Ticks
  priority = [string]$x.PriorityClass
} | ConvertTo-Json -Compress
'''
        raw = self._json(script, [str(pid)])
        return {
            "pid": int(raw["pid"]),
            "process_name": str(raw["process_name"]),
            "start_time_utc_ticks": int(raw["start_time_utc_ticks"]),
            "priority": str(raw["priority"]),
        }

    def set_process_priority(
        self,
        pid: int,
        *,
        expected_start_ticks: int,
        priority: str,
    ) -> dict[str, Any]:
        script = r'''
param([int]$P, [long]$Ticks, [string]$Priority)
$x = Get-Process -Id $P -ErrorAction Stop
$currentTicks = [long]$x.StartTime.ToUniversalTime().Ticks
if ($currentTicks -ne $Ticks) { throw "process identity changed; refusing PID reuse" }
$x.PriorityClass = $Priority
$x.Refresh()
[pscustomobject]@{
  pid = [int]$x.Id
  process_name = [string]$x.ProcessName
  start_time_utc_ticks = [long]$x.StartTime.ToUniversalTime().Ticks
  priority = [string]$x.PriorityClass
} | ConvertTo-Json -Compress
'''
        return self._json(
            script,
            [str(pid), str(expected_start_ticks), priority],
        )


class BoundedRepairExecutor:
    action_key: str

    def __init__(self, backend: RepairBackend):
        self.backend = backend

    def normalize(self, params: dict[str, Any]) -> dict[str, Any]:
        return normalize_params(self.action_key, params)

    def inspect(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def apply(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def rollback(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def expected_applied_state(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def state_matches(
        self,
        observed: dict[str, Any],
        expected: dict[str, Any],
    ) -> bool:
        return sha256_json(observed) == sha256_json(expected)


class InterfaceMetricExecutor(BoundedRepairExecutor):
    action_key = "windows.interface.metric"

    def inspect(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.inspect_interface_metric(
            p["interface_index"],
            p["address_family"],
        )

    def expected_applied_state(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return {
            "interface_index": p["interface_index"],
            "address_family": p["address_family"],
            "interface_alias": before["interface_alias"],
            "automatic_metric": False,
            "interface_metric": p["metric"],
        }

    def apply(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.set_interface_metric(
            p["interface_index"],
            p["address_family"],
            automatic_metric=False,
            metric=p["metric"],
        )

    def rollback(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.set_interface_metric(
            p["interface_index"],
            p["address_family"],
            automatic_metric=bool(before["automatic_metric"]),
            metric=before.get("interface_metric"),
        )


class ProcessPriorityExecutor(BoundedRepairExecutor):
    action_key = "windows.process.priority"

    def inspect(self, params: dict[str, Any]) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.inspect_process_priority(p["pid"])

    def expected_applied_state(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return {
            "pid": before["pid"],
            "process_name": before["process_name"],
            "start_time_utc_ticks": before["start_time_utc_ticks"],
            "priority": p["priority"],
        }

    def apply(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.set_process_priority(
            p["pid"],
            expected_start_ticks=int(before["start_time_utc_ticks"]),
            priority=p["priority"],
        )

    def rollback(
        self,
        params: dict[str, Any],
        before: dict[str, Any],
    ) -> dict[str, Any]:
        p = self.normalize(params)
        return self.backend.set_process_priority(
            p["pid"],
            expected_start_ticks=int(before["start_time_utc_ticks"]),
            priority=str(before["priority"]),
        )


def get_executor(
    action_key: str,
    backend: RepairBackend | None = None,
) -> BoundedRepairExecutor:
    actual_backend = backend or WindowsPowerShellBackend()
    if action_key == InterfaceMetricExecutor.action_key:
        return InterfaceMetricExecutor(actual_backend)
    if action_key == ProcessPriorityExecutor.action_key:
        return ProcessPriorityExecutor(actual_backend)
    raise RepairExecutorError(f"unknown bounded repair action: {action_key}")
