#!/usr/bin/env python3
"""Validate repository-local contracts without third-party dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_MEMBER = re.compile(r'^\s*"([^"]+)"[,]?\s*$')
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


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


def validate_no_developer_paths() -> list[str]:
    errors: list[str] = []
    forbidden = ("/Users/a1-6/", "/home/a1-6/")
    for path in sorted(ROOT.rglob("*")):
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
        validate_json()
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
