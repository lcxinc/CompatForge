# Mac-Win Bottle Read-Only Migration Design

- Status: Approved
- Date: 2026-08-15
- Issue: `MW-ASSET-003`
- Owner: `compatforge/bottle-migration`

## Goal

Prove that CompatForge can preserve representative Mac-Win Bottle planning
behavior before any Mac-Win-owned implementation is retired. The first bridge
is an explicit, offline importer: it snapshots a user-selected legacy Bottle
without modifying it, converts only authenticated snapshot content, pins the
result to an exact Runtime Pack ID and digest, installs a complete target
version transactionally, and can roll back to the last verified version.

## Decision

Implement a general offline, source-read-only importer rather than either an
evidence-only fixture converter or direct integration with the live Mac-Win
Application Support directory.

This boundary costs more than a fixture-only proof, but the same core will be
usable for a future user-selected Bottle. It avoids the permissions, process
liveness, implicit discovery, and source-corruption risks of operating on a
live Mac-Win directory.

## Alternatives Considered

### Fixture-only evidence conversion

This is the smallest immediate change, but it would defer the real path,
snapshot, transaction, and rollback contracts. A later live migration would
need a second design and could invalidate the original golden proof.

### Direct live Mac-Win migration

This would couple the bridge to mutable application state, platform paths,
permissions, concurrent Wine processes, and recovery ownership. It also makes
the strongest acceptance criterion -- leaving the source untouched -- harder
to prove. It is rejected for this milestone.

## Scope

The implementation adds a `compatforge-bottle` Rust crate and CLI commands for
snapshot, plan, import, verify, and rollback. The crate reuses the existing
CompatForge domain DTOs, Runtime Pack store, canonical JSON conventions, and
transactional storage patterns.

The importer:

- accepts only an explicitly supplied legacy Bottle directory;
- never searches the Mac-Win checkout or user profile;
- never invokes Swift, Wine, a shell, or any source artifact;
- never modifies or deletes the source Bottle;
- converts only an already committed and verified snapshot;
- requires an explicit legacy-engine-to-Runtime-Pack binding;
- writes only to an explicitly supplied CompatForge Bottle store;
- retains an exact previous target version for bounded rollback.

## Non-Goals

- automatic discovery of live Mac-Win Bottles;
- in-place conversion or deletion of legacy data;
- launching Wine or testing installed applications;
- inventing Recipe identities for unreviewed applications;
- following links outside the selected Bottle;
- network access, archive download, or Runtime Pack installation;
- multi-writer conflict resolution or automatic recovery of untrusted stale
  transactions.

## Architecture

### `compatforge-bottle`

The new crate owns five operations:

1. `snapshot`: authenticate and copy a legacy Bottle into immutable objects;
2. `plan`: map an authenticated snapshot to closed CompatForge DTOs;
3. `import`: materialize and publish a complete target version;
4. `verify`: reauthenticate the active version and all dependencies;
5. `rollback`: verify and reactivate the most recent complete historical
   version.

The crate does not depend on Mac-Win source code. It implements a closed legacy
JSON contract derived from the frozen `BottleManifest` and `LauncherManifest`
shapes already authenticated by the Mac-Win source pack.

### CLI

The CLI exposes explicit stages:

```text
compatforge-cli bottle snapshot <store-root> <legacy-bottle-root>
compatforge-cli bottle plan <store-root> <snapshot-digest> <runtime-store-root> <runtime-map.json>
compatforge-cli bottle import <store-root> <snapshot-digest> <runtime-store-root> <runtime-map.json>
compatforge-cli bottle verify <store-root> <bottle-id>
compatforge-cli bottle rollback <store-root> <bottle-id>
```

Every successful command emits bounded canonical JSON. Diagnostics use closed
codes and safe relative paths; they never reflect source absolute paths,
environment values, or file contents.

## Store Layout

The caller chooses one Bottle migration store root:

```text
objects/sha256/<content-digest>
snapshots/sha256/<snapshot-digest>.json
versions/<bottle-id>/<plan-digest>/
  manifest.json
  migration.json
  prefix/
refs/<bottle-id>/current.json
transactions/<exclusive-transaction-id>/
```

