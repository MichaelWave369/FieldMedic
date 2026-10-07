from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any


@dataclass(frozen=True)
class Specialist:
    specialist_id: str
    name: str
    domains: tuple[str, ...]
    capabilities: tuple[str, ...]
    preferred_tier: str
    max_authority: str = "infer"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SPECIALISTS: dict[str, Specialist] = {
    "host.general": Specialist(
        "host.general", "Host Generalist", ("host", "mixed", "unknown"),
        ("host triage", "Windows state review", "timeline review"), "utility"
    ),
    "host.windows": Specialist(
        "host.windows", "Windows Specialist", ("host", "mixed"),
        ("Windows events", "drivers", "updates", "boot", "services"), "utility"
    ),
    "host.storage": Specialist(
        "host.storage", "Storage Specialist", ("host", "mixed"),
        ("disk latency", "NVMe/SMART", "filesystem", "I/O contention"), "specialist"
    ),
    "host.process": Specialist(
        "host.process", "Process Specialist", ("host", "mixed"),
        ("process ancestry", "CPU/RAM contention", "application stalls"), "utility"
    ),
    "network.general": Specialist(
        "network.general", "Network Generalist", ("network", "mixed", "unknown"),
        ("network triage", "interface state", "path health"), "utility"
    ),
    "network.wifi": Specialist(
        "network.wifi", "Wi-Fi Specialist", ("network", "mixed"),
        ("association", "wireless adapter", "signal/path transitions"), "specialist"
    ),
    "network.dns": Specialist(
        "network.dns", "DNS Specialist", ("network", "mixed"),
        ("resolver behavior", "name resolution", "DNS comparison"), "utility"
    ),
    "network.routing": Specialist(
        "network.routing", "Routing Specialist", ("network", "mixed"),
        ("gateway", "route path", "latency/loss", "VPN"), "specialist"
    ),
    "case.correlation": Specialist(
        "case.correlation", "Correlation Specialist", ("mixed", "unknown"),
        ("cross-source timing", "contradictions", "diagnostic tensions"), "specialist"
    ),
    "case.evidence": Specialist(
        "case.evidence", "Evidence Steward", ("host", "network", "mixed", "unknown"),
        ("provenance", "claim classification", "evidence sufficiency"), "utility"
    ),
    "case.synthesis": Specialist(
        "case.synthesis", "Synthesis Specialist", ("host", "network", "mixed", "unknown"),
        ("evidence-cited synthesis", "uncertainty", "next-step framing"), "specialist"
    ),
}


def list_specialists() -> list[dict[str, Any]]:
    return [SPECIALISTS[key].to_dict() for key in sorted(SPECIALISTS)]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9-]+", text.lower()))


def plan_specialists(symptom: str, domain: str, correlation: dict[str, Any]) -> dict[str, Any]:
    tokens = _tokens(symptom)
    selected: list[str] = []
    reasons: list[str] = []

    def add(specialist_id: str, reason: str) -> None:
        if specialist_id not in selected:
            selected.append(specialist_id)
            reasons.append(f"{specialist_id}: {reason}")

    if domain in {"host", "mixed", "unknown"}:
        add("host.general", "host evidence is in scope")
    if domain in {"network", "mixed", "unknown"}:
        add("network.general", "network evidence is in scope")

    if tokens & {"windows", "driver", "boot", "update", "service", "services"}:
        add("host.windows", "Windows-specific symptom terms")
    if tokens & {"disk", "ssd", "nvme", "storage", "filesystem", "iops"}:
        add("host.storage", "storage-specific symptom terms")
    if tokens & {"process", "cpu", "ram", "memory", "application", "app"}:
        add("host.process", "process/resource symptom terms")
    if tokens & {"wifi", "wi-fi", "wireless", "association"}:
        add("network.wifi", "wireless-specific symptom terms")
    if tokens & {"dns", "resolver", "resolve", "hostname"}:
        add("network.dns", "DNS-specific symptom terms")
    if tokens & {"router", "route", "gateway", "vpn", "latency", "packet", "loss"}:
        add("network.routing", "path/routing symptom terms")

    contradictions = len(correlation.get("contradictions", []))
    tensions = len(correlation.get("diagnostic_tensions", []))
    pairs = len(correlation.get("cross_source_pairs", []))
    if domain in {"mixed", "unknown"} or contradictions or tensions or pairs:
        add("case.correlation", "cross-source interpretation is required")
    if contradictions or not correlation.get("evidence_ids"):
        add("case.evidence", "evidence consistency/sufficiency requires review")

    add("case.synthesis", "produce a bounded evidence-cited case synthesis")

    return {
        "schema": "field-medic-specialist-plan-v1",
        "specialist_ids": selected,
        "specialists": [SPECIALISTS[item].to_dict() for item in selected],
        "reasons": reasons,
        "authority_ceiling": "infer",
    }


def materialize_specialist_plan(
    specialist_ids: list[str],
    *,
    reasons: list[str] | None = None,
    source: str = "external-router",
) -> dict[str, Any]:
    unique = list(dict.fromkeys(specialist_ids))
    unknown = [item for item in unique if item not in SPECIALISTS]
    if unknown:
        raise ValueError(f"unknown specialist IDs: {unknown}")
    return {
        "schema": "field-medic-specialist-plan-v1",
        "specialist_ids": unique,
        "specialists": [SPECIALISTS[item].to_dict() for item in unique],
        "reasons": reasons or [f"{source}: selected {item}" for item in unique],
        "routing_source": source,
        "authority_ceiling": "infer",
    }
