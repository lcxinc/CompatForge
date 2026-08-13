#!/usr/bin/env python3
"""Pure deterministic conversion model for the frozen Mac-Win source pack."""

from __future__ import annotations

import hashlib
import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import threading
import types
from typing import NoReturn
from urllib.parse import unquote_to_bytes, urlsplit


if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import msvcrt


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
MAX_EVIDENCE_LOCATORS = 512
APPROVED_PORTABLE_ASSET_TABLE_SHA256 = (
    "9db4bac2e7ddb3f542e655f5f9be1aed9d265ecd6dfa44cd563ef2b1c7eddf54"
)
STATUSES = frozenset({"converted", "deferred", "quarantined"})
RECIPE_REASON_PRECEDENCE = (
    "missing-license",
    "missing-provenance",
    "absolute-path",
    "mutable-local-installation",
    "missing-digest",
    "unresolved-external-reference",
    "unresolved-environment-path",
    "unsupported-schema",
    "unsupported-behavior",
)
RECIPE_TOP_LEVEL_FIELDS = frozenset(
    {
        "bottleTemplate",
        "category",
        "compatibilityRating",
        "engineRequirements",
        "env",
        "id",
        "installer",
        "launchers",
        "name",
        "postInstall",
        "publisher",
        "warnings",
    }
)
REVIEWED_RECIPE_TOP_LEVEL_FIELDS = RECIPE_TOP_LEVEL_FIELDS | {"license", "tests"}
RECIPE_TEST_FIELDS = frozenset({"expected", "id", "kind", "timeoutSeconds"})
RECIPE_TEST_KINDS = frozenset(
    {"manual", "process-exit", "screenshot", "script", "window-visible"}
)
RECIPE_RELEASE_CONDITIONS = {
    "absolute-path": "Replace host-absolute locators with reviewed portable references and regenerate the migration.",
    "missing-digest": "Record the reviewed installer SHA-256 and regenerate the migration.",
    "missing-license": "Record a reviewed source license and regenerate the migration.",
    "missing-provenance": "Record reviewed source provenance and regenerate the migration.",
    "mutable-local-installation": "Replace the mutable local installation with a pinned portable source and regenerate the migration.",
    "unresolved-environment-path": "Close environment path dependencies over portable assets and regenerate the migration.",
    "unresolved-external-reference": "Close the reviewed external dependency over a pinned source and regenerate the migration.",
    "unsupported-behavior": "Remove or review unsupported source behavior and regenerate the migration.",
    "unsupported-schema": "Publish complete reviewed Recipe fields and regenerate the migration.",
}
PORTABLE_ASSET_TABLE = {
    "MacWinManager/Tools/build-native-ui-probe.sh": ("macwinmanager-tools-build-native-ui-probe-sh", "shell", "text/x-shellscript"),
    "MacWinManager/Tools/native-ui-probe.c": ("macwinmanager-tools-native-ui-probe-c", "source", "text/x-c"),
    "MacWinManager/Tools/native-ui-probe.manifest": ("macwinmanager-tools-native-ui-probe-manifest", "data", "application/manifest+xml"),
    "MacWinManager/Tools/native-ui-probe.rc": ("macwinmanager-tools-native-ui-probe-rc", "data", "text/plain"),
    "scripts/analyze-window-image.py": ("scripts-analyze-window-image-py", "source", "text/x-python"),
    "scripts/bootstrap-jasp-conan.sh": ("scripts-bootstrap-jasp-conan-sh", "shell", "text/x-shellscript"),
    "scripts/build-game-dll-coverage.sh": ("scripts-build-game-dll-coverage-sh", "shell", "text/x-shellscript"),
    "scripts/build-rosettax87.sh": ("scripts-build-rosettax87-sh", "shell", "text/x-shellscript"),
    "scripts/capture-macos-region.swift": ("scripts-capture-macos-region-swift", "source", "text/x-swift"),
    "scripts/capture-macos-window.swift": ("scripts-capture-macos-window-swift", "source", "text/x-swift"),
    "scripts/configure-jasp-compat-build.sh": ("scripts-configure-jasp-compat-build-sh", "shell", "text/x-shellscript"),
    "scripts/download-software-samples.sh": ("scripts-download-software-samples-sh", "shell", "text/x-shellscript"),
    "scripts/drag-pointer.swift": ("scripts-drag-pointer-swift", "source", "text/x-swift"),
    "scripts/dwsim-gdiplus-image-probe.cs": ("scripts-dwsim-gdiplus-image-probe-cs", "source", "text/x-csharp"),
    "scripts/find-macos-window.swift": ("scripts-find-macos-window-swift", "source", "text/x-swift"),
    "scripts/fixtures/SwingFontProbe.java": ("scripts-fixtures-swingfontprobe-java", "source", "text/x-java-source"),
    "scripts/fixtures/beekeeper-sqlite-smoke.js": ("scripts-fixtures-beekeeper-sqlite-smoke-js", "source", "text/javascript"),
    "scripts/fixtures/brave-browser-smoke.html": ("scripts-fixtures-brave-browser-smoke-html", "data", "text/html"),
    "scripts/fixtures/dbeaver-jdbc-smoke.java": ("scripts-fixtures-dbeaver-jdbc-smoke-java", "source", "text/x-java-source"),
    "scripts/fixtures/firefox-browser-smoke.py": ("scripts-fixtures-firefox-browser-smoke-py", "source", "text/x-python"),
    "scripts/fixtures/freeoffice-automation-probe.c": ("scripts-fixtures-freeoffice-automation-probe-c", "source", "text/x-c"),
    "scripts/fixtures/freeoffice-bootstrap.c": ("scripts-fixtures-freeoffice-bootstrap-c", "source", "text/x-c"),
    "scripts/fixtures/freeoffice-typeinfo-probe.c": ("scripts-fixtures-freeoffice-typeinfo-probe-c", "source", "text/x-c"),
    "scripts/fixtures/freeoffice-ui-probe.c": ("scripts-fixtures-freeoffice-ui-probe-c", "source", "text/x-c"),
    "scripts/fixtures/godot-vulkan-smoke/main.gd": ("scripts-fixtures-godot-vulkan-smoke-main-gd", "data", "text/plain"),
    "scripts/fixtures/godot-vulkan-smoke/main.tscn": ("scripts-fixtures-godot-vulkan-smoke-main-tscn", "data", "text/plain"),
    "scripts/fixtures/godot-vulkan-smoke/project.godot": ("scripts-fixtures-godot-vulkan-smoke-project-godot", "data", "text/plain"),
    "scripts/fixtures/inkscape-smoke.svg": ("scripts-fixtures-inkscape-smoke-svg", "data", "image/svg+xml"),
    "scripts/fixtures/jabref-smoke.bib": ("scripts-fixtures-jabref-smoke-bib", "data", "application/x-bibtex"),
    "scripts/fixtures/libreoffice-smoke.html": ("scripts-fixtures-libreoffice-smoke-html", "data", "text/html"),
    "scripts/fixtures/meshlab-cube.obj": ("scripts-fixtures-meshlab-cube-obj", "data", "text/plain"),
    "scripts/fixtures/openplc-smoke-main.cpp": ("scripts-fixtures-openplc-smoke-main-cpp", "source", "text/x-c++"),
    "scripts/fixtures/openplc-smoke.xml": ("scripts-fixtures-openplc-smoke-xml", "data", "application/xml"),
    "scripts/fixtures/pdfarranger-page-one.txt": ("scripts-fixtures-pdfarranger-page-one-txt", "data", "text/plain"),
    "scripts/fixtures/pdfarranger-page-two.txt": ("scripts-fixtures-pdfarranger-page-two-txt", "data", "text/plain"),
    "scripts/fixtures/pdfarranger-qpdf-probe.c": ("scripts-fixtures-pdfarranger-qpdf-probe-c", "source", "text/x-c"),
    "scripts/fixtures/pgadmin-backend-smoke.py": ("scripts-fixtures-pgadmin-backend-smoke-py", "source", "text/x-python"),
    "scripts/fixtures/projectlibre-mpxj-smoke.java": ("scripts-fixtures-projectlibre-mpxj-smoke-java", "source", "text/x-java-source"),
    "scripts/fixtures/qelectrotech-smoke.qet": ("scripts-fixtures-qelectrotech-smoke-qet", "data", "application/xml"),
    "scripts/fixtures/r-statistics-smoke.R": ("scripts-fixtures-r-statistics-smoke-r", "source", "text/x-r-source"),
    "scripts/fixtures/special-folder-probe.c": ("scripts-fixtures-special-folder-probe-c", "source", "text/x-c"),
    "scripts/fixtures/sqlitebrowser-probe.c": ("scripts-fixtures-sqlitebrowser-probe-c", "source", "text/x-c"),
    "scripts/fixtures/wow64-debug-exception.c": ("scripts-fixtures-wow64-debug-exception-c", "source", "text/x-c"),
    "scripts/fixtures/wow64-read-memory.c": ("scripts-fixtures-wow64-read-memory-c", "source", "text/x-c"),
    "scripts/fixtures/wps-smoke.rtf": ("scripts-fixtures-wps-smoke-rtf", "data", "application/rtf"),
    "scripts/inspect-chromium-page.swift": ("scripts-inspect-chromium-page-swift", "source", "text/x-swift"),
    "scripts/macos-session-state.swift": ("scripts-macos-session-state-swift", "source", "text/x-swift"),
    "scripts/prepare-jasp-compat-source.sh": ("scripts-prepare-jasp-compat-source-sh", "shell", "text/x-shellscript"),
    "scripts/repair-jasp-conan-cache.sh": ("scripts-repair-jasp-conan-cache-sh", "shell", "text/x-shellscript"),
    "scripts/repair-lenovo-app-store-page.swift": ("scripts-repair-lenovo-app-store-page-swift", "source", "text/x-swift"),
    "scripts/run-powertoys-quick-access-probe.sh": ("scripts-run-powertoys-quick-access-probe-sh", "shell", "text/x-shellscript"),
    "scripts/run-software-smoke.sh": ("scripts-run-software-smoke-sh", "shell", "text/x-shellscript"),
    "scripts/validate-chromium-page-report.py": ("scripts-validate-chromium-page-report-py", "source", "text/x-python"),
    "scripts/validate-pgadmin-page-report.py": ("scripts-validate-pgadmin-page-report-py", "source", "text/x-python"),
    "scripts/visual-acceptance-macwin.sh": ("scripts-visual-acceptance-macwin-sh", "shell", "text/x-shellscript"),
    "scripts/wic-codecs-minimal.reg": ("scripts-wic-codecs-minimal-reg", "registry", "text/x-ms-regedit"),
}
PORTABLE_REFERENCE_TABLE = {path: () for path in PORTABLE_ASSET_TABLE}
_PORTABLE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{1,127}\Z")
_PORTABLE_MEDIA_TYPE = re.compile(
    r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+\Z"
)
_PORTABLE_KINDS = {
    "probes": frozenset({"shell", "registry", "source", "binary", "data", "other"}),
    "fixtures": frozenset({"registry", "source", "binary", "data", "other"}),
}
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_LOADER_IDENTITY = object()


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

        module_name = (
            f"_compatforge_{name.removesuffix('.py')}_{id(_LOADER_IDENTITY):x}"
        )
        if module_name in sys.modules:
            raise RuntimeError
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = ""
        sys.modules[module_name] = module
        try:
            exec(compile(b"".join(chunks), str(path), "exec"), module.__dict__)
        finally:
            if sys.modules.get(module_name) is module:
                sys.modules.pop(module_name, None)
        return module
    except BaseException:
        raise RuntimeError("migration dependency could not be loaded") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


