# Mac-Win Patch Provenance Review Design

Date: 2026-08-14

Status: Approved

## Objective

Resolve the provenance boundary for the 11 frozen Mac-Win patch assets tracked
by `MW-ASSET-002` without applying a patch, executing a source asset, reading a
Bottle, or depending on a mutable upstream checkout.

This stage converts the existing generic `deferred` patch mappings into an
evidence-backed review result. A patch may remain retained for later work only
when its own license, exact upstream base, purpose, affected applications,
dependencies, and focused regression probe are all proven. A patch with
missing, contradictory, obsolete, or conflicting evidence is quarantined.

The stage does not make any retained patch executable or applicable. It adds no
patch application API and makes no runtime compatibility claim.

## Frozen Input Boundary

The review is bound to the already committed Mac-Win source pack:

- repository: `a1112/Mac-Win`;
- source tag: `mw-migration-baseline-db12d5e`;
- annotated tag object: `9f10d003382ce7ffbb269376c03477e17516302f`;
- source commit: `db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527`;
- inventory commit: `97f8423094d25325d8f864eb6f49a9e8628dbb93`;
- source index SHA-256:
  `1fc8b071a9c52c5f29d130e47e3bd1cb165effa860eaa45336c82ee07cafe3a3`;
- category: exactly 11 records whose source-pack category is `patches`.

The current generated patch mapping is also an explicit transition input:

- path: `migration/macwin/generated/mappings/patches.json`;
- SHA-256:
  `c4505c787005d962af5fae3f715f2e7856bbbe790283a21bde75cf214f8a61e2`;
- current state: 11 records, all `deferred`, all owned by `MW-ASSET-002`.

The frozen source pack remains immutable. The review file does not replace or
rewrite source objects.

## Verified Upstream Research

The one-time review established the following upstream identities from the
official repositories:

- JASP tag `v0.97.1` resolves to commit
  `28be3fee5c7ce2119f1945acd0254eb4fb8cb6e2`;
- Wine annotated tag `wine-11.11` has tag object
  `b08651f36865a3e1d9300d792df322d2ee8a807e` and peels to commit
  `f6c044e1890e84a4aa5e77e76ba7276a615630e1`;
- JASP documents AGPL-3.0-or-later for Desktop and GPL-2.0-or-later for
  Common/Engine;
- Wine `wine-11.11` documents LGPL-2.1-or-later for the Wine project.

Authoritative upstream locators are:

- `https://github.com/jasp-stats/jasp-desktop`;
- `https://github.com/jasp-stats/jasp-desktop/blob/development/Docs/development/jasp-licensing.md`;
- `https://gitlab.winehq.org/wine/wine/`.

Project-level licensing is contextual evidence only. It does not prove that a
Mac-Win-local patch, its authorship, or every added hunk is licensed for
redistribution. Publisher reputation and the target project's license never
substitute for patch-specific evidence.

The initial base comparison found:

| Patch group | Exact old-blob evidence against the named tag |
|---|---|
| JASP local macOS build configuration | all three preimage blobs match `v0.97.1` |
| Other three JASP patches | no complete usable preimage blob identity in the patch |
| Wine data-json modern apps | five of five existing preimages match `wine-11.11` |
| Wine graphics imaging | five existing preimages match; one file is added |
| Wine bilinear scaler | two of two preimages match |
| Wine virtual desktop manager | four existing preimages match; one file is added |
| Wine native macOS UI integration | eight match, two mismatch, one file is added |
| Wine DComp host composition | fourteen match, eleven mismatch, nine are absent or added |
| Wine pointer input | nine match and eight mismatch |

These observations are recorded as review evidence, not inferred into a more
favorable result. Partial matches do not establish a complete upstream base.

## Scope

### Included

- a closed manual review ledger covering exactly the 11 frozen patch records;
- a closed JSON Schema for the ledger;
- exact source, upstream, base, license, purpose, application, dependency,
  disposition, and regression-probe evidence;
- deterministic converter integration and generated mapping updates;
- quarantine updates and regenerated root-index seals;
- an independent repository oracle for the manual policy and generated result;
- focused mutation, determinism, and side-effect tests;
- an evidence summary on Mac-Win issue `MW-ASSET-002`.

### Excluded

- applying, rebasing, compiling, loading, or executing a patch;
- cloning or fetching an upstream repository in normal builds, tests, or CI;
- marking a patch licensed merely because JASP or Wine has a project license;
- Runtime Pack materialization or patch selection;
- Wine, JASP, macOS, or Windows runtime compatibility claims;
- Bottle reads or changes, which remain owned by `MW-ASSET-003`;
- repository archival, which remains owned by `MW-ARCH-001`.

## Repository Layout

