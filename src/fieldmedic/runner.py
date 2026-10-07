from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class ToolError(RuntimeError):
    pass


def run_tool(binary: str, args: list[str], timeout: int = 120) -> RunResult:
    path = Path(binary)
    if not path.exists():
        raise ToolError(f"binary not found: {binary}")
    cp = subprocess.run(
        [str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result = RunResult(tuple([str(path), *args]), cp.returncode, cp.stdout, cp.stderr)
    if cp.returncode != 0:
        raise ToolError(
            f"tool failed ({cp.returncode}): {' '.join(result.argv)}\n"
            f"stderr: {cp.stderr.strip()}\nstdout: {cp.stdout.strip()}"
        )
    return result