_COMMON = None
_SOURCE_PACK = None
_DEPENDENCY_LOCK = threading.RLock()


def _bootstrap_dependencies() -> None:
    """Load both trusted siblings atomically on first library or CLI use."""

    global _COMMON, _SOURCE_PACK
    if _COMMON is not None and _SOURCE_PACK is not None:
        return
    with _DEPENDENCY_LOCK:
        if _COMMON is not None and _SOURCE_PACK is not None:
            return
        try:
            common = _load_trusted_tool("macwin_asset_common.py")
            source_pack = _load_trusted_tool("import_macwin_source_pack.py")
        except RuntimeError:
            _fail("migration dependencies are unavailable")
        _COMMON, _SOURCE_PACK = common, source_pack


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


@dataclass(frozen=True, slots=True)
class RecipeFinding:
    reason: str
    evidence_locator: str


@dataclass(frozen=True, slots=True)
class _SourceTreeBinding:
    root_identity: tuple[int, int, int, int, int, int]
    index_identity: tuple[int, int, int, int, int, int]
    directories: tuple[tuple[str, tuple[int, int, int, int, int, int]], ...]
    leaves: tuple[tuple[str, tuple[int, int, int, int, int, int]], ...]


@dataclass(frozen=True, slots=True)
class _HeldSourceLeaf:
    path: Path
    path_identity: tuple[int, int, int, int, int, int]
    handle_identity: tuple[int, int, int, int, int, int]
    descriptor: int
    raw: bytes


if os.name == "nt":
    _GENERIC_READ = 0x80000000
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
    _FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _FileAttributeTagInfo(ctypes.Structure):
        _fields_ = (
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        )

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CREATE_FILE = _KERNEL32.CreateFileW
    _CREATE_FILE.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _CREATE_FILE.restype = wintypes.HANDLE
    _GET_FILE_INFORMATION = _KERNEL32.GetFileInformationByHandleEx
    _GET_FILE_INFORMATION.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    _GET_FILE_INFORMATION.restype = wintypes.BOOL
    _CLOSE_HANDLE = _KERNEL32.CloseHandle
    _CLOSE_HANDLE.argtypes = (wintypes.HANDLE,)
    _CLOSE_HANDLE.restype = wintypes.BOOL


