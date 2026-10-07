# Native case correlation

Rung 1 adds deterministic correlation before any model reasoning.

## What it does

1. Extracts timestamped events from DriveMedic and NetMedic evidence payloads.
2. Normalizes ISO-8601, Unix seconds, and Unix milliseconds to UTC.
3. Builds an evidence/event reference graph.
4. Links cross-source events that fall inside a bounded time window.
5. Distinguishes:
   - **co-occurrence**: two events are temporally near each other;
   - **diagnostic tension**: different subjects report opposite health states nearby;
   - **contradiction**: the same normalized subject reports opposite states nearby.
6. Computes a bounded temporal-association score for routing/prioritization.

## What it does not do

It never converts proximity into causation.

The correlation receipt always carries:

```json
{
  "causal_claim": false,
  "association_strength_semantics": "deterministic proximity score, not probability and not causal confidence"
}
```

A future model may explain the receipt, but it must cite evidence IDs and preserve those limits.

## Fallback behavior

If a source payload contains no extractable event timestamp, the evidence envelope's own `observed_at` is used as a single coarse event. This keeps the graph complete while making no claim that the underlying incident occurred exactly at ingestion time.
