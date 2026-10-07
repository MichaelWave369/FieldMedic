# Governed Experiments

Rung 3 lets Agent Medic propose controlled NetMedic experiments without granting generic execution authority.

## Boundary

The ordinary Reality Gate still denies generic EXECUTE.

A separate Experiment Gate can admit only these bounded diagnostic measurement scopes:

- netmedic.protocol.freeze
- netmedic.protocol.preflight
- netmedic.protocol.capture
- netmedic.protocol.matched

An experiment approval never grants repair authority.

## Immutable proposal + explicit approval

A proposal includes the FieldMedic case, NetMedic case, arm definition, trial count, pairing window, locked controls, and supporting evidence IDs. The proposal is content-addressed with SHA-256.

The operator approval binds to that SHA-256. Editing the proposal after approval invalidates it.

Approval also expires and names exact allowed scopes.

The operator label is local metadata, not independently verified identity.

## Physical confirmations

Protocol capture requires fresh explicit confirmations for:

- planned arm
- machine-state continuity
- test context
- every locked control

These map directly to NetMedic protocol preflight confirmations.

## Host-state controls

When DriveMedic is configured, FieldMedic captures host status immediately before and after each NetMedic protocol arm. The host receipts are linked beside the NetMedic preflight/execution receipt.

This can reveal material host changes during a network experiment. It does not prove those changes caused the result.

## NetMedic native workflow

FieldMedic binds to NetMedic's existing workflow rather than recreating it:

~~~text
protocol-freeze
  -> preflight
  -> execute-case --require-preflight
  -> repeated planned arms
  -> matched-case
~~~

NetMedic remains authoritative for frozen-protocol fingerprints, planned-arm order, preflight freshness/replay protection, trial supersession, and matched statistics.