def _open_source_leaf_descriptor(path: Path) -> int:
    if os.name != "nt":
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            return os.open(path, flags)
        except OSError:
            _fail("source leaf could not be opened safely")

    handle = _CREATE_FILE(
        str(path),
        _GENERIC_READ | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        _fail("source leaf could not be opened safely")
    transferred = False
    try:
        attributes = _FileAttributeTagInfo()
        if not _GET_FILE_INFORMATION(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(attributes),
            ctypes.sizeof(attributes),
        ):
            _fail("source leaf handle could not be authenticated")
        if attributes.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            _fail("source leaf handle is linked")
        try:
            descriptor = msvcrt.open_osfhandle(
                handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        except OSError:
            _fail("source leaf handle could not be bound")
        transferred = True
        return descriptor
    finally:
        if not transferred:
            _CLOSE_HANDLE(handle)


def _read_and_hold_regular_file(
    path: Path,
    maximum: int,
    *,
    expected_identity: tuple[int, int, int, int, int, int] | None = None,
) -> _HeldSourceLeaf:
    """Read one regular leaf once and retain its authenticated open handle."""

    descriptor: int | None = None
    try:
        before = _SOURCE_PACK._path_metadata(path)
        identity = _SOURCE_PACK._file_identity(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > maximum
            or (expected_identity is not None and identity != expected_identity)
        ):
            _fail("source leaf metadata is invalid")
        descriptor = _open_source_leaf_descriptor(path)
        opened = os.fstat(descriptor)
        handle_identity = _SOURCE_PACK._file_identity(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or handle_identity[:4] != identity[:4]
        ):
            _fail("source leaf handle identity changed")

        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(
                    descriptor,
                    min(1024 * 1024, maximum + 1 - total),
                )
            except OSError:
                _fail("source leaf could not be read")
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _fail("source leaf exceeds the byte limit")
            chunks.append(chunk)
        raw = b"".join(chunks)
        final = os.fstat(descriptor)
        if (
            _SOURCE_PACK._file_identity(final) != handle_identity
            or len(raw) != before.st_size
            or _SOURCE_PACK._file_identity(
                _SOURCE_PACK._path_metadata(path)
            )
            != identity
        ):
            _fail("source leaf changed while it was read")
        held = _HeldSourceLeaf(
            path.absolute(), identity, handle_identity, descriptor, raw
        )
        descriptor = None
        return held
    except OSError:
        _fail("source leaf could not be authenticated")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_held_source_leaf(leaf: _HeldSourceLeaf) -> None:
    try:
        descriptor_metadata = os.fstat(leaf.descriptor)
        path_metadata = _SOURCE_PACK._path_metadata(leaf.path)
    except OSError:
        _fail("source leaf binding could not be finalized")
    if (
        not stat.S_ISREG(descriptor_metadata.st_mode)
        or descriptor_metadata.st_nlink != 1
        or _SOURCE_PACK._file_identity(descriptor_metadata) != leaf.handle_identity
        or _SOURCE_PACK._file_identity(path_metadata) != leaf.path_identity
    ):
        _fail("source leaf binding changed")


def _load_authenticated_asset(
    source_root: Path,
    record: dict[str, object],
    expected_identity: tuple[int, int, int, int, int, int],
) -> _HeldSourceLeaf:
    path = source_root / PurePosixPath(record["objectPath"])
    leaf = _read_and_hold_regular_file(
        path,
        _SOURCE_PACK.MAX_SOURCE_OBJECT_BYTES,
        expected_identity=expected_identity,
    )
    raw = leaf.raw
    if (
        len(raw) != record["byteSize"]
        or hashlib.sha256(raw).hexdigest() != record["sha256"]
        or _git_blob_oid(raw) != record["gitBlobOid"]
    ):
        os.close(leaf.descriptor)
        _fail("source asset content is invalid")
    return leaf


def load_source_pack(repository_root: Path) -> SourcePack:
    """Load and authenticate the complete committed offline source pack."""

    _bootstrap_dependencies()
    if not isinstance(repository_root, Path):
        _fail("repository root is invalid")
    source_root = repository_root.absolute() / SOURCE_PACK_RELATIVE
    held_leaves: list[_HeldSourceLeaf] = []
    try:
        _SOURCE_PACK._validate_path_chain(source_root)
        root_metadata = _SOURCE_PACK._path_metadata(source_root)
        if not stat.S_ISDIR(root_metadata.st_mode):
            _fail("source pack path is not a directory")
        root_identity = _SOURCE_PACK._file_identity(root_metadata)

        index_path = source_root / "index.json"
        index_before = _SOURCE_PACK._file_identity(
            _SOURCE_PACK._path_metadata(index_path)
        )
        index_leaf = _read_and_hold_regular_file(
            index_path,
            _SOURCE_PACK.MAX_SOURCE_INDEX_BYTES,
            expected_identity=index_before,
        )
        held_leaves.append(index_leaf)
        index_raw = index_leaf.raw
        if (
            hashlib.sha256(index_raw).hexdigest()
            != _SOURCE_PACK.APPROVED_SOURCE_INDEX_SHA256
        ):
            _fail("source pack index does not match the approved seal")
        manifest = _SOURCE_PACK._validate_manifest(
            _SOURCE_PACK._parse_json(
                index_raw, maximum=_SOURCE_PACK.MAX_SOURCE_INDEX_BYTES
            )
        )
        try:
            if _COMMON.canonical_json_bytes(manifest) != index_raw:
                _fail("source pack index is not canonical")
        except _COMMON.MigrationError:
            _fail("source pack index is not canonical")

        expected_paths = frozenset(
            record["objectPath"] for record in manifest["assets"]
        )
        tree = _bind_source_tree(source_root, expected_paths)
        if (
            tree.root_identity != root_identity
            or tree.index_identity != index_before
        ):
            _fail("source pack tree identity changed")
        leaf_identities = dict(tree.leaves)
        assets: list[SourceAsset] = []
        total = 0
        for raw_record in manifest["assets"]:
            leaf = _load_authenticated_asset(
                source_root,
                raw_record,
                leaf_identities[raw_record["objectPath"]],
            )
            held_leaves.append(leaf)
            raw = leaf.raw
            total += len(raw)
            if total > _SOURCE_PACK.MAX_TOTAL_SOURCE_BYTES:
                _fail("source pack total bytes exceed the limit")
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
        if _bind_source_tree(source_root, expected_paths) != tree:
            _fail("source pack tree identity changed")
        _SOURCE_PACK._validate_path_chain(source_root)
        for leaf in held_leaves:
            _verify_held_source_leaf(leaf)
        return source_pack
    except _SOURCE_PACK.SourcePackError:
        _fail("source pack is invalid")
    finally:
        for leaf in reversed(held_leaves):
            try:
                os.close(leaf.descriptor)
            except OSError:
                pass


def _bind_source_tree(
    source_root: Path, expected_paths: frozenset[str]
) -> _SourceTreeBinding:
    """Bind the exact source-pack tree using metadata only, never content reads."""

    if type(expected_paths) is not frozenset or len(expected_paths) != 90:
        _fail("source pack object identity set is invalid")
    expected_shards: dict[str, set[str]] = {}
    for relative in expected_paths:
        parts = PurePosixPath(relative).parts
        if (
            len(parts) != 4
            or parts[:2] != ("objects", "sha256")
            or re.fullmatch(r"[0-9a-f]{2}", parts[2]) is None
            or re.fullmatch(r"[0-9a-f]{62}", parts[3]) is None
        ):
            _fail("source pack object path is invalid")
        expected_shards.setdefault(parts[2], set()).add(parts[3])

    root_metadata = _SOURCE_PACK._path_metadata(source_root)
    if not stat.S_ISDIR(root_metadata.st_mode):
        _fail("source pack path is not a directory")
    root_entries = _SOURCE_PACK._bounded_directory_entries(source_root, 2)
    if set(root_entries) != {"index.json", "objects"}:
        _fail("source pack root entries are invalid")

    index_path = Path(root_entries["index.json"].path)
    index_metadata = _SOURCE_PACK._path_metadata(index_path)
    if not stat.S_ISREG(index_metadata.st_mode) or index_metadata.st_nlink != 1:
        _fail("source pack index leaf is invalid")

    directories: list[tuple[str, tuple[int, int, int, int, int, int]]] = []
    leaves: list[tuple[str, tuple[int, int, int, int, int, int]]] = []
    objects = Path(root_entries["objects"].path)
    _append_bound_directory(source_root, objects, directories)
    algorithm_entries = _SOURCE_PACK._bounded_directory_entries(objects, 1)
    if set(algorithm_entries) != {"sha256"}:
        _fail("source pack digest directory is invalid")
    digest_root = Path(algorithm_entries["sha256"].path)
    _append_bound_directory(source_root, digest_root, directories)

    shard_entries = _SOURCE_PACK._bounded_directory_entries(digest_root, 90)
    if set(shard_entries) != set(expected_shards):
        _fail("source pack shard set is invalid")
    for shard_name in sorted(expected_shards):
        shard = Path(shard_entries[shard_name].path)
        _append_bound_directory(source_root, shard, directories)
        leaf_entries = _SOURCE_PACK._bounded_directory_entries(shard, 90)
        if set(leaf_entries) != expected_shards[shard_name]:
            _fail("source pack object set is incomplete")
        for leaf_name in sorted(expected_shards[shard_name]):
            leaf = Path(leaf_entries[leaf_name].path)
            metadata = _SOURCE_PACK._path_metadata(leaf)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                _fail("source pack object leaf is invalid")
            relative = leaf.relative_to(source_root).as_posix()
            leaves.append((relative, _SOURCE_PACK._file_identity(metadata)))

    directories.sort(key=lambda item: item[0].encode("ascii"))
    leaves.sort(key=lambda item: item[0].encode("ascii"))
    return _SourceTreeBinding(
        root_identity=_SOURCE_PACK._file_identity(root_metadata),
        index_identity=_SOURCE_PACK._file_identity(index_metadata),
        directories=tuple(directories),
        leaves=tuple(leaves),
    )


def _append_bound_directory(
    source_root: Path,
    directory: Path,
    bindings: list[tuple[str, tuple[int, int, int, int, int, int]]],
) -> None:
    metadata = _SOURCE_PACK._path_metadata(directory)
    if not stat.S_ISDIR(metadata.st_mode):
        _fail("source pack directory is invalid")
    bindings.append(
        (
            directory.relative_to(source_root).as_posix(),
            _SOURCE_PACK._file_identity(metadata),
        )
    )


def classify_source_pack(source_pack: SourcePack) -> ConversionResult:
    """Classify every authenticated identity into one closed migration result."""

    _bootstrap_dependencies()
    _validate_source_pack_model(source_pack)
    _validate_portable_contract_tables(source_pack)
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
    """Render the closed Task 5/6 outputs without writing output files."""

    _bootstrap_dependencies()
    _validate_conversion_result(result)
    source_pack = result.source_pack
    assets = {asset.source_path: asset for asset in source_pack.assets}
    records = {
        record.source_path: record
        for record in result.records
        if record.output_kind == "recipe"
    }
    candidates: list[dict[str, object]] = []
    quarantine_records: list[dict[str, object]] = []
    documents: dict[str, bytes] = {}
    for source_path in sorted(records, key=lambda value: value.encode("ascii")):
        record = records[source_path]
        asset = assets[source_path]
        source = _parse_json_object(asset)
        identifier = source.get("id")
        name = source.get("name")
        if type(identifier) is not str or type(name) is not str:
            _fail("catalog candidate identity is invalid")
        entry: dict[str, object] = {
            "id": identifier,
            "name": name,
            "sourceCommit": asset.source_commit,
            "sourcePath": asset.source_path,
            "sourceSha256": asset.sha256,
            "status": record.status,
        }
        if record.status == "quarantined":
            if record.reason is None:
                _fail("catalog quarantine reason is missing")
            entry["reason"] = record.reason
            quarantine_records.append(_quarantine_document(record))
        elif record.status == "converted":
            if re.fullmatch(r"[a-z0-9][a-z0-9._-]+", identifier) is None:
                _fail("reviewed Recipe identity is invalid")
            recipe_path = f"migration/macwin/generated/recipes/{identifier}.json"
            if recipe_path in documents:
                _fail("reviewed Recipe identity is duplicated")
            try:
                recipe_raw = _COMMON.canonical_json_bytes(
                    _render_reviewed_recipe(asset, source)
                )
            except _COMMON.MigrationError:
                _fail("reviewed Recipe cannot be rendered")
            documents[recipe_path] = recipe_raw
            entry["recipePath"] = recipe_path
            entry["recipeSha256"] = hashlib.sha256(recipe_raw).hexdigest()
        else:
            _fail("catalog candidate status is invalid")
        candidates.append(entry)

    portable_records = tuple(
        record
        for record in result.records
        if record.output_kind in {"portable-probe", "portable-fixture"}
    )
    for record in portable_records:
        asset = assets[record.source_path]
        if record.status == "quarantined":
            quarantine_records.append(_quarantine_document(record))
            continue
        if record.status != "converted":
            _fail("portable asset status is invalid")
        document = _portable_document(asset, record)
        category = "probes" if record.category == "probes" else "fixtures"
        manifest_path = (
            f"migration/macwin/generated/{category}/{document['id']}.json"
        )
        content_path = document["contentPath"]
        if manifest_path in documents or content_path in documents:
            _fail("portable asset output identity is duplicated")
        try:
            documents[manifest_path] = _COMMON.canonical_json_bytes(document)
        except _COMMON.MigrationError:
            _fail("portable asset cannot be rendered")
        documents[content_path] = asset.raw

    mapping_documents: dict[str, dict[str, object]] = {}
    for category, output_name in (
        ("patches", "patches.json"),
        ("bottle-schema", "bottle-schemas.json"),
    ):
        mapping_records = [
            _deferred_document(record, assets[record.source_path])
            for record in result.records
            if record.category == category
        ]
        mapping_documents[
            f"migration/macwin/generated/mappings/{output_name}"
        ] = {"schemaVersion": "1", "records": mapping_records}

    catalog_assets = {
        asset.source_path: asset
        for asset in source_pack.assets
        if asset.source_path in {CATALOG_INDEX_PATH, CATALOG_SIGNATURE_PATH}
    }
    if set(catalog_assets) != {CATALOG_INDEX_PATH, CATALOG_SIGNATURE_PATH}:
        _fail("catalog boundary is incomplete")
    converted_count = sum(entry["status"] == "converted" for entry in candidates)
    quarantined_count = sum(
        entry["status"] == "quarantined" for entry in candidates
    )
    catalog_document = {
        "schemaVersion": "1",
        "sourceRepository": source_pack.repository,
        "sourceCommit": source_pack.source_commit,
        "catalogBoundary": {
            "index": _catalog_boundary_document(catalog_assets[CATALOG_INDEX_PATH]),
            "signature": _catalog_boundary_document(
                catalog_assets[CATALOG_SIGNATURE_PATH]
            ),
        },
        "candidateCount": len(candidates),
        "convertedCount": converted_count,
        "quarantinedCount": quarantined_count,
        "candidates": candidates,
    }
    quarantine_document = {
        "schemaVersion": "1",
        "records": quarantine_records,
    }
    _validate_task5_documents(catalog_document, quarantine_document, result)
    _validate_task6_documents(mapping_documents, documents, result)
    try:
        documents["migration/macwin/generated/catalog.json"] = (
            _COMMON.canonical_json_bytes(catalog_document)
        )
        documents["migration/macwin/generated/quarantine.json"] = (
            _COMMON.canonical_json_bytes(quarantine_document)
        )
        for relative, document in mapping_documents.items():
            documents[relative] = _COMMON.canonical_json_bytes(document)
    except _COMMON.MigrationError:
        _fail("catalog outputs cannot be rendered")
    return documents


def _portable_document(
    asset: SourceAsset, record: ConversionRecord
) -> dict[str, object]:
    """Build one explicitly typed inert portable asset manifest."""

    if (
        record.status != "converted"
        or record.category not in {"probes", "fixtures"}
        or record.source_path != asset.source_path
        or record.source_sha256 != asset.sha256
        or asset.source_path not in PORTABLE_ASSET_TABLE
        or asset.license_status != "reviewed"
        or asset.provenance_status != "reviewed"
        or asset.external_refs
        or asset.development_dependencies
    ):
        _fail("portable asset evidence is incomplete")
    identifier, kind, media_type = PORTABLE_ASSET_TABLE[asset.source_path]
    category = "probes" if record.category == "probes" else "fixtures"
    content_path = (
        f"migration/macwin/generated/{category}/content/sha256/"
        f"{asset.sha256[:2]}/{asset.sha256[2:]}"
    )
    return {
        "schemaVersion": "1",
        "id": identifier,
        "kind": kind,
        "source": {
            "sourceRepository": record.source_repository,
            "sourceCommit": record.source_commit,
            "sourcePath": record.source_path,
            "sourceSha256": record.source_sha256,
            "gitBlobOid": asset.git_blob_oid,
            "gitMode": asset.git_mode,
        },
        "contentPath": content_path,
        "contentSha256": asset.sha256,
        "mediaType": media_type,
        "executable": False,
        "referencedAssetIds": list(PORTABLE_REFERENCE_TABLE[asset.source_path]),
        "intendedOwner": record.intended_owner,
        "license": {"status": asset.license_status},
        "provenance": {"status": asset.provenance_status},
    }


def _deferred_document(
    record: ConversionRecord, asset: SourceAsset
) -> dict[str, object]:
    if (
        record.status != "deferred"
        or record.category not in {"patches", "bottle-schema"}
        or record.source_path != asset.source_path
        or record.source_sha256 != asset.sha256
    ):
        _fail("deferred migration evidence is incomplete")
    return {
        "sourceRepository": record.source_repository,
        "sourcePath": record.source_path,
        "sourceCommit": record.source_commit,
        "gitBlobOid": asset.git_blob_oid,
        "gitMode": asset.git_mode,
        "sourceSha256": record.source_sha256,
        "category": record.category,
        "status": "deferred",
        "targetIssue": record.target_issue,
        "intendedOwner": record.intended_owner,
        "license": {"status": asset.license_status},
        "provenance": {"status": asset.provenance_status},
    }


def _is_exact_string_tuple(value: object) -> bool:
    return type(value) is tuple and all(type(item) is str for item in value)


def _validate_source_pack_field_types(source_pack: SourcePack) -> None:
    string_fields = (
        source_pack.repository,
        source_pack.source_tag,
        source_pack.source_tag_object,
        source_pack.source_commit,
        source_pack.inventory_commit,
        source_pack.digest_algorithm,
    )
    if (
        any(type(value) is not str for value in string_fields)
        or type(source_pack.category_counts) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            for item in source_pack.category_counts
        )
        or type(source_pack.assets) is not tuple
    ):
        _fail("source pack model fields are invalid")


def _validate_source_asset_field_types(asset: SourceAsset) -> None:
    string_fields = (
        asset.category,
        asset.source_path,
        asset.source_commit,
        asset.git_blob_oid,
        asset.sha256,
        asset.git_mode,
        asset.kind,
        asset.license_status,
        asset.provenance_status,
        asset.intended_owner,
        asset.object_path,
    )
    if (
        any(type(value) is not str for value in string_fields)
        or type(asset.byte_size) is not int
        or not _is_exact_string_tuple(asset.external_refs)
        or not _is_exact_string_tuple(asset.development_dependencies)
        or type(asset.raw) is not bytes
    ):
        _fail("source asset model fields are invalid")


def _validate_source_pack_model(source_pack: SourcePack) -> None:
    if type(source_pack) is not SourcePack:
        _fail("source pack model is invalid")
    _validate_source_pack_field_types(source_pack)
    if (
        source_pack.repository != APPROVED_REPOSITORY
        or source_pack.source_tag != APPROVED_SOURCE_TAG
        or source_pack.source_tag_object != APPROVED_SOURCE_TAG_OBJECT
        or source_pack.source_commit != APPROVED_SOURCE_COMMIT
        or source_pack.inventory_commit != APPROVED_INVENTORY_COMMIT
        or source_pack.digest_algorithm != "sha256"
        or source_pack.category_counts != EXPECTED_CATEGORY_COUNTS
        or len(source_pack.assets) != 90
    ):
        _fail("source pack model identity is invalid")

    paths: list[str] = []
    folded_paths: set[str] = set()
    digests: set[str] = set()
    counts = {category: 0 for category, _count in EXPECTED_CATEGORY_COUNTS}
    executable_count = 0
    for asset in source_pack.assets:
        if type(asset) is not SourceAsset:
            _fail("source asset model is invalid")
        _validate_source_asset_field_types(asset)
        if asset.category not in counts:
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
            or asset.byte_size < 0
            or asset.byte_size > _SOURCE_PACK.MAX_SOURCE_OBJECT_BYTES
            or asset.git_mode not in {"100644", "100755"}
            or asset.kind != EXPECTED_KINDS[asset.category]
            or asset.license_status not in {"reviewed", "unresolved"}
            or asset.provenance_status not in {"reviewed", "unresolved"}
            or asset.intended_owner != EXPECTED_OWNERS[asset.category]
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


def _validate_portable_contract_tables(source_pack: SourcePack) -> None:
    portable_assets = {
        asset.source_path: asset
        for asset in source_pack.assets
        if asset.category in {"probes", "fixtures"}
    }
    if (
        type(PORTABLE_ASSET_TABLE) is not dict
        or set(PORTABLE_ASSET_TABLE) != set(portable_assets)
    ):
        _fail("portable asset table is invalid")
    identifiers: dict[str, str] = {}
    folded_identifiers: set[str] = set()
    for path in sorted(PORTABLE_ASSET_TABLE, key=lambda value: value.encode("ascii")):
        entry = PORTABLE_ASSET_TABLE[path]
        asset = portable_assets[path]
        if (
            type(entry) is not tuple
            or len(entry) != 3
            or any(type(value) is not str for value in entry)
        ):
            _fail("portable asset table is invalid")
        identifier, kind, media_type = entry
        folded = identifier.casefold()
        try:
            _COMMON.require_relative_posix_path(
                f"migration/macwin/generated/probes/{identifier}.json"
            )
        except _COMMON.MigrationError:
            _fail("portable asset table is invalid")
        if (
            _PORTABLE_ID.fullmatch(identifier) is None
            or identifier in identifiers
            or folded in folded_identifiers
            or kind not in _PORTABLE_KINDS[asset.category]
            or not 3 <= len(media_type) <= 127
            or _PORTABLE_MEDIA_TYPE.fullmatch(media_type) is None
            or not 0 < asset.byte_size <= _SOURCE_PACK.MAX_SOURCE_OBJECT_BYTES
            or asset.git_mode not in {"100644", "100755"}
        ):
            _fail("portable asset table is invalid")
        identifiers[identifier] = path
        folded_identifiers.add(folded)
    try:
        table_raw = _COMMON.canonical_json_bytes(
            {
                path: list(PORTABLE_ASSET_TABLE[path])
                for path in sorted(
                    PORTABLE_ASSET_TABLE,
                    key=lambda value: value.encode("ascii"),
                )
            }
        )
    except _COMMON.MigrationError:
        _fail("portable asset table is invalid")
    if (
        hashlib.sha256(table_raw).hexdigest()
        != APPROVED_PORTABLE_ASSET_TABLE_SHA256
    ):
        _fail("portable asset table is invalid")

    if (
        type(PORTABLE_REFERENCE_TABLE) is not dict
        or set(PORTABLE_REFERENCE_TABLE) != set(portable_assets)
    ):
        _fail("portable reference graph is invalid")
    graph: dict[str, tuple[str, ...]] = {}
    for path in sorted(PORTABLE_REFERENCE_TABLE, key=lambda value: value.encode("ascii")):
        references = PORTABLE_REFERENCE_TABLE[path]
        if (
            type(references) is not tuple
            or len(references) > 90
            or any(type(value) is not str for value in references)
            or len(set(references)) != len(references)
            or tuple(sorted(references, key=lambda value: value.encode("ascii")))
            != references
            or any(value not in identifiers or identifiers[value] == path for value in references)
        ):
            _fail("portable reference graph is invalid")
        graph[PORTABLE_ASSET_TABLE[path][0]] = references
    visiting: set[str] = set()
    visited: set[str] = set()
    for root in sorted(graph, key=lambda value: value.encode("ascii")):
        if root in visited:
            continue
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                visiting.remove(node)
                visited.add(node)
                continue
            if node in visited:
                continue
            if node in visiting:
                _fail("portable reference graph is invalid")
            visiting.add(node)
            stack.append((node, True))
            for child in reversed(graph[node]):
                if child in visiting:
                    _fail("portable reference graph is invalid")
                if child not in visited:
                    stack.append((child, False))


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


def _add_recipe_finding(
    findings: list[RecipeFinding], reason: str, evidence_locator: str
) -> None:
    if reason not in QUARANTINE_REASONS:
        _fail("recipe finding is invalid")
    if type(evidence_locator) is not str or not evidence_locator or len(evidence_locator) > 4096:
        _fail("recipe evidence locator is invalid")
    finding = RecipeFinding(reason=reason, evidence_locator=evidence_locator)
    if finding not in findings:
        findings.append(finding)


def _is_host_absolute_locator(value: object) -> bool:
    _bootstrap_dependencies()
    return _COMMON.is_host_dependent_path(value)


def _is_safe_guest_executable(value: object) -> bool:
    _bootstrap_dependencies()
    return _COMMON.is_safe_guest_executable(value)


_INSTALLER_URL_MAX_LENGTH = 4096
_INSTALLER_URL_COMPONENT_MAX_LENGTH = 2048
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4_LIKE_HOST = re.compile(
    r"(?:0[xX][0-9A-Fa-f]+|0[0-9]+|[0-9]+)"
    r"(?:\.(?:0[xX][0-9A-Fa-f]+|0[0-9]+|[0-9]+)){0,3}"
)
_URL_PATH = re.compile(r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/%-])*")
_URL_QUERY = re.compile(r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/?%-])*")


