# macOS Headless Real PE Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** On Apple Silicon, register a developer-supplied local x86_64 Wine as an unsigned preview Runtime Pack and launch one real x86_64 Windows Console PE through the existing PreparedLaunch and ProcessSupervisor trust chain.

**Architecture:** Add a local-only Python registration tool that emits a preview Runtime bundle and existing `macos-provider.schema.json` configuration from explicit Wine paths. Add additive `prepared-launch` CLI commands that reuse `PreparedLaunch::prepare/authorize` and the existing event loop. Keep every cross-repository contract stable: no schema changes, no C ABI changes, no ForgeOS/ForgeTools/Mac-Win edits, no Runtime download or distribution.

**Tech Stack:** Rust 1.85+ workspace crates, Python 3.11+ standard library, existing JSON/serde contracts, SHA-256, macOS ARM64, Rosetta, developer-supplied x86_64 Wine, Homebrew MinGW only for compiling the local Console PE probe.

---

## Mandatory scope and stop rules

Before implementing any task, read:

- `docs/plans/2026-08-15-macos-headless-preview-design.md`
- `docs/implementation/phase-1-macos-provider.md`
- `docs/implementation/phase-1-trusted-launch-preparation.md`
- `docs/decisions/0009-macos-provider-evidence.md`
- `docs/security.md`
- `docs/compliance.md`

Do not modify any file in ForgeOS, ForgeTools, or Mac-Win. Do not change files under `schemas/` or `crates/compatforge-ffi/include/`. Do not add a C ABI symbol, change ABI major 1, alter existing DTO semantics, download Wine, scan `PATH`, bundle D3DMetal, commit a Wine binary, or commit a generated `.exe`.

If any implementation step appears to require one of those changes, stop that task and open a separate design issue. Do not fold the change into this branch.

## Task 1: Prepare the Mac worktree and prove the baseline

**Files:**

- Read: `docs/plans/2026-08-15-macos-headless-preview-design.md`
- No source modifications

**Step 1: Fetch the approved branch on the Mac**

```bash
cd /path/to/CompatForge
git fetch origin --prune
git switch --track origin/agent/macos-headless-preview
```

If the branch already exists locally:

```bash
git switch agent/macos-headless-preview
git pull --ff-only
```

Expected: branch points at the two documentation commits and `git status --short` is empty.

**Step 2: Create an isolated implementation worktree if desired**

From a clean main checkout:

```bash
git worktree add ../compatforge-macos-headless-preview agent/macos-headless-preview
cd ../compatforge-macos-headless-preview
```

Never implement directly on `main`.

**Step 3: Check the host prerequisites**

```bash
uname -s
uname -m
sw_vers
xcode-select -p
rustc --version
cargo --version
python3 --version
```

Expected:

- `Darwin`
- `arm64`
- Xcode Command Line Tools present
- Rust satisfies workspace `rust-version`
- Python 3.11 or newer

Install only the test PE compiler if it is not present:

```bash
brew install mingw-w64
x86_64-w64-mingw32-gcc --version
```

Do not install or discover Wine as part of this task. Record the developer-owned absolute Wine root and relative `wine`/`wineserver` entrypoints separately.

**Step 4: Run the clean baseline**

