from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath


ROOT = Path(__file__).resolve().parents[1]


class MigrationLayoutTests(unittest.TestCase):
    APPROVED_LAYOUT = (
        "migration/macwin/source/index.json",
        "migration/macwin/source/objects/sha256/ab/cdef",
        "migration/macwin/generated/index.json",
        "migration/macwin/generated/catalog.json",
        "migration/macwin/generated/recipes/example.json",
        "migration/macwin/generated/probes/example.json",
        "migration/macwin/generated/fixtures/example.json",
        "migration/macwin/generated/mappings/patches.json",
        "migration/macwin/generated/mappings/bottle-schemas.json",
        "migration/macwin/generated/quarantine.json",
        "schemas/macwin-source-pack.schema.json",
        "schemas/migration-record.schema.json",
        "schemas/quarantine.schema.json",
        "schemas/portable-probe.schema.json",
        "schemas/portable-fixture.schema.json",
        "tools/import_macwin_source_pack.py",
        "tools/convert_macwin_assets.py",
        "tests/test_macwin_asset_migration.py",
    )

    def test_approved_layout_uses_repository_relative_posix_paths(self) -> None:
        for value in self.APPROVED_LAYOUT:
            with self.subTest(path=value):
                path = PurePosixPath(value)
                self.assertEqual(path.as_posix(), value)
                self.assertFalse(path.is_absolute())
                self.assertFalse(PureWindowsPath(value).is_absolute())
                self.assertNotIn("\\", value)
                self.assertTrue(path.parts)
                self.assertNotIn("..", path.parts)

    def test_json_contracts_are_lf_pinned_by_repository_attributes(self) -> None:
        self._git(ROOT, "ls-files", "--error-unmatch", ".gitattributes")
        attributes = self._git_bytes(ROOT, "show", "HEAD:.gitattributes")
        self.assertNotIn(b"\r", attributes)
        self.assertEqual(
            attributes.count(b"/migration/macwin/**/*.json text eol=lf\n"),
            1,
        )
        self.assertEqual(
            attributes.count(b"/schemas/macwin-*.schema.json text eol=lf\n"),
            1,
        )

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / ".gitattributes").write_bytes(attributes)
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.name", "Migration Contract Test")
            self._git(repository, "config", "user.email", "migration@example.invalid")
            self._git(repository, "config", "core.autocrlf", "true")
            self._git(repository, "add", ".gitattributes")
            self._git(repository, "commit", "--quiet", "-m", "attributes")
            self.assertEqual(
                self._git_bytes(repository, "show", "HEAD:.gitattributes"),
                attributes,
            )

            samples = (
                "migration/macwin/source/index.json",
                "migration/macwin/generated/mappings/patches.json",
                "schemas/macwin-source-pack.schema.json",
            )
            for value in samples:
                path = repository / PurePosixPath(value)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'{\r\n  "schemaVersion": "1"\r\n}\r\n')

            self._git(repository, "add", *samples)
            for value in samples:
                with self.subTest(path=value):
                    self.assertEqual(
                        self._git(repository, "check-attr", "--cached", "eol", "--", value),
                        f"{value}: eol: lf",
                    )
                    blob = self._git_bytes(repository, "show", f":{value}")
                    self.assertIn(b"\n", blob)
                    self.assertNotIn(b"\r", blob)

    def test_migration_python_imports_leave_no_repository_bytecode(self) -> None:
        before = self._repository_bytecode()
        self.assertEqual(before, set())

        modules = (
            ROOT / "scripts/validate_repository.py",
            ROOT / "tools/import_macwin_source_pack.py",
            ROOT / "tools/convert_macwin_assets.py",
        )
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for module in modules:
            if not module.is_file():
                continue
            with self.subTest(module=module.relative_to(ROOT).as_posix()):
                subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        "import runpy, sys; runpy.run_path(sys.argv[1], "
                        "run_name='migration_import_contract')",
                        str(module),
                    ],
                    cwd=ROOT,
                    check=True,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

        self.assertEqual(self._repository_bytecode(), before)

    def test_repository_validation_skips_only_an_absent_converter(self) -> None:
        validator = self._load_repository_validator()
        self.assertTrue(
            hasattr(validator, "validate_macwin_asset_migration"),
            "repository validator is missing the temporary migration-check hook",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator.ROOT = root
            self.assertEqual(validator.validate_macwin_asset_migration(), [])

            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text(
                "import sys\n"
                "print('intentional converter failure', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_macwin_asset_migration()
            self.assertEqual(len(errors), 1)
            self.assertIn("intentional converter failure", errors[0])

    def test_repository_validation_runs_converter_check_before_success(self) -> None:
        validator = self._load_repository_validator()
        self.assertTrue(
            hasattr(validator, "validate_macwin_asset_migration"),
            "repository validator is missing the temporary migration-check hook",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_valid_repository(root)
            validator.ROOT = root

            standard_output = io.StringIO()
            standard_error = io.StringIO()
            with contextlib.redirect_stdout(standard_output), contextlib.redirect_stderr(
                standard_error
            ):
                result = validator.main()

            self.assertEqual(result, 0, standard_error.getvalue())
            self.assertEqual(
                (root / "migration-check-invocation.json").read_text(encoding="utf-8"),
                '["--check"]',
            )

    @staticmethod
    def _load_repository_validator():
        path = ROOT / "scripts/validate_repository.py"
        spec = importlib.util.spec_from_file_location(
            "macwin_migration_repository_validator", path
        )
        if spec is None or spec.loader is None:
            raise AssertionError(f"could not load repository validator: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _repository_bytecode() -> set[str]:
        bytecode: set[str] = set()
        pending = [ROOT]
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                if path.name in {".git", "target"}:
                    continue
                if path.is_dir():
                    if path.name == "__pycache__":
                        bytecode.add(path.relative_to(ROOT).as_posix())
                    else:
                        pending.append(path)
                elif path.suffix in {".pyc", ".pyo"}:
                    bytecode.add(path.relative_to(ROOT).as_posix())
        return bytecode

    @staticmethod
    def _write_minimal_valid_repository(root: Path) -> None:
        (root / "Cargo.toml").write_text(
            "[workspace]\nmembers = [\n]\n", encoding="utf-8", newline="\n"
        )
        fixture = b"MZ-migration-contract"
        fixture_path = root / "tests/fixtures/hello-x86_64.exe"
        fixture_path.parent.mkdir(parents=True)
        fixture_path.write_bytes(fixture)

        report = {
            "fileDigest": "sha256:" + hashlib.sha256(fixture).hexdigest(),
            "fileSizeBytes": len(fixture),
            "importLibraries": [],
            "schemaVersion": "1",
        }
        example = root / "examples/executable-inspection.hello-x86_64.json"
        example.parent.mkdir(parents=True)
        example.write_text(
            json.dumps(report, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        converter = root / "tools/convert_macwin_assets.py"
        converter.parent.mkdir(parents=True)
        converter.write_text(
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            "Path('migration-check-invocation.json').write_text(\n"
            "    json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            ")\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def _git(repository: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _git_bytes(repository: Path, *arguments: str) -> bytes:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout


if __name__ == "__main__":
    unittest.main()