def _has_well_formed_percent_escapes(value: str) -> bool:
    index = 0
    while index < len(value):
        if value[index] != "%":
            index += 1
            continue
        if index + 2 >= len(value) or re.fullmatch(
            r"[0-9A-Fa-f]{2}", value[index + 1 : index + 3]
        ) is None:
            return False
        index += 3
    return True


def _is_safe_url_component(value: str, *, path: bool) -> bool:
    if len(value) > _INSTALLER_URL_COMPONENT_MAX_LENGTH:
        return False
    if (path and _URL_PATH.fullmatch(value) is None) or (
        not path and _URL_QUERY.fullmatch(value) is None
    ):
        return False
    if not _has_well_formed_percent_escapes(value):
        return False
    try:
        decoded = unquote_to_bytes(value)
    except (UnicodeEncodeError, ValueError):
        return False
    if any(byte <= 0x20 or byte == 0x7F or byte == ord("\\") for byte in decoded):
        return False
    if path:
        if (value and not value.startswith("/")) or value.startswith("//"):
            return False
        if any(part in {b".", b".."} for part in decoded.split(b"/")):
            return False
    return True


def _is_safe_dns_hostname(hostname: str) -> bool:
    if len(hostname) > 253:
        return False
    labels = hostname.split(".")
    for label in labels:
        if _DNS_LABEL.fullmatch(label) is None:
            return False
        folded = label.casefold()
        if folded.startswith("xn--"):
            try:
                decoded = folded.encode("ascii").decode("idna")
                roundtrip = decoded.encode("idna").decode("ascii").casefold()
            except UnicodeError:
                return False
            if roundtrip != folded:
                return False
    return True


