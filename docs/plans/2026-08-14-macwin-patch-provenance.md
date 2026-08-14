# Mac-Win Patch Provenance Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 11 generic deferred Mac-Win patch records with an offline, independently authenticated provenance review that quarantines every currently unlicensed patch and preserves exact upstream evidence without applying any patch.

**Architecture:** Add one closed, canonical manual-review ledger that is cross-bound to the immutable 11-record source-pack slice. Load it through the existing no-follow bounded file boundary, derive classification rather than trusting human-written dispositions, enrich the existing patch mapping, merge patch records into the existing quarantine document, and rebuild the existing five-file generated graph. Keep the converter and repository validator as independent oracles; neither normal path may fetch upstream data, execute an asset, or add a patch application capability.

**Tech Stack:** Python 3.12 standard library, JSON Schema Draft 2020-12 documents validated by the repository's standard-library oracle, `unittest`, canonical UTF-8/LF JSON, existing CompatForge migration transaction code, Rust workspace verification, Git/DCO.

---

## Execution Rules

- Work only in `L:\project\FOS\.worktrees\compatforge-mw-asset-002` on branch
  `agent/mw-asset-002-patch-provenance`.
- Read `docs/plans/2026-08-14-macwin-patch-provenance-design.md` before changing
  code.
- Use @superpowers:test-driven-development for every behavior change: observe a
  meaningful RED, implement the smallest GREEN, and retain the regression.
- Use @superpowers:systematic-debugging for every unexpected failure; do not
  patch symptoms or weaken existing guards.
- Use `apply_patch` for hand edits. Do not rewrite user work or use destructive
  Git commands.
- Use Python standard library only. Do not add `jsonschema`, a package manager,
  network access, or a Git subprocess to normal validation.
- Never execute, import, apply, compile, or load any of the 11 patch assets.
- Run long Python, converter, validator, and Rust gates serially because their
  temporary fixtures intentionally make concurrent repository scans fail
  closed.
- Every commit uses `git commit -s` and must leave a clean index/worktree.
- Before claiming completion use @superpowers:verification-before-completion.

## Approved Constants

Use these independently reviewed identities; do not rediscover them from a
mutable branch during normal execution:

```python
APPROVED_PATCH_REVIEW_SOURCE = {
    "repository": "a1112/Mac-Win",
    "sourceTag": "mw-migration-baseline-db12d5e",
    "sourceTagObject": "9f10d003382ce7ffbb269376c03477e17516302f",
    "sourceCommit": "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527",
    "inventoryCommit": "97f8423094d25325d8f864eb6f49a9e8628dbb93",
    "sourceIndexSha256": "1fc8b071a9c52c5f29d130e47e3bd1cb165effa860eaa45336c82ee07cafe3a3",
    "digestAlgorithm": "sha256",
}

APPROVED_PATCH_UPSTREAMS = {
    "jasp": {
        "repository": "https://github.com/jasp-stats/jasp-desktop",
        "referenceKind": "tag",
        "reference": "v0.97.1",
        "tagObject": None,
        "commit": "28be3fee5c7ce2119f1945acd0254eb4fb8cb6e2",
    },
    "wine": {
        "repository": "https://gitlab.winehq.org/wine/wine/",
        "referenceKind": "annotated-tag",
        "reference": "wine-11.11",
        "tagObject": "b08651f36865a3e1d9300d792df322d2ee8a807e",
        "commit": "f6c044e1890e84a4aa5e77e76ba7276a615630e1",
    },
}

EXPECTED_FINAL_STATUS_COUNTS = {
    "converted": 2,
    "deferred": 4,
    "quarantined": 84,
}
```

The exact 11 source paths are the sorted `patches` records in
`migration/macwin/source/index.json`. The ledger must copy source identity
fields from that authenticated index; hand-entered values are then pinned by
focused tests and the independent repository oracle.

### Task 1: Define the Closed Patch Review Schema and Golden Ledger

**Files:**

- Create: `schemas/macwin-patch-review.schema.json`
- Create: `migration/macwin/reviewed/patches.json`
- Modify: `tests/test_macwin_asset_migration.py` near `MigrationSchemaTests`
- Modify: `.gitattributes`