Objects and versions are immutable after publication. `current.json` is the
only activation point. It contains the active plan digest and a bounded history
of prior plan digests. Publishing a version follows the Runtime Pack model:
stage all content, fsync, read back, revalidate identities and digests, publish
the immutable version, then atomically replace the active ref.

An exclusive transaction directory makes simultaneous writers fail closed.
Unknown or stale transaction state is diagnostic evidence and is never
silently repaired.

## Snapshot Contract

Snapshot traversal holds each parent directory and opens children relative to
that binding. POSIX uses directory file descriptors and no-follow operations;
Windows uses handles that reject or bind reparse points and prevent parent
replacement while the entry is authenticated.

The canonical snapshot manifest contains no host root. It records:

- schema version and legacy format identifier;
- Bottle ID from the authenticated `manifest.json`;
- sorted entries with safe relative path and entry kind;
- regular-file byte size and SHA-256;
- internal relative-link target where applicable;
- total entry count and regular-file bytes.

Regular files are streamed into `objects/sha256`. Directories and safe internal
relative links are represented in the manifest. A link is accepted only when
its normalized target remains inside the Bottle. Absolute, external,
device-like, reparse, cyclic, or otherwise ambiguous links fail closed.

Every entry is checked before and after reading. The directory tree and root
identity are revalidated before success. A source mutation produces
`source-changed`; partial objects may remain unreachable, but no snapshot
manifest is published.

## Planning Contract

Planning reads only a verified snapshot and validates the closed legacy JSON
shape. It never reopens the source directory.

Legacy fields map as follows:

| Legacy field | CompatForge result |
| --- | --- |
| `id`, `name` | Preserved after closed identifier/text validation |
| `windowsVersion` | Exact `win7`, `win10`, or `win11` |
| `arch: win32` | `guest.architecture: i386` |
| `arch: win64` | `guest.architecture: x86_64` |
| `engineId` | Explicit Runtime Pack ID and digest from the mapping input |
| `createdAt`, `updatedAt` | Preserved as canonical RFC 3339 values |
| Bottle `envOverrides` | Baseline launcher environment |
| launcher `envOverrides` | Overrides Bottle values for the same key |
| installed launcher metadata | Closed launcher planning input; no Recipe is invented |

Each legacy launcher must name the same Bottle ID, have a unique safe ID, and
use a bounded Wine guest executable path. Arguments, environment, display
metadata, visibility, and a safe optional guest icon path are preserved in the
migration plan. Host absolute paths, host variables, device names, ADS syntax,
and guest traversal are rejected.

The Runtime mapping is a closed canonical JSON document containing records of
`legacyEngineId`, `runtimePackId`, and `runtimePackDigest`. Planning requires
one exact match. The Runtime Pack store must already contain and verify that
digest, and the verified manifest ID must equal `runtimePackId`. No version or
channel inference is allowed.

The canonical `BottleMigrationPlan` binds:

- source snapshot digest;
- legacy format and engine ID;
- target `BottleManifest` and its digest;
- exact Runtime Pack ID and digest;
- sorted launcher planning inputs;
- fixed diagnostics;
- plan digest.

## Import and Rollback

Import verifies the snapshot, migration plan, Runtime Pack, and any existing
active ref before creating a transaction. It reconstructs the prefix only from
snapshot objects, writes the target manifest and migration plan, fsyncs every
new leaf and required directory, reads all data back, and revalidates the
complete version before publication.

Any failure before the final ref replacement leaves the prior active version
unchanged. The source is never part of rollback because it was never written.
The transaction is removed only after successful publication or a proven
complete rollback.

Rollback selects the most recent historical plan digest, verifies its version
manifest, materialized prefix, snapshot, and exact Runtime Pack binding, then
atomically updates `current.json`. A missing or corrupt prior version returns a
fixed error and leaves the active ref unchanged.

## Resource and Path Bounds

- relative path: at most 4096 UTF-8 bytes;
- relative depth: at most 128 components;
- entries per Bottle: at most 100,000;
- regular file: at most 64 GiB;
- total regular-file bytes: at most 1 TiB;
- canonical snapshot manifest: at most 64 MiB;
- all reads and hashes are streaming and use fixed-size buffers.

