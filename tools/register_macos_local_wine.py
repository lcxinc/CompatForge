#!/usr/bin/env python3
"""Create deterministic local-only macOS Wine preview Pack evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

COPY_BUFFER_BYTES = 64 * 1024
ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ["guest-i386", "guest-x86_64", "new-wow64"]
WINED3D_CAPABILITIES = ["d3d9", "d3d11", "opengl"]


class RegistrationError(Exception):
    """A closed registration failure that does not reflect caller paths."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--output-root", required=True)
    value.add_argument("--runtime-store-root", required=True)
    value.add_argument("--materialized-root", required=True)
    value.add_argument("--wine", required=True)
    value.add_argument("--wineserver", required=True)
    value.add_argument("--pack-id", required=True)
    value.add_argument("--version", required=True)
    return value


def absolute_path(value: str, field: str, *, strict: bool) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise RegistrationError(f"invalid-{field}")
    try:
        return path.resolve(strict=strict)
    except OSError as error:
        raise RegistrationError(f"invalid-{field}") from error


def portable_relative_path(value: str, field: str) -> PurePosixPath:
    if not value or "\\" in value or ":" in value or value.startswith("/"):
        raise RegistrationError(f"invalid-{field}")
    path = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in path.parts):
        raise RegistrationError(f"invalid-{field}")
    return path


def valid_identifier(value: str) -> bool:
    return (
        len(value) >= 2
        and (value[0].islower() or value[0].isdigit())
        and value.isascii()
        and all(character.islower() or character.isdigit() or character in "._-" for character in value)
    )


def overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def selected_entrypoint(root: Path, relative: PurePosixPath, field: str) -> Path:
    lexical = root.joinpath(*relative.parts)
    try:
        metadata = lexical.lstat()
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise RegistrationError(f"invalid-{field}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RegistrationError(f"invalid-{field}")
    if resolved != root and root not in resolved.parents:
        raise RegistrationError(f"invalid-{field}")
    if metadata.st_mode & 0o111 == 0:
        raise RegistrationError(f"invalid-{field}")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(COPY_BUFFER_BYTES), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def compact_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def pretty_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def manifest_for(
    pack_id: str,
    version: str,
    wine_relative: str,
    wine_digest: str,
    wineserver_relative: str,
    wineserver_digest: str,
) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "schemaVersion": "1",
        "id": pack_id,
        "version": version,
        "channel": "preview",
        "host": {"os": "macos", "architecture": "x86_64"},
        "components": [
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
        ],
        "capabilities": CAPABILITIES,
    }
    manifest = dict(unsigned)
    manifest["digest"] = f"sha256:{hashlib.sha256(compact_json(unsigned)).hexdigest()}"
    return manifest


def write_file(path: Path, content: bytes, mode: int = 0o600) -> None:
    with path.open("xb") as destination:
        destination.write(content)
        destination.flush()
        os.fsync(destination.fileno())
    path.chmod(mode)


def copy_file(source: Path, target: Path, expected_digest: str) -> None:
    digest = hashlib.sha256()
    with source.open("rb") as input_file, target.open("xb") as output_file:
        for chunk in iter(lambda: input_file.read(COPY_BUFFER_BYTES), b""):
            digest.update(chunk)
            output_file.write(chunk)
        output_file.flush()
        os.fsync(output_file.fileno())
    target.chmod(0o500)
    actual = f"sha256:{digest.hexdigest()}"
    if actual != expected_digest or sha256_file(target) != expected_digest:
        raise RegistrationError("source-changed")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def snapshot_tree(root: Path) -> dict[str, tuple[str, int, bytes]]:
    result: dict[str, tuple[str, int, bytes]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RegistrationError("output-collision")
        relative = path.relative_to(root).as_posix()
        mode = path.stat().st_mode & 0o777
        if path.is_dir():
            result[relative] = ("directory", mode, b"")
        elif path.is_file():
            result[relative] = ("file", mode, path.read_bytes())
        else:
            raise RegistrationError("output-collision")
    return result


def verify_existing(output: Path, expected: dict[str, tuple[str, int, bytes]]) -> None:
    if output.is_symlink() or not output.is_dir():
        raise RegistrationError("output-collision")
    if snapshot_tree(output) != expected:
        raise RegistrationError("output-collision")


def register(arguments: argparse.Namespace) -> dict[str, object]:
    output = absolute_path(arguments.output_root, "output-root", strict=False)
    runtime_store = absolute_path(arguments.runtime_store_root, "runtime-store-root", strict=False)
    materialized = absolute_path(arguments.materialized_root, "materialized-root", strict=True)
    if not materialized.is_dir():
        raise RegistrationError("invalid-materialized-root")
    if not valid_identifier(arguments.pack_id):
        raise RegistrationError("invalid-pack-id")
    if not arguments.version or any(character in "\r\n\x00" for character in arguments.version):
        raise RegistrationError("invalid-version")

    wine_relative = portable_relative_path(arguments.wine, "wine")
    wineserver_relative = portable_relative_path(arguments.wineserver, "wineserver")
    wine = selected_entrypoint(materialized, wine_relative, "wine")
    wineserver = selected_entrypoint(materialized, wineserver_relative, "wineserver")

    for protected in (runtime_store, materialized, ROOT.resolve()):
        if overlaps(output, protected):
            raise RegistrationError("path-overlap")

    wine_digest = sha256_file(wine)
    wineserver_digest = sha256_file(wineserver)
    manifest = manifest_for(
        arguments.pack_id,
        arguments.version,
        wine_relative.as_posix(),
        wine_digest,
        wineserver_relative.as_posix(),
        wineserver_digest,
    )
    pack_digest = str(manifest["digest"])
    provider = {
        "schemaVersion": "1",
        "runtimeStoreRoot": str(runtime_store),
        "wineRuntime": {
            "providerId": arguments.pack_id,
            "packId": arguments.pack_id,
            "packDigest": pack_digest,
            "version": arguments.version,
            "architecture": "x86_64",
            "materializedRoot": str(materialized),
            "wine": {"path": wine_relative.as_posix(), "digest": wine_digest},
            "wineserver": {"path": wineserver_relative.as_posix(), "digest": wineserver_digest},
            "capabilities": CAPABILITIES,
            "wined3dCapabilities": WINED3D_CAPABILITIES,
        },
    }
    receipt: dict[str, object] = {
        "activated": False,
        "bundlePath": str(output / "bundle"),
        "packDigest": pack_digest,
        "packId": arguments.pack_id,
        "providerConfigPath": str(output / "provider.json"),
        "schemaVersion": "1",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    published = False
    try:
        components = staging / "bundle" / "components"
        components.mkdir(parents=True)
        copy_file(wine, components / "wine-entrypoint.bin", wine_digest)
        copy_file(wineserver, components / "wineserver-entrypoint.bin", wineserver_digest)
        write_file(staging / "bundle" / "manifest.json", pretty_json(manifest))
        write_file(staging / "provider.json", pretty_json(provider))
        write_file(staging / "receipt.json", pretty_json(receipt))
        for directory in (components, staging / "bundle", staging):
            fsync_directory(directory)
        expected = snapshot_tree(staging)
        if output.exists() or output.is_symlink():
            verify_existing(output, expected)
        else:
            staging.rename(output)
            published = True
            fsync_directory(output.parent)
        return receipt
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    try:
        receipt = register(parser().parse_args())
    except RegistrationError as error:
        print(f"compatforge-register: {error.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError):
        print("compatforge-register: transaction-failed", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(compact_json(receipt) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