def _is_safe_installer_url(value: object) -> bool:
    """Accept one bounded, unambiguous HTTP(S) download locator."""

    if type(value) is not str or not value or len(value) > _INSTALLER_URL_MAX_LENGTH:
        return False
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    if any(byte <= 0x20 or byte == 0x7F for byte in raw) or "\\" in value:
        return False
    if "#" in value:
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (UnicodeError, ValueError):
        return False
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if (
        not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
        or "%" in parsed.netloc
        or parsed.fragment
    ):
        return False
    if port is not None and not 1 <= port <= 65535:
        return False

    authority = parsed.netloc
    if authority.startswith("["):
        close = authority.find("]")
        if close < 0:
            return False
        host_text = authority[1:close]
        suffix = authority[close + 1 :]
        if suffix and (
            not suffix.startswith(":")
            or not suffix[1:].isdigit()
            or str(int(suffix[1:])) != suffix[1:]
        ):
            return False
        try:
            address = ipaddress.IPv6Address(host_text)
            if str(address) != host_text.lower():
                return False
        except ValueError:
            return False
    else:
        if authority.count(":") > 1:
            return False
        host_text, separator, port_text = authority.partition(":")
        if separator and (
            not port_text.isdigit() or str(int(port_text)) != port_text
        ):
            return False
        if not host_text or hostname.lower() != host_text.lower():
            return False
        if re.fullmatch(r"[0-9.]+", host_text) or _IPV4_LIKE_HOST.fullmatch(
            host_text
        ):
            try:
                if str(ipaddress.IPv4Address(host_text)) != host_text:
                    return False
            except ipaddress.AddressValueError:
                return False
        elif not _is_safe_dns_hostname(host_text):
            return False

    if not _is_safe_url_component(parsed.path, path=True) or not _is_safe_url_component(
        parsed.query, path=False
    ):
        return False
    scheme_end = value.find(":")
    normalized_input = value[:scheme_end].lower() + value[scheme_end:]
    return parsed.geturl() == normalized_input