```bash
python3 -S -B scripts/validate_repository.py
cargo fmt --all -- --check
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

Expected: all commands exit 0. If any baseline fails, stop and separate the baseline defect from this feature.

**Step 5: Confirm forbidden paths are unchanged**

```bash
git diff --exit-code origin/main -- schemas crates/compatforge-ffi/include
git status --short
```

Expected: no output.

## Task 2: Specify the local Wine registration tool with RED tests

**Files:**

- Create: `tests/test_macos_headless_preview.py`
- Test: `tests/test_macos_headless_preview.py`

**Step 1: Create a standard-library unittest harness**

Start the file with:

```python
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "tools" / "register_macos_local_wine.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class MacOsHeadlessPreviewRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="compatforge-macos-preview-")
        self.root = Path(self.temporary.name)
        self.materialized = self.root / "materialized"
        (self.materialized / "bin").mkdir(parents=True)
        self.wine = self.materialized / "bin" / "wine"
        self.wineserver = self.materialized / "bin" / "wineserver"
        self.wine.write_bytes(b"wine-entrypoint-fixture")
        self.wineserver.write_bytes(b"wineserver-entrypoint-fixture")
        for path in (self.wine, self.wineserver):
            path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_register(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-S",
                "-B",
                str(REGISTER),
                "--output-root",
                str(output),
                "--runtime-store-root",
                str(self.root / "runtime-store"),
                "--materialized-root",
                str(self.materialized),
                "--wine",
                "bin/wine",
                "--wineserver",
                "bin/wineserver",
                "--pack-id",
                "wine-macos-local-preview",
                "--version",
                "developer-local",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
```

**Step 2: Add the deterministic output test**

```python
    def test_registration_is_deterministic_and_source_read_only(self) -> None:
        before = {path: path.read_bytes() for path in (self.wine, self.wineserver)}
        first = self.run_register(self.root / "first")
        second = self.run_register(self.root / "second")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)

        for relative in (
            "bundle/manifest.json",
            "bundle/components/wine-entrypoint.bin",
            "bundle/components/wineserver-entrypoint.bin",
        ):
            self.assertEqual((self.root / "first" / relative).read_bytes(),
                             (self.root / "second" / relative).read_bytes())

        manifest = json.loads((self.root / "first/bundle/manifest.json").read_text())
        provider = json.loads((self.root / "first/provider.json").read_text())
        receipt = json.loads(first.stdout)
        self.assertEqual(manifest["channel"], "preview")
        self.assertEqual(provider["wineRuntime"]["packDigest"], manifest["digest"])
        self.assertEqual(receipt["packDigest"], manifest["digest"])
        self.assertNotIn("d3dmetal", provider["wineRuntime"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})
```

**Step 3: Add fail-closed path tests**

Cover, as separate subtests:

- relative output/runtime/materialized roots;
- absolute or `..` entrypoint;
- entrypoint outside the materialized root through a symlink;
- directory, device, missing or non-executable entrypoint;
- output overlapping materialized root or Runtime store;
- invalid pack ID or empty version;
- pre-existing output containing foreign bytes;
- output root equal to the repository root.

Each case must assert nonzero exit, empty stdout, unchanged sources and no published output except an owned temporary that is cleaned.

**Step 4: Add no-discovery/no-execution tests**

Run with a minimal environment and a `PATH` containing executable sentinels named `wine`, `wine64`, and `wineserver`. Assert sentinel logs remain absent. Also scan the tool source after it exists and reject imports/calls for `urllib`, `requests`, `socket`, `subprocess`, `os.system`, `shutil.which`, `Path.home`, and environment-based Wine lookup.

**Step 5: Run RED**

```bash
python3 -S -B -m unittest tests.test_macos_headless_preview -v
```

Expected: FAIL because `tools/register_macos_local_wine.py` does not exist.

**Step 6: Commit only the RED tests**

```bash
git add tests/test_macos_headless_preview.py
git commit -s -m "test: specify local macOS Wine registration"
```

## Task 3: Implement the bounded local Wine registration tool

**Files:**

- Create: `tools/register_macos_local_wine.py`
- Modify: `tests/test_macos_headless_preview.py`
- Test: `tests/test_macos_headless_preview.py`

**Step 1: Implement explicit argument parsing**

Use `argparse` with exactly these required flags:

```python
parser.add_argument("--output-root", type=Path, required=True)
parser.add_argument("--runtime-store-root", type=Path, required=True)
parser.add_argument("--materialized-root", type=Path, required=True)
parser.add_argument("--wine", required=True)
parser.add_argument("--wineserver", required=True)
parser.add_argument("--pack-id", required=True)
parser.add_argument("--version", required=True)
```

Do not add implicit defaults for Wine location, pack ID, version or store roots.

**Step 2: Implement bounded validation helpers**

Use standard library only. Required constants and shape:

```python
COPY_BUFFER_BYTES = 64 * 1024
MAX_ENTRYPOINT_BYTES = 512 * 1024 * 1024
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]+$")


