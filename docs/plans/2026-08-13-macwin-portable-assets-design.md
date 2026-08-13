# Mac-Win Portable Asset Migration Design

Date: 2026-08-13

Status: Approved

## Objective

Convert the digest-pinned Mac-Win migration inventory into versioned,
host-independent CompatForge assets without downloading dependencies, executing
legacy inputs, probing developer-machine paths, or mutating a Bottle.

This work implements Mac-Win issue `MW-ASSET-001` and keeps ownership of the
portable representation in CompatForge. Mac-Win remains the frozen source and
evidence repository at:

- repository: `a1112/Mac-Win`;
- source tag: `mw-migration-baseline-db12d5e`;
- source commit: `db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527`;
- inventory merge commit: `97f8423094d25325d8f864eb6f49a9e8628dbb93`.

The approved inventory contains exactly 90 governed inputs:

| Category | Count | Migration treatment |
|---|---:|---|
| catalog | 19 | Convert the index/signature boundary and 17 Recipe candidates |
| patches | 11 | Produce deferred provenance mappings only |
| probes | 26 | Produce portable probe assets or quarantine records |
| fixtures | 30 | Produce portable fixture assets or quarantine records |
| bottle-schema | 4 | Produce deferred Bottle migration mappings only |

## Scope

### Included

- a complete offline source pack for all 90 governed inputs;
- deterministic conversion of the 17 Recipe candidates;
- a portable catalog manifest;
- typed probe and fixture assets with closed manifests;
- explicit quarantine for inputs that cannot be converted without guessing;
- deferred mappings for Wine patches and Bottle schema sources;
- schemas, documentation, golden outputs, and cross-platform validation;
- exact source provenance on every converted or deferred identity.

### Deferred

- Wine patch upstream status, conflict review, and removal criteria belong to
  Mac-Win issue `MW-ASSET-002`;
- Bottle snapshot, conversion, rollback, and source-preservation behavior belong
  to `MW-ASSET-003`;
- Runtime Pack materialization, signing, or binary distribution;
- executing Recipe installers, probes, scripts, registry files, C fixtures, or
  Windows binaries;
- compatibility ratings based on new runtime observations.

## Ownership Boundary

CompatForge owns the source pack contract, conversion tool, schemas, generated
portable assets, quarantine records, and golden tests. Mac-Win owns the frozen
source tag and the reviewed inventory that proves the source identities.

CompatForge builds and tests must not depend on:

- a neighboring Mac-Win checkout;
- GitHub availability;
- mutable branches, releases, or URLs;
- developer-machine environment variables or absolute paths.

The checked-in source pack is an immutable audit input. Generated documents are
the canonical CompatForge assets. The source pack must never be loaded by the
runtime, C ABI, providers, or desktop client.

## Repository Layout

The migration slice uses the following layout:

```text
migration/macwin/
  source/
    index.json
    objects/sha256/<first-two-hex>/<remaining-hex>
  generated/
    index.json
    catalog.json
    recipes/*.json
    probes/*.json
    fixtures/*.json
    mappings/patches.json
    mappings/bottle-schemas.json
    quarantine.json
schemas/
  macwin-source-pack.schema.json
  migration-record.schema.json
  quarantine.schema.json
  portable-probe.schema.json
  portable-fixture.schema.json
tools/
  import_macwin_source_pack.py
  convert_macwin_assets.py
tests/
  test_macwin_asset_migration.py
```

The importer is a one-time, review-only utility. It accepts an explicitly named
local Mac-Win repository and exact source identity, reads reviewed Git blobs,
and creates the source pack. It is not used in normal build or CI.

The converter and validator use only the committed source pack. They do not
invoke the importer.

## Source Pack Contract

`migration/macwin/source/index.json` is canonical UTF-8/LF JSON with a closed
Schema v1 object. It records:

- the exact Mac-Win repository, tag, commit, inventory merge commit, and digest
  algorithm;
- exact category counts and total count 90;
- one record per ASCII POSIX source path;
- source path, category, Git mode, Git blob OID, SHA-256, byte size, license,
  provenance, intended owner, external references, and development dependencies;
- the relative content-addressed object path.

Records are sorted by source path. Paths, object paths, and identifiers reject:

- absolute POSIX or Windows paths;
- drive-qualified, UNC, device, backslash, colon, empty, dot, or dot-dot
  components;