def _recipe_findings(
    asset: SourceAsset, source: dict[str, object]
) -> tuple[RecipeFinding, ...]:
    """Return all reviewed Recipe blockers without probing any locator."""

    if type(asset) is not SourceAsset or type(source) is not dict:
        _fail("recipe candidate model is invalid")
    findings: list[RecipeFinding] = []
    source_locator = asset.source_path
    if (
        asset.license_status != "reviewed"
        or type(source.get("license")) is not str
        or not source["license"]
    ):
        _add_recipe_finding(findings, "missing-license", f"{source_locator}#license")
    if asset.provenance_status != "reviewed":
        _add_recipe_finding(
            findings, "missing-provenance", f"{source_locator}#provenance"
        )
    tests = source.get("tests")
    if (
        type(tests) is not list
        or not tests
        or any(
            type(test) is not dict
            or not {"id", "kind", "timeoutSeconds"}.issubset(test)
            or not set(test).issubset(RECIPE_TEST_FIELDS)
            or type(test.get("id")) is not str
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]+", test["id"]) is None
            or test.get("kind") not in RECIPE_TEST_KINDS
            or type(test.get("timeoutSeconds")) is not int
            or not 1 <= test["timeoutSeconds"] <= 3600
            or ("expected" in test and type(test["expected"]) is not dict)
            for test in tests
        )
    ):
        _add_recipe_finding(findings, "unsupported-schema", f"{source_locator}#tests")

    for external_reference in asset.external_refs:
        _add_recipe_finding(
            findings, "unresolved-external-reference", external_reference
        )
    if frozenset(source) not in {
        RECIPE_TOP_LEVEL_FIELDS,
        REVIEWED_RECIPE_TOP_LEVEL_FIELDS,
    }:
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#source-fields"
        )

    for dependency in asset.development_dependencies:
        if _is_host_absolute_locator(dependency):
            _add_recipe_finding(findings, "absolute-path", dependency)
        _add_recipe_finding(findings, "unresolved-external-reference", dependency)

    installer = source.get("installer")
    if type(installer) is not dict:
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#installer"
        )
    else:
        allowed = {"arguments", "command", "fileName", "hints", "mode", "sha256", "url"}
        if not set(installer).issubset(allowed):
            _add_recipe_finding(
                findings,
                "unsupported-schema",
                f"{source_locator}#installer-fields",
            )
        mode = installer.get("mode")
        if mode == "alreadyInstalled":
            _add_recipe_finding(
                findings,
                "mutable-local-installation",
                f"{source_locator}#installer.mode",
            )
        elif mode == "localFile":
            _add_recipe_finding(
                findings,
                "unresolved-external-reference",
                f"{source_locator}#installer.mode",
            )
        elif mode not in {"download", "none"}:
            _add_recipe_finding(
                findings, "unsupported-schema", f"{source_locator}#installer.mode"
            )
        if mode == "download" and (
            type(installer.get("sha256")) is not str
            or _HEX_64.fullmatch(installer["sha256"]) is None
        ):
            _add_recipe_finding(
                findings, "missing-digest", f"{source_locator}#installer.sha256"
            )
        if mode == "download" and (
            type(installer.get("url")) is not str or not installer["url"]
        ):
            _add_recipe_finding(
                findings,
                "unresolved-external-reference",
                f"{source_locator}#installer.url",
            )
        elif mode == "download" and not _is_safe_installer_url(installer["url"]):
            _add_recipe_finding(
                findings,
                "absolute-path"
                if _is_host_absolute_locator(installer["url"])
                else "unresolved-external-reference",
                f"{source_locator}#installer.url",
            )
        file_name = installer.get("fileName")
        if mode == "download" and not _COMMON.is_safe_portable_basename(file_name):
            _add_recipe_finding(
                findings, "unsupported-schema", f"{source_locator}#installer.fileName"
            )
        hints = installer.get("hints", [])
        if type(hints) is not list or any(type(value) is not str for value in hints):
            _add_recipe_finding(
                findings, "unsupported-schema", f"{source_locator}#installer.hints"
            )
        else:
            for hint in hints:
                if _is_host_absolute_locator(hint):
                    _add_recipe_finding(findings, "absolute-path", hint)
        command = installer.get("command")
        if command is not None and command != "msiexec":
            _add_recipe_finding(
                findings,
                "unsupported-behavior",
                f"{source_locator}#installer.command",
            )

    environment = source.get("env")
    if type(environment) is not dict or any(
        type(key) is not str or type(value) is not str
        for key, value in environment.items()
    ):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#env"
        )
    elif any(_is_host_absolute_locator(value) for value in environment.values()):
        for value in environment.values():
            if _is_host_absolute_locator(value):
                _add_recipe_finding(findings, "unresolved-environment-path", value)

    launchers = source.get("launchers")
    if type(launchers) is not list or not launchers:
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#launchers"
        )
    else:
        launcher_fields = {"args", "displayName", "envOverrides", "exePath", "id", "showInHome"}
        for index, launcher in enumerate(launchers):
            locator = f"{source_locator}#launchers/{index}"
            if type(launcher) is not dict or set(launcher) != launcher_fields:
                _add_recipe_finding(findings, "unsupported-schema", locator)
                continue
            executable = launcher.get("exePath")
            if not _is_safe_guest_executable(executable):
                if _is_host_absolute_locator(executable):
                    _add_recipe_finding(findings, "absolute-path", executable)
                else:
                    _add_recipe_finding(findings, "unsupported-behavior", locator)
            overrides = launcher.get("envOverrides")
            if type(overrides) is not dict or any(
                type(key) is not str or type(value) is not str
                for key, value in overrides.items()
            ):
                _add_recipe_finding(findings, "unsupported-schema", locator)
            else:
                for value in overrides.values():
                    if _is_host_absolute_locator(value):
                        _add_recipe_finding(
                            findings, "unresolved-environment-path", value
                        )

    post_install = source.get("postInstall")
    if type(post_install) is not list:
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#postInstall"
        )
    elif post_install:
        _add_recipe_finding(
            findings, "unsupported-behavior", f"{source_locator}#postInstall"
        )

    bottle = source.get("bottleTemplate")
    if (
        type(bottle) is not dict
        or set(bottle) != {"arch", "windowsVersion"}
        or bottle.get("arch") != "win64"
        or bottle.get("windowsVersion") not in {"win7", "win10", "win11"}
    ):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#bottleTemplate"
        )
    requirements = source.get("engineRequirements")
    if type(requirements) is not dict or not set(requirements).issubset(
        {"minWineVersion", "requiresWin32", "supportedArch"}
    ):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#engineRequirements"
        )
    elif (
        type(requirements.get("minWineVersion")) is not str
        or requirements.get("supportedArch") != ["win64"]
        or (
            "requiresWin32" in requirements
            and type(requirements["requiresWin32"]) is not bool
        )
    ):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#engineRequirements"
        )

    scalar_fields = ("id", "name", "publisher", "category")
    if any(type(source.get(field)) is not str or not source[field] for field in scalar_fields):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#identity"
        )
    if source.get("compatibilityRating") not in {
        "excellent",
        "good",
        "limited",
        "experimental",
        "unknown",
    }:
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#compatibilityRating"
        )
    warnings = source.get("warnings")
    if type(warnings) is not list or any(
        type(warning) is not str or not warning for warning in warnings
    ):
        _add_recipe_finding(
            findings, "unsupported-schema", f"{source_locator}#warnings"
        )
    return tuple(findings)


def _select_recipe_reason(findings: tuple[RecipeFinding, ...]) -> str | None:
    reasons = {finding.reason for finding in findings}
    return next((reason for reason in RECIPE_REASON_PRECEDENCE if reason in reasons), None)


def _sorted_string_map(value: dict[str, object]) -> dict[str, str]:
    if type(value) is not dict or any(
        type(key) is not str or type(item) is not str for key, item in value.items()
    ):
        _fail("recipe string map is invalid")
    return {
        key: value[key]
        for key in sorted(value, key=lambda item: item.encode("utf-8"))
    }