def digest_file(path: Path) -> str:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise RegistrationError("entrypoint-not-regular")
    if metadata.st_size <= 0 or metadata.st_size > MAX_ENTRYPOINT_BYTES:
        raise RegistrationError("entrypoint-size")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(COPY_BUFFER_BYTES), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
```

Canonicalize the materialized root and each entrypoint. Require the canonical entrypoint to remain inside the canonical root. Require execute bits. Validate portable relative paths without backslashes, drive prefixes, empty components, `.` or `..`.

**Step 3: Build two explicit Runtime components**

Generate component artifacts by streaming the selected entrypoint bytes to owned staging files:

```python
components = [
    {
        "name": "wine-entrypoint",
        "version": version,
        "license": "LGPL-2.1-or-later",
        "artifact": "components/wine-entrypoint.bin",
        "digest": wine_digest,
        "entrypoints": {"wine": wine_relative},
    },
    {
        "name": "wineserver-entrypoint",
        "version": version,
        "license": "LGPL-2.1-or-later",
        "artifact": "components/wineserver-entrypoint.bin",
        "digest": wineserver_digest,
        "entrypoints": {"wineserver": wineserver_relative},
    },
]
```

Use fixed capabilities:

```python
capabilities = ["guest-i386", "guest-x86_64", "new-wow64"]
wined3d_capabilities = ["d3d9", "d3d11", "opengl"]
```

The manifest host is `macos/x86_64`, channel is `preview`, and no signature, SBOM or D3DMetal claim is emitted.

**Step 4: Compute the existing canonical manifest digest**

Build the unsigned manifest in schema order, serialize with:

```python
canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
manifest_digest = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
```

Append `digest` only after hashing the unsigned form. Write pretty JSON with one LF.

**Step 5: Generate existing macOS Provider schema v1 JSON**

Populate:

```python
provider = {
    "schemaVersion": "1",
    "runtimeStoreRoot": str(runtime_store_root),
    "wineRuntime": {
        "providerId": pack_id,
        "packId": pack_id,
        "packDigest": manifest_digest,
        "version": version,
        "architecture": "x86_64",
        "materializedRoot": str(materialized_root),
        "wine": {"path": wine_relative, "digest": wine_digest},
        "wineserver": {"path": wineserver_relative, "digest": wineserver_digest},
        "capabilities": capabilities,
        "wined3dCapabilities": wined3d_capabilities,
    },
}
```

Do not add a new schema.

**Step 6: Publish transactionally**

Create staging as a sibling of output. Write and `fsync` artifacts/JSON, reread and rehash them, then rename staging to a previously absent output path. If output exists, compare all expected regular files exactly: identical output returns an idempotent receipt; any extra/missing/different/nonregular entry fails without overwrite.

Never recursively delete a path unless it is the exact owned staging directory and its identity still matches the directory created by this process.

**Step 7: Emit one closed receipt**

Stdout is exactly one canonical JSON line:

```json
{"activated":false,"bundlePath":"<absolute>","packDigest":"sha256:...","packId":"...","providerConfigPath":"<absolute>","schemaVersion":"1"}
```

On failure, stdout is empty and stderr uses a fixed diagnostic code without reflecting arbitrary input paths.

**Step 8: Run GREEN and mutation tests**

```bash
python3 -S -B -m unittest tests.test_macos_headless_preview -v
python3 -S -B tools/register_macos_local_wine.py --help
python3 -S -B scripts/validate_repository.py
```

Expected: all tests pass and help performs no filesystem writes.

**Step 9: Commit**

```bash
git add tools/register_macos_local_wine.py tests/test_macos_headless_preview.py
git commit -s -m "feat: register local macOS Wine preview packs"
```

## Task 4: Specify additive PreparedLaunch CLI commands with RED tests

**Files:**

- Modify: `apps/cli/src/main.rs`
- Test: `apps/cli/src/main.rs`
- Test: `tests/test_macos_headless_preview.py`

**Step 1: Add parser tests before implementation**

In the CLI test module, add tests for an exact `PreparedCommand` parser:

```rust
#[test]
fn parses_only_exact_prepared_launch_forms() {
    assert_eq!(
        parse_prepared_command(&words(&[
            "prepared-launch", "context.json", "/tmp/probe.exe", "request.json",
        ])),
        Some(PreparedCommand::Launch {
            config_path: "context.json",
            executable_path: "/tmp/probe.exe",
            request_path: "request.json",
            terminate_after_milliseconds: None,
        })
    );
    assert_eq!(
        parse_prepared_command(&words(&[
            "prepared-launch-terminate", "context.json", "/tmp/probe.exe",
            "request.json", "1000",
        ])).unwrap().terminate_after_milliseconds(),
        Some(1000)
    );
    assert!(parse_prepared_command(&words(&[
        "prepared-launch", "context.json", "request.json",
    ])).is_none());
}
```

Test zero/overflow/invalid delay, extra arguments and unknown commands.

**Step 2: Add a black-box failure-boundary test**

Build the CLI into an external target. Invoke `prepared-launch` with a valid config/request shape but a non-PE source. Assert:

- exit code 1;
- stdout empty;
- stderr contains the fixed inspection/preparation error class;
- no process marker file appears;
- storage contains no executable launch result.

This proves the new command enters PreparedLaunch before process creation.

**Step 3: Run RED**

```bash
cargo test -p compatforge-cli parses_only_exact_prepared_launch_forms --locked
python3 -S -B -m unittest tests.test_macos_headless_preview -v
```

Expected: compile/test failure because `PreparedCommand` and `prepared-launch` do not exist.

**Step 4: Commit the RED tests**

```bash
git add apps/cli/src/main.rs tests/test_macos_headless_preview.py
git commit -s -m "test: specify PreparedLaunch CLI boundary"
```

## Task 5: Implement PreparedLaunch CLI without changing ABI or schemas

**Files:**

- Modify: `apps/cli/src/main.rs`
- Test: `apps/cli/src/main.rs`
- Test: `tests/test_macos_headless_preview.py`

**Step 1: Add the internal parser enum**

Keep it private to the CLI:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PreparedCommand<'a> {
    Launch {
        config_path: &'a str,
        executable_path: &'a str,
        request_path: &'a str,
        terminate_after_milliseconds: Option<u64>,
    },
}
```

