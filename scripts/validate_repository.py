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

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _VALIDATOR_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _VALIDATOR_CREATE_FILE = _VALIDATOR_KERNEL32.CreateFileW
    _VALIDATOR_CREATE_FILE.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _VALIDATOR_CREATE_FILE.restype = wintypes.HANDLE
    _VALIDATOR_CLOSE_HANDLE = _VALIDATOR_KERNEL32.CloseHandle
    _VALIDATOR_CLOSE_HANDLE.argtypes = (wintypes.HANDLE,)
    _VALIDATOR_CLOSE_HANDLE.restype = wintypes.BOOL
    _VALIDATOR_INVALID_HANDLE = ctypes.c_void_p(-1).value


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_MEMBER = re.compile(r'^\s*"([^"]+)"[,]?\s*$')
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MIGRATION_CHECK_TIMEOUT_SECONDS = 120
MAX_MIGRATION_CONVERTER_BYTES = 2 * 1024 * 1024
MIGRATION_CONVERTER_BOOTSTRAP = (
    "import sys; path=sys.argv[1]; sys.argv=sys.argv[1:]; "
    "source=sys.stdin.buffer.read(); "
    "namespace={'__file__':path,'__name__':'__main__','__package__':None}; "
    "exec(compile(source,path,'exec'),namespace)"
)
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
TASK6_DOCUMENT_PATHS = frozenset(
    {
        "migration/macwin/generated/mappings/patches.json",
        "migration/macwin/generated/mappings/bottle-schemas.json",
    }
)
TASK7_DOCUMENT_PATHS = frozenset(
    {"migration/macwin/generated/index.json"}
)
TASK6_EVIDENCE_PATHS = TASK5_DOCUMENT_PATHS | TASK6_DOCUMENT_PATHS
GENERATED_EVIDENCE_PATHS = TASK6_EVIDENCE_PATHS | TASK7_DOCUMENT_PATHS
TASK5_DOCUMENT_SHA256 = {
    "migration/macwin/generated/catalog.json": "c0c5b93b97b3f3c6e9197d2e00645dc28b1163b3130fe3e73ec7d1fde9e8fa4a",
    "migration/macwin/generated/quarantine.json": "ca0132b78ac4bae8ed00446194cd7e9712b37ebc2aea4087ebad695248e2b2e9",
}
TASK6_DOCUMENT_SHA256 = {
    "migration/macwin/generated/mappings/patches.json": "202c56f99c7f332a7b5c6b93b87baef66d1445ae3981954c23f2b6c7ea64edd1",
    "migration/macwin/generated/mappings/bottle-schemas.json": "f99698eaf5e341a58c7f7b91299701481c38df8a31203064aab38822622041cb",
}
TASK7_DOCUMENT_SHA256 = {
    "migration/macwin/generated/index.json": "2c6a0447b4a27c8c0baf0da9dd45cad355db75a6a880e9b90434bc7b93cdf080",
}
PATCH_REVIEW_PATH = "migration/macwin/reviewed/patches.json"
PATCH_REVIEW_DOCUMENT_SHA256 = (
    "38c54730634616bdc0b6a82aa5a5b57bb1c0d6da17d429897cd8da2414bc7783"
)
PATCH_REVIEW_TREE = {"patches.json": "regular"}
MAX_PATCH_REVIEW_BYTES = 1024 * 1024
PATCH_REVIEW_SOURCE = {
    "repository": "a1112/Mac-Win",
    "sourceTag": "mw-migration-baseline-db12d5e",
    "sourceTagObject": "9f10d003382ce7ffbb269376c03477e17516302f",
    "sourceCommit": "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527",
    "inventoryCommit": "97f8423094d25325d8f864eb6f49a9e8628dbb93",
    "sourceIndexSha256": "1fc8b071a9c52c5f29d130e47e3bd1cb165effa860eaa45336c82ee07cafe3a3",
    "digestAlgorithm": "sha256",
}
PATCH_UPSTREAM_JASP = {
    "repository": "https://github.com/jasp-stats/jasp-desktop",
    "referenceKind": "tag",
    "reference": "v0.97.1",
    "tagObject": None,
    "commit": "28be3fee5c7ce2119f1945acd0254eb4fb8cb6e2",
}
PATCH_UPSTREAM_WINE = {
    "repository": "https://gitlab.winehq.org/wine/wine/",
    "referenceKind": "annotated-tag",
    "reference": "wine-11.11",
    "tagObject": "b08651f36865a3e1d9300d792df322d2ee8a807e",
    "commit": "f6c044e1890e84a4aa5e77e76ba7276a615630e1",
}
PATCH_MISSING_LICENSE_RELEASE = (
    "Record patch-specific license evidence and repeat review."
)
PATCH_PREIMAGE_EVIDENCE_SHA256 = (
    "5d9cc21f82fe883acfa5174d4e06dfdf1cf48ca7ff2e822d8d54fd81bf9d974d"
)
PATCH_PREIMAGE_RECORD_COUNT = 11
PATCH_PREIMAGE_COUNT = 88
PATCH_APPLICATIONS = {
    "patches/jasp-0.97.1-avoid-nested-workspace-reset.patch": (
        "jasp-desktop",
    ),
    "patches/jasp-0.97.1-fix-proxy-model-reset.patch": ("jasp-desktop",),
    "patches/jasp-0.97.1-initialize-enginesync-before-reset.patch": (
        "jasp-desktop",
    ),
    "patches/jasp-0.97.1-local-macos-build-configure.patch": (
        "jasp-build",
        "jasp-desktop",
    ),
    "patches/wine-dcomp-winui-host-composition.patch": ("wine", "winui"),
    "patches/wine-macos-native-ui-integration.patch": ("macos-driver", "wine"),
    "patches/wine-shell32-virtual-desktop-manager.patch": ("shell32", "wine"),
    "patches/wine-windows-data-json-modern-apps.patch": (
        "windows-data-json",
        "wine",
    ),
    "patches/wine-windows-graphics-imaging.patch": (
        "windows-graphics-imaging",
        "wine",
    ),
    "patches/wine-windowscodecs-bilinear-scaler.patch": (
        "windowscodecs",
        "wine",
    ),
    "patches/wine-winui-pointer-input.patch": ("wine", "winui"),
}
PATCH_GIT_OID = re.compile(r"^(?!0{40}$)[0-9a-f]{40}$")
PATCH_GIT_PREFIX = re.compile(r"^(?!0{7,40}$)[0-9a-f]{7,40}$")
PATCH_ANY_GIT_PREFIX = re.compile(r"^[0-9a-f]{7,40}$")
PATCH_ZERO_GIT_PREFIX = re.compile(r"^0{7,40}$")
PATCH_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PATCH_HTTPS_EVIDENCE = re.compile(
    r"^https://(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))+"
    r"(?:/|(?:/[A-Za-z0-9._~!$&'()*+,;=:@+-]+)+/?)?$"
)
PATCH_MAIL_AUTHOR = re.compile(r"^([^<>\r\n]{1,256}) <([^<>\s]{3,254})>$")
PATCH_RESERVED_SEGMENT = re.compile(
    r"^(?:conin\$|conout\$|con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
PATCH_INDEX_LINE = re.compile(
    rb"^index ([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})(?: ([0-7]{6}))?$"
)
TASK5_SOURCE_REPOSITORY = "a1112/Mac-Win"
TASK5_SOURCE_COMMIT = "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527"
TASK5_CATALOG_ROOT = "MacWinManager/Sources/MacWinManagerApp/Resources/Catalog"
TASK5_CATALOG_INDEX = f"{TASK5_CATALOG_ROOT}/catalog.index.json"
TASK5_CATALOG_SIGNATURE = f"{TASK5_CATALOG_ROOT}/catalog.signature.json"
MAX_TASK5_DOCUMENT_BYTES = 1024 * 1024
MAX_ORDINARY_SCAN_BYTES = 32 * 1024 * 1024
MAX_ORDINARY_SCAN_ENTRIES = 100_000
MAX_ORDINARY_SCAN_TOTAL_BYTES = 1024 * 1024 * 1024
DEVELOPER_PATH_VALIDATION_ERROR = "Repository developer-path validation failed"


def _bind_validator_directory(path: Path) -> tuple[object, tuple[int, int]]:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or getattr(metadata, "st_reparse_tag", 0)
    ):
        raise ValueError("validator directory is unsafe")
    if os.name == "nt":
        descriptor = _VALIDATOR_CREATE_FILE(
            str(path),
            0x80000000 | 0x0080,
            0x00000001 | 0x00000002,
            None,
            3,
            0x02000000 | 0x00200000,
            None,
        )
        if descriptor == _VALIDATOR_INVALID_HANDLE:
            raise ValueError("validator directory could not be bound")
        opened = metadata
    else:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino)
    if not stat.S_ISDIR(opened.st_mode) or identity != (
        metadata.st_dev,
        metadata.st_ino,
    ):
        _close_validator_directory(descriptor)
        raise ValueError("validator directory identity changed")
    return descriptor, identity