def _map_recipe_structure(source: dict[str, object]) -> dict[str, object]:
    """Map only representable source structure; reviewed evidence is added later."""

    if type(source) is not dict or frozenset(source) not in {
        RECIPE_TOP_LEVEL_FIELDS,
        REVIEWED_RECIPE_TOP_LEVEL_FIELDS,
    }:
        _fail("recipe source fields are unsupported")
    bottle = source["bottleTemplate"]
    installer = source["installer"]
    launchers = source["launchers"]
    requirements = source["engineRequirements"]
    if (
        type(bottle) is not dict
        or set(bottle) != {"arch", "windowsVersion"}
        or bottle.get("arch") != "win64"
        or bottle.get("windowsVersion") not in {"win7", "win10", "win11"}
        or type(requirements) is not dict
        or not set(requirements).issubset(
            {"minWineVersion", "requiresWin32", "supportedArch"}
        )
        or type(requirements.get("minWineVersion")) is not str
        or requirements.get("supportedArch") != ["win64"]
        or (
            "requiresWin32" in requirements
            and type(requirements["requiresWin32"]) is not bool
        )
    ):
        _fail("recipe bottle fields are unsupported")
    if type(installer) is not dict or not set(installer).issubset(
        {"arguments", "command", "fileName", "hints", "mode", "sha256", "url"}
    ):
        _fail("recipe installer fields are unsupported")
    mode = installer.get("mode")
    if mode not in {"download", "none"}:
        _fail("recipe installer behavior is unsupported")
    if installer.get("command") not in {None, "msiexec"}:
        _fail("recipe installer behavior is unsupported")
    arguments = installer.get("arguments", [])
    if type(arguments) is not list or any(type(value) is not str for value in arguments):
        _fail("recipe installer arguments are invalid")
    mapped_installer: dict[str, object] = {"mode": mode, "arguments": list(arguments)}
    if mode == "download":
        if (
            type(installer.get("url")) is not str
            or not installer["url"]
            or not _is_safe_installer_url(installer["url"])
            or type(installer.get("fileName")) is not str
            or not installer["fileName"]
            or not _COMMON.is_safe_portable_basename(installer["fileName"])
            or type(installer.get("sha256")) is not str
            or _HEX_64.fullmatch(installer["sha256"]) is None
        ):
            _fail("recipe installer evidence is incomplete")
        mapped_installer.update(
            {
                "url": installer["url"],
                "fileName": installer["fileName"],
                "sha256": installer["sha256"],
            }
        )
        mapped_installer = {
            key: mapped_installer[key]
            for key in ("mode", "url", "fileName", "sha256", "arguments")
        }

    if type(launchers) is not list or not launchers:
        _fail("recipe launchers are invalid")
    mapped_launchers: list[dict[str, object]] = []
    expected_launcher_fields = {"args", "displayName", "envOverrides", "exePath", "id", "showInHome"}
    for launcher in launchers:
        if (
            type(launcher) is not dict
            or set(launcher) != expected_launcher_fields
            or type(launcher.get("id")) is not str
            or not launcher["id"]
            or type(launcher.get("displayName")) is not str
            or not launcher["displayName"]
            or not _is_safe_guest_executable(launcher.get("exePath"))
            or type(launcher.get("args")) is not list
            or any(type(value) is not str for value in launcher["args"])
            or type(launcher.get("showInHome")) is not bool
        ):
            _fail("recipe launcher fields are unsupported")
        mapped_launchers.append(
            {
                "id": launcher["id"],
                "name": launcher["displayName"],
                "executable": launcher["exePath"],
                "arguments": list(launcher["args"]),
                "environment": _sorted_string_map(launcher["envOverrides"]),
            }
        )
    for field in ("id", "name", "publisher", "category"):
        if type(source[field]) is not str or not source[field]:
            _fail("recipe identity fields are invalid")
    rating = source["compatibilityRating"]
    if rating not in {"excellent", "good", "limited", "experimental", "unknown"}:
        _fail("recipe compatibility rating is invalid")
    warnings = source["warnings"]
    if type(warnings) is not list or any(
        type(warning) is not str or not warning for warning in warnings
    ):
        _fail("recipe warnings are invalid")
    if source["postInstall"] != []:
        _fail("recipe post-install behavior is unsupported")
    return {
        "schemaVersion": "2",
        "id": source["id"],
        "metadata": {
            "name": source["name"],
            "publisher": source["publisher"],
            "category": source["category"],
        },
        "installer": mapped_installer,
        "bottle": {
            "windowsVersion": bottle["windowsVersion"],
            "guestArchitecture": "x86_64",
            "environment": _sorted_string_map(source["env"]),
        },
        "launchers": mapped_launchers,
        "compatibility": {
            "rating": rating,
            "platforms": [],
            "warnings": list(warnings),
        },
        "fixes": [],
    }


