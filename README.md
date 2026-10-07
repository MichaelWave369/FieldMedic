# Field Medic v0.6.0

**Field Medic** is the orchestration layer above two independent diagnostic engines:

- **DriveMedic** observes and verifies host / Windows state.
- **NetMedic** measures network state, runs controlled experiments, and governs evidence.
- **Agent Medic** correlates evidence, proposes the next diagnostic step, and remains subordinate to operator authority.

The engines are intentionally **not merged**. Field Medic speaks to each through adapters and translates their outputs into a shared, append-only evidence contract.

## Core rule

> Measurement is not inference. Inference is not authority. A recommendation is not an executed action.

Generic Agent Medic authority remains limited to:

1. **OBSERVE** existing machine-readable evidence.
2. **NORMALIZE** it without rewriting source payloads.
3. **CORRELATE** host/network evidence by time and case.
4. **ROUTE** a case toward host, network, mixed, or unknown specialists.
5. **PROPOSE** a next bounded diagnostic step.

Generic **EXECUTE remains denied**. Rung 5 adds a separate Repair Gate that can admit only registered, reversible, hash-bound repair actions after explicit operator authorization and live preflight checks.

## Quick start

Requires Python 3.11+ and no third-party runtime dependencies.

```powershell
python -m pip install -e .
fieldmedic health --drivemedic "C:\\Program Files\\DriveMedic\\drivemedic.exe" --netmedic "C:\\Tools\\netmedic.exe"
fieldmedic doctor "internet freezes for 10 seconds" --drivemedic "...\\drivemedic.exe" --netmedic "...\\netmedic.exe"
fieldmedic specialists
fieldmedic models
# Optional: let the selected local Ollama model refine the governed synthesis
fieldmedic doctor "wifi drops when Windows freezes" --drivemedic "..." --netmedic "..." --local-reasoning
```

You can also set:

```text
DRIVEMEDIC_BIN=...
NETMEDIC_BIN=...
FIELDMEDIC_HOME=...
```

## Architecture

```text
                         ┌─────────────────────┐
                         │     Agent Medic     │
                         │ correlate / route   │
                         │ explain / propose   │
                         └──────────┬──────────┘
                                    │
                          Field Medic contracts
                      ┌─────────────┴─────────────┐
                      │                           │
              ┌───────▼────────┐          ┌──────▼─────────┐
              │   DriveMedic   │          │    NetMedic    │
              │ host evidence  │          │ network/evidence│
              └───────┬────────┘          └──────┬─────────┘
                      │                           │
                      └────────────┬──────────────┘
                                   ▼
                         append-only case ledger
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
                   NBG           BrainC       Reality Gate
                 memory          routing        authority
                  hook            hook           hook
```

See `docs/ARCHITECTURE.md`, `docs/GOVERNANCE.md`, `docs/CORRELATION.md`, and `docs/ROADMAP.md`.

## Native correlation

Rung 1 adds deterministic timestamp normalization, a cross-source evidence/event graph, bounded co-occurrence windows, diagnostic-tension detection, same-subject contradiction detection, and a temporal-association score that is explicitly **not** probability or causal confidence. Correlation receipts always retain `causal_claim=false`.

## Specialist reasoning

Rung 2 adds bounded specialist capability descriptors, an optional BrainC routing bridge, localhost-only Ollama discovery, cheap-local-first model selection, sparse escalation rules, and evidence-cited synthesis receipts.

The reasoning policy is intentionally asymmetric:

```text
deterministic evidence
  -> cheapest adequate local utility model
  -> local specialist model when needed
  -> frontier model only after unresolved local specialist work
```

BrainC can choose specialists and reasoning tier, but cannot create observations, grant authority, invent unknown specialists, or open the frontier gate. Local model synthesis is opt-in and is rejected if it invents evidence IDs or asserts causation.

See `docs/SPECIALIST_PROTOCOL.md`.

## Governed experiments

Rung 3 binds Agent Medic to NetMedic's native frozen-protocol workflow without granting generic execution authority.

~~~text
Agent Medic proposal
  -> SHA-256-bound operator approval
  -> NetMedic protocol freeze
  -> fresh physical confirmations + preflight
  -> one planned-arm capture
  -> DriveMedic before/after host brackets
  -> matched analysis
  -> FieldMedic evidence ledger
~~~