**Step 1: Write the missing-contract tests**

Add `MacWinPatchProvenanceTests` and make the first tests load the proposed
schema and ledger without importing production converter code:

```python
class MacWinPatchProvenanceTests(unittest.TestCase):
    REVIEW_RELATIVE = PurePosixPath("migration/macwin/reviewed/patches.json")
    SCHEMA_RELATIVE = PurePosixPath("schemas/macwin-patch-review.schema.json")

    def _strict_json(self, relative: PurePosixPath) -> object:
        common = _load_macwin_asset_common()
        return common.parse_json_bytes(
            (ROOT / relative).read_bytes(),
            label="Mac-Win patch review",
        )

    def test_patch_review_schema_is_closed_and_bounded(self) -> None:
        schema = self._strict_json(self.SCHEMA_RELATIVE)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["recordCount"], {"const": 11})
        self.assertEqual(schema["properties"]["records"]["minItems"], 11)
        self.assertEqual(schema["properties"]["records"]["maxItems"], 11)

    def test_patch_review_covers_the_exact_source_slice(self) -> None:
        review = self._strict_json(self.REVIEW_RELATIVE)
        source = self._strict_json(PurePosixPath("migration/macwin/source/index.json"))
        expected = sorted(
            (record for record in source["records"] if record["category"] == "patches"),
            key=lambda record: record["sourcePath"].encode("ascii"),
        )
        self.assertEqual(review["recordCount"], 11)
        self.assertEqual(
            [record["sourcePath"] for record in review["records"]],
            [record["sourcePath"] for record in expected],
        )
        for record, asset in zip(review["records"], expected, strict=True):
            self.assertEqual(record["sourceSha256"], asset["sha256"])
            self.assertEqual(record["gitBlobOid"], asset["gitBlobOid"])
            self.assertEqual(record["gitMode"], asset["gitMode"])
            self.assertEqual(record["byteSize"], asset["byteSize"])
```

Also extend `MigrationSchemaTests` so the new schema is part of the standard
library boundary oracle and schema inventory.

**Step 2: Run the focused tests and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_patch_review_schema_is_closed_and_bounded `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_patch_review_covers_the_exact_source_slice
```

Expected: two errors because the schema and ledger do not exist. Confirm there
is no syntax or test-discovery error.

**Step 3: Add the closed Draft 2020-12 schema**

Create a closed top-level object with these exact fields:

```json
{
  "schemaVersion": "1",
  "source": {},
  "recordCount": 11,
  "records": []
}
```

Define closed `$defs` for:

- lowercase 40-hex Git OIDs and 64-hex SHA-256;
- host-independent relative POSIX paths using the exact established pattern
  from `schemas/migration-record.schema.json`;
- bounded HTTPS evidence locators;
- project-license context;
- patch-license evidence with `reviewed`/`unresolved` dependent fields;
- upstream identity;
- preimage evidence with result enum `matched`, `mismatched`, `added`,
  `unproven`;
- the exact upstream-status, disposition, and reason enums from the design;
- sorted unique arrays bounded by the design limits.

The record's `additionalProperties` must be `false`. Conditional rules must
require SPDX and evidence only when patch license is `reviewed`, require
non-empty probe IDs only when disposition is `retained`, and require empty
probe IDs when quarantined.

**Step 4: Add the exact 11-record canonical ledger**

Populate all records in ASCII source-path order. For this approved first ledger:

```json
{
  "patchLicense": {"status": "unresolved"},
  "reviewDisposition": "quarantined",
  "reason": "missing-license",
  "regressionProbeIds": []
}
```

is required on every record. Record JASP and Wine project licenses only as
non-authorizing context. Preserve the exact verified base-result matrix from
the design; never rewrite `mismatched` or `unproven` as `matched`.

Use bounded purpose/application values derived from patch subjects and touched
paths:

