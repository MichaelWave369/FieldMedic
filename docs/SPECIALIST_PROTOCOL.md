# Agent Medic Specialist Protocol

Rung 2 separates **who should think** from **what is true**.

## Capability descriptors

Every specialist has a stable specialist ID, supported diagnostic domains, bounded capabilities, a preferred reasoning tier, and an authority ceiling.

The authority ceiling is currently **INFER** for every specialist.

## BrainC bridge

An optional BRAINC_ROUTER_BIN can receive one JSON routing request on stdin and return one JSON response on stdout. FieldMedic validates the response.

BrainC may recommend specialist IDs, a reasoning tier, whether further escalation is warranted, and textual routing reasons.

BrainC may not create sensor observations, grant itself authority, invent a specialist ID, invoke frontier reasoning while the frontier gate is closed, or execute a repair.

Invalid BrainC output is rejected and deterministic FieldMedic routing remains available.

## Local-first model policy

FieldMedic discovers local Ollama models from localhost only. The default policy is:

~~~text
deterministic evidence
  -> cheapest adequate local utility model
  -> local specialist model only when needed
  -> frontier eligibility only after unresolved specialist work
~~~

Rung 2 does not automatically call a frontier/cloud model.

## Synthesis receipts

Every diagnostic claim must cite one or more FieldMedic evidence IDs. Model prose without valid evidence references is not admitted as a synthesis receipt.

A synthesis receipt cannot set causal_claim=true and cannot raise its authority above infer.
