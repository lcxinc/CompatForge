# Mac-Win Bottle Read-Only Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a cross-platform offline Bottle migration store that snapshots a user-selected Mac-Win Bottle without modifying it, produces sealed planning parity evidence, imports a complete CompatForge version pinned to an exact Runtime Pack, and verifies or rolls back that version safely.

**Architecture:** Add a new `compatforge-bottle` crate with closed contracts, a content-addressed snapshot store, pure planning, and immutable version/ref transactions. Extend the CLI with explicit snapshot/plan/import/verify/rollback stages, then seal two representative fixtures and enforce the complete boundary in the repository validator and three-platform CI.

**Tech Stack:** Rust 1.78, `serde`, `serde_json`, RustCrypto `sha2`, `libc`, existing `compatforge-domain`, `compatforge-storage`, and `compatforge-runtime`; Python 3.12 standard-library contract tests and repository validator; GitHub Actions on Linux, macOS, and Windows.

---

## Execution Rules

- Use `@superpowers:test-driven-development` for every production change.
- Run Cargo with `CARGO_TARGET_DIR` outside the repository because the
  repository validator deliberately scans ignored files for developer paths.
  In this worktree use
  `L:\project\FOS\.codex-tmp\compatforge-mw-asset-003-target`.
- For each RED, confirm that the assertion fails for the missing behavior, not
  for a fixture typo or compilation error.
- Do not run the long Python migration suite concurrently with the repository
  validator or another fixture-mutating test.
- Use canonical JSON: sorted object keys, two-space pretty output, one trailing
  LF for committed documents; compact canonical preimages for digests.
- Use DCO (`git commit -s`) for every commit.
- Never read or modify the neighboring `Mac-Win` checkout from production code,
  tests, validator, or CI.

### Task 1: Create closed Bottle migration contracts

**Files:**
- Modify: `Cargo.toml`
- Modify: `Cargo.lock`
- Create: `crates/compatforge-bottle/Cargo.toml`
- Create: `crates/compatforge-bottle/src/lib.rs`
- Create: `crates/compatforge-bottle/src/contract.rs`
- Create: `crates/compatforge-bottle/src/error.rs`
- Modify: `crates/compatforge-domain/src/lib.rs:762-822`

**Step 1: Write the failing domain and crate tests**

Add tests that require:

```rust
#[test]
fn bottle_manifest_rejects_unknown_versions_and_unpinned_runtime() {
    let mut manifest = valid_bottle_manifest();
    manifest.runtime_pack.digest = "sha256:0000".into();
    assert_eq!(
        manifest.validate(),
        Err(ContractError::UnsupportedValue("bottle.runtimePack.digest"))
    );
}

#[test]
fn legacy_contract_is_closed_and_bounded() {
    let error = LegacyBottleManifest::from_json(
        br#"{"id":"sample","unknown":true}"#,
    ).unwrap_err();
    assert_eq!(error.code(), DiagnosticCode::InvalidManifest);
}
```

Also cover JSON bool-vs-integer distinctions, duplicate launcher IDs, launcher
Bottle ID mismatch, empty/oversized text, unknown fields, invalid RFC 3339
timestamps, win32/win64 only, and exact collection bounds.

**Step 2: Run the tests and verify RED**

Run:

```powershell
$env:CARGO_TARGET_DIR='L:\project\FOS\.codex-tmp\compatforge-mw-asset-003-target'
cargo test -p compatforge-domain bottle_manifest --locked
cargo test -p compatforge-bottle contract --locked
```

Expected: the domain test fails because `BottleManifest::validate` is missing,
and the new package/API does not yet exist.

**Step 3: Implement the minimal contracts**

Define closed `serde(deny_unknown_fields)` types for:

