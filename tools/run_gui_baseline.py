#!/usr/bin/env python3
"""Opt-in macOS GUI acceptance for the fixed CompatForge baseline apps.

This script intentionally records ``accepted``, ``failed`` or ``unverified``
per application. A visible process or a blank window is never promoted to an
acceptance claim. Downloads, screenshots and evidence live in caller-owned
external directories and are excluded from the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import selectors
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "tools" / "download_gui_assets.py"
MAX_COMMAND_SECONDS = 180
WINDOW_APPEARANCE_SECONDS = 30
INTERACTIVE_RUNTIME_MILLISECONDS = 60_000

REQUIRED_INTERACTIONS = {
    "7zip": ("fileList", "menus", "cjkTextReadable"),
    "sumatrapdf": ("mainWindow", "openDialog", "cjkTextReadable"),
    "notepad-plus-plus": ("open", "edit", "saveUtf8Chinese", "rereadMatches", "cjkTextReadable"),
    "firefox": ("mainWindow", "browserContentRendered", "cjkTextReadable"),
    "krita": ("mainWindow", "workspaceVisible", "cjkTextReadable"),
}
BASELINE_APPLICATION_IDS = {"7zip", "sumatrapdf", "notepad-plus-plus"}


class AcceptanceError(Exception):
    pass


def absolute(value: str, field: str, *, external: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise AcceptanceError(f"{field} must be an absolute non-traversing path")
    if external and (path == ROOT or ROOT in path.parents):
        raise AcceptanceError(f"{field} must be outside the repository")
    return path


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--compatforge-cli", required=True)
    value.add_argument("--cache-root", required=True)
    value.add_argument("--runtime-store", required=True)
    value.add_argument("--storage-root", required=True)
    value.add_argument("--work-root", required=True)
    value.add_argument("--allow-network", action="store_true")
    value.add_argument("--wine-root")
    value.add_argument("--wine")
    value.add_argument("--wineserver")
    value.add_argument("--version")
    value.add_argument(
        "--app",
        action="append",
        dest="applications",
        help="run only the named baseline application; repeat for multiple applications",
    )
    value.add_argument(
        "--accept-interactive",
        action="store_true",
        help="promote non-empty window/screenshot evidence after manual GUI behavior checks",
    )
    value.add_argument(
        "--interaction-evidence",
        help="absolute JSON record of the required per-application manual checks",
    )
    return value


def invoke(argv: list[str], *, timeout: int = MAX_COMMAND_SECONDS) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise AcceptanceError(f"command failed: {Path(argv[0]).name} {' '.join(argv[1:3])}")
    return result


def json_object(result: subprocess.CompletedProcess[str], label: str) -> dict[str, object]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AcceptanceError(f"{label} did not return JSON") from error
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label} did not return an object")
    return value


def run_events(result: subprocess.CompletedProcess[str], label: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in result.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AcceptanceError(f"{label} emitted invalid RuntimeEvent JSON") from error
        if not isinstance(value, dict):
            raise AcceptanceError(f"{label} emitted a non-object RuntimeEvent")
        events.append(value)
    if not events:
        raise AcceptanceError(f"{label} emitted no RuntimeEvent")
    return events


def exit_observation(events: list[dict[str, object]]) -> dict[str, object]:
    """Return the terminal exit evidence in a stable, compact projection."""
    event = next((value for value in reversed(events) if value.get("kind") == "exited"), None)
    if event is None:
        return {"present": False}
    exit_value = event.get("exit")
    if not isinstance(exit_value, dict):
        return {"present": False}
    return {
        "present": True,
        "code": exit_value.get("code"),
        "success": exit_value.get("success") is True,
    }


def process_table() -> list[tuple[int, int, str]]:
    """Return a bounded macOS process table projection without shelling out."""
    if platform.system() != "Darwin":
        return []
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,pgid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            continue
    return rows


def process_snapshot(marker: str, process_group_id: int | None = None) -> list[str]:
    """List residual commands tied to either the Bottle path or launch group."""
    current = os.getpid()
    rows = process_table()
    if not rows:
        return ["process observation unavailable"]
    return [
        f"{pid} {command}"
        for pid, pgid, command in rows
        if pid != current and (marker in command or (process_group_id is not None and pgid == process_group_id))
    ]


def process_group_ids(process_group_id: int) -> list[int]:
    return [pid for pid, pgid, _command in process_table() if pgid == process_group_id]


def matching_windows(output: str, title_tokens: tuple[str, ...]) -> list[dict[str, object]]:
    matching: list[dict[str, object]] = []
    for line in output.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) != 3 or not any(token.casefold() in parts[1].casefold() for token in title_tokens):
            continue
        dimensions = parts[2].split("x", 1)
        try:
            process_id = int(parts[0])
            width = int(dimensions[0])
            height = int(dimensions[1])
        except (ValueError, IndexError):
            continue
        if width <= 0 or height <= 0:
            continue
        matching.append({"processId": process_id, "title": parts[1], "width": width, "height": height})
    return matching


def parse_event_line(line: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise AcceptanceError(f"{label} emitted invalid RuntimeEvent JSON") from error
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label} emitted a non-object RuntimeEvent")
    return value


def observed_launch(
    argv: list[str],
    screenshot_path: Path,
    title_tokens: tuple[str, ...],
    *,
    screenshot_delay_seconds: int = 0,
    window_appearance_seconds: int = WINDOW_APPEARANCE_SECONDS,
    timeout: int = MAX_COMMAND_SECONDS,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object], int | None]:
    """Keep the Core launch process alive while collecting visual evidence."""
    process = subprocess.Popen(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise AcceptanceError("GUI launch pipes were not created")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    started = time.monotonic()
    windows: dict[str, object] = {"available": False, "reason": "observation pending"}
    shot: dict[str, object] = {"available": False, "path": str(screenshot_path)}
    events: list[dict[str, object]] = []
    root_process_id: int | None = None
    next_observation = started
    while process.poll() is None:
        elapsed = time.monotonic() - started
        for key, _mask in selector.select(timeout=0.1):
            line = key.fileobj.readline()
            if not line:
                continue
            event = parse_event_line(line, "GUI launch")
            events.append(event)
            if event.get("kind") == "started" and isinstance(event.get("processId"), int):
                root_process_id = event["processId"]
        now = time.monotonic()
        if root_process_id is not None and now >= next_observation:
            if not windows.get("available") and elapsed <= window_appearance_seconds:
                windows = observer(root_process_id, title_tokens)
            if (
                windows.get("available") is True
                and not shot.get("available")
                and elapsed >= screenshot_delay_seconds
            ):
                shot = screenshot(screenshot_path)
            next_observation = now + 0.5
        if elapsed >= timeout:
            process.kill()
            process.wait(timeout=10)
            raise AcceptanceError("GUI launch exceeded the bounded observation timeout")
        time.sleep(0.1)
    selector.unregister(process.stdout)
    selector.close()
    for line in process.stdout.read().splitlines():
        if line.strip():
            events.append(parse_event_line(line, "GUI launch"))
    stderr = process.stderr.read()
    process.wait(timeout=10)
    if process.returncode != 0:
        detail = stderr.strip().splitlines()[-1] if stderr.strip() else "no stderr"
        raise AcceptanceError(f"GUI launch failed: {detail}")
    if not events:
        raise AcceptanceError("GUI launch emitted no RuntimeEvent")
    return events, windows, shot, root_process_id


def status(events: list[dict[str, object]]) -> str:
    exit_event = next((event for event in reversed(events) if event.get("kind") == "exited"), None)
    if exit_event is None:
        return "failed"
    exit_value = exit_event.get("exit")
    if isinstance(exit_value, dict) and exit_value.get("success") is True:
        return "accepted"
    if any(event.get("kind") == "terminate-requested" for event in events):
        return "accepted"
    if not isinstance(exit_value, dict):
        return "failed"
    return "failed"


def observer(process_group_id: int, title_tokens: tuple[str, ...]) -> dict[str, object]:
    if platform.system() != "Darwin":
        return {"available": False, "reason": "window observation requires macOS"}
    target_ids = process_group_ids(process_group_id)
    if not target_ids:
        return {"available": False, "reason": "launch process group is no longer visible", "processGroupId": process_group_id}
    ids = ",".join(str(value) for value in target_ids)
    script = (
        'tell application "System Events"\n'
        "set resultText to {}\n"
        f"set targetIds to {{{ids}}}\n"
        "repeat with p in (every process whose background only is false)\n"
        "if targetIds contains (unix id of p) then\n"
        "repeat with w in (every window of p)\n"
        "set t to title of w\n"
        "set windowSize to size of w\n"
        "if t is not missing value and t is not \"\" then set end of resultText to ((unix id of p as text) & \"|\" & t & \"|\" & (item 1 of windowSize as text) & \"x\" & (item 2 of windowSize as text))\n"
        "end repeat\n"
        "end if\n"
        "end repeat\n"
        "set AppleScript's text item delimiters to linefeed\n"
        "return resultText as text\n"
        "end tell"
    )
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "osascript unavailable"}
    if result.returncode != 0:
        return {"available": False, "reason": "Accessibility permission unavailable"}
    matching = matching_windows(result.stdout, title_tokens)
    if matching:
        return {
            "available": True,
            "processGroupId": process_group_id,
            "processIds": target_ids,
            "expectedTitleTokens": list(title_tokens),
            "windows": matching[:32],
        }
    fallback_script = (
        "tell application \"System Events\"\\n"
        "set resultText to {}\\n"
        "repeat with p in (every application process whose background only is false)\\n"
        "repeat with w in (every window of p)\\n"
        "set t to title of w\\n"
        "set windowSize to size of w\\n"
        "if t is not missing value and t is not \"\" then\\n"
        "set end of resultText to ((name of p as text) & \"|\" & (unix id of p as text) & \"|\" & t & \"|\" & (item 1 of windowSize as text) & \"x\" & (item 2 of windowSize as text))\\n"
        "end if\\n"
        "end repeat\\n"
        "end repeat\\n"
        "set AppleScript's text item delimiters to linefeed\\n"
        "return resultText as text\\n"
        "end tell"
    )
    fallback = subprocess.run(
        ["/usr/bin/osascript", "-e", fallback_script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
    )
    if fallback.returncode == 0:
        matching_all = matching_windows(fallback.stdout, title_tokens)
        if matching_all:
            return {
                "available": True,
                "processGroupId": process_group_id,
                "processIds": target_ids,
                "expectedTitleTokens": list(title_tokens),
                "windows": matching_all[:32],
            }
    return {
        "available": False,
        "reason": "launch process group is no longer visible",
        "processGroupId": process_group_id,
    }


def screenshot(path: Path) -> dict[str, object]:
    try:
        result = subprocess.run(
            ["/usr/sbin/screencapture", "-x", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "screencapture unavailable"}
    return {"available": result.returncode == 0 and path.is_file() and path.stat().st_size > 0, "path": str(path)}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def interaction_evidence(
    path: Path | None,
    accept_interactive: bool,
    application_ids: set[str] | None = None,
) -> dict[str, dict[str, bool]]:
    application_ids = application_ids or BASELINE_APPLICATION_IDS
    if not accept_interactive:
        if path is not None:
            raise AcceptanceError("--interaction-evidence requires --accept-interactive")
        return {}
    if path is None:
        raise AcceptanceError("--accept-interactive requires --interaction-evidence")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceError("interaction evidence is not readable JSON") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != "1":
        raise AcceptanceError("interaction evidence must use schemaVersion 1")
    applications = value.get("applications")
    if not isinstance(applications, dict):
        raise AcceptanceError("interaction evidence omitted applications")
    result: dict[str, dict[str, bool]] = {}
    for app_id in application_ids:
        required = REQUIRED_INTERACTIONS[app_id]
        checks = applications.get(app_id)
        if not isinstance(checks, dict) or any(checks.get(name) is not True for name in required):
            raise AcceptanceError(f"interaction evidence is incomplete for {app_id}")
        result[app_id] = {name: True for name in required}
    return result


def installed_executable(asset, bottle_root: Path) -> Path:  # type: ignore[no-untyped-def]
    """Resolve only fixed, application-specific install locations."""
    primary = bottle_root / Path(asset.installed_executable)
    candidates = [primary]
    if asset.app_id == "sumatrapdf":
        candidates.append(
            bottle_root
            / "users"
            / os.environ.get("USER", "Public")
            / "AppData"
            / "Local"
            / "SumatraPDF"
            / "SumatraPDF.exe"
        )
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return primary


def request_architecture(value: str) -> str:
    # PE inspection uses the human-readable x86 label; the public schema
    # intentionally uses the stable i386 enum.
    return "i386" if value == "x86" else value


def fetch_asset(arguments: argparse.Namespace, app_id: str) -> Path:
    result = invoke(
        [
            sys.executable,
            "-S",
            "-B",
            str(DOWNLOAD),
            "fetch",
            app_id,
            "--cache-root",
            str(arguments.cache_root),
            *(["--allow-network"] if arguments.allow_network else []),
        ],
        timeout=240,
    )
    value = json_object(result, f"{app_id} asset fetch")
    path = value.get("path")
    if not isinstance(path, str):
        raise AcceptanceError(f"{app_id} asset fetch omitted path")
    return absolute(path, f"{app_id} asset")


def main() -> int:
    try:
        arguments = parser().parse_args()
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise AcceptanceError("GUI baseline requires Darwin/arm64")
        arguments.compatforge_cli = absolute(arguments.compatforge_cli, "compatforge-cli")
        arguments.cache_root = absolute(arguments.cache_root, "cache-root", external=True)
        arguments.runtime_store = absolute(arguments.runtime_store, "runtime-store", external=True)
        arguments.storage_root = absolute(arguments.storage_root, "storage-root", external=True)
        arguments.work_root = absolute(arguments.work_root, "work-root", external=True)
        arguments.work_root.mkdir(parents=True, exist_ok=True)
        if any(arguments.work_root.iterdir()):
            raise AcceptanceError("work-root must be empty")
        explicit = [arguments.wine_root, arguments.wine, arguments.wineserver, arguments.version]
        if any(explicit) and not all(explicit):
            raise AcceptanceError("wine-root, wine, wineserver and version must be provided together")
        evidence_path = (
            absolute(arguments.interaction_evidence, "interaction-evidence", external=True)
            if arguments.interaction_evidence
            else None
        )
        from download_gui_assets import ASSETS, BASELINE_ASSETS  # type: ignore[import-not-found]

        known_applications = {asset.app_id for asset in ASSETS}
        selected_applications = set(arguments.applications or (asset.app_id for asset in BASELINE_ASSETS))
        unknown_applications = selected_applications - known_applications
        if unknown_applications:
            raise AcceptanceError(f"unknown baseline application: {sorted(unknown_applications)[0]}")
        manual_checks = interaction_evidence(evidence_path, arguments.accept_interactive, selected_applications)

        request = {
            "schemaVersion": "1",
            "runtimeStoreRoot": str(arguments.runtime_store),
            "storageRoot": str(arguments.storage_root),
        }
        if all(explicit):
            request.update(
                {
                    "materializedRoot": str(absolute(arguments.wine_root, "wine-root")),
                    "wine": arguments.wine,
                    "wineserver": arguments.wineserver,
                    "version": arguments.version,
                }
            )
        request_path = arguments.work_root / "bootstrap-request.json"
        context_path = arguments.work_root / "context.json"
        write_json(request_path, request)
        receipt = json_object(
            invoke([str(arguments.compatforge_cli), "local", "macos", "context", str(request_path), str(context_path)]),
            "bootstrap receipt",
        )
        context = json.loads(context_path.read_text(encoding="utf-8"))
        if not isinstance(context, dict):
            raise AcceptanceError("bootstrap context is not an object")
        canonical_storage = context.get("storageRoot")
        if not isinstance(canonical_storage, str) or not Path(canonical_storage).is_absolute():
            raise AcceptanceError("bootstrap context omitted an absolute storage root")
        # Rust bootstrap canonicalizes macOS aliases such as /tmp ->
        # /private/tmp. Reuse that authoritative root for Bottle paths so
        # string-boundary validation and the filesystem observe the same path.
        arguments.storage_root = Path(canonical_storage)
        supervisor = context.setdefault("supervisor", {})
        if isinstance(supervisor, dict):
            supervisor["maximumRuntimeMilliseconds"] = 120_000
        write_json(context_path, context)
        write_json(arguments.work_root / "bootstrap-receipt.json", receipt)

        results: list[dict[str, object]] = []
        for asset in ASSETS:
            if asset.app_id not in selected_applications:
                continue
            bottle_id = f"gui-{asset.app_id}"
            bottle_root = arguments.storage_root / "bottles" / bottle_id / "prefix" / "drive_c"
            bottle_root.mkdir(parents=True, exist_ok=True)
            evidence: dict[str, object] = {
                "schemaVersion": "1",
                "appId": asset.app_id,
                "bottleId": bottle_id,
                "status": "unverified",
                "cleanup": False,
            }
            try:
                installer = fetch_asset(arguments, asset.app_id)
                installer_inspection = json_object(
                    invoke([str(arguments.compatforge_cli), "inspect", str(installer)]),
                    f"{asset.app_id} installer inspection",
                )
                installer_architecture = installer_inspection.get("architecture")
                if not isinstance(installer_architecture, str):
                    raise AcceptanceError(f"{asset.app_id} installer inspection omitted architecture")
                evidence["installerInspection"] = installer_inspection
                inspection_request = {
                    "schemaVersion": "1",
                    "requestId": str(uuid.uuid4()),
                    "bottleId": bottle_id,
                    "executable": {
                        "path": str(installer),
                        "architecture": request_architecture(installer_architecture),
                        "mode": "immutableArtifact",
                    },
                    "arguments": list(asset.install_args),
                    "environment": dict(asset.runtime_environment),
                    "constraints": {
                        "allowVirtualMachine": False,
                        "allowRemote": False,
                        "networkPolicy": "deny",
                    },
                }
                installer_request_path = arguments.work_root / f"{asset.app_id}-installer-request.json"
                write_json(installer_request_path, inspection_request)
                plan = json_object(
                    invoke(
                        [
                            str(arguments.compatforge_cli),
                            "prepared-plan",
                            str(context_path),
                            str(installer),
                            str(installer_request_path),
                        ]
                    ),
                    f"{asset.app_id} installer plan",
                )
                evidence["installerPlan"] = plan
                installer_events = run_events(
                    invoke(
                        [
                            str(arguments.compatforge_cli),
                            "prepared-launch-terminate",
                            str(context_path),
                            str(installer),
                            str(installer_request_path),
                            str(asset.install_wait_milliseconds),
                        ]
                    ),
                    f"{asset.app_id} installer",
                )
                evidence["installerEvents"] = installer_events
                evidence["installerExit"] = exit_observation(installer_events)
                installed = installed_executable(asset, bottle_root)
                if not installed.is_file() or installed.is_symlink():
                    evidence["status"] = "unverified"
                    evidence["reason"] = "installer exited but expected GUI executable was not found"
                    results.append(evidence)
                    continue
                launch_request = {
                    "schemaVersion": "1",
                    "requestId": str(uuid.uuid4()),
                    "bottleId": bottle_id,
                    "executable": {
                        "path": str(installed),
                        "architecture": "x86_64",
                        "mode": "bottleInPlace",
                    },
                    "arguments": list(asset.launch_args),
                    "environment": dict(asset.runtime_environment),
                    "constraints": {
                        "allowVirtualMachine": False,
                        "allowRemote": False,
                        "networkPolicy": "deny",
                    },
                }
                launch_request_path = arguments.work_root / f"{asset.app_id}-launch-request.json"
                gui_inspection = json_object(
                    invoke([str(arguments.compatforge_cli), "inspect", str(installed)]),
                    f"{asset.app_id} GUI inspection",
                )
                gui_architecture = gui_inspection.get("architecture")
                if not isinstance(gui_architecture, str):
                    raise AcceptanceError(f"{asset.app_id} GUI inspection omitted architecture")
                launch_request["executable"]["architecture"] = request_architecture(gui_architecture)  # type: ignore[index]
                write_json(launch_request_path, launch_request)
                evidence["inspection"] = gui_inspection
                evidence["plan"] = json_object(
                    invoke(
                        [
                            str(arguments.compatforge_cli),
                            "prepared-plan",
                            str(context_path),
                            str(installed),
                            str(launch_request_path),
                        ]
                    ),
                    f"{asset.app_id} GUI plan",
                )
                events, windows, shot, process_group_id = observed_launch(
                    [
                        str(arguments.compatforge_cli),
                        "prepared-launch-terminate",
                        str(context_path),
                        str(installed),
                        str(launch_request_path),
                        str(INTERACTIVE_RUNTIME_MILLISECONDS if arguments.accept_interactive else 30_000),
                    ],
                    arguments.work_root / f"{asset.app_id}.png",
                    asset.window_title_tokens,
                    screenshot_delay_seconds=asset.screenshot_delay_seconds,
                    window_appearance_seconds=asset.window_appearance_seconds,
                )
                evidence["events"] = events
                evidence["exit"] = exit_observation(events)
                evidence["windows"] = windows
                evidence["screenshot"] = shot
                evidence["interactionChecks"] = manual_checks.get(asset.app_id, {})
                evidence["residualProcesses"] = process_snapshot(str(bottle_root), process_group_id)
                basic = status(events) == "accepted" and evidence["windows"].get("available") is True and evidence[
                    "screenshot"
                ].get("available") is True and not evidence["residualProcesses"]
                interactions_complete = all(
                    evidence["interactionChecks"].get(name) is True
                    for name in REQUIRED_INTERACTIONS[asset.app_id]
                )
                evidence["status"] = "accepted" if basic and interactions_complete else "unverified"
                if not basic:
                    evidence["reason"] = "target window/screenshot/exit cleanup evidence is incomplete"
                elif not interactions_complete:
                    evidence["reason"] = "required per-application interaction evidence was not supplied"
            except (AcceptanceError, OSError, subprocess.TimeoutExpired) as error:
                evidence["status"] = "failed"
                evidence["reason"] = str(error)
            finally:
                try:
                    if bottle_root.exists() or bottle_root.is_symlink():
                        if bottle_root.is_symlink():
                            raise AcceptanceError("Bottle root became a symlink")
                        shutil.rmtree(arguments.storage_root / "bottles" / bottle_id)
                    evidence["cleanup"] = True
                except (OSError, AcceptanceError) as error:
                    evidence["cleanup"] = False
                    evidence["cleanupError"] = str(error)
                if evidence["status"] == "accepted" and evidence["cleanup"] is not True:
                    evidence["status"] = "failed"
                    evidence["reason"] = "Bottle cleanup failed"
                write_json(arguments.work_root / f"{asset.app_id}-evidence.json", evidence)
                results.append(evidence)

        summary = {"schemaVersion": "1", "receipt": receipt, "applications": results}
        write_json(arguments.work_root / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0 if all(value["status"] == "accepted" for value in results) else 1
    except (AcceptanceError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ImportError) as error:
        print(f"compatforge-gui-baseline: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
