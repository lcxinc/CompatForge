#!/usr/bin/env python3
"""Pure deterministic conversion model for the frozen Mac-Win source pack."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import types
from typing import NoReturn


sys.dont_write_bytecode = True

ROOT = Path(os.path.abspath(__file__)).parent.parent
SOURCE_PACK_RELATIVE = PurePosixPath("migration/macwin/source")

APPROVED_REPOSITORY = "a1112/Mac-Win"
APPROVED_SOURCE_TAG = "mw-migration-baseline-db12d5e"
APPROVED_SOURCE_TAG_OBJECT = "9f10d003382ce7ffbb269376c03477e17516302f"
APPROVED_SOURCE_COMMIT = "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527"
APPROVED_INVENTORY_COMMIT = "97f8423094d25325d8f864eb6f49a9e8628dbb93"

EXPECTED_CATEGORY_COUNTS = (
    ("bottle-schema", 4),
    ("catalog", 19),
    ("fixtures", 30),
    ("patches", 11),
    ("probes", 26),
)
EXPECTED_OWNERS = {
    "bottle-schema": "compatforge/bottle-schema",
    "catalog": "compatforge/catalog",
    "fixtures": "compatforge/probes",
    "patches": "compatforge/patches",
    "probes": "compatforge/probes",
}
EXPECTED_KINDS = {
    "bottle-schema": "bottle-schema",
    "catalog": "catalog-record",
    "fixtures": "test-fixture",
    "patches": "source-patch",
    "probes": "probe",
}

CATALOG_ROOT = (
    "MacWinManager/Sources/MacWinManagerApp/Resources/Catalog"
)
CATALOG_INDEX_PATH = f"{CATALOG_ROOT}/catalog.index.json"
CATALOG_SIGNATURE_PATH = f"{CATALOG_ROOT}/catalog.signature.json"
CATALOG_RECIPE_PREFIX = f"{CATALOG_ROOT}/recipes/"

QUARANTINE_REASONS = frozenset(
    {
        "absolute-path",
        "missing-digest",
        "missing-license",
        "missing-provenance",
        "mutable-local-installation",
        "unresolved-environment-path",
        "unresolved-external-reference",
        "unsupported-behavior",
        "unsupported-schema",
    }
)
STATUSES = frozenset({"converted", "deferred", "quarantined"})
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")


class ConversionError(ValueError):
    """A stable, non-reflective conversion-model failure."""


def _fail(message: str) -> NoReturn:
    raise ConversionError(message)


def _load_trusted_tool(name: str):
    """Load one repository-owned migration tool through a bound regular leaf."""

    descriptor: int | None = None
    path = Path(os.path.abspath(__file__)).with_name(name)
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_reparse_tag", 0)
            or before.st_nlink != 1
            or before.st_size > 1024 * 1024
        ):
            raise OSError
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_nlink,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink)
            != identity[:4]
        ):
            raise OSError
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, 1024 * 1024 + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024:
                raise OSError
            chunks.append(chunk)
        final = os.fstat(descriptor)
        if (
            final.st_dev,
            final.st_ino,
            final.st_size,
            final.st_nlink,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_nlink,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise OSError
        after = path.lstat()
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_nlink,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != identity:
            raise OSError

        module_name = f"_compatforge_{name.removesuffix('.py')}"
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = ""
        sys.modules[module_name] = module
        try:
            exec(compile(b"".join(chunks), str(path), "exec"), module.__dict__)
        finally:
            sys.modules.pop(module_name, None)
        return module
    except Exception:
        raise RuntimeError("migration dependency could not be loaded") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


_COMMON = _load_trusted_tool("macwin_asset_common.py")
_SOURCE_PACK = _load_trusted_tool("import_macwin_source_pack.py")


@dataclass(frozen=True, slots=True)
class SourceAsset:
    category: str
    source_path: str
    source_commit: str
    git_blob_oid: str
    sha256: str
    byte_size: int
    git_mode: str
    kind: str
    license_status: str
    provenance_status: str
    intended_owner: str
    external_refs: tuple[str, ...]
    development_dependencies: tuple[str, ...]
    object_path: str
    raw: bytes


@dataclass(frozen=True, slots=True)
class SourcePack:
    repository: str
    source_tag: str
    source_tag_object: str
    source_commit: str
    inventory_commit: str
    digest_algorithm: str
    category_counts: tuple[tuple[str, int], ...]
    assets: tuple[SourceAsset, ...]


@dataclass(frozen=True, slots=True)
class ConversionRecord:
    source_repository: str
    source_commit: str
    source_path: str
    source_sha256: str
    source_kind: str
    category: str
    intended_owner: str
    output_kind: str
    status: str
    action: str
    target_issue: str | None
    reason: str | None
    evidence_locators: tuple[str, ...]
    release_condition: str | None


@dataclass(frozen=True, slots=True)
class ConversionResult:
    source_pack: SourcePack
    records: tuple[ConversionRecord, ...]


def _load_authenticated_asset_bytes(binding, source_root: Path, record: dict[str, object]) -> bytes:
    path = source_root / PurePosixPath(record["objectPath"])
    raw = binding.verify_path(path)
    if (
        type(raw) is not bytes
        or len(raw) != record["byteSize"]
        or hashlib.sha256(raw).hexdigest() != record["sha256"]
        or _git_blob_oid(raw) != record["gitBlobOid"]
    ):
        _fail("source asset content is invalid")
    return raw


def load_source_pack(repository_root: Path) -> SourcePack:
    """Load and authenticate the complete committed offline source pack."""

    if not isinstance(repository_root, Path):
        _fail("repository root is invalid")
    source_root = repository_root.absolute() / SOURCE_PACK_RELATIVE
    try:
        with _SOURCE_PACK.bind_source_pack(source_root) as binding:
            manifest = binding.manifest
            assets: list[SourceAsset] = []
            for raw_record in manifest["assets"]:
                raw = _load_authenticated_asset_bytes(binding, source_root, raw_record)
                assets.append(
                    SourceAsset(
                        category=raw_record["category"],
                        source_path=raw_record["sourcePath"],
                        source_commit=raw_record["sourceCommit"],
                        git_blob_oid=raw_record["gitBlobOid"],
                        sha256=raw_record["sha256"],
                        byte_size=raw_record["byteSize"],
                        git_mode=raw_record["gitMode"],
                        kind=raw_record["kind"],
                        license_status=raw_record["license"]["status"],
                        provenance_status=raw_record["provenance"]["status"],
                        intended_owner=raw_record["intendedOwner"],
                        external_refs=tuple(raw_record["externalRefs"]),
                        development_dependencies=tuple(
                            raw_record["developmentDependencies"]
                        ),
                        object_path=raw_record["objectPath"],
                        raw=raw,
                    )
                )
    except _SOURCE_PACK.SourcePackError:
        _fail("source pack is invalid")
    source_pack = SourcePack(
        repository=manifest["repository"],
        source_tag=manifest["sourceTag"],
        source_tag_object=manifest["sourceTagObject"],
        source_commit=manifest["sourceCommit"],
        inventory_commit=manifest["inventoryCommit"],
        digest_algorithm=manifest["digestAlgorithm"],
        category_counts=EXPECTED_CATEGORY_COUNTS,
        assets=tuple(assets),
    )
    _validate_source_pack_model(source_pack)
    return source_pack


def classify_source_pack(source_pack: SourcePack) -> ConversionResult:
    """Classify every authenticated identity into one closed migration result."""

    _validate_source_pack_model(source_pack)
    recipe_paths = _validate_catalog_boundary(source_pack)
    records = tuple(
        _classify_asset(source_pack, asset, recipe_paths) for asset in source_pack.assets
    )
    result = ConversionResult(source_pack=source_pack, records=records)
    _validate_conversion_result(result)
    return result


def build_conversion(repository_root: Path) -> ConversionResult:
    """Build the pure in-memory conversion ledger from committed source bytes."""

    return classify_source_pack(load_source_pack(repository_root))


def render_documents(result: ConversionResult) -> dict[str, bytes]:
    """Render the closed Task 4 ledger in memory without writing output files."""

    _validate_conversion_result(result)
    source_pack = result.source_pack
    document = {
        "schemaVersion": "1",
        "source": {
            "repository": source_pack.repository,
            "sourceTag": source_pack.source_tag,
            "sourceTagObject": source_pack.source_tag_object,
            "sourceCommit": source_pack.source_commit,
            "inventoryCommit": source_pack.inventory_commit,
        },
        "assetCount": len(result.records),
        "categoryCounts": {
            category: count for category, count in source_pack.category_counts
        },
        "records": [_record_document(record) for record in result.records],
    }
    try:
        raw = _COMMON.canonical_json_bytes(document)
    except _COMMON.MigrationError:
        _fail("conversion ledger cannot be rendered")
    return {"conversion-ledger.json": raw}


def _validate_source_pack_model(source_pack: SourcePack) -> None:
    if type(source_pack) is not SourcePack:
        _fail("source pack model is invalid")
    if (
        source_pack.repository != APPROVED_REPOSITORY
        or source_pack.source_tag != APPROVED_SOURCE_TAG
        or source_pack.source_tag_object != APPROVED_SOURCE_TAG_OBJECT
        or source_pack.source_commit != APPROVED_SOURCE_COMMIT
        or source_pack.inventory_commit != APPROVED_INVENTORY_COMMIT
        or source_pack.digest_algorithm != "sha256"
        or source_pack.category_counts != EXPECTED_CATEGORY_COUNTS
        or type(source_pack.assets) is not tuple
        or len(source_pack.assets) != 90
    ):
        _fail("source pack model identity is invalid")

    paths: list[str] = []
    folded_paths: set[str] = set()
    digests: set[str] = set()
    counts = {category: 0 for category, _count in EXPECTED_CATEGORY_COUNTS}
    executable_count = 0
    for asset in source_pack.assets:
        if type(asset) is not SourceAsset or asset.category not in counts:
            _fail("source asset model is invalid")
        try:
            _COMMON.require_relative_posix_path(asset.source_path)
            _COMMON.require_relative_posix_path(asset.object_path)
        except _COMMON.MigrationError:
            _fail("source asset path is invalid")
        folded = asset.source_path.casefold()
        if asset.source_path in paths or folded in folded_paths:
            _fail("source asset identity is duplicated")
        paths.append(asset.source_path)
        folded_paths.add(folded)
        counts[asset.category] += 1
        if (
            asset.source_commit != source_pack.source_commit
            or _HEX_40.fullmatch(asset.git_blob_oid) is None
            or _HEX_64.fullmatch(asset.sha256) is None
            or asset.sha256 in digests
            or type(asset.byte_size) is not int
            or asset.byte_size < 0
            or asset.byte_size > _SOURCE_PACK.MAX_SOURCE_OBJECT_BYTES
            or asset.git_mode not in {"100644", "100755"}
            or asset.kind != EXPECTED_KINDS[asset.category]
            or asset.license_status != "unresolved"
            or asset.provenance_status != "unresolved"
            or asset.intended_owner != EXPECTED_OWNERS[asset.category]
            or type(asset.external_refs) is not tuple
            or type(asset.development_dependencies) is not tuple
            or len(asset.external_refs) > 512
            or len(asset.development_dependencies) > 512
            or len(set(asset.external_refs)) != len(asset.external_refs)
            or len(set(asset.development_dependencies))
            != len(asset.development_dependencies)
            or any(type(value) is not str or not value or len(value) > 4096 for value in asset.external_refs)
            or any(
                type(value) is not str or not value or len(value) > 4096
                for value in asset.development_dependencies
            )
            or asset.object_path
            != f"objects/sha256/{asset.sha256[:2]}/{asset.sha256[2:]}"
            or type(asset.raw) is not bytes
            or len(asset.raw) != asset.byte_size
            or hashlib.sha256(asset.raw).hexdigest() != asset.sha256
            or _git_blob_oid(asset.raw) != asset.git_blob_oid
        ):
            _fail("source asset model fields are invalid")
        digests.add(asset.sha256)
        if asset.git_mode == "100755":
            executable_count += 1
            if asset.category != "probes":
                _fail("source executable category is invalid")
    if paths != sorted(paths, key=lambda value: value.encode("ascii")):
        _fail("source assets are not ordered")
    if tuple(sorted(counts.items())) != EXPECTED_CATEGORY_COUNTS or executable_count != 11:
        _fail("source asset category coverage is invalid")


def _validate_catalog_boundary(source_pack: SourcePack) -> frozenset[str]:
    assets = {asset.source_path: asset for asset in source_pack.assets}
    if CATALOG_INDEX_PATH not in assets or CATALOG_SIGNATURE_PATH not in assets:
        _fail("catalog boundary is incomplete")
    catalog_paths = {
        asset.source_path for asset in source_pack.assets if asset.category == "catalog"
    }
    recipe_paths = catalog_paths - {CATALOG_INDEX_PATH, CATALOG_SIGNATURE_PATH}
    if len(recipe_paths) != 17 or any(
        not path.startswith(CATALOG_RECIPE_PREFIX)
        or "/" in path[len(CATALOG_RECIPE_PREFIX) :]
        or not path.endswith(".json")
        for path in recipe_paths
    ):
        _fail("catalog candidate identity is ambiguous")

    index = _parse_json_object(assets[CATALOG_INDEX_PATH])
    if set(index) != {"expiresAt", "generatedAt", "recipes"}:
        _fail("catalog index fields are unsupported")
    entries = index["recipes"]
    if type(entries) is not list or len(entries) != 17:
        _fail("catalog candidate coverage is invalid")
    indexed_paths: set[str] = set()
    indexed_ids: set[str] = set()
    for raw_entry in entries:
        if type(raw_entry) is not dict or set(raw_entry) != {"file", "id", "name", "sha256"}:
            _fail("catalog candidate entry is invalid")
        relative = raw_entry["file"]
        identifier = raw_entry["id"]
        name = raw_entry["name"]
        digest = raw_entry["sha256"]
        if (
            type(relative) is not str
            or not relative.startswith("recipes/")
            or "/" in relative[len("recipes/") :]
            or not relative.endswith(".json")
            or type(identifier) is not str
            or not identifier
            or type(name) is not str
            or not name
            or type(digest) is not str
            or _HEX_64.fullmatch(digest) is None
        ):
            _fail("catalog candidate entry is invalid")
        try:
            _COMMON.require_relative_posix_path(relative)
        except _COMMON.MigrationError:
            _fail("catalog candidate path is invalid")
        path = f"{CATALOG_ROOT}/{relative}"
        if path in indexed_paths or identifier in indexed_ids or path not in recipe_paths:
            _fail("catalog candidate identity is duplicated")
        recipe = _parse_json_object(assets[path])
        if (
            recipe.get("id") != identifier
            or recipe.get("name") != name
            or identifier != relative.removeprefix("recipes/").removesuffix(".json")
            or assets[path].sha256 != digest
        ):
            _fail("catalog candidate identity does not match its source")
        indexed_paths.add(path)
        indexed_ids.add(identifier)
    if indexed_paths != recipe_paths:
        _fail("catalog candidate coverage is incomplete")

    signature = _parse_json_object(assets[CATALOG_SIGNATURE_PATH])
    if (
        set(signature) != {"algorithm", "keyId", "signatureBase64"}
        or signature.get("algorithm") != "p256-sha256-der"
        or any(type(signature.get(field)) is not str or not signature[field] for field in signature)
    ):
        _fail("catalog signature boundary is invalid")
    return frozenset(recipe_paths)


def _parse_json_object(asset: SourceAsset) -> dict[str, object]:
    try:
        value = _COMMON.parse_json_bytes(
            asset.raw,
            label="Mac-Win source asset",
            max_bytes=max(1, asset.byte_size),
        )
    except _COMMON.MigrationError:
        _fail("catalog source JSON is invalid")
    if type(value) is not dict:
        _fail("catalog source JSON is not an object")
    return value


def _classify_asset(
    source_pack: SourcePack,
    asset: SourceAsset,
    recipe_paths: frozenset[str],
) -> ConversionRecord:
    base = {
        "source_repository": source_pack.repository,
        "source_commit": asset.source_commit,
        "source_path": asset.source_path,
        "source_sha256": asset.sha256,
        "source_kind": asset.kind,
        "category": asset.category,
        "intended_owner": asset.intended_owner,
    }
    if asset.source_path in {CATALOG_INDEX_PATH, CATALOG_SIGNATURE_PATH}:
        if asset.category != "catalog":
            _fail("catalog boundary category is invalid")
        return ConversionRecord(
            **base,
            output_kind="catalog-boundary",
            status="converted",
            action="retain-catalog-boundary",
            target_issue=None,
            reason=None,
            evidence_locators=(),
            release_condition=None,
        )
    if asset.source_path in recipe_paths:
        return _classify_publishable(base, asset, "recipe", "convert-recipe")
    if asset.category == "probes":
        return _classify_publishable(
            base, asset, "portable-probe", "export-portable-probe"
        )
    if asset.category == "fixtures":
        return _classify_publishable(
            base, asset, "portable-fixture", "export-portable-fixture"
        )
    if asset.category == "patches":
        return ConversionRecord(
            **base,
            output_kind="patch-mapping",
            status="deferred",
            action="defer-patch",
            target_issue="MW-ASSET-002",
            reason=None,
            evidence_locators=(),
            release_condition=None,
        )
    if asset.category == "bottle-schema":
        return ConversionRecord(
            **base,
            output_kind="bottle-schema-mapping",
            status="deferred",
            action="defer-bottle-schema",
            target_issue="MW-ASSET-003",
            reason=None,
            evidence_locators=(),
            release_condition=None,
        )
    _fail("source asset classification is unsupported")


def _classify_publishable(
    base: dict[str, str],
    asset: SourceAsset,
    output_kind: str,
    converted_action: str,
) -> ConversionRecord:
    if asset.license_status == "unresolved":
        return ConversionRecord(
            **base,
            output_kind=output_kind,
            status="quarantined",
            action="quarantine",
            target_issue=None,
            reason="missing-license",
            evidence_locators=(f"{asset.source_path}#license",),
            release_condition=(
                "Record a reviewed source license and regenerate the migration."
            ),
        )
    if asset.provenance_status == "unresolved":
        return ConversionRecord(
            **base,
            output_kind=output_kind,
            status="quarantined",
            action="quarantine",
            target_issue=None,
            reason="missing-provenance",
            evidence_locators=(f"{asset.source_path}#provenance",),
            release_condition=(
                "Record reviewed source provenance and regenerate the migration."
            ),
        )
    return ConversionRecord(
        **base,
        output_kind=output_kind,
        status="converted",
        action=converted_action,
        target_issue=None,
        reason=None,
        evidence_locators=(),
        release_condition=None,
    )


def _validate_conversion_result(result: ConversionResult) -> None:
    if type(result) is not ConversionResult or type(result.records) is not tuple:
        _fail("conversion result is invalid")
    _validate_source_pack_model(result.source_pack)
    if len(result.records) != 90 or any(
        type(record) is not ConversionRecord for record in result.records
    ):
        _fail("conversion result coverage is invalid")
    paths = tuple(record.source_path for record in result.records)
    if (
        len(set(paths)) != 90
        or paths != tuple(sorted(paths, key=lambda value: value.encode("ascii")))
        or paths != tuple(asset.source_path for asset in result.source_pack.assets)
    ):
        _fail("conversion result identity set is invalid")
    recipe_paths = _validate_catalog_boundary(result.source_pack)
    expected = tuple(
        _classify_asset(result.source_pack, asset, recipe_paths)
        for asset in result.source_pack.assets
    )
    if result.records != expected:
        _fail("conversion result record is invalid")
    for record in result.records:
        if (
            record.status not in STATUSES
            or (record.reason is not None and record.reason not in QUARANTINE_REASONS)
            or type(record.evidence_locators) is not tuple
            or len(set(record.evidence_locators)) != len(record.evidence_locators)
            or record.evidence_locators
            != tuple(sorted(record.evidence_locators, key=lambda value: value.encode("utf-8")))
        ):
            _fail("conversion result vocabulary is invalid")


def _record_document(record: ConversionRecord) -> dict[str, object]:
    return {
        "sourceRepository": record.source_repository,
        "sourceCommit": record.source_commit,
        "sourcePath": record.source_path,
        "sourceSha256": record.source_sha256,
        "sourceKind": record.source_kind,
        "category": record.category,
        "intendedOwner": record.intended_owner,
        "outputKind": record.output_kind,
        "status": record.status,
        "action": record.action,
        "targetIssue": record.target_issue,
        "reason": record.reason,
        "evidenceLocators": list(record.evidence_locators),
        "releaseCondition": record.release_condition,
    }


def _git_blob_oid(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def main(arguments: tuple[str, ...]) -> int:
    """Run the temporary read-only Task 4 repository validation boundary."""

    if arguments != ("--check",):
        return 2
    try:
        render_documents(build_conversion(ROOT))
    except ConversionError:
        print("Mac-Win asset conversion failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
