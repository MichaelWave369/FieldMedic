# NBG Diagnostic Memory

Rung 4 turns FieldMedic case history into governed diagnostic memory using the live NestedBubbleGear epistemic contract rather than a model-owned chat transcript.

## NBG compatibility

FieldMedic emits `NBG_EPISTEMIC_1` records with the same core fields used by NestedBubbleGear:

- `content`
- `epistemic.origin`
- `epistemic.confidence`
- `epistemic.evidence`
- `epistemic.lineage`
- `epistemic.authority`
- `validTime`
- `knownTime`
- `tags`
- `recordFingerprint`

FieldMedic mirrors NBG's stable JavaScript FNV-1a fingerprint semantics for its controlled diagnostic records. A pinned cross-language test vector prevents silent Python/JavaScript number-serialization drift.

The durable store remains local to FieldMedic. No NestedBubbleGear source is vendored.

## Memory is not fact

Every new FieldMedic case candidate begins as `INFERRED`.

It is retainable and reasoning-usable, but `actionAuthorized=false`.

A verified result does not rewrite the original inference. It derives a new `VERIFIED` memory with:

- a new memory ID;
- new verification evidence;
- parent/root lineage;
- an NBG-style epistemic transition receipt;
- `authorityChanged=false`.

The source inference remains replayable.

## Explicit admission

`doctor` writes `nbg-candidate.json`, but that file is not durable memory.

Admission requires:

~~~text
fieldmedic memory-admit CASE_ID --operator "local operator"
~~~

The admission receipt records the case, record fingerprint, local operator label, reason, known time, and the fact that the memory grants no action authority.

## Verified outcomes

Supported verified outcomes are:

- `VERIFIED_SUCCESS`
- `VERIFIED_FAILURE`
- `VERIFIED_NO_EFFECT`
- `VERIFIED_CONTRADICTION`

An admitted inference can be derived into a verified outcome with an explicit verification receipt:

~~~text
fieldmedic memory-verify CASE_ID --operator "local operator" --outcome VERIFIED_NO_EFFECT --details "Ethernet did not change the failure rate"
~~~

The command adds an operator verification evidence envelope to the case ledger. The operator label is provenance metadata, not independently authenticated identity. `VERIFIED` therefore means verified under the declared evidence path, not objective truth.

Success, failure and no-effect memories receive the same reliability weight when equally verified. Negative evidence is not discarded simply because it ruined a favorite hypothesis.

## Durable store

~~~text
memory/nbg/
  records.jsonl
  transitions.jsonl
  admissions.jsonl
~~~

All three are append-only.

## Model-independent case similarity

Routing memory uses deterministic features only:

- symptom-token Jaccard similarity;
- exact diagnostic-domain match;
- specialist-set overlap;
- epistemic reliability weight.

No embeddings, LLM calls or hidden model state are required.

Every returned match preserves:

- memory ID;
- record fingerprint;
- epistemic origin;
- outcome;
- evidence records;
- lineage;
- score components.

Similarity is not evidence and never changes epistemic origin.

## Routing boundary

Prior memory may add a known specialist hint. It may not:

- remove a specialist demanded by current evidence;
- create a sensor observation;
- promote an inference;
- claim causation;
- grant action authority.

Current evidence outranks remembered similarity. Corrupt memory fails closed and contributes no routing influence.

## Weight semantics

The memory reliability weight is an epistemic routing weight. It is not a probability that the memory is true, and it does not score evidence quality or source independence. Those remain separate governance questions.