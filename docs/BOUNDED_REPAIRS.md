# Bounded Repair Executors

Rung 5 introduces execution without granting Agent Medic a generic shell.

## Authority model

The original Reality Gate remains fail-closed for generic `EXECUTE`.

Repair execution uses a separate, narrower authority path:

```text
evidence-backed case
  -> typed repair proposal
  -> live preflight / rollback capture
  -> exact proposal + preflight operator grant
  -> stale-state check
  -> typed executor
  -> typed postcondition
  -> DriveMedic + NetMedic post-action measurement
  -> later operator outcome classification
```

The grant contains:

- the exact proposal SHA-256;
- the exact preflight SHA-256;
- case ID;
- registered action key;
- short expiry;
- `repair.execute` and exact rollback authority;
- `generic_shell_authorized=false`.

No model, BrainC route, memory match, or synthesis receipt can manufacture this grant.

## Initial executor registry

### windows.interface.metric

Parameters:

- `interface_index`: positive integer;
- `address_family`: `IPv4` or `IPv6`;
- `metric`: integer 1–9999.

Preflight captures the interface identity plus whether Windows was using an automatic or manual metric. Rollback restores the exact captured configuration class and, for manual configuration, the prior metric.

This action requires current NetMedic evidence in the case.

### windows.process.priority

Parameters:

- `pid`: positive integer;
- `priority`: only `BelowNormal` or `Normal`.

The executor deliberately refuses High/RealTime classes. Preflight captures process name, start-time identity, and prior priority. Execution and rollback both require the same process start-time identity, preventing PID reuse from redirecting a repair at another process.

This action requires current DriveMedic evidence in the case.

## No arbitrary command surface

The repair CLI accepts only a registered action key plus action-specific parameters. Extra parameter names are rejected.

The built-in Windows backend contains fixed PowerShell programs. User/model content is passed only as validated primitive values. There is no `shell=True`, arbitrary script string, command template, executable path, or generic PowerShell argument exposed through the repair proposal.

## Preconditions

Execution is denied when:

- no DriveMedic/NetMedic source evidence exists;
- the action's required source is absent;
- the proposal cites non-source evidence;
- same-subject contradictions remain unresolved;
- the preflight or grant fingerprint is invalid;
- proposal/preflight/grant IDs or hashes do not match;
- the preflight or grant expired;
- the target state changed after preflight;
- both independent verifiers are not configured.

## Rollback

Every registered repair is reversible.

The original operator grant pre-authorizes the **exact** captured rollback state. This lets FieldMedic automatically roll back inside the same transaction when:

- the typed postcondition fails; or
- independent post-action verifier capture fails.

A later manual rollback is also bounded. It proceeds only if the target still matches the exact state FieldMedic previously applied. If anything else changed the target afterward, rollback fails closed instead of overwriting newer state.

## Verification

Repair execution never emits a `FIXED` outcome.

A successful mutation is:

```text
EXECUTED_PENDING_OUTCOME_VERIFICATION
```

Later `repair-verify` captures fresh DriveMedic and NetMedic evidence plus the typed target state and yields either:

- `MEASURED_PENDING_OPERATOR_OUTCOME`; or
- `TARGET_STATE_DRIFTED`.

The final diagnostic outcome remains an explicit NBG verification step such as `VERIFIED_SUCCESS`, `VERIFIED_FAILURE`, or `VERIFIED_NO_EFFECT`.

This prevents the executor from treating successful mutation as successful diagnosis.

## Live qualification boundary

CI qualifies schemas, authority binding, stale-state rejection, exact rollback semantics, PID-reuse protection, source-evidence gates, independent verifier requirements, and transaction behavior using deterministic fake backends.

It does **not** claim that a GitHub runner performed live Windows network/process mutations. Live Windows executor qualification remains a release gate before Field Supply stable promotion.