```text
JASP dataset reset/model patches -> affected application "jasp-desktop"
JASP local build configuration    -> affected applications "jasp-desktop", "jasp-build"
Wine DComp/WinUI patches          -> affected applications "wine", "winui"
Wine shell32 patch                -> affected applications "wine", "shell32"
Wine data-json/imaging patches    -> affected applications "wine", named Windows API family
Wine native macOS integration     -> affected applications "wine", "macos-driver"
```

Do not add speculative copyright holders, SPDX expressions, upstream merge
commits, or regression probes.

**Step 5: Add mutation tests for the actual schema semantics**

Using the existing standard-library schema oracle, add table-driven mutants for:

```python
mutants = {
    "unknown-field": lambda value: value["records"][0].__setitem__("extra", True),
    "wrong-count": lambda value: value.__setitem__("recordCount", 12),
    "bad-path": lambda value: value["records"][0].__setitem__("sourcePath", "../patch"),
    "reviewed-without-spdx": lambda value: value["records"][0].__setitem__(
        "patchLicense", {"status": "reviewed"}
    ),
    "retained-without-probe": lambda value: value["records"][0].__setitem__(
        "reviewDisposition", "retained"
    ),
}
```

Each mutant must be rejected by the real stdlib oracle, not `re.fullmatch`
against isolated patterns.

**Step 6: Make LF treatment explicit and run GREEN**

Add:

```gitattributes
/migration/macwin/reviewed/*.json text eol=lf
/schemas/macwin-patch-review.schema.json text eol=lf
/docs/plans/*.md text eol=lf
```

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MigrationSchemaTests
git diff --check
```

Expected: all focused tests pass; all three new text classes have zero CR bytes.

**Step 7: Commit**

```powershell
git add .gitattributes schemas/macwin-patch-review.schema.json `
  migration/macwin/reviewed/patches.json tests/test_macwin_asset_migration.py
git commit -s -m "feat: record Mac-Win patch review evidence"
```

### Task 2: Authenticate and Parse the Review Ledger

**Files:**

- Modify: `tools/convert_macwin_assets.py:28-438,669-887`
- Modify: `tests/test_macwin_asset_migration.py` in `MacWinPatchProvenanceTests`

**Step 1: Write loader RED tests**

Add tests for:

- bounded canonical read of the real ledger;
- missing review file;
- review directory or leaf symlink/reparse point;
- hardlinked review leaf;
- oversized file before JSON parsing;
- duplicate key, invalid UTF-8, wrong source-index digest;
- same-size/restored-mtime mutation during read;
- replacement between authentication and final verification;
- exact/case-fold duplicate source identities;
- missing/extra/reordered source paths.

The happy-path assertion is:

```python
source_pack = converter.load_source_pack(ROOT)
review = converter.load_patch_review(ROOT, source_pack)
self.assertEqual(len(review.records), 11)
self.assertEqual(
    tuple(record.source_path for record in review.records),
    tuple(
        asset.source_path for asset in source_pack.assets
        if asset.category == "patches"
    ),
)
```

**Step 2: Run the loader test and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_loader_authenticates_exact_review_ledger
```

Expected: error because `load_patch_review` and its model do not exist.

**Step 3: Add immutable review models**

Add frozen, slotted models; keep untrusted nested dictionaries out of
`ConversionResult`:

```python
@dataclass(frozen=True, slots=True)
class PatchPreimageEvidence:
    path: str
    patch_old_blob: str | None
    upstream_blob_oid: str | None
    result: str

@dataclass(frozen=True, slots=True)
class PatchReviewRecord:
    source_path: str
    source_sha256: str
    git_blob_oid: str
    git_mode: str
    byte_size: int
    purpose: str
    affected_applications: tuple[str, ...]
    upstream_repository: str
    upstream_reference_kind: str
    upstream_reference: str
    upstream_tag_object: str | None
    upstream_commit: str
    preimages: tuple[PatchPreimageEvidence, ...]
    patch_author: str
    project_license_spdx: str
    project_license_locator: str
    patch_license_status: str
    patch_license_spdx: str | None
    patch_license_evidence: tuple[str, ...]
    external_dependencies: tuple[str, ...]
    development_dependencies: tuple[str, ...]
    upstream_status: str
    review_disposition: str
    reason: str
    release_condition: str
    regression_probe_ids: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class PatchReviewLedger:
    source_index_sha256: str
    records: tuple[PatchReviewRecord, ...]
