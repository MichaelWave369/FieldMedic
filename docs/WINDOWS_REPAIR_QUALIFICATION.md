# Live Windows Repair Qualification

FieldMedic 0.7.0rc2 adds the qualification protocol for the two built-in bounded Windows repair executors.

This protocol is intentionally a **live workstation gate**. CI does not satisfy it.

## Preconditions

Run from an elevated Administrator PowerShell on the Windows workstation being qualified.

DriveMedic and NetMedic must both be discoverable and healthy enough for FieldMedic diagnostics.

Choose the exact network interface to test first:

~~~powershell
Get-NetIPInterface |
  Sort-Object InterfaceIndex, AddressFamily |
  Format-Table InterfaceIndex, AddressFamily, InterfaceAlias, AutomaticMetric, InterfaceMetric
~~~

Select:

- the intended `InterfaceIndex`;
- `IPv4` or `IPv6`;
- a temporary metric that differs from the current effective/manual test state.

Do not select an interface whose temporary metric change is unacceptable for the workstation. The harness is designed to roll back automatically, but it is still a live network-state mutation.

## Run

From the FieldMedic repository:

~~~powershell
.\scripts\qualify-windows-repairs.ps1 -InterfaceIndex 12 -AddressFamily IPv4 -TemporaryMetric 50 -Operator "local operator"
~~~

Optional explicit engine paths:

~~~powershell
.\scripts\qualify-windows-repairs.ps1 -InterfaceIndex 12 -AddressFamily IPv4 -TemporaryMetric 50 -Operator "local operator" -DriveMedic "C:\Path\To\drivemedic.exe" -NetMedic "C:\Path\To\netmedic.exe"
~~~

## What actually runs

The harness first creates a real FieldMedic case using DriveMedic and NetMedic evidence.

### Process-priority executor

FieldMedic spawns a disposable Python helper process.

The production repair path then performs:

~~~text
proposal
  -> live preflight
  -> operator grant
  -> BelowNormal apply
  -> typed postcondition
  -> DriveMedic + NetMedic post-action capture
  -> repair verification capture
  -> exact priority rollback
  -> DriveMedic + NetMedic post-rollback capture
~~~

The process start-time identity is part of the target state, so PID reuse cannot qualify the executor.

### Interface-metric executor

The operator-selected interface runs through the same production repair path:

~~~text
proposal
  -> live interface-state preflight
  -> operator grant
  -> temporary metric apply
  -> typed postcondition
  -> DriveMedic + NetMedic post-action capture
  -> repair verification capture
  -> exact automatic/manual metric rollback
  -> DriveMedic + NetMedic post-rollback capture
~~~

The test fails if the requested temporary state would be identical to the captured pre-state.

## PASS requirements

Both executor tests must prove all of the following:

- production Repair Gate admitted the exact proposal/preflight/grant;
- target state actually changed;
- typed postcondition matched;
- DriveMedic and NetMedic captured post-action evidence;
- repair verification reached `MEASURED_PENDING_OPERATOR_OUTCOME`;
- exact captured pre-state was restored;
- DriveMedic and NetMedic captured post-rollback evidence;
- execution, verification and rollback evidence IDs exist.

Any missing condition produces `FAIL`.

## Receipt

A run writes:

~~~text
FIELDMEDIC_HOME/
  qualification/
    windows-repair/
      winqual-<timestamp>-<id>.json
      latest.json
~~~

The receipt is SHA-256 bound and includes:

- FieldMedic version;
- Windows/runtime identity;
- elevation state;
- DriveMedic and NetMedic discovery/version data;
- operator-selected interface test parameters;
- both executor test summaries;
- evidence IDs and state hashes;
- final PASS/FAIL status.

The ordinary `fieldmedic release-receipt` command accepts the gate only when `latest.json`:

- has a valid receipt hash;
- says `PASS`;
- was produced by the current FieldMedic version;
- records Windows + Administrator execution;
- records both engines and versions;
- proves both executor verification and rollback requirements.

Updating FieldMedic invalidates an older executor qualification until the current version is rerun.

## Claim boundary

A PASS means:

> the bounded executor apply / independent measurement / exact rollback path passed on the recorded Windows workstation and environment.

It does **not** mean:

- every Windows version is qualified;
- every network adapter or driver is qualified;
- every process/workload is qualified;
- DriveMedic has completed its separate lifecycle release gate;
- NetMedic has completed its separate Windows/field promotion gate.

Those remain independent release claims.