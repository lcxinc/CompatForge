# Mac-Win patch provenance review

This document is the committed evidence result for `MW-ASSET-002`. It is linked
from the repository [README](../../README.md) and the [testing entry point](../testing.md).
It records an offline review result; it does not make a runtime or
application-compatibility claim. No patch was applied or executed.

## Frozen evidence identities

The review is bound to repository `a1112/Mac-Win`, source tag
`mw-migration-baseline-db12d5e`, annotated tag object
`9f10d003382ce7ffbb269376c03477e17516302f`, source commit
`db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527`, and inventory commit
`97f8423094d25325d8f864eb6f49a9e8628dbb93`.

The upstream comparison is frozen to these exact identities:

- JASP tag `v0.97.1` resolves to commit `28be3fee5c7ce2119f1945acd0254eb4fb8cb6e2`.
- Wine annotated tag `wine-11.11` has tag object `b08651f36865a3e1d9300d792df322d2ee8a807e`
  and resolves to commit `f6c044e1890e84a4aa5e77e76ba7276a615630e1`.

All sizes and SHA-256 values below are computed from the committed bytes.

| Evidence path | Bytes | SHA-256 |
| --- | ---: | --- |
| `migration/macwin/source/index.json` | 101,199 | `1fc8b071a9c52c5f29d130e47e3bd1cb165effa860eaa45336c82ee07cafe3a3` |
| `migration/macwin/reviewed/patches.json` | 35,368 | `38c54730634616bdc0b6a82aa5a5b57bb1c0d6da17d429897cd8da2414bc7783` |

The source index authenticates the frozen source pack. The review ledger is a
separate closed, canonical evidence file cross-bound to the exact 11 patch
source identities; it neither replaces source objects nor grants permission to
use their patch contents.

## Reviewed patch result

The exact result is: 11 patches -> 0 retained / 11 quarantined. Each patch has
an unresolved patch license and therefore stops at the first policy rule,
`missing-license`, even where its upstream base is completely matched.

Project license context is not patch-specific license evidence. JASP's
AGPL-3.0-or-later and Wine's LGPL-2.1-or-later project notices are recorded only
as context; neither establishes a redistribution license for a Mac-Win-local
patch, its author contribution, or its added hunks.

| Source path | Purpose | Base result | Patch license | Disposition |
| --- | --- | --- | --- | --- |
| `patches/jasp-0.97.1-avoid-nested-workspace-reset.patch` | Avoid nested workspace resets while creating a JASP dataset. | matched=0, mismatched=0, added=0, unproven=2 | `unresolved` | `quarantined / missing-license` |
| `patches/jasp-0.97.1-fix-proxy-model-reset.patch` | Avoid nested model resets in JASP dataset proxy models. | matched=0, mismatched=0, added=0, unproven=2 | `unresolved` | `quarantined / missing-license` |
| `patches/jasp-0.97.1-initialize-enginesync-before-reset.patch` | Initialize JASP EngineSync IPC state before resetting a dataset. | matched=0, mismatched=0, added=0, unproven=1 | `unresolved` | `quarantined / missing-license` |
| `patches/jasp-0.97.1-local-macos-build-configure.patch` | Configure local macOS dependencies for the JASP build. | matched=3, mismatched=0, added=0, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-dcomp-winui-host-composition.patch` | Add Wine host-composition behavior needed by DirectComposition and WinUI. | matched=14, mismatched=11, added=0, unproven=9 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-macos-native-ui-integration.patch` | Integrate selected Wine dialogs with native macOS UI behavior. | matched=8, mismatched=2, added=1, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-shell32-virtual-desktop-manager.patch` | Add a Wine shell32 virtual desktop manager implementation. | matched=4, mismatched=0, added=1, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-windows-data-json-modern-apps.patch` | Expand Wine Windows.Data.Json behavior for modern applications. | matched=5, mismatched=0, added=0, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-windows-graphics-imaging.patch` | Add Wine Windows.Graphics.Imaging API behavior. | matched=5, mismatched=0, added=1, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-windowscodecs-bilinear-scaler.patch` | Add bilinear scaling behavior to Wine WindowsCodecs. | matched=2, mismatched=0, added=0, unproven=0 | `unresolved` | `quarantined / missing-license` |
| `patches/wine-winui-pointer-input.patch` | Expand Wine pointer-input behavior needed by WinUI applications. | matched=9, mismatched=8, added=0, unproven=0 | `unresolved` | `quarantined / missing-license` |

The stable decision priority is: missing-license -> unverified-base -> conflict -> upstreamed-or-obsolete -> retained. Evaluation stops at the first unmet
condition. The release condition for every current patch is: Record patch-specific license evidence and repeat review.

A future retained patch must additionally bind an SPDX expression and official
patch-license evidence, match every preimage against the exact upstream commit,
close external and development dependencies, remain local-only and needed, and
name at least one registered focused regression probe. Retained still means
`deferred`; it never authorizes automatic application or execution.

## Generated result

The complete 90-record graph now reports 2 converted + 4 deferred + 84 quarantined.
The four deferred records are Bottle schema mappings owned by
`MW-ASSET-003`. The five-file graph remains exact; no Recipe, patch payload,
probe, fixture, or sixth generated leaf is emitted.

| Path | Bytes | SHA-256 |
| --- | ---: | --- |
| `migration/macwin/generated/catalog.json` | 7,603 | `c0c5b93b97b3f3c6e9197d2e00645dc28b1163b3130fe3e73ec7d1fde9e8fa4a` |
| `migration/macwin/generated/index.json` | 34,845 | `2c6a0447b4a27c8c0baf0da9dd45cad355db75a6a880e9b90434bc7b93cdf080` |
| `migration/macwin/generated/mappings/bottle-schemas.json` | 2,637 | `f99698eaf5e341a58c7f7b91299701481c38df8a31203064aab38822622041cb` |
| `migration/macwin/generated/mappings/patches.json` | 21,032 | `202c56f99c7f332a7b5c6b93b87baef66d1445ae3981954c23f2b6c7ea64edd1` |
| `migration/macwin/generated/quarantine.json` | 89,656 | `ca0132b78ac4bae8ed00446194cd7e9712b37ebc2aea4087ebad695248e2b2e9` |

## Verification and side-effect boundary

Run these commands serially from the repository root:

```text
python -S -B -m unittest tests.test_macwin_asset_migration.MacWinPatchProvenanceTests tests.test_macwin_asset_migration.MacWinMigrationDocumentationTests tests.test_macwin_asset_migration.MacWinMigrationSideEffectTests
python -B tools/convert_macwin_assets.py
python -B tools/convert_macwin_assets.py --check
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --write
python -B tools/convert_macwin_assets.py --explain patches/jasp-0.97.1-avoid-nested-workspace-reset.patch
python -B scripts/validate_repository.py
git diff --check
python -S -B -m unittest tests.test_macwin_asset_migration
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

Default, `--check`, every `--explain`, and repository validation are offline
and read-only. The two writes may replace only the authenticated five generated
leaves and the second is a byte-for-byte no-op. These modes do not resolve
evidence URLs, invoke Git to inspect upstream state, open evidence locators,
read ambient environment or home paths, access a Bottle, or import, compile,
apply, execute, or reflect patch contents.

`MW-ASSET-002` owns this evidence result. `MW-ASSET-003` remains open for Bottle
schema work, and `MW-ARCH-001` remains open for repository archival. Neither is
closed or advanced by this review.