```rust
pub struct LegacyBottleManifest {
    pub id: String,
    pub name: String,
    pub windows_version: String,
    pub arch: LegacyWineArch,
    pub engine_id: String,
    pub env_overrides: BTreeMap<String, String>,
    pub installed_apps: Vec<LegacyLauncher>,
    pub created_at: String,
    pub updated_at: String,
}

pub struct LegacyLauncher {
    pub id: String,
    pub app_id: String,
    pub bottle_id: String,
    pub display_name: String,
    pub exe_path: String,
    pub args: Vec<String>,
    pub icon_path: Option<String>,
    pub env_overrides: BTreeMap<String, String>,
    pub show_in_home: bool,
}

pub enum DiagnosticCode {
    SourceChanged,
    UnsafeEntry,
    InvalidManifest,
    RuntimeUnmapped,
    RuntimeMismatch,
    SnapshotCorrupt,
    TargetCollision,
    TransactionFailed,
    RollbackUnavailable,
    RollbackCorrupt,
}
```

Add `BottleManifest::validate` in the domain crate. Validate schema version,
IDs, digest, timestamps, guest combination, Recipe uniqueness, layout version,
and state without adding migration-specific policy to the generic DTO.

**Step 4: Run GREEN and the adjacent domain suite**

Run:

```powershell
cargo test -p compatforge-domain --locked
cargo test -p compatforge-bottle contract --locked
cargo fmt --all -- --check
```

Expected: PASS with no warnings.

**Step 5: Commit**

```powershell
git add Cargo.toml Cargo.lock crates/compatforge-domain crates/compatforge-bottle
git commit -s -m "feat: define Bottle migration contracts"
```

### Task 2: Publish JSON schemas and an independent schema oracle

**Files:**
- Create: `schemas/bottle-snapshot.schema.json`
- Create: `schemas/bottle-runtime-map.schema.json`
- Create: `schemas/bottle-migration-plan.schema.json`
- Create: `schemas/bottle-active-ref.schema.json`
- Create: `tests/test_bottle_migration_contracts.py`
- Modify: `.gitattributes`

**Step 1: Write failing standard-library schema tests**

Create `BottleMigrationSchemaTests` using the existing Draft 2020-12
standard-library oracle pattern. Require exact closed top-level fields, const
schema versions, exact type semantics, safe identifiers/digests/paths,
collection bounds, sorted/unique records, and conditional entry fields.

Include mutants for:

- extra fields;
- integer `1` for boolean `true`;
- uppercase or short digests;
- duplicate runtime mappings;
- file entries without digest/size;
- directories with file-only fields;
- links with absolute or escaping targets;
- active history longer than 32;
- plan Runtime ID/digest not equal to the Bottle manifest binding.

**Step 2: Verify RED**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationSchemaTests
```

Expected: ERROR because the four schemas are absent.

**Step 3: Add minimal closed schemas**

Each schema must:

- use Draft 2020-12 and a unique
  `https://compatforge.dev/schemas/<name>` ID;
- have `additionalProperties: false` at every object layer;
- use lowercase `sha256:<64 hex>` digests;
- cap all strings, arrays, and numeric values;
- model file/directory/link entries with `oneOf` and disjoint required fields;
- require exact Runtime Pack ID/digest equality in the plan via the test oracle
  where JSON Schema cannot express cross-field equality.

Add explicit LF attributes for the schemas and Bottle migration fixture JSON.

