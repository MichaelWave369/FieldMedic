# Governance

Field Medic separates generic Agent Medic authority from narrower purpose-built execution gates.

| Class | Meaning | Generic Agent Medic |
|---|---|---|
| OBSERVE | read evidence | allowed |
| INFER | create labeled hypotheses/correlations | allowed |
| PROPOSE | recommend a diagnostic next step | allowed |
| EXECUTE | arbitrary host/network state change | **denied** |

## Bounded execution

Generic `EXECUTE` remains denied by the Reality Gate.

Purpose-built subsystems may expose narrower authority only through their own contracts:

- the **Experiment Gate** admits explicitly approved diagnostic measurement scopes;
- the **Repair Gate** admits only registered, reversible repair actions bound to an exact proposal, exact live preflight state, short-lived operator grant, rollback state, and independent verification.

Neither gate exposes a generic shell or inherits authority from a model, BrainC route, memory match, or recommendation.

## Rules

1. Source evidence is immutable inside the Field Medic ledger.
2. Normalization must not erase the original payload.
3. Temporal association must not be serialized as causation.
4. Model output is an inference artifact, never a sensor reading.
5. Generic repair/change commands remain unavailable to Agent Medic.
6. Bounded repair execution requires explicit operator authorization, a registered typed action, current source evidence, live preconditions, exact rollback information, and DriveMedic + NetMedic verification.
7. Repair execution success is not diagnostic success. The executor may report that the requested state was applied; only later evidence may support a diagnostic outcome.
8. If the preflight state becomes stale, authority expires, source evidence is insufficient, same-subject contradictions remain unresolved, postconditions fail, or independent verification cannot be captured, execution fails closed or returns to the exact authorized rollback state.
9. NetMedic's evidence governance remains authoritative for NetMedic evidence. Field Medic must not bypass quarantine, dispute, withdrawal, resolution, signature, or local trust-policy state.
10. Memory similarity, repetition, model agreement, or confidence cannot grant execution authority.