The stage adds one reviewed input and one schema:

```text
migration/macwin/
  source/                         # unchanged frozen pack
  reviewed/
    patches.json                  # exact human-reviewed 11-record ledger
  generated/
    index.json                    # regenerated seal
    mappings/patches.json         # enriched review outcome
    quarantine.json               # patch quarantine records added here
schemas/
  macwin-patch-review.schema.json
tools/
  convert_macwin_assets.py
scripts/
  validate_repository.py
tests/
  test_macwin_asset_migration.py
docs/
  migration/macwin-patch-provenance.md
```

No sixth generated leaf is introduced. The existing generated five-file graph
remains exact; only the bytes and seals of existing leaves change.

## Manual Review Ledger Contract

`migration/macwin/reviewed/patches.json` is canonical UTF-8/LF JSON with sorted
keys, two-space indentation, and one final newline. Its top-level object is
closed and contains:

- `schemaVersion`;
- exact source repository, tag, tag object, source commit, inventory commit,
  source-index digest, and digest algorithm;
- `recordCount`, fixed to 11;
- records sorted by bytewise ASCII source path.

Each record is closed and contains:

- exact `sourcePath`, `sourceSha256`, `gitBlobOid`, `gitMode`, and `byteSize`;
- patch subject and a bounded purpose statement;
- sorted, unique affected-application identifiers;
- an upstream repository, exact reference kind and name, tag object when one
  exists, and exact peeled commit;
- a sorted preimage table containing path, patch old-blob prefix, resolved
  upstream blob OID, and result `matched`, `mismatched`, `added`, or `unproven`;
- patch authorship as represented by the frozen bytes;
- project-license context and its official evidence locator;
- patch-license status `reviewed` or `unresolved`, with SPDX expression and
  exact evidence required only for `reviewed`;
- sorted external and development dependency evidence;
- upstream status `local-only`, `upstreamed`, `superseded`, `conflicting`, or
  `unresolved`;
- review disposition `retained` or `quarantined`;
- a fixed reason code and release condition;
- regression-probe references, required and non-empty only for `retained`.

All URLs are inert evidence strings. Normal validation neither resolves nor
opens them. Unknown fields, duplicate keys, duplicate exact or case-folded
identities, incorrect order, invalid UTF-8, invalid paths, excessive nesting,
or excessive size fail closed.

Initial limits are:

- review ledger: 1 MiB;
- records: exactly 11;
- preimage entries per record: 128;
- affected applications per record: 32;
- evidence locators and dependencies per record: 128 combined;
- regression probes per retained record: 32;
- JSON nesting depth: 128.

## Classification Policy

Classification uses the following stable priority and stops at the first
unsatisfied condition:

1. missing patch-specific license evidence:
   `quarantined/missing-license`;
2. incomplete or contradictory upstream base:
   `quarantined/unverified-base`;
3. conflicting or unclosed dependencies:
   `quarantined/conflict`;
4. upstreamed, superseded, or obsolete behavior:
   `quarantined/upstreamed-or-obsolete`;
5. complete evidence and at least one focused regression probe:
   `retained`, with migration status still `deferred`.

A `retained` record therefore proves all of the following:

- patch-specific redistribution license;
- exact upstream commit and every preimage identity;
- bounded purpose and affected-application set;
- closed dependency evidence;
- local-only, still-needed upstream status;
- at least one repository-owned focused regression probe.

The converter rejects a manual disposition inconsistent with this policy. It
does not trust a human-written `retained` value without rebuilding the result.

## Initial Approved Result

None of the 11 frozen patches currently has independent patch-specific license
evidence. The initial approved review therefore classifies every patch as:

```text
quarantined / missing-license
```

Upstream base matches remain visible evidence, but cannot override the first
classification rule. No patch is retained, converted, or applied.

The complete 90-record migration status changes deterministically from:

```text
converted=2, deferred=15, quarantined=73
```

to:

```text
converted=2, deferred=4, quarantined=84
```

The four remaining deferred records are the Bottle schema records owned by
`MW-ASSET-003`.

## Generated Mapping Contract

`migration/macwin/generated/mappings/patches.json` continues to contain exactly
11 source identities. Each generated record preserves its existing source
repository, commit, path, SHA-256, Git blob OID, mode, owner, license, and
provenance fields and adds the reviewed evidence needed to explain the result:

- upstream repository, reference, tag object where applicable, and commit;
- base-verification summary and exact counts;
- affected applications;
- upstream status;
- review disposition and stable reason code;
- regression-probe IDs for retained records;
- target issue `MW-ASSET-002`.