A capture approval must explicitly authorize both preflight and capture, expires, and requires fresh confirmations of the planned arm, machine stability, test context, and every locked control. The approval cannot authorize repairs.

Example workflow:

~~~powershell
fieldmedic experiment-propose --case-id CASE --netmedic-case C:\\Cases\\wifi --name "Wi-Fi vs Ethernet" --design-key connection --arm-a wifi --arm-b ethernet --test-label ethernet-ab --control vpn=off

fieldmedic experiment-approve fieldmedic-experiment-proposal.json --operator "local operator" --scope netmedic.protocol.freeze

fieldmedic experiment-freeze fieldmedic-experiment-proposal.json fieldmedic-experiment-proposal-approval.json --netmedic C:\\Tools\\netmedic.exe
~~~

Capture approval is intentionally separate and should be created only when the physical arm and locked controls are actually confirmed.

See `docs/GOVERNED_EXPERIMENTS.md`.

## NBG diagnostic memory

Rung 4 turns completed cases into governed, model-independent diagnostic memory using the live NBG epistemic envelope.

New cases remain `INFERRED` candidates until explicitly admitted:

~~~text
fieldmedic memory-admit CASE_ID --operator "local operator"
~~~

A verified outcome derives a new `VERIFIED` descendant rather than rewriting the original memory:

~~~text
fieldmedic memory-verify CASE_ID --operator "local operator" --outcome VERIFIED_FAILURE --details "rollback did not help"
~~~

Verified success, failure and no-effect outcomes carry equal epistemic routing weight. Negative cases are retained instead of being quietly selected out because they were inconvenient.

Prior cases influence routing through deterministic symptom/domain/specialist similarity. They may add specialist hints, but never remove specialists required by current evidence. One root NBG lineage contributes at most one routing vote, so derivation and repetition cannot manufacture extra evidence.

Inspect memory without invoking a model:

~~~text
fieldmedic memory-query "wifi disconnects while Windows freezes" --domain mixed --specialist network.wifi
fieldmedic memory-stats
~~~

Every match preserves its memory ID, record fingerprint, origin, outcome, evidence, lineage and score components. Memory similarity is not causation, verification, or action authority.

See `docs/NBG_DIAGNOSTIC_MEMORY.md`.

## Bounded repairs

Rung 5 introduces a separate Repair Gate without giving Agent Medic a generic shell.

Initial executable actions are deliberately tiny:

- `windows.interface.metric`: set one Windows IPv4/IPv6 interface metric, preserving automatic/manual pre-state for rollback;
- `windows.process.priority`: set one process to `BelowNormal` or `Normal`, pinned to PID + process start identity so PID reuse cannot redirect the action.

Inspect the registry:

~~~text
fieldmedic repair-actions
~~~

A repair is a multi-step transaction:

~~~text
repair-propose
  -> repair-prepare
  -> repair-authorize
  -> repair-execute
  -> repair-verify
  -> memory-verify
~~~

Example proposal:

~~~powershell
fieldmedic repair-propose CASE_ID --action windows.interface.metric --param interface_index=12 --param address_family=IPv4 --param metric=10
~~~

`repair-prepare` inspects the live target and freezes both the exact pre-state and exact rollback state. The operator grant binds the proposal SHA-256 and preflight SHA-256. Any state drift after preflight causes execution to be denied.

Both DriveMedic and NetMedic must successfully capture the pre-action baseline before mutation. A typed postcondition must then pass and both engines must capture post-action evidence. If the postcondition fails or independent post-action capture fails, FieldMedic automatically rolls back to the exact authorized pre-state when that rollback remains safe.

A successful mutation is **not** called a fix. It remains `EXECUTED_PENDING_OUTCOME_VERIFICATION`; later measurement remains `MEASURED_PENDING_OPERATOR_OUTCOME` until an explicit NBG outcome verification records success, failure, no effect, or contradiction.

CI qualifies the governance/state-machine behavior with deterministic fake mutation backends. Live Windows mutation qualification remains a stable-release gate.

See `docs/BOUNDED_REPAIRS.md`.

## Free and open source

Field Medic is released under the **MIT License** so people can use it, inspect it, modify it, redistribute it, and build on it without asking permission.

This repository does not vendor DriveMedic or NetMedic source code. They remain independent engines connected through machine-readable interfaces.
