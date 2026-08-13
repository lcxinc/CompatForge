# Mac-Win Portable Asset Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Export all 90 digest-pinned Mac-Win migration inputs into a complete, deterministic CompatForge source pack and convert each input to exactly one portable, deferred, or quarantined CompatForge record without external side effects.

**Architecture:** A review-only importer creates a content-addressed source pack from the exact Mac-Win tag and reviewed inventory. Normal builds use a pure Python converter that validates the committed source pack, builds bounded canonical outputs in memory, and implements `--check`, transactional `--write`, and `--explain`; CompatForge schemas and golden tests close every generated record. The runtime, C ABI, providers, and desktop client never load the migration source pack.

**Tech Stack:** Python 3.12 standard library, JSON Schema Draft 2020-12 documents, Rust workspace validation, GitHub Actions, `unittest`, SHA-256, canonical UTF-8/LF JSON.

---

## Fixed Inputs and Commands

Work in the isolated branch created from CompatForge `origin/main`:

```powershell
L:\project\FOS\.worktrees\compatforge-macwin-portable-assets
```

The reviewed Mac-Win identity is fixed:

```text
repository: a1112/Mac-Win
tag: mw-migration-baseline-db12d5e
source commit: db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527
inventory merge commit: 97f8423094d25325d8f864eb6f49a9e8628dbb93
assets: 90 = 19 catalog + 11 patches + 26 probes + 30 fixtures + 4 bottle-schema
```

Use these executable focused commands. Do not use dotted `tests.test_*` module
names because `tests/` is not a Python package.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -v
python -B scripts/validate_repository.py
python -B tools/convert_macwin_assets.py --check
```

All implementation commits require `git commit -s` DCO trailers. Never push,
open a PR, or change either GitHub issue until Task 10 completes both review
gates.

### Task 1: Establish the migration test skeleton and repository rules

**Files:**
- Create: `tests/test_macwin_asset_migration.py`
- Modify: `.gitattributes`
- Modify: `scripts/validate_repository.py`
- Test: `tests/test_macwin_asset_migration.py`

**Step 1: Write the failing contract test**

Create a `MigrationLayoutTests` class that asserts:

- all paths named in the approved layout are repository-relative POSIX paths;
- `migration/macwin/**/*.json` is LF-pinned through the committed
  `.gitattributes` blob, not only through mutable checkout attributes;
- Python migration modules import without writing repository-local bytecode;
- `scripts/validate_repository.py` invokes the migration check before reporting
  repository success once the converter exists.

The initial test must fail only because the migration paths and LF rules do not
exist. Use real raw-byte assertions for `.gitattributes`; do not normalize mixed
newlines.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationLayoutTests -v
```

Expected: FAIL for missing migration layout and LF attribute rules; existing
repository validation remains green.

**Step 3: Implement the minimum layout contract**

Add exact LF rules:

```gitattributes
/migration/macwin/**/*.json text eol=lf
/schemas/macwin-*.schema.json text eol=lf
```

Create import-safe placeholder modules only if the tests need an import target;
they must not implement conversion behavior yet. Extend repository validation
with a narrowly named hook that skips only while the converter path is absent in
this Task, then remove that skip in Task 8.

**Step 4: Run GREEN and baseline gates**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationLayoutTests -v
python -B scripts/validate_repository.py
cargo fmt --all --check
```

Expected: focused tests and existing repository contracts pass; no
`__pycache__`, `.pyc`, or `.pyo` exists.

**Step 5: Commit**

```powershell
git add .gitattributes scripts/validate_repository.py tests/test_macwin_asset_migration.py
git commit -s -m "test: establish Mac-Win asset migration contract"
```

### Task 2: Add closed schemas and bounded JSON primitives

**Files:**
- Create: `schemas/macwin-source-pack.schema.json`
- Create: `schemas/migration-record.schema.json`
- Create: `schemas/quarantine.schema.json`
- Create: `schemas/portable-probe.schema.json`
- Create: `schemas/portable-fixture.schema.json`
- Modify: `schemas/recipe.schema.json`
- Create: `tools/macwin_asset_common.py`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing parser and schema tests**

Add `MigrationJsonBoundaryTests` and `MigrationSchemaTests` for:

- maximum 1 MiB metadata input and a max+1 rejection before decode;
- strict UTF-8;
- duplicate keys including Unicode-escaped duplicates;
- maximum JSON depth 128 before `json.loads` recursion;
- closed keys and exact `schemaVersion` strings;
- exact ASCII POSIX relative path validation independent of host OS;
- Windows drive/UNC/device/backslash/colon and dot-component rejection;
- stable one-line errors that do not reflect hostile keys or ANSI/control text;
- the five new unique schema `$id` values;
- Recipe v2 additive closed provenance with all four source fields together or
  none, and no partial provenance object.

Use direct parser and subprocess entrypoint tests. Raise the process recursion
limit in depth tests so a 129-level input proves the explicit pre-scan rejects
before the standard decoder.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationJsonBoundaryTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationSchemaTests -v
```

