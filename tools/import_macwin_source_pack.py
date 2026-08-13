#!/usr/bin/env python3
"""Review-only importer for the frozen Mac-Win migration source pack."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
from typing import NoReturn


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK_ROOT = ROOT / "migration" / "macwin" / "source"

APPROVED_REPOSITORY = "a1112/Mac-Win"
APPROVED_SOURCE_TAG = "mw-migration-baseline-db12d5e"
APPROVED_SOURCE_TAG_OBJECT = "9f10d003382ce7ffbb269376c03477e17516302f"
APPROVED_SOURCE_COMMIT = "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527"
APPROVED_INVENTORY_COMMIT = "97f8423094d25325d8f864eb6f49a9e8628dbb93"
APPROVED_SOURCE_INDEX_SHA256 = (
    "1fc8b071a9c52c5f29d130e47e3bd1cb165effa860eaa45336c82ee07cafe3a3"
)

MAX_SOURCE_INDEX_BYTES = 1024 * 1024
MAX_SOURCE_OBJECT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_INVENTORY_DOCUMENT_BYTES = 64 * 1024
MAX_GIT_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_GIT_ERROR_BYTES = 64 * 1024
MAX_GIT_METADATA_LEAVES = 100_000
MAX_GIT_METADATA_BYTES = 512 * 1024 * 1024
MAX_GIT_REF_NODES = 2_048
GIT_TIMEOUT_SECONDS = 30

EXPECTED_CATEGORY_COUNTS = {
    "catalog": 19,
    "patches": 11,
    "probes": 26,
    "fixtures": 30,
    "bottleSchema": 4,
}
INVENTORY_CATEGORIES = {
    "bottle-schema": ("bottleSchema", "bottle-schema", 4),
    "catalog": ("catalog", "catalog-record", 19),
    "fixtures": ("fixtures", "test-fixture", 30),
    "patches": ("patches", "source-patch", 11),
    "probes": ("probes", "probe", 26),
}
INVENTORY_INDEX_PATH = "migration/assets/index.json"
INVENTORY_SHARD_PATHS = (
    "migration/assets/bottle-schema.json",
    "migration/assets/catalog.json",
    "migration/assets/fixtures.json",
    "migration/assets/patches.json",
    "migration/assets/probes.json",
    "migration/assets/dependencies.json",
)
INVENTORY_PATHS = (INVENTORY_INDEX_PATH, *INVENTORY_SHARD_PATHS)

_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_OWNER = re.compile(r"compatforge/[a-z0-9][a-z0-9._-]{0,116}\Z")
_INCLUDE_CONFIG = re.compile(
    rb"^[ \t]*(?:\[include(?:if)?(?:[ \t\"]|\])|"
    rb"include(?:if\.[^\r\n=]+)?\.path(?:[ \t]*=|[ \t]*$))",
    re.IGNORECASE | re.MULTILINE,
)


def _load_common():
    try:
        import macwin_asset_common as common

        return common
    except ModuleNotFoundError:
        path = Path(__file__).with_name("macwin_asset_common.py")
        spec = importlib.util.spec_from_file_location("macwin_asset_common", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("migration common module could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_COMMON = _load_common()


class SourcePackError(ValueError):
    """A stable, non-reflective source-pack failure."""


def _fail(message: str) -> NoReturn:
    raise SourcePackError(message)


@dataclass(frozen=True)
class GitBinding:
    repository: Path
    git_directory: Path
    source_tag: str
    tag_oid: str
    source_commit: str
    inventory_commit: str


@dataclass(frozen=True)
class SourcePackLeafBinding:
    path: Path
    identity: tuple[int, int, int, int, int, int]
    raw: bytes


class SourcePackBinding:
    """Bind the exact source-pack path identities and authenticated bytes."""

    def __init__(
        self,
        root: Path,
        root_identity: tuple[int, int, int, int, int, int],
        manifest: dict[str, object],
        leaves: dict[Path, SourcePackLeafBinding],
    ) -> None:
        self.root = root
        self.root_identity = root_identity
        self.manifest = manifest
        self._leaves = leaves

    def __enter__(self) -> SourcePackBinding:
        return self

    def __exit__(self, _kind, _value, _traceback) -> None:
        return None

    def contains(self, path: Path) -> bool:
        return path.absolute() in self._leaves

    def verify_path(self, path: Path) -> bytes:
        absolute = path.absolute()
        leaf = self._leaves.get(absolute)
        if leaf is None:
            _fail("source-pack binding path is not authenticated")
        before = _path_metadata(absolute)
        if _file_identity(before) != leaf.identity:
            _fail("source-pack binding identity changed")
        maximum = (
            MAX_SOURCE_INDEX_BYTES
            if absolute == self.root / "index.json"
            else MAX_SOURCE_OBJECT_BYTES
        )
        raw = _read_regular_file(absolute, maximum)
        after = _path_metadata(absolute)
        if _file_identity(after) != leaf.identity or raw != leaf.raw:
            _fail("source-pack binding content changed")
        return raw

    def revalidate(self) -> None:
        current_root = _path_metadata(self.root)
        if _file_identity(current_root) != self.root_identity:
            _fail("source-pack binding root changed")
        if validate_source_pack(self.root) != self.manifest:
            _fail("source-pack binding manifest changed")
        for path in sorted(self._leaves, key=lambda value: str(value).encode("utf-8")):
            self.verify_path(path)
        final_root = _path_metadata(self.root)
        if _file_identity(final_root) != self.root_identity:
            _fail("source-pack binding root changed")


def _safe_git_environment() -> dict[str, str]:
    allowed = {
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _run_git(
    repository: Path,
    arguments: tuple[str, ...],
    *,
    input_bytes: bytes | None = None,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    """Run one fixed local Git command without ambient repository controls."""

    root = repository.resolve(strict=True)
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        f"safe.directory={root}",
        "-c",
        "commit.gpgSign=false",
        "-c",
        "tag.gpgSign=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        *arguments,
    ]
    options: dict[str, object] = {
        "cwd": root,
        "check": False,
        "env": _safe_git_environment(),
        "executable": None,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
        "timeout": GIT_TIMEOUT_SECONDS,
    }
    if input_bytes is None:
        options["stdin"] = subprocess.DEVNULL
    else:
        if type(input_bytes) is not bytes or len(input_bytes) > MAX_GIT_OUTPUT_BYTES:
            _fail("Git batch input exceeds the limit")
        options["input"] = input_bytes
    try:
        completed = subprocess.run(command, **options)
    except (OSError, subprocess.TimeoutExpired):
        _fail("Git command failed")
    if (
        type(completed.stdout) is not bytes
        or type(completed.stderr) is not bytes
        or len(completed.stdout) > MAX_GIT_OUTPUT_BYTES
        or len(completed.stderr) > MAX_GIT_ERROR_BYTES
    ):
        _fail("Git command output exceeds the limit")
    if completed.returncode not in allowed_returncodes:
        _fail("Git command failed")
    return completed


def _path_metadata(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("filesystem boundary is invalid")
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_reparse_tag", 0):
        _fail("filesystem boundary is linked")
    return metadata


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _validate_path_chain(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        _path_metadata(current)


def _read_regular_file(
    path: Path,
    maximum: int,
    *,
    single_link: bool = True,
) -> bytes:
    before = _path_metadata(path)
    if not stat.S_ISREG(before.st_mode):
        _fail("filesystem leaf is not a regular file")
    if single_link and before.st_nlink != 1:
        _fail("filesystem leaf is hardlinked")
    if before.st_size > maximum:
        _fail("filesystem leaf exceeds the byte limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _fail("filesystem leaf could not be opened safely")
    try:
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or after.st_size != before.st_size
            or (single_link and after.st_nlink != 1)
        ):
            _fail("filesystem leaf identity changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            except OSError:
                _fail("filesystem leaf could not be read")
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _fail("filesystem leaf exceeds the byte limit")
            chunks.append(chunk)
        final = os.fstat(descriptor)
        if (
            (final.st_dev, final.st_ino, final.st_size)
            != (after.st_dev, after.st_ino, after.st_size)
            or (single_link and final.st_nlink != 1)
        ):
            _fail("filesystem leaf identity changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_git_tree(root: Path, *, maximum_nodes: int) -> None:
    pending = [root]
    nodes = 0
    total_bytes = 0
    while pending:
        directory = pending.pop()
        metadata = _path_metadata(directory)
        if not stat.S_ISDIR(metadata.st_mode):
            _fail("Git metadata directory is invalid")
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    nodes += 1
                    if nodes > maximum_nodes:
                        _fail("Git metadata exceeds the entry limit")
                    path = Path(entry.path)
                    item = _path_metadata(path)
                    if stat.S_ISDIR(item.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(item.st_mode):
                        if item.st_nlink != 1:
                            _fail("Git metadata leaf is hardlinked")
                        total_bytes += item.st_size
                        if total_bytes > MAX_GIT_METADATA_BYTES:
                            _fail("Git metadata exceeds the byte limit")
                    else:
                        _fail("Git metadata leaf is invalid")
        except OSError:
            _fail("Git metadata directory could not be read")


def _path_exists_without_following(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        _fail("Git metadata boundary is invalid")
    return True


def _validate_git_storage(repository: Path) -> Path:
    _validate_path_chain(repository)
    root_metadata = _path_metadata(repository)
    if not stat.S_ISDIR(root_metadata.st_mode):
        _fail("source repository is not a directory")
    git_directory = repository / ".git"
    git_metadata = _path_metadata(git_directory)
    if not stat.S_ISDIR(git_metadata.st_mode):
        _fail("source Git directory is not an owned directory")

    config = _read_regular_file(git_directory / "config", 64 * 1024)
    lowered = config.lower()
    if (
        _INCLUDE_CONFIG.search(config)
        or b"promisor" in lowered
        or b"partialclone" in lowered
        or b"objectformat" in lowered
        or _path_exists_without_following(git_directory / "config.worktree")
        or _path_exists_without_following(git_directory / "shallow")
        or _path_exists_without_following(git_directory / "objects/info/alternates")
    ):
        _fail("source Git storage uses an external boundary")

    objects = git_directory / "objects"
    refs = git_directory / "refs"
    _validate_git_tree(objects, maximum_nodes=MAX_GIT_METADATA_LEAVES)
    _validate_git_tree(refs, maximum_nodes=MAX_GIT_REF_NODES)
    for path in objects.rglob("*.promisor"):
        if _path_exists_without_following(path):
            _fail("source Git storage is a promisor store")
    replace_directory = refs / "replace"
    if _path_exists_without_following(replace_directory):
        _fail("source Git storage contains replace refs")
    packed_refs = git_directory / "packed-refs"
    if _path_exists_without_following(packed_refs):
        raw = _read_regular_file(packed_refs, 16 * 1024 * 1024)
        if b" refs/replace/" in raw:
            _fail("source Git storage contains replace refs")
    _read_regular_file(git_directory / "index", 64 * 1024 * 1024)
    return git_directory


def _one_line(completed: subprocess.CompletedProcess[bytes]) -> str:
    try:
        value = completed.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        _fail("Git returned an invalid identifier")
    if "\n" in value or "\r" in value or "\x00" in value:
        _fail("Git returned an invalid identifier")
    return value


def _git_object_oid(kind: str, raw: bytes) -> str:
    header = f"{kind} {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _cat_file_batch(
    repository: Path,
    object_ids: tuple[str, ...],
    *,
    per_object_limit: int,
    total_limit: int,
) -> tuple[tuple[str, str, bytes], ...]:
    if not object_ids or any(_HEX_40.fullmatch(value) is None for value in object_ids):
        _fail("Git object query is invalid")
    query = b"".join(value.encode("ascii") + b"\n" for value in object_ids)
    checked = _run_git(
        repository,
        ("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"),
        input_bytes=query,
    ).stdout
    lines = checked.splitlines()
    if len(lines) != len(object_ids):
        _fail("Git object batch metadata is incomplete")
    expected: list[tuple[str, str, int]] = []
    total = 0
    for requested, line in zip(object_ids, lines, strict=True):
        parts = line.split(b" ")
        if len(parts) != 3:
            _fail("Git object batch metadata is invalid")
        try:
            oid = parts[0].decode("ascii")
            kind = parts[1].decode("ascii")
            size = int(parts[2], 10)
        except (UnicodeDecodeError, ValueError, OverflowError):
            _fail("Git object batch metadata is invalid")
        if oid != requested or kind not in {"blob", "commit", "tag", "tree"}:
            _fail("Git object identity does not match")
        if size < 0 or size > per_object_limit:
            _fail("Git object exceeds the byte limit")
        total += size
        if total > total_limit:
            _fail("Git object batch exceeds the byte limit")
        expected.append((oid, kind, size))

    output = _run_git(
        repository,
        ("cat-file", "--batch=%(objectname) %(objecttype) %(objectsize)"),
        input_bytes=query,
    ).stdout
    offset = 0
    result: list[tuple[str, str, bytes]] = []
    for oid, kind, size in expected:
        newline = output.find(b"\n", offset)
        if newline < 0:
            _fail("Git object batch is incomplete")
        header = output[offset:newline]
        expected_header = f"{oid} {kind} {size}".encode("ascii")
        if header != expected_header:
            _fail("Git object batch identity changed")
        start = newline + 1
        end = start + size
        if end >= len(output) or output[end : end + 1] != b"\n":
            _fail("Git object batch is incomplete")
        raw = output[start:end]
        if _git_object_oid(kind, raw) != oid:
            _fail("Git object content does not match its identity")
        result.append((oid, kind, raw))
        offset = end + 1
    if offset != len(output):
        _fail("Git object batch contains trailing data")
    return tuple(result)


def _bind_repository(
    repository: Path,
    *,
    tag: str,
    tag_object: str,
    source_commit: str,
    inventory_commit: str,
) -> GitBinding:
    if (
        not isinstance(repository, Path)
        or type(tag) is not str
        or _TAG.fullmatch(tag) is None
        or type(source_commit) is not str
        or type(tag_object) is not str
        or _HEX_40.fullmatch(tag_object) is None
        or _HEX_40.fullmatch(source_commit) is None
        or type(inventory_commit) is not str
        or _HEX_40.fullmatch(inventory_commit) is None
    ):
        _fail("source Git identity is invalid")
    try:
        requested_root = repository.absolute()
        _validate_path_chain(requested_root)
        root = requested_root.resolve(strict=True)
    except OSError:
        _fail("source repository could not be resolved")
    git_directory = _validate_git_storage(root)

    reported_root = Path(
        _one_line(_run_git(root, ("rev-parse", "--show-toplevel")))
    ).resolve(strict=True)
    if reported_root != root:
        _fail("source repository root does not match")
    common_directory = _one_line(
        _run_git(root, ("rev-parse", "--path-format=absolute", "--git-common-dir"))
    )
    object_directory = _one_line(
        _run_git(root, ("rev-parse", "--path-format=absolute", "--git-path", "objects"))
    )
    index_path = _one_line(
        _run_git(root, ("rev-parse", "--path-format=absolute", "--git-path", "index"))
    )
    if (
        Path(common_directory).resolve(strict=True) != git_directory
        or Path(object_directory).resolve(strict=True) != git_directory / "objects"
        or Path(index_path).resolve(strict=True) != git_directory / "index"
    ):
        _fail("source Git storage identity does not match")
    if _one_line(_run_git(root, ("rev-parse", "--is-bare-repository"))) != "false":
        _fail("source repository must be a non-bare checkout")

    symbolic = _run_git(
        root,
        ("symbolic-ref", "-q", f"refs/tags/{tag}"),
        allowed_returncodes=(0, 1),
    )
    if symbolic.returncode == 0:
        _fail("source tag must not be symbolic")
    refs = _run_git(
        root,
        (
            "for-each-ref",
            "--format=%(refname)%00%(objecttype)%00%(objectname)%00%(*objectname)",
            "refs/tags/",
        ),
    ).stdout
    exact: tuple[str, str, str] | None = None
    folded_match = False
    for line in refs.splitlines():
        fields = line.split(b"\x00")
        if len(fields) != 4:
            _fail("source tag reference is invalid")
        try:
            refname, kind, oid, peeled = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeDecodeError:
            _fail("source tag reference is invalid")
        if refname.casefold() == f"refs/tags/{tag}".casefold():
            folded_match = True
        if refname == f"refs/tags/{tag}":
            exact = (kind, oid, peeled)
    if exact is None or not folded_match:
        _fail("source tag is missing")
    kind, tag_oid, peeled = exact
    if (
        kind != "tag"
        or tag_oid != tag_object
        or peeled != source_commit
    ):
        _fail("source tag is not the approved annotated tag")

    for oid in (source_commit, inventory_commit):
        if _one_line(_run_git(root, ("cat-file", "-t", oid))) != "commit":
            _fail("source Git commit identity is invalid")
    ancestry = _run_git(
        root,
        ("merge-base", "--is-ancestor", source_commit, inventory_commit),
        allowed_returncodes=(0, 1),
    )
    if ancestry.returncode != 0:
        _fail("source commit is not an ancestor of the inventory commit")

    objects = _cat_file_batch(
        root,
        (tag_oid, source_commit, inventory_commit),
        per_object_limit=1024 * 1024,
        total_limit=3 * 1024 * 1024,
    )
    tag_raw = objects[0][2]
    tag_lines = tag_raw.split(b"\n")
    if (
        f"object {source_commit}".encode("ascii") not in tag_lines[:4]
        or b"type commit" not in tag_lines[:4]
        or f"tag {tag}".encode("ascii") not in tag_lines[:4]
    ):
        _fail("source tag object does not match")

    return GitBinding(
        repository=root,
        git_directory=git_directory,
        source_tag=tag,
        tag_oid=tag_oid,
        source_commit=source_commit,
        inventory_commit=inventory_commit,
    )


def _parse_tree_entries(raw: bytes) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for entry in raw.split(b"\x00"):
        if not entry:
            continue
        try:
            metadata, path_raw = entry.split(b"\t", 1)
            mode, kind, oid = metadata.split(b" ", 2)
            path = path_raw.decode("ascii", errors="strict")
            mode_text = mode.decode("ascii")
            kind_text = kind.decode("ascii")
            oid_text = oid.decode("ascii")
        except (ValueError, UnicodeDecodeError):
            _fail("Git tree entry is invalid")
        if (
            path in result
            or kind_text != "blob"
            or _HEX_40.fullmatch(oid_text) is None
        ):
            _fail("Git tree entry is invalid")
        result[path] = (mode_text, oid_text)
    return result


def _parse_stage_entries(raw: bytes) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for entry in raw.split(b"\x00"):
        if not entry:
            continue
        try:
            metadata, path_raw = entry.split(b"\t", 1)
            mode, oid, stage = metadata.split(b" ", 2)
            path = path_raw.decode("ascii", errors="strict")
            mode_text = mode.decode("ascii")
            oid_text = oid.decode("ascii")
        except (ValueError, UnicodeDecodeError):
            _fail("Git index entry is invalid")
        if stage != b"0" or path in result or _HEX_40.fullmatch(oid_text) is None:
            _fail("Git index contains an unreviewed stage")
        result[path] = (mode_text, oid_text)
    return result


def _read_inventory_documents(binding: GitBinding) -> dict[str, bytes]:
    arguments = (
        "ls-tree",
        "-z",
        binding.inventory_commit,
        "--",
        *INVENTORY_PATHS,
    )
    tree = _parse_tree_entries(_run_git(binding.repository, arguments).stdout)
    if set(tree) != set(INVENTORY_PATHS):
        _fail("inventory commit does not contain the reviewed documents")
    if any(mode != "100644" for mode, _oid in tree.values()):
        _fail("inventory document mode is invalid")

    stage = _parse_stage_entries(
        _run_git(
            binding.repository,
            ("ls-files", "--stage", "-z", "--", *INVENTORY_PATHS),
        ).stdout
    )
    if stage != tree:
        _fail("stage-0 inventory does not match the inventory commit")

    ordered_oids = tuple(tree[path][1] for path in INVENTORY_PATHS)
    objects = _cat_file_batch(
        binding.repository,
        ordered_oids,
        per_object_limit=MAX_INVENTORY_DOCUMENT_BYTES,
        total_limit=len(INVENTORY_PATHS) * MAX_INVENTORY_DOCUMENT_BYTES,
    )
    documents: dict[str, bytes] = {}
    for path, (_oid, kind, raw) in zip(INVENTORY_PATHS, objects, strict=True):
        if kind != "blob":
            _fail("inventory document is not a blob")
        documents[path] = raw
    return documents


def _parse_json(raw: bytes, *, maximum: int) -> object:
    try:
        return _COMMON.parse_json_bytes(raw, label="source pack", max_bytes=maximum)
    except _COMMON.MigrationError:
        _fail("source-pack JSON is invalid")


def _require_exact_object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        _fail("source-pack object fields are invalid")
    return value


def _require_string(value: object, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail("source-pack string is invalid")
    return value


def _require_string_array(value: object) -> list[str]:
    if type(value) is not list or len(value) > 512:
        _fail("source-pack string array is invalid")
    seen: set[str] = set()
    for item in value:
        text = _require_string(item, 4096)
        if text in seen:
            _fail("source-pack string array is duplicated")
        seen.add(text)
    return value


def _validate_review_status(value: object) -> None:
    obj = _require_exact_object(value, {"status"})
    if obj["status"] != "unresolved":
        _fail("source-pack review status is invalid")


def _validate_manifest(value: object) -> dict[str, object]:
    manifest = _require_exact_object(
        value,
        {
            "schemaVersion",
            "repository",
            "sourceTag",
            "sourceTagObject",
            "sourceCommit",
            "inventoryCommit",
            "digestAlgorithm",
            "assetCount",
            "categoryCounts",
            "assets",
        },
    )
    if (
        manifest["schemaVersion"] != "1"
        or manifest["repository"] != APPROVED_REPOSITORY
        or manifest["sourceTag"] != APPROVED_SOURCE_TAG
        or manifest["sourceTagObject"] != APPROVED_SOURCE_TAG_OBJECT
        or manifest["sourceCommit"] != APPROVED_SOURCE_COMMIT
        or manifest["inventoryCommit"] != APPROVED_INVENTORY_COMMIT
        or manifest["digestAlgorithm"] != "sha256"
        or manifest["assetCount"] != 90
        or manifest["categoryCounts"] != EXPECTED_CATEGORY_COUNTS
    ):
        _fail("source-pack identity is invalid")
    assets = manifest["assets"]
    if type(assets) is not list or len(assets) != 90:
        _fail("source-pack asset count is invalid")

    paths: list[str] = []
    folded_paths: set[str] = set()
    digests: set[str] = set()
    object_paths: set[str] = set()
    counts = {key: 0 for key in EXPECTED_CATEGORY_COUNTS}
    executable_count = 0
    fields = {
        "category",
        "sourcePath",
        "sourceCommit",
        "gitBlobOid",
        "sha256",
        "byteSize",
        "gitMode",
        "kind",
        "license",
        "provenance",
        "intendedOwner",
        "externalRefs",
        "developmentDependencies",
        "objectPath",
    }
    category_contract = {
        key: (output_key, kind)
        for key, (output_key, kind, _count) in INVENTORY_CATEGORIES.items()
    }
    for raw_record in assets:
        record = _require_exact_object(raw_record, fields)
        category = record["category"]
        if category not in category_contract:
            _fail("source-pack category is invalid")
        output_key, expected_kind = category_contract[category]
        counts[output_key] += 1
        source_path = _require_string(record["sourcePath"], 1024)
        try:
            _COMMON.require_relative_posix_path(source_path)
        except _COMMON.MigrationError:
            _fail("source-pack path is invalid")
        folded = source_path.casefold()
        if source_path in paths or folded in folded_paths:
            _fail("source-pack source path is duplicated")
        paths.append(source_path)
        folded_paths.add(folded)
        if record["sourceCommit"] != APPROVED_SOURCE_COMMIT:
            _fail("source-pack record commit is invalid")
        oid = record["gitBlobOid"]
        digest = record["sha256"]
        if (
            type(oid) is not str
            or _HEX_40.fullmatch(oid) is None
            or type(digest) is not str
            or _HEX_64.fullmatch(digest) is None
            or digest in digests
        ):
            _fail("source-pack digest identity is invalid")
        digests.add(digest)
        size = record["byteSize"]
        if type(size) is not int or size < 0 or size > MAX_SOURCE_OBJECT_BYTES:
            _fail("source-pack byte size is invalid")
        mode = record["gitMode"]
        if mode not in {"100644", "100755"}:
            _fail("source-pack Git mode is invalid")
        if mode == "100755":
            executable_count += 1
            if category != "probes":
                _fail("source-pack executable mode category is invalid")
        if record["kind"] != expected_kind:
            _fail("source-pack kind is invalid")
        _validate_review_status(record["license"])
        _validate_review_status(record["provenance"])
        owner = record["intendedOwner"]
        if type(owner) is not str or _OWNER.fullmatch(owner) is None:
            _fail("source-pack intended owner is invalid")
        _require_string_array(record["externalRefs"])
        _require_string_array(record["developmentDependencies"])
        object_path = record["objectPath"]
        expected_object_path = f"objects/sha256/{digest[:2]}/{digest[2:]}"
        if object_path != expected_object_path or object_path in object_paths:
            _fail("source-pack object path is invalid")
        object_paths.add(object_path)
    if paths != sorted(paths, key=lambda item: item.encode("ascii")):
        _fail("source-pack records are not sorted")
    if counts != EXPECTED_CATEGORY_COUNTS or executable_count != 11:
        _fail("source-pack category counts are invalid")
    return manifest


def _validate_inventory_index(
    documents: dict[str, bytes], binding: GitBinding
) -> dict[str, object]:
    index = _require_exact_object(
        _parse_json(
            documents[INVENTORY_INDEX_PATH], maximum=MAX_INVENTORY_DOCUMENT_BYTES
        ),
        {
            "schemaVersion",
            "repository",
            "sourceCommit",
            "sourceTag",
            "digestAlgorithm",
            "order",
            "assetCount",
            "dependencyCounts",
            "shards",
        },
    )
    if (
        index["schemaVersion"] != 1
        or index["repository"] != APPROVED_REPOSITORY
        or index["sourceCommit"] != binding.source_commit
        or index["sourceTag"] != binding.source_tag
        or index["digestAlgorithm"] != "sha256"
        or index["order"] != "ascii-posix-path"
        or index["assetCount"] != 90
        or type(index["shards"]) is not list
        or len(index["shards"]) != 6
    ):
        _fail("inventory index identity is invalid")
    expected_shards = set(INVENTORY_SHARD_PATHS)
    seen: set[str] = set()
    for raw_shard in index["shards"]:
        shard = _require_exact_object(
            raw_shard, {"path", "sha256", "category", "recordCount"}
        )
        path = shard["path"]
        digest = shard["sha256"]
        if (
            path not in expected_shards
            or path in seen
            or type(digest) is not str
            or _HEX_64.fullmatch(digest) is None
            or hashlib.sha256(documents[path]).hexdigest() != digest
        ):
            _fail("inventory shard identity is invalid")
        seen.add(path)
    if seen != expected_shards:
        _fail("inventory shard set is incomplete")
    return index


def _inventory_records(
    documents: dict[str, bytes], binding: GitBinding
) -> list[dict[str, object]]:
    _validate_inventory_index(documents, binding)
    records: list[dict[str, object]] = []
    inventory_fields = {
        "sourcePath",
        "sourceCommit",
        "gitBlobOid",
        "sha256",
        "byteSize",
        "gitMode",
        "kind",
        "license",
        "provenance",
        "intendedOwner",
        "externalRefs",
        "developmentDependencies",
    }
    for category, (output_key, kind, count) in INVENTORY_CATEGORIES.items():
        path = f"migration/assets/{category}.json"
        shard = _require_exact_object(
            _parse_json(documents[path], maximum=MAX_INVENTORY_DOCUMENT_BYTES),
            {
                "schemaVersion",
                "repository",
                "sourceCommit",
                "sourceTag",
                "category",
                "assetCount",
                "assets",
            },
        )
        if (
            shard["schemaVersion"] != 1
            or shard["repository"] != APPROVED_REPOSITORY
            or shard["sourceCommit"] != binding.source_commit
            or shard["sourceTag"] != binding.source_tag
            or shard["category"] != category
            or shard["assetCount"] != count
            or type(shard["assets"]) is not list
            or len(shard["assets"]) != count
        ):
            _fail("inventory category shard is invalid")
        for raw_record in shard["assets"]:
            record = _require_exact_object(raw_record, inventory_fields)
            if record["kind"] != kind:
                _fail("inventory record kind is invalid")
            records.append({"category": category, **record})

    dependencies = _require_exact_object(
        _parse_json(
            documents["migration/assets/dependencies.json"],
            maximum=MAX_INVENTORY_DOCUMENT_BYTES,
        ),
        {
            "schemaVersion",
            "repository",
            "sourceCommit",
            "sourceTag",
            "externalRefs",
            "developmentDependencies",
        },
    )
    if (
        dependencies["schemaVersion"] != 1
        or dependencies["repository"] != APPROVED_REPOSITORY
        or dependencies["sourceCommit"] != binding.source_commit
        or dependencies["sourceTag"] != binding.source_tag
        or type(dependencies["externalRefs"]) is not list
        or type(dependencies["developmentDependencies"]) is not list
    ):
        _fail("inventory dependency shard is invalid")
    return sorted(records, key=lambda item: item["sourcePath"].encode("ascii"))


def _bind_source_tree_and_objects(
    binding: GitBinding, records: list[dict[str, object]]
) -> dict[str, bytes]:
    paths = tuple(record["sourcePath"] for record in records)
    if len(paths) != 90 or len(set(paths)) != 90:
        _fail("inventory source identity set is invalid")
    tree = _parse_tree_entries(
        _run_git(
            binding.repository,
            ("ls-tree", "-z", binding.source_commit, "--", *paths),
        ).stdout
    )
    if set(tree) != set(paths):
        _fail("source commit does not contain every inventoried path")
    for record in records:
        mode, oid = tree[record["sourcePath"]]
        if mode != record["gitMode"] or oid != record["gitBlobOid"]:
            _fail("source tree identity does not match the inventory")

    oids = tuple(record["gitBlobOid"] for record in records)
    objects = _cat_file_batch(
        binding.repository,
        oids,
        per_object_limit=MAX_SOURCE_OBJECT_BYTES,
        total_limit=MAX_TOTAL_SOURCE_BYTES,
    )
    result: dict[str, bytes] = {}
    for record, (oid, kind, raw) in zip(records, objects, strict=True):
        if (
            kind != "blob"
            or oid != record["gitBlobOid"]
            or len(raw) != record["byteSize"]
            or hashlib.sha256(raw).hexdigest() != record["sha256"]
        ):
            _fail("source object content does not match the inventory")
        result[record["sha256"]] = raw
    if len(result) != 90:
        _fail("source object digests are duplicated")
    return result


def generate_source_pack(
    repository: Path,
    *,
    tag: str,
    source_commit: str,
    inventory_commit: str,
) -> dict[str, bytes]:
    """Build every source-pack byte in memory from the exact reviewed Git objects."""

    if (
        tag != APPROVED_SOURCE_TAG
        or source_commit != APPROVED_SOURCE_COMMIT
        or inventory_commit != APPROVED_INVENTORY_COMMIT
    ):
        _fail("requested source identity is not approved")
    binding = _bind_repository(
        repository,
        tag=tag,
        tag_object=APPROVED_SOURCE_TAG_OBJECT,
        source_commit=source_commit,
        inventory_commit=inventory_commit,
    )
    inventory = _read_inventory_documents(binding)
    records = _inventory_records(inventory, binding)
    objects = _bind_source_tree_and_objects(binding, records)
    manifest_records: list[dict[str, object]] = []
    documents: dict[str, bytes] = {}
    for record in records:
        digest = record["sha256"]
        object_path = f"objects/sha256/{digest[:2]}/{digest[2:]}"
        manifest_records.append({**record, "objectPath": object_path})
        documents[object_path] = objects[digest]
    manifest = {
        "schemaVersion": "1",
        "repository": APPROVED_REPOSITORY,
        "sourceTag": tag,
        "sourceTagObject": binding.tag_oid,
        "sourceCommit": source_commit,
        "inventoryCommit": inventory_commit,
        "digestAlgorithm": "sha256",
        "assetCount": 90,
        "categoryCounts": EXPECTED_CATEGORY_COUNTS,
        "assets": manifest_records,
    }
    _validate_manifest(manifest)
    try:
        documents["index.json"] = _COMMON.canonical_json_bytes(manifest)
    except _COMMON.MigrationError:
        _fail("source-pack index cannot be rendered within its limit")
    if hashlib.sha256(documents["index.json"]).hexdigest() != APPROVED_SOURCE_INDEX_SHA256:
        _fail("rendered source-pack index does not match the approved seal")
    _validate_git_storage(binding.repository)
    repeated = _bind_repository(
        binding.repository,
        tag=tag,
        tag_object=APPROVED_SOURCE_TAG_OBJECT,
        source_commit=source_commit,
        inventory_commit=inventory_commit,
    )
    if repeated != binding:
        _fail("source Git identity changed during import")
    return documents


def _bounded_directory_entries(
    directory: Path, maximum: int
) -> dict[str, os.DirEntry[str]]:
    result: dict[str, os.DirEntry[str]] = {}
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(result) >= maximum or entry.name in result:
                    _fail("source-pack directory exceeds the entry limit")
                result[entry.name] = entry
    except OSError:
        _fail("source-pack directory could not be read")
    return result


def _scan_object_paths(source_root: Path) -> set[str]:
    root_entries = _bounded_directory_entries(source_root, 2)
    if set(root_entries) != {"index.json", "objects"}:
        _fail("source-pack root entries are invalid")
    objects = Path(root_entries["objects"].path)
    objects_metadata = _path_metadata(objects)
    if not stat.S_ISDIR(objects_metadata.st_mode):
        _fail("source-pack object directory is invalid")
    algorithm_entries = _bounded_directory_entries(objects, 1)
    if set(algorithm_entries) != {"sha256"}:
        _fail("source-pack digest directory is invalid")
    digest_root = Path(algorithm_entries["sha256"].path)
    digest_metadata = _path_metadata(digest_root)
    if not stat.S_ISDIR(digest_metadata.st_mode):
        _fail("source-pack digest directory is invalid")

    result: set[str] = set()
    shard_entries = _bounded_directory_entries(digest_root, 90)
    for shard_entry in shard_entries.values():
        shard = Path(shard_entry.path)
        shard_metadata = _path_metadata(shard)
        if (
            re.fullmatch(r"[0-9a-f]{2}", shard_entry.name) is None
            or not stat.S_ISDIR(shard_metadata.st_mode)
        ):
            _fail("source-pack shard directory is invalid")
        leaves = _bounded_directory_entries(shard, 90)
        if not leaves:
            _fail("source-pack shard directory is empty")
        for leaf_entry in leaves.values():
            leaf = Path(leaf_entry.path)
            metadata = _path_metadata(leaf)
            if (
                re.fullmatch(r"[0-9a-f]{62}", leaf_entry.name) is None
                or not stat.S_ISREG(metadata.st_mode)
            ):
                _fail("source-pack object leaf is invalid")
            result.add(leaf.relative_to(source_root).as_posix())
    return result


def validate_source_pack(source_root: Path) -> dict[str, object]:
    """Validate a complete committed source pack without reading Mac-Win or Git."""

    if not isinstance(source_root, Path):
        _fail("source-pack path is invalid")
    try:
        requested_root = source_root.absolute()
        _validate_path_chain(requested_root)
        root = requested_root.resolve(strict=True)
    except OSError:
        _fail("source-pack directory is missing")
    _validate_path_chain(root)
    root_metadata = _path_metadata(root)
    if not stat.S_ISDIR(root_metadata.st_mode):
        _fail("source-pack path is not a directory")
    index_raw = _read_regular_file(root / "index.json", MAX_SOURCE_INDEX_BYTES)
    if hashlib.sha256(index_raw).hexdigest() != APPROVED_SOURCE_INDEX_SHA256:
        _fail("source-pack index does not match the approved seal")
    manifest = _validate_manifest(
        _parse_json(index_raw, maximum=MAX_SOURCE_INDEX_BYTES)
    )
    try:
        if _COMMON.canonical_json_bytes(manifest) != index_raw:
            _fail("source-pack index is not canonical")
    except _COMMON.MigrationError:
        _fail("source-pack index is not canonical")

    expected_paths = {record["objectPath"] for record in manifest["assets"]}
    actual_paths = _scan_object_paths(root)
    if actual_paths != expected_paths or len(actual_paths) != 90:
        _fail("source-pack object set is incomplete")
    total = 0
    for record in manifest["assets"]:
        object_path = root / PurePosixPath(record["objectPath"])
        raw = _read_regular_file(object_path, MAX_SOURCE_OBJECT_BYTES)
        total += len(raw)
        if total > MAX_TOTAL_SOURCE_BYTES:
            _fail("source-pack total bytes exceed the limit")
        if (
            len(raw) != record["byteSize"]
            or hashlib.sha256(raw).hexdigest() != record["sha256"]
            or _git_object_oid("blob", raw) != record["gitBlobOid"]
        ):
            _fail("source-pack object content does not match the index")
    return manifest


def bind_source_pack(source_root: Path) -> SourcePackBinding:
    """Authenticate and bind every exact offline source-pack leaf for a caller."""

    manifest = validate_source_pack(source_root)
    root = source_root.absolute()
    root_identity = _file_identity(_path_metadata(root))
    relative_paths = ["index.json"]
    relative_paths.extend(record["objectPath"] for record in manifest["assets"])
    leaves: dict[Path, SourcePackLeafBinding] = {}
    for relative in relative_paths:
        path = root / PurePosixPath(relative)
        maximum = (
            MAX_SOURCE_INDEX_BYTES
            if relative == "index.json"
            else MAX_SOURCE_OBJECT_BYTES
        )
        before = _path_metadata(path)
        raw = _read_regular_file(path, maximum)
        after = _path_metadata(path)
        identity = _file_identity(before)
        if _file_identity(after) != identity:
            _fail("source-pack binding identity changed")
        absolute = path.absolute()
        leaves[absolute] = SourcePackLeafBinding(absolute, identity, raw)
    if len(leaves) != 91:
        _fail("source-pack binding leaf count is invalid")
    binding = SourcePackBinding(root, root_identity, manifest, leaves)
    binding.revalidate()
    return binding


def _document_bytes(source_root: Path, manifest: dict[str, object]) -> dict[str, bytes]:
    result = {"index.json": _read_regular_file(source_root / "index.json", MAX_SOURCE_INDEX_BYTES)}
    for record in manifest["assets"]:
        path = record["objectPath"]
        result[path] = _read_regular_file(
            source_root / PurePosixPath(path), MAX_SOURCE_OBJECT_BYTES
        )
    return result


def _prepare_parent(destination: Path) -> Path:
    migration = destination.parents[1]
    macwin = destination.parent
    if not migration.exists():
        migration.mkdir()
    _validate_path_chain(migration)
    if not macwin.exists():
        macwin.mkdir()
    _validate_path_chain(macwin)
    if not stat.S_ISDIR(_path_metadata(macwin).st_mode):
        _fail("source-pack parent directory is invalid")
    return macwin


def _write_stage(stage: Path, documents: dict[str, bytes]) -> None:
    for relative, raw in sorted(documents.items(), key=lambda item: item[0].encode("ascii")):
        try:
            _COMMON.require_relative_posix_path(relative)
        except _COMMON.MigrationError:
            _fail("source-pack output path is invalid")
        destination = stage / PurePosixPath(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            _fail("source-pack stage could not be written")


def _write_source_pack(destination: Path, documents: dict[str, bytes]) -> None:
    if destination != SOURCE_PACK_ROOT:
        _fail("source-pack destination is invalid")
    parent = _prepare_parent(destination)
    parent_identity = _path_metadata(parent)
    stage = parent / f".source-stage-{secrets.token_hex(16)}"
    backup = parent / f".source-backup-{secrets.token_hex(16)}"
    stage.mkdir()
    committed = False
    try:
        _write_stage(stage, documents)
        staged_manifest = validate_source_pack(stage)
        if _document_bytes(stage, staged_manifest) != documents:
            _fail("source-pack staged bytes do not match")
        current_parent = _path_metadata(parent)
        if (current_parent.st_dev, current_parent.st_ino) != (
            parent_identity.st_dev,
            parent_identity.st_ino,
        ):
            _fail("source-pack parent identity changed")
        if destination.exists():
            current_manifest = validate_source_pack(destination)
            if _document_bytes(destination, current_manifest) == documents:
                return
            os.replace(destination, backup)
            try:
                os.replace(stage, destination)
                committed = True
            except OSError:
                os.replace(backup, destination)
                _fail("source-pack transaction failed")
            try:
                installed = validate_source_pack(destination)
                if _document_bytes(destination, installed) != documents:
                    _fail("source-pack installed bytes do not match")
            except SourcePackError:
                failed = parent / f".source-failed-{secrets.token_hex(16)}"
                os.replace(destination, failed)
                os.replace(backup, destination)
                shutil.rmtree(failed)
                committed = False
                raise
            shutil.rmtree(backup)
        else:
            try:
                os.replace(stage, destination)
                committed = True
            except OSError:
                _fail("source-pack transaction failed")
            installed = validate_source_pack(destination)
            if _document_bytes(destination, installed) != documents:
                _fail("source-pack installed bytes do not match")
    finally:
        if stage.exists() and not committed:
            shutil.rmtree(stage)


def _check_source_pack(destination: Path, documents: dict[str, bytes]) -> None:
    manifest = validate_source_pack(destination)
    if _document_bytes(destination, manifest) != documents:
        _fail("committed source pack differs from the reviewed source")


class _StableArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: invalid command-line arguments\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = _StableArgumentParser(
        prog="import_macwin_source_pack.py",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--inventory-commit", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--write", action="store_true")
    return parser


def main(arguments: tuple[str, ...] = ()) -> int:
    try:
        options = _argument_parser().parse_args(arguments)
    except SystemExit as error:
        return int(error.code)
    try:
        documents = generate_source_pack(
            options.repository,
            tag=options.tag,
            source_commit=options.source_commit,
            inventory_commit=options.inventory_commit,
        )
        if options.write:
            _write_source_pack(SOURCE_PACK_ROOT, documents)
        else:
            _check_source_pack(SOURCE_PACK_ROOT, documents)
    except SourcePackError as error:
        print(f"Mac-Win source-pack import failed: {error}", file=sys.stderr)
        return 1
    print(
        "Mac-Win source pack was written."
        if options.write
        else "Mac-Win source pack matches the reviewed source."
    )
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main(tuple(sys.argv[1:])))