**Step 4: Verify GREEN and mutation effectiveness**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationSchemaTests
git diff --check
```

Temporarily loosen one digest pattern and prove the corresponding mutant test
fails, then restore it and rerun GREEN.

**Step 5: Commit**

```powershell
git add .gitattributes schemas tests/test_bottle_migration_contracts.py
git commit -s -m "feat: add Bottle migration schemas"
```

### Task 3: Snapshot regular files into an immutable object store

**Files:**
- Create: `crates/compatforge-bottle/src/snapshot.rs`
- Create: `crates/compatforge-bottle/src/digest.rs`
- Modify: `crates/compatforge-bottle/src/lib.rs`
- Test: `crates/compatforge-bottle/src/snapshot.rs`

**Step 1: Write a failing happy-path snapshot test**

Build a temporary Bottle containing canonical `manifest.json`, an empty
directory, and two identical regular files. Require:

```rust
let receipt = BottleStore::new(store).snapshot(&source).unwrap();
assert_eq!(receipt.entry_count, 4);
assert_eq!(receipt.total_file_bytes, expected_bytes);
assert_eq!(receipt.snapshot_digest, expected_snapshot_digest);
assert_eq!(object_count(&store), 2); // manifest plus deduplicated payload
assert_eq!(fs::read(source.join("payload.txt")).unwrap(), b"public fixture\n");
```

**Step 2: Verify RED**

Run `cargo test -p compatforge-bottle snapshot_regular_files --locked`.

Expected: FAIL because `BottleStore::snapshot` is missing.

**Step 3: Implement streaming objects and canonical manifests**

Implement:

```rust
impl BottleStore {
    pub fn snapshot(&self, source: &Path) -> Result<SnapshotReceipt, BottleMigrationError>;
    pub fn verify_snapshot(&self, digest: &str) -> Result<BottleSnapshot, BottleMigrationError>;
}
```

Use a fixed 64 KiB buffer, `sha2::Sha256`, `create_new` temporary objects,
`sync_all`, digest readback, idempotent object collision comparison, canonical
compact digest preimages, and pretty-LF published manifests. Publish the
manifest only after every object is durable and verified.

**Step 4: Verify GREEN and idempotence**

Run:

```powershell
cargo test -p compatforge-bottle snapshot --locked
cargo test -p compatforge-bottle object --locked
```

Call snapshot twice and require identical receipt bytes, no extra object, and
no source metadata change.

**Step 5: Commit**

```powershell
git add crates/compatforge-bottle
git commit -s -m "feat: snapshot legacy Bottles by content"
```

### Task 4: Bind traversal, links, bounds, and source races

**Files:**
- Create: `crates/compatforge-bottle/src/platform.rs`
- Create: `crates/compatforge-bottle/src/path.rs`
- Modify: `crates/compatforge-bottle/src/snapshot.rs`
- Modify: `crates/compatforge-bottle/Cargo.toml`
- Modify: `Cargo.lock`
- Test: `crates/compatforge-bottle/src/snapshot.rs`

**Step 1: Write failing adversarial traversal tests**

Add one focused test per behavior:

- source root, parent, directory, or leaf replacement;
- same-size mutation with restored timestamp;
- late child insertion/deletion;
- absolute, escaping, cyclic, and external relative links;
- safe internal relative link;
- FIFO/socket/device/reparse/non-regular entry;
- case-fold collision, leaf/directory prefix collision, reserved name,
  trailing-dot/space, control, invalid path component;
- exact pass/fail boundaries for 4096 bytes, depth 128, 100,000 entries,
  64 GiB file, 1 TiB total, and 64 MiB manifest using injected metadata/readers
  rather than allocating huge fixtures.

Each failure test snapshots source bytes, metadata, identities, store ref tree,
and an external sentinel before and after.

**Step 2: Verify RED**

Run `cargo test -p compatforge-bottle snapshot_security --locked`.

Expected: tests demonstrate at least the link and replacement attacks are
accepted by the Task 3 pathname implementation.

**Step 3: Implement held traversal**

Use platform modules:

- POSIX: held root/parent `File`, `openat`, `fstatat`, `readlinkat`,
  `O_NOFOLLOW`, and final root/directory enumeration revalidation;
- Windows: `OpenOptionsExt` with backup semantics/open-reparse-point flags,
  share modes that deny delete while bound, file identity and reparse checks,
  and identity revalidation around any path API needed to read a safe link.

Preflight normalized leaf paths and implied directories before publishing any
object. Transfer handle ownership only on success and close every failure path,
including `BaseException`-equivalent Rust unwinding tests via `catch_unwind`.

**Step 4: Verify GREEN on available platforms**

Run:

```powershell
cargo test -p compatforge-bottle snapshot_security --locked
cargo test -p compatforge-bottle resource_cleanup --locked
```

On Windows, assert process handle count returns to baseline. On POSIX CI, assert
`/proc/self/fd` or a close-spy proves each acquired descriptor is closed.

**Step 5: Commit**

```powershell
git add Cargo.toml Cargo.lock crates/compatforge-bottle
git commit -s -m "fix: bind Bottle snapshot traversal"
```

### Task 5: Derive a sealed migration plan and Runtime Pack binding

**Files:**
- Create: `crates/compatforge-bottle/src/plan.rs`
- Modify: `crates/compatforge-bottle/src/contract.rs`
- Modify: `crates/compatforge-bottle/src/lib.rs`
- Modify: `crates/compatforge-runtime/src/lib.rs`
- Test: `crates/compatforge-bottle/src/plan.rs`

**Step 1: Write failing mapping tests**

Require a pure API:

```rust
let plan = store.plan(
    &snapshot_digest,
    &RuntimePackStore::new(runtime_store),
    &runtime_map,
).unwrap();
assert_eq!(plan.bottle.runtime_pack.id, "fixture-runtime");
assert_eq!(plan.bottle.runtime_pack.digest, FIXTURE_RUNTIME_V2_DIGEST);
assert_eq!(plan.launchers[0].environment["SHARED"], "launcher");
```

Add RED tests for missing/duplicate engine mapping, valid-shape wrong Runtime
ID, valid-shape wrong digest, corrupt installed object, unsupported Windows
version/arch, duplicate launcher, Bottle ID mismatch, unsafe executable/icon,
environment collision rules, and a forged snapshot manifest with a resealed
digest.

**Step 2: Verify RED**

Run `cargo test -p compatforge-bottle planning --locked`.

Expected: FAIL because planning and a verified Runtime manifest lookup API are
missing.

**Step 3: Implement exact planning**

Expose a read-only Runtime API that returns a manifest only after digest and
all objects verify. In the Bottle crate:

- parse legacy JSON only from the verified snapshot object;
- require one exact runtime mapping;
- compare mapping ID to verified Runtime manifest ID;
- map win32/win64 and timestamps exactly;
- merge Bottle environment first and launcher environment second;
- sort launchers and maps canonically;
- generate a target `BottleManifest`, closed launcher inputs, fixed diagnostics,
  target digest, and plan digest;
- never create a Recipe reference from a legacy launcher.

**Step 4: Verify GREEN and generic Runtime regressions**

Run:

```powershell
cargo test -p compatforge-bottle planning --locked
cargo test -p compatforge-runtime --locked
cargo test -p compatforge-domain --locked
```

**Step 5: Commit**

```powershell
git add crates/compatforge-bottle crates/compatforge-runtime crates/compatforge-domain Cargo.lock
git commit -s -m "feat: plan exact Bottle migrations"
```

### Task 6: Add representative fixtures and independent golden parity

**Files:**
- Create: `tests/fixtures/bottle-migration/win64/manifest.json`
- Create: `tests/fixtures/bottle-migration/win64/drive_c/Public/example.txt`
- Create: `tests/fixtures/bottle-migration/win32/manifest.json`
- Create: `tests/fixtures/bottle-migration/win32/drive_c/Public/example.txt`
- Create: `tests/fixtures/bottle-migration/runtime-map.json`
- Create: `tests/fixtures/bottle-migration/goldens/win64-legacy-planning.json`
- Create: `tests/fixtures/bottle-migration/goldens/win64-migration-plan.json`
- Create: `tests/fixtures/bottle-migration/goldens/win64-launch-plan.json`
- Create: `tests/fixtures/bottle-migration/goldens/win32-legacy-planning.json`
- Create: `tests/fixtures/bottle-migration/goldens/win32-migration-plan.json`
- Create: `tests/fixtures/bottle-migration/goldens/win32-launch-plan.json`
- Modify: `tests/test_bottle_migration_contracts.py`
- Modify: `crates/compatforge-bottle/src/plan.rs`

**Step 1: Write failing independent golden tests**

The Python oracle must parse the fixture directly, build an independent legacy
planning projection, validate all schema documents, and compare exact canonical
bytes and literal SHA-256 constants. Do not call Rust to construct expected
values.

Add self-consistent forgery tests that modify a launcher, Runtime digest, or
environment in both a generated plan and its apparent root digest; the
independent oracle must still reject the fixture.

**Step 2: Verify RED**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationGoldenTests
```