```

Extend `ConversionResult` with `patch_review: PatchReviewLedger`.

**Step 4: Implement the bounded no-follow loader**

Add constants:

```python
PATCH_REVIEW_RELATIVE = PurePosixPath("migration/macwin/reviewed/patches.json")
MAX_PATCH_REVIEW_BYTES = 1024 * 1024
PATCH_REVIEW_RECORD_COUNT = 11
```

Implement `load_patch_review(repository_root, source_pack)` using the existing
`_read_and_hold_regular_file` and path-chain helpers. The order is:

1. validate the repository-relative parent chain without following links;
2. hold and bounded-read the single-link regular leaf once;
3. strict-parse and require canonical bytes;
4. validate exact field types before regex, sorting, set, or equality work;
5. build immutable models;
6. cross-bind exact source fields to the source-pack patch slice;
7. verify the held leaf and parent identity again;
8. close the descriptor in `finally` on every `BaseException` path.

Normalize all owned failures to `ConversionError("patch review evidence is invalid")`.
Do not reflect JSON values, paths, exceptions, or OS diagnostics.

**Step 5: Require the review in the pure conversion API**

Change the signatures deliberately rather than loading ambient global state:

```python
def classify_source_pack(
    source_pack: SourcePack,
    patch_review: PatchReviewLedger,
) -> ConversionResult:
    ...

def build_conversion(repository_root: Path) -> ConversionResult:
    source_pack = load_source_pack(repository_root)
    patch_review = load_patch_review(repository_root, source_pack)
    return classify_source_pack(source_pack, patch_review)
```

Update existing synthetic tests to obtain the real review and pass it explicitly,
or to construct a closed synthetic review when they deliberately replace patch
records. Do not add an optional fallback that silently treats patches as
unreviewed.

**Step 6: Run focused GREEN and mutation gates**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MacWinConversionModelTests `
  tests.test_macwin_asset_migration.MacWinSourcePackTests
```

Then temporarily mutate one path-chain check and one canonical-byte comparison;
confirm the corresponding regression turns RED, restore, and rerun GREEN.

**Step 7: Commit**

```powershell
git add tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py
git commit -s -m "feat: authenticate Mac-Win patch reviews"
```

### Task 3: Derive Patch Classification Fail Closed

**Files:**

- Modify: `tools/convert_macwin_assets.py:340-390,866-887,2510-2600,2699-2790`
- Modify: `tests/test_macwin_asset_migration.py` in `MacWinPatchProvenanceTests`

**Step 1: Write classification-priority RED tests**

Add one table-driven test that starts from a single real patch review record and
changes only the evidence needed to expose each subsequent rule:

```python
cases = (
    ("unresolved-license", "missing-license"),
    ("reviewed-license-partial-base", "unverified-base"),
    ("reviewed-license-matched-base-conflict", "conflict"),
    ("reviewed-license-upstreamed", "upstreamed-or-obsolete"),
)
```

Add explicit tests that:

- project-license SPDX never clears missing patch license;
- a hand-written `retained` disposition cannot override derived quarantine;
- `retained` requires complete `matched` preimages, closed dependencies,
  `local-only`, and a registered focused probe ID;
- an unknown or duplicate probe ID fails before any document is rendered;
- all real 11 patches become `quarantined/missing-license`;
- full real counts are exactly `2 converted / 4 deferred / 84 quarantined`.

Use a test-only registered pure probe with a positive control and a mutant so
the retained branch is reachable without retaining a real patch.

**Step 2: Run and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_patch_classification_priority `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_real_patch_status_counts
```

Expected: old `_classify_asset` returns `deferred` for every patch.

**Step 3: Implement one classification function**

Add fixed release conditions and a pure function:

```python
PATCH_RELEASE_CONDITIONS = {
    "missing-license": "Record patch-specific license evidence and repeat review.",
    "unverified-base": "Bind every patch preimage to one exact upstream commit.",
    "conflict": "Resolve patch conflicts and close every dependency.",
    "upstreamed-or-obsolete": "Confirm removal or replacement in the reviewed source set.",
}