Parse only the two exact argv forms. Delay must be `1..=86_400_000` milliseconds.

**Step 2: Dispatch before the generic help fallback**

At the top of `run_arguments`, after the Bottle group check:

```rust
if let Some(command) = parse_prepared_command(arguments) {
    return run_prepared_command(command);
}
```

Import `PreparedLaunch` from `compatforge_orchestrator`.

**Step 3: Implement the trusted command path**

Required structure:

```rust
fn run_prepared_command(command: PreparedCommand<'_>) -> Result<(), Box<dyn Error>> {
    let PreparedCommand::Launch {
        config_path,
        executable_path,
        request_path,
        terminate_after_milliseconds,
    } = command;
    let config = read_json::<CoreConfig>(Path::new(config_path))?;
    let request = read_json::<LaunchRequest>(Path::new(request_path))?;
    let source = absolute_path(Path::new(executable_path))?;
    let prepared = PreparedLaunch::prepare(&config, &source, &request)?;
    let plan = prepared.authorize(&config)?;
    supervise_plan(
        plan,
        terminate_after_milliseconds.map(Duration::from_millis),
    )
}
```

Do not fall back to `PolicyEngine::compile`, ordinary `launch`, another Runtime or a shell command.

**Step 4: Refactor the existing event loop once**

Keep ordinary `launch` behavior byte-compatible where observable:

