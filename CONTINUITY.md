# Continuity

Created from review of:

- DriveMedic `v1.0.0-rc13` source package
- Parallax NetMedic `v0.34.0` private source package

No source from either product is vendored here.

## Next implementation target

Rung 1 should add a **correlation receipt** that consumes a bounded DriveMedic timeline plus a NetMedic snapshot/watch receipt and emits only:

- co-occurring timestamps/windows
- supporting evidence IDs
- conflicts/missing evidence
- explicit uncertainty
- `causal_claim=false`

Do not add automatic repairs before the authority contract exists and is independently tested.