def _classify_patch_review(review: PatchReviewRecord) -> tuple[str, str, str]:
    if review.patch_license_status != "reviewed":
        reason = "missing-license"
    elif not review.preimages or any(item.result != "matched" for item in review.preimages):
        reason = "unverified-base"
    elif review.upstream_status in {"conflicting", "unresolved"} or (
        review.external_dependencies or review.development_dependencies
    ):
        reason = "conflict"
    elif review.upstream_status in {"upstreamed", "superseded"}:
        reason = "upstreamed-or-obsolete"
    else:
        return "deferred", "retain-patch", ""
    return "quarantined", "quarantine", reason
```

The production version must also validate patch SPDX/evidence, local-only
status, probe registry membership, and exact manual-disposition consistency
before returning retained. Keep the decision pure and deterministic.

Pass the exact review record into `_classify_asset`. For quarantined patches set:

```python
ConversionRecord(
    output_kind="patch-mapping",
    status="quarantined",
    action="quarantine",
    target_issue="MW-ASSET-002",
    reason=reason,
    evidence_locators=derived_sorted_evidence,
    release_condition=PATCH_RELEASE_CONDITIONS[reason],
)
```

Bottle records remain unchanged and deferred.

**Step 4: Validate results independently from construction**

In `_validate_conversion_result`, rebuild every patch decision from
`result.patch_review`; require exact equality with the 11 source records and
require the real status counts. A forged `ConversionRecord` must fail even when
its fields are otherwise schema-valid.

Extend `QUARANTINE_REASONS` and `schemas/quarantine.schema.json` with only the
new fixed reasons actually emitted: `unverified-base`, `conflict`, and
`upstreamed-or-obsolete`.

**Step 5: Run GREEN and retained-branch mutation proof**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MacWinConversionModelTests
```

Temporarily remove the probe-registry check and confirm the unregistered-probe
test turns RED. Restore and rerun GREEN.

**Step 6: Commit**

```powershell
git add schemas/quarantine.schema.json tools/convert_macwin_assets.py `
  tests/test_macwin_asset_migration.py
git commit -s -m "feat: classify reviewed Mac-Win patches"
```

### Task 4: Render the Enriched Mapping and Re-Seal the Five-File Graph

**Files:**

- Modify: `schemas/migration-record.schema.json`
- Modify: `tools/convert_macwin_assets.py:887-1035,1098-1245,1377-1468,1576-1600,2974-3035`
- Modify: `migration/macwin/generated/mappings/patches.json`
- Modify: `migration/macwin/generated/quarantine.json`
- Modify: `migration/macwin/generated/index.json`
- Modify: `tests/test_macwin_asset_migration.py` in patch, graph, and schema test classes

**Step 1: Write generated-document RED tests**

Add assertions that:

- patch mapping has exactly 11 records in source-path order;
- every patch mapping retains exact source identity and adds exact upstream,
  preimage-summary, application, disposition, reason, and probe fields;
- all 11 mapping statuses are `quarantined` and target `MW-ASSET-002`;
- quarantine has exactly 84 records, including each patch exactly once;
- root status counts are `2/4/84`;
- every patch root record points to `quarantine.json`;
- generated paths remain exactly the existing five leaves;
- mapping records contain no command, apply, executable, argv, environment, or
  checkout fields.

**Step 2: Run and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_generated_patch_review_documents `
  tests.test_macwin_asset_migration.MacWinGeneratedGraphTests
```

Expected: renderer rejects quarantined patches in `_deferred_document`, and old
goldens still report `2/15/73`.

**Step 3: Close the mapping schema**

Refactor `migration-record.schema.json` into a common source identity plus two
closed record branches:

- Bottle branch: unchanged `deferred`, target `MW-ASSET-003`;
- Patch branch: category `patches`, status `deferred|quarantined`, target
  `MW-ASSET-002`, and the exact review fields.

Do not loosen `additionalProperties`, path patterns, OID formats, or review
status types. Add stdlib-oracle mutants for valid-but-wrong status, upstream
commit, disposition, reason, and application ordering.

**Step 4: Add a dedicated patch mapping serializer**

Keep `_deferred_document` for Bottle records. Add:

```python
def _reviewed_patch_document(
    record: ConversionRecord,
    asset: SourceAsset,
    review: PatchReviewRecord,
) -> dict[str, object]:
    ...