Expected: ERROR for missing fixtures/goldens.

**Step 3: Add minimal public text fixtures and goldens**

The win64 fixture contains multiple launchers and overlapping Bottle/launcher
environment keys. The win32 fixture is minimal. Use the existing public
Runtime Pack fixture v2 and its fixed digest. Store no executable, Wine binary,
commercial content, host path, or Mac-Win checkout data.

Generate candidate actual output once, review every field against the
independent projection, then commit the reviewed bytes and literal digests.

**Step 4: Verify GREEN and mutation gates**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationGoldenTests
cargo test -p compatforge-bottle planning_golden --locked
```

Temporarily alter one golden byte and separately alter a fixed digest; prove
each test RED, restore, and rerun GREEN.

**Step 5: Commit**

```powershell
git add tests/fixtures/bottle-migration tests/test_bottle_migration_contracts.py crates/compatforge-bottle
git commit -s -m "test: seal Bottle planning parity"
```

### Task 7: Transactionally import immutable Bottle versions

**Files:**
- Create: `crates/compatforge-bottle/src/store.rs`
- Modify: `crates/compatforge-bottle/src/lib.rs`
- Modify: `crates/compatforge-bottle/src/contract.rs`
- Test: `crates/compatforge-bottle/src/store.rs`

**Step 1: Write failing install transaction tests**

Require:

```rust
let receipt = store.import(&plan).unwrap();
assert_eq!(receipt.bottle_id, plan.bottle.id);
assert_eq!(store.active_plan(&plan.bottle.id).unwrap(), Some(plan.digest));
store.verify_active(&plan.bottle.id).unwrap();
```

Add a failure injector covering every object materialization, directory create,
file create/write/sync/readback, version publish, ref stage/sync/replace, and
final verify ordinal. Snapshot source, old active ref, target tree, and external
sentinel before every injected failure.

**Step 2: Verify RED**

Run `cargo test -p compatforge-bottle import_transaction --locked`.

Expected: FAIL because import/active APIs do not exist.

**Step 3: Implement stage-verify-publish-ref**

Implement an explicit transaction state machine:

```rust
enum ImportPhase {
    Preflight,
    Staged,
    VersionPublished,
    RefPublished,
}
```

Preflight the complete output graph before creating the transaction. Stage all
new leaves and trusted rollback/ref bytes, fsync, read back and bind identities,
publish an immutable version without overwriting an unequal existing version,
then atomically replace the ref. A repeated identical import is a true no-op.

**Step 4: Verify GREEN and failure cleanup**

Run:

```powershell
cargo test -p compatforge-bottle import_transaction --locked
cargo test -p compatforge-bottle import_failure_ordinals --locked
```

Require no transaction residue after success or proven rollback and unchanged
source metadata on all paths.

**Step 5: Commit**

```powershell
git add crates/compatforge-bottle
git commit -s -m "feat: import immutable Bottle versions"
```

### Task 8: Verify active versions and roll back safely

**Files:**
- Modify: `crates/compatforge-bottle/src/store.rs`
- Modify: `crates/compatforge-bottle/src/contract.rs`
- Test: `crates/compatforge-bottle/src/store.rs`

**Step 1: Write failing verify/rollback tests**

Install two plans for one Bottle, then require the second active and rollback
to the first. Add RED cases for tampered version file, object, snapshot,
manifest, migration plan, current ref, history entry, Runtime object, and
same-byte replacement identity.

Also inject failure at each rollback stage and prove the active ref remains the
second plan.

**Step 2: Verify RED**

Run `cargo test -p compatforge-bottle rollback --locked`.

Expected: FAIL because rollback is absent.

**Step 3: Implement verify-before-switch rollback**

`verify_active` must bind and rehash the active ref, version manifest,
migration plan, prefix tree, snapshot manifest, objects, and Runtime Pack. The
rollback path must fully verify the historical target before staging a new ref
and must revalidate the current state immediately before replacement.

Cap history at 32, reject duplicate/current entries in history, and never
discard history until the new ref is durable and read back.

**Step 4: Verify GREEN**

Run:

```powershell
cargo test -p compatforge-bottle verify_active --locked
cargo test -p compatforge-bottle rollback --locked
```

**Step 5: Commit**

```powershell
git add crates/compatforge-bottle
git commit -s -m "feat: verify and roll back Bottle versions"
```

### Task 9: Add bounded CLI commands

**Files:**
- Modify: `apps/cli/Cargo.toml`
- Modify: `apps/cli/src/main.rs`
- Modify: `Cargo.lock`
- Test: `apps/cli/src/main.rs`
- Test: `tests/test_bottle_migration_contracts.py`

**Step 1: Write failing CLI tests**

Add CLI integration tests for exact argv, help text, canonical success receipt,
closed error diagnostic, exit code 1, empty stdout on failure, no reflected
absolute path, output at most 1 MiB, and all five subcommands.

Run the binary twice for snapshot/plan/import/verify and require byte-identical
output where the operation is a no-op.

**Step 2: Verify RED**

Run:

```powershell
cargo test -p compatforge-cli bottle_cli --locked
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationCliTests
```

Expected: FAIL because the `bottle` command group is absent.

**Step 3: Implement the minimal command group**

Parse only exact positional forms documented in the design. Call the crate API,
serialize one canonical receipt to stdout, and convert
`BottleMigrationError::diagnostic()` to fixed JSON on stderr. Unknown or
incomplete commands print help without accessing the filesystem.

Do not read environment variables or current-directory-relative defaults.

**Step 4: Verify GREEN**

Run:

```powershell
cargo test -p compatforge-cli bottle_cli --locked
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationCliTests
```

**Step 5: Commit**

```powershell
git add apps/cli Cargo.lock tests/test_bottle_migration_contracts.py
git commit -s -m "feat: expose Bottle migration CLI"
```

### Task 10: Enforce repository contracts, docs, and CI

**Files:**
- Modify: `scripts/validate_repository.py`
- Modify: `tests/test_bottle_migration_contracts.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/testing.md`
- Modify: `docs/migration/work-breakdown.md`
- Modify: `docs/architecture/component-model.md`
- Create: `docs/implementation/phase-1-bottle-migration.md`

**Step 1: Write failing repository/documentation tests**

Require the validator to authenticate:

- exact schemas and their fixed digests;
- exact fixture/golden tree and fixed bytes;
- independent legacy-to-new semantic projection;
- no missing/extra/link/non-regular fixture entries;
- all documented commands, Runtime digest, fixture counts, and golden digests;
- the CLI crate as a workspace dependency and all five commands in CI.

Add self-consistent fixture/golden/schema forgery mutants and final
revalidation races.

**Step 2: Verify RED**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationRepositoryTests
python -S -B scripts/validate_repository.py
```