- duplicate exact or case-folded identities;
- symlinks, reparse points, directories, and non-regular leaves.

The content store uses `objects/sha256/aa/bb...` paths derived from lowercase
SHA-256. The index and every leaf are bounded before reading. The initial limits
are:

- source index: 1 MiB;
- one source object: 8 MiB;
- source objects: exactly 90;
- total source bytes: 8 MiB;
- JSON nesting depth: 128;
- strings and collections: explicitly bounded by each schema.

The reviewed source set is currently about 1.74 MiB, so these limits leave room
for canonical serialization without permitting unbounded allocations.

The validator rejects missing, extra, duplicate, incorrectly sorted, oversized,
linked, or digest-mismatched content. Every object must match both its index
SHA-256 and byte size. JSON metadata parsing uses strict UTF-8, duplicate-key
rejection, an iterative depth gate, and closed-field validation.

## Conversion Model

### Catalog and Recipes

The 19 catalog inputs comprise `catalog.index.json`,
`catalog.signature.json`, and 17 Recipe candidates. The converter produces one
result for every candidate: `converted` or `quarantined`. A candidate is never
silently omitted.

A candidate may become a Recipe v2 only when all of the following are true:

- installer mode is representable as a pinned download or explicit `none`;
- a remote installer has both a URL and a SHA-256 digest;
- launcher executable and artifact references are safe guest or repository
  relative paths;
- no behavior depends on a developer-machine absolute path, unresolved local
  installation, undeclared environment path, or mutable local artifact;
- required license, provenance, and at least one test record are complete;
- every source field has an explicit deterministic mapping to Recipe v2.

Approved mechanical mappings include:

- Mac-Win `win64` to CompatForge `x86_64`;
- closed launcher field renames;
- frozen repository references to checked-in relative portable asset paths;
- known compatibility rating values to the existing Recipe v2 enum.

Unknown fields, ambiguous behavior, or missing information are not repaired by
heuristic defaults.

Recipe v2 receives an additive optional, closed provenance extension:

```json
{
  "sourceRepository": "a1112/Mac-Win",
  "sourceCommit": "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527",
  "sourcePath": "MacWinManager/.../recipes/7zip.json",
  "sourceSha256": "..."
}
```

Generated Mac-Win Recipes must populate all four fields. This is an additive
Schema v2 change, not a new Recipe schema version.

The generated catalog manifest contains the complete 17-candidate identity set,
the converted Recipe IDs and digests, and the quarantined source identities. It
does not treat quarantine as compatibility success.

### Probes and Fixtures

Probes and fixtures retain their raw source bytes only when the source is
host-independent and all referenced inputs are closed over the source pack or a
safe relative CompatForge artifact path. Their manifests record:

- stable ID and kind;
- source identity and digest;
- content digest, media type, and execution policy;
- referenced portable asset IDs;
- intended owner and license/provenance;
- explicit `executable: false` migration policy.

The migration tool never executes `.sh`, `.reg`, C, binary, or other fixture
content. Assets with developer paths, unresolved dependencies, or unsupported
semantics are quarantined.

### Patch and Bottle Mappings

The 11 patch inputs and four Bottle schema inputs produce closed migration
records with status `deferred`.

- patch records point to `MW-ASSET-002` and retain source digest, owner, license,
  and source path;
- Bottle schema records point to `MW-ASSET-003` and retain the same identity
  evidence;
- neither record is a Runtime Pack component, Recipe, or executable asset;
- no patch is applied and no Bottle data is read or written.

## Quarantine Contract

Quarantine is a first-class, closed Schema v1 output. Each record includes:

- source identity and category;
- source commit and SHA-256;
- fixed reason code;
- the reviewed evidence locators that caused quarantine;
- intended owner;
- an explicit release condition;
- status `quarantined`.

Reason codes are a fixed enum:

- `absolute-path`;
- `mutable-local-installation`;
- `missing-digest`;
- `unresolved-external-reference`;
- `unresolved-environment-path`;
- `missing-license`;
- `missing-provenance`;
- `unsupported-schema`;
- `unsupported-behavior`.

Free-form strings cannot substitute for status or reason codes. Evidence
locators are preserved as data only and are never opened, expanded, fetched, or
executed. Quarantine release requires a reviewed source or policy update and a
new deterministic generation result.