```rust
fn launch(
    config: &CoreConfig,
    request: &LaunchRequest,
    terminate_after: Option<Duration>,
) -> Result<(), Box<dyn Error>> {
    let plan = PolicyEngine::compile(config, request)?;
    PolicyEngine::authorize(config, &plan)?;
    supervise_plan(&plan, terminate_after)
}

fn supervise_plan(
    plan: &LaunchPlan,
    terminate_after: Option<Duration>,
) -> Result<(), Box<dyn Error>> {
    let handle = ProcessSupervisor::start(plan)?;
    // Move the existing event loop here without changing event serialization.
}
```

PreparedLaunch must remain alive until `ProcessSupervisor::start` has consumed the authorized plan reference.

**Step 5: Update help additively**

Add exactly:

```text
compatforge-cli prepared-launch <context-config.json> <absolute-windows-executable> <launch-request.json>
compatforge-cli prepared-launch-terminate <context-config.json> <absolute-windows-executable> <launch-request.json> <delay-ms>
```

Do not remove or rename existing commands.

**Step 6: Run focused GREEN**

```bash
cargo fmt --all -- --check
cargo test -p compatforge-cli --all-targets --locked
cargo test -p compatforge-orchestrator --all-targets --locked
cargo test -p compatforge-process --all-targets --locked
cargo test -p compatforge-ffi --all-targets --locked
python3 -S -B -m unittest tests.test_macos_headless_preview -v
```

Expected: all pass. The FFI test confirms no ForgeOS-facing behavior regressed.

**Step 7: Prove ABI/schema isolation**

```bash
git diff --exit-code origin/main -- schemas crates/compatforge-ffi/include
git diff --check
```

Expected: no ABI/schema diff and no whitespace errors.

**Step 8: Commit**

```bash
git add apps/cli/src/main.rs tests/test_macos_headless_preview.py
git commit -s -m "feat: launch prepared guest artifacts from the CLI"
```

## Task 6: Add an explicit Apple Silicon local acceptance harness

**Files:**

- Create: `tests/fixtures/windows_console_smoke.c`
- Create: `tools/run_macos_headless_preview.py`
- Modify: `tests/test_macos_headless_preview.py`
- Test: `tests/test_macos_headless_preview.py`

**Step 1: Add source-only Windows probe**

Create:

```c
#include <stdio.h>

int main(void) {
    puts("COMPATFORGE_WINDOWS_CONSOLE_OK");
    return 0;
}
```

Do not commit the compiled `.exe`.

**Step 2: Write RED tests for the harness**

The harness must reject before running subprocesses when:

- host is not `Darwin/arm64`;
- any required path is relative;
- compiler, CLI, Wine root, Wine or wineserver is missing;
- work root overlaps repository, source runtime or stores;
- Wine paths are not portable relative paths;
- the selected PE is not produced inside the owned work root;
- an output evidence directory already contains foreign entries.

Mock subprocess results for the unit tests. Require exact command arrays; no `shell=True`, PATH Wine lookup, URL, environment discovery or neighbouring checkout access.

**Step 3: Implement explicit harness arguments**

Required interface:

```text
python3 -S -B tools/run_macos_headless_preview.py \
  --compatforge-cli <absolute-built-cli> \
  --cc <absolute-x86_64-w64-mingw32-gcc> \
  --wine-root <absolute-local-wine-root> \
  --wine <relative-entrypoint> \
  --wineserver <relative-entrypoint> \
  --runtime-store <absolute-local-runtime-store> \
  --storage-root <absolute-local-core-storage> \
  --work-root <absolute-empty-work-root> \
  --pack-id <local-preview-id> \
  --version <explicit-version>
```

