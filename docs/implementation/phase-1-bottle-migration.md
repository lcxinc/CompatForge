# Phase 1 Bottle migration evidence

This document records the bounded, offline Bottle migration slice delivered in
Phase 1. It is an implementation contract, not a promise that arbitrary
legacy applications will run on every host.

## Scope and non-goals

`compatforge-bottle` reads a user-selected Mac-Win Bottle, snapshots regular
files into a content-addressed store, derives a closed migration plan, and
publishes an immutable version pinned to one exact Runtime Pack. The source is
read-only: snapshotting does not write, rename, unlink, chmod, execute, load a
binary, access the network, or inspect the neighbouring `Mac-Win` checkout.

Source is read-only.

The slice does not import commercial Wine binaries, discover host defaults,
apply recipes, launch applications, or claim compatibility. Recipes remain
absent from the migration plan. Provider-specific execution, signatures and
artifact distribution are separate work.

## Public contract

The CLI accepts only these five bounded forms:

```text
compatforge-cli bottle snapshot <store-root> <legacy-bottle-root>
compatforge-cli bottle plan <store-root> <snapshot-digest> <runtime-store-root> <runtime-map.json>
compatforge-cli bottle import <store-root> <snapshot-digest> <runtime-store-root> <runtime-map.json>
compatforge-cli bottle verify <store-root> <bottle-id>
compatforge-cli bottle rollback <store-root> <bottle-id>
```

Success is one canonical JSON receipt on stdout. Failure is a closed
`{"code","message"}` diagnostic on stderr, exit status 1, and empty stdout.
Unknown or incomplete commands print help without touching a path.

## Runtime binding and parity

The public fixtures use Runtime Pack `fixture-runtime` at digest
`sha256:b7e18e933c0a51f6f1ec387862793e5d22cc2edb7e23c114449ea98357d717af`.
The independent Python oracle recomputes the legacy projection, environment
precedence, snapshot preimage, migration plan digest, and launch plan. It does
not call Rust to construct an expected value. The validator authenticates four
Draft 2020-12 schemas and the exact fixture/golden bytes.

| fixture | entries | file bytes | snapshot digest | migration plan digest |
| --- | ---: | ---: | --- | --- |
| win32 | 4 | 558 | `sha256:7a2661322918a821a597d0ccfd1736e8c9f490d6bf41e4f1778c74a121e37523` | `sha256:0fd681397b014e699a5e1251ee0045e4d1a95408b6cec97791bb2f70805d12da` |
| win64 | 4 | 1152 | `sha256:672021ed04ed3e53eff0df940e214bb580bb1690506440867666cd8370288c35` | `sha256:ee984e0e15ba9707b8ff9c6a8ac745c6ecc60149d687ffdda5336cf797388dba` |

The six golden files are sealed to these bytes:

```text
win32-launch-plan.json       sha256:041c16b7aa1040395e685db817c2360b57208d8c5d502bec843ee7944845335d
win32-legacy-planning.json   sha256:4db891c9b1524fc7cab947e7cb331d42a9a4067e2b53c849e8c8ef600b4fefe7
win32-migration-plan.json    sha256:1a7c47bb3491431c9750288e67d85acf8a3d92e854b9afe8646d8a81e044d321
win64-launch-plan.json       sha256:e9477955494b6469397a5b1651355b5fd876d7b0814f720243aeee55307373ec
win64-legacy-planning.json   sha256:664ed33a9a5743a5d9367c9ac628309fb958e95764630d50c197b126c86bd8b2
win64-migration-plan.json    sha256:4be176308c112323f01fe6b21e440d06b2ae828c4d8c2cefb93cc053402a57b4
```

## Store, verification and rollback

Snapshot objects are SHA-256 addressed and deduplicated. Import stages the
complete version graph, verifies every object and prefix entry, then atomically
publishes the active reference. Repeating the same import is a no-op. Active
verification rehashes the ref, version manifest, migration plan, prefix,
snapshot and Runtime Pack. Rollback verifies the historical target first,
stages a durable ref, revalidates the current state immediately before the
replace, and retains history until the new ref is read back. History is capped
at 32 entries; corrupt or duplicate/current history fails closed.

## Evidence commands

Run the repository oracle and migration converter serially:

```text
python -S -B -m unittest tests.test_bottle_migration_contracts
python -S -B scripts/validate_repository.py
python -S -B tools/convert_macwin_assets.py --check
```

The three-platform CI matrix runs the Rust Bottle tests and the same public
fixture sequence. macOS keeps the strict `UnsupportedPlatform` snapshot
boundary; Linux and Windows execute snapshot, plan, import, verify and
rollback against the text-only fixtures.
