# Adapter contract

## DriveMedic

v0.1 consumes documented machine-readable commands:

```text
drivemedic self-check-json
drivemedic status-json
drivemedic timeline-json <hours> <max-points>
```

The adapter does not call `repair-start` or any state-changing path.

## NetMedic

v0.1 creates a temporary privacy-safe snapshot:

```text
netmedic --report <temp.json> --samples 3 --dns-samples 2 --redact-report --omit-raw-evidence
```

The source report is then wrapped unchanged in a Field Medic evidence envelope. v0.1 does not mutate NetMedic cases, protocols, governance ledgers, or trust roots.