def _close_validator_directory(descriptor: object) -> None:
    if os.name == "nt":
        _VALIDATOR_CLOSE_HANDLE(descriptor)
    else:
        os.close(descriptor)


def _read_bound_converter(
    tools: Path, descriptor: object, identity: tuple[int, int]
) -> bytes:
    path = tools / "convert_macwin_assets.py"
    if os.name == "nt":
        raw, _leaf_identity = _read_bound_regular_file(
            path, MAX_MIGRATION_CONVERTER_BYTES
        )
    else:
        leaf = os.open(
            path.name,
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=descriptor,
        )
        try:
            opened = os.fstat(leaf)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_size > MAX_MIGRATION_CONVERTER_BYTES
            ):
                raise ValueError("migration converter is unsafe")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(
                    leaf,
                    min(
                        64 * 1024,
                        MAX_MIGRATION_CONVERTER_BYTES + 1 - total,
                    ),
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MIGRATION_CONVERTER_BYTES:
                    raise ValueError("migration converter is too large")
                chunks.append(chunk)
            final = os.fstat(leaf)
            if _filesystem_identity(final) != _filesystem_identity(opened):
                raise ValueError("migration converter changed")
            raw = b"".join(chunks)
        finally:
            os.close(leaf)
    current = tools.lstat()
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
        or (
            os.name != "nt"
            and (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
            != identity
        )
    ):
        raise ValueError("migration tools binding changed")
    return raw


def validate_macwin_asset_migration() -> list[str]:
    """Run the required migration converter check."""
    converter = ROOT / "tools/convert_macwin_assets.py"
    tools_descriptor: object | None = None
    try:
        tools_descriptor, tools_identity = _bind_validator_directory(
            ROOT / "tools"
        )
        converter_raw = _read_bound_converter(
            ROOT / "tools", tools_descriptor, tools_identity
        )
    except (FileNotFoundError, ValueError):
        return ["Mac-Win asset migration converter path is not a regular file"]
    except OSError:
        return ["Mac-Win asset migration converter path is not a regular file"]
    finally:
        if tools_descriptor is not None:
            _close_validator_directory(tools_descriptor)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in MIGRATION_ENVIRONMENT_NAMES
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                MIGRATION_CONVERTER_BOOTSTRAP,
                str(converter),
                "--check",
            ],
            cwd=ROOT,
            check=False,
            env=environment,
            executable=None,
            input=converter_raw,
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
        tuple[Path, str, tuple[int, ...]]
    ] = []
    for part in absolute.parts[1:]:
        current /= part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_reparse_tag", 0):
            raise ValueError("generated evidence path is linked")
        if stat.S_ISDIR(metadata.st_mode):
            bindings.append((current, "directory", _directory_identity(metadata)))
        elif current == absolute and stat.S_ISREG(metadata.st_mode):
            bindings.append((current, "regular", _filesystem_identity(metadata)))
        else:
            raise ValueError("generated evidence path is invalid")
    for component, kind, identity in bindings:
        metadata = component.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_reparse_tag", 0):
            raise ValueError("generated evidence path identity changed")
        if kind == "directory":
            valid = stat.S_ISDIR(metadata.st_mode) and _directory_identity(
                metadata
            ) == identity
        else:
            valid = stat.S_ISREG(metadata.st_mode) and _filesystem_identity(
                metadata
            ) == identity
        if not valid:
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
    """Bind the exact Task 7 generated graph to converter-rebuilt bytes."""

    def __init__(
        self,
        generated_root: Path,
        root_identity: tuple[int, int, int, int, int, int],
        expected: dict[str, bytes],
        leaves: dict[Path, tuple[bytes, tuple[int, int, int, int, int, int]]],
        directories: dict[
            Path,
            tuple[tuple[int, int], tuple[tuple[str, str], ...]],
        ],
        converter: object,
        converter_path: Path,
        converter_raw: bytes,
        converter_identity: tuple[int, int, int, int, int, int],
        patch_review_binding: _PatchReviewBinding,
    ) -> None:
        self.generated_root = generated_root
        self.root_identity = root_identity
        self.expected = expected
        self.leaves = leaves
        self.directories = directories
        self.converter = converter
        self.converter_path = converter_path
        self.converter_raw = converter_raw
        self.converter_identity = converter_identity
        self.patch_review_binding = patch_review_binding

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
        self.patch_review_binding.revalidate()
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
        if type(regenerated) is not dict or set(regenerated) != GENERATED_EVIDENCE_PATHS or any(
            regenerated.get(relative) != raw
            for relative, raw in self.expected.items()
        ):
            raise ValueError("generated evidence semantics changed")
        _revalidate_exact_generated_tree(self.directories)
        for path in sorted(self.leaves, key=lambda value: str(value).encode("utf-8")):
            self.verify_path(path)
        _revalidate_exact_generated_tree(self.directories)
        final_root = self.generated_root.lstat()
        if _filesystem_identity(final_root) != self.root_identity:
            raise ValueError("generated evidence root changed")
        self.patch_review_binding.revalidate()


def _read_exact_generated_directory(
    path: Path,
    expected: tuple[tuple[str, str], ...],
) -> tuple[int, int]:
    """Bind one small generated directory without accepting extra identities."""

    _validate_bound_path_chain(path)
    before = path.lstat()
    if _ordinary_entry_kind(before) != "directory":
        raise ValueError("generated evidence tree is invalid")
    identity = _directory_identity(before)
    entries: list[tuple[str, str]] = []
    with os.scandir(path) as iterator:
        for entry in iterator:
            if len(entries) >= len(expected):
                raise ValueError("generated evidence tree is invalid")
            metadata = entry.stat(follow_symlinks=False)
            entries.append((entry.name, _ordinary_entry_kind(metadata)))
    actual = tuple(sorted(entries, key=lambda item: item[0].encode("utf-8")))
    after = path.lstat()
    if (
        actual != expected
        or _ordinary_entry_kind(after) != "directory"
        or _directory_identity(after) != identity
    ):
        raise ValueError("generated evidence tree is invalid")
    _validate_bound_path_chain(path)
    return identity


def _bind_exact_generated_tree(
    generated_root: Path,
) -> dict[Path, tuple[tuple[int, int], tuple[tuple[str, str], ...]]]:
    expected = {
        generated_root: (
            ("catalog.json", "regular"),
            ("index.json", "regular"),
            ("mappings", "directory"),
            ("quarantine.json", "regular"),
        ),
        generated_root / "mappings": (
            ("bottle-schemas.json", "regular"),
            ("patches.json", "regular"),
        ),
    }
    return {
        path: (_read_exact_generated_directory(path, entries), entries)
        for path, entries in expected.items()
    }


