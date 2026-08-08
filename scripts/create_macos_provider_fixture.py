#!/usr/bin/env python3
"""Build manifest/config JSON around the macOS CI Provider stub."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: create_macos_provider_fixture.py <fixture-root>")

    root = Path(sys.argv[1]).resolve()
    materialized = root / "materialized"
    bundle = root / "bundle"
    store = root / "store"
    wine = materialized / "bin" / "wine"
    wineserver = materialized / "bin" / "wineserver"
    artifact = bundle / "components" / "runtime.blob"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(wine, artifact)

    capabilities = ["guest-i386", "guest-x86_64", "new-wow64"]
    component = {
        "name": "wine",
        "version": "11.0",
        "license": "LGPL-2.1-or-later",
        "artifact": "components/runtime.blob",
        "digest": sha256(artifact),
        "entrypoints": {"wine": "bin/wine", "wineserver": "bin/wineserver"},
    }
    unsigned = {
        "schemaVersion": "1",
        "id": "wine-macos-ci",
        "version": "11.0",
        "channel": "preview",
        "host": {"os": "macos", "architecture": "x86_64"},
        "components": [component],
        "capabilities": capabilities,
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":")).encode()
    manifest_digest = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    manifest = dict(unsigned)
    manifest["digest"] = manifest_digest
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    config = {
        "schemaVersion": "1",
        "runtimeStoreRoot": str(store),
        "wineRuntime": {
            "providerId": "wine-macos-ci",
            "packId": "wine-macos-ci",
            "packDigest": manifest_digest,
            "version": "11.0",
            "architecture": "x86_64",
            "materializedRoot": str(materialized),
            "wine": {"path": "bin/wine", "digest": sha256(wine)},
            "wineserver": {"path": "bin/wineserver", "digest": sha256(wineserver)},
            "capabilities": capabilities,
            "wined3dCapabilities": ["d3d9", "d3d11", "opengl"],
        },
    }
    (root / "provider.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
