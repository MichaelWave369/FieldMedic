# Field Medic v0.1.0 Bootstrap

**Field Medic** is the orchestration layer above two independent diagnostic engines:

- **DriveMedic** observes and verifies host / Windows state.
- **NetMedic** measures network state, runs controlled experiments, and governs evidence.
- **Agent Medic** correlates evidence, proposes the next diagnostic step, and remains subordinate to operator authority.

The engines are intentionally **not merged**. Field Medic speaks to each through adapters and translates their outputs into a shared, append-only evidence contract.

## Core rule

> Measurement is not inference. Inference is not authority. A recommendation is not an executed action.

v0.1 therefore grants Agent Medic only these capabilities:

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

See `docs/ARCHITECTURE.md`, `docs/GOVERNANCE.md`, and `docs/ROADMAP.md`.

## Important source/licensing boundary

This bootstrap contains **no NetMedic source code** and no DriveMedic source code. It calls installed binaries through documented machine-readable surfaces. DriveMedic and NetMedic retain their own licenses and release gates.
