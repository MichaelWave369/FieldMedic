# Governance

Field Medic uses four authority classes:

| Class | Meaning | Agent Medic v0.1 |
|---|---|---|
| OBSERVE | read evidence | allowed |
| INFER | create labeled hypotheses/correlations | allowed |
| PROPOSE | recommend a diagnostic next step | allowed |
| EXECUTE | change host/network state | **denied** |

## Rules

1. Source evidence is immutable inside the Field Medic ledger.
2. Normalization must not erase the original payload.
3. Temporal association must not be serialized as causation.
4. Model output is an inference artifact, never a sensor reading.
5. No repair/change command is available through the v0.1 Agent Medic executor.
6. Future execution must require explicit operator authorization, a bounded action contract, rollback information where possible, and post-action verification.
7. NetMedic's evidence governance remains authoritative for NetMedic evidence. Field Medic must not bypass quarantine, dispute, withdrawal, resolution, signature, or local trust-policy state.