## Deterministic Data Flow

The normal converter follows this order:

1. validate the source directory and every path component without following
   links or reparse points;
2. bounded-read and validate the source index;
3. read each source object once through a bounded no-follow regular-file handle;
4. verify size and SHA-256 against the index;
5. parse applicable JSON with strict, duplicate-aware, depth-bounded parsing;
6. convert each identity to exactly one generated or quarantine result;
7. validate every in-memory document against closed application rules;
8. canonicalize with sorted keys, UTF-8, LF, two-space indentation, and one final
   newline;
9. build the generated root index from exact counts and document SHA-256 values;
10. either compare worktree bytes (`--check`) or commit all outputs as one
    transaction (`--write`).

Output order is bytewise ASCII POSIX path order. Sets are represented as sorted,
unique arrays. The converter does not use clock time, locale, random values,
filesystem enumeration order, user identity, current working directory, or
environment configuration.

`--write` stages every new output and every rollback source before the first
replacement, fsyncs and bounded-readback verifies staged bytes, binds directory
and leaf identities, and either replaces the complete output set or restores the
complete prior set. Linked parents/leaves, output-directory replacement, partial
commit, or rollback uncertainty fail closed.

## Side-Effect Boundary

Normal generation, checking, validation, and explanation must not:

- access a network or perform DNS resolution;
- spawn subprocesses or invoke a shell;
- read process environment values;
- expand `~`, environment placeholders, or dependency locators;
- test whether dependency locators exist;
- execute or import source assets;
- write outside `migration/macwin/generated`;
- mutate a Bottle, Runtime Pack store, source pack, Git metadata, or external
  sentinel.

`--explain <source-id>` returns an already-reviewed structured conversion or
quarantine explanation. It does not probe the locator named in the explanation.

## Diagnostics

CLI failures use stable exit codes, empty stdout, and one bounded stderr line.
Untrusted source paths, keys, JSON values, locators, ANSI sequences, and control
characters are not reflected in diagnostics. Expected data-specific explanations
are available only through successful `--explain` output after source identity
validation.

OS errors, parser implementation exceptions, recursion failures, integer-length
errors, and encoding failures are normalized only at the narrow boundary that
owns them. Programmer errors are not swallowed.

## Validation and Tests

The migration suite proves:

- exact coverage of 90 source identities and category counts 19/11/26/30/4;
- exact equality with the Mac-Win inventory at source commit `db12d5e`;
- 17 Recipe candidates each produce exactly one converted or quarantine result;
- 26 probes, 30 fixtures, 11 patches, and four Bottle schema sources each have
  exactly one closed mapping;
- source and output digests, root counts, shard counts, and canonical ordering;
- two independent in-memory generations and repeated `--write` are byte-for-byte
  identical;
- every generated Recipe validates against Recipe v2 and contains complete source
  provenance;
- any single-byte source/output drift, missing/extra identity, unknown field,
  duplicate key, order change, invalid UTF-8, excessive size/depth, absolute or
  escaping path, and missing provenance fails closed;
- link/reparse, hardlink, directory replacement, and transactional failure cases
  have explicit cross-platform expectations;
- controlled guards detect network, subprocess, environment, path-probe, asset
  execution, and Bottle-write mutants;
- explanation output is bounded, deterministic, and never probes evidence paths.

Repository gates remain:

```text
cargo fmt --check
cargo check --workspace --all-targets
cargo test --workspace --all-targets
cargo clippy --workspace --all-targets -- -D warnings
python -B scripts/validate_repository.py
python -B tools/convert_macwin_assets.py --check
```

Linux, macOS, and Windows CI validate the same committed source and output
digests. CI never executes migrated assets.

## Acceptance Mapping

Mac-Win `MW-ASSET-001` acceptance is satisfied as follows:

- developer-machine absolute paths become quarantine evidence or reviewed
  relative artifact references;
- conversion is pure and guarded against download, Wine launch, registry change,
  and Bottle writes;
- all new schemas are closed and path-safe;
- every converted, deferred, or quarantined identity retains source commit and
  digest provenance;
- golden tests cover the complete existing catalog and the full 90-input source
  set.

The design does not claim Recipe compatibility, patch readiness, or Bottle
migration success for quarantined or deferred records.