Expected: errors for missing common module/schemas and Recipe provenance.

**Step 3: Implement bounded primitives and schemas**

In `tools/macwin_asset_common.py`, implement:

```python
MAX_METADATA_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 128

class MigrationError(Exception):
    pass

def parse_json_bytes(raw: bytes, *, label: str, max_bytes: int) -> object:
    ...

def canonical_json_bytes(value: object) -> bytes:
    ...

def require_relative_posix_path(value: object) -> str:
    ...
```

The canonical renderer accepts only null/bool/bounded integer/string/list/dict,
requires string keys, detects cycles/depth iteratively, rejects floats and
unsupported containers, emits `indent=2`, `sort_keys=True`, `ensure_ascii=False`,
UTF-8, and one final LF.

All schemas use `additionalProperties: false`, closed nested objects, bounded
strings/arrays, fixed status/reason enums, and the path pattern from the approved
design. Do not add third-party Python dependencies.

**Step 4: Run GREEN and mutation checks**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationJsonBoundaryTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MigrationSchemaTests -v
python -B scripts/validate_repository.py
```

Temporarily remove each depth, duplicate-key, path, and provenance gate and
prove its corresponding test fails. Restore before continuing.

**Step 5: Commit**

```powershell
git add schemas tools/macwin_asset_common.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: define portable migration contracts"
```

### Task 3: Import and bind the complete offline source pack

**Files:**
- Modify: `.gitattributes`
- Create: `tools/import_macwin_source_pack.py`
- Create: `migration/macwin/source/index.json`
- Create: `migration/macwin/source/objects/sha256/**`
- Modify: `scripts/validate_repository.py`
- Modify: `tests/test_macwin_asset_migration.py`

The repository developer-path gate is integrated in this task instead of
waiting for Task 8 because the exact frozen source bytes and dependency
evidence intentionally contain reviewed developer-machine locators. This is
not a subtree exclusion. The validator first performs the complete offline
source-pack validation: canonical index, exact 90-record/count/mode contract,
derived object paths, exact referenced object set, and every raw-byte size,
SHA-256, and Git blob OID. Only after that validation succeeds may the existing
developer-path scan exempt the validated index and its exact 90 referenced
content-addressed leaves. Any extra or unreferenced file, index/object drift,
linked boundary, or source-pack validation failure grants no exemption and
fails closed. This validation never reads a neighboring repository or uses the
network.

The content-addressed raw object leaves are also pinned by the exact
`.gitattributes` rule
`/migration/macwin/source/objects/sha256/** binary`. The rule expands to
`-diff -merge -text`, does not match generated or neighboring paths, and keeps
Git add/checkout byte identity independent of `core.autocrlf`; the canonical
source index remains UTF-8/LF JSON under the existing JSON rule.

**Step 1: Write failing source-pack tests**

Add `MacWinSourcePackTests` covering:

- exact repository/tag/source/inventory merge identity;
- exact counts `90 = 19/11/26/30/4`;
- ASCII POSIX ordering, exact and case-fold uniqueness;
- each object path is derived from lowercase SHA-256;
- object size/digest matches the index;
- source record matches Mac-Win inventory fields exactly;
- missing/extra object, linked parent/leaf, reparse point, directory,
  non-regular leaf, oversize object/index, duplicate digest/path, single-byte
  object mutation, and index mutation fail closed;
- ordinary same-content hardlinks have an explicit supported or rejected
  contract; choose supported only if identity/content verification remains exact;
- importer Git reads use exact repository cwd, list argv, `shell=False`, stdin
  disabled, exact process-local `safe.directory`, no replace refs, and a scrubbed
  Git environment;
- importer rejects missing/wrong/lightweight/symbolic/case-variant source tag,
  non-ancestor source, alternates/promisor stores, linked index/refs/object leaves,
  and object identity mismatch;
- importer performs no writes to the Mac-Win repository and no network access.

Use a small temporary Git repository for hostile boundaries and the real local
Mac-Win repository only for the approved one-time import golden test.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinSourcePackTests -v
```

Expected: FAIL because the importer, index, and objects do not exist.

**Step 3: Implement the review-only importer**

The importer CLI requires explicit arguments:

```powershell
python -B tools/import_macwin_source_pack.py `
  --repository L:\project\FOS\Mac-Win `
  --tag mw-migration-baseline-db12d5e `
  --source-commit db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527 `
  --inventory-commit 97f8423094d25325d8f864eb6f49a9e8628dbb93 `
  --write
```

Implementation order:

1. bind exact repository root, common Git directory, object directory, source
   tag object, peeled source, inventory index, and stage-0 reviewed inventory;
2. reject external object/config/include/promisor/replace boundaries before
   reading reviewed content;
3. read the six reviewed inventory documents from the exact inventory commit;
4. type/size/read every source blob by OID with bounded `cat-file --batch`;
5. recompute Git object OID and SHA-256 from raw bytes;
6. construct all output bytes in memory;
7. transactionally stage and commit the source pack after path/identity/readback
   verification.

The checked-in source pack is the result. Normal CI must not invoke this importer.

**Step 4: Run GREEN and exact-diff validation**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinSourcePackTests -v
python -B tools/import_macwin_source_pack.py --repository L:\project\FOS\Mac-Win --tag mw-migration-baseline-db12d5e --source-commit db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527 --inventory-commit 97f8423094d25325d8f864eb6f49a9e8628dbb93 --check
```

Run `--write` twice and prove the second run is byte-identical with zero Git
diff. Snapshot both repositories' status, index, refs, and object file metadata
before/after and prove only CompatForge source-pack paths changed during the first
approved write.

**Step 5: Commit**

```powershell
git add tools/import_macwin_source_pack.py migration/macwin/source tests/test_macwin_asset_migration.py
git commit -s -m "feat: import the frozen Mac-Win source pack"
```

### Task 4: Build the deterministic conversion model and coverage ledger

**Files:**
- Create: `tools/convert_macwin_assets.py`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing model tests**

Add `MacWinConversionModelTests` for:

- all 90 source identities produce exactly one ledger result;
- category counts remain exact;
- exactly 17 catalog Recipe candidates are classified `converted` or
  `quarantined`;
- catalog index/signature produce catalog-boundary records, not Recipes;
- probes/fixtures/patches/Bottle sources get the approved result types;
- patch and Bottle statuses are fixed `deferred` with the exact target issue;
- duplicate/missing/extra results, wrong category, unsupported status/reason,
  wrong source digest/commit, and unstable ordering are rejected;
- two in-memory generations are byte-identical;
- conversion does not inspect dependency locator existence.

Do not assert a desired converted Recipe count yet. Let the approved rules and
real data determine it; seal the observed count only after review in Task 5.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinConversionModelTests -v
```

Expected: errors for missing converter and result model.

**Step 3: Implement the in-memory ledger**

Implement import-safe functions:

```python
def load_source_pack(repository_root: Path) -> SourcePack:
    ...

def build_conversion(repository_root: Path) -> ConversionResult:
    ...

def render_documents(result: ConversionResult) -> dict[str, bytes]:
    ...
```

Use immutable dataclasses/tuples for the internal model. Load each source object
once, verify before use, and classify all identities before rendering any output.
No output is written in this Task.

**Step 4: Run GREEN and focused mutation checks**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinConversionModelTests -v
```

Delete the final completeness check and verify a test fails. Restore it before
commit.

**Step 5: Commit**

```powershell
git add tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: classify every Mac-Win migration input"
```

### Task 5: Convert catalog Recipes and quarantine unsupported candidates

**Files:**
- Modify: `tools/convert_macwin_assets.py`
- Modify: `schemas/recipe.schema.json`
- Create: `migration/macwin/generated/catalog.json`
- Create: `migration/macwin/generated/recipes/*.json`
- Create: `migration/macwin/generated/quarantine.json`
- Modify: `scripts/validate_repository.py`
- Modify: `tests/test_macwin_asset_migration.py`

The frozen catalog can preserve reviewed developer-machine locators in
quarantine evidence. The repository developer-path gate therefore exempts only
the exact `catalog.json` and `quarantine.json` leaves after the Task 5 converter
rebuilds both documents from the authenticated source pack, validates their
closed application contracts, and proves exact canonical byte equality. The
scan binds both generated leaf identities and raw bytes, revalidates the full
documents and source pack after scanning, and grants no subtree or pattern
exemption. Modified, forged, extra, unreferenced, linked, or replaced generated
evidence remains subject to the ordinary developer-path failure.

The reviewed Task 5 result for source commit
`db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527` is 0 converted and 17
quarantined candidates. Every candidate is blocked first by unresolved source
license evidence; no placeholder Recipe is emitted.

| Source ID | Status | First reason |
| --- | --- | --- |
| `7zip` | quarantined | `missing-license` |
| `firefox` | quarantined | `missing-license` |
| `hoyoplay-cn` | quarantined | `missing-license` |
| `jasp-stats` | quarantined | `missing-license` |
| `lenovo-app-store` | quarantined | `missing-license` |
| `libreoffice` | quarantined | `missing-license` |
| `ltspice` | quarantined | `missing-license` |
| `macwin-core-capability-tests` | quarantined | `missing-license` |
| `macwin-game-tests` | quarantined | `missing-license` |
| `macwin-probes` | quarantined | `missing-license` |
| `notepad-plus-plus` | quarantined | `missing-license` |
| `portableapps-platform` | quarantined | `missing-license` |
| `sqlitestudio` | quarantined | `missing-license` |
| `steam` | quarantined | `missing-license` |
| `sumatrapdf` | quarantined | `missing-license` |
| `texstudio` | quarantined | `missing-license` |
| `vlc` | quarantined | `missing-license` |

**Step 1: Write failing Recipe/quarantine tests**

Add `MacWinRecipeConversionTests` for each approved mapping and rejection rule:

- `win64 → x86_64`, launcher field mapping, environment sorting, warnings,
  installer mode/URL/file/digest/arguments, compatibility enums;
- all generated Recipes contain full source provenance and validate against the
  closed Recipe application contract;
- mutable `alreadyInstalled`, absolute hints, missing installer digest,
  unsupported post-install behavior, missing provenance/license, unsafe paths,
  and unknown fields quarantine with fixed reason codes;
- catalog references every one of the 17 candidates exactly once;
- catalog Recipe digest equals canonical generated bytes;
- quarantine evidence is preserved as inert data and never opened;
- no Recipe receives a placeholder URL, digest, executable, license, test, or
  compatibility rating;
- the complete real-data converted/quarantine counts are sealed only after the
  first reviewed GREEN result.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinRecipeConversionTests -v
```

Expected: FAIL because Recipe and quarantine rendering is not implemented.

**Step 3: Implement minimal deterministic conversion**

Implement explicit field maps, not generic key copying. Validate source keys
against per-version allowlists. Construct a Recipe only after all fields pass.
Otherwise construct one quarantine record with the first fixed rule in an
approved precedence table, while preserving all applicable reviewed evidence
locators in sorted order.

Render the catalog, Recipe files, and quarantine data in memory. Do not add
`--write` yet; create committed golden files with a one-off test-controlled
renderer invocation, then ensure Task 8 owns normal writes.

**Step 4: Run GREEN and seal reviewed counts**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinRecipeConversionTests -v
python -B scripts/validate_repository.py
```

Record the actual converted/quarantine counts in tests and the human migration
document only after inspecting every quarantined candidate. Add a table mapping
source ID to status/reason for review.

**Step 5: Commit**

```powershell
git add schemas/recipe.schema.json migration/macwin/generated/catalog.json migration/macwin/generated/recipes migration/macwin/generated/quarantine.json tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: convert frozen Mac-Win recipes"
```

### Task 6: Export portable probes, fixtures, and deferred mappings

At the Task 6 checkpoint, the top-level generated-evidence oracle accepts
exactly `catalog.json`, `quarantine.json`, `mappings/patches.json`, and
`mappings/bottle-schemas.json`, with no other generated file or directory.
Task 7 explicitly replaces this checkpoint set when it adds the sealed root
index and any newly approved generated graph leaves; the Task 5 two-leaf
sub-oracle remains independently reusable inside both checkpoints.

**Files:**
- Modify: `tools/convert_macwin_assets.py`
- Create: `migration/macwin/generated/probes/*.json`
- Create: `migration/macwin/generated/fixtures/*.json`
- Create: `migration/macwin/generated/mappings/patches.json`
- Create: `migration/macwin/generated/mappings/bottle-schemas.json`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing category-output tests**

Add `MacWinPortableAssetTests` for:

- 26 probe identities and 30 fixture identities are each portable or
  quarantined exactly once;
- portable records use safe relative content references, exact media types,
  `executable: false`, source provenance, intended owner, license, and digest;
- source modes such as `100755` never make migration assets executable;
- absolute/developer/environment/repository dependency locators remain inert
  evidence and force quarantine when not closed over the source pack;
- 11 exact patch mappings have `status: deferred`, target `MW-ASSET-002`, and no
  apply/runtime fields;
- four exact Bottle mappings have `status: deferred`, target `MW-ASSET-003`, and
  no conversion/write fields;
- linked/missing/modified source objects reject before output construction;
- asset bytes are never imported/executed as Python, shell, registry, C, or PE.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinPortableAssetTests -v
```

Expected: FAIL for missing portable and deferred outputs.

**Step 3: Implement category-specific exporters**

Use explicit source-path/kind tables for media type and migration policy. Store
raw portable content by content digest under generated category directories only
when all dependencies are closed. Otherwise reuse the Task 5 quarantine model.
Never infer an executable policy from Git mode or filename.

**Step 4: Run GREEN and exact-count validation**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinPortableAssetTests -v
```

Inspect every portable/quarantine decision before sealing the actual category
counts.

**Step 5: Commit**

```powershell
git add migration/macwin/generated/probes migration/macwin/generated/fixtures migration/macwin/generated/mappings tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: export portable Mac-Win migration assets"
```

### Task 7: Render the root index and validate the complete output graph

**Files:**
- Modify: `tools/convert_macwin_assets.py`
- Modify: `scripts/validate_repository.py` (only the generated-tree checkpoint;
  the independent Task 5 and Task 6 semantic oracles remain intact)
- Create: `migration/macwin/generated/index.json`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing canonical graph tests**

Add `MacWinGeneratedGraphTests` for:

- root source identity, exact 90 coverage, category/status counts, and output
  document count;
- every generated document has a root index SHA-256 and byte size;
- every catalog Recipe, portable asset, deferred mapping, and quarantine
  reference resolves to exactly one bounded regular generated leaf;
- document paths and records are sorted/unique;
- all JSON is strict UTF-8, exact canonical LF, closed, and at most 1 MiB;
- missing/extra/reordered/modified output, stale digest, unknown field, invalid
  reference, circular reference, and single-byte drift reject;
- source provenance in every output equals source-pack provenance;
- a forged output with a recomputed root digest still rejects on semantic graph
  mismatch.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinGeneratedGraphTests -v
```

Expected: FAIL because root index/graph validation is missing.

**Step 3: Implement root rendering and graph validation**

Build the root index last from the complete in-memory document map. Validate the
graph independently from the renderer so a renderer bug cannot validate itself.
The validator accepts a document map and source pack, expands all identities,
and compares exact normalized records.

**Step 4: Run GREEN and whole-file mutation matrix**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinGeneratedGraphTests -v
```

For every generated JSON file, flip each byte position in a controlled subtest
or use an equivalent exhaustive seal mutation where runtime remains bounded.
Ensure the validator rejects before trusting dependent content.

**Step 5: Commit**

```powershell
git add migration/macwin/generated/index.json tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: seal the portable asset graph"
```

### Task 8: Add safe CLI check, transactional write, and explain modes

**Files:**
- Modify: `tools/convert_macwin_assets.py`
- Modify: `scripts/validate_repository.py`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing CLI and transaction tests**

Add `MacWinMigrationCliTests` and `MacWinMigrationTransactionTests` for:

- default and `--check` are read-only and compare exact worktree bytes;
- `--write` stages all new outputs and rollback sources before the first replace,
  fsyncs/readback verifies, and is byte-identical on repeat;
- replacement failures at every destination restore the complete previous set;
- missing destination, ordinary hardlink, symlink/reparse parent/leaf, directory,
  non-regular leaf, same-identity in-place content mutation, staged input
  substitution, destination substitution, and parent replacement have explicit
  Windows/POSIX behavior;
- no file is ever created outside the bound generated directory, even
  transiently;
- `--explain <source-id>` is bounded deterministic JSON and never probes evidence
  locators;
- unknown/abbreviated/hostile argv yields stable exit 2, usage, no traceback, and
  no hostile reflection;
- generation errors yield stable exit 1, empty stdout, one-line stderr, no
  traceback/reflection;
- only the narrow migration error type is normalized; `OSError`/programmer errors
  used by direct API tests are not broadly swallowed;
- repository validator invokes converter `--check` with bytecode disabled and
  cannot report success before it passes.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationCliTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationTransactionTests -v
```

Expected: FAIL because CLI and transaction functions do not exist.

**Step 3: Implement the CLI and transaction**

Use `argparse.ArgumentParser(allow_abbrev=False)` with mutually exclusive
`--check`, `--write`, and `--explain`. The writer must use platform-specific
no-follow directory/leaf handles and expected identity plus expected raw-byte
binding. On POSIX use `dir_fd`, `O_NOFOLLOW`, `fstat`, and an atomic conditional
replacement strategy; on Windows use no-follow handles, file IDs, share modes,
and atomic replace. Fail closed if the platform cannot meet the transaction
contract.

Remove any temporary Task 1 repository-validator skip. Invoke converter
validation in-process only through an import-safe read-only API or as a fixed
Python `-B` subprocess with exact argv/env/cwd; test whichever boundary is
selected.

**Step 4: Run GREEN and two-write proof**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationCliTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationTransactionTests -v
python -B tools/convert_macwin_assets.py --check
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --write
git status --short
```

Expected: all tests/commands pass; both writes leave identical output bytes and
an empty status.

**Step 5: Commit**

```powershell
git add tools/convert_macwin_assets.py scripts/validate_repository.py tests/test_macwin_asset_migration.py migration/macwin/generated
git commit -s -m "feat: validate portable asset generation"
```

### Task 9: Prove side-effect freedom and publish the migration boundary

**Files:**
- Create: `docs/migration/macwin-portable-assets.md`
- Modify: `README.md`
- Modify: `docs/testing.md`
- Modify: `tests/test_macwin_asset_migration.py`

**Step 1: Write failing side-effect and documentation tests**

Add `MacWinMigrationSideEffectTests` and `MacWinMigrationDocumentationTests`:

- snapshot source/generated bytes, Git status/index/refs/object DB/config,
  Runtime Pack store, Bottle fixtures, external sentinels, environment, and
  repository caches before/after default/check/explain/validator/two writes;
- guard `subprocess.Popen`, socket/connect/DNS APIs, URL openers, environment
  lookup, home expansion, locator `exists/stat/open`, dynamic imports, and asset
  execution entrypoints; permit only explicitly audited repository test commands;
- controlled mutants prove each guard genuinely turns RED;
- docs state exact source identity/counts, actual converted/quarantine counts,
  deferred issues, non-claims, 1 MiB bounds, command sequence, owner, and release
  criteria;
- README has a visible link without weakening existing project status;
- whole-document raw-byte seal rejects CRLF, mixed/lone CR, comments, non-UTF8,
  oversize, and semantic decoys before comment stripping.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationSideEffectTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationDocumentationTests -v
```

Expected: missing docs and guard assertions fail; controlled mutants escape until
the guard is complete.

**Step 3: Implement documentation and complete guards**

Document only claims proven by generated bytes. Distinguish source pack,
converter `--check`, repository validator, quarantine, deferred mapping, and
runtime non-consumption boundaries. The issue owner is the stable migration
domain, not a personal account.

**Step 4: Run GREEN and controlled RED→GREEN proofs**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationSideEffectTests -v
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationDocumentationTests -v
python -B scripts/validate_repository.py
```

For each side-effect family, apply a controlled in-memory mutant, observe the
expected test failure, restore it, and rerun GREEN.

**Step 5: Commit**

```powershell
git add README.md docs/migration/macwin-portable-assets.md docs/testing.md tests/test_macwin_asset_migration.py
git commit -s -m "docs: publish the portable asset boundary"
```

### Task 10: Integrate CI, run fresh verification, and complete two-stage review

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify only review findings in other files; each finding gets an isolated DCO
  commit.

**Step 1: Write failing workflow tests**

Add tests that parse the workflow with duplicate-key rejection and require:

- pinned `actions/checkout` and `actions/setup-python` SHAs, not mutable tags;
- `permissions: contents: read` and no write/secret capabilities;
- Python 3.12 on the contracts job;
- order: repository validation, migration `--check`, then existing header checks;
- Linux/macOS/Windows Rust jobs also run migration `--check` so all platforms
  validate identical digests;
- no `--write`, importer invocation, asset execution, URL download, shell
  interpolation, or failure masking;
- all existing Runtime Pack, PE, Provider, C ABI, fmt/check/test/clippy steps remain
  semantically intact.

**Step 2: Run RED**

```powershell
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -k MacWinMigrationWorkflowTests -v
```

Expected: FAIL because CI does not run migration checks and actions use mutable
tags.

**Step 3: Implement the minimum CI gate**

Pin approved action commit SHAs. Add only read-only migration checks. Do not
alter Runtime Pack/provider behavior or introduce asset execution.

**Step 4: Run the complete fresh matrix**

Use an owned process-local TEMP/TMP directory. Run serially:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m unittest discover -s tests -p 'test_macwin_asset_migration.py' -v
python -B scripts/validate_repository.py
python -B tools/convert_macwin_assets.py --check
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
git diff --check origin/main...HEAD
git status --short --branch
```

Also prove:

- two `--write` runs are byte-identical;
- source pack and generated graph counts/digests are exact;
- no cache, bytecode, transaction temp, Runtime/Bottle mutation, or external
  sentinel change exists;
- every branch commit contains a DCO trailer;
- the Mac-Win tag object/source identity and CompatForge `origin/main` base are
  unchanged;
- normal and deliberately hostile environment runs produce the same results.

**Step 5: Commit CI**

```powershell
git add .github/workflows/ci.yml tests/test_macwin_asset_migration.py
git commit -s -m "ci: verify portable Mac-Win assets"
```

**Step 6: Request specification review**

Use `@superpowers:requesting-code-review`. The reviewer is read-only and must
compare issue `MW-ASSET-001`, the approved design, and this complete plan against
`origin/main...HEAD`. Findings are Critical/Important/Minor with commands and
line references.

Resolve every accepted Critical/Important/Minor with
`@superpowers:receiving-code-review`, `@superpowers:systematic-debugging`, and
`@superpowers:test-driven-development`: reproduce RED, implement minimum GREEN,
run focused/full verification, commit with DCO, and return to the same reviewer.

**Step 7: Request independent code-quality review**

Use a separate read-only reviewer for deterministic parsing/rendering, path and
file bounds, source/output identity, transaction rollback, side-effect guards,
diagnostics, cross-platform behavior, test false-greens, and CI failure
propagation. Resolve all findings through the same isolated RED→GREEN process.

**Step 8: Prepare the GitHub handoff only after both reviews pass 0/0/0**

Run the complete fresh matrix again on the final HEAD. Then push
`agent/macwin-portable-assets`, create a draft CompatForge PR linked to Mac-Win
issue `MW-ASSET-001`, and wait for every required Linux/macOS/Windows contract,
Rust, and migration job. Do not merge or close the Mac-Win issue until the merge
commit, generated counts/digests, quarantine evidence, and CI URLs are recorded.

## Execution Handoff

Plan complete and saved to
`docs/plans/2026-08-13-macwin-portable-assets.md`.

Two execution options:

1. **Subagent-Driven (this session)** — dispatch a fresh implementation agent per
   task with specification and quality review checkpoints.
2. **Parallel Session (separate)** — open a new session in this worktree and use
   `superpowers:executing-plans` in batches with review checkpoints.
