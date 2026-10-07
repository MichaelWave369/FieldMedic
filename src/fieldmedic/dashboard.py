from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any

from .discovery import discover_engines
from .nbg_memory import DiagnosticMemoryStore
from .repair_executors import list_repair_actions
from .release_receipt import build_release_receipt


def _case_rows(home: Path) -> list[dict[str, Any]]:
    root = home / "cases"
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for case_file in sorted(root.glob("*/case.json")):
        try:
            value = json.loads(case_file.read_text(encoding="utf-8"))
            rows.append({
                "case_id": str(value.get("case_id", case_file.parent.name)),
                "symptom": str(value.get("symptom", "")),
                "domain": str(value.get("routing", {}).get("domain", "unknown")),
                "errors": len(value.get("errors", [])),
                "path": str(case_file.parent),
            })
        except Exception as exc:
            rows.append({
                "case_id": case_file.parent.name,
                "symptom": "",
                "domain": "unreadable",
                "errors": 1,
                "path": str(case_file.parent),
                "error": str(exc),
            })
    return rows


def build_dashboard_model(
    *,
    home: Path,
    drivemedic: str | None = None,
    netmedic: str | None = None,
) -> dict[str, Any]:
    discovery = discover_engines(drivemedic=drivemedic, netmedic=netmedic)
    memory = DiagnosticMemoryStore(home / "memory" / "nbg").stats()
    receipt = build_release_receipt(
        home=home,
        drivemedic=drivemedic,
        netmedic=netmedic,
    )
    return {
        "schema": "field-medic-dashboard-v1",
        "engines": discovery,
        "cases": _case_rows(home),
        "memory": memory,
        "repair_actions": list_repair_actions(),
        "release_receipt": receipt,
    }


def render_dashboard(model: dict[str, Any]) -> str:
    engines = model["engines"]
    cases = model["cases"]
    memory = model["memory"]
    receipt = model["release_receipt"]

    def engine_card(name: str) -> str:
        item = engines[name]
        status = "READY" if item["present"] and item["healthy"] is not False else "NOT READY"
        return f"""
        <section class="card">
          <h2>{escape(name.title())}</h2>
          <p class="status">{escape(status)}</p>
          <dl>
            <dt>Version</dt><dd>{escape(str(item.get("version") or "unknown"))}</dd>
            <dt>Path</dt><dd>{escape(str(item.get("path") or "not found"))}</dd>
            <dt>Discovered by</dt><dd>{escape(str(item.get("discovered_by") or "n/a"))}</dd>
          </dl>
        </section>
        """

    case_html = "".join(
        f"<tr><td>{escape(row['case_id'])}</td><td>{escape(row['domain'])}</td>"
        f"<td>{escape(row['symptom'])}</td><td>{row['errors']}</td></tr>"
        for row in cases
    ) or '<tr><td colspan="4">No cases yet.</td></tr>'

    actions = "".join(
        f"<li><strong>{escape(item['action_key'])}</strong> — {escape(item['description'])}</li>"
        for item in model["repair_actions"]
    )

    gates = "".join(
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
        for key, value in receipt["release_gates"].items()
    )

    raw = escape(json.dumps(model, indent=2, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Field Medic Operator Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#111;color:#eee}}
main{{max-width:1100px;margin:auto;padding:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.card{{background:#1b1b1b;border:1px solid #333;border-radius:12px;padding:18px}}
.status{{font-weight:700}}
table{{width:100%;border-collapse:collapse}}
td,th{{padding:8px;border-bottom:1px solid #333;text-align:left;vertical-align:top}}
code,pre{{background:#080808;padding:2px 5px;border-radius:4px}}
pre{{overflow:auto;padding:12px}}
small{{color:#aaa}}
</style>
</head>
<body><main>
<h1>Field Medic</h1>
<p>Local operator dashboard. This file is a read-only snapshot; it grants no authority.</p>
<div class="grid">{engine_card("drivemedic")}{engine_card("netmedic")}</div>
<section class="card"><h2>Cases</h2>
<table><thead><tr><th>Case</th><th>Domain</th><th>Symptom</th><th>Errors</th></tr></thead>
<tbody>{case_html}</tbody></table></section>
<section class="card"><h2>NBG Memory</h2>
<p>Records: {memory.get("records",0)} · Transitions: {memory.get("transitions",0)} · Admissions: {memory.get("admissions",0)}</p>
</section>
<section class="card"><h2>Bounded Repair Registry</h2><ul>{actions}</ul></section>
<section class="card"><h2>Release Gates</h2><table>{gates}</table>
<p><small>Receipt SHA-256: {escape(receipt["receipt_sha256"])}</small></p></section>
<details class="card"><summary>Raw governed dashboard model</summary><pre>{raw}</pre></details>
</main></body></html>"""


def write_dashboard(
    output: Path,
    *,
    home: Path,
    drivemedic: str | None = None,
    netmedic: str | None = None,
) -> dict[str, Any]:
    model = build_dashboard_model(
        home=home,
        drivemedic=drivemedic,
        netmedic=netmedic,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(model), encoding="utf-8")
    return {
        "schema": "field-medic-dashboard-write-v1",
        "path": str(output),
        "case_count": len(model["cases"]),
        "ready_for_diagnostics": model["engines"]["ready_for_diagnostics"],
        "release_receipt_sha256": model["release_receipt"]["receipt_sha256"],
    }