Every executable path is explicit. The harness may invoke only the supplied compiler, supplied CompatForge CLI and the repository registration tool through `sys.executable`.

**Step 4: Build the probe in the owned work root**

Exact compiler argv:

```python
[
    str(cc),
    "-Os",
    "-s",
    "-Wall",
    "-Wextra",
    "-Werror",
    str(ROOT / "tests/fixtures/windows_console_smoke.c"),
    "-o",
    str(work_root / "windows-console-smoke.exe"),
]
```

After compilation, call `compatforge-cli inspect` and require `x86_64`, `windowsConsole`, `executable` before continuing.

**Step 5: Run the existing trust chain**

Execute, with exact argv and captured outputs:

1. `register_macos_local_wine.py`;
2. `compatforge-cli runtime install`;
3. `compatforge-cli runtime verify`;
4. `compatforge-cli provider macos probe`;
5. `compatforge-cli provider macos context`;
6. generate a local LaunchRequest whose executable path is the absolute compiled PE and architecture is `x86_64`;
7. `compatforge-cli prepared-launch`.

Set `bottleId` to a fixed safe ID and `networkPolicy` to `deny`. Do not add host environment variables to the request.

**Step 6: Authenticate the result**

Parse every stdout JSON/JSONL record. Require:

- provider runtime available;
- Rosetta provider available;
- selected graphics backend is WineD3D;
- LaunchPlan Runtime Pack digest equals install/verify receipts;
- Guest Artifact digest equals inspection digest;
- monotonically increasing event sequence;
- started event;
- stdout output containing exactly `COMPATFORGE_WINDOWS_CONSOLE_OK` after line normalization;
- exited event with `success: true` and code 0.

Write a local `summary.json` containing only stable IDs, versions, digests, architecture, provider kinds, event kinds and exit status. Do not write usernames, absolute paths or environment values into the summary.

**Step 7: Run mocked automated tests**

```bash
python3 -S -B -m unittest tests.test_macos_headless_preview -v
```

Expected: pass on all development hosts without executing Wine.

**Step 8: Run the real Mac acceptance**

Build the CLI first:

```bash
cargo build -p compatforge-cli --locked
```

Then run the harness with explicit local paths. Expected final output is one canonical summary JSON and exit 0. Run it twice with separate empty work roots and compare stable fields:

```bash
python3 - <<'PY'
import json
from pathlib import Path

left = json.loads(Path("/absolute/run-1/summary.json").read_text())
right = json.loads(Path("/absolute/run-2/summary.json").read_text())
assert left == right
PY
```

Do not add either work root to Git.

**Step 9: Run two real negative checks**

- Copy the Wine entrypoint to an isolated temporary root, register it, mutate the copy, and confirm Provider probe refuses before guest process creation.
- Copy the probe PE, prepare a request, mutate the source before invocation, and confirm Guest Artifact/inspection produces the new digest rather than trusting stale caller data; then mutate the stored object only in an isolated disposable store and confirm launch refuses.

Never mutate the developer's real Wine installation.

**Step 10: Commit source and harness**

```bash
git add tests/fixtures/windows_console_smoke.c tools/run_macos_headless_preview.py tests/test_macos_headless_preview.py
git commit -s -m "test: add Apple Silicon Wine preview acceptance"
```

## Task 7: Document the Mac operator workflow and preserve FOS ownership

**Files:**

- Create: `docs/guides/macos-headless-preview.md`
- Modify: `README.md`
- Modify: `docs/implementation/phase-1-macos-provider.md`
- Modify: `docs/testing.md`
- Test: `scripts/validate_repository.py`

**Step 1: Write the operator guide**

Document:

- exact prerequisites and explicit path discovery by the developer;
- why local Wine is not downloaded or distributed;
- how to identify the Wine root and entrypoints without PATH scanning by CompatForge;
- branch/worktree setup;
- MinGW probe compilation;
- registration, install, verify, provider and PreparedLaunch commands;
- evidence directory and privacy rules;
- expected success event sequence;
- negative tests;
- cleanup commands limited to the explicitly created work/store roots;
- limitations: Console-only, unsigned preview, no sandbox, no GUI/Qt/D3DMetal/distribution promise.