```

The function must require exact cross-identity and derived-decision equality,
then return only the approved closed fields. Render patch records through it
regardless of `deferred` or `quarantined` result.

Append patch quarantine entries through `_quarantine_document`. Sort the merged
84-record quarantine by source path. Update `_record_output_path` so quarantined
patches map to quarantine while their review evidence remains sealed in the
patch mapping document.

**Step 5: Validate application contracts before serialization**

Extend `_validate_task6_documents` or introduce
`_validate_patch_review_documents` so it independently rebuilds all 11 mapping
records and the patch quarantine subset from `ConversionResult.patch_review`.
It must reject:

- a missing or extra patch record;
- a schema-valid but wrong upstream tuple;
- wrong base counts;
- wrong manual or derived disposition;
- a patch omitted from quarantine;
- a retained patch present in quarantine;
- a mapping/quarantine self-consistent forge.

**Step 6: Generate once and inspect the exact diff**

Run:

```powershell
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --check
git diff -- migration/macwin/generated
```

Expected: exactly three generated files change: patch mapping, quarantine, and
root index. Catalog and Bottle mapping bytes remain unchanged. No Recipe, probe,
fixture, or sixth generated leaf appears.

**Step 7: Run GREEN, then repeat write**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MigrationSchemaTests `
  tests.test_macwin_asset_migration.MacWinGeneratedGraphTests
python -B tools/convert_macwin_assets.py --write
git diff --exit-code -- migration/macwin/generated
```

Expected: focused tests pass; the second write is a byte-for-byte no-op relative
to the first generated result. The final `git diff --exit-code` is run only
after staging the intended first-write golden changes or against a saved digest
snapshot; do not discard intended changes.

**Step 8: Commit atomically**

The code, schemas, tests, and all three golden changes must be one commit so no
intermediate commit violates repository validation:

```powershell
git add schemas/migration-record.schema.json schemas/quarantine.schema.json `
  tools/convert_macwin_assets.py tests/test_macwin_asset_migration.py `
  migration/macwin/generated/mappings/patches.json `
  migration/macwin/generated/quarantine.json migration/macwin/generated/index.json
git commit -s -m "feat: publish Mac-Win patch review results"
```

### Task 5: Add an Independent Repository Oracle

**Files:**

- Modify: `scripts/validate_repository.py:60-110,480-620,960-1190`
- Modify: `tests/test_macwin_asset_migration.py` in patch and layout test classes

**Step 1: Write repository-oracle RED attacks**

In isolated repository fixtures, prove the current validator incorrectly accepts
or cannot authenticate the new review boundary. Cover:

- missing review ledger;
- extra file or directory under `migration/macwin/reviewed`;
- review root/leaf symlink, reparse point, hardlink, non-regular leaf;
- ledger mutation after first read and same-size/restored-mtime mutation;
- converter plus ledger plus all five goldens self-consistently forged;
- a correct source identity with a schema-valid but wrong upstream commit;
- mapping/quarantine/index all resealed around a false `deferred` patch;
- replacement between ordinary developer-path scan and successful return.

Every failure must be fixed, bounded, and non-reflective.