Expected: new tests fail because the validator/docs/CI do not yet bind Bottle
migration artifacts.

**Step 3: Implement an independent validator oracle**

Use only Python standard library and literal trust roots. Do not import or call
the Rust crate to construct expected values. Bind directory and leaf identities
through final success, limit entries/bytes, parse closed JSON, recompute source
and golden semantics, and reject missing/extra safe files as well as unsafe
entries.

Document the store, CLI, exact non-goals, golden parity, source-read-only proof,
Runtime binding, failure diagnostics, and rollback sequence. Add a three-
platform CI sequence using the public text fixtures and fixed snapshot/plan
digests.

**Step 4: Verify GREEN**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts
python -S -B scripts/validate_repository.py
git diff --check
```

Temporarily alter one schema, fixture, golden, documented digest, and CI command
in isolation; prove each gate RED, restore, and rerun GREEN.

**Step 5: Commit**

```powershell
git add scripts/validate_repository.py tests/test_bottle_migration_contracts.py .github/workflows/ci.yml docs
git commit -s -m "docs: publish Bottle migration evidence"
```

### Task 11: Close side-effect, race, and boundedness gaps

**Files:**
- Modify: `crates/compatforge-bottle/src/platform.rs`
- Modify: `crates/compatforge-bottle/src/snapshot.rs`
- Modify: `crates/compatforge-bottle/src/store.rs`
- Modify: `tests/test_bottle_migration_contracts.py`
- Modify: `scripts/validate_repository.py`

**Step 1: Write controlled side-effect mutants**

Mutate production behind test injection points so each forbidden capability is
actually attempted:

- source open with write access, metadata update, rename, unlink, or temp file;
- network/socket/DNS;
- subprocess or executable loading;
- implicit environment, HOME, TEMP, or cwd lookup;
- neighboring Mac-Win path access;
- external link read/write;
- target creation before path graph preflight;
- transaction cleanup path substitution;
- post-final-validation source/ref/version mutation;
- unbounded output, manifest construction, traversal, or recursive cleanup.

Each guard test must first demonstrate RED against its controlled mutant.

**Step 2: Run the mutants and capture RED**

Run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts.BottleMigrationSideEffectTests
cargo test -p compatforge-bottle adversarial --locked
```