**Step 2: Update current-state wording precisely**

README must distinguish:

- automated fixture path;
- opt-in Apple Silicon local real PE evidence;
- unimplemented product/distribution capabilities.

Do not claim Tier 1, release readiness or arbitrary PE support.

**Step 3: Update Provider and testing evidence docs**

State that the local registration tool is not the formal Runtime materializer. Add the exact local acceptance command to `docs/testing.md`, but do not add it as a default CI gate because CI has no redistributable Wine Runtime.

**Step 4: Validate documentation links and repository contracts**

```bash
python3 -S -B scripts/validate_repository.py
python3 -S -B tools/convert_macwin_assets.py --check
git diff --check
```

Expected: all pass.

**Step 5: Commit**

```bash
git add README.md docs/guides/macos-headless-preview.md docs/implementation/phase-1-macos-provider.md docs/testing.md
git commit -s -m "docs: explain the macOS headless preview workflow"
```

## Task 8: Run final gates and hand the branch back without cross-repository conflicts

**Files:**

- Verify all files changed since `origin/main`
- No new implementation files

**Step 1: Review the exact scope**

```bash
git diff --name-status origin/main...HEAD
git diff --exit-code origin/main...HEAD -- schemas crates/compatforge-ffi/include
git status --short
```

Expected production scope is limited to:

- `apps/cli/src/main.rs`
- `tools/register_macos_local_wine.py`
- `tools/run_macos_headless_preview.py`
- tests/fixtures/docs listed above

No other repository or ABI/schema path may appear.

**Step 2: Run focused gates**

```bash
python3 -S -B -m unittest tests.test_macos_headless_preview -v
cargo test -p compatforge-cli --all-targets --locked
cargo test -p compatforge-provider-macos --all-targets --locked
cargo test -p compatforge-orchestrator --all-targets --locked
cargo test -p compatforge-process --all-targets --locked
cargo test -p compatforge-ffi --all-targets --locked
```

Expected: all pass.

**Step 3: Run full repository gates**

```bash
python3 -S -B scripts/validate_repository.py
python3 -S -B tools/convert_macwin_assets.py --check
python3 -S -B -m unittest tests.test_bottle_migration_contracts
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo test --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
git diff --check
```

Expected: all pass. Do not omit Bottle migration gates because this branch shares CLI and repository validation code.

**Step 4: Verify DCO and hygiene**

```bash
git log --format='%H%n%B%n---' origin/main..HEAD
git status --short --untracked-files=all
find . -type d \( -name target -o -name __pycache__ -o -name .pytest_cache \) -prune -print
```

Expected: every commit contains `Signed-off-by`, status is empty, and no generated local evidence or binary is tracked.

**Step 5: Synchronize main once at the task boundary**

```bash
git fetch origin --prune
git rebase origin/main
```

If the rebase touches schemas, FFI, Runtime DTO semantics or overlapping FOS integration code, stop and review rather than resolving mechanically. After a clean rebase, rerun Steps 2–4.

**Step 6: Push the implementation branch**

```bash
git push -u origin agent/macos-headless-preview
```

Do not push directly to main. Open a PR only after attaching:

- full gate results;
- local Apple Silicon summary with paths removed;
- exact Wine version/source statement;
- confirmation that no Wine/PE binary is in the diff;
- confirmation of no schema/C ABI/ForgeOS changes;
- known limitations and deferred Phase 1 work.

**Step 7: Stop at the approved milestone**

Do not continue into Qt/QML, GUI PE, D3DMetal, sandbox, daemon, Runtime downloading/materialization or ForgeOS integration on this branch. Those require separate designs after the headless preview evidence is reviewed.