def _revalidate_exact_generated_tree(
    directories: dict[
        Path,
        tuple[tuple[int, int], tuple[tuple[str, str], ...]],
    ],
) -> None:
    if type(directories) is not dict or len(directories) != 2:
        raise ValueError("generated evidence tree is invalid")
    for path in sorted(directories, key=lambda value: str(value).encode("utf-8")):
        identity, expected = directories[path]
        if _read_exact_generated_directory(path, expected) != identity:
            raise ValueError("generated evidence tree changed")


class _PatchReviewBinding:
    """Bind the one-leaf reviewed tree through every later repository scan."""

    def __init__(
        self,
        root: Path,
        root_identity: tuple[int, int],
        expected_children: tuple[tuple[str, str], ...],
        leaf: Path,
        raw: bytes,
        leaf_identity: tuple[int, int, int, int, int, int],
    ) -> None:
        self.root = root
        self.root_identity = root_identity
        self.expected_children = expected_children
        self.leaf = leaf
        self.raw = raw
        self.leaf_identity = leaf_identity

    def contains(self, path: Path) -> bool:
        return path.absolute() == self.leaf

    def verify_path(self, path: Path) -> bytes:
        if path.absolute() != self.leaf:
            raise ValueError("patch review evidence path is not authenticated")
        raw, identity = _read_bound_regular_file(path, MAX_PATCH_REVIEW_BYTES)
        if raw != self.raw or identity != self.leaf_identity:
            raise ValueError("patch review evidence changed")
        return raw

    def revalidate(self) -> None:
        if (
            _read_exact_generated_directory(self.root, self.expected_children)
            != self.root_identity
        ):
            raise ValueError("patch review evidence tree changed")
        self.verify_path(self.leaf)
        if (
            _read_exact_generated_directory(self.root, self.expected_children)
            != self.root_identity
        ):
            raise ValueError("patch review evidence tree changed")