def _render_reviewed_recipe(
    asset: SourceAsset, source: dict[str, object]
) -> dict[str, object]:
    """Close reviewed evidence over one representable Recipe v2 document."""

    if _select_recipe_reason(_recipe_findings(asset, source)) is not None:
        _fail("reviewed Recipe evidence is incomplete")
    recipe = _map_recipe_structure(source)
    recipe["metadata"] = {
        **recipe["metadata"],
        "license": source["license"],
    }
    recipe["tests"] = [
        {
            key: test[key]
            for key in ("id", "kind", "timeoutSeconds", "expected")
            if key in test
        }
        for test in source["tests"]
    ]
    recipe["provenance"] = {
        "sourceRepository": APPROVED_REPOSITORY,
        "sourceCommit": asset.source_commit,
        "sourcePath": asset.source_path,
        "sourceSha256": asset.sha256,
    }
    return recipe


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
        source = _parse_json_object(asset)
        findings = _recipe_findings(asset, source)
        reason = _select_recipe_reason(findings)
        if reason is not None:
            evidence = tuple(
                sorted(
                    {finding.evidence_locator for finding in findings},
                    key=lambda value: value.encode("utf-8"),
                )
            )
            return ConversionRecord(
                **base,
                output_kind="recipe",
                status="quarantined",
                action="quarantine",
                target_issue=None,
                reason=reason,
                evidence_locators=evidence,
                release_condition=RECIPE_RELEASE_CONDITIONS[reason],
            )
        _map_recipe_structure(source)
        return ConversionRecord(
            **base,
            output_kind="recipe",
            status="converted",
            action="convert-recipe",
            target_issue=None,
            reason=None,
            evidence_locators=(),
            release_condition=None,
        )
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
    evidence = _portable_evidence_locators(asset)
    if asset.license_status == "unresolved":
        return ConversionRecord(
            **base,
            output_kind=output_kind,
            status="quarantined",
            action="quarantine",
            target_issue=None,
            reason="missing-license",
            evidence_locators=evidence,
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
            evidence_locators=evidence,
            release_condition=(
                "Record reviewed source provenance and regenerate the migration."
            ),
        )
    dependency_reason = _portable_dependency_reason(asset)
    if dependency_reason is not None:
        return ConversionRecord(
            **base,
            output_kind=output_kind,
            status="quarantined",
            action="quarantine",
            target_issue=None,
            reason=dependency_reason,
            evidence_locators=evidence,
            release_condition=RECIPE_RELEASE_CONDITIONS[dependency_reason],
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


def _portable_evidence_locators(asset: SourceAsset) -> tuple[str, ...]:
    evidence = tuple(
        sorted(
            {
                *((f"{asset.source_path}#license",) if asset.license_status == "unresolved" else ()),
                *((f"{asset.source_path}#provenance",) if asset.provenance_status == "unresolved" else ()),
                *asset.external_refs,
                *asset.development_dependencies,
            },
            key=lambda value: value.encode("utf-8"),
        )
    )
    if len(evidence) > MAX_EVIDENCE_LOCATORS:
        _fail("portable evidence locator set is invalid")
    return evidence


def _portable_dependency_reason(asset: SourceAsset) -> str | None:
    """Classify reviewed locator strings as inert data without probing them."""

    locators = (*asset.external_refs, *asset.development_dependencies)
    if any(
        value.startswith(("/", "\\"))
        or re.match(r"[A-Za-z]:[/\\]", value) is not None
        for value in locators
    ):
        return "absolute-path"
    if asset.external_refs:
        return "unresolved-external-reference"
    if any(
        re.search(r"\$(?:\{)?[A-Za-z_][A-Za-z0-9_]*", value) is not None
        or re.fullmatch(r"[A-Z][A-Z0-9_]*", value) is not None
        for value in asset.development_dependencies
    ):
        return "unresolved-environment-path"
    if asset.development_dependencies:
        return "unresolved-external-reference"
    return None


def _validate_conversion_record_field_types(record: ConversionRecord) -> None:
    string_fields = (
        record.source_repository,
        record.source_commit,
        record.source_path,
        record.source_sha256,
        record.source_kind,
        record.category,
        record.intended_owner,
        record.output_kind,
        record.status,
        record.action,
    )
    optional_strings = (
        record.target_issue,
        record.reason,
        record.release_condition,
    )
    if (
        any(type(value) is not str for value in string_fields)
        or any(value is not None and type(value) is not str for value in optional_strings)
        or not _is_exact_string_tuple(record.evidence_locators)
    ):
        _fail("conversion result record fields are invalid")
    try:
        _COMMON.require_relative_posix_path(record.source_path)
    except _COMMON.MigrationError:
        _fail("conversion result record path is invalid")


def _validate_conversion_result(result: ConversionResult) -> None:
    if (
        type(result) is not ConversionResult
        or type(result.source_pack) is not SourcePack
        or type(result.records) is not tuple
    ):
        _fail("conversion result is invalid")
    for record in result.records:
        if type(record) is not ConversionRecord:
            _fail("conversion result coverage is invalid")
        _validate_conversion_record_field_types(record)
    _validate_source_pack_model(result.source_pack)
    _validate_portable_contract_tables(result.source_pack)
    if len(result.records) != 90:
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
    records_by_path = {record.source_path: record for record in result.records}
    paths_by_identifier = {
        entry[0]: path for path, entry in PORTABLE_ASSET_TABLE.items()
    }
    for source_path in sorted(
        PORTABLE_REFERENCE_TABLE, key=lambda value: value.encode("ascii")
    ):
        if records_by_path[source_path].status != "converted":
            continue
        for target_identifier in PORTABLE_REFERENCE_TABLE[source_path]:
            target_path = paths_by_identifier[target_identifier]
            if records_by_path[target_path].status != "converted":
                _fail("portable converted reference is unresolved")
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


def _catalog_boundary_document(asset: SourceAsset) -> dict[str, str]:
    return {
        "sourceCommit": asset.source_commit,
        "sourcePath": asset.source_path,
        "sourceSha256": asset.sha256,
    }


def _quarantine_document(record: ConversionRecord) -> dict[str, object]:
    if (
        record.status != "quarantined"
        or record.reason is None
        or record.release_condition is None
        or not record.evidence_locators
    ):
        _fail("quarantine record is incomplete")
    return {
        "sourcePath": record.source_path,
        "sourceCommit": record.source_commit,
        "sourceSha256": record.source_sha256,
        "category": record.category,
        "status": "quarantined",
        "reason": record.reason,
        "evidenceLocators": list(record.evidence_locators),
        "intendedOwner": record.intended_owner,
        "releaseCondition": record.release_condition,
    }


def _validate_task5_documents(
    catalog: dict[str, object],
    quarantine: dict[str, object],
    result: ConversionResult,
) -> None:
    """Validate Task 5 application contracts independently of serialization."""

    catalog_fields = {
        "schemaVersion",
        "sourceRepository",
        "sourceCommit",
        "catalogBoundary",
        "candidateCount",
        "convertedCount",
        "quarantinedCount",
        "candidates",
    }
    if type(catalog) is not dict or set(catalog) != catalog_fields:
        _fail("generated catalog fields are invalid")
    if (
        catalog["schemaVersion"] != "1"
        or catalog["sourceRepository"] != result.source_pack.repository
        or catalog["sourceCommit"] != result.source_pack.source_commit
        or type(catalog["candidateCount"]) is not int
        or type(catalog["convertedCount"]) is not int
        or type(catalog["quarantinedCount"]) is not int
        or catalog["candidateCount"] != 17
        or catalog["convertedCount"] + catalog["quarantinedCount"] != 17
        or type(catalog["candidates"]) is not list
        or len(catalog["candidates"]) != 17
    ):
        _fail("generated catalog counts are invalid")
    boundary = catalog["catalogBoundary"]
    if type(boundary) is not dict or set(boundary) != {"index", "signature"}:
        _fail("generated catalog boundary is invalid")
    source_assets = {asset.source_path: asset for asset in result.source_pack.assets}
    for name, path in (
        ("index", CATALOG_INDEX_PATH),
        ("signature", CATALOG_SIGNATURE_PATH),
    ):
        if boundary.get(name) != _catalog_boundary_document(source_assets[path]):
            _fail("generated catalog boundary is invalid")

    recipe_records = {
        record.source_path: record
        for record in result.records
        if record.output_kind == "recipe"
    }
    candidate_paths: list[str] = []
    converted_count = 0
    quarantined_count = 0
    identifiers: set[str] = set()
    for entry in catalog["candidates"]:
        if type(entry) is not dict:
            _fail("generated catalog candidate is invalid")
        status = entry.get("status")
        expected_fields = {
            "id",
            "name",
            "sourceCommit",
            "sourcePath",
            "sourceSha256",
            "status",
        }
        if status == "quarantined":
            expected_fields.add("reason")
            quarantined_count += 1
        elif status == "converted":
            expected_fields.update({"recipePath", "recipeSha256"})
            converted_count += 1
        else:
            _fail("generated catalog candidate status is invalid")
        if set(entry) != expected_fields:
            _fail("generated catalog candidate fields are invalid")
        source_path = entry["sourcePath"]
        identifier = entry["id"]
        if (
            type(source_path) is not str
            or source_path not in recipe_records
            or type(identifier) is not str
            or not identifier
            or identifier in identifiers
        ):
            _fail("generated catalog candidate identity is invalid")
        asset = source_assets[source_path]
        record = recipe_records[source_path]
        source = _parse_json_object(asset)
        if (
            entry["name"] != source.get("name")
            or identifier != source.get("id")
            or entry["sourceCommit"] != asset.source_commit
            or entry["sourceSha256"] != asset.sha256
            or status != record.status
            or (status == "quarantined" and entry["reason"] != record.reason)
            or (
                status == "converted"
                and (
                    entry["recipePath"]
                    != f"migration/macwin/generated/recipes/{identifier}.json"
                    or type(entry["recipeSha256"]) is not str
                    or _HEX_64.fullmatch(entry["recipeSha256"]) is None
                )
            )
        ):
            _fail("generated catalog candidate provenance is invalid")
        candidate_paths.append(source_path)
        identifiers.add(identifier)
    if (
        candidate_paths
        != sorted(candidate_paths, key=lambda value: value.encode("ascii"))
        or set(candidate_paths) != set(recipe_records)
        or converted_count != catalog["convertedCount"]
        or quarantined_count != catalog["quarantinedCount"]
    ):
        _fail("generated catalog candidate coverage is invalid")

    if type(quarantine) is not dict or set(quarantine) != {"schemaVersion", "records"}:
        _fail("generated quarantine fields are invalid")
    quarantine_records = quarantine["records"]
    if quarantine["schemaVersion"] != "1" or type(quarantine_records) is not list:
        _fail("generated quarantine contract is invalid")
    expected_quarantine = [
        _quarantine_document(record)
        for record in result.records
        if record.status == "quarantined"
    ]
    if quarantine_records != expected_quarantine:
        _fail("generated quarantine records are invalid")
    for record in quarantine_records:
        if set(record) != {
            "sourcePath",
            "sourceCommit",
            "sourceSha256",
            "category",
            "status",
            "reason",
            "evidenceLocators",
            "intendedOwner",
            "releaseCondition",
        }:
            _fail("generated quarantine record fields are invalid")


def _validate_task6_documents(
    mappings: dict[str, dict[str, object]],
    portable_documents: dict[str, bytes],
    result: ConversionResult,
) -> None:
    """Validate Task 6 coverage independently from its serializers."""

    expected_paths = {
        "migration/macwin/generated/mappings/patches.json": "patches",
        "migration/macwin/generated/mappings/bottle-schemas.json": "bottle-schema",
    }
    if type(mappings) is not dict or set(mappings) != set(expected_paths):
        _fail("deferred mapping set is invalid")
    assets = {asset.source_path: asset for asset in result.source_pack.assets}
    for relative, category in expected_paths.items():
        document = mappings[relative]
        if (
            type(document) is not dict
            or set(document) != {"schemaVersion", "records"}
            or document["schemaVersion"] != "1"
            or type(document["records"]) is not list
        ):
            _fail("deferred mapping contract is invalid")
        expected = [
            _deferred_document(record, assets[record.source_path])
            for record in result.records
            if record.category == category
        ]
        if document["records"] != expected:
            _fail("deferred mapping coverage is invalid")

    portable_records = tuple(
        record
        for record in result.records
        if record.category in {"probes", "fixtures"}
    )
    if len(portable_records) != 56 or set(PORTABLE_ASSET_TABLE) != {
        record.source_path for record in portable_records
    }:
        _fail("portable asset table is incomplete")
    for record in portable_records:
        asset = assets[record.source_path]
        if record.status == "quarantined":
            continue
        manifest = _portable_document(asset, record)
        category = "probes" if record.category == "probes" else "fixtures"
        manifest_path = (
            f"migration/macwin/generated/{category}/{manifest['id']}.json"
        )
        content_path = manifest["contentPath"]
        try:
            expected_manifest = _COMMON.canonical_json_bytes(manifest)
        except _COMMON.MigrationError:
            _fail("portable asset contract is invalid")
        if (
            portable_documents.get(manifest_path) != expected_manifest
            or portable_documents.get(content_path) != asset.raw
            or hashlib.sha256(asset.raw).hexdigest() != manifest["contentSha256"]
            or manifest["executable"] is not False
        ):
            _fail("portable asset output is invalid")


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
