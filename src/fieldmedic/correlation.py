from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import EvidenceEnvelope


_TIMESTAMP_KEYS = {
    "timestamp", "time", "ts", "datetime", "observed_at", "occurred_at",
    "created_at", "recorded_at", "collected_at", "started_at", "ended_at",
}
_SUBJECT_KEYS = ("subject", "component", "interface", "adapter", "device", "name", "category")
_SUMMARY_KEYS = ("summary", "message", "event", "type", "name", "status", "state", "result")
_NEGATIVE = ("fail", "error", "down", "disconnect", "timeout", "unhealthy", "degrad", "reset", "crash", "freeze", "lost")
_POSITIVE = ("ok", "healthy", "up", "connected", "success", "normal", "pass", "ready")


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    evidence_id: str
    source: str
    observed_at: str
    epoch_seconds: float
    path: str
    summary: str
    subject: str | None
    state: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_timestamp(value: Any) -> str | None:
    dt = _parse_time(value)
    if dt is None:
        return None
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _classify_state(value: Any) -> str | None:
    text = str(value).lower()
    if any(token in text for token in _NEGATIVE):
        return "unhealthy"
    if any(token in text for token in _POSITIVE):
        return "healthy"
    return None


def _first_text(item: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            return str(value).strip()
    return None


def _event_from_dict(evidence: EvidenceEnvelope, item: dict[str, Any], path: str, ordinal: int) -> NormalizedEvent | None:
    timestamp_value = None
    for key, value in item.items():
        if key.lower() in _TIMESTAMP_KEYS:
            timestamp_value = value
            break
    normalized = normalize_timestamp(timestamp_value)
    if normalized is None:
        return None

    dt = _parse_time(timestamp_value)
    assert dt is not None
    summary = _first_text(item, _SUMMARY_KEYS) or evidence.summary
    subject = _first_text(item, _SUBJECT_KEYS)
    state_basis = " ".join(
        str(item.get(key, "")) for key in ("status", "state", "result", "message", "summary")
    )
    return NormalizedEvent(
        event_id=f"{evidence.evidence_id}:event:{ordinal}",
        evidence_id=evidence.evidence_id,
        source=evidence.source,
        observed_at=normalized,
        epoch_seconds=dt.timestamp(),
        path=path,
        summary=summary,
        subject=subject.lower() if subject else None,
        state=_classify_state(state_basis),
    )


def extract_events(evidence: EvidenceEnvelope) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            event = _event_from_dict(evidence, value, path, len(events))
            if event is not None:
                events.append(event)
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(evidence.payload, "payload")
    if events:
        return events

    fallback = _parse_time(evidence.observed_at)
    if fallback is None:
        return []
    return [
        NormalizedEvent(
            event_id=f"{evidence.evidence_id}:event:0",
            evidence_id=evidence.evidence_id,
            source=evidence.source,
            observed_at=normalize_timestamp(evidence.observed_at) or evidence.observed_at,
            epoch_seconds=fallback.timestamp(),
            path="envelope",
            summary=evidence.summary,
            subject=evidence.category.lower() if evidence.category else None,
            state=_classify_state(evidence.summary),
        )
    ]


def _association_strength(delta_seconds: float, pair_count: int) -> float:
    if delta_seconds <= 5:
        base = 0.75
    elif delta_seconds <= 30:
        base = 0.60
    elif delta_seconds <= 120:
        base = 0.40
    else:
        base = 0.20
    return round(min(0.85, base + min(max(pair_count - 1, 0), 5) * 0.02), 2)


def correlate_evidence(
    evidence: Iterable[EvidenceEnvelope],
    *,
    window_seconds: int = 30,
) -> dict[str, Any]:
    items = list(evidence)
    events = [event for item in items for event in extract_events(item)]
    events.sort(key=lambda event: (event.epoch_seconds, event.event_id))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for item in items:
        nodes.append({"id": item.evidence_id, "kind": "evidence", "source": item.source})
    for event in events:
        nodes.append({
            "id": event.event_id,
            "kind": "event",
            "source": event.source,
            "observed_at": event.observed_at,
            "summary": event.summary,
            "subject": event.subject,
            "state": event.state,
        })
        edges.append({"from": event.evidence_id, "to": event.event_id, "relation": "CONTAINS"})

    pairs: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    tensions: list[dict[str, Any]] = []

    for index, left in enumerate(events):
        for right in events[index + 1:]:
            if left.source == right.source:
                continue
            delta = abs(right.epoch_seconds - left.epoch_seconds)
            if delta > window_seconds:
                if right.epoch_seconds >= left.epoch_seconds:
                    break
                continue
            pair = {
                "left_event_id": left.event_id,
                "right_event_id": right.event_id,
                "delta_seconds": round(delta, 3),
                "left_source": left.source,
                "right_source": right.source,
            }
            pairs.append(pair)
            edges.append({
                "from": left.event_id,
                "to": right.event_id,
                "relation": "CO_OCCURS_WITH",
                "delta_seconds": round(delta, 3),
            })

            opposite = {left.state, right.state} == {"healthy", "unhealthy"}
            same_subject = bool(left.subject and right.subject and left.subject == right.subject)
            if opposite and same_subject:
                contradiction = {
                    **pair,
                    "subject": left.subject,
                    "reason": "same subject has opposite normalized states inside correlation window",
                }
                contradictions.append(contradiction)
                edges.append({
                    "from": left.event_id,
                    "to": right.event_id,
                    "relation": "CONTRADICTS",
                    "subject": left.subject,
                })
            elif opposite:
                tensions.append({
                    **pair,
                    "left_subject": left.subject,
                    "right_subject": right.subject,
                    "reason": "different subjects show opposite health states in the same time window",
                })

    nearest = min((pair["delta_seconds"] for pair in pairs), default=None)
    strength = 0.0 if nearest is None else _association_strength(nearest, len(pairs))

    return {
        "schema": "field-medic-correlation-v1",
        "causal_claim": False,
        "window_seconds": window_seconds,
        "source_count": len({item.source for item in items}),
        "evidence_ids": [item.evidence_id for item in items],
        "event_count": len(events),
        "cross_source_pairs": pairs,
        "contradictions": contradictions,
        "diagnostic_tensions": tensions,
        "temporal_association_strength": strength,
        "association_strength_semantics": "deterministic proximity score, not probability and not causal confidence",
        "graph": {"nodes": nodes, "edges": edges},
        "limits": [
            "temporal association does not establish causation",
            "absence of extracted events does not prove absence of an incident",
            "contradictions require the same normalized subject with opposite states",
        ],
    }
