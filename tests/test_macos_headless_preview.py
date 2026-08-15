from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "tools" / "register_macos_local_wine.py"
HARNESS = ROOT / "tools" / "run_macos_headless_preview.py"
DISCOVER = ROOT / "tools" / "discover_macos_wine.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


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

    def run_register(self, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        arguments = [
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
        ]
        arguments.extend(extra)
        return subprocess.run(
            arguments,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_registration_is_deterministic_source_read_only_and_rust_compatible(self) -> None:
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
            self.assertEqual((self.root / "first" / relative).read_bytes(), (self.root / "second" / relative).read_bytes())
        manifest = json.loads((self.root / "first/bundle/manifest.json").read_text())
        provider = json.loads((self.root / "first/provider.json").read_text())
        receipt = json.loads(first.stdout)
        unsigned = {key: value for key, value in manifest.items() if key != "digest"}
        canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":")).encode()
        self.assertEqual(manifest["digest"], f"sha256:{hashlib.sha256(canonical).hexdigest()}")
        self.assertEqual(provider["wineRuntime"]["packDigest"], manifest["digest"])
        self.assertEqual(receipt["packDigest"], manifest["digest"])
        self.assertNotIn("d3dmetal", provider["wineRuntime"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(sha256(self.root / "first/bundle/components/wine-entrypoint.bin"), sha256(self.wine))

    def test_identical_existing_output_is_idempotent_but_foreign_output_fails(self) -> None:
        output = self.root / "output"
        self.assertEqual(self.run_register(output).returncode, 0)
        repeat = self.run_register(output)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        (output / "foreign").write_text("foreign")
        collision = self.run_register(output)
        self.assertNotEqual(collision.returncode, 0)
        self.assertEqual(collision.stdout, "")
        self.assertIn("output-collision", collision.stderr)

        empty_foreign = self.root / "empty-foreign"
        self.assertEqual(self.run_register(empty_foreign).returncode, 0)
        (empty_foreign / "unexpected-directory").mkdir()
        collision = self.run_register(empty_foreign)
        self.assertNotEqual(collision.returncode, 0)

    def test_rejects_relative_traversing_and_overlapping_paths(self) -> None:
        cases = [
            ("--output-root", "relative-output"),
            ("--runtime-store-root", "relative-store"),
            ("--materialized-root", "relative-runtime"),
            ("--wine", "../wine"),
            ("--wineserver", "/bin/true"),
            ("--output-root", str(self.materialized / "generated")),
            ("--output-root", str(ROOT)),
            ("--pack-id", "Invalid ID"),
            ("--version", ""),
        ]
        for index, (name, value) in enumerate(cases):
            with self.subTest(name=name, value=value):
                result = self.run_register(self.root / f"bad-{index}", name, value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_rejects_symlink_directory_and_non_executable_entrypoints(self) -> None:
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        outside.chmod(0o700)
        cases: list[tuple[str, Path]] = []
        symlink = self.materialized / "bin" / "symlink"
        symlink.symlink_to(outside)
        cases.append(("bin/symlink", symlink))
        directory = self.materialized / "bin" / "directory"
        directory.mkdir()
        cases.append(("bin/directory", directory))
        plain = self.materialized / "bin" / "plain"
        plain.write_bytes(b"plain")
        plain.chmod(0o600)
        cases.append(("bin/plain", plain))
        for index, (relative, _path) in enumerate(cases):
            with self.subTest(relative=relative):
                result = self.run_register(self.root / f"entry-{index}", "--wine", relative)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_tool_has_no_runtime_discovery_or_execution_surface(self) -> None:
        source = REGISTER.read_text()
        for forbidden in (
            "import subprocess",
            "import socket",
            "import urllib",
            "requests",
            "shutil.which",
            "Path.home",
            "os.system",
        ):
            self.assertNotIn(forbidden, source)


class MacOsHeadlessPreviewHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("run_macos_headless_preview", HARNESS)
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            spec.loader.exec_module(cls.module)
        finally:
            sys.path.remove(str(ROOT / "tools"))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="compatforge-preview-harness-")
        self.root = Path(self.temporary.name)
        self.wine_root = self.root / "wine-root"
        (self.wine_root / "bin").mkdir(parents=True)
        self.cli = self.root / "compatforge-cli"
        self.cc = self.root / "x86_64-w64-mingw32-gcc"
        self.wine = self.wine_root / "bin/wine"
        self.wineserver = self.wine_root / "bin/wineserver"
        for path in (self.cli, self.cc, self.wine, self.wineserver):
            path.write_bytes(b"fixture")
            path.chmod(0o700)
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def arguments(self):
        return self.module.parser().parse_args(
            [
                "--compatforge-cli",
                str(self.cli),
                "--cc",
                str(self.cc),
                "--wine-root",
                str(self.wine_root),
                "--wine",
                "bin/wine",
                "--wineserver",
                "bin/wineserver",
                "--runtime-store",
                str(self.root / "runtime-store"),
                "--storage-root",
                str(self.root / "storage-root"),
                "--work-root",
                str(self.work),
                "--pack-id",
                "wine-macos-local-preview",
                "--version",
                "developer-local",
            ]
        )

    def test_harness_accepts_isolated_darwin_arm64_paths(self) -> None:
        validated = self.module.validate(self.arguments(), "Darwin", "arm64")
        self.assertEqual(validated["wine"].as_posix(), "bin/wine")
        for system, machine in (("Linux", "arm64"), ("Darwin", "x86_64")):
            with self.assertRaises(self.module.AcceptanceError):
                self.module.validate(self.arguments(), system, machine)
        self.work.write_text("not-a-directory") if not self.work.exists() else None
        (self.work / "foreign").write_text("foreign")
        with self.assertRaises(self.module.AcceptanceError):
            self.module.validate(self.arguments(), "Darwin", "arm64")

    def test_harness_rejects_relative_and_overlapping_roots_before_commands(self) -> None:
        arguments = self.arguments()
        arguments.runtime_store = "relative-store"
        with self.assertRaises(self.module.AcceptanceError):
            self.module.validate(arguments, "Darwin", "arm64")
        arguments = self.arguments()
        arguments.work_root = str(self.wine_root / "work")
        (self.wine_root / "work").mkdir()
        with self.assertRaises(self.module.AcceptanceError):
            self.module.validate(arguments, "Darwin", "arm64")

    def test_harness_uses_no_shell_or_path_discovery(self) -> None:
        source = HARNESS.read_text()
        self.assertNotIn("shell=True", source)
        self.assertNotIn("shutil.which", source)
        self.assertNotIn("Path.home", source)
        self.assertNotIn("urllib", source)

    def test_harness_auto_discovery_populates_a_complete_verified_selection(self) -> None:
        arguments = self.arguments()
        arguments.wine_root = None
        arguments.wine = None
        arguments.wineserver = None
        arguments.version = None
        original = self.module.discover
        self.module.discover = lambda runner: {
            "materializedRoot": str(self.wine_root),
            "wine": "bin/wine",
            "wineserver": "bin/wineserver",
            "version": "11.11",
            "source": "test-candidate",
        }
        try:
            resolved = self.module.resolve_wine(arguments, runner=lambda *_args, **_kwargs: None)
        finally:
            self.module.discover = original
        self.assertEqual(resolved.wine_root, str(self.wine_root))
        self.assertEqual(resolved.version, "11.11")
        self.assertEqual(resolved.wine_source, "test-candidate")

    def test_harness_rejects_partial_explicit_wine_selection(self) -> None:
        arguments = self.arguments()
        arguments.version = None
        with self.assertRaises(self.module.AcceptanceError):
            self.module.resolve_wine(arguments)

    def test_mocked_harness_runs_the_exact_trust_chain_and_writes_redacted_summary(self) -> None:
        calls: list[list[str]] = []
        digest = "sha256:" + "a" * 64
        pack_digest = "sha256:" + "b" * 64

        def completed(argv, stdout=""):
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        def fake_runner(argv, **kwargs):
            calls.append(list(argv))
            self.assertNotIn("shell", kwargs)
            if argv[0] == str(self.cc.resolve()):
                Path(argv[argv.index("-o") + 1]).write_bytes(b"mock-pe")
                return completed(argv)
            if argv[0] == sys.executable:
                registration = self.work / "registration"
                (registration / "bundle").mkdir(parents=True)
                (registration / "provider.json").write_text("{}")
                return completed(
                    argv,
                    json.dumps(
                        {
                            "schemaVersion": "1",
                            "packId": "wine-macos-local-preview",
                            "packDigest": pack_digest,
                            "bundlePath": str(registration / "bundle"),
                            "providerConfigPath": str(registration / "provider.json"),
                            "activated": False,
                        }
                    ),
                )
            self.assertEqual(argv[0], str(self.cli.resolve()))
            command = argv[1:]
            if command[0] == "inspect":
                return completed(
                    argv,
                    json.dumps(
                        {
                            "schemaVersion": "1",
                            "fileDigest": digest,
                            "architecture": "x86_64",
                            "subsystem": "windowsConsole",
                            "imageKind": "executable",
                        }
                    ),
                )
            if command[:2] == ["runtime", "install"]:
                return completed(argv, json.dumps({"digest": pack_digest, "packId": "wine-macos-local-preview"}))
            if command[:2] == ["runtime", "verify"]:
                return completed(argv, json.dumps({"digest": pack_digest, "packId": "wine-macos-local-preview"}))
            if command[:3] == ["provider", "macos", "probe"]:
                return completed(
                    argv,
                    json.dumps(
                        {
                            "host": {"architecture": "arm64"},
                            "runtimeProviders": [{"kind": "wine", "available": True}],
                            "translators": [{"kind": "rosetta", "available": True}],
                            "graphicsBackends": [{"kind": "wined3d", "available": True}],
                        }
                    ),
                )
            if command[:3] == ["provider", "macos", "context"]:
                return completed(
                    argv,
                    json.dumps(
                        {
                            "schemaVersion": "1",
                            "storageRoot": str(self.root / "storage-root"),
                            "supervisor": {"terminationGraceMilliseconds": 5000},
                        }
                    ),
                )
            if command[0] == "prepared-plan":
                working_directory = self.root / "storage-root/bottles/macos-headless-preview"
                return completed(
                    argv,
                    json.dumps(
                        {
                            "runtime": {"packDigest": pack_digest},
                            "translator": {"provider": "rosetta"},
                            "graphics": {"backend": "wined3d"},
                            "guestArtifact": {"digest": digest},
                            "process": {
                                "workingDirectory": str(working_directory),
                                "environment": {"WINEPREFIX": str(working_directory / "prefix")},
                            },
                        }
                    ),
                )
            if command[0] == "prepared-launch":
                events = [
                    {"sequence": 0, "kind": "started"},
                    {
                        "sequence": 1,
                        "kind": "output",
                        "output": {"stream": "stdout", "text": "COMPATFORGE_WINDOWS_CONSOLE_OK\n"},
                    },
                    {"sequence": 2, "kind": "exited", "exit": {"success": True, "code": 0}},
                ]
                return completed(argv, "".join(json.dumps(event) + "\n" for event in events))
            self.fail(f"unexpected command: {argv}")

        with mock.patch.object(self.module.platform, "system", return_value="Darwin"), mock.patch.object(
            self.module.platform, "machine", return_value="arm64"
        ):
            summary = self.module.run(self.arguments(), runner=fake_runner)
        self.assertTrue(summary["success"])
        self.assertEqual(summary["packDigest"], pack_digest)
        self.assertEqual(summary["runtimeSource"], "explicit")
        self.assertEqual(
            calls[0][1:8],
            [
                "-Os",
                "-s",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wl,--no-insert-timestamp",
                str(ROOT / "tests/fixtures/windows_console_smoke.c"),
            ],
        )
        self.assertEqual(calls[-2][1], "prepared-plan")
        self.assertEqual(calls[-1][1], "prepared-launch")
        serialized = json.dumps(summary)
        self.assertNotIn(str(self.root), serialized)
        self.assertTrue((self.work / "prepared-launch-plan.json").is_file())
        self.assertTrue((self.work / "runtime-events.jsonl").is_file())


class MacOsWineDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("discover_macos_wine", DISCOVER)
        assert spec is not None and spec.loader is not None
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="compatforge-wine-discovery-")
        self.root = Path(self.temporary.name)
        (self.root / "loader").mkdir()
        (self.root / "server").mkdir()
        self.wine = self.root / "loader/wine"
        self.wineserver = self.root / "server/wineserver"
        macho = b"\xcf\xfa\xed\xfe" + (0x0100_0007).to_bytes(4, "little") + b"fixture"
        for path in (self.wine, self.wineserver):
            path.write_bytes(macho)
            path.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_discovery_requires_thin_x86_64_and_successful_version_execution(self) -> None:
        calls: list[list[str]] = []

        def runner(argv, **kwargs):
            calls.append(list(argv))
            self.assertEqual(kwargs["env"], {"LANG": "C", "LC_ALL": "C", "WINEDEBUG": "-all"})
            stdout = "wine-11.11\n" if argv[0].endswith("/wine") else "Wine 11.11\n"
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

        candidate = self.module.Candidate("test", self.root, "loader/wine", "server/wineserver")
        selected = self.module.verify_candidate(candidate, runner)
        self.assertEqual(selected["version"], "11.11")
        self.assertEqual(selected["wine"], "loader/wine")
        self.assertEqual(len(calls), 2)

        self.wine.write_bytes(b"\xcf\xfa\xed\xfe" + (0x0100_000C).to_bytes(4, "little") + b"fixture")
        self.assertIsNone(self.module.verify_candidate(candidate, runner))

    def test_discovery_rejects_failed_version_probe_and_escaping_entrypoint(self) -> None:
        candidate = self.module.Candidate("test", self.root, "loader/wine", "server/wineserver")

        def failed(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="failed")

        self.assertIsNone(self.module.verify_candidate(candidate, failed))
        outside = self.root.parent / "outside-wine"
        outside.write_bytes(self.wine.read_bytes())
        outside.chmod(0o700)
        self.wine.unlink()
        self.wine.symlink_to(outside)
        self.assertIsNone(self.module.verify_candidate(candidate, failed))


if __name__ == "__main__":
    unittest.main()