Quarantined patch identities also appear exactly once in
`migration/macwin/generated/quarantine.json`. The generated root index maps each
of the 90 source records to exactly one output document and seals the four
dependent documents by path, kind, size, and SHA-256.

## Regression Probe Boundary

A retained patch must reference one or more focused tests registered by stable
probe ID. A registered probe:

- is repository-owned and reviewed code, not a command stored in JSON;
- consumes only bounded in-memory copies of authenticated source bytes or
  synthetic fixtures;
- names the exact patch source digest and upstream commit it covers;
- has a positive control proving the assertion path runs;
- has a mutation that fails when the intended compatibility behavior is
  removed;
- does not invoke Git, Wine, JASP, a compiler, a shell, or a network client in
  normal CI.

The v1 ledger contains no retained records, so it contains no probe references.
The validator still enforces the retained-to-probe rule so a later review cannot
enable a patch without adding and executing an appropriate focused test.

## Deterministic Data Flow

The converter follows this order:

1. authenticate the existing five-file generated checkpoint and frozen source
   pack using the already approved boundaries;
2. bounded-read the manual review ledger without following links or reparse
   points;
3. parse it with strict UTF-8, duplicate-key rejection, bounded depth, and the
   closed application contract;
4. prove exact 11-record equality with the frozen patch category;
5. rebuild every classification from source and evidence fields;
6. require every retained probe ID to exist in the repository-owned registry;
7. render the enriched patch mapping and merged quarantine document;
8. rebuild the generated root index and its status counts;
9. validate the complete in-memory five-file graph independently of the
   renderer;
10. compare bytes for read-only modes or use the existing authenticated,
    rollback-safe five-file transaction for `--write`.

Repeated generation and repeated writes must be byte-for-byte no-ops.

## Repository Validation

The repository validator does not accept the converter and its golden files as
a self-authenticating oracle. It independently:

- binds and validates the frozen source index and 11 patch objects;
- validates the manual review schema and exact source identities;
- recomputes classification priority and expected status counts;
- recomputes the patch mapping and patch quarantine subset;
- binds those results into the complete generated graph;
- rejects missing, extra, linked, replaced, reordered, or self-consistently
  resealed forged evidence;
- revalidates directory and leaf identities before successful return.

The generated-tree checkpoint remains exactly five regular, single-link leaves
under the already approved directory layout.

## Side-Effect and Diagnostic Boundary

Default, `--check`, `--explain`, repository validation, and tests remain
offline and read-only. They must not:

- fetch, clone, or inspect an upstream repository;
- resolve evidence URLs or dependency locators;
- execute or import patch content;
- invoke Git, patch, a compiler, Wine, JASP, a shell, or a subprocess;
- read ambient environment, home, credential, or developer-machine paths;
- mutate the source pack, Bottle, Runtime Pack, Git state, or external files.

Failures use the existing bounded, non-reflective diagnostic contract. Untrusted
patch content, locators, paths, author strings, ANSI sequences, and OS errors do
not appear in failure output.

## Tests

The stage adds strict RED-to-GREEN coverage for:

- exact source-pack and ledger counts of 11;
- exact source path, SHA-256, Git blob OID, mode, size, and ordering;
- exact approved upstream tag and commit identities;
- project-license context never satisfying patch-license evidence;
- missing-license priority over otherwise verified base evidence;
- incomplete and partially matching upstream bases;
- missing, extra, duplicate, reordered, and case-fold-colliding records;
- unknown fields, duplicate JSON keys, invalid UTF-8, excessive size/depth, and
  unsafe paths;
- schema-valid but wrong OIDs, applications, status, disposition, and reason;
- forged `retained` records without license, full base, dependencies, or probe;
- retained probe registry presence, positive-control execution, and mutation
  failure semantics;
- exact generated counts `2/4/84`, 11 patch mappings, and 84 quarantine records;
- independent-oracle rejection of converter-plus-golden self-consistent forges;
- one-byte drift of the review ledger and all affected generated JSON;
- repeated generation and two writes producing identical bytes;
- the existing network, process, environment, locator, asset-execution, Bottle,
  external-write, link, race, rollback, and bounded-output guards.

Fresh completion gates remain:

```text
python -S -B -m unittest tests.test_macwin_asset_migration
python -B tools/convert_macwin_assets.py --check
python -B scripts/validate_repository.py
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

## Delivery and Issue State

The implementation will publish an evidence summary to Mac-Win issue
`MW-ASSET-002` containing the exact review commit, source identities, upstream
identities, classification counts, generated document digests, and verification
matrix.

The issue is closed only if its accepted exit condition is evidence review, not
patch integration. The completion note must state clearly that all 11 patches
remain quarantined and no patch was applied. `MW-ASSET-003` and `MW-ARCH-001`
remain open and unchanged.
