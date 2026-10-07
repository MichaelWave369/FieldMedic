# Field Supply RC1

FieldMedic 0.7.0rc1 is a product-shell release candidate, not the stable Field Supply release.

## What RC1 proves

RC1 provides a single local operator surface around the already-qualified FieldMedic core:

- DriveMedic / NetMedic discovery;
- declared-interface version and health probing;
- local case inventory;
- NBG memory statistics;
- bounded repair registry visibility;
- portable case export/import;
- local product/release receipts.

## Discover

~~~text
fieldmedic discover
~~~

Discovery checks explicit CLI paths, environment variables, PATH, and a small set of documented Windows install locations. It probes DriveMedic through `version` and `self-check-json`; NetMedic through `--version` and `--crypto-status`.

Discovery never installs, downloads, or upgrades an engine.

## Dashboard

~~~text
fieldmedic dashboard --output fieldmedic-dashboard.html
~~~

The dashboard is a dependency-free static HTML snapshot. It is read-only and grants no authority. It shows engine status, local cases, memory counts, bounded repair actions, and current release-gate state.

## Portable cases

~~~text
fieldmedic case-export CASE_ID case.fieldmedic.zip
fieldmedic case-import case.fieldmedic.zip
~~~

Bundles contain the complete local case directory plus a SHA-256 manifest.

Import:

- rejects path traversal;
- rejects nonportable case IDs;
- rejects oversized expanded members;
- rejects manifest/file hash mismatches;
- rejects duplicate manifest paths;
- never overwrites an existing local case.

Portable case transfer does not promote memory, evidence, or authority.

## Release receipt

~~~text
fieldmedic release-receipt --output fieldmedic-release-receipt.json
~~~

The receipt records:

- FieldMedic version;
- Python/runtime/platform;
- discovered engine paths, versions, health and probe details;
- registered bounded repair actions;
- SHA-256 inventory of the installed FieldMedic Python package;
- explicit stable-release gates.

Unproven gates remain serialized as `UNPROVEN_BY_LOCAL_RECEIPT`. Discovery does not imply lifecycle qualification, field promotion, or live repair qualification.

## Stable promotion still requires

1. a Windows install/uninstall handoff;
2. live Windows qualification of both bounded repair executors;
3. the final DriveMedic lifecycle checkpoint;
4. NetMedic Windows/field promotion;
5. free-public NetMedic licensing alignment;
6. final package hashes and release receipt.

RC1 is intended to make those remaining gates observable and repeatable rather than hand-operated folklore.
