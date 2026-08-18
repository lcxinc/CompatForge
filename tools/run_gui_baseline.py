#!/usr/bin/env python3
"""Opt-in macOS GUI acceptance for the fixed CompatForge baseline apps.

This script intentionally records ``accepted``, ``failed`` or ``unverified``
per application. A visible process or a blank window is never promoted to an
acceptance claim. Downloads, screenshots and evidence live in caller-owned
external directories and are excluded from the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import selectors
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "tools" / "download_gui_assets.py"
MAX_COMMAND_SECONDS = 180
WINDOW_APPEARANCE_SECONDS = 30
INTERACTIVE_RUNTIME_MILLISECONDS = 60_000
MAX_INTERACTION_EVIDENCE_BYTES = 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4096
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
TEST_SUITE_VERSION = "gui-interactive-v2"

REQUIRED_INTERACTIONS = {
    "7zip": ("fileList", "menus", "cjkTextReadable"),
    "sumatrapdf": ("mainWindow", "openDialog", "cjkTextReadable"),
    "notepad-plus-plus": ("open", "edit", "saveUtf8Chinese", "rereadMatches", "cjkTextReadable"),
    "firefox": ("mainWindow", "browserContentRendered", "cjkTextReadable"),
    "krita": ("mainWindow", "workspaceVisible", "cjkTextReadable"),
    "7zip-x86": ("fileList", "menus", "cjkTextReadable"),
    "vlc": ("mainWindow", "mediaControls", "cjkTextReadable"),
    "winmerge": ("mainWindow", "compareDialog", "cjkTextReadable"),
    "audacity-x86": ("mainWindow", "waveformWorkspace", "cjkTextReadable"),
    "everything-x86": ("mainWindow", "searchField", "cjkTextReadable"),
}
BASELINE_APPLICATION_IDS = {"7zip", "sumatrapdf", "notepad-plus-plus"}


class AcceptanceError(Exception):
    pass


class InfrastructureUnavailable(AcceptanceError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def prefix_process_ids(bottle_root: Path) -> set[int] | None:
    """Return macOS clients retaining this exact prefix marker/directory."""
    if platform.system() != "Darwin":
        return set()
    system32 = bottle_root / "windows" / "system32"
    marker = system32 / "ntdll.dll"
    if not system32.is_dir() or system32.is_symlink() or not marker.is_file() or marker.is_symlink():
        return None
    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-t", "--", str(marker), str(system32)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
            env={},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in (0, 1) or len(result.stdout.encode("utf-8")) > 64 * 1024:
        return None
    process_ids: set[int] = set()
    for line in result.stdout.splitlines():
        try:
            process_id = int(line)
        except ValueError:
            return None
        if process_id > 1:
            process_ids.add(process_id)
    return process_ids


def process_snapshot(bottle_root: Path, process_group_id: int | None = None) -> list[str]:
    """List residual commands or loaded clients tied to the exact Bottle."""
    current = os.getpid()
    rows = process_table()
    if not rows:
        return ["process observation unavailable"]
    loaded = prefix_process_ids(bottle_root)
    if loaded is None:
        return ["prefix process observation unavailable"]
    marker = str(bottle_root)
    return [
        f"{pid} {command}"
        for pid, pgid, command in rows
        if pid != current
        and (pid in loaded or marker in command or (process_group_id is not None and pgid == process_group_id))
    ]


def process_group_ids(process_group_id: int) -> list[int]:
    return [pid for pid, pgid, _command in process_table() if pgid == process_group_id]


def cleanup_bottle(context: dict[str, object], storage_root: Path, bottle_id: str) -> dict[str, object]:
    """Stop only the bound Bottle's Wine server, verify, then remove its directory."""
    if not bottle_id or bottle_id in {".", ".."} or "/" in bottle_id or "\\" in bottle_id:
        return {"success": False, "reason": "Bottle identifier is not a single path component"}
    bottle_directory = storage_root / "bottles" / bottle_id
    prefix = bottle_directory / "prefix"
    drive_c = prefix / "drive_c"
    if not bottle_directory.exists() and not bottle_directory.is_symlink():
        return {"success": True, "method": "already-absent", "residualProcessIds": []}
    if bottle_directory.is_symlink() or not bottle_directory.is_dir():
        return {"success": False, "reason": "Bottle directory is not a regular directory"}

    bindings = context.get("runtimeBindings")
    if not isinstance(bindings, list) or len(bindings) != 1 or not isinstance(bindings[0], dict):
        return {"success": False, "reason": "context must contain exactly one runtime binding"}
    binding = bindings[0]
    wineserver_value = binding.get("wineserverExecutable")
    environment_value = binding.get("environment")
    if not isinstance(wineserver_value, str) or not isinstance(environment_value, dict):
        return {"success": False, "reason": "runtime binding omitted wineserver cleanup data"}
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in environment_value.items()):
        return {"success": False, "reason": "runtime binding environment must contain only strings"}
    wineserver = Path(wineserver_value)
    if not wineserver.is_absolute() or not wineserver.is_file() or wineserver.is_symlink() or not os.access(wineserver, os.X_OK):
        return {"success": False, "reason": "bound wineserver is not an absolute regular executable"}
    expected_digest = environment_value.get("COMPATFORGE_WINESERVER_EXECUTABLE_SHA256")
    if not isinstance(expected_digest, str) or expected_digest != f"sha256:{file_sha256(wineserver)}":
        return {"success": False, "reason": "bound wineserver digest changed before cleanup"}

    cleanup_environment = dict(environment_value)
    cleanup_environment["WINEPREFIX"] = str(prefix)
    try:
        terminated = subprocess.run(
            [str(wineserver), "-k"],
            cwd=bottle_directory,
            env=cleanup_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"success": False, "reason": f"Bottle-scoped wineserver cleanup failed: {error}"}
    if terminated.returncode not in (0, 1):
        return {"success": False, "reason": f"Bottle-scoped wineserver returned {terminated.returncode}"}

    time.sleep(0.5)
    loaded = prefix_process_ids(drive_c)
    command_residuals = [pid for pid, _pgid, command in process_table() if str(prefix) in command]
    residuals = sorted((loaded or set()).union(command_residuals))
    if residuals:
        return {
            "success": False,
            "reason": "Bottle-scoped processes remained after wineserver cleanup",
            "wineserverReturnCode": terminated.returncode,
            "residualProcessIds": residuals,
        }
    try:
        shutil.rmtree(bottle_directory)
    except OSError as error:
        return {"success": False, "reason": f"Bottle directory removal failed: {error}"}
    return {
        "success": not bottle_directory.exists() and not bottle_directory.is_symlink(),
        "method": "bound-wineserver-kill-and-remove",
        "wineserverReturnCode": terminated.returncode,
        "residualProcessIds": [],
    }