Expected: every mutant reaches the intended guard and is rejected; if a mutant
escapes, keep the RED and fix only that boundary.

**Step 3: Apply minimal fixes**

Use held-handle/dirfd operations, preflight exact path graphs, trusted in-memory
rollback bytes, final closed revalidation, incremental bounded enumeration, and
fixed-size output buffers. Do not add broad platform behavior not required by
the failing test.

**Step 4: Verify GREEN on Windows and cross-platform CI-compatible branches**

Run:

```powershell
cargo test -p compatforge-bottle --all-targets --locked
python -S -B -m unittest tests.test_bottle_migration_contracts
python -S -B scripts/validate_repository.py
```

When available, run POSIX focused tests in WSL and record capability skips
explicitly; never turn an attack test into an unconditional platform skip.

**Step 5: Commit**

```powershell
git add crates/compatforge-bottle tests/test_bottle_migration_contracts.py scripts/validate_repository.py
git commit -s -m "fix: close Bottle migration identity gaps"
```

### Task 12: Full verification, reviews, and issue evidence

**Files:**
- Modify only if a verified regression requires a TDD fix.

**Step 1: Read verification and review skills**

Use `@superpowers:verification-before-completion` and
`@superpowers:requesting-code-review` before making any completion claim.

**Step 2: Run fresh serial Python gates**