Paths are normalized without using the current working directory, HOME, TEMP,
or platform separator guesses. Case-fold collisions, leaf/directory prefix
collisions, reserved names, controls, invalid Unicode, trailing-dot/space
ambiguity, and unsafe links are rejected before target creation.

## Errors and Diagnostics

The public error contract has stable categories including:

- `source-changed`;
- `unsafe-entry`;
- `invalid-manifest`;
- `runtime-unmapped`;
- `runtime-mismatch`;
- `snapshot-corrupt`;
- `target-collision`;
- `transaction-failed`;
- `rollback-unavailable`;
- `rollback-corrupt`.

Errors contain a fixed message and, where useful, a safe relative locator. They
do not include arbitrary JSON values, source contents, external path targets,
or OS error text in the stable serialized diagnostic.

## Golden Parity

Two deterministic, non-executable fixtures cover representative planning:

1. a win64 Bottle with multiple launchers, Bottle environment, launcher
   overrides, arguments, and visibility metadata;
2. a minimal win32 Bottle.

The fixtures contain only public text placeholders. An independent legacy
oracle produces sealed planning goldens. CompatForge produces the new
`BottleMigrationPlan` and representative `LaunchPlan` goldens using a fixed,
verified preview Runtime Pack. The comparison binds:

- Bottle ID and guest Windows version;
- guest architecture;
- launcher executable and arguments;
- environment merge precedence;
- target prefix path;
- exact Runtime Pack ID and digest;
- canonical output bytes and SHA-256.

No test executes Wine, a launcher, or any fixture content. Each checked-in
golden has a fixed digest, and independent tests reject self-consistently
resealed drift.

## Test Strategy

Implementation follows strict RED-GREEN-REFACTOR TDD.

### Snapshot tests

- regular files, empty directories, duplicate content, Unicode paths, and safe
  internal links;
- absolute/external/cyclic links, reparse points, devices, FIFOs, sockets, and
  non-regular entries;
- case-fold and leaf/directory collisions;
- exact path, depth, entry, per-file, total-byte, and manifest boundaries;
- same-size mutation, restored timestamps, file replacement, parent/root
  replacement, and late-child races;
- source bytes, metadata, and identity unchanged on every outcome.

### Planning tests

- all closed legacy fields and unknown-field rejection;
- win32/win64 mapping and timestamp preservation;
- Bottle/launcher environment precedence;
- duplicate launchers, mismatched Bottle IDs, unsafe guest paths, and bounded
  strings/collections;
- missing, duplicate, malformed, or wrong Runtime mapping;
- Runtime manifest ID/digest mismatch and installed-object corruption.

### Transaction tests

- every stage, fsync, readback, publish, and ref-replace failure ordinal;
- exact no-op repeated import;
- source untouched and prior active ref unchanged on failure;
- target file, directory, link, hardlink, and same-byte replacement races;
- no transaction residue after proven success or rollback;
- corrupt or unavailable rollback history never changes the active version.

### Repository and side-effect tests

- three-platform Rust unit and integration tests;
- CLI canonical output, output bounds, and fixed diagnostics;
- schema and golden validation using independent oracles;
- no network, subprocess, implicit environment, Mac-Win checkout, Bottle
  discovery, source write, or fixture execution;
- repository validator requires the fixtures, schemas, docs, and golden seals;
- `cargo fmt`, `cargo check`, `cargo test`, and `cargo clippy -D warnings`.

## Acceptance Mapping

| `MW-ASSET-003` acceptance criterion | Design proof |
| --- | --- |
| Representative old/new planning goldens | Two sealed legacy/new planning fixtures and independent parity oracle |
| Read-only snapshot and content manifest | Held-handle snapshot with content-addressed objects and canonical manifest |
| Exact Runtime Pack ID plus digest | Explicit mapping plus verified Runtime Pack store lookup |
| Failure leaves source untouched and produces diagnostics | Source has no write path; failure-injection and side-effect snapshots cover every stage |
| Rollback to last complete snapshot | Immutable versions, bounded ref history, verify-before-ref-switch rollback |

## Delivery Boundary

This issue ends when the offline Bottle store, CLI, representative fixtures,
goldens, documentation, repository validation, and three-platform tests are
complete. It does not archive Mac-Win. `MW-ARCH-001` remains open until the
broader migration exit criteria are independently verified.
