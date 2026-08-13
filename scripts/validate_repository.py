#!/usr/bin/env python3
"""Validate repository-local contracts without third-party dependencies."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


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


def _scan_developer_paths(binding: object | None) -> list[str]:
    errors: list[str] = []
    forbidden = ("/Users/a1-6/", "/home/a1-6/")
    for path in sorted(ROOT.rglob("*")):
        if binding is not None and binding.contains(path):
            binding.verify_path(path)
            continue
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for value in forbidden:
            if value in content:
                errors.append(f"{path.relative_to(ROOT)}: contains developer path {value}")
    return errors


def validate_no_developer_paths() -> list[str]:
    binding, errors = _validated_macwin_source_pack_binding()
    if binding is None:
        return [*errors, *_scan_developer_paths(None)]
    try:
        scanned_errors = _scan_developer_paths(binding)
        binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return ["Mac-Win source pack validation failed", *_scan_developer_paths(None)]
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
