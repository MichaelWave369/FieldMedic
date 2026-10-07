# Field Medic v0.4.0

**Field Medic** is the orchestration layer above two independent diagnostic engines:

- **DriveMedic** observes and verifies host / Windows state.
- **NetMedic** measures network state, runs controlled experiments, and governs evidence.
- **Agent Medic** correlates evidence, proposes the next diagnostic step, and remains subordinate to operator authority.

The engines are intentionally **not merged**. Field Medic speaks to each through adapters and translates their outputs into a shared, append-only evidence contract.

## Core rule

> Measurement is not inference. Inference is not authority. A recommendation is not an executed action.

Field Medic grants Agent Medic only these capabilities:

1. **OBSERVE** existing machine-readable evidence.
2. **NORMALIZE** it without rewriting source payloads.
3. **CORRELATE** host/network evidence by time and case.
4. **ROUTE** a case toward host, network, mixed, or unknown specialists.
5. **PROPOSE** a next bounded diagnostic step.

It **cannot execute repairs**. Execution is fail-closed in this bootstrap.

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

## Free and open source

Field Medic is released under the **MIT License** so people can use it, inspect it, modify it, redistribute it, and build on it without asking permission.

This repository does not vendor DriveMedic or NetMedic source code. They remain independent engines connected through machine-readable interfaces.