**Step 2: Run one self-forge and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests.test_repository_oracle_rejects_self_consistent_patch_review_forge
```

Expected: failure showing the old repository oracle still derives patch status
without independent review evidence.

**Step 3: Bind the exact reviewed tree**

Add fixed path and digest constants after the approved golden is generated:

```python
PATCH_REVIEW_PATH = "migration/macwin/reviewed/patches.json"
PATCH_REVIEW_DOCUMENT_SHA256 = "<reviewed canonical digest>"
PATCH_REVIEW_TREE = {"patches.json": "regular"}
```

Authenticate the reviewed directory as exactly one directory and one regular,
single-link bounded leaf. Use existing held directory/file primitives and
stable directory identities; do not use `Path.resolve`, `exists`, `rglob`, or a
path-based open after validation. Revalidate directory children and leaf raw
bytes before success.

**Step 4: Rebuild policy independently**

Implement `_independent_patch_review_oracle(source_binding, review_raw,
documents)` without calling converter policy helpers. It must:

1. strict-parse and require canonical ledger bytes;
2. require the fixed ledger SHA-256 and source identity;
3. cross-bind exact 11 source records;
4. enforce field types, ordering, bounds, allowed upstream tuples, and license
   priority;
5. independently derive 11 `missing-license` patch outcomes;
6. rebuild the expected patch mapping and patch quarantine records;
7. require total counts `2/4/84` and exact generated document SHA-256 values.

Update `_independent_task6_oracle` so the Bottle and probe/fixture semantics stay
unchanged while the patch sub-oracle delegates to the new exact evidence. Update
`_independent_task7_oracle` to derive patch records as quarantined and to require
the new status counts and dependent-document digests.

**Step 5: Revalidate after developer-path scanning**

Ensure the reviewed tree binding and all five generated leaves are checked both
after scanning and immediately before successful return. A safe extra file is
not accepted merely because it lacks a developer path.

**Step 6: Run focused GREEN and mutation gates**

Run serially:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MigrationLayoutTests
python -B scripts/validate_repository.py
```

Temporarily replace the fixed review digest with a digest computed from the
untrusted fixture and confirm the self-forge regression turns RED. Restore the
fixed digest and rerun GREEN.

**Step 7: Commit**

```powershell
git add scripts/validate_repository.py tests/test_macwin_asset_migration.py
git commit -s -m "fix: independently verify Mac-Win patch evidence"
```

### Task 6: Document the Evidence Result and Explanation Contract

**Files:**

- Create: `docs/migration/macwin-patch-provenance.md`
- Modify: `docs/migration/macwin-portable-assets.md`
- Modify: `README.md`
- Modify: `docs/testing.md`
- Modify: `.gitattributes`
- Modify: `tests/test_macwin_asset_migration.py` in documentation and side-effect classes

**Step 1: Write documentation RED tests**

Require exact prose/data bindings, not isolated number mentions:

- source pack digest paired with its path;
- review ledger path paired with size and digest;
- all five generated paths paired with size and digest;
- exact `11 patches -> 0 retained / 11 quarantined` statement;
- exact global `2/4/84` statement;
- JASP/Wine tag and commit identities;
- explicit distinction between project license and patch license;
- explicit statement that no patch was applied or executed;
- links to `MW-ASSET-002`, README, and testing entry points;
- no remaining contradictory `2/15/73` current-state claim.

**Step 2: Run and observe RED**

Run:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinMigrationDocumentationTests
```

Expected: failures for the missing provenance document and stale status/digest
facts.

**Step 3: Write the evidence document**

Document:

- all exact frozen and upstream identities;
- the per-patch purpose/base-result/license/disposition table;
- the reason-priority policy;
- exact review and generated file sizes/digests from committed bytes;
- the full verification commands;
- release condition for any future retained patch;
- open ownership of `MW-ASSET-003` and `MW-ARCH-001`.

Update existing migration docs to describe the new current state. Add README and
testing links. Add explicit LF rules for the new reviewed evidence and migration
document.

**Step 4: Prove explanation and side-effect behavior**

Add tests that all 11 source paths passed to `--explain` return stable,
canonical, bounded JSON with `action=quarantine`, `reason=missing-license`, and
no patch content reflection. Extend the existing isolated-process side-effect
suite to snapshot `migration/macwin/reviewed` and to run default, `--check`, all
11 explanations, validator, and two writes.

Controlled mutants must show the guards catch:

- DNS/network access to official evidence URLs;
- a Git/subprocess upstream lookup;
- reading an evidence locator with `open`, `Path`, or `os` APIs;
- patch import/execution/application attempts;
- environment/home expansion;
- Bottle or external writes.

**Step 5: Run focused GREEN**

Run serially:

```powershell
python -S -B -m unittest `
  tests.test_macwin_asset_migration.MacWinPatchProvenanceTests `
  tests.test_macwin_asset_migration.MacWinMigrationDocumentationTests `
  tests.test_macwin_asset_migration.MacWinMigrationSideEffectTests
python -B tools/convert_macwin_assets.py --check
python -B scripts/validate_repository.py
git diff --check
```

