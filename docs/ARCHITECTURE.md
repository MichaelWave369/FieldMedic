# Architecture

## 1. Product boundaries

Field Medic does not absorb DriveMedic or NetMedic. Each remains independently testable and independently releasable.

### DriveMedic
Authoritative for **host observations** and its own guided repair-verification sessions.

### NetMedic
Authoritative for **network observations**, experimental protocol state, evidence provenance/governance, and its own recovery verification artifacts.

### Agent Medic
Authoritative for **nothing it did not directly observe or govern**. It may ingest evidence, correlate it, form explicitly labeled hypotheses, route to specialists, and propose bounded next steps.

## 2. Shared evidence envelope

The envelope preserves the source payload unchanged and adds only cross-system metadata:

- case identity
- source identity
- ingestion time
- category
- claim class
- canonical SHA-256 of the payload
- explicit `causal_claim`
- provenance

The first version always emits `causal_claim=false` for adapter observations.

## 3. Sparse reasoning

Agent Medic is designed for the same economical reasoning principle as BrainC:

```text
continuous deterministic measurement
        -> anomaly / symptom relevance
        -> sparse evidence collection
        -> cheap routing
        -> specialist reasoning if needed
        -> synthesis
        -> proposal
        -> operator / Reality Gate
        -> bounded action
        -> independent verification
```

Large models are not in the telemetry loop.

## 4. NBG boundary

v0.1 writes `nbg-candidate.json` but does not admit it into NBG. Admission is a later governed operation. This keeps diagnostic memory from silently turning an unverified inference into durable truth.

## 5. BrainC boundary

The deterministic router is the v0.1 fallback. BrainC can later consume the same symptom/evidence envelope and return specialist/model routing decisions. BrainC does not gain execution authority by being a better router.
