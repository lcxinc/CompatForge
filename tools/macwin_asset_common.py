"""Strict, deterministic boundaries shared by the Mac-Win migration tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import NoReturn


MAX_METADATA_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_JSON_COLLECTION_ITEMS = 100_000
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
    *,
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
        value = json.loads(
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
    _validate_json_strings(value)
    return value


def _validate_json_strings(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is str:
            try:
                current.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                _fail("metadata contains a non-Unicode scalar")
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is dict:
            pending.extend(current.keys())
            pending.extend(current.values())


def _emit_json_string(value: str, emit: Callable[[bytes], None]) -> None:
    """Emit one JSON string without allocating its complete encoded form."""

    escapes = {
        '"': b'\\"',
        "\\": b"\\\\",
        "\b": b"\\b",
        "\f": b"\\f",
        "\n": b"\\n",
        "\r": b"\\r",
        "\t": b"\\t",
    }
    chunk = bytearray(b'"')

    def flush() -> None:
        if chunk:
            emit(bytes(chunk))
            chunk.clear()

    for character in value:
        encoded = escapes.get(character)
        if encoded is None:
            codepoint = ord(character)
            if codepoint < 0x20:
                encoded = f"\\u{codepoint:04x}".encode("ascii")
            else:
                try:
                    encoded = character.encode("utf-8", errors="strict")
                except UnicodeEncodeError:
                    _fail("canonical JSON contains a non-Unicode scalar")
        if len(chunk) + len(encoded) > 4096:
            flush()
        chunk.extend(encoded)
    if len(chunk) == 4096:
        flush()
    chunk.extend(b'"')
    flush()


def canonical_json_bytes(value: object) -> bytes:
    """Serialize the supported JSON value model to canonical UTF-8/LF bytes."""

    output = bytearray()
    active: set[int] = set()
    stack: list[tuple[object, ...]] = [("value", value, 0)]
    node_count = 0

    def emit(chunk: bytes) -> None:
        if len(output) + len(chunk) > MAX_METADATA_BYTES:
            _fail("canonical JSON exceeds the byte limit")
        output.extend(chunk)

    while stack:
        frame = stack.pop()
        kind = frame[0]
        if kind == "value":
            current, parent_depth = frame[1], frame[2]
            node_count += 1
            if node_count > MAX_JSON_COLLECTION_ITEMS:
                _fail("canonical JSON exceeds the collection limit")
            current_type = type(current)
            if current is None:
                emit(b"null")
            elif current_type is bool:
                emit(b"true" if current else b"false")
            elif current_type is int:
                if current < MIN_JSON_INTEGER or current > MAX_JSON_INTEGER:
                    _fail("canonical JSON contains an out-of-range integer")
                emit(str(current).encode("ascii"))
            elif current_type is str:
                _emit_json_string(current, emit)
            elif current_type in (list, dict):
                identity = id(current)
                if identity in active:
                    _fail("canonical JSON contains a reference cycle")
                depth = parent_depth + 1
                if depth > MAX_JSON_DEPTH:
                    _fail("canonical JSON exceeds the nesting limit")
                if len(current) > MAX_JSON_COLLECTION_ITEMS:
                    _fail("canonical JSON exceeds the collection limit")
                active.add(identity)
                if current_type is list:
                    emit(b"[")
                    if current:
                        emit(b"\n")
                        stack.append(("list", current, 0, depth))
                    else:
                        active.remove(identity)
                        emit(b"]")
                else:
                    for key in current:
                        if type(key) is not str:
                            _fail("canonical JSON object keys must be strings")
                    try:
                        keys = tuple(sorted(current))
                    except (UnicodeError, ValueError, OverflowError):
                        _fail("canonical JSON key sorting failed")
                    emit(b"{")
                    if keys:
                        emit(b"\n")
                        stack.append(("object", current, keys, 0, depth))
                    else:
                        active.remove(identity)
                        emit(b"}")
            else:
                _fail("canonical JSON contains an unsupported value")
        elif kind == "list":
            current, index, depth = frame[1], frame[2], frame[3]
            if index == len(current):
                emit(b"\n" + (b" " * (2 * (depth - 1))) + b"]")
                active.remove(id(current))
            else:
                if index:
                    emit(b",\n")
                emit(b" " * (2 * depth))
                stack.append(("list", current, index + 1, depth))
                stack.append(("value", current[index], depth))
        else:
            current, keys, index, depth = frame[1], frame[2], frame[3], frame[4]
            if index == len(keys):
                emit(b"\n" + (b" " * (2 * (depth - 1))) + b"}")
                active.remove(id(current))
            else:
                if index:
                    emit(b",\n")
                key = keys[index]
                emit(b" " * (2 * depth))
                _emit_json_string(key, emit)
                emit(b": ")
                stack.append(("object", current, keys, index + 1, depth))
                stack.append(("value", current[key], depth))

    emit(b"\n")
    return bytes(output)


def require_relative_posix_path(value: str) -> str:
    """Return an ASCII repository-relative POSIX path or fail closed."""

    if type(value) is not str or not value:
        _fail("path is not a safe relative POSIX path")
    try:
        encoded = value.encode("ascii", errors="strict")
    except UnicodeEncodeError:
        _fail("path is not a safe relative POSIX path")
    if len(encoded) > 1024 or any(byte < 0x20 or byte == 0x7F for byte in encoded):
        _fail("path is not a safe relative POSIX path")
    if (
        value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or ":" in value
        or "//" in value
        or any(character in '<>"|?*' for character in value)
    ):
        _fail("path is not a safe relative POSIX path")
    reserved = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    reserved.update(f"com{number}" for number in range(1, 10))
    reserved.update(f"lpt{number}" for number in range(1, 10))
    for part in value.split("/"):
        device_stem = part.split(".", 1)[0].split(":", 1)[0].rstrip(" ").casefold()
        if (
            part in ("", ".", "..")
            or len(part.encode("utf-8")) > 255
            or part.endswith((".", " "))
            or device_stem in reserved
        ):
            _fail("path is not a safe relative POSIX path")
    return value
