# Stable Promotion Evidence Packet

FieldMedic RC4 does not add another diagnostic feature. It turns the remaining release checklist into explicit evidence gates.

## Stable packaging gates

A promotion candidate requires all five:

1. Windows install/default-uninstall smoke;
2. live Windows bounded-repair qualification;
3. DriveMedic lifecycle qualification evidence;
4. NetMedic Windows/field promotion evidence;
5. NetMedic public-license evidence.

Run:

~~~text
fieldmedic promotion-candidate --output fieldmedic-stable-promotion.json
~~~

The command exits nonzero while any gate is blocked.

`READY_FOR_STABLE_PACKAGING` means the configured evidence set is present, internally valid, and bound to the currently discovered engine versions. It is not a new independent audit.

## Windows install/default-uninstall smoke

The deterministic Windows bundle contains its own smoke runner.

From PowerShell:

~~~powershell
.\smoke-windows-install.ps1 -Bundle .\FieldMedic-Windows.zip
~~~

With explicit existing engine paths:

~~~powershell
.\smoke-windows-install.ps1 -Bundle .\FieldMedic-Windows.zip -DriveMedic "C:\Path\drivemedic.exe" -NetMedic "C:\Path\netmedic.exe"
~~~

The smoke uses temporary program and data roots. It must prove:

- installer completion;
- `fieldmedic discover`;
- dashboard generation;
- release-receipt generation;
- default uninstall completion;
- temporary program root removed;
- temporary data root preserved;
- preservation sentinel preserved.

Only the resulting qualification receipt is written to the real evidence home.

## Imported engine evidence

FieldMedic does not pretend to own DriveMedic or NetMedic release claims. Their evidence is imported as exact hashed artifacts.

### DriveMedic lifecycle

~~~text
fieldmedic import-promotion-evidence drivemedic-lifecycle DRIVE_RECEIPT --operator "local operator" --declare-pass
~~~

### NetMedic field promotion

~~~text
fieldmedic import-promotion-evidence netmedic-field NET_RECEIPT --operator "local operator" --declare-pass
~~~

### NetMedic public license

~~~text
fieldmedic import-promotion-evidence netmedic-license LICENSE --operator "local operator" --declare-pass --license-id MIT --redistribution-allowed
~~~

The imported artifact is copied into the FieldMedic qualification store and SHA-256 bound.

The local operator declaration is provenance metadata. FieldMedic does not independently certify that an external qualification report is scientifically or legally correct.

For license evidence, the imported text must also contain markers consistent with the declared SPDX license family. This prevents a proprietary license artifact from being promoted merely by labeling it `MIT`.

## Version binding

DriveMedic and NetMedic external evidence is bound to the exact version string currently returned by engine discovery.

If an engine version changes, its imported promotion evidence no longer satisfies the current gate until new evidence is imported.

The Windows repair and install-smoke receipts are similarly bound to the current FieldMedic version.

## Claim boundary

The promotion packet answers:

> Do we possess the required, internally valid release evidence for these exact currently discovered components?

It does not answer:

> Has FieldMedic independently reproduced every external test, performed a legal audit, or proven universal hardware compatibility?

Those are different claims and remain different records.