Ensure no Cargo `target/` exists in the repository, then run:

```powershell
python -S -B -m unittest tests.test_bottle_migration_contracts
python -S -B -m unittest tests.test_macwin_asset_migration
python -S -B scripts/validate_repository.py
python -S -B tools/convert_macwin_assets.py --check
```

Expected: all tests pass with only documented platform capability skips.

**Step 3: Run fresh Rust gates with the external target directory**

```powershell
$env:CARGO_TARGET_DIR='L:\project\FOS\.codex-tmp\compatforge-mw-asset-003-target'
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

Expected: all exit 0.

**Step 4: Run the exact CLI acceptance sequence twice**

Install the fixed preview Runtime Pack, snapshot each fixture, compare snapshot
and plan receipts to fixed digests, import, verify, import again as a byte-level
no-op, install the second representative version, roll back, and verify the
first version. Snapshot source fixtures, Runtime store, Git metadata, and an
external sentinel before/after; only the explicit Bottle store may change.

**Step 5: Audit Git and repository hygiene**

Run:

```powershell
git diff --check origin/main...HEAD
git status --short
git log --format='%H%n%B' origin/main..HEAD
git ls-files --eol
```

Require all commits to contain `Signed-off-by`, exact approved file scope, LF
for committed text, no `target`, `__pycache__`, `.pyc`, transaction, fixture,
or temporary residues, and no modifications to Mac-Win.

**Step 6: Request independent spec and quality reviews**

Spec review must trace every issue acceptance criterion to implementation and
fresh evidence. Quality review must independently replay source races, links,
runtime forgeries, self-consistent golden forgeries, every transaction failure
ordinal, rollback corruption, side-effect mutants, resource cleanup, and
cross-platform branches. Fix every finding with a new RED-GREEN commit and
return to the same reviewer until both report `C0/I0/M0`.

**Step 7: Publish completion evidence only after both reviews pass**

Post exact commits, fixture/golden/store digests, test counts, platform skips,
CLI sequence, source-untouched proof, Runtime binding, rollback proof, and
spec/quality results to `MW-ASSET-003`. Open a PR, wait for all required checks,
and merge only with explicit user approval. Leave `MW-ARCH-001` open.
