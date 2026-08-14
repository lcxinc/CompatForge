# Mac-Win portable asset migration boundary

This document records the reviewed, offline result of `MW-ASSET-001`. It is an
audit and generation boundary, not a compatibility certification. The stable
issue owner is the migration domain: owner: `compatforge/migration`.

## Frozen source boundary

- repository: `a1112/Mac-Win`
- source tag: `mw-migration-baseline-db12d5e`
- source tag object: `9f10d003382ce7ffbb269376c03477e17516302f`
- source commit: `db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527`
- inventory commit: `97f8423094d25325d8f864eb6f49a9e8628dbb93`
- governed inventory: 90 = 19 catalog + 11 patches + 26 probes + 30 fixtures + 4 bottle-schema

The committed source pack at `migration/macwin/source` contains the exact 90
reviewed objects plus its content-addressed index. Normal conversion reads only
that pack. It does not consult a neighboring Mac-Win checkout, mutable branch,
release, URL, developer-machine path, process environment, or current working
directory. The importer is a review-only utility and is not part of normal
generation, repository validation, or CI.

The 11 patch identities also have a closed reviewed evidence ledger at
`migration/macwin/reviewed/patches.json`. Its exact upstream comparison,
license boundary, and disposition are documented in the [Mac-Win patch
provenance review](macwin-patch-provenance.md).

The source index and each generated JSON document are bounded to 1 MiB before
parsing or comparison. Source objects have separate per-object and aggregate
bounds recorded by the source-pack contract. Inputs are strict UTF-8 where JSON
is expected; paths, duplicate keys, depth, regular-file identity, byte size,
and SHA-256 are validated before conversion.

## Reviewed result

The sealed root graph reports 2 converted + 4 deferred + 84 quarantined across
all 90 identities.

| Category | Inputs | Reviewed result |
| --- | ---: | --- |
| Catalog | 19 | The catalog index and signature boundary are the two converted records; all 17 Recipe candidates are quarantined. |
| Patches | 11 | All 11 are quarantined as `missing-license` under `MW-ASSET-002`; 0 are retained. No patch is applied or executed. |
| Probes | 26 | All 26 are quarantined; no source asset is executed or emitted as portable content. |
| Fixtures | 30 | All 30 are quarantined; no source asset is imported, compiled, or executed. |
| Bottle schema | 4 | Four deferred mappings target `MW-ASSET-003`. No Bottle is opened or written. |

Emitted portable application assets: 0 Recipes, 0 portable probes, and 0 portable fixtures.
Missing or unresolved license/provenance evidence is never replaced
with a guessed value. Quarantine preserves reviewed evidence locators as inert
data; it does not expand them, test their existence, or read their targets.

The current status does not claim application compatibility, does not claim patch readiness, and does not migrate or mutate Bottles.
The source pack and generated migration graph are not Runtime Pack components and the graph is not consumed by the CompatForge runtime, C ABI, providers, or desktop application.

## Sealed output graph

The root index authenticates four dependent JSON documents. The five committed
files and their reviewed SHA-256 values are:

| Path | Bytes | SHA-256 |
| --- | ---: | --- |
| `migration/macwin/generated/catalog.json` | 7,603 | `c0c5b93b97b3f3c6e9197d2e00645dc28b1163b3130fe3e73ec7d1fde9e8fa4a` |
| `migration/macwin/generated/index.json` | 34,845 | `2c6a0447b4a27c8c0baf0da9dd45cad355db75a6a880e9b90434bc7b93cdf080` |
| `migration/macwin/generated/mappings/bottle-schemas.json` | 2,637 | `f99698eaf5e341a58c7f7b91299701481c38df8a31203064aab38822622041cb` |
| `migration/macwin/generated/mappings/patches.json` | 21,032 | `202c56f99c7f332a7b5c6b93b87baef66d1445ae3981954c23f2b6c7ea64edd1` |
| `migration/macwin/generated/quarantine.json` | 89,656 | `ca0132b78ac4bae8ed00446194cd7e9712b37ebc2aea4087ebad695248e2b2e9` |

`index.json` is the root seal and therefore does not list itself as a dependent
document. It records four dependent documents, 90 records, the exact category
counts, source identity, byte sizes, SHA-256 values, and deterministic ordering.
The validator also reconstructs semantic identity coverage, so merely
recomputing a digest cannot authorize a forged graph.

## Commands and mode boundaries

Run commands from the CompatForge repository root with Python bytecode disabled.

```text
python -B tools/convert_macwin_assets.py
python -B tools/convert_macwin_assets.py --check
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --explain 7zip
python -B scripts/validate_repository.py
```

- Default mode validates the source pack and complete generated graph, compares
  exact committed bytes, and prints a one-line count summary. It is read-only.
- `--check` performs the same validation and exact comparison without a success
  payload. It is the normal CI and repository-validation mode.
- `--explain ID` returns one bounded, deterministic reviewed decision. Evidence
  locators are returned as inert strings and are not probed.
- `--write` is the only approved write mode. It transactionally replaces the
  exact generated output set beneath `migration/macwin/generated`, verifies
  staged bytes and identities, and restores the complete prior set on failure.
  Repeating it with unchanged inputs is byte-for-byte a no-op.
- Repository validation invokes the fixed converter `--check` boundary with
  bytecode disabled. None of these modes downloads dependencies, resolves DNS,
  opens sockets, launches subprocesses from migrated data, executes assets,
  imports assets, accesses a Bottle, or writes a Runtime Pack store.

## Review and release workflow

Changes begin with a reviewed update to the frozen source/policy evidence, then
regenerate the complete graph, inspect every changed status/reason, run focused
migration tests, repository validation, converter `--check`, and the full Rust
and Python gates. Reviewers compare source commit and SHA-256 provenance, exact
identity coverage, quarantine reasons, deferred targets, document digests, and
side-effect snapshots before accepting new bytes.

Quarantine release requires the release condition in the record to be met by a
reviewed source or policy update; rerunning the converter alone cannot release
it. The patch evidence result under `MW-ASSET-002` is 0 retained and 11
quarantined; a future retained review must prove a patch-specific license,
complete upstream base, closed dependencies, local-only need, and a registered
focused regression probe. Bottle schema mappings remain deferred until the
snapshot, conversion, rollback, and source-preservation work in `MW-ASSET-003`
is completed. Any future portable asset or Recipe must carry complete license,
provenance, safe references, and its required test evidence before regeneration
can change its status.

Offline generation proves deterministic representation and audit coverage. It
does not execute installers, Wine, registry inputs, shell scripts, source code,
or Windows binaries, and it cannot establish real-device behavior or a new
compatibility rating.