Expected: all pass, no cache/temp/transaction residue, and documentation facts
match exact committed bytes.

**Step 6: Commit**

```powershell
git add .gitattributes README.md docs/testing.md `
  docs/migration/macwin-portable-assets.md `
  docs/migration/macwin-patch-provenance.md `
  tests/test_macwin_asset_migration.py
git commit -s -m "docs: publish Mac-Win patch review evidence"
```

### Task 7: Fresh Full Verification and Review

**Files:**

- Verify only; modify files only to fix a reproduced failure through a new RED
  test and an isolated DCO commit.

**Step 1: Run the complete Python migration suite**

Run with no concurrent repository validator:

```powershell
python -S -B -m unittest tests.test_macwin_asset_migration
```

Expected: all tests pass; record the exact test/skip count and elapsed time.

**Step 2: Verify deterministic generation and repository contracts**

Capture the review and five generated file digests, then run serially:

```powershell
python -B tools/convert_macwin_assets.py
python -B tools/convert_macwin_assets.py --check
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --write
python -B scripts/validate_repository.py
```

Expected:

- all exit zero;
- both writes are exact no-ops;
- the review ledger, source pack, Git metadata, Bottle fixtures, external
  sentinel, and generated digests are unchanged by read-only modes;
- generated output remains exactly five files;
- no patch is executed or applied.

**Step 3: Run the Rust gates serially**

```powershell
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

Expected: every command exits zero with no warnings promoted by Clippy.

**Step 4: Audit repository state**

```powershell
git diff --check origin/main...HEAD
git diff --cached --check
git status --short --branch
git log --format='%H%n%B' origin/main..HEAD
```

Also verify:

- every new commit has `Signed-off-by`;
- no `__pycache__`, `.pyc`, `.compatforge-transaction`, `.macwin-*`, or owned
  temporary directory remains;
- new JSON/docs are LF-only;
- no source object, Recipe, probe, fixture, Bottle, Rust runtime, or CI workflow
  changed outside approved scope.

**Step 5: Perform spec and adversarial quality review**

Use @superpowers:requesting-code-review only if an explicitly authorized
reviewer is available. Otherwise perform two separate read-only review passes:

1. specification pass against the approved design and every plan acceptance;
2. quality pass with schema-valid forges, link/race/TOCTOU, bounded allocation,
   non-reflective diagnostics, cross-platform paths, and side-effect mutants.

Any finding gets a real RED regression, the smallest GREEN fix, a fresh full
matrix, and an isolated DCO commit before re-review. Do not advance while either
review has a Critical, Important, or Minor finding.

### Task 8: Integration Handoff and MW-ASSET-002 Evidence

**Files:**

- No new repository file is required unless review identifies a missing fact.

**Step 1: Prepare the exact completion packet**

Record:

- branch HEAD and commit list;
- source/review/generated sizes and SHA-256 values;
- exact per-category and status counts;
- exact upstream identities;
- full Python and Rust verification results;
- explicit `0 retained / 11 quarantined / 0 applied` outcome;
- spec and quality review results.

**Step 2: Stop for integration authorization**

Use @superpowers:finishing-a-development-branch to present push/PR/merge options.
Do not push, open, or merge a PR until the user authorizes that external state
change.

**Step 3: After an authorized merge, update the issue**

Post one evidence comment to Mac-Win `MW-ASSET-002` with the merged commit, PR,
digests, counts, verification links, and the statement that no patch was
applied. Close the issue only when its defined acceptance criterion is evidence
review rather than integration. Leave `MW-ASSET-003` and `MW-ARCH-001` open.
