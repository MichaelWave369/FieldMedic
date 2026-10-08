# Gated Release Builder

FieldMedic RC5 adds the final artifact builder. It is intentionally downstream of the stable-promotion evidence packet.

## Preconditions

`fieldmedic release-build` refuses to run unless:

- the promotion evaluator currently returns `READY_FOR_STABLE_PACKAGING`;
- the repository is a Git checkout;
- the Git worktree is completely clean, including untracked files;
- the checked-out source commit and tree can be resolved;
- the requested release channel is valid;
- `stable` is not requested from a prerelease version.

## Candidate build

From a clean checkout:

~~~text
fieldmedic release-build --repository-root . --output-dir dist/release --channel candidate
~~~

RC builds may use the `candidate` channel.

## Stable build

After the repository version has been changed to the final stable version and that exact version has re-earned all current-version evidence gates:

~~~text
fieldmedic release-build --repository-root . --output-dir dist/release --channel stable
~~~

A prerelease version such as `0.7.0rc5` is rejected by the stable channel.

## Artifacts

The builder creates:

- the FieldMedic wheel;
- a Git-derived source ZIP;
- the deterministic FieldMedic-only Windows ZIP;
- `FieldMedic-<version>-release-lock.json`;
- `FieldMedic-<version>-release.zip`;
- `FieldMedic-<version>-release-receipt.json`;
- `SHA256SUMS`.

## Reproducible release lock

The release lock contains no wall-clock timestamp. It binds:

- exact Git commit;
- exact Git tree;
- Git commit timestamp used as `SOURCE_DATE_EPOCH`;
- current DriveMedic version;
- current NetMedic version;
- each required promotion gate status and evidence hash;
- Windows-bundle manifest SHA-256;
- wheel/source/Windows artifact sizes and SHA-256 values.

The release packet uses fixed ZIP timestamps. The same source/evidence/artifact inputs therefore produce the same release lock and packet identity.

The ordinary release receipt remains timestamped operational evidence and is emitted as a sidecar rather than being allowed to make the reproducible lock depend on the clock.

## Source identity

The wheel is built from the clean checkout. The source archive is created with `git archive` from the exact HEAD commit. The builder records both HEAD and the Git tree hash.

Changing tracked or untracked worktree content blocks packaging until the checkout is clean.

## Claim boundary

The release lock proves which source, component versions, gate hashes, and artifacts were used for a package.

It does not replace the underlying qualification artifacts or independently prove their claims.