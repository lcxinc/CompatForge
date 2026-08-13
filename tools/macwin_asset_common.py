"""Strict, deterministic boundaries shared by the Mac-Win migration tools."""

from __future__ import annotations

import json
from typing import NoReturn


MAX_METADATA_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 128
MIN_JSON_INTEGER = -(2**63)
MAX_JSON_INTEGER = (2**63) - 1


class MigrationError(ValueError):
    """A bounded, stable migration contract error."""


def _fail(message: str) -> NoReturn:
    raise MigrationError(message)


def _prescan_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                _fail("metadata exceeds the JSON nesting limit")
        elif character in "]}":
            depth -= 1


def _reject_constant(_value: str) -> NoReturn:
    _fail("metadata is not strict JSON")


def _parse_integer(value: str) -> int:
    try:
        parsed = int(value, 10)
    except (ValueError, OverflowError):
        _fail("metadata contains an invalid integer")
    if parsed < MIN_JSON_INTEGER or parsed > MAX_JSON_INTEGER:
        _fail("metadata contains an out-of-range integer")
    return parsed


def _reject_float(_value: str) -> NoReturn:
    _fail("metadata contains a non-integer number")


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("metadata contains duplicate object keys")
        result[key] = value
    return result


def parse_json_bytes(
    raw: bytes,
    label: str,
    max_bytes: int = MAX_METADATA_BYTES,
) -> object:
    """Parse bounded strict UTF-8 JSON without reflecting untrusted input."""

    del label
    if type(raw) is not bytes or type(max_bytes) is not int or max_bytes < 1:
        _fail("metadata parser configuration is invalid")
    if len(raw) > max_bytes:
        _fail("metadata exceeds the byte limit")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("metadata is not valid UTF-8")

    _prescan_json_depth(text)
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_integer,
        )
    except MigrationError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError, OverflowError):
        _fail("metadata is not valid JSON")


def _validate_canonical_value(value: object) -> None:
    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    active: set[int] = set()

    while stack:
        current, parent_depth, exiting = stack.pop()
        current_type = type(current)
        if current_type in (list, dict):
            identity = id(current)
            if exiting:
                active.remove(identity)
                continue
            if identity in active:
                _fail("canonical JSON contains a reference cycle")
            depth = parent_depth + 1
            if depth > MAX_JSON_DEPTH:
                _fail("canonical JSON exceeds the nesting limit")
            active.add(identity)
            stack.append((current, parent_depth, True))
            if current_type is list:
                for item in reversed(current):
                    stack.append((item, depth, False))
            else:
                items = list(current.items())
                for key, item in reversed(items):
                    if type(key) is not str:
                        _fail("canonical JSON object keys must be strings")
                    stack.append((key, depth, False))
                    stack.append((item, depth, False))
        elif current is None or current_type in (bool, str):
            continue
        elif current_type is int:
            if current < MIN_JSON_INTEGER or current > MAX_JSON_INTEGER:
                _fail("canonical JSON contains an out-of-range integer")
        else:
            _fail("canonical JSON contains an unsupported value")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize the supported JSON value model to canonical UTF-8/LF bytes."""

    _validate_canonical_value(value)
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        encoded = (rendered + "\n").encode("utf-8", errors="strict")
    except (RecursionError, UnicodeError, TypeError, ValueError, OverflowError):
        _fail("canonical JSON serialization failed")
    if len(encoded) > MAX_METADATA_BYTES:
        _fail("canonical JSON exceeds the byte limit")
    return encoded


def require_relative_posix_path(value: str) -> str:
    """Return an ASCII repository-relative POSIX path or fail closed."""

    if type(value) is not str or not value or len(value) > 4096:
        _fail("path is not a safe relative POSIX path")
    try:
        encoded = value.encode("ascii", errors="strict")
    except UnicodeEncodeError:
        _fail("path is not a safe relative POSIX path")
    if any(byte < 0x20 or byte == 0x7F for byte in encoded):
        _fail("path is not a safe relative POSIX path")
    if (
        value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or ":" in value
        or "//" in value
    ):
        _fail("path is not a safe relative POSIX path")
    if any(part in ("", ".", "..") for part in value.split("/")):
        _fail("path is not a safe relative POSIX path")
    return value
