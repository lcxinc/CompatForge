#!/usr/bin/env python3
"""Opt-in downloader for the fixed GUI compatibility baseline installers.

The cache must live outside the repository. Downloads are never attempted
unless ``--allow-network`` is explicitly provided, and every response is
streamed through an allowlisted redirect chain with a bounded byte count and
SHA-256 verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MAX_DOWNLOAD_BYTES = 384 * 1024 * 1024


@dataclass(frozen=True)
class GuiAsset:
    app_id: str
    display_name: str
    filename: str
    url: str
    sha256: str
    install_args: tuple[str, ...]
    installed_executable: str
    window_title_tokens: tuple[str, ...]
    launch_args: tuple[str, ...] = ()
    install_wait_milliseconds: int = 8_000
    screenshot_delay_seconds: int = 0
    runtime_environment: tuple[tuple[str, str], ...] = ()
    window_appearance_seconds: int = 30


BASELINE_ASSETS = (
    GuiAsset(
        "7zip",
        "7-Zip 26.01",
        "7z2601-x64.exe",
        "https://www.7-zip.org/a/7z2601-x64.exe",
        "d64a0468f5b5b0b0fc5b2188450bcd655b70809d97b1c4535f2884635094377d",
        ("/S",),
        "Program Files/7-Zip/7zFM.exe",
        ("7-Zip",),
    ),
    GuiAsset(
        "sumatrapdf",
        "SumatraPDF 3.6.1",
        "SumatraPDF-3.6.1-64-install.exe",
        "https://www.sumatrapdfreader.org/dl/rel/3.6.1/SumatraPDF-3.6.1-64-install.exe",
        "1eee71cccd2ea6e94d5bcea54ee2f759844da3e1a0ee2f6045035b1d17b94381",
        ("-silent",),
        "Program Files/SumatraPDF/SumatraPDF.exe",
        ("SumatraPDF",),
    ),
    GuiAsset(
        "notepad-plus-plus",
        "Notepad++ 8.9.6.2",
        "npp.8.9.6.2.Installer.x64.exe",
        "https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.6.2/npp.8.9.6.2.Installer.x64.exe",
        "7c243203265ce8fdac76c839bf744ae35dcf620760eb97c2ea279af498560e45",
        ("/S",),
        "Program Files/Notepad++/notepad++.exe",
        ("Notepad++",),
    ),
)

EXTENDED_ASSETS = (
    GuiAsset(
        "firefox",
        "Mozilla Firefox 152.0.1",
        "Firefox_Setup_152.0.1.exe",
        "https://download.mozilla.org/?product=firefox-152.0.1-ssl&os=win64&lang=zh-CN",
        "5435b3117b1789eacb7443259dbea06c6e221cc676d1295b70c190bbac24d72c",
        ("/S",),
        "Program Files/Mozilla Firefox/firefox.exe",
        ("Firefox", "Mozilla"),
        (
            "--no-remote",
            "--new-instance",
            "data:text/html;charset=utf-8,%3Ctitle%3ECompatForge%20Firefox%3C/title%3E%3Ch1%3ECompatForge%20%E4%B8%AD%E6%96%87%E5%85%BC%E5%AE%B9%E9%AA%8C%E8%AF%81%3C/h1%3E",
        ),
        20_000,
        35,
    ),
    GuiAsset(
        "krita",
        "Krita 5.2.9",
        "krita-x64-5.2.9-setup.exe",
        "https://download.kde.org/stable/krita/5.2.9/krita-x64-5.2.9-setup.exe",
        "e394029b3529a7c7411fc200e5627368ac3818a4fda4f453d18c86e220db7057",
        ("/S",),
        "Program Files/Krita (x64)/bin/krita.exe",
        ("Krita",),
        ("--nosplash",),
        45_000,
        30,
        (
            ("WINE_D3D_CONFIG", "renderer=gl,csmt=0x0"),
            ("PYTHONHASHSEED", "0"),
            ("MACWIN_COMPAT_PROFILE", "krita-opengl"),
            ("MACWIN_APP_MODE_INPUT_REPAIR", "1"),
            ("MACWIN_FORCE_MOUSE_FOCUS", "1"),
            ("MACWIN_KRITA_OPENGL_REPAIR", "1"),
            ("QT_ACCESSIBILITY", "0"),
            ("QT_AUTO_SCREEN_SCALE_FACTOR", "0"),
            ("QT_ENABLE_HIGHDPI_SCALING", "0"),
            ("QT_FONT_DPI", "96"),
            ("QT_OPENGL", "desktop"),
            ("QT_SCALE_FACTOR", "1"),
        ),
        55,
    ),
)

ASSETS = BASELINE_ASSETS + EXTENDED_ASSETS

ALLOWED_HOSTS = {
    "www.7-zip.org",
    "7-zip.org",
    "www.sumatrapdfreader.org",
    "sumatrapdfreader.org",
    "files2.sumatrapdfreader.org",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "download.mozilla.org",
    "download-installer.cdn.mozilla.net",
    "download.kde.org",
    "mirrors.xtom.com",
}


class AssetError(Exception):
    pass


def asset_for(app_id: str) -> GuiAsset:
    for asset in ASSETS:
        if asset.app_id == app_id:
            return asset
    raise AssetError(f"unknown GUI baseline asset: {app_id}")


def validate_cache_root(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise AssetError("cache-root must be absolute")
    if any(part in (".", "..") for part in path.parts):
        raise AssetError("cache-root must not contain traversal")
    repository = Path(__file__).resolve().parents[1]
    if path == repository or repository in path.parents:
        raise AssetError("cache-root must be outside the repository")
    return path


class AllowlistedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise AssetError("download redirect leaves the official host allowlist")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(asset: GuiAsset, cache_root: Path, allow_network: bool) -> Path:
    destination = cache_root / asset.filename
    if destination.exists():
        if not destination.is_file() or destination.is_symlink():
            raise AssetError("cache entry is not a regular file")
        if digest_file(destination) != asset.sha256:
            raise AssetError(f"cached {asset.app_id} digest mismatch")
        return destination
    if not allow_network:
        raise AssetError(f"{asset.app_id} is not cached; pass --allow-network to download")
    parsed = urllib.parse.urlparse(asset.url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise AssetError("asset URL is outside the official host allowlist")
    cache_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{asset.app_id}-", dir=cache_root)
    os.close(descriptor)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    total = 0
    try:
        opener = urllib.request.build_opener(AllowlistedRedirect)
        request = urllib.request.Request(
            asset.url,
            headers={
                "User-Agent": "CompatForge/0.11 (official GUI baseline)",
                "Accept": "application/octet-stream,*/*",
            },
        )
        with opener.open(request, timeout=30) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise AssetError("download exceeds the bounded asset size")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest()
        if actual != asset.sha256:
            raise AssetError(f"downloaded {asset.app_id} digest mismatch")
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("command", choices=("list", "fetch"))
    value.add_argument("app", nargs="?", choices=tuple(asset.app_id for asset in ASSETS))
    value.add_argument("--cache-root", required=True)
    value.add_argument("--allow-network", action="store_true")
    return value


def asset_json(asset: GuiAsset) -> dict[str, object]:
    return {
        "appId": asset.app_id,
        "displayName": asset.display_name,
        "filename": asset.filename,
        "url": asset.url,
        "sha256": asset.sha256,
        "installArgs": list(asset.install_args),
        "installedExecutable": asset.installed_executable,
        "windowTitleTokens": list(asset.window_title_tokens),
        "launchArgs": list(asset.launch_args),
        "installWaitMilliseconds": asset.install_wait_milliseconds,
        "screenshotDelaySeconds": asset.screenshot_delay_seconds,
        "runtimeEnvironment": dict(asset.runtime_environment),
        "windowAppearanceSeconds": asset.window_appearance_seconds,
    }


def main() -> int:
    try:
        arguments = parser().parse_args()
        cache_root = validate_cache_root(arguments.cache_root)
        if arguments.command == "list":
            print(json.dumps([asset_json(asset) for asset in ASSETS], ensure_ascii=False, sort_keys=True))
            return 0
        if arguments.app is None:
            raise AssetError("fetch requires an app id")
        path = fetch(asset_for(arguments.app), cache_root, arguments.allow_network)
        print(json.dumps({"appId": arguments.app, "path": str(path)}, ensure_ascii=False, sort_keys=True))
        return 0
    except (AssetError, OSError, urllib.error.URLError, ValueError) as error:
        print(f"compatforge-gui-assets: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