def _validated_patch_review_binding() -> tuple[_PatchReviewBinding | None, list[str]]:
    """Authenticate the exact canonical reviewed policy independently."""

    try:
        root = (ROOT / "migration" / "macwin" / "reviewed").absolute()
        expected_children = tuple(
            sorted(PATCH_REVIEW_TREE.items(), key=lambda item: item[0].encode("ascii"))
        )
        root_identity = _read_exact_generated_directory(root, expected_children)
        leaf = (ROOT / PurePosixPath(PATCH_REVIEW_PATH)).absolute()
        raw, leaf_identity = _read_bound_regular_file(
            leaf, MAX_PATCH_REVIEW_BYTES
        )
        if hashlib.sha256(raw).hexdigest() != PATCH_REVIEW_DOCUMENT_SHA256:
            raise ValueError("patch review evidence digest is invalid")
        _canonical_patch_review_json(raw)
        binding = _PatchReviewBinding(
            root,
            root_identity,
            expected_children,
            leaf,
            raw,
            leaf_identity,
        )
        binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None, ["Mac-Win patch review evidence validation failed"]
    return binding, []


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
            Path, tuple[tuple[int, int], tuple[int, int, int, int, int, int]]
        ] = {}
        self.contents: dict[
            tuple[int, int],
            tuple[bytes | None, bytes, tuple[int, int, int, int, int, int], Path],
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
        key = identity[:2]
        existing = self.contents.get(key)
        if existing is None:
            self.contents[key] = (
                raw if identity[3] > 1 else None,
                hashlib.sha256(raw).digest(),
                identity,
                absolute,
            )
        elif existing[1:3] != (hashlib.sha256(raw).digest(), identity):
            raise _DeveloperPathScanError()
        self.leaves[absolute] = (key, identity)

    def add_alias(
        self,
        path: Path,
        identity: tuple[int, int, int, int, int, int],
    ) -> bytes:
        absolute = path.absolute()
        key = identity[:2]
        existing = self.contents.get(key)
        if absolute in self.leaves or existing is None or existing[2] != identity:
            raise _DeveloperPathScanError()
        self.leaves[absolute] = (key, identity)
        raw = existing[0]
        if raw is None:
            raise _DeveloperPathScanError()
        return raw

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
        for key in sorted(self.contents):
            _raw, expected_digest, expected_identity, path = self.contents[key]
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
        for path in sorted(self.leaves, key=lambda value: str(value).encode("utf-8")):
            _key, expected_identity = self.leaves[path]
            try:
                _validate_bound_path_chain(path)
                metadata = path.lstat()
            except (OSError, RuntimeError, TypeError, ValueError):
                raise _DeveloperPathScanError() from None
            if (
                _ordinary_entry_kind(metadata) != "regular"
                or _filesystem_identity(metadata) != expected_identity
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


def _canonical_task5_json(raw: bytes) -> dict[str, object]:
    if len(raw) > MAX_TASK5_DOCUMENT_BYTES:
        raise ValueError("generated evidence is oversized")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("generated evidence JSON is invalid") from None
    if type(value) is not dict:
        raise ValueError("generated evidence JSON is invalid")
    canonical = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    if raw != canonical:
        raise ValueError("generated evidence JSON is not canonical")
    return value


def _canonical_patch_review_json(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_PATCH_REVIEW_BYTES:
        raise ValueError("patch review evidence is invalid")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("patch review evidence is invalid")
            value[key] = item
        return value

    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("patch review evidence is invalid") from None
    if type(value) is not dict:
        raise ValueError("patch review evidence is invalid")
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > 128:
            raise ValueError("patch review evidence is invalid")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("patch review evidence is invalid")
            pending.extend((nested, depth + 1) for nested in item.values())
        elif type(item) is list:
            pending.extend((nested, depth + 1) for nested in item)
    canonical = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    if raw != canonical:
        raise ValueError("patch review evidence is invalid")
    return value


def _independent_patch_text(value: object, maximum: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and all(32 <= ord(character) <= 126 for character in value)
    )


def _independent_patch_relative_path(value: object) -> bool:
    if (
        not _independent_patch_text(value, 1024)
        or value.startswith("/")
        or "\\" in value
        or any(character in '<>:"|?*' for character in value)
    ):
        return False
    segments = value.split("/")
    for segment in segments:
        if (
            not segment
            or len(segment) > 255
            or segment in {".", ".."}
            or segment[-1] in {" ", "."}
        ):
            return False
        reserved_stem = segment.split(".", 1)[0].rstrip(" ")
        if PATCH_RESERVED_SEGMENT.fullmatch(reserved_stem):
            return False
    return True


def _independent_patch_diff_metadata(
    raw: bytes,
) -> tuple[tuple[str, str | None], ...]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 1024 * 1024 or b"\r" in raw:
        raise ValueError("patch source diff evidence is invalid")
    entries: list[tuple[str, str | None]] = []
    current_path: str | None = None
    current_old_blob: str | None = None
    current_has_index = False
    for line in raw.split(b"\n"):
        if line.startswith(b"diff --git "):
            if current_path is not None:
                entries.append((current_path, current_old_blob))
            if not line.startswith(b"diff --git a/"):
                raise ValueError("patch source diff evidence is invalid")
            left, separator, right = line[len(b"diff --git a/") :].partition(b" b/")
            if not separator or b" b/" in right or left != right:
                raise ValueError("patch source diff evidence is invalid")
            try:
                current_path = left.decode("ascii", errors="strict")
            except UnicodeDecodeError:
                raise ValueError("patch source diff evidence is invalid") from None
            if not _independent_patch_relative_path(current_path):
                raise ValueError("patch source diff evidence is invalid")
            current_old_blob = None
            current_has_index = False
        elif line.startswith(b"index "):
            match = PATCH_INDEX_LINE.fullmatch(line)
            if current_path is None or current_has_index or match is None:
                raise ValueError("patch source diff evidence is invalid")
            current_old_blob = match.group(1).decode("ascii")
            current_has_index = True
    if current_path is not None:
        entries.append((current_path, current_old_blob))
    if not 1 <= len(entries) <= 128:
        raise ValueError("patch source diff evidence is invalid")
    entries.sort(key=lambda item: item[0].encode("ascii"))
    if len({path.casefold() for path, _old_blob in entries}) != len(entries):
        raise ValueError("patch source diff evidence is invalid")
    return tuple(entries)


def _independent_patch_mail_identity(
    source_binding: object, asset: dict[str, object]
) -> tuple[str | None, dict[str, object], bytes]:
    object_path = asset.get("objectPath")
    if type(object_path) is not str:
        raise ValueError("patch source object identity is invalid")
    raw = source_binding.verify_path(
        source_binding.root / PurePosixPath(object_path)
    )
    if type(raw) is not bytes or len(raw) != asset.get("byteSize"):
        raise ValueError("patch source object identity is invalid")
    if not raw.startswith(b"From "):
        return None, {"status": "unresolved"}, raw
    header_end = raw.find(b"\n\n")
    if not 0 < header_end <= 16 * 1024 or b"\r" in raw[:header_end]:
        raise ValueError("patch source mail identity is invalid")
    try:
        lines = raw[:header_end].decode("ascii", errors="strict").split("\n")
    except UnicodeDecodeError:
        raise ValueError("patch source mail identity is invalid") from None
    if not lines or re.fullmatch(
        r"From [0-9a-f]{40} Mon Sep 17 00:00:00 2001", lines[0]
    ) is None:
        raise ValueError("patch source mail identity is invalid")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ": " not in line:
            raise ValueError("patch source mail identity is invalid")
        key, value = line.split(": ", 1)
        if key in headers:
            raise ValueError("patch source mail identity is invalid")
        headers[key] = value
    if set(headers) != {"From", "Date", "Subject"}:
        raise ValueError("patch source mail identity is invalid")
    subject = headers["Subject"]
    author_match = PATCH_MAIL_AUTHOR.fullmatch(headers["From"])
    if (
        not _independent_patch_text(subject, 256)
        or not _independent_patch_text(headers["Date"], 128)
        or author_match is None
    ):
        raise ValueError("patch source mail identity is invalid")
    return (
        subject,
        {
            "displayName": author_match.group(1),
            "email": author_match.group(2),
            "evidence": "frozen-patch-mail-header",
            "status": "reviewed",
        },
        raw,
    )


def _independent_patch_author(author: object) -> bool:
    if type(author) is not dict or not {"status"}.issubset(author):
        return False
    status = author.get("status")
    if status == "reviewed":
        return (
            set(author) == {"displayName", "email", "evidence", "status"}
            and type(author.get("displayName")) is str
            and 1 <= len(author["displayName"]) <= 256
            and type(author.get("email")) is str
            and 3 <= len(author["email"]) <= 254
            and author.get("evidence") == "frozen-patch-mail-header"
        )
    if status == "unresolved":
        return set(author).issubset(
            {"displayName", "email", "evidence", "status"}
        ) and all(
            author.get(optional) is None
            for optional in ("displayName", "email", "evidence")
            if optional in author
        )
    return False


def _independent_patch_dependencies(
    dependencies: object, asset: dict[str, object]
) -> list[dict[str, str]]:
    if type(dependencies) is not list or len(dependencies) > 128:
        raise ValueError("patch review dependency evidence is invalid")
    keys: list[tuple[str, str]] = []
    for dependency in dependencies:
        if (
            type(dependency) is not dict
            or set(dependency) != {"kind", "value"}
            or dependency.get("kind")
            not in {
                "patch-license",
                "external-dependency",
                "development-dependency",
            }
            or not _independent_patch_text(dependency.get("value"), 2048)
            or (
                dependency["kind"] in {"patch-license", "external-dependency"}
                and PATCH_HTTPS_EVIDENCE.fullmatch(dependency["value"]) is None
            )
        ):
            raise ValueError("patch review dependency evidence is invalid")
        keys.append((dependency["kind"], dependency["value"]))
    if keys != sorted(set(keys)):
        raise ValueError("patch review dependency evidence is invalid")
    external_refs = asset.get("externalRefs")
    development_dependencies = asset.get("developmentDependencies")
    if type(external_refs) is not list or type(development_dependencies) is not list:
        raise ValueError("patch source dependency evidence is invalid")
    expected = [
        {"kind": "development-dependency", "value": value}
        for value in development_dependencies
    ] + [
        {"kind": "external-dependency", "value": value}
        for value in external_refs
    ]
    expected.sort(key=lambda item: (item["kind"], item["value"]))
    if dependencies != expected:
        raise ValueError("patch source dependency evidence is invalid")
    return expected


def _independent_patch_preimages(
    preimages: object,
    source_metadata: tuple[tuple[str, str | None], ...],
) -> dict[str, int]:
    if type(preimages) is not list or not 1 <= len(preimages) <= 128:
        raise ValueError("patch review base evidence is invalid")
    paths: list[str] = []
    old_blobs: list[tuple[str, str | None]] = []
    counts = {"matched": 0, "mismatched": 0, "added": 0, "unproven": 0}
    for preimage in preimages:
        if (
            type(preimage) is not dict
            or set(preimage)
            != {"path", "patchOldBlob", "upstreamBlobOid", "result"}
            or not _independent_patch_relative_path(preimage.get("path"))
            or preimage.get("result") not in counts
        ):
            raise ValueError("patch review base evidence is invalid")
        path = preimage["path"]
        result = preimage["result"]
        patch_old = preimage["patchOldBlob"]
        upstream = preimage["upstreamBlobOid"]
        if result in {"matched", "mismatched"}:
            if (
                type(patch_old) is not str
                or PATCH_GIT_PREFIX.fullmatch(patch_old) is None
                or type(upstream) is not str
                or PATCH_GIT_OID.fullmatch(upstream) is None
                or (result == "matched") != upstream.startswith(patch_old)
            ):
                raise ValueError("patch review base evidence is invalid")
        elif result == "added":
            if (
                type(patch_old) is not str
                or PATCH_ZERO_GIT_PREFIX.fullmatch(patch_old) is None
                or upstream is not None
            ):
                raise ValueError("patch review base evidence is invalid")
        elif (
            patch_old is not None
            and (
                type(patch_old) is not str
                or PATCH_ANY_GIT_PREFIX.fullmatch(patch_old) is None
            )
        ) or (
            upstream is not None
            and (
                type(upstream) is not str
                or PATCH_GIT_OID.fullmatch(upstream) is None
            )
        ):
            raise ValueError("patch review base evidence is invalid")
        paths.append(path)
        old_blobs.append((path, patch_old))
        counts[result] += 1
    if (
        paths != sorted(paths, key=lambda value: value.encode("ascii"))
        or len({path.casefold() for path in paths}) != len(paths)
        or tuple(old_blobs) != source_metadata
    ):
        raise ValueError("patch review base evidence is invalid")
    return counts


def _independent_patch_review_oracle(
    source_binding: object,
    review_raw: bytes,
    documents: dict[str, bytes],
) -> None:
    """Rebuild the exact patch decision without converter policy callbacks."""

    if (
        type(review_raw) is not bytes
        or hashlib.sha256(review_raw).hexdigest() != PATCH_REVIEW_DOCUMENT_SHA256
        or type(documents) is not dict
        or set(documents) != TASK6_EVIDENCE_PATHS
    ):
        raise ValueError("patch review evidence is invalid")
    review = _canonical_patch_review_json(review_raw)
    if set(review) != {"schemaVersion", "source", "recordCount", "records"}:
        raise ValueError("patch review evidence is invalid")
    review_records = review.get("records")
    if (
        review.get("schemaVersion") != "1"
        or review.get("source") != PATCH_REVIEW_SOURCE
        or review.get("recordCount") != 11
        or type(review_records) is not list
        or len(review_records) != 11
    ):
        raise ValueError("patch review evidence is invalid")
    manifest = source_binding.manifest
    assets = manifest.get("assets") if type(manifest) is dict else None
    if type(assets) is not list or len(assets) != 90:
        raise ValueError("patch review source evidence is invalid")
    patch_assets = sorted(
        (
            asset
            for asset in assets
            if type(asset) is dict and asset.get("category") == "patches"
        ),
        key=lambda asset: asset["sourcePath"].encode("ascii"),
    )
    if len(patch_assets) != 11:
        raise ValueError("patch review source evidence is invalid")
    if any(type(record) is not dict for record in review_records):
        raise ValueError("patch review coverage is invalid")
    review_paths = [record.get("sourcePath") for record in review_records]
    expected_paths = [asset["sourcePath"] for asset in patch_assets]
    if (
        any(type(path) is not str for path in review_paths)
        or review_paths != expected_paths
        or review_paths != sorted(review_paths, key=lambda value: value.encode("ascii"))
        or len({path.casefold() for path in review_paths}) != 11
        or set(PATCH_APPLICATIONS) != set(expected_paths)
    ):
        raise ValueError("patch review coverage is invalid")

    expected_mapping: list[dict[str, object]] = []
    expected_quarantine: list[dict[str, object]] = []
    preimage_evidence: list[dict[str, object]] = []
    preimage_count = 0
    record_fields = {
        "sourcePath",
        "sourceSha256",
        "gitBlobOid",
        "gitMode",
        "byteSize",
        "subject",
        "purpose",
        "affectedApplications",
        "upstream",
        "preimages",
        "patchAuthor",
        "projectLicense",
        "patchLicense",
        "evidenceAndDependencies",
        "upstreamStatus",
        "reviewDisposition",
        "reason",
        "releaseCondition",
        "regressionProbeIds",
    }
    for record, asset in zip(review_records, patch_assets, strict=True):
        if type(record) is not dict or set(record) != record_fields:
            raise ValueError("patch review record is invalid")
        path = record["sourcePath"]
        if (
            record.get("sourceSha256") != asset.get("sha256")
            or record.get("gitBlobOid") != asset.get("gitBlobOid")
            or record.get("gitMode") != asset.get("gitMode")
            or record.get("byteSize") != asset.get("byteSize")
            or type(record.get("byteSize")) is not int
            or not 1 <= record["byteSize"] <= 1024 * 1024
            or not _independent_patch_text(record.get("purpose"), 2048)
            or record.get("upstreamStatus") != "unresolved"
            or record.get("reviewDisposition") != "quarantined"
            or record.get("reason") != "missing-license"
            or record.get("releaseCondition") != PATCH_MISSING_LICENSE_RELEASE
            or record.get("regressionProbeIds") != []
            or record.get("patchLicense") != {"status": "unresolved"}
        ):
            raise ValueError("patch review record is invalid")
        expected_upstream = (
            PATCH_UPSTREAM_JASP
            if path.startswith("patches/jasp-")
            else PATCH_UPSTREAM_WINE
            if path.startswith("patches/wine-")
            else None
        )
        if expected_upstream is None or record.get("upstream") != expected_upstream:
            raise ValueError("patch review upstream evidence is invalid")
        expected_subject, expected_author, patch_raw = _independent_patch_mail_identity(
            source_binding, asset
        )
        subject = record.get("subject")
        if (
            subject != expected_subject
            or (
                subject is not None
                and not _independent_patch_text(subject, 256)
            )
        ):
            raise ValueError("patch review subject evidence is invalid")
        author = record.get("patchAuthor")
        if not _independent_patch_author(author) or author != expected_author:
            raise ValueError("patch review author evidence is invalid")
        applications = record.get("affectedApplications")
        expected_applications = PATCH_APPLICATIONS.get(path)
        if (
            type(applications) is not list
            or not 1 <= len(applications) <= 32
            or any(
                type(item) is not str or PATCH_IDENTIFIER.fullmatch(item) is None
                for item in applications
            )
            or applications
            != sorted(set(applications), key=lambda value: value.encode("ascii"))
            or tuple(applications) != expected_applications
        ):
            raise ValueError("patch review application evidence is invalid")
        preimages = record.get("preimages")
        source_metadata = _independent_patch_diff_metadata(patch_raw)
        base_counts = _independent_patch_preimages(preimages, source_metadata)
        preimage_evidence.append(
            {
                "sourcePath": path,
                "preimages": [
                    {
                        "path": preimage["path"],
                        "result": preimage["result"],
                        "upstreamBlobOid": preimage["upstreamBlobOid"],
                    }
                    for preimage in preimages
                ],
            }
        )
        preimage_count += len(preimages)
        project_license = record.get("projectLicense")
        expected_project_license = (
            {
                "contextOnly": True,
                "evidenceLocator": (
                    "https://github.com/jasp-stats/jasp-desktop/blob/"
                    "28be3fee5c7ce2119f1945acd0254eb4fb8cb6e2/"
                    "Docs/development/jasp-licensing.md"
                ),
                "spdxExpression": "AGPL-3.0-or-later",
            }
            if path.startswith("patches/jasp-")
            else {
                "contextOnly": True,
                "evidenceLocator": (
                    "https://gitlab.winehq.org/wine/wine/-/blob/"
                    "f6c044e1890e84a4aa5e77e76ba7276a615630e1/LICENSE"
                ),
                "spdxExpression": "LGPL-2.1-or-later",
            }
        )
        if project_license != expected_project_license:
            raise ValueError("patch review project license is invalid")
        dependencies = _independent_patch_dependencies(
            record.get("evidenceAndDependencies"), asset
        )
        expected_mapping.append(
            {
                "sourceRepository": TASK5_SOURCE_REPOSITORY,
                "sourcePath": path,
                "sourceCommit": asset["sourceCommit"],
                "gitBlobOid": asset["gitBlobOid"],
                "gitMode": asset["gitMode"],
                "sourceSha256": asset["sha256"],
                "category": "patches",
                "status": "quarantined",
                "targetIssue": "MW-ASSET-002",
                "intendedOwner": "compatforge/patches",
                "license": asset["license"],
                "provenance": asset["provenance"],
                "purpose": record["purpose"],
                "affectedApplications": applications,
                "upstream": expected_upstream,
                "baseEvidence": base_counts,
                "patchAuthor": author,
                "projectLicense": project_license,
                "patchLicense": {"status": "unresolved"},
                "evidenceAndDependencies": dependencies,
                "upstreamStatus": "unresolved",
                "reviewDisposition": "quarantined",
                "reason": "missing-license",
                "releaseCondition": PATCH_MISSING_LICENSE_RELEASE,
                "regressionProbeIds": [],
            }
        )
        expected_quarantine.append(
            {
                "sourcePath": path,
                "sourceCommit": asset["sourceCommit"],
                "sourceSha256": asset["sha256"],
                "category": "patches",
                "status": "quarantined",
                "reason": "missing-license",
                "evidenceLocators": [f"{path}#patchLicense"],
                "intendedOwner": "compatforge/patches",
                "releaseCondition": PATCH_MISSING_LICENSE_RELEASE,
            }
        )

    preimage_evidence_raw = json.dumps(
        preimage_evidence,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if (
        len(preimage_evidence) != PATCH_PREIMAGE_RECORD_COUNT
        or preimage_count != PATCH_PREIMAGE_COUNT
        or hashlib.sha256(preimage_evidence_raw).hexdigest()
        != PATCH_PREIMAGE_EVIDENCE_SHA256
    ):
        raise ValueError("patch review canonical preimage evidence is invalid")

    mapping_raw = documents.get(
        "migration/macwin/generated/mappings/patches.json"
    )
    quarantine_raw = documents.get("migration/macwin/generated/quarantine.json")
    if (
        type(mapping_raw) is not bytes
        or hashlib.sha256(mapping_raw).hexdigest()
        != TASK6_DOCUMENT_SHA256[
            "migration/macwin/generated/mappings/patches.json"
        ]
        or type(quarantine_raw) is not bytes
        or hashlib.sha256(quarantine_raw).hexdigest()
        != TASK5_DOCUMENT_SHA256["migration/macwin/generated/quarantine.json"]
    ):
        raise ValueError("patch generated evidence digest is invalid")
    mapping = _canonical_task5_json(mapping_raw)
    quarantine = _canonical_task5_json(quarantine_raw)
    quarantine_records = quarantine.get("records")
    if (
        mapping
        != {"schemaVersion": "1", "records": expected_mapping}
        or type(quarantine_records) is not list
        or len(quarantine_records) != 84
        or [item.get("sourcePath") for item in quarantine_records if type(item) is dict]
        != sorted(
            (item.get("sourcePath") for item in quarantine_records if type(item) is dict),
            key=lambda value: value.encode("ascii"),
        )
        or [
            item
            for item in quarantine_records
            if type(item) is dict and item.get("category") == "patches"
        ]
        != expected_quarantine
    ):
        raise ValueError("patch generated evidence semantics are invalid")
    if {
        "converted": 2,
        "deferred": 4,
        "quarantined": 84,
    } != {
        "converted": 2,
        "deferred": sum(asset.get("category") == "bottle-schema" for asset in assets),
        "quarantined": len(assets) - 2 - sum(
            asset.get("category") == "bottle-schema" for asset in assets
        ),
    }:
        raise ValueError("patch migration status counts are invalid")


def _independent_task5_oracle(
    source_binding: object,
    documents: dict[str, bytes],
) -> None:
    """Authenticate the fixed real Task 5 ledger without converter callbacks."""

    if type(documents) is not dict or set(documents) != TASK5_DOCUMENT_PATHS:
        raise ValueError("generated evidence set is invalid")
    for relative, expected_digest in TASK5_DOCUMENT_SHA256.items():
        raw = documents.get(relative)
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError("generated evidence digest is invalid")
    catalog = _canonical_task5_json(
        documents["migration/macwin/generated/catalog.json"]
    )
    quarantine = _canonical_task5_json(
        documents["migration/macwin/generated/quarantine.json"]
    )
    manifest = source_binding.manifest
    if (
        type(manifest) is not dict
        or manifest.get("repository") != TASK5_SOURCE_REPOSITORY
        or manifest.get("sourceCommit") != TASK5_SOURCE_COMMIT
        or type(manifest.get("assets")) is not list
    ):
        raise ValueError("source evidence identity is invalid")
    assets = {
        item["sourcePath"]: item
        for item in manifest["assets"]
        if type(item) is dict and type(item.get("sourcePath")) is str
    }
    recipe_paths = sorted(
        (
            path
            for path in assets
            if path.startswith(f"{TASK5_CATALOG_ROOT}/recipes/")
        ),
        key=lambda value: value.encode("ascii"),
    )
    if len(recipe_paths) != 17:
        raise ValueError("source recipe coverage is invalid")
    expected_candidates: list[dict[str, object]] = []
    expected_records: list[dict[str, object]] = []
    for path in recipe_paths:
        asset = assets[path]
        raw = source_binding.verify_path(
            source_binding.root / PurePosixPath(asset["objectPath"])
        )
        try:
            source = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("source recipe JSON is invalid") from None
        if (
            type(source) is not dict
            or type(source.get("id")) is not str
            or type(source.get("name")) is not str
            or asset.get("category") != "catalog"
            or asset.get("intendedOwner") != "compatforge/catalog"
            or asset.get("sourceCommit") != TASK5_SOURCE_COMMIT
            or asset.get("license") != {"status": "unresolved"}
            or asset.get("provenance") != {"status": "unresolved"}
        ):
            raise ValueError("source recipe evidence is invalid")
        expected_candidates.append(
            {
                "id": source["id"],
                "name": source["name"],
                "reason": "missing-license",
                "sourceCommit": TASK5_SOURCE_COMMIT,
                "sourcePath": path,
                "sourceSha256": asset["sha256"],
                "status": "quarantined",
            }
        )
        expected_records.append(
            {
                "sourcePath": path,
                "sourceCommit": TASK5_SOURCE_COMMIT,
                "sourceSha256": asset["sha256"],
                "category": "catalog",
                "status": "quarantined",
                "reason": "missing-license",
                "intendedOwner": "compatforge/catalog",
            }
        )
    if (
        set(catalog)
        != {
            "schemaVersion", "sourceRepository", "sourceCommit", "catalogBoundary",
            "candidateCount", "convertedCount", "quarantinedCount", "candidates",
        }
        or catalog.get("schemaVersion") != "1"
        or catalog.get("sourceRepository") != TASK5_SOURCE_REPOSITORY
        or catalog.get("sourceCommit") != TASK5_SOURCE_COMMIT
        or catalog.get("candidateCount") != 17
        or catalog.get("convertedCount") != 0
        or catalog.get("quarantinedCount") != 17
        or catalog.get("candidates") != expected_candidates
    ):
        raise ValueError("generated catalog semantics are invalid")
    boundary = catalog["catalogBoundary"]
    if type(boundary) is not dict or set(boundary) != {"index", "signature"}:
        raise ValueError("generated catalog boundary is invalid")
    for label, path in (("index", TASK5_CATALOG_INDEX), ("signature", TASK5_CATALOG_SIGNATURE)):
        asset = assets.get(path)
        if boundary.get(label) != {
            "sourceCommit": TASK5_SOURCE_COMMIT,
            "sourcePath": path,
            "sourceSha256": asset.get("sha256") if type(asset) is dict else None,
        }:
            raise ValueError("generated catalog boundary is invalid")
    records = quarantine.get("records")
    if (
        set(quarantine) != {"schemaVersion", "records"}
        or quarantine.get("schemaVersion") != "1"
        or type(records) is not list
        or len(records) != 84
    ):
        raise ValueError("generated quarantine semantics are invalid")
    catalog_records = {
        record.get("sourcePath"): record
        for record in records
        if type(record) is dict and record.get("category") == "catalog"
    }
    if set(catalog_records) != {
        record["sourcePath"] for record in expected_records
    }:
        raise ValueError("generated quarantine catalog coverage is invalid")
    for expected in expected_records:
        actual = catalog_records[expected["sourcePath"]]
        if (
            type(actual) is not dict
            or set(actual)
            != {
                "sourcePath", "sourceCommit", "sourceSha256", "category", "status",
                "reason", "evidenceLocators", "intendedOwner", "releaseCondition",
            }
            or any(actual.get(key) != value for key, value in expected.items())
            or type(actual.get("evidenceLocators")) is not list
            or not actual["evidenceLocators"]
            or actual["evidenceLocators"]
            != sorted(set(actual["evidenceLocators"]), key=lambda value: value.encode("utf-8"))
            or f'{actual["sourcePath"]}#license' not in actual["evidenceLocators"]
            or actual.get("releaseCondition")
            != "Record a reviewed source license and regenerate the migration."
        ):
            raise ValueError("generated quarantine record is invalid")


def _independent_task6_oracle(
    source_binding: object,
    review_raw: bytes,
    documents: dict[str, bytes],
) -> None:
    """Independently close every real Task 6 mapping and quarantine decision."""

    if type(documents) is not dict or set(documents) != TASK6_EVIDENCE_PATHS:
        raise ValueError("generated evidence set is invalid")
    for relative, expected_digest in TASK6_DOCUMENT_SHA256.items():
        raw = documents.get(relative)
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != expected_digest:
            raise ValueError("Task 6 generated evidence digest is invalid")
    manifest = source_binding.manifest
    assets = manifest.get("assets") if type(manifest) is dict else None
    if type(assets) is not list:
        raise ValueError("source evidence identity is invalid")
    by_category: dict[str, list[dict[str, object]]] = {
        "patches": [],
        "bottle-schema": [],
        "probes": [],
        "fixtures": [],
    }
    for asset in assets:
        if type(asset) is not dict:
            raise ValueError("source evidence identity is invalid")
        category = asset.get("category")
        if category in by_category:
            by_category[category].append(asset)
    if {key: len(value) for key, value in by_category.items()} != {
        "patches": 11,
        "bottle-schema": 4,
        "probes": 26,
        "fixtures": 30,
    }:
        raise ValueError("Task 6 source coverage is invalid")

    bottle_relative = "migration/macwin/generated/mappings/bottle-schemas.json"
    bottle_mapping = _canonical_task5_json(documents[bottle_relative])
    expected_bottles = [
        {
            "sourceRepository": TASK5_SOURCE_REPOSITORY,
            "sourcePath": asset["sourcePath"],
            "sourceCommit": asset["sourceCommit"],
            "gitBlobOid": asset["gitBlobOid"],
            "gitMode": asset["gitMode"],
            "sourceSha256": asset["sha256"],
            "category": "bottle-schema",
            "status": "deferred",
            "targetIssue": "MW-ASSET-003",
            "intendedOwner": "compatforge/bottle-schema",
            "license": asset["license"],
            "provenance": asset["provenance"],
        }
        for asset in by_category["bottle-schema"]
    ]
    if bottle_mapping != {"schemaVersion": "1", "records": expected_bottles}:
        raise ValueError("deferred Bottle mapping semantics are invalid")

    _independent_patch_review_oracle(source_binding, review_raw, documents)

    quarantine = _canonical_task5_json(
        documents["migration/macwin/generated/quarantine.json"]
    )
    records = quarantine.get("records")
    if type(records) is not list or len(records) != 84:
        raise ValueError("Task 6 quarantine coverage is invalid")
    task6_assets = sorted(
        (*by_category["probes"], *by_category["fixtures"]),
        key=lambda asset: asset["sourcePath"].encode("ascii"),
    )
    task6_records = {
        record.get("sourcePath"): record
        for record in records
        if type(record) is dict
        and record.get("category") in {"probes", "fixtures"}
    }
    if set(task6_records) != {asset["sourcePath"] for asset in task6_assets}:
        raise ValueError("Task 6 quarantine coverage is invalid")
    for asset in task6_assets:
        record = task6_records[asset["sourcePath"]]
        evidence = sorted(
            {
                f'{asset["sourcePath"]}#license',
                f'{asset["sourcePath"]}#provenance',
                *asset["externalRefs"],
                *asset["developmentDependencies"],
            },
            key=lambda value: value.encode("utf-8"),
        )
        expected = {
            "sourcePath": asset["sourcePath"],
            "sourceCommit": asset["sourceCommit"],
            "sourceSha256": asset["sha256"],
            "category": asset["category"],
            "status": "quarantined",
            "reason": "missing-license",
            "evidenceLocators": evidence,
            "intendedOwner": asset["intendedOwner"],
            "releaseCondition": "Record a reviewed source license and regenerate the migration.",
        }
        if record != expected:
            raise ValueError("Task 6 quarantine semantics are invalid")


def _independent_task7_oracle(
    source_binding: object,
    documents: dict[str, bytes],
) -> None:
    """Independently authenticate the fixed real Task 7 root seal."""

    if type(documents) is not dict or set(documents) != GENERATED_EVIDENCE_PATHS:
        raise ValueError("generated graph set is invalid")
    raw = documents["migration/macwin/generated/index.json"]
    if hashlib.sha256(raw).hexdigest() != TASK7_DOCUMENT_SHA256[
        "migration/macwin/generated/index.json"
    ]:
        raise ValueError("Task 7 generated graph digest is invalid")
    root = _canonical_task5_json(raw)
    manifest = source_binding.manifest
    assets = manifest.get("assets") if type(manifest) is dict else None
    if type(assets) is not list or len(assets) != 90:
        raise ValueError("Task 7 source coverage is invalid")
    expected_source = {
        "repository": TASK5_SOURCE_REPOSITORY,
        "sourceTag": "mw-migration-baseline-db12d5e",
        "sourceTagObject": "9f10d003382ce7ffbb269376c03477e17516302f",
        "sourceCommit": TASK5_SOURCE_COMMIT,
        "inventoryCommit": "97f8423094d25325d8f864eb6f49a9e8628dbb93",
        "digestAlgorithm": "sha256",
    }
    expected_document_kinds = {
        "migration/macwin/generated/catalog.json": "catalog",
        "migration/macwin/generated/mappings/bottle-schemas.json": "deferred-mapping",
        "migration/macwin/generated/mappings/patches.json": "deferred-mapping",
        "migration/macwin/generated/quarantine.json": "quarantine",
    }
    expected_documents = [
        {
            "path": path,
            "kind": expected_document_kinds[path],
            "byteSize": len(documents[path]),
            "sha256": hashlib.sha256(documents[path]).hexdigest(),
            "references": [],
        }
        for path in sorted(expected_document_kinds, key=lambda value: value.encode("ascii"))
    ]
    expected_records: list[dict[str, object]] = []
    category_counts = {
        "bottle-schema": 0,
        "catalog": 0,
        "fixtures": 0,
        "patches": 0,
        "probes": 0,
    }
    status_counts = {"converted": 0, "deferred": 0, "quarantined": 0}
    for asset in sorted(assets, key=lambda item: item["sourcePath"].encode("ascii")):
        if type(asset) is not dict:
            raise ValueError("Task 7 source identity is invalid")
        category = asset.get("category")
        path = asset.get("sourcePath")
        if category not in category_counts or type(path) is not str:
            raise ValueError("Task 7 source identity is invalid")
        category_counts[category] += 1
        if path in {TASK5_CATALOG_INDEX, TASK5_CATALOG_SIGNATURE}:
            status = "converted"
            document_path = "migration/macwin/generated/catalog.json"
        elif category == "catalog" or category in {"fixtures", "probes"}:
            status = "quarantined"
            document_path = "migration/macwin/generated/quarantine.json"
        elif category == "patches":
            status = "quarantined"
            document_path = "migration/macwin/generated/quarantine.json"
        elif category == "bottle-schema":
            status = "deferred"
            document_path = "migration/macwin/generated/mappings/bottle-schemas.json"
        else:
            raise ValueError("Task 7 source classification is invalid")
        status_counts[status] += 1
        expected_records.append(
            {
                "sourcePath": path,
                "sourceCommit": asset.get("sourceCommit"),
                "sourceSha256": asset.get("sha256"),
                "category": category,
                "status": status,
                "documentPath": document_path,
            }
        )
    if (
        set(root)
        != {
            "schemaVersion", "source", "recordCount", "categoryCounts",
            "statusCounts", "documentCount", "documents", "records",
        }
        or root.get("schemaVersion") != "1"
        or root.get("source") != expected_source
        or root.get("recordCount") != 90
        or root.get("categoryCounts")
        != {
            "bottleSchema": 4,
            "catalog": 19,
            "fixtures": 30,
            "patches": 11,
            "probes": 26,
        }
        or category_counts
        != {"bottle-schema": 4, "catalog": 19, "fixtures": 30, "patches": 11, "probes": 26}
        or root.get("statusCounts") != status_counts
        or status_counts != {"converted": 2, "deferred": 4, "quarantined": 84}
        or root.get("documentCount") != 4
        or root.get("documents") != expected_documents
        or root.get("records") != expected_records
    ):
        raise ValueError("Task 7 generated graph semantics are invalid")


def _validated_macwin_generated_evidence_binding(
    source_binding: object,
    patch_review_binding: _PatchReviewBinding,
) -> tuple[
    _GeneratedEvidenceBinding | None, list[str]
]:
    """Rebuild, compare, and bind the complete Task 7 generated graph."""

    try:
        converter, converter_path, converter_raw, converter_identity = (
            _load_task5_converter()
        )
        expected = converter.render_documents(converter.build_conversion(ROOT))
        if type(expected) is not dict or set(expected) != GENERATED_EVIDENCE_PATHS:
            raise ValueError("generated evidence set is invalid")
        selected = {relative: expected[relative] for relative in GENERATED_EVIDENCE_PATHS}
        if any(
            type(raw) is not bytes or len(raw) > MAX_TASK5_DOCUMENT_BYTES
            for raw in selected.values()
        ):
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
        directories = _bind_exact_generated_tree(generated_root)
        leaves: dict[
            Path, tuple[bytes, tuple[int, int, int, int, int, int]]
        ] = {}
        committed: dict[str, bytes] = {}
        for relative in sorted(selected, key=lambda value: value.encode("ascii")):
            path = (ROOT / PurePosixPath(relative)).absolute()
            raw, identity = _read_bound_regular_file(path, MAX_TASK5_DOCUMENT_BYTES)
            if raw != selected[relative] or hashlib.sha256(raw).digest() != hashlib.sha256(selected[relative]).digest():
                raise ValueError("generated evidence bytes do not match")
            leaves[path] = (raw, identity)
            committed[relative] = raw
        _independent_task5_oracle(
            source_binding,
            {relative: committed[relative] for relative in TASK5_DOCUMENT_PATHS},
        )
        _independent_task6_oracle(
            source_binding,
            patch_review_binding.raw,
            {relative: committed[relative] for relative in TASK6_EVIDENCE_PATHS},
        )
        _independent_task7_oracle(source_binding, committed)
        if len(leaves) != 5:
            raise ValueError("generated evidence leaf set is invalid")
        binding = _GeneratedEvidenceBinding(
            generated_root,
            root_identity,
            selected,
            leaves,
            directories,
            converter,
            converter_path,
            converter_raw,
            converter_identity,
            patch_review_binding,
        )
        binding.revalidate()
    except (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None, ["Mac-Win generated evidence validation failed"]
    return binding, []


def _scan_developer_paths(
    source_binding: object | None,
    generated_binding: _GeneratedEvidenceBinding | None = None,
    patch_review_binding: _PatchReviewBinding | None = None,
) -> tuple[list[str], _OrdinaryFileBinding]:
    errors: list[str] = []
    ordinary_binding = _OrdinaryFileBinding()
    forbidden = ("/Users/a1-6/", "/home/a1-6/")
    paths: list[Path] = []
    try:
        for path in ROOT.rglob("*"):
            if ".git" in path.parts:
                continue
            if len(paths) >= MAX_ORDINARY_SCAN_ENTRIES:
                raise _DeveloperPathScanError()
            paths.append(path)
        paths.sort()
    except _DeveloperPathScanError:
        raise
    except OSError:
        raise _DeveloperPathScanError() from None
    entries: list[tuple[Path, str, tuple[int, int, int, int, int, int] | None]] = []
    expected_children: dict[Path, list[tuple[str, str]]] = {
        ROOT.absolute(): []
    }
    for path in paths:
        try:
            metadata = path.lstat()
            kind = _ordinary_entry_kind(metadata)
        except _DeveloperPathScanError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError):
            raise _DeveloperPathScanError() from None
        absolute = path.absolute()
        entries.append(
            (
                absolute,
                kind,
                _filesystem_identity(metadata) if kind == "regular" else None,
            )
        )
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

    unique_bytes = 0
    for path, kind, enumerated_identity in entries:
        if kind == "directory":
            continue
        if source_binding is not None and source_binding.contains(path):
            source_binding.verify_path(path)
            continue
        if generated_binding is not None and generated_binding.contains(path):
            generated_binding.verify_path(path)
            continue
        if patch_review_binding is not None and patch_review_binding.contains(path):
            patch_review_binding.verify_path(path)
            continue
        if path == Path(__file__).absolute():
            continue
        if enumerated_identity is None:
            raise _DeveloperPathScanError()
        key = enumerated_identity[:2]
        if key in ordinary_binding.contents:
            try:
                _validate_bound_path_chain(path)
                current = path.lstat()
            except (OSError, RuntimeError, TypeError, ValueError):
                raise _DeveloperPathScanError() from None
            identity = _filesystem_identity(current)
            if _ordinary_entry_kind(current) != "regular" or identity != enumerated_identity:
                raise _DeveloperPathScanError()
            raw = ordinary_binding.add_alias(path, identity)
        else:
            unique_bytes += enumerated_identity[2]
            if unique_bytes > MAX_ORDINARY_SCAN_TOTAL_BYTES:
                raise _DeveloperPathScanError()
            try:
                raw, identity = _read_bound_regular_file(
                    path,
                    MAX_ORDINARY_SCAN_BYTES,
                    require_single_link=False,
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                raise _DeveloperPathScanError() from None
            if identity != enumerated_identity:
                raise _DeveloperPathScanError()
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
        errors, binding = _scan_developer_paths(None, None, None)
        binding.revalidate()
    except _DeveloperPathScanError:
        return [DEVELOPER_PATH_VALIDATION_ERROR]
    return errors


def validate_no_developer_paths() -> list[str]:
    source_binding, errors = _validated_macwin_source_pack_binding()
    if source_binding is None:
        return [*errors, *_unbound_developer_path_scan()]
    patch_review_binding, patch_review_errors = _validated_patch_review_binding()
    if patch_review_binding is None:
        try:
            scanned_errors, ordinary_binding = _scan_developer_paths(
                source_binding, None, None
            )
            source_binding.revalidate()
            ordinary_binding.revalidate()
            source_binding.revalidate()
        except (_DeveloperPathScanError, OSError, RuntimeError, TypeError, ValueError):
            return [*patch_review_errors, DEVELOPER_PATH_VALIDATION_ERROR]
        return [*patch_review_errors, *scanned_errors]
    generated_binding, generated_errors = (
        _validated_macwin_generated_evidence_binding(
            source_binding, patch_review_binding
        )
    )
    if generated_binding is None:
        try:
            scanned_errors, ordinary_binding = _scan_developer_paths(
                source_binding, None, patch_review_binding
            )
            source_binding.revalidate()
            patch_review_binding.revalidate()
            ordinary_binding.revalidate()
            patch_review_binding.revalidate()
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
            source_binding, generated_binding, patch_review_binding
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
        patch_review_binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return [
            "Mac-Win patch review evidence validation failed",
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
        patch_review_binding.revalidate()
    except (OSError, RuntimeError, TypeError, ValueError):
        return [
            "Mac-Win patch review evidence validation failed",
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
