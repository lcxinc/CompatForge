#!/usr/bin/env python3
"""Validate repository-local contracts without third-party dependencies."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import types
from pathlib import Path
from pathlib import PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_MEMBER = re.compile(r'^\s*"([^"]+)"[,]?\s*$')
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MIGRATION_CHECK_TIMEOUT_SECONDS = 120
MIGRATION_ENVIRONMENT_NAMES = frozenset(
    {
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)
SOURCE_PACK_VALIDATOR = Path(__file__).resolve().parents[1] / "tools" / "import_macwin_source_pack.py"
TASK5_DOCUMENT_PATHS = frozenset(
    {
        "migration/macwin/generated/catalog.json",
        "migration/macwin/generated/quarantine.json",
    }
)
MAX_TASK5_DOCUMENT_BYTES = 1024 * 1024
MAX_ORDINARY_SCAN_BYTES = 32 * 1024 * 1024
DEVELOPER_PATH_VALIDATION_ERROR = "Repository developer-path validation failed"


def validate_macwin_asset_migration() -> list[str]:
    """Run the migration converter check once the Task 4 tool exists."""
    converter = ROOT / "tools/convert_macwin_assets.py"
    try:
        converter_metadata = converter.lstat()
    except FileNotFoundError:
        # Temporary Task 1 boundary: Task 8 removes this absence-only skip.
        return []
    except OSError:
        return ["Mac-Win asset migration converter path is not a regular file"]
    if not stat.S_ISREG(converter_metadata.st_mode) or getattr(
        converter_metadata, "st_reparse_tag", 0
    ):
        return ["Mac-Win asset migration converter path is not a regular file"]

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in MIGRATION_ENVIRONMENT_NAMES
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(converter), "--check"],
            cwd=ROOT,
            check=False,
            env=environment,
            executable=None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=MIGRATION_CHECK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ["Mac-Win asset migration check timed out"]
    except OSError:
        return ["Mac-Win asset migration check could not start"]
    if completed.returncode == 0:
        return []

    return [f"Mac-Win asset migration check failed with exit {completed.returncode}"]


def validate_json() -> list[str]:
    errors: list[str] = []
    identifiers: dict[str, Path] = {}
    paths = sorted((ROOT / "schemas").glob("*.json"))
    paths += sorted((ROOT / "examples").rglob("*.json"))

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{path.relative_to(ROOT)}: {error}")
            continue

        if "schemaVersion" not in data and path.parent.name != "schemas":
            errors.append(f"{path.relative_to(ROOT)}: missing schemaVersion")

        schema_id = data.get("$id")
        if schema_id:
            if schema_id in identifiers:
                errors.append(
                    f"{path.relative_to(ROOT)}: duplicate $id also used by "
                    f"{identifiers[schema_id].relative_to(ROOT)}"
                )
            identifiers[schema_id] = path

    return errors


def validate_workspace_members() -> list[str]:
    errors: list[str] = []
    cargo = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    in_members = False
    for line in cargo.splitlines():
        if line.strip() == "members = [":
            in_members = True
            continue
        if in_members and line.strip() == "]":
            break
        if not in_members:
            continue
        match = WORKSPACE_MEMBER.match(line)
        if match and not (ROOT / match.group(1) / "Cargo.toml").is_file():
            errors.append(f"workspace member is missing: {match.group(1)}")
    return errors


def validate_markdown_links() -> list[str]:
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(content):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if ROOT not in resolved.parents and resolved != ROOT:
                errors.append(f"{path.relative_to(ROOT)}: link escapes repository: {target}")
            elif not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken local link: {target}")
    return errors


def _validated_macwin_source_pack_binding() -> tuple[object | None, list[str]]:
    """Return a live identity/content binding for the authenticated source pack."""
    source_root = ROOT / "migration" / "macwin" / "source"
    try:
        source_metadata = source_root.lstat()
    except FileNotFoundError:
        return None, ["Mac-Win source pack validation failed"]
    except OSError:
        return None, ["Mac-Win source pack validation failed"]
    if (
        not stat.S_ISDIR(source_metadata.st_mode)
        or stat.S_ISLNK(source_metadata.st_mode)
        or getattr(source_metadata, "st_reparse_tag", 0)
    ):
        return None, ["Mac-Win source pack validation failed"]

    try:
        validator_metadata = SOURCE_PACK_VALIDATOR.lstat()
    except OSError:
        return None, ["Mac-Win source pack validation failed"]
    if (
        not stat.S_ISREG(validator_metadata.st_mode)
        or stat.S_ISLNK(validator_metadata.st_mode)
        or getattr(validator_metadata, "st_reparse_tag", 0)
    ):
        return None, ["Mac-Win source pack validation failed"]

    try:
        spec = importlib.util.spec_from_file_location(
            "repository_macwin_source_pack_validator", SOURCE_PACK_VALIDATOR
        )
        if spec is None or spec.loader is None:
            return None, ["Mac-Win source pack validation failed"]
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        binding = module.bind_source_pack(source_root)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None, ["Mac-Win source pack validation failed"]
    return binding, []


def _filesystem_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _validate_bound_path_chain(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    bindings: list[
        tuple[Path, tuple[int, int, int, int, int, int]]
    ] = []
    for part in absolute.parts[1:]:
        current /= part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_reparse_tag", 0):
            raise ValueError("generated evidence path is linked")
        if current != absolute and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("generated evidence path is invalid")
        bindings.append((current, _filesystem_identity(metadata)))
    for component, identity in bindings:
        if _filesystem_identity(component.lstat()) != identity:
            raise ValueError("generated evidence path identity changed")


def _read_bound_regular_file(
    path: Path,
    maximum: int,
    *,
    require_single_link: bool = True,
) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    if type(require_single_link) is not bool:
        raise TypeError("regular-file link policy is invalid")
    _validate_bound_path_chain(path)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or getattr(before, "st_reparse_tag", 0)
        or (require_single_link and before.st_nlink != 1)
        or before.st_size > maximum
    ):
        raise ValueError("generated evidence leaf is invalid")
    identity = _filesystem_identity(before)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _filesystem_identity(opened)[:4] != identity[:4]:
            raise ValueError("generated evidence identity changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError("generated evidence exceeds the byte limit")
            chunks.append(chunk)
        final = os.fstat(descriptor)
        if _filesystem_identity(final) != _filesystem_identity(opened):
            raise ValueError("generated evidence identity changed")
    finally:
        os.close(descriptor)
    after = path.lstat()
    if _filesystem_identity(after) != identity:
        raise ValueError("generated evidence identity changed")
    _validate_bound_path_chain(path)
    return b"".join(chunks), identity


class _GeneratedEvidenceBinding:
    """Bind exact Task 5 output paths to converter-rebuilt canonical bytes."""

    def __init__(
        self,
        generated_root: Path,
        root_identity: tuple[int, int, int, int, int, int],
        expected: dict[str, bytes],
        leaves: dict[Path, tuple[bytes, tuple[int, int, int, int, int, int]]],
        converter: object,
        converter_path: Path,
        converter_raw: bytes,
        converter_identity: tuple[int, int, int, int, int, int],
    ) -> None:
        self.generated_root = generated_root
        self.root_identity = root_identity
        self.expected = expected
        self.leaves = leaves
        self.converter = converter
        self.converter_path = converter_path
        self.converter_raw = converter_raw
        self.converter_identity = converter_identity

    def contains(self, path: Path) -> bool:
        return path.absolute() in self.leaves

    def verify_path(self, path: Path) -> bytes:
        absolute = path.absolute()
        expected = self.leaves.get(absolute)
        if expected is None:
            raise ValueError("generated evidence path is not authenticated")
        raw, identity = _read_bound_regular_file(absolute, MAX_TASK5_DOCUMENT_BYTES)
        if identity != expected[1] or raw != expected[0]:
            raise ValueError("generated evidence changed")
        return raw

    def revalidate(self) -> None:
        root = self.generated_root.lstat()
        if (
            not stat.S_ISDIR(root.st_mode)
            or stat.S_ISLNK(root.st_mode)
            or getattr(root, "st_reparse_tag", 0)
            or _filesystem_identity(root) != self.root_identity
        ):
            raise ValueError("generated evidence root changed")
        converter_raw, converter_identity = _read_bound_regular_file(
            self.converter_path, MAX_TASK5_DOCUMENT_BYTES
        )
        if (
            converter_raw != self.converter_raw
            or converter_identity != self.converter_identity
        ):
            raise ValueError("generated evidence converter changed")
        regenerated = self.converter.render_documents(
            self.converter.build_conversion(ROOT)
        )
        if type(regenerated) is not dict or regenerated != self.expected:
            raise ValueError("generated evidence semantics changed")
        for path in sorted(self.leaves, key=lambda value: str(value).encode("utf-8")):
            self.verify_path(path)
        final_root = self.generated_root.lstat()
        if _filesystem_identity(final_root) != self.root_identity:
            raise ValueError("generated evidence root changed")


class _DeveloperPathScanError(ValueError):
    """Signal an untrusted ordinary repository path without reflecting it."""


def _ordinary_entry_kind(metadata: os.stat_result) -> str:
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_reparse_tag", 0):
        raise _DeveloperPathScanError()
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    if stat.S_ISREG(metadata.st_mode):
        return "regular"
    raise _DeveloperPathScanError()


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    """Return the stable volume/file identity, excluding mutable metadata."""

    return (metadata.st_dev, metadata.st_ino)


def _read_bound_directory(
    path: Path,
) -> tuple[
    tuple[int, int],
    tuple[tuple[str, str], ...],
]:
    try:
        _validate_bound_path_chain(path)
        before = path.lstat()
        if _ordinary_entry_kind(before) != "directory":
            raise _DeveloperPathScanError()
        identity = _directory_identity(before)
        entries: list[tuple[str, str]] = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                if entry.name == ".git":
                    continue
                metadata = entry.stat(follow_symlinks=False)
                entries.append((entry.name, _ordinary_entry_kind(metadata)))
        after = path.lstat()
        if _ordinary_entry_kind(after) != "directory" or _directory_identity(
            after
        ) != identity:
            raise _DeveloperPathScanError()
        _validate_bound_path_chain(path)
    except _DeveloperPathScanError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise _DeveloperPathScanError() from None
    return identity, tuple(
        sorted(entries, key=lambda item: item[0].encode("utf-8"))
    )


class _OrdinaryFileBinding:
    """Retain exact ordinary directory and leaf bindings through validation."""

    def __init__(self) -> None:
        self.directories: dict[
            Path,
            tuple[
                tuple[int, int],
                tuple[tuple[str, str], ...],
            ],
        ] = {}
        self.leaves: dict[
            Path, tuple[bytes, tuple[int, int, int, int, int, int]]
        ] = {}

    def add_directory(
        self,
        path: Path,
        expected_entries: tuple[tuple[str, str], ...],
    ) -> None:
        absolute = path.absolute()
        if absolute in self.directories:
            raise _DeveloperPathScanError()
        identity, entries = _read_bound_directory(absolute)
        if entries != expected_entries:
            raise _DeveloperPathScanError()
        self.directories[absolute] = (identity, entries)

    def add(
        self,
        path: Path,
        raw: bytes,
        identity: tuple[int, int, int, int, int, int],
    ) -> None:
        absolute = path.absolute()
        if absolute in self.leaves:
            raise _DeveloperPathScanError()
        self.leaves[absolute] = (hashlib.sha256(raw).digest(), identity)

    def _revalidate_directories(self) -> None:
        for path in sorted(
            self.directories, key=lambda value: str(value).encode("utf-8")
        ):
            expected_identity, expected_entries = self.directories[path]
            identity, entries = _read_bound_directory(path)
            if identity != expected_identity or entries != expected_entries:
                raise _DeveloperPathScanError()

    def revalidate(self) -> None:
        self._revalidate_directories()
        for path in sorted(self.leaves, key=lambda value: str(value).encode("utf-8")):
            expected_digest, expected_identity = self.leaves[path]
            try:
                raw, identity = _read_bound_regular_file(
                    path,
                    MAX_ORDINARY_SCAN_BYTES,
                    require_single_link=False,
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                raise _DeveloperPathScanError() from None
            if (
                identity != expected_identity
                or hashlib.sha256(raw).digest() != expected_digest
            ):
                raise _DeveloperPathScanError()
        self._revalidate_directories()


def _load_task5_converter() -> tuple[
    object,
    Path,
    bytes,
    tuple[int, int, int, int, int, int],
]:
    path = ROOT / "tools" / "convert_macwin_assets.py"
    raw, identity = _read_bound_regular_file(path, MAX_TASK5_DOCUMENT_BYTES)
    module_name = f"_repository_macwin_task5_converter_{id(raw):x}"
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        if sys.modules.get(module_name) is module:
            sys.modules.pop(module_name, None)
    after_raw, after_identity = _read_bound_regular_file(
        path, MAX_TASK5_DOCUMENT_BYTES
    )
    if after_raw != raw or after_identity != identity:
        raise ValueError("generated evidence converter changed")
    return module, path, raw, identity


def _validated_macwin_generated_evidence_binding() -> tuple[
    _GeneratedEvidenceBinding | None, list[str]
]:
    """Rebuild, compare, and bind only the two approved Task 5 leaves."""

    try:
        converter, converter_path, converter_raw, converter_identity = (
            _load_task5_converter()
        )
        expected = converter.render_documents(converter.build_conversion(ROOT))
        if type(expected) is not dict or set(expected) != TASK5_DOCUMENT_PATHS:
            raise ValueError("generated evidence set is invalid")
        if any(type(raw) is not bytes or len(raw) > MAX_TASK5_DOCUMENT_BYTES for raw in expected.values()):
            raise ValueError("generated evidence bytes are invalid")
        generated_root = (ROOT / "migration" / "macwin" / "generated").absolute()
        root = generated_root.lstat()
        if (
            not stat.S_ISDIR(root.st_mode)
            or stat.S_ISLNK(root.st_mode)
            or getattr(root, "st_reparse_tag", 0)
        ):
            raise ValueError("generated evidence root is invalid")
        root_identity = _filesystem_identity(root)
        leaves: dict[
            Path, tuple[bytes, tuple[int, int, int, int, int, int]]
        ] = {}
        for relative in sorted(expected, key=lambda value: value.encode("ascii")):
            path = (ROOT / PurePosixPath(relative)).absolute()
            raw, identity = _read_bound_regular_file(path, MAX_TASK5_DOCUMENT_BYTES)
            if raw != expected[relative] or hashlib.sha256(raw).digest() != hashlib.sha256(expected[relative]).digest():
                raise ValueError("generated evidence bytes do not match")
            leaves[path] = (raw, identity)
        if len(leaves) != 2:
            raise ValueError("generated evidence leaf set is invalid")
        binding = _GeneratedEvidenceBinding(
            generated_root,
            root_identity,
            dict(expected),
            leaves,
            converter,
            converter_path,
            converter_raw,
            converter_identity,
        )
        binding.revalidate()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None, ["Mac-Win generated evidence validation failed"]
    return binding, []


def _scan_developer_paths(
    source_binding: object | None,
    generated_binding: _GeneratedEvidenceBinding | None = None,
) -> tuple[list[str], _OrdinaryFileBinding]:
    errors: list[str] = []
    ordinary_binding = _OrdinaryFileBinding()
    forbidden = ("/Users/a1-6/", "/home/a1-6/")
    try:
        paths = sorted(ROOT.rglob("*"))
    except OSError:
        raise _DeveloperPathScanError() from None
    entries: list[tuple[Path, str]] = []
    expected_children: dict[Path, list[tuple[str, str]]] = {
        ROOT.absolute(): []
    }
    for path in paths:
        if ".git" in path.parts:
            continue
        try:
            kind = _ordinary_entry_kind(path.lstat())
        except _DeveloperPathScanError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError):
            raise _DeveloperPathScanError() from None
        absolute = path.absolute()
        entries.append((absolute, kind))
        expected_children.setdefault(absolute.parent, []).append(
            (absolute.name, kind)
        )
        if kind == "directory":
            expected_children.setdefault(absolute, [])

    for directory in sorted(
        expected_children, key=lambda value: str(value).encode("utf-8")
    ):
        expected = tuple(
            sorted(
                expected_children[directory],
                key=lambda item: item[0].encode("utf-8"),
            )
        )
        ordinary_binding.add_directory(directory, expected)

    for path, kind in entries:
        if kind == "directory":
            continue
        if source_binding is not None and source_binding.contains(path):
            source_binding.verify_path(path)
            continue
        if generated_binding is not None and generated_binding.contains(path):
            generated_binding.verify_path(path)
            continue
        if path == Path(__file__).absolute():
            continue
        try:
            raw, identity = _read_bound_regular_file(
                path,
                MAX_ORDINARY_SCAN_BYTES,
                require_single_link=False,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            raise _DeveloperPathScanError() from None
        ordinary_binding.add(path, raw, identity)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for value in forbidden:
            if value in content:
                errors.append(f"{path.relative_to(ROOT)}: contains developer path {value}")
    return errors, ordinary_binding


def _unbound_developer_path_scan() -> list[str]:
    try:
        errors, binding = _scan_developer_paths(None, None)
        binding.revalidate()
    except _DeveloperPathScanError:
        return [DEVELOPER_PATH_VALIDATION_ERROR]
    return errors


def validate_no_developer_paths() -> list[str]:
    source_binding, errors = _validated_macwin_source_pack_binding()
    if source_binding is None:
        return [*errors, *_unbound_developer_path_scan()]
    generated_binding, generated_errors = (
        _validated_macwin_generated_evidence_binding()
    )
    if generated_binding is None:
        try:
            scanned_errors, ordinary_binding = _scan_developer_paths(
                source_binding, None
            )
            source_binding.revalidate()
            ordinary_binding.revalidate()
            source_binding.revalidate()
        except _DeveloperPathScanError:
            return [*generated_errors, DEVELOPER_PATH_VALIDATION_ERROR]
        except (OSError, RuntimeError, TypeError, ValueError):
            return [
                "Mac-Win source pack validation failed",
                *generated_errors,
                *_unbound_developer_path_scan(),
            ]
        return [*generated_errors, *scanned_errors]
    try:
        scanned_errors, ordinary_binding = _scan_developer_paths(
            source_binding, generated_binding
        )
    except _DeveloperPathScanError:
        return [DEVELOPER_PATH_VALIDATION_ERROR]
    except (OSError, RuntimeError, TypeError, ValueError):
        try:
            source_binding.revalidate()
        except (OSError, RuntimeError, TypeError, ValueError):
            return [
                "Mac-Win source pack validation failed",
                "Mac-Win generated evidence validation failed",
                *_unbound_developer_path_scan(),
            ]
        return [
            "Mac-Win generated evidence validation failed",
            *_unbound_developer_path_scan(),
        ]
    try:
        ordinary_binding.revalidate()
    except _DeveloperPathScanError:
        return [DEVELOPER_PATH_VALIDATION_ERROR]
    try:
        source_binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return [
            "Mac-Win source pack validation failed",
            *_unbound_developer_path_scan(),
        ]
    try:
        generated_binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return [
            "Mac-Win generated evidence validation failed",
            *_unbound_developer_path_scan(),
        ]
    try:
        source_binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return [
            "Mac-Win source pack validation failed",
            *_unbound_developer_path_scan(),
        ]
    try:
        ordinary_binding.revalidate()
    except _DeveloperPathScanError:
        return [DEVELOPER_PATH_VALIDATION_ERROR]
    return scanned_errors


def validate_pe_inspection_fixture() -> list[str]:
    fixture = ROOT / "tests/fixtures/hello-x86_64.exe"
    example = ROOT / "examples/executable-inspection.hello-x86_64.json"
    try:
        fixture_bytes = fixture.read_bytes()
        report = json.loads(example.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"PE inspection fixture: {error}"]

    digest = "sha256:" + hashlib.sha256(fixture_bytes).hexdigest()
    errors: list[str] = []
    if report.get("fileDigest") != digest:
        errors.append("PE inspection example digest does not match the fixture")
    if report.get("fileSizeBytes") != len(fixture_bytes):
        errors.append("PE inspection example size does not match the fixture")
    if report.get("schemaVersion") != "1":
        errors.append("PE inspection example must use Schema v1")
    imports = report.get("importLibraries")
    if not isinstance(imports, list) or not all(
        isinstance(item, str) for item in imports
    ):
        errors.append("PE inspection imports must be a string array")
    elif imports != sorted(set(imports)):
        errors.append("PE inspection imports must be canonical, sorted and unique")
    return errors


def main() -> int:
    errors = (
        validate_macwin_asset_migration()
        + validate_json()
        + validate_workspace_members()
        + validate_markdown_links()
        + validate_no_developer_paths()
        + validate_pe_inspection_fixture()
    )
    if errors:
        print("repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("repository contracts are internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