def matching_windows(output: str, title_tokens: tuple[str, ...]) -> list[dict[str, object]]:
    matching: list[dict[str, object]] = []
    for line in output.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            process_id_value, title, dimensions_value = parts
        elif len(parts) == 4:
            _process_name, process_id_value, title, dimensions_value = parts
        else:
            continue
        if not any(token.casefold() in title.casefold() for token in title_tokens):
            continue
        dimensions = dimensions_value.split("x", 1)
        try:
            process_id = int(process_id_value)
            width = int(dimensions[0])
            height = int(dimensions[1])
        except (ValueError, IndexError):
            continue
        if width <= 0 or height <= 0:
            continue
        matching.append({"processId": process_id, "title": title, "width": width, "height": height})
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


def launch_runtime_milliseconds(
    window_appearance_seconds: int,
    screenshot_delay_seconds: int,
    accept_interactive: bool,
) -> int:
    """Keep the guest alive long enough to consume its visual evidence budget."""
    minimum = INTERACTIVE_RUNTIME_MILLISECONDS if accept_interactive else 30_000
    visual_budget = (max(window_appearance_seconds, screenshot_delay_seconds) + 5) * 1_000
    return max(minimum, visual_budget)


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


def desktop_session_state() -> dict[str, object]:
    """Classify whether macOS can currently provide interactive GUI evidence."""
    if platform.system() != "Darwin":
        return {
            "observable": False,
            "state": "unsupported-host",
            "failureClassification": "test-infrastructure",
        }
    try:
        session_result = subprocess.run(
            ["/usr/sbin/ioreg", "-n", "Root", "-d1"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
        power_result = subprocess.run(
            ["/usr/bin/pmset", "-g", "assertions"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "observable": False,
            "state": "session-probe-unavailable",
            "failureClassification": "test-infrastructure",
        }
    locked = any(
        marker in session_result.stdout
        for marker in (
            '"CGSSessionScreenIsLocked"=Yes',
            '"CGSSessionScreenIsLocked" = Yes',
            '"CGSSessionScreenIsLocked"=true',
            '"CGSSessionScreenIsLocked" = true',
            '"IOConsoleLocked"=Yes',
            '"IOConsoleLocked" = Yes',
        )
    )
    on_console = '"kCGSSessionOnConsoleKey"=Yes' in session_result.stdout
    assertions = {
        parts[0]: parts[1] == "1"
        for line in power_result.stdout.splitlines()
        if len(parts := line.split()) == 2 and parts[1] in {"0", "1"}
    }
    user_active = assertions.get("UserIsActive") is True
    display_held_awake = assertions.get("PreventUserIdleDisplaySleep") is True
    observable = (
        session_result.returncode == 0
        and power_result.returncode == 0
        and on_console
        and not locked
        and (user_active or display_held_awake)
    )
    if locked:
        state = "locked"
    elif not on_console:
        state = "not-console-session"
    elif not user_active and not display_held_awake:
        state = "display-inactive"
    elif session_result.returncode != 0 or power_result.returncode != 0:
        state = "session-probe-unavailable"
    else:
        state = "interactive"
    return {
        "observable": observable,
        "state": state,
        "onConsole": on_console,
        "userActive": user_active,
        "displayHeldAwake": display_held_awake,
        **({"failureClassification": "test-infrastructure"} if not observable else {}),
    }


def observation_diagnostic(windows: dict[str, object], shot: dict[str, object]) -> dict[str, object]:
    if windows.get("available") is True and shot.get("available") is True:
        return {"state": "observed"}
    reason = str(windows.get("reason") or shot.get("reason") or "visual evidence incomplete")
    infrastructure = windows.get("failureClassification") == "test-infrastructure" or any(
        token in reason.casefold()
        for token in ("locked", "inactive", "console-session", "accessibility", "osascript", "screencapture", "unavailable")
    )
    return {
        "state": "infrastructure-unavailable" if infrastructure else "target-not-observed",
        "failureClassification": "test-infrastructure" if infrastructure else "runtime-regression",
        "reason": reason,
    }


def observer(process_group_id: int, title_tokens: tuple[str, ...]) -> dict[str, object]:
    if platform.system() != "Darwin":
        return {
            "available": False,
            "reason": "window observation requires macOS",
            "failureClassification": "test-infrastructure",
        }
    session = desktop_session_state()
    if session.get("observable") is not True:
        return {
            "available": False,
            "reason": f"desktop session is {session.get('state')}",
            "session": session,
            "failureClassification": "test-infrastructure",
        }
    target_ids = process_group_ids(process_group_id)
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
        return {
            "available": False,
            "reason": "osascript unavailable",
            "failureClassification": "test-infrastructure",
        }
    if result.returncode != 0:
        return {
            "available": False,
            "reason": "Accessibility permission unavailable",
            "failureClassification": "test-infrastructure",
        }
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
        "reason": "target window was not observed",
        "processGroupId": process_group_id,
        "processIds": target_ids,
        "failureClassification": "runtime-regression",
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
        return {
            "available": False,
            "reason": "screencapture unavailable",
            "failureClassification": "test-infrastructure",
        }
    available = result.returncode == 0 and path.is_file() and path.stat().st_size > 0
    return {
        "available": available,
        "path": str(path),
        **(
            {}
            if available
            else {"reason": "screencapture returned no image", "failureClassification": "test-infrastructure"}
        ),
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_interaction_evidence(
    path: Path | None,
    accept_interactive: bool,
    application_ids: set[str] | None = None,
) -> tuple[dict[str, dict[str, bool]], dict[str, str]]:
    application_ids = application_ids or BASELINE_APPLICATION_IDS
    if not accept_interactive:
        if path is not None:
            raise AcceptanceError("--interaction-evidence requires --accept-interactive")
        return {}, {}
    if path is None:
        raise AcceptanceError("--accept-interactive requires --interaction-evidence")
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_INTERACTION_EVIDENCE_BYTES:
        raise AcceptanceError("interaction evidence must be a bounded regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceError("interaction evidence is not readable JSON") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != "2":
        raise AcceptanceError("interaction evidence must use schemaVersion 2")
    if set(value) != {"schemaVersion", "attestation", "applications"}:
        raise AcceptanceError("interaction evidence contains unknown fields")
    attestation = value.get("attestation")
    if not isinstance(attestation, dict) or set(attestation) != {"mode", "observer", "observedAt"}:
        raise AcceptanceError("interaction evidence omitted the closed attestation")
    if attestation.get("mode") != "human":
        raise AcceptanceError("interactive acceptance requires a human attestation")
    observer_name = attestation.get("observer")
    observed_at = attestation.get("observedAt")
    if not isinstance(observer_name, str) or not observer_name.strip() or len(observer_name.encode("utf-8")) > 256:
        raise AcceptanceError("interaction observer is invalid")
    if not isinstance(observed_at, str):
        raise AcceptanceError("interaction observedAt is invalid")
    try:
        parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise AcceptanceError("interaction observedAt is invalid") from error
    if parsed_observed_at.tzinfo is None:
        raise AcceptanceError("interaction observedAt must include a timezone")
    applications = value.get("applications")
    if not isinstance(applications, dict):
        raise AcceptanceError("interaction evidence omitted applications")
    result: dict[str, dict[str, bool]] = {}
    for app_id in application_ids:
        required = REQUIRED_INTERACTIONS[app_id]
        checks = applications.get(app_id)
        if (
            not isinstance(checks, dict)
            or set(checks) != set(required)
            or any(checks.get(name) is not True for name in required)
        ):
            raise AcceptanceError(f"interaction evidence is incomplete for {app_id}")
        result[app_id] = {name: True for name in required}
    return result, {
        "mode": "human",
        "observer": observer_name.strip(),
        "observedAt": observed_at,
    }


def interaction_evidence(
    path: Path | None,
    accept_interactive: bool,
    application_ids: set[str] | None = None,
) -> dict[str, dict[str, bool]]:
    """Return validated checks for callers that do not need attestation metadata."""
    return load_interaction_evidence(path, accept_interactive, application_ids)[0]


def installed_executable(asset, bottle_root: Path) -> Path:  # type: ignore[no-untyped-def]
    """Resolve only fixed, application-specific install locations."""
    primary = bottle_root / Path(asset.installed_executable)
    candidates = [primary, *(bottle_root / Path(value) for value in asset.alternate_installed_executables)]
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


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return stream_sha256(source)


def stream_sha256(source) -> str:  # type: ignore[no-untyped-def]
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(64 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def materialize_portable_zip(archive: Path, bottle_root: Path, expected_sha256: str) -> dict[str, object]:
    """Extract a fixed-digest portable ZIP without links, traversal, or overwrites."""
    descriptor = os.open(archive, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as pinned:
        metadata = os.fstat(pinned.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise AcceptanceError("portable archive is not a regular file")
        if stream_sha256(pinned) != expected_sha256:
            raise AcceptanceError("portable archive digest changed before materialization")
        pinned.seek(0)
        with zipfile.ZipFile(pinned) as bundle:
            entries = bundle.infolist()
            if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
                raise AcceptanceError("portable archive entry count is outside the fixed bound")
            total = sum(entry.file_size for entry in entries)
            if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise AcceptanceError("portable archive exceeds the uncompressed size bound")
            seen: set[str] = set()
            for entry in entries:
                if "\\" in entry.filename:
                    raise AcceptanceError("portable archive contains a non-canonical path")
                relative = PurePosixPath(entry.filename)
                if relative.is_absolute() or not relative.parts or any(
                    part in ("", ".", "..") for part in relative.parts
                ):
                    raise AcceptanceError("portable archive contains path traversal")
                folded = "/".join(relative.parts).casefold().rstrip("/")
                if folded in seen and not entry.is_dir():
                    raise AcceptanceError("portable archive contains a duplicate path")
                seen.add(folded)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise AcceptanceError("portable archive contains a symbolic link")
                destination = bottle_root.joinpath(*relative.parts)
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    if destination.is_symlink():
                        raise AcceptanceError("portable archive directory became a symbolic link")
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() or destination.is_symlink():
                    raise AcceptanceError("portable archive would overwrite an existing path")
                with bundle.open(entry) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=64 * 1024)
                if destination.stat().st_size != entry.file_size:
                    raise AcceptanceError("portable archive entry size changed during extraction")
        final_metadata = os.fstat(pinned.fileno())
        if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
            final_metadata.st_dev,
            final_metadata.st_ino,
            final_metadata.st_size,
        ):
            raise AcceptanceError("portable archive identity changed during materialization")
    return {
        "schemaVersion": "1",
        "format": "zip",
        "fileDigest": "sha256:" + expected_sha256,
        "fileSizeBytes": metadata.st_size,
        "entryCount": len(entries),
        "uncompressedBytes": total,
    }


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


def matrix_entry_digest(asset) -> str:  # type: ignore[no-untyped-def]
    value = {
        "appId": asset.app_id,
        "displayName": asset.display_name,
        "installerSha256": asset.sha256,
        "installArgs": list(asset.install_args),
        "installedExecutable": asset.installed_executable,
        "alternateInstalledExecutables": list(asset.alternate_installed_executables),
        "launchArgs": list(asset.launch_args),
        "runtimeEnvironment": dict(asset.runtime_environment),
        "installWaitMilliseconds": asset.install_wait_milliseconds,
        "screenshotDelaySeconds": asset.screenshot_delay_seconds,
        "windowAppearanceSeconds": asset.window_appearance_seconds,
        "category": asset.category,
        "toolkit": asset.toolkit,
        "guestArchitecture": asset.guest_architecture,
        "packageKind": asset.package_kind,
        "requiredInteractions": list(REQUIRED_INTERACTIONS[asset.app_id]),
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def check_outcome(passed: bool, *, blocked: bool = False) -> str:
    if passed:
        return "passed"
    return "blocked" if blocked else "failed"


def compatibility_result(
    asset,  # type: ignore[no-untyped-def]
    evidence: dict[str, object],
    receipt: dict[str, object],
    started_at: str,
    finished_at: str,
) -> dict[str, object]:
    status_value = evidence.get("status")
    blocked = status_value == "unverified"
    accepted = status_value == "accepted"
    windows = evidence.get("windows") if isinstance(evidence.get("windows"), dict) else {}
    shot = evidence.get("screenshot") if isinstance(evidence.get("screenshot"), dict) else {}
    exit_value = evidence.get("exit") if isinstance(evidence.get("exit"), dict) else {}
    interactions = evidence.get("interactionChecks") if isinstance(evidence.get("interactionChecks"), dict) else {}
    residual = evidence.get("residualProcesses") if isinstance(evidence.get("residualProcesses"), list) else []
    failure_classification = evidence.get("failureClassification")
    if not accepted and failure_classification is None:
        failure_classification = "policy-blocked" if blocked else "runtime-regression"
    checks = [
        {
            "id": "installer-inspection",
            "outcome": check_outcome(isinstance(evidence.get("installerInspection"), dict)),
        },
        {
            "id": "window-visible",
            "outcome": check_outcome(windows.get("available") is True, blocked=blocked),
            **({"message": str(windows.get("reason"))} if windows.get("reason") else {}),
        },
        {
            "id": "screenshot",
            "outcome": check_outcome(shot.get("available") is True, blocked=blocked),
            **(
                {"artifacts": [Path(str(shot["path"])).name]}
                if shot.get("available") is True and isinstance(shot.get("path"), str)
                else {}
            ),
        },
        {
            "id": "interactive-behavior",
            "outcome": check_outcome(
                all(interactions.get(name) is True for name in REQUIRED_INTERACTIONS[asset.app_id]),
                blocked=True,
            ),
        },
        {
            "id": "lifecycle-exit",
            "outcome": check_outcome(exit_value.get("present") is True),
        },
        {
            "id": "bottle-cleanup",
            "outcome": check_outcome(evidence.get("cleanup") is True),
        },
        {
            "id": "no-residual-processes",
            "outcome": check_outcome(not residual),
        },
    ]
    return {
        "schemaVersion": "1",
        "runId": str(uuid.uuid4()),
        "recipeId": asset.app_id,
        "recipeDigest": matrix_entry_digest(asset),
        "installerDigest": "sha256:" + asset.sha256,
        "testSuiteVersion": TEST_SUITE_VERSION,
        "host": {
            "os": "macos",
            "version": platform.mac_ver()[0],
            "architecture": platform.machine(),
        },
        "runtimePackDigest": receipt.get("packDigest"),
        "outcome": "passed" if accepted else ("blocked" if blocked else "failed"),
        **({"failureClassification": failure_classification} if failure_classification is not None else {}),
        "startedAt": started_at,
        "finishedAt": finished_at,
        "checks": checks,
    }


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
        manual_checks, manual_attestation = load_interaction_evidence(
            evidence_path,
            arguments.accept_interactive,
            selected_applications,
        )

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
        compatibility_results: list[dict[str, object]] = []
        for asset in ASSETS:
            if asset.app_id not in selected_applications:
                continue
            bottle_id = f"gui-{asset.app_id}"
            bottle_root = arguments.storage_root / "bottles" / bottle_id / "prefix" / "drive_c"
            bottle_root.mkdir(parents=True, exist_ok=True)
            started_at = utc_now()
            evidence: dict[str, object] = {
                "schemaVersion": "1",
                "appId": asset.app_id,
                "bottleId": bottle_id,
                "matrix": {
                    "category": asset.category,
                    "toolkit": asset.toolkit,
                    "guestArchitecture": asset.guest_architecture,
                    "recipeDigest": matrix_entry_digest(asset),
                },
                "startedAt": started_at,
                "status": "unverified",
                "cleanup": False,
            }
            try:
                desktop_preflight = desktop_session_state()
                evidence["desktopPreflight"] = desktop_preflight
                if desktop_preflight.get("observable") is not True:
                    raise InfrastructureUnavailable(f"desktop session is {desktop_preflight.get('state')}")
                package = fetch_asset(arguments, asset.app_id)
                if asset.package_kind == "portable-zip":
                    evidence["installerInspection"] = materialize_portable_zip(
                        package,
                        bottle_root,
                        asset.sha256,
                    )
                elif asset.package_kind == "installer":
                    installer_inspection = json_object(
                        invoke([str(arguments.compatforge_cli), "inspect", str(package)]),
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
                            "path": str(package),
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
                                str(package),
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
                                str(package),
                                str(installer_request_path),
                                str(asset.install_wait_milliseconds),
                            ]
                        ),
                        f"{asset.app_id} installer",
                    )
                    evidence["installerEvents"] = installer_events
                    evidence["installerExit"] = exit_observation(installer_events)
                else:
                    raise AcceptanceError(f"{asset.app_id} package kind is unsupported")
                installed = installed_executable(asset, bottle_root)
                if not installed.is_file() or installed.is_symlink():
                    evidence["status"] = "unverified"
                    evidence["reason"] = "package prepared but expected GUI executable was not found"
                    evidence["failureClassification"] = "recipe-regression"
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
                if request_architecture(gui_architecture) != asset.guest_architecture:
                    raise AcceptanceError(f"{asset.app_id} GUI architecture does not match the fixed matrix")
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
                        str(
                            launch_runtime_milliseconds(
                                asset.window_appearance_seconds,
                                asset.screenshot_delay_seconds,
                                arguments.accept_interactive,
                            )
                        ),
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
                evidence["observation"] = observation_diagnostic(windows, shot)
                evidence["interactionChecks"] = manual_checks.get(asset.app_id, {})
                if manual_attestation:
                    evidence["interactionAttestation"] = manual_attestation
                evidence["residualProcesses"] = process_snapshot(bottle_root, process_group_id)
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
                    diagnostic = evidence["observation"]
                    if isinstance(diagnostic, dict):
                        evidence["failureClassification"] = diagnostic.get("failureClassification", "runtime-regression")
                elif not interactions_complete:
                    evidence["reason"] = "required per-application interaction evidence was not supplied"
                    evidence["failureClassification"] = "policy-blocked"
            except InfrastructureUnavailable as error:
                evidence["status"] = "unverified"
                evidence["reason"] = str(error)
                evidence["failureClassification"] = "test-infrastructure"
            except (AcceptanceError, OSError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
                evidence["status"] = "failed"
                evidence["reason"] = str(error)
                evidence["failureClassification"] = (
                    "installer-upstream" if "asset" in str(error).casefold() or "installer" in str(error).casefold()
                    else "runtime-regression"
                )
            finally:
                cleanup_evidence = cleanup_bottle(context, arguments.storage_root, bottle_id)
                evidence["cleanupEvidence"] = cleanup_evidence
                evidence["cleanup"] = cleanup_evidence.get("success") is True
                if evidence["cleanup"] is not True:
                    evidence["cleanupError"] = cleanup_evidence.get("reason", "Bottle cleanup failed")
                if evidence["status"] == "accepted" and evidence["cleanup"] is not True:
                    evidence["status"] = "failed"
                    evidence["reason"] = "Bottle cleanup failed"
                    evidence["failureClassification"] = "runtime-regression"
                finished_at = utc_now()
                evidence["finishedAt"] = finished_at
                result = compatibility_result(asset, evidence, receipt, started_at, finished_at)
                write_json(arguments.work_root / f"{asset.app_id}-evidence.json", evidence)
                write_json(arguments.work_root / f"{asset.app_id}-compatibility-result.json", result)
                results.append(evidence)
                compatibility_results.append(result)

        summary = {
            "schemaVersion": "1",
            "testSuiteVersion": TEST_SUITE_VERSION,
            "receipt": receipt,
            "applications": results,
            "compatibilityResults": compatibility_results,
        }
        write_json(arguments.work_root / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0 if all(value["status"] == "accepted" for value in results) else 1
    except (
        AcceptanceError,
        OSError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        ImportError,
        zipfile.BadZipFile,
    ) as error:
        print(f"compatforge-gui-baseline: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
