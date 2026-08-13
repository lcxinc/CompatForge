from __future__ import annotations

import ast
import builtins
import concurrent.futures
import contextlib
import copy
import dataclasses
import hashlib
import importlib.util
import io
import json
import os
import random
import re
import runpy
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GIT_TIMEOUT_SECONDS = 30
IMPORT_PROBE_TIMEOUT_SECONDS = 30
IMPORT_PROBE_ENVIRONMENT_NAMES = frozenset(
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


def _load_macwin_asset_common():
    path = ROOT / "tools/macwin_asset_common.py"
    if not path.is_file():
        raise AssertionError("Mac-Win migration JSON boundary module is missing")
    spec = importlib.util.spec_from_file_location("macwin_asset_common_contract", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load Mac-Win migration JSON boundary module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_macwin_asset_converter():
    path = ROOT / "tools/convert_macwin_assets.py"
    if not path.is_file():
        raise AssertionError("Mac-Win migration converter is missing")
    spec = importlib.util.spec_from_file_location("macwin_asset_converter_contract", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load Mac-Win migration converter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class MigrationJsonBoundaryTests(unittest.TestCase):
    def test_parser_configuration_is_keyword_only(self) -> None:
        common = _load_macwin_asset_common()
        self.assertEqual(common.parse_json_bytes(b"{}", label="index"), {})
        with self.assertRaises(TypeError):
            common.parse_json_bytes(b"{}", "index")
        with self.assertRaises(TypeError):
            common.parse_json_bytes(b"{}", "index", 1024)

    def test_metadata_limit_is_enforced_before_decoding(self) -> None:
        common = _load_macwin_asset_common()
        self.assertEqual(common.MAX_METADATA_BYTES, 1024 * 1024)
        maximum = common.MAX_METADATA_BYTES
        exact = b'"' + (b"a" * (maximum - 2)) + b'"'
        self.assertEqual(len(exact), maximum)
        self.assertEqual(len(common.parse_json_bytes(exact, label="index")), maximum - 2)

        oversized = b"\xff" + (b" " * maximum)
        self.assertEqual(len(oversized), maximum + 1)
        with mock.patch.object(common.json, "loads") as loads:
            with self.assertRaises(common.MigrationError) as caught:
                common.parse_json_bytes(oversized, label="index")
        loads.assert_not_called()
        self.assertEqual(str(caught.exception), "metadata exceeds the byte limit")
        self._assert_stable_error(caught.exception)

    def test_parser_requires_strict_utf8(self) -> None:
        common = _load_macwin_asset_common()
        with self.assertRaises(common.MigrationError) as caught:
            common.parse_json_bytes(b'{"value":"\xff"}', label="index")
        self._assert_stable_error(caught.exception)

    def test_parser_rejects_surrogates_and_accepts_unicode_scalars(self) -> None:
        common = _load_macwin_asset_common()
        for raw in (
            b'"\\ud800"',
            b'"\\udfff"',
            b'{"\\ud800":1}',
            b'{"nested":["\\udfff"]}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(common.MigrationError) as caught:
                    common.parse_json_bytes(raw, label="index")
                self._assert_stable_error(caught.exception)
        expected = "\U0001f600"
        self.assertEqual(
            common.parse_json_bytes(b'"\\ud83d\\ude00"', label="index"), expected
        )
        self.assertEqual(
            common.parse_json_bytes(('"' + expected + '"').encode("utf-8"), label="index"),
            expected,
        )

    def test_parser_rejects_raw_nested_and_escaped_duplicate_keys(self) -> None:
        common = _load_macwin_asset_common()
        cases = (
            b'{"duplicate":1,"duplicate":2}',
            b'{"outer":{"duplicate":1,"duplicate":2}}',
            b'{"duplicate":1,"\\u0064uplicate":2}',
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(common.MigrationError) as caught:
                common.parse_json_bytes(raw, label="index")
            self._assert_stable_error(caught.exception)

    def test_parser_enforces_explicit_depth_before_json_loads(self) -> None:
        common = _load_macwin_asset_common()
        self.assertEqual(common.MAX_JSON_DEPTH, 128)
        at_limit = (b"[" * common.MAX_JSON_DEPTH) + b"0" + (
            b"]" * common.MAX_JSON_DEPTH
        )
        old_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(max(old_limit, 10_000))
            common.parse_json_bytes(at_limit, label="index")
            too_deep = b"[" + at_limit + b"]"
            with mock.patch.object(common.json, "loads") as loads:
                with self.assertRaises(common.MigrationError) as caught:
                    common.parse_json_bytes(too_deep, label="index")
            loads.assert_not_called()
        finally:
            sys.setrecursionlimit(old_limit)
        self._assert_stable_error(caught.exception)

    def test_depth_prescan_is_string_and_escape_aware(self) -> None:
        common = _load_macwin_asset_common()
        value = "[\\\"{not structural}\\\"]"
        self.assertEqual(
            common.parse_json_bytes(json.dumps(value).encode("utf-8"), label="index"),
            value,
        )

    def test_relative_posix_paths_are_host_independent(self) -> None:
        common = _load_macwin_asset_common()
        valid = (
            "MacWinManager/catalog/7zip.json",
            "migration/macwin/source/objects/sha256/ab/cdef",
            "a-b_c.1/file name.txt",
        )
        for value in valid:
            with self.subTest(path=value):
                self.assertEqual(common.require_relative_posix_path(value), value)

        invalid = (
            "",
            ".",
            "..",
            "/absolute",
            "//server/share",
            "C:/drive",
            "C:\\drive",
            "\\\\server\\share",
            "\\\\?\\C:\\device",
            "folder\\file",
            "folder:file",
            "folder//file",
            "folder/./file",
            "folder/../file",
            "folder/",
            "café/file",
            "control\x00/file",
            "CON",
            "con.txt",
            "folder/PRN.log",
            "folder/aux",
            "folder/NUL.txt",
            "CON .txt",
            "folder/NUL .txt",
            "COM1 .x",
            "folder/LPT1 .x",
            "CONIN$",
            "conin$.txt",
            "folder/CONOUT$ .log",
            "COM1/file",
            "folder/lpt9.bin",
            "folder/name.",
            "folder/name ",
            "folder/a<b",
            "folder/a>b",
            'folder/a"b',
            "folder/a|b",
            "folder/a?b",
            "folder/a*b",
            ("a" * 256) + "/file",
            "/".join(["a" * 255] * 5),
        )
        for value in invalid:
            with self.subTest(path=repr(value)), self.assertRaises(common.MigrationError):
                common.require_relative_posix_path(value)

        self.assertEqual(
            common.require_relative_posix_path(("a" * 255) + "/file"),
            ("a" * 255) + "/file",
        )

    def test_canonical_json_is_utf8_sorted_indented_and_lf_terminated(self) -> None:
        common = _load_macwin_asset_common()
        value = {"z": [None, True, -7], "é": {"a": "雪"}}
        self.assertEqual(
            common.canonical_json_bytes(value),
            (
                '{\n'
                '  "z": [\n'
                '    null,\n'
                '    true,\n'
                '    -7\n'
                '  ],\n'
                '  "é": {\n'
                '    "a": "雪"\n'
                '  }\n'
                '}\n'
            ).encode("utf-8"),
        )

    def test_canonical_json_rejects_unsupported_or_unbounded_values(self) -> None:
        common = _load_macwin_asset_common()
        cycle: list[object] = []
        cycle.append(cycle)
        invalid = (
            1.0,
            (1,),
            {1},
            b"bytes",
            {1: "non-string key"},
            common.MAX_JSON_INTEGER + 1,
            common.MIN_JSON_INTEGER - 1,
            cycle,
        )
        for value in invalid:
            with self.subTest(value=type(value).__name__), self.assertRaises(
                common.MigrationError
            ) as caught:
                common.canonical_json_bytes(value)
            self._assert_stable_error(caught.exception)

    def test_canonical_json_enforces_depth_iteratively(self) -> None:
        common = _load_macwin_asset_common()
        value: object = 0
        for _ in range(common.MAX_JSON_DEPTH):
            value = [value]
        common.canonical_json_bytes(value)
        value = [value]
        with self.assertRaises(common.MigrationError) as caught:
            common.canonical_json_bytes(value)
        self._assert_stable_error(caught.exception)

    def test_canonical_json_enforces_output_budget_without_json_dumps(self) -> None:
        common = _load_macwin_asset_common()
        exact = "a" * (common.MAX_METADATA_BYTES - 3)
        with mock.patch.object(common.json, "dumps", side_effect=AssertionError("not bounded")):
            encoded = common.canonical_json_bytes(exact)
            self.assertEqual(len(encoded), common.MAX_METADATA_BYTES)
            with self.assertRaises(common.MigrationError) as caught:
                common.canonical_json_bytes(exact + "a")
        self.assertEqual(str(caught.exception), "canonical JSON exceeds the byte limit")

        wide: object = list(range(100_000))
        for _ in range(common.MAX_JSON_DEPTH - 1):
            wide = [wide]
        tracemalloc.start()
        try:
            with self.assertRaises(common.MigrationError):
                common.canonical_json_bytes(wide)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 8 * common.MAX_METADATA_BYTES)

    def test_canonical_json_streams_oversized_strings_with_bounded_memory(self) -> None:
        common = _load_macwin_asset_common()
        values = (
            "a" * (8 * common.MAX_METADATA_BYTES),
            "\n" * common.MAX_METADATA_BYTES,
        )
        for value in values:
            with self.subTest(character=repr(value[0])), mock.patch.object(
                common.json.encoder,
                "encode_basestring",
                side_effect=AssertionError("unbounded string encoder called"),
            ):
                tracemalloc.start()
                try:
                    with self.assertRaises(common.MigrationError):
                        common.canonical_json_bytes(value)
                    _current, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertLess(peak, 4 * common.MAX_METADATA_BYTES)

    def test_canonical_json_matches_stdlib_for_allowed_fuzz_values(self) -> None:
        common = _load_macwin_asset_common()
        generator = random.Random(20260813)
        scalars: list[object] = [
            None,
            False,
            True,
            -7,
            0,
            42,
            "",
            "plain",
            "quote\"slash\\controls\n\t\x00",
            "".join(chr(codepoint) for codepoint in range(0x20))
            + '"\\\x7f\u2028',
            "雪😀",
        ]
        values: list[object] = [*scalars, [], {}, [1, "two", None]]
        for _ in range(100):
            keys = generator.sample(("a", "b", "é", "雪", "quote\""), 3)
            values.append(
                {
                    keys[0]: generator.choice(scalars),
                    keys[1]: [generator.choice(scalars), generator.choice(scalars)],
                    keys[2]: {"nested": generator.choice(scalars)},
                }
            )
        for value in values:
            with self.subTest(value=repr(value)[:80]):
                expected = (
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        allow_nan=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                self.assertEqual(common.canonical_json_bytes(value), expected)

    def test_errors_are_single_line_stable_and_do_not_reflect_input(self) -> None:
        common = _load_macwin_asset_common()
        hostile = "secret-key\x1b[31m\r\nsecond-line"
        raw = json.dumps({hostile: 1}, ensure_ascii=False)[:-1]
        raw += "," + json.dumps(hostile) + ":2}"
        messages = []
        for _ in range(2):
            with self.assertRaises(common.MigrationError) as caught:
                common.parse_json_bytes(raw.encode("utf-8"), label=hostile)
            messages.append(str(caught.exception))
            self._assert_stable_error(caught.exception)
            self.assertNotIn("secret-key", messages[-1])
        self.assertEqual(messages[0], messages[1])

    def _assert_stable_error(self, error: Exception) -> None:
        message = str(error)
        self.assertTrue(message)
        self.assertNotIn("\n", message)
        self.assertNotIn("\r", message)
        self.assertNotIn("\x1b", message)
        self.assertLessEqual(len(message.encode("utf-8")), 160)


class MigrationSchemaTests(unittest.TestCase):
    SCHEMA_NAMES = (
        "macwin-source-pack.schema.json",
        "migration-record.schema.json",
        "quarantine.schema.json",
        "portable-probe.schema.json",
        "portable-fixture.schema.json",
    )

    def test_new_schemas_have_unique_canonical_ids_and_exact_versions(self) -> None:
        schemas = self._schemas()
        identifiers = [schema["$id"] for schema in schemas.values()]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for name, schema in schemas.items():
            with self.subTest(schema=name):
                self.assertEqual(
                    schema["$id"], f"https://compatforge.dev/schemas/{name}"
                )
                self.assertEqual(schema["properties"]["schemaVersion"], {"const": "1"})
                self.assertIn("schemaVersion", schema["required"])

    def test_every_declared_object_boundary_is_closed(self) -> None:
        for name, schema in self._schemas().items():
            for location, node in self._walk_schema(schema):
                if node.get("type") == "object":
                    with self.subTest(schema=name, location=location):
                        self.assertIs(node.get("additionalProperties"), False)
                        self.assertIsInstance(node.get("properties"), dict)

    def test_collections_strings_and_integers_are_explicitly_bounded(self) -> None:
        for name, schema in self._schemas().items():
            for location, node in self._walk_schema(schema):
                node_type = node.get("type")
                with self.subTest(schema=name, location=location):
                    if node_type == "array":
                        self.assertIn("maxItems", node)
                    elif node_type == "string" and not any(
                        keyword in node for keyword in ("const", "enum", "$ref")
                    ):
                        self.assertIn("maxLength", node)
                    elif node_type == "integer":
                        self.assertIn("minimum", node)
                        self.assertIn("maximum", node)

    def test_all_path_fields_use_the_ascii_relative_posix_contract(self) -> None:
        for name, schema in self._schemas().items():
            relative_path = schema["$defs"]["relativePath"]
            pattern = re.compile(relative_path["pattern"], re.ASCII)
            self.assertEqual(relative_path["type"], "string", name)
            for value in (
                "MacWinManager/catalog/7zip.json",
                "objects/sha256/ab/cdef",
            ):
                self.assertIsNotNone(pattern.fullmatch(value), (name, value))
            for value in (
                "",
                ".",
                "..",
                "/absolute",
                "C:/drive",
                "C:\\drive",
                "\\\\server\\share",
                "\\\\?\\C:\\device",
                "a\\b",
                "a:b",
                "a//b",
                "a/./b",
                "a/../b",
                "a/",
                "café/file",
            ):
                self.assertIsNone(pattern.fullmatch(value), (name, value))

    def test_schema_patterns_use_absolute_end_and_reject_hostile_tail(self) -> None:
        for name in (*self.SCHEMA_NAMES, "recipe.schema.json"):
            schema = self._schema(name)
            for location, node in self._walk_schema(schema):
                pattern = node.get("pattern")
                if pattern is None:
                    continue
                with self.subTest(schema=name, location=location):
                    self.assertFalse(pattern.endswith("$"))
                    valid = self._valid_pattern_value(location, pattern)
                    self.assertIsNotNone(re.search(pattern, valid), (location, valid))
                    for suffix in ("\n", "\r", "\x00"):
                        self.assertIsNone(
                            re.search(pattern, valid + suffix),
                            (location, repr(valid + suffix)),
                        )

    def test_complete_schema_instances_reject_pattern_tail_mutants(self) -> None:
        instances = self._complete_schema_instances()
        mutations = {
            "macwin-source-pack.schema.json": lambda value: value.__setitem__(
                "sourceTag", value["sourceTag"] + "\n"
            ),
            "migration-record.schema.json": lambda value: value["records"][0].__setitem__(
                "sourcePath", value["records"][0]["sourcePath"] + "\n"
            ),
            "quarantine.schema.json": lambda value: value["records"][0].__setitem__(
                "sourceSha256", value["records"][0]["sourceSha256"] + "\n"
            ),
            "portable-probe.schema.json": lambda value: value.__setitem__(
                "mediaType", value["mediaType"] + "\n"
            ),
            "portable-fixture.schema.json": lambda value: value["source"].__setitem__(
                "sourcePath", value["source"]["sourcePath"] + "\n"
            ),
            "recipe.schema.json": lambda value: value["provenance"].__setitem__(
                "sourceCommit", value["provenance"]["sourceCommit"] + "\n"
            ),
        }
        for name, value in instances.items():
            schema = self._schema(name)
            with self.subTest(schema=name, case="valid"):
                self._assert_schema_instance_valid(value, schema, schema)
            mutant = copy.deepcopy(value)
            mutations[name](mutant)
            with self.subTest(schema=name, case="tail-mutant"):
                with self.assertRaises(AssertionError):
                    self._assert_schema_instance_valid(mutant, schema, schema)

    def test_schema_paths_match_portable_windows_segment_rules(self) -> None:
        valid = ("safe/path.txt", ("a" * 255) + "/file")
        invalid = (
            "CON",
            "con.txt",
            "folder/PRN.log",
            "folder/aux",
            "folder/NUL.txt",
            "CON .txt",
            "folder/NUL .txt",
            "COM1 .x",
            "folder/LPT1 .x",
            "CONIN$",
            "conin$.txt",
            "folder/CONOUT$ .log",
            "COM1/file",
            "folder/lpt9.bin",
            "folder/name.",
            "folder/name ",
            "folder/a<b",
            "folder/a>b",
            'folder/a"b',
            "folder/a|b",
            "folder/a?b",
            "folder/a*b",
            ("a" * 256) + "/file",
            "/".join(["a" * 255] * 5),
        )
        for name in (*self.SCHEMA_NAMES, "recipe.schema.json"):
            schema = self._schema(name)
            contract = schema["$defs"]["relativePath"]
            for value in valid:
                with self.subTest(schema=name, valid=value[:20]):
                    self._assert_schema_instance_valid(value, contract, schema)
            for value in invalid:
                with self.subTest(schema=name, invalid=value[:20]):
                    with self.assertRaises(AssertionError):
                        self._assert_schema_instance_valid(value, contract, schema)

    def test_schema_boundary_oracle_uses_only_the_standard_library(self) -> None:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported = set()
        importlib_aliases = {"importlib"}
        import_module_aliases = {"__import__"}
        dynamic_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                importlib_aliases.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "importlib"
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
                if node.module == "importlib":
                    import_module_aliases.update(
                        alias.asname or alias.name
                        for alias in node.names
                        if alias.name == "import_module"
                    )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "jsonschema"
                and (
                    (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id in importlib_aliases
                        and node.func.attr == "import_module"
                    )
                    or (
                        isinstance(node.func, ast.Name)
                        and node.func.id in import_module_aliases
                    )
                )
            ):
                dynamic_imports.add(node.args[0].value)
        self.assertNotIn("jsonschema", imported)
        self.assertNotIn("jsonschema", dynamic_imports)

    def test_source_pack_contract_captures_source_identities_and_dependencies(self) -> None:
        schema = self._schema("macwin-source-pack.schema.json")
        self.assertEqual(
            set(schema["required"]),
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
        self.assertEqual(schema["properties"]["repository"], {"const": "a1112/Mac-Win"})
        self.assertEqual(schema["properties"]["digestAlgorithm"], {"const": "sha256"})
        self.assertEqual(schema["properties"]["assetCount"], {"const": 90})
        counts = schema["properties"]["categoryCounts"]
        self.assertEqual(
            counts["properties"],
            {
                "catalog": {"const": 19},
                "patches": {"const": 11},
                "probes": {"const": 26},
                "fixtures": {"const": 30},
                "bottleSchema": {"const": 4},
            },
        )
        record = schema["$defs"]["sourceRecord"]
        self.assertEqual(
            set(record["required"]),
            {
                "category",
                "sourcePath",
                "sourceCommit",
                "gitMode",
                "gitBlobOid",
                "sha256",
                "byteSize",
                "kind",
                "license",
                "provenance",
                "intendedOwner",
                "externalRefs",
                "developmentDependencies",
                "objectPath",
            },
        )
        self.assertEqual(record["properties"]["externalRefs"]["uniqueItems"], True)
        self.assertEqual(
            record["properties"]["developmentDependencies"]["uniqueItems"], True
        )
        self.assertEqual(
            record["properties"]["provenance"], {"$ref": "#/$defs/reviewStatus"}
        )
        self.assertEqual(record["properties"]["license"], {"$ref": "#/$defs/reviewStatus"})
        self.assertEqual(record["properties"]["objectPath"], {"$ref": "#/$defs/objectPath"})
        object_path = re.compile(schema["$defs"]["objectPath"]["pattern"], re.ASCII)
        self.assertIsNotNone(
            object_path.fullmatch("objects/sha256/ab/" + ("c" * 62))
        )
        for value in (
            "migration/macwin/source/objects/sha256/ab/" + ("c" * 62),
            "objects/sha256/AB/" + ("c" * 62),
            "objects/sha256/ab/short",
            "objects/sha1/ab/" + ("c" * 62),
        ):
            self.assertIsNone(object_path.fullmatch(value), value)

    def test_source_pack_preserves_reviewed_regular_and_executable_git_modes(self) -> None:
        schema = self._schema("macwin-source-pack.schema.json")
        record = schema["$defs"]["sourceRecord"]
        reviewed_mode_counts = {"100644": 79, "100755": 11}
        self.assertEqual(sum(reviewed_mode_counts.values()), 90)

        git_mode = record["properties"]["gitMode"]
        self.assertEqual(git_mode, {"enum": ["100644", "100755"]})
        allowed_modes = set(git_mode["enum"])
        representative_assets = (
            {"category": "catalog", "kind": "catalog-record", "gitMode": "100644"},
            {"category": "probes", "kind": "probe", "gitMode": "100755"},
        )
        for asset in representative_assets:
            with self.subTest(asset=asset):
                self.assertIn(asset["category"], record["properties"]["category"]["enum"])
                self.assertIn(asset["kind"], record["properties"]["kind"]["enum"])
                self.assertIn(asset["gitMode"], allowed_modes)
        for unknown in ("100600", "100664", "120000", "160000", "100755 "):
            with self.subTest(gitMode=unknown):
                self.assertNotIn(unknown, allowed_modes)

    def test_migration_records_are_closed_and_deferred_to_fixed_issues(self) -> None:
        schema = self._schema("migration-record.schema.json")
        record = schema["$defs"]["record"]
        self.assertEqual(record["properties"]["status"], {"const": "deferred"})
        self.assertEqual(
            set(record["properties"]["targetIssue"]["enum"]),
            {"MW-ASSET-002", "MW-ASSET-003"},
        )
        self.assertEqual(
            set(record["properties"]["category"]["enum"]),
            {"patches", "bottle-schema"},
        )
        self.assertTrue(
            {"sourceRepository", "gitBlobOid", "gitMode"}.issubset(record["required"])
        )

    def test_quarantine_has_fixed_reasons_and_release_evidence(self) -> None:
        schema = self._schema("quarantine.schema.json")
        record = schema["$defs"]["record"]
        self.assertEqual(record["properties"]["status"], {"const": "quarantined"})
        self.assertEqual(
            set(record["properties"]["reason"]["enum"]),
            {
                "absolute-path",
                "mutable-local-installation",
                "missing-digest",
                "unresolved-external-reference",
                "unresolved-environment-path",
                "missing-license",
                "missing-provenance",
                "unsupported-schema",
                "unsupported-behavior",
            },
        )
        self.assertIn("evidenceLocators", record["required"])
        self.assertIn("releaseCondition", record["required"])

    def test_probe_and_fixture_contracts_are_non_executable_and_provenanced(self) -> None:
        expected_kinds = {
            "portable-probe.schema.json": {
                "shell",
                "registry",
                "source",
                "binary",
                "data",
                "other",
            },
            "portable-fixture.schema.json": {
                "registry",
                "source",
                "binary",
                "data",
                "other",
            },
        }
        for name, kinds in expected_kinds.items():
            schema = self._schema(name)
            properties = schema["properties"]
            with self.subTest(schema=name):
                self.assertEqual(properties["executable"], {"const": False})
                self.assertEqual(set(properties["kind"]["enum"]), kinds)
                self.assertTrue(
                    {
                        "id",
                        "kind",
                        "source",
                        "contentPath",
                        "contentSha256",
                        "mediaType",
                        "executable",
                        "referencedAssetIds",
                        "intendedOwner",
                        "license",
                        "provenance",
                    }.issubset(schema["required"])
                )
                source = schema["$defs"]["sourceIdentity"]
                self.assertEqual(
                    set(source["required"]),
                    {
                        "sourceRepository",
                        "sourceCommit",
                        "sourcePath",
                        "sourceSha256",
                        "gitBlobOid",
                        "gitMode",
                    },
                )
                self.assertEqual(properties["source"], {"$ref": "#/$defs/sourceIdentity"})
                self.assertEqual(properties["license"], {"$ref": "#/$defs/reviewStatus"})
                self.assertEqual(properties["provenance"], {"$ref": "#/$defs/reviewStatus"})
                self.assertEqual(
                    schema["$defs"]["reviewStatus"]["properties"]["status"],
                    {"const": "reviewed"},
                )
        source_pack = self._schema("macwin-source-pack.schema.json")
        self.assertEqual(
            source_pack["$defs"]["reviewStatus"]["properties"]["status"],
            {"const": "unresolved"},
        )

    def test_recipe_v2_provenance_is_additive_closed_and_all_or_none(self) -> None:
        recipe = self._schema("recipe.schema.json")
        self.assertEqual(recipe["properties"]["schemaVersion"], {"const": "2"})
        self.assertNotIn("provenance", recipe["required"])
        provenance = recipe["properties"]["provenance"]
        expected = {
            "sourceRepository",
            "sourceCommit",
            "sourcePath",
            "sourceSha256",
        }
        self.assertIs(provenance["additionalProperties"], False)
        self.assertTrue(
            expected.issubset(provenance["properties"]),
            "source provenance must be additive to the existing Recipe provenance",
        )
        self.assertTrue(
            {"source", "maintainer", "reviewedAt"}.issubset(provenance["properties"])
        )
        self.assertNotIn("required", provenance)
        self.assertEqual(
            provenance["dependentRequired"],
            {field: sorted(expected - {field}) for field in sorted(expected)},
        )

    def _schemas(self) -> dict[str, dict[str, object]]:
        return {name: self._schema(name) for name in self.SCHEMA_NAMES}

    def _schema(self, name: str) -> dict[str, object]:
        path = ROOT / "schemas" / name
        if not path.is_file():
            raise AssertionError(f"required migration schema is missing: {name}")
        return json.loads(path.read_bytes())

    @classmethod
    def _walk_schema(cls, node: object, location: str = "$"):
        if isinstance(node, dict):
            yield location, node
            for key, value in node.items():
                yield from cls._walk_schema(value, f"{location}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from cls._walk_schema(value, f"{location}/{index}")

    @classmethod
    def _assert_schema_instance_valid(
        cls,
        value: object,
        schema: dict[str, object],
        root: dict[str, object],
    ) -> None:
        reference = schema.get("$ref")
        if reference is not None:
            if not isinstance(reference, str) or not reference.startswith("#/"):
                raise AssertionError("schema oracle only accepts local references")
            target: object = root
            for component in reference[2:].split("/"):
                if not isinstance(target, dict) or component not in target:
                    raise AssertionError("schema oracle reference does not resolve")
                target = target[component]
            if not isinstance(target, dict):
                raise AssertionError("schema oracle reference target is not an object")
            cls._assert_schema_instance_valid(value, target, root)
            return

        if "const" in schema and value != schema["const"]:
            raise AssertionError("const mismatch")
        if "enum" in schema and value not in schema["enum"]:
            raise AssertionError("enum mismatch")

        declared_type = schema.get("type")
        if declared_type is not None:
            allowed = declared_type if isinstance(declared_type, list) else [declared_type]
            if not any(cls._matches_json_type(value, candidate) for candidate in allowed):
                raise AssertionError("type mismatch")

        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                raise AssertionError("string is too short")
            if len(value) > schema.get("maxLength", len(value)):
                raise AssertionError("string is too long")
            pattern = schema.get("pattern")
            if pattern is not None and re.search(pattern, value) is None:
                raise AssertionError("pattern mismatch")
        elif type(value) is int:
            if value < schema.get("minimum", value):
                raise AssertionError("integer is too small")
            if value > schema.get("maximum", value):
                raise AssertionError("integer is too large")
        elif isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise AssertionError("array is too short")
            if len(value) > schema.get("maxItems", len(value)):
                raise AssertionError("array is too long")
            if schema.get("uniqueItems"):
                rendered = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
                if len(rendered) != len(set(rendered)):
                    raise AssertionError("array items are not unique")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for item in value:
                    cls._assert_schema_instance_valid(item, item_schema, root)
        elif isinstance(value, dict):
            required = schema.get("required", [])
            if any(field not in value for field in required):
                raise AssertionError("required property is absent")
            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                raise AssertionError("properties contract is malformed")
            for key, item in value.items():
                property_schema = properties.get(key)
                if isinstance(property_schema, dict):
                    cls._assert_schema_instance_valid(item, property_schema, root)
                elif schema.get("additionalProperties") is False:
                    raise AssertionError("additional property is forbidden")
                elif isinstance(schema.get("additionalProperties"), dict):
                    cls._assert_schema_instance_valid(
                        item, schema["additionalProperties"], root
                    )
            dependent = schema.get("dependentRequired", {})
            for field, dependencies in dependent.items():
                if field in value and any(dependency not in value for dependency in dependencies):
                    raise AssertionError("dependent property is absent")

        for conditional in schema.get("allOf", []):
            condition = conditional.get("if")
            if isinstance(condition, dict) and cls._schema_matches(value, condition, root):
                consequence = conditional.get("then")
                if isinstance(consequence, dict):
                    cls._assert_schema_instance_valid(value, consequence, root)

    @classmethod
    def _schema_matches(
        cls,
        value: object,
        schema: dict[str, object],
        root: dict[str, object],
    ) -> bool:
        try:
            cls._assert_schema_instance_valid(value, schema, root)
        except AssertionError:
            return False
        return True

    @staticmethod
    def _matches_json_type(value: object, declared: object) -> bool:
        return {
            "null": value is None,
            "boolean": type(value) is bool,
            "integer": type(value) is int,
            "number": type(value) in (int, float),
            "string": type(value) is str,
            "array": type(value) is list,
            "object": type(value) is dict,
        }.get(declared, False)

    @staticmethod
    def _valid_pattern_value(location: str, pattern: str) -> str:
        if location.endswith("/relativePath"):
            return "safe/path.txt"
        if location.endswith("/objectPath"):
            return "objects/sha256/aa/" + ("a" * 62)
        if "sourceCommit" in location or location.endswith("/commit"):
            return "a" * 40
        if "Sha256" in location or location.endswith("/sha256"):
            return "a" * 64
        if location.endswith("/gitBlobOid"):
            return "a" * 40
        if location.endswith("/id"):
            return "valid-id"
        if "mediaType" in location:
            return "text/plain"
        if "intendedOwner" in location:
            return "compatforge/probes"
        if "sourceTag" in location:
            return "migration-tag"
        candidate = "valid"
        if re.fullmatch(pattern, candidate):
            return candidate
        raise AssertionError(f"missing representative value for {location}: {pattern}")

    def _complete_schema_instances(self) -> dict[str, dict[str, object]]:
        source = {
            "sourceRepository": "a1112/Mac-Win",
            "sourceCommit": "d" * 40,
            "sourcePath": "scripts/example.sh",
            "sourceSha256": "a" * 64,
            "gitBlobOid": "b" * 40,
            "gitMode": "100755",
        }
        unresolved_review = {"status": "unresolved"}
        reviewed = {"status": "reviewed"}
        asset = {
            "category": "probes",
            "sourcePath": source["sourcePath"],
            "sourceCommit": source["sourceCommit"],
            "gitBlobOid": "b" * 40,
            "sha256": source["sourceSha256"],
            "byteSize": 1,
            "gitMode": "100755",
            "kind": "probe",
            "license": unresolved_review,
            "provenance": unresolved_review,
            "intendedOwner": "compatforge/probes",
            "externalRefs": [],
            "developmentDependencies": [],
            "objectPath": "objects/sha256/aa/" + ("a" * 62),
        }
        deferred = {
            "sourceRepository": "a1112/Mac-Win",
            "sourcePath": "patches/example.patch",
            "sourceCommit": "d" * 40,
            "gitBlobOid": "b" * 40,
            "gitMode": "100644",
            "sourceSha256": "a" * 64,
            "category": "patches",
            "status": "deferred",
            "targetIssue": "MW-ASSET-002",
            "intendedOwner": "compatforge/patches",
            "license": unresolved_review,
            "provenance": unresolved_review,
        }
        quarantine = {
            "sourcePath": "scripts/example.sh",
            "sourceCommit": "d" * 40,
            "sourceSha256": "a" * 64,
            "category": "probes",
            "status": "quarantined",
            "reason": "unsupported-behavior",
            "evidenceLocators": ["reviewed evidence"],
            "intendedOwner": "compatforge/probes",
            "releaseCondition": "review source semantics",
        }
        portable = {
            "schemaVersion": "1",
            "id": "portable-example",
            "kind": "source",
            "source": source,
            "contentPath": "migration/macwin/generated/content/example.sh",
            "contentSha256": "c" * 64,
            "mediaType": "text/plain",
            "executable": False,
            "referencedAssetIds": [],
            "intendedOwner": "compatforge/probes",
            "license": reviewed,
            "provenance": reviewed,
        }
        recipe = json.loads((ROOT / "examples/recipes/7zip.json").read_bytes())
        recipe["provenance"] = {
            "sourceRepository": "a1112/Mac-Win",
            "sourceCommit": "d" * 40,
            "sourcePath": "MacWinManager/catalog/7zip.json",
            "sourceSha256": "a" * 64,
        }
        return {
            "macwin-source-pack.schema.json": {
                "schemaVersion": "1",
                "repository": "a1112/Mac-Win",
                "sourceTag": "mw-migration-baseline-db12d5e",
                "sourceTagObject": "f" * 40,
                "sourceCommit": "d" * 40,
                "inventoryCommit": "e" * 40,
                "digestAlgorithm": "sha256",
                "assetCount": 90,
                "categoryCounts": {
                    "catalog": 19,
                    "patches": 11,
                    "probes": 26,
                    "fixtures": 30,
                    "bottleSchema": 4,
                },
                "assets": [copy.deepcopy(asset) for _ in range(90)],
            },
            "migration-record.schema.json": {"schemaVersion": "1", "records": [deferred]},
            "quarantine.schema.json": {"schemaVersion": "1", "records": [quarantine]},
            "portable-probe.schema.json": portable,
            "portable-fixture.schema.json": {**copy.deepcopy(portable), "kind": "source"},
            "recipe.schema.json": recipe,
        }


class MacWinConversionModelTests(unittest.TestCase):
    EXPECTED_CATEGORY_COUNTS = {
        "bottle-schema": 4,
        "catalog": 19,
        "fixtures": 30,
        "patches": 11,
        "probes": 26,
    }
    EXPECTED_OWNERS = {
        "bottle-schema": "compatforge/bottle-schema",
        "catalog": "compatforge/catalog",
        "fixtures": "compatforge/probes",
        "patches": "compatforge/patches",
        "probes": "compatforge/probes",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.source_pack = cls.converter.load_source_pack(ROOT)
        cls.result = cls.converter.build_conversion(ROOT)

    def test_every_source_identity_has_one_closed_ordered_ledger_record(self) -> None:
        converter = self.converter
        source_pack = self.source_pack
        result = self.result
        self.assertEqual(len(source_pack.assets), 90)
        self.assertEqual(len(result.records), 90)
        self.assertEqual(result.source_pack, source_pack)

        paths = tuple(record.source_path for record in result.records)
        self.assertEqual(paths, tuple(sorted(paths, key=lambda item: item.encode("ascii"))))
        self.assertEqual(len(set(paths)), 90)
        self.assertEqual(paths, tuple(asset.source_path for asset in source_pack.assets))

        counts = {category: 0 for category in self.EXPECTED_CATEGORY_COUNTS}
        for asset, record in zip(source_pack.assets, result.records, strict=True):
            counts[asset.category] += 1
            self.assertEqual(asset.intended_owner, self.EXPECTED_OWNERS[asset.category])
            self.assertEqual(record.source_repository, source_pack.repository)
            self.assertEqual(record.source_commit, asset.source_commit)
            self.assertEqual(record.source_path, asset.source_path)
            self.assertEqual(record.source_sha256, asset.sha256)
            self.assertEqual(record.source_kind, asset.kind)
            self.assertEqual(record.category, asset.category)
            self.assertEqual(record.intended_owner, asset.intended_owner)
        self.assertEqual(counts, self.EXPECTED_CATEGORY_COUNTS)

        self.assertEqual(
            tuple(converter.ConversionRecord.__dataclass_fields__),
            (
                "source_repository",
                "source_commit",
                "source_path",
                "source_sha256",
                "source_kind",
                "category",
                "intended_owner",
                "output_kind",
                "status",
                "action",
                "target_issue",
                "reason",
                "evidence_locators",
                "release_condition",
            ),
        )

    def test_catalog_boundaries_and_all_recipe_candidates_are_classified(self) -> None:
        records = tuple(
            record for record in self.result.records if record.category == "catalog"
        )
        boundaries = {
            record.source_path.rsplit("/", 1)[-1]: record
            for record in records
            if record.output_kind == "catalog-boundary"
        }
        self.assertEqual(set(boundaries), {"catalog.index.json", "catalog.signature.json"})
        for record in boundaries.values():
            self.assertEqual(record.status, "converted")
            self.assertEqual(record.action, "retain-catalog-boundary")
            self.assertIsNone(record.reason)
            self.assertIsNone(record.target_issue)

        recipes = tuple(record for record in records if record.output_kind == "recipe")
        self.assertEqual(len(recipes), 17)
        self.assertTrue(
            all("/recipes/" in record.source_path for record in recipes), recipes
        )
        for record in recipes:
            self.assertIn(record.status, {"converted", "quarantined"})
            self.assertEqual(
                record.action,
                "convert-recipe" if record.status == "converted" else "quarantine",
            )

    def test_non_catalog_categories_use_only_the_approved_result_contracts(self) -> None:
        expected = {
            "probes": ("portable-probe", None, None),
            "fixtures": ("portable-fixture", None, None),
            "patches": ("patch-mapping", "deferred", "MW-ASSET-002"),
            "bottle-schema": (
                "bottle-schema-mapping",
                "deferred",
                "MW-ASSET-003",
            ),
        }
        for record in self.result.records:
            if record.category not in expected:
                continue
            output_kind, fixed_status, target = expected[record.category]
            self.assertEqual(record.output_kind, output_kind)
            if fixed_status is None:
                self.assertIn(record.status, {"converted", "quarantined"})
                expected_action = (
                    f"export-{output_kind}"
                    if record.status == "converted"
                    else "quarantine"
                )
                self.assertEqual(record.action, expected_action)
                self.assertIsNone(record.target_issue)
            else:
                self.assertEqual(record.status, fixed_status)
                self.assertEqual(record.target_issue, target)
                self.assertEqual(
                    record.action,
                    "defer-patch"
                    if record.category == "patches"
                    else "defer-bottle-schema",
                )
                self.assertIsNone(record.reason)

    def test_model_rejects_incomplete_duplicate_extra_and_forged_results(self) -> None:
        converter = self.converter
        result = self.result
        first = result.records[0]
        quarantined = next(record for record in result.records if record.status == "quarantined")
        mutants = {
            "missing": dataclasses.replace(result, records=result.records[:-1]),
            "extra": dataclasses.replace(result, records=(*result.records, first)),
            "duplicate": dataclasses.replace(
                result, records=(first, first, *result.records[2:])
            ),
            "unstable-order": dataclasses.replace(
                result, records=tuple(reversed(result.records))
            ),
            "wrong-category": self._replace_record(
                result, first, category="catalog"
            ),
            "wrong-action": self._replace_record(result, first, action="quarantine"),
            "unsupported-status": self._replace_record(
                result, first, status="portable"
            ),
            "unsupported-reason": self._replace_record(
                result, quarantined, reason="invented-reason"
            ),
            "wrong-commit": self._replace_record(
                result, first, source_commit="0" * 40
            ),
            "wrong-digest": self._replace_record(
                result, first, source_sha256="0" * 64
            ),
            "wrong-owner": self._replace_record(
                result, first, intended_owner="compatforge/other"
            ),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), self.assertRaises(converter.ConversionError):
                converter.render_documents(mutant)

    def test_unknown_or_ambiguous_source_facts_fail_closed(self) -> None:
        converter = self.converter
        source_pack = self.source_pack
        catalog_asset = next(
            asset
            for asset in source_pack.assets
            if asset.source_path.endswith("/catalog.index.json")
        )
        recipe_asset = next(
            asset for asset in source_pack.assets if "/recipes/" in asset.source_path
        )
        cases = (
            dataclasses.replace(catalog_asset, category="unknown"),
            dataclasses.replace(
                recipe_asset,
                source_path=(
                    "MacWinManager/Sources/MacWinManagerApp/Resources/Catalog/"
                    "recipes/nested/ambiguous.json"
                ),
            ),
            dataclasses.replace(recipe_asset, raw=b"{}"),
        )
        for asset in cases:
            assets = tuple(
                asset if existing.source_path == recipe_asset.source_path else existing
                for existing in source_pack.assets
            )
            if asset is cases[0]:
                assets = tuple(
                    asset if existing.source_path == catalog_asset.source_path else existing
                    for existing in source_pack.assets
                )
            forged = dataclasses.replace(source_pack, assets=assets)
            with self.subTest(asset=asset.source_path), self.assertRaises(
                converter.ConversionError
            ):
                converter.classify_source_pack(forged)

    def test_model_type_gates_reject_hostile_fields_without_reflection(self) -> None:
        converter = self.converter
        source_pack = self.source_pack
        source_asset = source_pack.assets[0]
        record = self.result.records[0]

        def explode(*_arguments, **_options):
            raise AssertionError("hostile class\n\x1b[31mreflected")

        hostile_type = type(
            "Hostile\n\x1b[31mName",
            (),
            {
                "__eq__": explode,
                "__hash__": explode,
                "casefold": explode,
                "encode": explode,
                "__str__": explode,
            },
        )
        hostile = hostile_type()

        source_pack_mutants = (
            dataclasses.replace(source_pack, repository=hostile),
            dataclasses.replace(source_pack, category_counts=(("catalog", True),)),
            dataclasses.replace(source_pack, assets=list(source_pack.assets)),
        )
        for mutant in source_pack_mutants:
            with self.subTest(boundary="source-pack"), self.assertRaisesRegex(
                converter.ConversionError,
                r"\Asource pack model fields are invalid\Z",
            ):
                converter.classify_source_pack(mutant)

        asset_mutants = (
            dataclasses.replace(source_asset, category=[]),
            dataclasses.replace(source_asset, sha256=[]),
            dataclasses.replace(source_asset, byte_size=True),
            dataclasses.replace(source_asset, external_refs=([],)),
            dataclasses.replace(source_asset, raw=bytearray(source_asset.raw)),
        )
        for mutant in asset_mutants:
            assets = tuple(
                mutant if existing is source_asset else existing
                for existing in source_pack.assets
            )
            forged = dataclasses.replace(source_pack, assets=assets)
            with self.subTest(boundary="source-asset"), self.assertRaisesRegex(
                converter.ConversionError,
                r"\Asource asset model fields are invalid\Z",
            ):
                converter.classify_source_pack(forged)

        hostile_path = dataclasses.replace(
            source_asset, source_path="hostile\n\x1b[31m/path"
        )
        assets = tuple(
            hostile_path if existing is source_asset else existing
            for existing in source_pack.assets
        )
        with self.assertRaisesRegex(
            converter.ConversionError,
            r"\Asource asset path is invalid\Z",
        ):
            converter.classify_source_pack(
                dataclasses.replace(source_pack, assets=assets)
            )

        record_mutants = (
            dataclasses.replace(record, source_path=[]),
            dataclasses.replace(record, source_sha256=[]),
            dataclasses.replace(record, status=[]),
            dataclasses.replace(record, target_issue=1),
            dataclasses.replace(record, evidence_locators=([],)),
        )
        for mutant in record_mutants:
            records = tuple(
                mutant if existing is record else existing
                for existing in self.result.records
            )
            forged = dataclasses.replace(self.result, records=records)
            with self.subTest(boundary="conversion-record"), self.assertRaisesRegex(
                converter.ConversionError,
                r"\Aconversion result record fields are invalid\Z",
            ):
                converter.render_documents(forged)

    def test_converter_import_is_lazy_and_preserves_bytecode_policy(self) -> None:
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = False
            with tempfile.TemporaryDirectory(
                prefix=".macwin-converter-test-", dir=ROOT
            ) as directory:
                tools = Path(directory) / "tools"
                tools.mkdir()
                copied = tools / "convert_macwin_assets.py"
                shutil.copyfile(ROOT / "tools/convert_macwin_assets.py", copied)
                spec = importlib.util.spec_from_file_location(
                    "isolated_macwin_converter", copied
                )
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                try:
                    try:
                        spec.loader.exec_module(module)
                    except Exception as error:
                        self.fail(
                            "converter import attempted sibling bootstrap: "
                            f"{type(error).__name__}"
                        )
                finally:
                    sys.modules.pop(spec.name, None)
                self.assertFalse(sys.dont_write_bytecode)
                with self.assertRaisesRegex(
                    module.ConversionError,
                    r"\Amigration dependencies are unavailable\Z",
                ):
                    module.load_source_pack(Path(directory))
        finally:
            sys.dont_write_bytecode = previous

    def test_converter_cli_stabilizes_every_sibling_bootstrap_failure(self) -> None:
        converter_source = ROOT / "tools/convert_macwin_assets.py"
        common_source = ROOT / "tools/macwin_asset_common.py"
        importer_source = ROOT / "tools/import_macwin_source_pack.py"
        expected_error = "Mac-Win asset conversion failed.\n"
        scenarios = (
            "missing-common",
            "missing-importer",
            "corrupt-common",
            "corrupt-importer",
            "exiting-common",
            "linked-common",
            "linked-importer",
            "unreadable-common",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=".macwin-converter-test-", dir=ROOT
            ) as directory:
                root = Path(directory)
                tools = root / "tools"
                tools.mkdir()
                converter = tools / converter_source.name
                shutil.copyfile(converter_source, converter)
                common = tools / common_source.name
                importer = tools / importer_source.name
                if scenario != "missing-common":
                    shutil.copyfile(common_source, common)
                if scenario != "missing-importer":
                    shutil.copyfile(importer_source, importer)
                if scenario == "corrupt-common":
                    common.write_bytes(b"\xffhostile\n\x1b[31m")
                elif scenario == "corrupt-importer":
                    importer.write_bytes(b"\xffhostile\n\x1b[31m")
                elif scenario == "exiting-common":
                    common.write_text(
                        "raise SystemExit('hostile\\n\\x1b[31m')\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                elif scenario == "linked-common":
                    common.unlink()
                    outside = root / "outside-common.py"
                    shutil.copyfile(common_source, outside)
                    os.symlink(outside, common)
                elif scenario == "linked-importer":
                    importer.unlink()
                    outside = root / "outside-importer.py"
                    shutil.copyfile(importer_source, outside)
                    os.symlink(outside, importer)

                command = [sys.executable, "-B", str(converter), "--check"]
                if scenario == "unreadable-common":
                    denial_probe = (
                        "import os,runpy,sys\n"
                        "original_open=os.open\n"
                        "def denied(path,*args,**kwargs):\n"
                        " if str(path).endswith('macwin_asset_common.py'):\n"
                        "  raise PermissionError('hostile\\n\\x1b[31m')\n"
                        " return original_open(path,*args,**kwargs)\n"
                        "os.open=denied\n"
                        "target=sys.argv[1]\n"
                        "sys.argv=[target,'--check']\n"
                        "runpy.run_path(target,run_name='__main__')\n"
                    )
                    command = [
                        sys.executable,
                        "-B",
                        "-c",
                        denial_probe,
                        str(converter),
                    ]
                completed = subprocess.run(
                    command,
                    cwd=root,
                    check=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
                )
                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, expected_error)

    def test_private_bootstrap_publishes_one_pair_under_sixteen_threads(self) -> None:
        converter = _load_macwin_asset_converter()
        thread_count = 16
        ready = threading.Barrier(thread_count)
        loader_entered = threading.Event()
        release_loader = threading.Event()
        count_lock = threading.Lock()
        counts: dict[str, int] = {}
        original = converter._load_trusted_tool

        def observed_load(name):
            with count_lock:
                counts[name] = counts.get(name, 0) + 1
            loader_entered.set()
            if not release_loader.wait(timeout=5):
                raise AssertionError("bootstrap loader release timed out")
            return original(name)

        def worker():
            ready.wait(timeout=5)
            try:
                converter._bootstrap_dependencies()
            except BaseException as error:
                return ("error", type(error).__name__, str(error))
            return ("success", converter._COMMON, converter._SOURCE_PACK)

        with mock.patch.object(
            converter, "_load_trusted_tool", side_effect=observed_load
        ), concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_count
        ) as executor:
            futures = [executor.submit(worker) for _index in range(thread_count)]
            self.assertTrue(loader_entered.wait(timeout=5))
            time.sleep(0.1)
            release_loader.set()
            results = [future.result(timeout=30) for future in futures]

        self.assertTrue(all(result[0] == "success" for result in results), results)
        self.assertEqual(
            counts,
            {
                "macwin_asset_common.py": 1,
                "import_macwin_source_pack.py": 1,
            },
        )
        published = results[0][1:]
        self.assertTrue(
            all(
                result[1] is published[0] and result[2] is published[1]
                for result in results
            )
        )

    def test_public_build_conversion_shares_bootstrap_under_eight_threads(self) -> None:
        converter = _load_macwin_asset_converter()
        thread_count = 8
        ready = threading.Barrier(thread_count)
        loader_entered = threading.Event()
        release_loader = threading.Event()
        count_lock = threading.Lock()
        counts: dict[str, int] = {}
        original = converter._load_trusted_tool

        def observed_load(name):
            with count_lock:
                counts[name] = counts.get(name, 0) + 1
            loader_entered.set()
            if not release_loader.wait(timeout=5):
                raise AssertionError("bootstrap loader release timed out")
            return original(name)

        def worker():
            ready.wait(timeout=5)
            try:
                result = converter.build_conversion(ROOT)
                rendered = converter.render_documents(result)
            except BaseException as error:
                return ("error", type(error).__name__, str(error))
            return (
                "success",
                converter._COMMON,
                converter._SOURCE_PACK,
                tuple(sorted(rendered.items())),
            )

        with mock.patch.object(
            converter, "_load_trusted_tool", side_effect=observed_load
        ), concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_count
        ) as executor:
            futures = [executor.submit(worker) for _index in range(thread_count)]
            self.assertTrue(loader_entered.wait(timeout=5))
            time.sleep(0.1)
            release_loader.set()
            results = [future.result(timeout=30) for future in futures]

        self.assertTrue(all(result[0] == "success" for result in results), results)
        self.assertEqual(
            counts,
            {
                "macwin_asset_common.py": 1,
                "import_macwin_source_pack.py": 1,
            },
        )
        published = results[0][1:3]
        expected_document = results[0][3]
        self.assertTrue(
            all(
                result[1] is published[0]
                and result[2] is published[1]
                and result[3] == expected_document
                for result in results
            )
        )

    def test_failed_concurrent_bootstrap_is_atomic_retryable_and_deadlock_free(self) -> None:
        converter = _load_macwin_asset_converter()
        thread_count = 8
        ready = threading.Barrier(thread_count)
        count_lock = threading.Lock()
        counts: dict[str, int] = {}
        failed_state = None
        original = converter._load_trusted_tool

        def fail_first_importer(name):
            nonlocal failed_state
            with count_lock:
                counts[name] = counts.get(name, 0) + 1
                should_fail = (
                    name == "import_macwin_source_pack.py"
                    and counts[name] == 1
                )
                if should_fail:
                    failed_state = (converter._COMMON, converter._SOURCE_PACK)
            if should_fail:
                raise RuntimeError("hostile\n\x1b[31m bootstrap failure")
            return original(name)

        def worker():
            ready.wait(timeout=5)
            try:
                converter._bootstrap_dependencies()
            except converter.ConversionError as error:
                return ("failure", str(error))
            except BaseException as error:
                return ("error", type(error).__name__, str(error))
            return ("success", converter._COMMON, converter._SOURCE_PACK)

        with mock.patch.object(
            converter, "_load_trusted_tool", side_effect=fail_first_importer
        ), concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_count
        ) as executor:
            futures = [executor.submit(worker) for _index in range(thread_count)]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual(failed_state, (None, None))
        self.assertEqual(
            [result for result in results if result[0] == "failure"],
            [("failure", "migration dependencies are unavailable")],
        )
        successes = [result for result in results if result[0] == "success"]
        self.assertEqual(len(successes), thread_count - 1, results)
        self.assertEqual(
            counts,
            {
                "macwin_asset_common.py": 2,
                "import_macwin_source_pack.py": 2,
            },
        )
        published = successes[0][1:]
        self.assertTrue(
            all(
                result[1] is published[0] and result[2] is published[1]
                for result in successes
            )
        )
        with mock.patch.object(
            converter,
            "_load_trusted_tool",
            side_effect=AssertionError("valid dependency pair was reloaded"),
        ):
            converter._bootstrap_dependencies()
        self.assertIs(converter._COMMON, published[0])
        self.assertIs(converter._SOURCE_PACK, published[1])

    def test_two_converter_instances_bootstrap_without_sys_modules_collision(self) -> None:
        converter_path = ROOT / "tools/convert_macwin_assets.py"

        def load_instance(name):
            spec = importlib.util.spec_from_file_location(name, converter_path)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(name, None)
            return module

        converters = (
            load_instance("macwin_converter_instance_alpha"),
            load_instance("macwin_converter_instance_beta"),
        )
        thread_count = 16
        ready = threading.Barrier(thread_count)
        exec_barriers = {
            "macwin_asset_common.py": threading.Barrier(2),
            "import_macwin_source_pack.py": threading.Barrier(2),
        }
        counts = [{}, {}]
        count_locks = [threading.Lock(), threading.Lock()]
        original_loaders = tuple(
            converter._load_trusted_tool for converter in converters
        )
        original_exec = exec
        baseline_temporary_keys = {
            key for key in sys.modules if key.startswith("_compatforge_")
        }

        def synchronized_exec(code, globals_value, locals_value=None):
            filename = (
                Path(code.co_filename).name
                if hasattr(code, "co_filename")
                else None
            )
            barrier = exec_barriers.get(filename)
            if barrier is not None:
                barrier.wait(timeout=5)
            if locals_value is None:
                return original_exec(code, globals_value)
            return original_exec(code, globals_value, locals_value)

        wrappers = []
        for index, original in enumerate(original_loaders):
            def observed_load(name, *, _index=index, _original=original):
                with count_locks[_index]:
                    current = counts[_index]
                    current[name] = current.get(name, 0) + 1
                return _original(name)

            wrappers.append(observed_load)

        def worker(index):
            converter = converters[index]
            ready.wait(timeout=5)
            try:
                result = converter.build_conversion(ROOT)
                documents = converter.render_documents(result)
            except BaseException as error:
                return ("error", type(error).__name__, str(error))
            return (
                "success",
                converter._COMMON,
                converter._SOURCE_PACK,
                tuple(
                    (path, hashlib.sha256(raw).hexdigest())
                    for path, raw in sorted(documents.items())
                ),
            )

        with mock.patch("builtins.exec", side_effect=synchronized_exec), mock.patch.object(
            converters[0], "_load_trusted_tool", side_effect=wrappers[0]
        ), mock.patch.object(
            converters[1], "_load_trusted_tool", side_effect=wrappers[1]
        ), concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_count
        ) as executor:
            futures = [executor.submit(worker, index % 2) for index in range(thread_count)]
            results = [future.result(timeout=30) for future in futures]

        self.assertTrue(all(result[0] == "success" for result in results), results)
        for count in counts:
            self.assertEqual(
                count,
                {
                    "macwin_asset_common.py": 1,
                    "import_macwin_source_pack.py": 1,
                },
            )
        for instance_index, converter in enumerate(converters):
            instance_results = results[instance_index::2]
            self.assertTrue(
                all(
                    result[1] is converter._COMMON
                    and result[2] is converter._SOURCE_PACK
                    and result[3] == instance_results[0][3]
                    for result in instance_results
                )
            )
        self.assertIsNot(converters[0]._COMMON, converters[1]._COMMON)
        self.assertIsNot(converters[0]._SOURCE_PACK, converters[1]._SOURCE_PACK)
        self.assertEqual(results[0][3], results[1][3])
        self.assertEqual(
            {key for key in sys.modules if key.startswith("_compatforge_")},
            baseline_temporary_keys,
        )

    def test_converter_instance_bootstrap_failure_is_isolated_and_retryable(self) -> None:
        first = _load_macwin_asset_converter()
        second_path = ROOT / "tools/convert_macwin_assets.py"
        spec = importlib.util.spec_from_file_location(
            "macwin_converter_failure_isolation", second_path
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        second = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = second
        try:
            spec.loader.exec_module(second)
        finally:
            sys.modules.pop(spec.name, None)

        ready = threading.Barrier(2)
        original_first = first._load_trusted_tool
        first_importer_attempts = 0

        def corrupt_first(name):
            nonlocal first_importer_attempts
            if name == "import_macwin_source_pack.py":
                first_importer_attempts += 1
                if first_importer_attempts == 1:
                    raise RuntimeError("corrupt isolated sibling")
            return original_first(name)

        def run_first():
            ready.wait(timeout=5)
            try:
                first._bootstrap_dependencies()
            except first.ConversionError as error:
                return ("failure", str(error), first._COMMON, first._SOURCE_PACK)
            return ("success", first._COMMON, first._SOURCE_PACK)

        def run_second():
            ready.wait(timeout=5)
            try:
                result = second.build_conversion(ROOT)
            except BaseException as error:
                return ("error", type(error).__name__, str(error))
            return ("success", second._COMMON, second._SOURCE_PACK, len(result.records))

        with mock.patch.object(
            first, "_load_trusted_tool", side_effect=corrupt_first
        ), concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(run_first)
            second_future = executor.submit(run_second)
            first_result = first_future.result(timeout=30)
            second_result = second_future.result(timeout=30)

        self.assertEqual(
            first_result,
            ("failure", "migration dependencies are unavailable", None, None),
        )
        self.assertEqual(second_result[0], "success", second_result)
        self.assertEqual(second_result[3], 90)
        first._bootstrap_dependencies()
        self.assertIsNotNone(first._COMMON)
        self.assertIsNotNone(first._SOURCE_PACK)
        self.assertIsNot(first._COMMON, second._COMMON)
        self.assertIsNot(first._SOURCE_PACK, second._SOURCE_PACK)

    def test_each_source_leaf_is_read_once_by_the_bounded_bottom_primitive(self) -> None:
        converter = self.converter
        source_root = (ROOT / "migration/macwin/source").absolute()
        counts: dict[str, int] = {}
        limits: dict[str, set[int]] = {}
        original = converter._read_and_hold_regular_file

        def observe(path, maximum, **options):
            relative = path.absolute().relative_to(source_root).as_posix()
            counts[relative] = counts.get(relative, 0) + 1
            limits.setdefault(relative, set()).add(maximum)
            return original(path, maximum, **options)

        with mock.patch.object(
            converter, "_read_and_hold_regular_file", side_effect=observe
        ):
            loaded = converter.load_source_pack(ROOT)
        self.assertEqual(len(loaded.assets), 90)
        expected_objects = {asset.object_path for asset in loaded.assets}
        self.assertEqual(set(counts), {"index.json", *expected_objects})
        self.assertEqual(
            (
                counts["index.json"],
                sum(counts[path] for path in expected_objects),
            ),
            (1, 90),
            counts,
        )
        self.assertTrue(
            all(counts[path] == 1 for path in expected_objects), counts
        )
        self.assertEqual(sum(counts.values()), 91)
        self.assertEqual(
            limits["index.json"], {converter._SOURCE_PACK.MAX_SOURCE_INDEX_BYTES}
        )
        self.assertTrue(
            all(
                limits[path] == {converter._SOURCE_PACK.MAX_SOURCE_OBJECT_BYTES}
                for path in expected_objects
            ),
            limits,
        )

    def test_classification_and_rendering_reuse_authenticated_memory_bytes(self) -> None:
        converter = self.converter
        with mock.patch.object(
            converter,
            "_read_and_hold_regular_file",
            side_effect=AssertionError("authenticated source bytes were reread"),
        ):
            result = converter.classify_source_pack(self.source_pack)
            documents = converter.render_documents(result)
        self.assertEqual(
            set(documents),
            {
                "migration/macwin/generated/catalog.json",
                "migration/macwin/generated/quarantine.json",
                "migration/macwin/generated/mappings/patches.json",
                "migration/macwin/generated/mappings/bottle-schemas.json",
                "migration/macwin/generated/index.json",
            },
        )

    def test_single_pass_loader_rejects_post_read_mutation_without_rereading(self) -> None:
        converter = self.converter
        source_asset = self.source_pack.assets[0]
        with tempfile.TemporaryDirectory(
            prefix=".macwin-converter-test-", dir=ROOT
        ) as directory:
            repository_root = Path(directory)
            source_root = repository_root / "migration/macwin/source"
            source_root.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "migration/macwin/source", source_root)
            target = source_root / PurePosixPath(source_asset.object_path)
            original_load = converter._load_authenticated_asset
            original_read = converter._read_and_hold_regular_file
            target_reads = 0
            mutation_attempted = False
            mutation_blocked = False

            def observe_read(path, maximum, **options):
                nonlocal target_reads
                if path.absolute() == target.absolute():
                    target_reads += 1
                return original_read(path, maximum, **options)

            def mutate_after_read(root, record, expected_identity):
                nonlocal mutation_attempted, mutation_blocked
                leaf = original_load(root, record, expected_identity)
                if record["objectPath"] == source_asset.object_path:
                    mutation_attempted = True
                    try:
                        target.write_bytes(leaf.raw + b"post-read-mutation")
                    except OSError:
                        mutation_blocked = True
                return leaf

            rejected = False
            with mock.patch.object(
                converter,
                "_read_and_hold_regular_file",
                side_effect=observe_read,
            ), mock.patch.object(
                converter,
                "_load_authenticated_asset",
                side_effect=mutate_after_read,
            ):
                try:
                    converter.load_source_pack(repository_root)
                except converter.ConversionError:
                    rejected = True
        self.assertTrue(mutation_attempted)
        self.assertTrue(mutation_blocked or rejected)
        self.assertEqual(target_reads, 1)

    def test_authentication_window_blocks_or_rejects_restored_mtime_rewrites(self) -> None:
        converter = self.converter
        source_asset = self.source_pack.assets[0]
        cases = (
            ("index", PurePosixPath("index.json")),
            ("object", PurePosixPath(source_asset.object_path)),
        )
        for name, relative in cases:
            with self.subTest(leaf=name), tempfile.TemporaryDirectory(
                prefix=".macwin-converter-test-", dir=ROOT
            ) as directory:
                repository_root = Path(directory)
                source_root = repository_root / "migration/macwin/source"
                source_root.parent.mkdir(parents=True)
                shutil.copytree(ROOT / "migration/macwin/source", source_root)
                target = source_root / relative
                original = target.read_bytes()
                original_metadata = target.stat()
                original_bind = converter._bind_source_tree
                original_read = converter._read_and_hold_regular_file
                bind_calls = 0
                target_reads = 0
                mutation_attempted = False
                mutation_blocked = False

                def observe_read(path, maximum, **options):
                    nonlocal target_reads
                    if path.absolute() == target.absolute():
                        target_reads += 1
                    return original_read(path, maximum, **options)

                def mutate_before_final_bind(root, expected_paths):
                    nonlocal bind_calls, mutation_attempted, mutation_blocked
                    bind_calls += 1
                    if bind_calls == 2:
                        mutation_attempted = True
                        mutated = bytes([original[0] ^ 1]) + original[1:]
                        try:
                            with target.open("r+b") as stream:
                                stream.write(mutated)
                                stream.flush()
                                os.fsync(stream.fileno())
                            os.utime(
                                target,
                                ns=(
                                    original_metadata.st_atime_ns,
                                    original_metadata.st_mtime_ns,
                                ),
                            )
                        except OSError:
                            mutation_blocked = True
                    return original_bind(root, expected_paths)

                rejected = False
                with mock.patch.object(
                    converter,
                    "_read_and_hold_regular_file",
                    side_effect=observe_read,
                ), mock.patch.object(
                    converter,
                    "_bind_source_tree",
                    side_effect=mutate_before_final_bind,
                ):
                    try:
                        converter.load_source_pack(repository_root)
                    except converter.ConversionError:
                        rejected = True

                self.assertTrue(mutation_attempted)
                self.assertTrue(
                    mutation_blocked or rejected,
                    "same-size rewrite with restored mtime was silently accepted",
                )
                if os.name == "nt":
                    self.assertTrue(mutation_blocked)
                self.assertEqual(target_reads, 1)

    def test_authentication_window_blocks_or_rejects_leaf_replacement(self) -> None:
        converter = self.converter
        source_asset = self.source_pack.assets[0]
        with tempfile.TemporaryDirectory(
            prefix=".macwin-converter-test-", dir=ROOT
        ) as directory:
            repository_root = Path(directory)
            source_root = repository_root / "migration/macwin/source"
            source_root.parent.mkdir(parents=True)
            shutil.copytree(ROOT / "migration/macwin/source", source_root)
            target = source_root / PurePosixPath(source_asset.object_path)
            replacement = repository_root / "replacement-object"
            shutil.copyfile(target, replacement)
            original_bind = converter._bind_source_tree
            original_read = converter._read_and_hold_regular_file
            bind_calls = 0
            target_reads = 0
            replacement_attempted = False
            replacement_blocked = False

            def observe_read(path, maximum, **options):
                nonlocal target_reads
                if path.absolute() == target.absolute():
                    target_reads += 1
                return original_read(path, maximum, **options)

            def replace_before_final_bind(root, expected_paths):
                nonlocal bind_calls, replacement_attempted, replacement_blocked
                bind_calls += 1
                if bind_calls == 2:
                    replacement_attempted = True
                    try:
                        os.replace(replacement, target)
                    except OSError:
                        replacement_blocked = True
                return original_bind(root, expected_paths)

            rejected = False
            with mock.patch.object(
                converter,
                "_read_and_hold_regular_file",
                side_effect=observe_read,
            ), mock.patch.object(
                converter,
                "_bind_source_tree",
                side_effect=replace_before_final_bind,
            ):
                try:
                    converter.load_source_pack(repository_root)
                except converter.ConversionError:
                    rejected = True

            self.assertTrue(replacement_attempted)
            self.assertTrue(replacement_blocked or rejected)
            if os.name == "nt":
                self.assertTrue(replacement_blocked)
            self.assertEqual(target_reads, 1)

    def test_held_source_handles_close_after_success_and_failure(self) -> None:
        converter = self.converter
        source_asset = self.source_pack.assets[0]
        for outcome in ("success", "failure"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory(
                prefix=".macwin-converter-test-", dir=ROOT
            ) as directory:
                repository_root = Path(directory)
                source_root = repository_root / "migration/macwin/source"
                source_root.parent.mkdir(parents=True)
                shutil.copytree(ROOT / "migration/macwin/source", source_root)
                target = source_root / PurePosixPath(source_asset.object_path)
                original = converter._read_and_hold_regular_file
                calls = 0

                def fail_after_one_object(path, maximum, **options):
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        raise converter.ConversionError("injected load failure")
                    return original(path, maximum, **options)

                if outcome == "success":
                    converter.load_source_pack(repository_root)
                else:
                    with mock.patch.object(
                        converter,
                        "_read_and_hold_regular_file",
                        side_effect=fail_after_one_object,
                    ), self.assertRaises(converter.ConversionError):
                        converter.load_source_pack(repository_root)

                with target.open("r+b"):
                    pass
                moved = repository_root / "released-source-object"
                os.replace(target, moved)
                os.replace(moved, target)

    def test_conversion_is_byte_deterministic_and_has_no_locator_side_effects(self) -> None:
        converter = self.converter
        first = converter.render_documents(self.result)
        with mock.patch.object(
            Path, "exists", side_effect=AssertionError("locator existence probed")
        ), mock.patch.object(
            Path, "is_file", side_effect=AssertionError("locator file type probed")
        ), mock.patch.object(
            Path, "is_dir", side_effect=AssertionError("locator directory probed")
        ), mock.patch.object(
            subprocess, "run", side_effect=AssertionError("subprocess invoked")
        ), mock.patch.object(
            os, "getenv", side_effect=AssertionError("environment inspected")
        ), mock.patch.object(
            os.path, "expanduser", side_effect=AssertionError("home expanded")
        ):
            repeated = converter.build_conversion(ROOT)
            second = converter.render_documents(repeated)
        self.assertEqual(second, first)
        self.assertEqual(
            set(first),
            {
                "migration/macwin/generated/catalog.json",
                "migration/macwin/generated/quarantine.json",
                "migration/macwin/generated/mappings/patches.json",
                "migration/macwin/generated/mappings/bottle-schemas.json",
                "migration/macwin/generated/index.json",
            },
        )
        common = _load_macwin_asset_common()
        for path, raw in first.items():
            document = common.parse_json_bytes(raw, label=path)
            self.assertEqual(common.canonical_json_bytes(document), raw)

    @staticmethod
    def _replace_record(result, record, **changes):
        replacement = dataclasses.replace(record, **changes)
        records = tuple(
            replacement if existing is record else existing for existing in result.records
        )
        return dataclasses.replace(result, records=records)


class MacWinPortableAssetTests(unittest.TestCase):
    EXPECTED_COUNTS = {
        "probes": 26,
        "fixtures": 30,
        "patches": 11,
        "bottle-schema": 4,
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.common = _load_macwin_asset_common()
        cls.result = cls.converter.build_conversion(ROOT)
        cls.assets = {
            asset.source_path: asset for asset in cls.result.source_pack.assets
        }

    def test_real_probe_and_fixture_decisions_are_complete_and_exact(self) -> None:
        documents = self.converter.render_documents(self.result)
        quarantine = self.common.parse_json_bytes(
            documents["migration/macwin/generated/quarantine.json"],
            label="generated quarantine",
        )
        records = {
            record["sourcePath"]: record for record in quarantine["records"]
        }
        for category in ("probes", "fixtures"):
            source_paths = {
                asset.source_path
                for asset in self.result.source_pack.assets
                if asset.category == category
            }
            portable_paths = {
                record.source_path
                for record in self.result.records
                if record.category == category and record.status == "converted"
            }
            quarantined_paths = {
                path for path in source_paths if path in records
            }
            self.assertEqual(len(source_paths), self.EXPECTED_COUNTS[category])
            self.assertEqual(portable_paths | quarantined_paths, source_paths)
            self.assertFalse(portable_paths & quarantined_paths)
            self.assertEqual(len(portable_paths), 0)
            self.assertEqual(len(quarantined_paths), len(source_paths))
            for path in sorted(source_paths):
                self.assertEqual(records[path]["reason"], "missing-license")
                self.assertEqual(records[path]["sourceSha256"], self.assets[path].sha256)
                self.assertEqual(records[path]["sourceCommit"], self.assets[path].source_commit)
                self.assertEqual(records[path]["intendedOwner"], self.assets[path].intended_owner)
                expected_evidence = sorted(
                    {
                        f"{path}#license",
                        f"{path}#provenance",
                        *self.assets[path].external_refs,
                        *self.assets[path].development_dependencies,
                    },
                    key=lambda value: value.encode("utf-8"),
                )
                self.assertEqual(records[path]["evidenceLocators"], expected_evidence)

    def test_deferred_patch_and_bottle_mappings_are_closed_and_exact(self) -> None:
        documents = self.converter.render_documents(self.result)
        cases = (
            ("patches", "MW-ASSET-002", "patches.json"),
            ("bottle-schema", "MW-ASSET-003", "bottle-schemas.json"),
        )
        schema = json.loads(
            (ROOT / "schemas/migration-record.schema.json").read_bytes()
        )
        forbidden = {"apply", "runtime", "convert", "write", "executable", "contentPath"}
        for category, target, name in cases:
            relative = f"migration/macwin/generated/mappings/{name}"
            value = self.common.parse_json_bytes(documents[relative], label=relative)
            self.assertEqual(self.common.canonical_json_bytes(value), documents[relative])
            MigrationSchemaTests._assert_schema_instance_valid(value, schema, schema)
            source = [
                asset
                for asset in self.result.source_pack.assets
                if asset.category == category
            ]
            self.assertEqual(len(value["records"]), self.EXPECTED_COUNTS[category])
            self.assertEqual(
                [record["sourcePath"] for record in value["records"]],
                [asset.source_path for asset in source],
            )
            for record, asset in zip(value["records"], source, strict=True):
                self.assertEqual(set(record) & forbidden, set())
                self.assertEqual(record["status"], "deferred")
                self.assertEqual(record["targetIssue"], target)
                self.assertEqual(record["sourceCommit"], asset.source_commit)
                self.assertEqual(record["sourceSha256"], asset.sha256)
                self.assertEqual(record["sourceRepository"], self.result.source_pack.repository)
                self.assertEqual(record["gitBlobOid"], asset.git_blob_oid)
                self.assertEqual(record["gitMode"], asset.git_mode)
                self.assertEqual(record["intendedOwner"], asset.intended_owner)
                self.assertEqual(record["license"], {"status": asset.license_status})
                self.assertEqual(record["provenance"], {"status": asset.provenance_status})

    def test_portable_renderer_is_explicit_non_executable_and_content_addressed(self) -> None:
        asset = next(
            asset for asset in self.result.source_pack.assets if asset.category == "probes"
        )
        reviewed_asset = dataclasses.replace(
            asset, license_status="reviewed", provenance_status="reviewed"
        )
        record = next(
            record for record in self.result.records if record.source_path == asset.source_path
        )
        converted_record = dataclasses.replace(
            record,
            status="converted",
            action="export-portable-probe",
            reason=None,
            evidence_locators=(),
            release_condition=None,
        )
        with self.assertRaisesRegex(
            self.converter.ConversionError, "portable asset evidence is incomplete"
        ):
            self.converter._portable_document(asset, converted_record)
        portable = self.converter._portable_document(reviewed_asset, converted_record)
        self.assertFalse(portable["executable"])
        self.assertEqual(portable["source"]["sourceSha256"], asset.sha256)
        self.assertEqual(portable["source"]["gitBlobOid"], asset.git_blob_oid)
        self.assertEqual(portable["source"]["gitMode"], asset.git_mode)
        self.assertEqual(portable["contentSha256"], asset.sha256)
        self.assertTrue(portable["contentPath"].startswith("migration/macwin/generated/probes/content/sha256/"))
        self.assertEqual(portable["referencedAssetIds"], [])
        self.assertEqual(portable["license"], {"status": "reviewed"})
        self.assertEqual(portable["provenance"], {"status": "reviewed"})
        self.assertEqual(asset.git_mode, "100755")
        schema = json.loads(
            (ROOT / "schemas/portable-probe.schema.json").read_bytes()
        )
        MigrationSchemaTests._assert_schema_instance_valid(portable, schema, schema)

    def test_rendering_never_executes_or_imports_asset_bytes(self) -> None:
        with mock.patch.object(
            subprocess, "run", side_effect=AssertionError("asset executed")
        ), mock.patch.object(
            subprocess, "Popen", side_effect=AssertionError("asset executed")
        ), mock.patch.object(
            importlib.util, "spec_from_file_location", side_effect=AssertionError("asset imported")
        ), mock.patch.object(
            os, "system", side_effect=AssertionError("asset executed")
        ):
            documents = self.converter.render_documents(self.result)
        self.assertIn("migration/macwin/generated/mappings/patches.json", documents)
        self.assertIn("migration/macwin/generated/mappings/bottle-schemas.json", documents)

    def test_real_source_failures_precede_portable_output_rendering(self) -> None:
        asset = self.assets["scripts/analyze-window-image.py"]
        for case in ("mutated", "missing"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=".macwin-task6-source-", dir=ROOT
            ) as directory:
                temporary_root = Path(directory)
                source = temporary_root / "migration/macwin/source"
                shutil.copytree(ROOT / "migration/macwin/source", source)
                object_path = source / PurePosixPath(asset.object_path)
                if case == "mutated":
                    object_path.write_bytes(asset.raw + b"x")
                else:
                    object_path.unlink()
                with mock.patch.object(
                    self.converter,
                    "_portable_document",
                    wraps=self.converter._portable_document,
                ) as render_spy, self.assertRaises(self.converter.ConversionError):
                    self.converter.build_conversion(temporary_root)
                render_spy.assert_not_called()

    def test_real_linked_source_rejects_before_portable_output_rendering(self) -> None:
        asset = self.assets["scripts/analyze-window-image.py"]
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task6-source-link-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            source = temporary_root / "migration/macwin/source"
            shutil.copytree(ROOT / "migration/macwin/source", source)
            object_path = source / PurePosixPath(asset.object_path)
            outside = temporary_root / "outside-object"
            outside.write_bytes(asset.raw)
            object_path.unlink()
            try:
                object_path.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"file symlink unavailable: {error}")
            with mock.patch.object(
                self.converter,
                "_portable_document",
                wraps=self.converter._portable_document,
            ) as render_spy, self.assertRaises(self.converter.ConversionError):
                self.converter.build_conversion(temporary_root)
            render_spy.assert_not_called()

    def test_repository_oracle_closes_task6_leaves_and_scans_extra_evidence(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task6-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            MacWinRecipeConversionTests._copy_validator_fixture(temporary_root)
            validator.ROOT = temporary_root
            self.assertEqual(validator.validate_no_developer_paths(), [])

            mapping = temporary_root / "migration/macwin/generated/mappings/patches.json"
            original = mapping.read_bytes()
            mapping.write_bytes(original[:-2] + b" \n")
            self.assertIn(
                "Mac-Win generated evidence validation failed",
                validator.validate_no_developer_paths(),
            )
            mapping.write_bytes(original)

            extra = temporary_root / "migration/macwin/generated/probes/extra.json"
            extra.parent.mkdir()
            extra.write_bytes(b'{"path":"/Users/' + b'a1-6/unsafe"}\n')
            errors = validator.validate_no_developer_paths()
            self.assertTrue(
                any("contains developer path" in error for error in errors), errors
            )

    def test_repository_oracle_rejects_self_consistent_forged_task6_mapping(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task6-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            MacWinRecipeConversionTests._copy_validator_fixture(temporary_root)
            mapping_path = temporary_root / "migration/macwin/generated/mappings/patches.json"
            mapping = self.common.parse_json_bytes(
                mapping_path.read_bytes(), label="patch mapping"
            )
            mapping["records"][0]["targetIssue"] = "MW-ASSET-003"
            forged = self.common.canonical_json_bytes(mapping)
            mapping_path.write_bytes(forged)

            real_loader = validator._load_task5_converter
            real_converter, path, raw, identity = real_loader()

            class ForgedConverter:
                @staticmethod
                def build_conversion(root):
                    return real_converter.build_conversion(root)

                @staticmethod
                def render_documents(result):
                    documents = real_converter.render_documents(result)
                    documents["migration/macwin/generated/mappings/patches.json"] = forged
                    return documents

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator,
                "_load_task5_converter",
                return_value=(ForgedConverter(), path, raw, identity),
            ):
                self.assertIn(
                    "Mac-Win generated evidence validation failed",
                    validator.validate_no_developer_paths(),
                )

    def test_repository_oracle_requires_the_exact_committed_task7_tree(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        fixed = (
            "catalog.json",
            "index.json",
            "quarantine.json",
            "mappings/patches.json",
            "mappings/bottle-schemas.json",
        )
        cases = ("safe-extra-file", "extra-empty-directory", *fixed)
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=".macwin-task6-validator-", dir=ROOT
            ) as directory:
                temporary_root = Path(directory)
                MacWinRecipeConversionTests._copy_validator_fixture(temporary_root)
                generated = temporary_root / "migration/macwin/generated"
                if case == "safe-extra-file":
                    (generated / "future.json").write_bytes(b'{"future":"safe"}\n')
                elif case == "extra-empty-directory":
                    (generated / "future").mkdir()
                else:
                    (generated / PurePosixPath(case)).unlink()
                validator.ROOT = temporary_root
                self.assertIn(
                    "Mac-Win generated evidence validation failed",
                    validator.validate_no_developer_paths(),
                )

    def test_task6_suboracle_remains_an_exact_reusable_four_leaf_oracle(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task6-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            MacWinRecipeConversionTests._copy_validator_fixture(temporary_root)
            validator.ROOT = temporary_root
            source_binding, errors = validator._validated_macwin_source_pack_binding()
            self.assertEqual(errors, [])
            self.assertIsNotNone(source_binding)
            full = self.converter.render_documents(
                self.converter.build_conversion(temporary_root)
            )
            task6 = {
                path: full[path]
                for path in validator.TASK6_EVIDENCE_PATHS
            }
            validator._independent_task6_oracle(source_binding, task6)
            with self.assertRaises(ValueError):
                validator._independent_task6_oracle(source_binding, full)

    def test_repository_oracle_rejects_an_extra_generated_link(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task6-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            MacWinRecipeConversionTests._copy_validator_fixture(temporary_root)
            generated = temporary_root / "migration/macwin/generated"
            target = temporary_root / "safe-target.json"
            target.write_bytes(b'{"safe":true}\n')
            try:
                (generated / "future.json").symlink_to(target)
            except OSError as error:
                self.skipTest(f"file symlink unavailable: {error}")
            validator.ROOT = temporary_root
            self.assertIn(
                "Mac-Win generated evidence validation failed",
                validator.validate_no_developer_paths(),
            )

    def test_reviewed_portable_assets_quarantine_unclosed_dependency_classes(self) -> None:
        cases = (
            ("scripts/inspect-chromium-page.swift", "unresolved-external-reference"),
            ("scripts/bootstrap-jasp-conan.sh", "unresolved-environment-path"),
            ("scripts/visual-acceptance-macwin.sh", "absolute-path"),
        )
        for path, reason in cases:
            with self.subTest(path=path):
                asset = self.assets[path]
                replacement = dataclasses.replace(
                    asset, license_status="reviewed", provenance_status="reviewed"
                )
                source_pack = dataclasses.replace(
                    self.result.source_pack,
                    assets=tuple(
                        replacement if existing is asset else existing
                        for existing in self.result.source_pack.assets
                    ),
                )
                result = self.converter.classify_source_pack(source_pack)
                record = next(
                    item for item in result.records if item.source_path == path
                )
                self.assertEqual(record.status, "quarantined")
                self.assertEqual(record.reason, reason)
                self.assertEqual(
                    record.evidence_locators,
                    tuple(
                        sorted(
                            {*asset.external_refs, *asset.development_dependencies},
                            key=lambda value: value.encode("utf-8"),
                        )
                    ),
                )

    def test_reviewed_closed_fixture_converts_to_a_schema_valid_inert_manifest(self) -> None:
        asset = self.assets["scripts/fixtures/meshlab-cube.obj"]
        replacement = dataclasses.replace(
            asset, license_status="reviewed", provenance_status="reviewed"
        )
        source_pack = dataclasses.replace(
            self.result.source_pack,
            assets=tuple(
                replacement if existing is asset else existing
                for existing in self.result.source_pack.assets
            ),
        )
        result = self.converter.classify_source_pack(source_pack)
        record = next(item for item in result.records if item.source_path == asset.source_path)
        self.assertEqual(record.status, "converted")
        manifest = self.converter._portable_document(replacement, record)
        schema = json.loads(
            (ROOT / "schemas/portable-fixture.schema.json").read_bytes()
        )
        MigrationSchemaTests._assert_schema_instance_valid(manifest, schema, schema)
        self.assertFalse(manifest["executable"])
        self.assertEqual(manifest["license"], {"status": "reviewed"})
        self.assertEqual(manifest["provenance"], {"status": "reviewed"})
        documents = self.converter.render_documents(result)
        manifest_path = (
            "migration/macwin/generated/fixtures/"
            "scripts-fixtures-meshlab-cube-obj.json"
        )
        self.assertEqual(
            self.common.parse_json_bytes(documents[manifest_path], label=manifest_path),
            manifest,
        )
        self.assertEqual(documents[manifest["contentPath"]], replacement.raw)

    def test_portable_content_uses_the_source_object_limit_not_metadata_limit(self) -> None:
        asset = self.assets["scripts/fixtures/meshlab-cube.obj"]
        raw = b"x" * (self.common.MAX_METADATA_BYTES + 1)
        digest = hashlib.sha256(raw).hexdigest()
        replacement = dataclasses.replace(
            asset,
            raw=raw,
            byte_size=len(raw),
            sha256=digest,
            git_blob_oid=self.converter._git_blob_oid(raw),
            object_path=f"objects/sha256/{digest[:2]}/{digest[2:]}",
            license_status="reviewed",
            provenance_status="reviewed",
        )
        result = self.converter.classify_source_pack(
            self._replace_asset(self.result.source_pack, asset, replacement)
        )
        documents = self.converter.render_documents(result)
        content_path = (
            "migration/macwin/generated/fixtures/content/sha256/"
            f"{digest[:2]}/{digest[2:]}"
        )
        self.assertEqual(documents[content_path], raw)

    def test_reviewed_closed_probe_and_fixture_use_the_real_portable_renderer(self) -> None:
        paths = (
            "scripts/analyze-window-image.py",
            "scripts/fixtures/meshlab-cube.obj",
        )
        replacements = {
            path: dataclasses.replace(
                self.assets[path],
                license_status="reviewed",
                provenance_status="reviewed",
            )
            for path in paths
        }
        source_pack = dataclasses.replace(
            self.result.source_pack,
            assets=tuple(
                replacements.get(asset.source_path, asset)
                for asset in self.result.source_pack.assets
            ),
        )
        result = self.converter.classify_source_pack(source_pack)
        with mock.patch.object(
            self.converter,
            "_portable_document",
            wraps=self.converter._portable_document,
        ) as render_spy:
            documents = self.converter.render_documents(result)

        rendered_paths = tuple(
            call.args[0].source_path for call in render_spy.call_args_list
        )
        self.assertEqual(set(rendered_paths), set(paths))
        for path in paths:
            self.assertGreaterEqual(rendered_paths.count(path), 1)
        for path in paths:
            identifier, _kind, _media_type = self.converter.PORTABLE_ASSET_TABLE[
                path
            ]
            category = (
                "probes" if self.assets[path].category == "probes" else "fixtures"
            )
            manifest_path = f"migration/macwin/generated/{category}/{identifier}.json"
            manifest = self.common.parse_json_bytes(
                documents[manifest_path], label=manifest_path
            )
            self.assertEqual(manifest["source"]["sourcePath"], path)
            self.assertEqual(documents[manifest["contentPath"]], replacements[path].raw)

    def test_portable_schemas_require_reviewed_license_and_provenance(self) -> None:
        cases = (
            ("scripts/analyze-window-image.py", "portable-probe.schema.json"),
            ("scripts/fixtures/meshlab-cube.obj", "portable-fixture.schema.json"),
        )
        for path, schema_name in cases:
            with self.subTest(schema=schema_name):
                asset = self.assets[path]
                reviewed = dataclasses.replace(
                    asset, license_status="reviewed", provenance_status="reviewed"
                )
                result = self.converter.classify_source_pack(
                    self._replace_asset(self.result.source_pack, asset, reviewed)
                )
                record = next(
                    item for item in result.records if item.source_path == path
                )
                manifest = self.converter._portable_document(reviewed, record)
                schema = json.loads((ROOT / "schemas" / schema_name).read_bytes())
                MigrationSchemaTests._assert_schema_instance_valid(
                    manifest, schema, schema
                )
                for field in ("license", "provenance"):
                    mutant = copy.deepcopy(manifest)
                    mutant[field] = {"status": "unresolved"}
                    with self.subTest(field=field), self.assertRaises(AssertionError):
                        MigrationSchemaTests._assert_schema_instance_valid(
                            mutant, schema, schema
                        )

    def test_portable_evidence_union_is_bounded_after_deduplication(self) -> None:
        schema = json.loads((ROOT / "schemas/quarantine.schema.json").read_bytes())
        asset = self.assets["scripts/analyze-window-image.py"]

        for count in (511, 512):
            with self.subTest(count=count):
                locators = tuple(
                    f"https://example.invalid/{index:03d}"
                    for index in range(count - 2)
                )
                replacement = dataclasses.replace(
                    asset,
                    external_refs=locators,
                )
                result = self.converter.classify_source_pack(
                    self._replace_asset(self.result.source_pack, asset, replacement)
                )
                documents = self.converter.render_documents(result)
                quarantine = self.common.parse_json_bytes(
                    documents["migration/macwin/generated/quarantine.json"],
                    label="bounded quarantine",
                )
                MigrationSchemaTests._assert_schema_instance_valid(
                    quarantine, schema, schema
                )
                record = next(
                    item
                    for item in quarantine["records"]
                    if item["sourcePath"] == asset.source_path
                )
                self.assertEqual(len(record["evidenceLocators"]), count)

        shared = tuple(
            f"https://example.invalid/{index:03d}" for index in range(510)
        )
        deduplicated = dataclasses.replace(
            asset,
            external_refs=shared,
            development_dependencies=(shared[-1],),
        )
        result = self.converter.classify_source_pack(
            self._replace_asset(self.result.source_pack, asset, deduplicated)
        )
        record = next(
            item for item in result.records if item.source_path == asset.source_path
        )
        self.assertEqual(len(record.evidence_locators), 512)

        oversized = dataclasses.replace(
            asset,
            external_refs=shared + ("https://example.invalid/510",),
        )
        with self.assertRaisesRegex(
            self.converter.ConversionError,
            "portable evidence locator set is invalid",
        ):
            self.converter.classify_source_pack(
                self._replace_asset(self.result.source_pack, asset, oversized)
            )

    def test_portable_asset_table_is_unconditionally_closed(self) -> None:
        converter = self.converter
        table = converter.PORTABLE_ASSET_TABLE
        self.assertEqual(len(table), 56)
        self.assertEqual(
            converter.APPROVED_PORTABLE_ASSET_TABLE_SHA256,
            "9db4bac2e7ddb3f542e655f5f9be1aed9d265ecd6dfa44cd563ef2b1c7eddf54",
        )
        probe_path = "scripts/analyze-window-image.py"
        fixture_path = "scripts/fixtures/meshlab-cube.obj"
        probe = table[probe_path]
        fixture = table[fixture_path]
        mutants = {
            "missing": {key: value for key, value in table.items() if key != probe_path},
            "extra": {
                **table,
                "scripts/extra.py": (
                    "scripts-extra-py",
                    "source",
                    "text/x-python",
                ),
            },
            "tuple": {**table, probe_path: probe[:2]},
            "media": {**table, probe_path: (probe[0], probe[1], "Text/Plain")},
            "duplicate-id": {
                **table,
                fixture_path: (probe[0], fixture[1], fixture[2]),
            },
            "fixture-kind": {
                **table,
                fixture_path: (fixture[0], "shell", fixture[2]),
            },
            "invalid-id": {
                **table,
                probe_path: ("Invalid/Id", probe[1], probe[2]),
            },
            "reserved-id": {
                **table,
                probe_path: ("con", probe[1], probe[2]),
            },
            "valid-id-substitution": {
                **table,
                probe_path: (f"{probe[0]}-reviewed", probe[1], probe[2]),
            },
            "valid-kind-substitution": {
                **table,
                probe_path: (probe[0], "data", probe[2]),
            },
            "valid-media-substitution": {
                **table,
                probe_path: (probe[0], probe[1], "application/octet-stream"),
            },
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), mock.patch.object(
                converter, "PORTABLE_ASSET_TABLE", mutant
            ), self.assertRaisesRegex(
                converter.ConversionError, "portable asset table is invalid"
            ):
                converter.classify_source_pack(self.result.source_pack)

        with mock.patch.object(
            converter, "PORTABLE_ASSET_TABLE", mutants["media"]
        ), self.assertRaisesRegex(
            converter.ConversionError,
            "portable asset table is invalid",
        ):
            converter.render_documents(self.result)

    def test_portable_asset_size_and_mode_rules_reject_source_mutants(self) -> None:
        asset = self.assets["scripts/analyze-window-image.py"]
        empty = b""
        empty_sha = hashlib.sha256(empty).hexdigest()
        empty_oid = hashlib.sha1(b"blob 0\0").hexdigest()
        mutants = {
            "zero-size": dataclasses.replace(
                asset,
                raw=empty,
                byte_size=0,
                sha256=empty_sha,
                git_blob_oid=empty_oid,
                object_path=f"objects/sha256/{empty_sha[:2]}/{empty_sha[2:]}",
            ),
            "invalid-mode": dataclasses.replace(asset, git_mode="100600"),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), self.assertRaises(
                self.converter.ConversionError
            ):
                self.converter.classify_source_pack(
                    self._replace_asset(self.result.source_pack, asset, mutant)
                )

    def test_portable_reference_graph_is_closed_acyclic_and_bounded(self) -> None:
        converter = self.converter
        references = converter.PORTABLE_REFERENCE_TABLE
        paths = tuple(converter.PORTABLE_ASSET_TABLE)
        first, second = paths[:2]
        first_id = converter.PORTABLE_ASSET_TABLE[first][0]
        second_id = converter.PORTABLE_ASSET_TABLE[second][0]
        mutants = {
            "missing": {key: value for key, value in references.items() if key != first},
            "unknown": {**references, first: ("unknown-id",)},
            "self": {**references, first: (first_id,)},
            "cycle": {**references, first: (second_id,), second: (first_id,)},
            "duplicate": {**references, first: (second_id, second_id)},
            "oversized": {**references, first: tuple(second_id for _ in range(91))},
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), mock.patch.object(
                converter, "PORTABLE_REFERENCE_TABLE", mutant
            ), self.assertRaisesRegex(
                converter.ConversionError, "portable reference graph is invalid"
            ):
                converter.classify_source_pack(self.result.source_pack)

    def test_converted_portable_reference_rejects_a_quarantined_target(self) -> None:
        converter = self.converter
        source_path = "scripts/analyze-window-image.py"
        target_path = "scripts/fixtures/meshlab-cube.obj"
        source = self.assets[source_path]
        reviewed_source = dataclasses.replace(
            source, license_status="reviewed", provenance_status="reviewed"
        )
        references = {
            **converter.PORTABLE_REFERENCE_TABLE,
            source_path: (converter.PORTABLE_ASSET_TABLE[target_path][0],),
        }
        with mock.patch.object(
            converter, "PORTABLE_REFERENCE_TABLE", references
        ), self.assertRaisesRegex(
            converter.ConversionError,
            "portable converted reference is unresolved",
        ):
            converter.classify_source_pack(
                self._replace_asset(self.result.source_pack, source, reviewed_source)
            )

    def test_converted_portable_reference_renders_both_closed_manifests(self) -> None:
        converter = self.converter
        source_path = "scripts/analyze-window-image.py"
        target_path = "scripts/fixtures/meshlab-cube.obj"
        replacements = {
            path: dataclasses.replace(
                self.assets[path],
                license_status="reviewed",
                provenance_status="reviewed",
            )
            for path in (source_path, target_path)
        }
        source_pack = dataclasses.replace(
            self.result.source_pack,
            assets=tuple(
                replacements.get(asset.source_path, asset)
                for asset in self.result.source_pack.assets
            ),
        )
        target_id = converter.PORTABLE_ASSET_TABLE[target_path][0]
        references = {
            **converter.PORTABLE_REFERENCE_TABLE,
            source_path: (target_id,),
        }
        with mock.patch.object(converter, "PORTABLE_REFERENCE_TABLE", references):
            result = converter.classify_source_pack(source_pack)
            documents = converter.render_documents(result)
        source_id = converter.PORTABLE_ASSET_TABLE[source_path][0]
        source_manifest_path = (
            f"migration/macwin/generated/probes/{source_id}.json"
        )
        target_manifest_path = (
            f"migration/macwin/generated/fixtures/{target_id}.json"
        )
        source_manifest = self.common.parse_json_bytes(
            documents[source_manifest_path], label=source_manifest_path
        )
        self.assertEqual(source_manifest["referencedAssetIds"], [target_id])
        self.assertIn(target_manifest_path, documents)

    @staticmethod
    def _replace_asset(source_pack, original, replacement):
        return dataclasses.replace(
            source_pack,
            assets=tuple(
                replacement if existing is original else existing
                for existing in source_pack.assets
            ),
        )


class MacWinRecipeConversionTests(unittest.TestCase):
    EXPECTED_RECIPE_DECISIONS = {
        "7zip": "missing-license",
        "firefox": "missing-license",
        "hoyoplay-cn": "missing-license",
        "jasp-stats": "missing-license",
        "lenovo-app-store": "missing-license",
        "libreoffice": "missing-license",
        "ltspice": "missing-license",
        "macwin-core-capability-tests": "missing-license",
        "macwin-game-tests": "missing-license",
        "macwin-probes": "missing-license",
        "notepad-plus-plus": "missing-license",
        "portableapps-platform": "missing-license",
        "sqlitestudio": "missing-license",
        "steam": "missing-license",
        "sumatrapdf": "missing-license",
        "texstudio": "missing-license",
        "vlc": "missing-license",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.common = _load_macwin_asset_common()
        cls.result = cls.converter.build_conversion(ROOT)
        cls.assets = {
            asset.source_path: asset for asset in cls.result.source_pack.assets
        }

    def test_real_catalog_count_and_each_reviewed_decision_are_sealed(self) -> None:
        documents = self.converter.render_documents(self.result)
        catalog_path = "migration/macwin/generated/catalog.json"
        quarantine_path = "migration/macwin/generated/quarantine.json"
        self.assertEqual(
            set(documents),
            {
                catalog_path,
                quarantine_path,
                "migration/macwin/generated/mappings/patches.json",
                "migration/macwin/generated/mappings/bottle-schemas.json",
                "migration/macwin/generated/index.json",
            },
        )
        catalog = self.common.parse_json_bytes(
            documents[catalog_path], label="generated catalog"
        )
        quarantine = self.common.parse_json_bytes(
            documents[quarantine_path], label="generated quarantine"
        )

        self.assertEqual(catalog["candidateCount"], 17)
        self.assertEqual(catalog["convertedCount"], 0)
        self.assertEqual(catalog["quarantinedCount"], 17)
        self.assertEqual(catalog["catalogBoundary"]["index"]["sourcePath"], self.converter.CATALOG_INDEX_PATH)
        self.assertEqual(catalog["catalogBoundary"]["signature"]["sourcePath"], self.converter.CATALOG_SIGNATURE_PATH)
        actual = {
            entry["id"]: entry["reason"] for entry in catalog["candidates"]
        }
        self.assertEqual(actual, self.EXPECTED_RECIPE_DECISIONS)
        self.assertEqual(
            [entry["sourcePath"] for entry in catalog["candidates"]],
            sorted(
                (entry["sourcePath"] for entry in catalog["candidates"]),
                key=lambda value: value.encode("ascii"),
            ),
        )
        catalog_quarantine = [
            record for record in quarantine["records"] if record["category"] == "catalog"
        ]
        self.assertEqual(len(catalog_quarantine), 17)
        self.assertEqual(
            {record["sourcePath"] for record in catalog_quarantine},
            {entry["sourcePath"] for entry in catalog["candidates"]},
        )

    def test_supported_source_structure_maps_without_inventing_evidence(self) -> None:
        asset = self._recipe_asset("7zip")
        source = self.converter._parse_json_object(asset)
        draft = self.converter._map_recipe_structure(source)
        self.assertEqual(
            set(draft),
            {
                "schemaVersion",
                "id",
                "metadata",
                "installer",
                "bottle",
                "launchers",
                "compatibility",
                "fixes",
            },
        )
        self.assertNotIn("license", draft["metadata"])
        self.assertNotIn("tests", draft)
        self.assertNotIn("provenance", draft)
        self.assertEqual(draft["bottle"]["guestArchitecture"], "x86_64")
        self.assertEqual(draft["bottle"]["windowsVersion"], "win11")
        self.assertEqual(list(draft["bottle"]["environment"]), [])
        self.assertEqual(
            draft["launchers"],
            [
                {
                    "id": "7zip-file-manager",
                    "name": "7-Zip File Manager",
                    "executable": "C:\\Program Files\\7-Zip\\7zFM.exe",
                    "arguments": [],
                    "environment": {},
                }
            ],
        )
        self.assertEqual(
            draft["installer"],
            {
                "mode": "download",
                "url": "https://www.7-zip.org/a/7z2601-x64.exe",
                "fileName": "7z2601-x64.exe",
                "sha256": "d64a0468f5b5b0b0fc5b2188450bcd655b70809d97b1c4535f2884635094377d",
                "arguments": ["/S"],
            },
        )
        self.assertEqual(draft["compatibility"]["rating"], "excellent")
        self.assertEqual(draft["compatibility"]["platforms"], [])
        self.assertEqual(
            draft["compatibility"]["warnings"], source["warnings"]
        )

    def test_complete_reviewed_candidate_renders_a_schema_valid_recipe(self) -> None:
        result = self._synthetic_reviewed_recipe_result()
        documents = self.converter.render_documents(result)
        recipe_path = "migration/macwin/generated/recipes/7zip.json"
        self.assertEqual(
            set(documents),
            {
                "migration/macwin/generated/catalog.json",
                "migration/macwin/generated/quarantine.json",
                "migration/macwin/generated/mappings/patches.json",
                "migration/macwin/generated/mappings/bottle-schemas.json",
                recipe_path,
                "migration/macwin/generated/index.json",
            },
        )
        self.assertEqual(documents, self.converter.render_documents(result))
        self.assertFalse((ROOT / PurePosixPath(recipe_path)).exists())

        catalog = self.common.parse_json_bytes(
            documents["migration/macwin/generated/catalog.json"],
            label="synthetic catalog",
        )
        self.assertEqual(catalog["convertedCount"], 1)
        self.assertEqual(catalog["quarantinedCount"], 16)
        converted = next(
            entry for entry in catalog["candidates"] if entry["status"] == "converted"
        )
        self.assertEqual(converted["recipePath"], recipe_path)
        self.assertEqual(
            converted["recipeSha256"], hashlib.sha256(documents[recipe_path]).hexdigest()
        )

        recipe = self.common.parse_json_bytes(
            documents[recipe_path], label="synthetic recipe"
        )
        self.assertEqual(recipe["metadata"]["license"], "LGPL-2.1-or-later")
        self.assertEqual(
            recipe["tests"],
            [
                {
                    "expected": {"exitCode": 0},
                    "id": "launch-smoke",
                    "kind": "process-exit",
                    "timeoutSeconds": 120,
                }
            ],
        )
        recipe_asset = next(
            asset for asset in result.source_pack.assets if asset.source_path.endswith(
                "/recipes/7zip.json"
            )
        )
        self.assertEqual(
            recipe["provenance"],
            {
                "sourceCommit": recipe_asset.source_commit,
                "sourcePath": recipe_asset.source_path,
                "sourceRepository": result.source_pack.repository,
                "sourceSha256": recipe_asset.sha256,
            },
        )
        recipe_schema = json.loads((ROOT / "schemas/recipe.schema.json").read_bytes())
        MigrationSchemaTests._assert_schema_instance_valid(
            recipe, recipe_schema, recipe_schema
        )

    def test_reviewed_candidate_missing_evidence_fails_closed(self) -> None:
        cases = {
            "tests": (
                "unsupported-schema",
                lambda source, asset: (source.pop("tests"), None)[1],
            ),
            "license": (
                "missing-license",
                lambda source, asset: (source.pop("license"), None)[1],
            ),
            "provenance": (
                "missing-provenance",
                lambda source, asset: {"provenance_status": "unresolved"},
            ),
            "unknown-test-field": (
                "unsupported-schema",
                lambda source, asset: source["tests"][0].__setitem__(
                    "shell", "host-command"
                ),
            ),
        }
        for name, (expected_reason, mutation) in cases.items():
            with self.subTest(case=name):
                result = self._synthetic_reviewed_recipe_result(mutation)
                record = next(
                    record
                    for record in result.records
                    if record.source_path.endswith("/recipes/7zip.json")
                )
                self.assertEqual(record.status, "quarantined")
                self.assertEqual(record.reason, expected_reason)

    def test_environment_and_launcher_maps_are_sorted(self) -> None:
        asset = self._recipe_asset("firefox")
        source = self.converter._parse_json_object(asset)
        draft = self.converter._map_recipe_structure(source)
        self.assertEqual(
            list(draft["bottle"]["environment"]),
            sorted(source["env"], key=lambda value: value.encode("utf-8")),
        )
        self.assertEqual(
            list(draft["launchers"][0]["environment"]),
            sorted(
                source["launchers"][0]["envOverrides"],
                key=lambda value: value.encode("utf-8"),
            ),
        )
        self.assertNotIn("command", draft["installer"])
        self.assertEqual(draft["installer"]["arguments"], source["installer"]["arguments"])

    def test_host_dependency_detection_covers_portable_path_attacks(self) -> None:
        hostile = (
            "~",
            "~reviewer",
            "~reviewer/private/tool.exe",
            "~reviewer\\private\\tool.exe",
            "/Users/reviewer/tool.exe",
            "C:/Users/reviewer/tool.exe",
            "C:\\Users\\reviewer\\tool.exe",
            "//server/share/tool.exe",
            "\\\\server\\share\\tool.exe",
            "//?/C:/device/tool.exe",
            "\\\\?\\C:\\device\\tool.exe",
            "//./pipe/host",
            "\\\\.\\pipe\\host",
            "~/private/tool.exe",
            "~\\private\\tool.exe",
            "%USERPROFILE%\\private\\tool.exe",
            "%USERPROFILE%",
            "${HOME}/private/tool.exe",
            "${HOME}",
            "${REVIEW_ROOT}",
            "$HOME/private/tool.exe",
            "$HOME",
            "$REVIEW_ROOT",
            "file:///Users/reviewer/tool.exe",
            "FILE://server/share/tool.exe",
            "C:relative.exe",
        )
        for value in hostile:
            with self.subTest(value=value):
                self.assertTrue(self.converter._is_host_absolute_locator(value))
        for value in (
            "bin/tool.exe",
            "bin\\tool.exe",
            "https://example.invalid/tool.exe",
            "release-26.2.4",
            "version:$stable",
        ):
            with self.subTest(safe=value):
                self.assertFalse(self.converter._is_host_absolute_locator(value))

    def test_guest_executable_contract_normalizes_separators_and_windows_rules(self) -> None:
        safe = (
            "bin/tool.exe",
            "bin\\tool.exe",
            "Program Files/App/tool.exe",
            "Program Files\\App\\tool.exe",
            "C:/Program Files/App/tool.exe",
            "C:\\Program Files\\App\\tool.exe",
        )
        hostile = (
            "",
            "/absolute/tool.exe",
            "D:/absolute/tool.exe",
            "C:relative.exe",
            "//server/share/tool.exe",
            "\\\\server\\share\\tool.exe",
            "\\\\?\\C:\\device\\tool.exe",
            "\\\\.\\pipe\\tool.exe",
            "../tool.exe",
            ".\\tool.exe",
            "bin/../tool.exe",
            "bin//tool.exe",
            "bin/tool.exe:stream",
            "C:/Program Files/App/tool.exe:stream",
            "C:\\Program Files/App\\..\\tool.exe",
            "bin/a<b.exe",
            "bin/a>b.exe",
            'bin/a"b.exe',
            "bin/a|b.exe",
            "bin/a?b.exe",
            "bin/a*b.exe",
            "bin/trailing.",
            "bin/trailing ",
            "bin/control\x1f.exe",
            "CON",
            "con.txt",
            "bin/PRN.log",
            "bin/AUX",
            "bin/NUL.txt",
            "bin/COM1.exe",
            "bin/LPT9.exe",
            "bin/CONIN$.txt",
            "bin/CONOUT$.txt",
            ("a" * 256) + "/tool.exe",
            "/".join(["a" * 255] * 5),
        )
        for value in safe:
            with self.subTest(safe=value):
                self.assertTrue(self.converter._is_safe_guest_executable(value))
        for value in hostile:
            with self.subTest(hostile=value):
                self.assertFalse(self.converter._is_safe_guest_executable(value))

    def test_installer_locators_and_filenames_are_portable(self) -> None:
        asset = self._recipe_asset("7zip")
        base = self.converter._parse_json_object(asset)
        reviewed = dataclasses.replace(
            asset,
            development_dependencies=(),
            external_refs=(),
            license_status="reviewed",
            provenance_status="reviewed",
        )
        source = copy.deepcopy(base)
        source["license"] = "LGPL-2.1-or-later"
        source["tests"] = [
            {"id": "smoke", "kind": "process-exit", "timeoutSeconds": 30}
        ]
        hostile_urls = (
            "file:///Users/reviewer/setup.exe",
            "FILE://server/share/setup.exe",
            "/Users/reviewer/setup.exe",
            "C:\\Users\\reviewer\\setup.exe",
            "%TEMP%\\setup.exe",
        )
        hostile_names = (
            "../setup.exe",
            "folder/setup.exe",
            "folder\\setup.exe",
            "C:\\setup.exe",
            "setup.exe:stream",
            "CON.exe",
            "setup.exe.",
            "setup.exe ",
            "set?up.exe",
            "setup\x1f.exe",
            ("a" * 256) + ".exe",
        )
        for field, values in (("url", hostile_urls), ("fileName", hostile_names)):
            for value in values:
                with self.subTest(field=field, value=value[:30]):
                    candidate = copy.deepcopy(source)
                    candidate["installer"][field] = value
                    findings = self.converter._recipe_findings(reviewed, candidate)
                    self.assertIn(
                        self.converter._select_recipe_reason(findings),
                        {"absolute-path", "unresolved-external-reference", "unsupported-schema"},
                    )
        findings = self.converter._recipe_findings(reviewed, source)
        self.assertIsNone(self.converter._select_recipe_reason(findings))
        recipe = self.converter._render_reviewed_recipe(reviewed, source)
        schema = json.loads((ROOT / "schemas/recipe.schema.json").read_bytes())
        MigrationSchemaTests._assert_schema_instance_valid(recipe, schema, schema)

    def test_installer_network_url_contract_is_closed_and_unambiguous(self) -> None:
        invalid = (
            "https://",
            "http://",
            " https://example.invalid/setup.exe",
            "https://example.invalid/setup.exe ",
            "https://example.invalid/set up.exe",
            "https://example.invalid/setup.exe\n",
            "https://example.invalid/setup.exe\x1f",
            "https://[::1/setup.exe",
            "https://::1/setup.exe",
            "https:///setup.exe",
            "https://.example.invalid/setup.exe",
            "https://example..invalid/setup.exe",
            "https://-example.invalid/setup.exe",
            "https://example-.invalid/setup.exe",
            "https://example.invalid:0/setup.exe",
            "https://example.invalid:65536/setup.exe",
            "https://example.invalid:notaport/setup.exe",
            "https://example.invalid:/setup.exe",
            "https://example.invalid:0443/setup.exe",
            "https://user@example.invalid/setup.exe",
            "https://user:secret@example.invalid/setup.exe",
            "https://example.invalid\\setup.exe",
            "https:\\example.invalid\\setup.exe",
            "https://example.invalid/setup.exe#fragment",
            "https://example.invalid/setup.exe#",
            "https://example.invalid/setup.exe?",
            "https://example.invalid//setup.exe",
            "https://example.invalid/%2e%2e/setup.exe",
            "https://example.invalid/%5csetup.exe",
            "https://example.invalid/%zz/setup.exe",
            "https://example.invalid/set|up.exe",
            "https://café.invalid/setup.exe",
            "https://example.invalid./setup.exe",
            "https://256.1.1.1/setup.exe",
            "https://example.invalid/" + ("a" * 2049),
            "https://example.invalid/setup.exe?" + ("a" * 2049),
            "ftp://example.invalid/setup.exe",
        )
        valid = (
            "https://example.invalid/setup.exe",
            "HTTP://example.invalid/setup.exe",
            "https://127.0.0.1/setup.exe",
            "https://[2001:db8::1]/setup.exe",
            "https://example.invalid:8443/path/setup.exe?channel=stable",
        )
        for value in invalid:
            with self.subTest(invalid=value[:40]):
                self.assertFalse(self.converter._is_safe_installer_url(value))
                asset = self._recipe_asset("7zip")
                source = self.converter._parse_json_object(asset)
                source["installer"]["url"] = value
                finding = self.converter.RecipeFinding(
                    reason="unresolved-external-reference",
                    evidence_locator=f"{asset.source_path}#installer.url",
                )
                self.assertIn(finding, self.converter._recipe_findings(asset, source))
        for value in valid:
            with self.subTest(valid=value):
                self.assertTrue(self.converter._is_safe_installer_url(value))

        result = self._synthetic_reviewed_recipe_result(
            lambda source, asset: source["installer"].__setitem__(
                "url", valid[-1]
            )
        )
        documents = self.converter.render_documents(result)
        recipe = self.common.parse_json_bytes(
            documents["migration/macwin/generated/recipes/7zip.json"],
            label="safe URL recipe",
        )
        schema = json.loads((ROOT / "schemas/recipe.schema.json").read_bytes())
        MigrationSchemaTests._assert_schema_instance_valid(recipe, schema, schema)

    def test_reviewed_candidate_rejects_ambiguous_numeric_and_invalid_alabel_hosts(self) -> None:
        invalid = (
            "https://0x7f.0.0.1/setup.exe",
            "https://0x7f000001/setup.exe",
            "https://0177.0.0.1/setup.exe",
            "https://127.1/setup.exe",
            "https://2130706433/setup.exe",
            "https://xn--a.invalid/setup.exe",
        )
        for value in invalid:
            with self.subTest(invalid=value):
                result = self._synthetic_reviewed_recipe_result(
                    lambda source, asset, url=value: source["installer"].__setitem__(
                        "url", url
                    )
                )
                record = next(
                    record
                    for record in result.records
                    if record.source_path.endswith("/recipes/7zip.json")
                )
                self.assertEqual(record.status, "quarantined")
                self.assertEqual(record.reason, "unresolved-external-reference")
                self.assertIn(
                    f"{record.source_path}#installer.url", record.evidence_locators
                )
                self.assertNotIn(value, record.evidence_locators)

        valid = (
            "https://127.0.0.1/setup.exe",
            "https://example.invalid/setup.exe",
            "https://xn--caf-dma.invalid/setup.exe",
            "https://XN--CAF-DMA.invalid/setup.exe",
            "https://[2001:db8::1]/setup.exe",
        )
        for value in valid:
            with self.subTest(valid=value):
                self.assertTrue(self.converter._is_safe_installer_url(value))
                result = self._synthetic_reviewed_recipe_result(
                    lambda source, asset, url=value: source["installer"].__setitem__(
                        "url", url
                    )
                )
                record = next(
                    record
                    for record in result.records
                    if record.source_path.endswith("/recipes/7zip.json")
                )
                self.assertEqual(record.status, "converted")

    def test_every_rejection_rule_is_detected_with_fixed_precedence(self) -> None:
        asset = self._recipe_asset("7zip")
        base = self.converter._parse_json_object(asset)
        cases = {}

        candidate = copy.deepcopy(base)
        candidate["installer"]["mode"] = "alreadyInstalled"
        cases["mutable"] = (candidate, "mutable-local-installation")

        candidate = copy.deepcopy(base)
        candidate["installer"]["hints"] = ["/Users/reviewer/private/installer.exe"]
        cases["absolute-hint"] = (candidate, "absolute-path")

        candidate = copy.deepcopy(base)
        candidate["installer"].pop("sha256")
        cases["missing-digest"] = (candidate, "missing-digest")

        candidate = copy.deepcopy(base)
        candidate["postInstall"] = [{"command": "host-shell"}]
        cases["post-install"] = (candidate, "unsupported-behavior")

        candidate = copy.deepcopy(base)
        candidate["unknownField"] = "must not be copied"
        cases["unknown-field"] = (candidate, "unsupported-schema")

        candidate = copy.deepcopy(base)
        candidate["launchers"][0]["exePath"] = "../host.exe"
        cases["unsafe-launcher"] = (candidate, "unsupported-behavior")

        for name, (candidate, expected) in cases.items():
            with self.subTest(case=name):
                findings = self.converter._recipe_findings(asset, candidate)
                reasons = tuple(finding.reason for finding in findings)
                self.assertIn(expected, reasons)
                self.assertEqual(
                    self.converter._select_recipe_reason(findings),
                    "missing-license",
                    "the frozen asset's missing license has fixed first precedence",
                )

        provenance_only = dataclasses.replace(asset, license_status="reviewed")
        source_with_license = copy.deepcopy(base)
        source_with_license["license"] = "reviewed-license"
        findings = self.converter._recipe_findings(
            provenance_only, source_with_license
        )
        self.assertEqual(
            self.converter._select_recipe_reason(findings), "missing-provenance"
        )

    def test_quarantine_keeps_inert_evidence_and_never_probes_it(self) -> None:
        with mock.patch.object(
            Path, "open", side_effect=AssertionError("evidence opened")
        ), mock.patch.object(
            Path, "exists", side_effect=AssertionError("evidence probed")
        ), mock.patch.object(
            Path, "stat", side_effect=AssertionError("evidence stated")
        ), mock.patch.object(
            os.path, "expandvars", side_effect=AssertionError("environment expanded")
        ), mock.patch.object(
            os.path, "expanduser", side_effect=AssertionError("home expanded")
        ):
            documents = self.converter.render_documents(self.result)
        quarantine = self.common.parse_json_bytes(
            documents["migration/macwin/generated/quarantine.json"],
            label="generated quarantine",
        )
        records = {record["sourcePath"]: record for record in quarantine["records"]}
        download_record = records[self._recipe_asset("7zip").source_path]
        self.assertIn(
            "https://www.7-zip.org/a/7z2601-x64.exe",
            download_record["evidenceLocators"],
        )
        for identifier in (
            "hoyoplay-cn",
            "macwin-core-capability-tests",
            "macwin-game-tests",
            "macwin-probes",
        ):
            record = records[self._recipe_asset(identifier).source_path]
            evidence = record["evidenceLocators"]
            self.assertEqual(
                evidence, sorted(set(evidence), key=lambda value: value.encode("utf-8"))
            )
            self.assertTrue(any(value.startswith("/Users/") for value in evidence))

    def test_outputs_are_closed_canonical_and_match_committed_goldens(self) -> None:
        documents = self.converter.render_documents(self.result)
        recipe_schema = json.loads((ROOT / "schemas/recipe.schema.json").read_bytes())
        quarantine_schema = json.loads(
            (ROOT / "schemas/quarantine.schema.json").read_bytes()
        )
        mapping_schema = json.loads(
            (ROOT / "schemas/migration-record.schema.json").read_bytes()
        )
        for relative, raw in documents.items():
            with self.subTest(path=relative):
                value = self.common.parse_json_bytes(raw, label=relative)
                self.assertEqual(self.common.canonical_json_bytes(value), raw)
                self.assertLessEqual(len(raw), self.common.MAX_METADATA_BYTES)
                committed = ROOT / PurePosixPath(relative)
                self.assertTrue(committed.is_file())
                self.assertEqual(committed.read_bytes(), raw)
                if relative.endswith("quarantine.json"):
                    MigrationSchemaTests._assert_schema_instance_valid(
                        value, quarantine_schema, quarantine_schema
                    )
                elif "/mappings/" in relative:
                    MigrationSchemaTests._assert_schema_instance_valid(
                        value, mapping_schema, mapping_schema
                    )
                elif "/recipes/" in relative:
                    MigrationSchemaTests._assert_schema_instance_valid(
                        value, recipe_schema, recipe_schema
                    )

    def test_catalog_digest_traceability_and_task6_scope_are_exact(self) -> None:
        documents = self.converter.render_documents(self.result)
        catalog = self.common.parse_json_bytes(
            documents["migration/macwin/generated/catalog.json"],
            label="generated catalog",
        )
        for entry in catalog["candidates"]:
            asset = self.assets[entry["sourcePath"]]
            self.assertEqual(entry["sourceSha256"], asset.sha256)
            self.assertEqual(entry["sourceCommit"], asset.source_commit)
            if entry["status"] == "converted":
                raw = documents[entry["recipePath"]]
                self.assertEqual(entry["recipeSha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(
            any(
                "/probes/" in path
                or "/fixtures/" in path
                or "/recipes/" in path
                for path in documents
            )
        )
        self.assertIn("migration/macwin/generated/index.json", documents)
        self.assertEqual(
            {path for path in documents if "/mappings/" in path},
            {
                "migration/macwin/generated/mappings/patches.json",
                "migration/macwin/generated/mappings/bottle-schemas.json",
            },
        )

    def test_repository_validator_exempts_only_exact_rebuilt_task5_evidence(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            validator.ROOT = temporary_root
            self.assertEqual(validator.validate_no_developer_paths(), [])

    def test_repository_validator_rejects_self_consistent_forged_task5_documents(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            catalog_path = temporary_root / "migration/macwin/generated/catalog.json"
            quarantine_path = temporary_root / "migration/macwin/generated/quarantine.json"
            forged_catalog = catalog_path.read_bytes().replace(
                b'"name": "7-Zip"',
                b'"name": "\\u002fUsers\\u002freviewer\\u002fhidden"',
                1,
            )
            self.assertNotIn(b"/Users/", forged_catalog)
            catalog_path.write_bytes(forged_catalog)
            forged = {
                "migration/macwin/generated/catalog.json": forged_catalog,
                "migration/macwin/generated/quarantine.json": quarantine_path.read_bytes(),
            }

            class ForgedConverter:
                @staticmethod
                def build_conversion(_root):
                    return object()

                @staticmethod
                def render_documents(_result):
                    return dict(forged)

            real_loader = validator._load_task5_converter

            def load_forged_converter():
                _converter, path, raw, identity = real_loader()
                return ForgedConverter(), path, raw, identity

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator, "_load_task5_converter", load_forged_converter
            ):
                errors = validator.validate_no_developer_paths()
            self.assertIn("Mac-Win generated evidence validation failed", errors)

            quarantine = temporary_root / "migration/macwin/generated/quarantine.json"
            original = quarantine.read_bytes()
            value = json.loads(original)
            value["records"][0]["releaseCondition"] = "self-consistent forgery"
            quarantine.write_bytes(self.common.canonical_json_bytes(value))
            errors = validator.validate_no_developer_paths()
            self.assertIn("Mac-Win generated evidence validation failed", errors)

    def test_repository_validator_rejects_self_consistent_future_converter_documents(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        for case in ("safe", "hostile"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=".macwin-task5-validator-", dir=ROOT
            ) as directory:
                temporary_root = Path(directory)
                self._copy_validator_fixture(temporary_root)
                future = temporary_root / "migration/macwin/generated/future.json"
                future_raw = (
                    b'{"future":"portable"}\n'
                    if case == "safe"
                    else b'{"future":"/Users/' + b'a1-6/hostile"}\n'
                )
                future.write_bytes(future_raw)
                real_loader = validator._load_task5_converter

                class FutureConverter:
                    def __init__(self, converter):
                        self._converter = converter

                    def build_conversion(self, root):
                        return self._converter.build_conversion(root)

                    def render_documents(self, result):
                        documents = self._converter.render_documents(result)
                        return {
                            **documents,
                            "migration/macwin/generated/future.json": future_raw,
                        }

                def load_future_converter():
                    converter, path, raw, identity = real_loader()
                    return FutureConverter(converter), path, raw, identity

                validator.ROOT = temporary_root
                with mock.patch.object(
                    validator, "_load_task5_converter", load_future_converter
                ):
                    errors = validator.validate_no_developer_paths()
                self.assertIn(
                    "Mac-Win generated evidence validation failed", errors
                )

    def test_repository_validator_rejects_extra_generated_developer_evidence(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            hostile = temporary_root / "migration/macwin/generated/unreferenced.json"
            hostile.write_text(
                '{"path":"/Users/' + 'a1-6/unreviewed"}\n',
                encoding="utf-8",
                newline="\n",
            )
            validator.ROOT = temporary_root
            errors = validator.validate_no_developer_paths()
            self.assertTrue(
                any(
                    hostile.name in error
                    and "contains developer path /Users/" + "a1-6/" in error
                    for error in errors
                ),
                errors,
            )

    def test_repository_validator_rejects_an_ordinary_external_symlink_without_following_it(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory, tempfile.TemporaryDirectory(
            prefix=".macwin-task5-external-", dir=ROOT
        ) as external_directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            external = Path(external_directory) / "hostile.json"
            external.write_text(
                '{"path":"/Users/' + 'a1-6/external"}\n',
                encoding="utf-8",
                newline="\n",
            )
            linked = temporary_root / "migration/macwin/generated/unreferenced.json"
            try:
                linked.symlink_to(external)
            except OSError as error:
                self.skipTest(f"file symlink unavailable: {error}")

            validator.ROOT = temporary_root
            self.assertEqual(
                validator.validate_no_developer_paths(),
                [
                    "Mac-Win generated evidence validation failed",
                    "Repository developer-path validation failed",
                ],
            )

    def test_repository_validator_rejects_ordinary_post_read_same_size_mutation(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            target = temporary_root / "ordinary.txt"
            hostile = b"/Users/" + b"a1-6/owned\n"
            benign = b"x" * (len(hostile) - 1) + b"\n"
            target.write_bytes(benign)
            metadata = target.stat()
            original_reader = validator._read_bound_regular_file
            injected = False

            def mutate_after_read(
                path: Path, maximum: int, *, require_single_link: bool = True
            ):
                nonlocal injected
                if require_single_link:
                    result = original_reader(path, maximum)
                else:
                    result = original_reader(
                        path, maximum, require_single_link=False
                    )
                if path.absolute() == target.absolute() and not injected:
                    target.write_bytes(hostile)
                    os.utime(
                        target,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
                    )
                    injected = True
                return result

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator, "_read_bound_regular_file", mutate_after_read
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(target.stat().st_size, metadata.st_size)
            self.assertEqual(target.stat().st_mtime_ns, metadata.st_mtime_ns)
            self.assertEqual(
                errors,
                ["Repository developer-path validation failed"],
            )

    def test_repository_validator_accepts_safe_regular_and_stable_hardlinks(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            safe = temporary_root / "ordinary-safe.txt"
            safe.write_text("portable evidence\n", encoding="utf-8", newline="\n")
            validator.ROOT = temporary_root
            self.assertEqual(validator.validate_no_developer_paths(), [])

            linked = temporary_root / "ordinary-hardlink.txt"
            try:
                os.link(safe, linked)
            except OSError as error:
                self.skipTest(f"hardlink unavailable: {error}")
            self.assertEqual(validator.validate_no_developer_paths(), [])

    def test_ordinary_scan_reads_each_unique_hardlink_inode_only_twice(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            source = temporary_root / "ordinary-hardlink-00.bin"
            source.write_bytes(b"x" * (1024 * 1024))
            try:
                for index in range(1, 65):
                    os.link(source, temporary_root / f"ordinary-hardlink-{index:02d}.bin")
            except OSError as error:
                self.skipTest(f"hardlink unavailable: {error}")
            original_reader = validator._read_bound_regular_file
            reads = 0

            def count_reads(path: Path, maximum: int, *, require_single_link=True):
                nonlocal reads
                if path.name.startswith("ordinary-hardlink-"):
                    reads += 1
                return original_reader(
                    path, maximum, require_single_link=require_single_link
                )

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator, "_read_bound_regular_file", count_reads
            ):
                errors, binding = validator._scan_developer_paths(None, None)
                binding.revalidate()
            self.assertEqual(errors, [])
            self.assertLessEqual(reads, 2)

    def test_ordinary_scan_entry_and_unique_byte_limits_fail_closed(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        for case in ("entries", "bytes"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=".macwin-task5-validator-", dir=ROOT
            ) as directory:
                temporary_root = Path(directory)
                if case == "entries":
                    for index in range(3):
                        (temporary_root / f"safe-{index}.txt").write_text(
                            "x", encoding="utf-8", newline="\n"
                        )
                    patches = {"MAX_ORDINARY_SCAN_ENTRIES": 2}
                else:
                    (temporary_root / "safe.txt").write_bytes(b"12345")
                    patches = {"MAX_ORDINARY_SCAN_TOTAL_BYTES": 4}
                validator.ROOT = temporary_root
                with mock.patch.multiple(validator, **patches):
                    with self.assertRaises(validator._DeveloperPathScanError):
                        validator._scan_developer_paths(None, None)

    def test_repository_validator_stably_accepts_complete_fixture_twenty_four_times(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            cargo = temporary_root / "target/debug/build/example"
            cargo.mkdir(parents=True)
            executable = cargo / "build-script-build.exe"
            executable.write_bytes(b"MZ-stable-build-output")
            try:
                os.link(executable, cargo / "build_script_build.exe")
            except OSError as error:
                self.skipTest(f"hardlink unavailable: {error}")

            validator.ROOT = temporary_root
            for iteration in range(24):
                with self.subTest(iteration=iteration):
                    self.assertEqual(validator.validate_no_developer_paths(), [])

    def test_repository_validator_accepts_stable_tree_directory_timestamp_drift(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            ordinary = temporary_root / "ordinary-directory"
            ordinary.mkdir()
            original_revalidate = validator._OrdinaryFileBinding.revalidate
            injected = False

            def drift_directory_timestamp(binding) -> None:
                nonlocal injected
                if not injected:
                    metadata = ordinary.stat()
                    os.utime(
                        ordinary,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
                    )
                    injected = True
                original_revalidate(binding)

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator._OrdinaryFileBinding,
                "revalidate",
                drift_directory_timestamp,
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(errors, [])

    def test_repository_validator_accepts_ancestor_timestamp_drift_inside_path_chain(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            ancestor = temporary_root / "ordinary-parent"
            ordinary = ancestor / "ordinary-directory"
            ordinary.mkdir(parents=True)
            ancestor_metadata = ancestor.stat()
            original_revalidate = validator._OrdinaryFileBinding.revalidate
            original_lstat = Path.lstat
            injected = False

            def drift_during_path_chain(path: Path):
                nonlocal injected
                metadata = original_lstat(path)
                if path.absolute() == ordinary.absolute() and not injected:
                    os.utime(
                        ancestor,
                        ns=(
                            ancestor_metadata.st_atime_ns,
                            ancestor_metadata.st_mtime_ns + 1_000_000,
                        ),
                    )
                    injected = True
                return metadata

            def revalidate_with_drift(binding) -> None:
                with mock.patch.object(Path, "lstat", drift_during_path_chain):
                    original_revalidate(binding)

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator._OrdinaryFileBinding,
                "revalidate",
                revalidate_with_drift,
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(errors, [])

    def test_repository_validator_rejects_ordinary_hardlink_alias_mutation(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            alias = temporary_root / "ordinary-alias.txt"
            target = temporary_root / "ordinary-hardlink.txt"
            hostile = b"/Users/" + b"a1-6/owned\n"
            alias.write_bytes(b"x" * (len(hostile) - 1) + b"\n")
            try:
                os.link(alias, target)
            except OSError as error:
                self.skipTest(f"hardlink unavailable: {error}")
            metadata = target.stat()
            original_reader = validator._read_bound_regular_file
            injected = False

            def mutate_alias_after_read(
                path: Path, maximum: int, *, require_single_link: bool = True
            ):
                nonlocal injected
                if require_single_link:
                    result = original_reader(path, maximum)
                else:
                    result = original_reader(
                        path, maximum, require_single_link=False
                    )
                if path.absolute() in {
                    alias.absolute(),
                    target.absolute(),
                } and not injected:
                    alias.write_bytes(hostile)
                    os.utime(
                        alias,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
                    )
                    injected = True
                return result

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator, "_read_bound_regular_file", mutate_alias_after_read
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(
                errors,
                ["Repository developer-path validation failed"],
            )

    def test_repository_validator_rejects_scanned_directory_replaced_by_external_symlink(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory, tempfile.TemporaryDirectory(
            prefix=".macwin-task5-external-", dir=ROOT
        ) as external_directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            ordinary = temporary_root / "ordinary-empty"
            ordinary.mkdir()
            external = Path(external_directory)
            (external / "hostile.txt").write_bytes(
                b"/Users/" + b"a1-6/external\n"
            )
            original_revalidate = validator._OrdinaryFileBinding.revalidate
            injected = False

            def replace_directory(binding) -> None:
                nonlocal injected
                if not injected:
                    ordinary.rmdir()
                    try:
                        ordinary.symlink_to(external, target_is_directory=True)
                    except OSError as error:
                        self.skipTest(f"directory symlink unavailable: {error}")
                    injected = True
                original_revalidate(binding)

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator._OrdinaryFileBinding,
                "revalidate",
                replace_directory,
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(
                errors,
                ["Repository developer-path validation failed"],
            )

    def test_repository_validator_rejects_late_child_in_scanned_directory(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            ordinary = temporary_root / "ordinary-directory"
            ordinary.mkdir()
            original_revalidate = validator._OrdinaryFileBinding.revalidate
            injected = False

            def add_late_child(binding) -> None:
                nonlocal injected
                if not injected:
                    (ordinary / "unreferenced.txt").write_bytes(
                        b"/Users/" + b"a1-6/late-child\n"
                    )
                    injected = True
                original_revalidate(binding)

            validator.ROOT = temporary_root
            with mock.patch.object(
                validator._OrdinaryFileBinding,
                "revalidate",
                add_late_child,
            ):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertEqual(
                errors,
                ["Repository developer-path validation failed"],
            )

    def test_repository_validator_rejects_scanned_child_deletion_and_type_change(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        for case in ("delete", "type-change"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=".macwin-task5-validator-", dir=ROOT
            ) as directory:
                temporary_root = Path(directory)
                self._copy_validator_fixture(temporary_root)
                ordinary = temporary_root / "ordinary-directory"
                ordinary.mkdir()
                child = ordinary / "child.txt"
                child.write_text("stable\n", encoding="utf-8", newline="\n")
                original_revalidate = validator._OrdinaryFileBinding.revalidate
                injected = False

                def mutate_child(binding) -> None:
                    nonlocal injected
                    if not injected:
                        child.unlink()
                        if case == "type-change":
                            child.mkdir()
                        injected = True
                    original_revalidate(binding)

                validator.ROOT = temporary_root
                with mock.patch.object(
                    validator._OrdinaryFileBinding,
                    "revalidate",
                    mutate_child,
                ):
                    errors = validator.validate_no_developer_paths()
                self.assertTrue(injected)
                self.assertEqual(
                    errors,
                    ["Repository developer-path validation failed"],
                )

    def test_repository_validator_rejects_task5_replacement_before_scan(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            target = temporary_root / "migration/macwin/generated/quarantine.json"
            raw = target.read_bytes()
            original_rglob = Path.rglob
            injected = False

            def replace_before_scan(path: Path, pattern: str):
                nonlocal injected
                if path == temporary_root and not injected:
                    injected = True
                    replaced = target.with_name("replaced-quarantine.json")
                    target.replace(replaced)
                    target.write_bytes(raw)
                return original_rglob(path, pattern)

            validator.ROOT = temporary_root
            with mock.patch.object(Path, "rglob", replace_before_scan):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertIn("Mac-Win generated evidence validation failed", errors)

    def test_repository_validator_revalidates_task5_evidence_after_skip(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            target = temporary_root / "migration/macwin/generated/quarantine.json"
            original_rglob = Path.rglob
            injected = False

            def mutate_after_skip(path: Path, pattern: str):
                nonlocal injected
                values = original_rglob(path, pattern)
                if path != temporary_root or injected:
                    yield from values
                    return
                for value in values:
                    yield value
                    if value == target:
                        raw = target.read_bytes()
                        target.write_bytes(raw[:-1] + b" \n")
                        injected = True

            validator.ROOT = temporary_root
            with mock.patch.object(Path, "rglob", mutate_after_skip):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertIn("Mac-Win generated evidence validation failed", errors)

    def test_repository_validator_rejects_a_linked_converter_parent(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory(
            prefix=".macwin-task5-validator-", dir=ROOT
        ) as directory:
            temporary_root = Path(directory)
            self._copy_validator_fixture(temporary_root)
            tools = temporary_root / "tools"
            external = temporary_root / "external-tools"
            tools.replace(external)
            try:
                tools.symlink_to(external, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlink unavailable: {error}")
            validator.ROOT = temporary_root
            errors = validator.validate_no_developer_paths()
            self.assertIn("Mac-Win generated evidence validation failed", errors)

    @staticmethod
    def _copy_validator_fixture(temporary_root: Path) -> None:
        source = temporary_root / "migration/macwin/source"
        source.parent.mkdir(parents=True)
        shutil.copytree(ROOT / "migration/macwin/source", source)
        generated = temporary_root / "migration/macwin/generated"
        generated.mkdir()
        for name in ("catalog.json", "index.json", "quarantine.json"):
            shutil.copyfile(ROOT / "migration/macwin/generated" / name, generated / name)
        mappings = generated / "mappings"
        mappings.mkdir()
        for name in ("patches.json", "bottle-schemas.json"):
            shutil.copyfile(
                ROOT / "migration/macwin/generated/mappings" / name,
                mappings / name,
            )
        tools = temporary_root / "tools"
        tools.mkdir()
        for name in (
            "convert_macwin_assets.py",
            "import_macwin_source_pack.py",
            "macwin_asset_common.py",
        ):
            shutil.copyfile(ROOT / "tools" / name, tools / name)

    def _recipe_asset(self, identifier: str):
        suffix = f"/recipes/{identifier}.json"
        return next(
            asset for asset in self.result.source_pack.assets if asset.source_path.endswith(suffix)
        )

    def _synthetic_reviewed_recipe_result(self, mutation=None):
        converter = self.converter
        source_pack = self.result.source_pack
        recipe_asset = self._recipe_asset("7zip")
        source = converter._parse_json_object(recipe_asset)
        source["license"] = "LGPL-2.1-or-later"
        source["tests"] = [
            {
                "expected": {"exitCode": 0},
                "id": "launch-smoke",
                "kind": "process-exit",
                "timeoutSeconds": 120,
            }
        ]
        asset_changes = {
            "development_dependencies": (),
            "external_refs": (),
            "license_status": "reviewed",
            "provenance_status": "reviewed",
        }
        if mutation is not None:
            changes = mutation(source, recipe_asset)
            if changes is not None:
                asset_changes.update(changes)
        recipe_raw = self.common.canonical_json_bytes(source)
        recipe_digest = hashlib.sha256(recipe_raw).hexdigest()
        replacement = dataclasses.replace(
            recipe_asset,
            raw=recipe_raw,
            byte_size=len(recipe_raw),
            sha256=recipe_digest,
            git_blob_oid=converter._git_blob_oid(recipe_raw),
            object_path=(
                f"objects/sha256/{recipe_digest[:2]}/{recipe_digest[2:]}"
            ),
            **asset_changes,
        )

        index_asset = self.assets[converter.CATALOG_INDEX_PATH]
        index = converter._parse_json_object(index_asset)
        index_entry = next(entry for entry in index["recipes"] if entry["id"] == "7zip")
        index_entry["sha256"] = recipe_digest
        index_raw = self.common.canonical_json_bytes(index)
        index_digest = hashlib.sha256(index_raw).hexdigest()
        index_replacement = dataclasses.replace(
            index_asset,
            raw=index_raw,
            byte_size=len(index_raw),
            sha256=index_digest,
            git_blob_oid=converter._git_blob_oid(index_raw),
            object_path=f"objects/sha256/{index_digest[:2]}/{index_digest[2:]}",
        )
        assets = tuple(
            replacement
            if asset.source_path == recipe_asset.source_path
            else index_replacement
            if asset.source_path == index_asset.source_path
            else asset
            for asset in source_pack.assets
        )
        return converter.classify_source_pack(
            dataclasses.replace(source_pack, assets=assets)
        )


class MacWinGeneratedGraphTests(unittest.TestCase):
    INDEX_PATH = "migration/macwin/generated/index.json"
    EXPECTED_LEAVES = {
        "migration/macwin/generated/catalog.json",
        "migration/macwin/generated/mappings/bottle-schemas.json",
        "migration/macwin/generated/mappings/patches.json",
        "migration/macwin/generated/quarantine.json",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.common = _load_macwin_asset_common()
        cls.result = cls.converter.build_conversion(ROOT)

    def test_root_index_seals_exact_real_source_and_output_coverage(self) -> None:
        documents = self.converter.render_documents(self.result)
        self.assertEqual(set(documents), self.EXPECTED_LEAVES | {self.INDEX_PATH})
        root = self._parse_root(documents)
        self.assertEqual(
            set(root),
            {
                "schemaVersion",
                "source",
                "recordCount",
                "categoryCounts",
                "statusCounts",
                "documentCount",
                "documents",
                "records",
            },
        )
        self.assertEqual(
            root["source"],
            {
                "repository": "a1112/Mac-Win",
                "sourceTag": "mw-migration-baseline-db12d5e",
                "sourceTagObject": "9f10d003382ce7ffbb269376c03477e17516302f",
                "sourceCommit": "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527",
                "inventoryCommit": "97f8423094d25325d8f864eb6f49a9e8628dbb93",
                "digestAlgorithm": "sha256",
            },
        )
        self.assertEqual(root["recordCount"], 90)
        self.assertEqual(
            root["categoryCounts"],
            {
                "bottleSchema": 4,
                "catalog": 19,
                "fixtures": 30,
                "patches": 11,
                "probes": 26,
            },
        )
        self.assertEqual(
            root["statusCounts"],
            {"converted": 2, "deferred": 15, "quarantined": 73},
        )
        self.assertEqual(root["documentCount"], 4)
        self.assertEqual(
            [entry["path"] for entry in root["documents"]],
            sorted(self.EXPECTED_LEAVES, key=lambda value: value.encode("ascii")),
        )
        self.assertEqual(
            [record["sourcePath"] for record in root["records"]],
            sorted(
                (asset.source_path for asset in self.result.source_pack.assets),
                key=lambda value: value.encode("ascii"),
            ),
        )
        self.converter.validate_generated_graph(documents, self.result.source_pack)

    def test_every_leaf_is_canonical_bounded_and_sealed_once(self) -> None:
        documents = self.converter.render_documents(self.result)
        root = self._parse_root(documents)
        entries = root["documents"]
        self.assertEqual(len(entries), len({entry["path"] for entry in entries}))
        for entry in entries:
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    set(entry), {"path", "kind", "byteSize", "sha256", "references"}
                )
                raw = documents[entry["path"]]
                self.assertLessEqual(len(raw), self.common.MAX_METADATA_BYTES)
                self.assertEqual(entry["byteSize"], len(raw))
                self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
                value = self.common.parse_json_bytes(raw, label="generated graph leaf")
                self.assertEqual(raw, self.common.canonical_json_bytes(value))
                self.assertEqual(
                    entry["references"],
                    sorted(set(entry["references"]), key=lambda value: value.encode("ascii")),
                )

    def test_every_source_identity_has_one_exact_provenanced_graph_record(self) -> None:
        documents = self.converter.render_documents(self.result)
        root = self._parse_root(documents)
        assets = {asset.source_path: asset for asset in self.result.source_pack.assets}
        records = root["records"]
        self.assertEqual(len(records), 90)
        self.assertEqual(len({record["sourcePath"] for record in records}), 90)
        for record in records:
            with self.subTest(source=record["sourcePath"]):
                self.assertEqual(
                    set(record),
                    {
                        "sourcePath",
                        "sourceCommit",
                        "sourceSha256",
                        "category",
                        "status",
                        "documentPath",
                    },
                )
                asset = assets[record["sourcePath"]]
                self.assertEqual(record["sourceCommit"], asset.source_commit)
                self.assertEqual(record["sourceSha256"], asset.sha256)
                self.assertEqual(record["category"], asset.category)
                self.assertIn(record["documentPath"], self.EXPECTED_LEAVES)

    def test_graph_rejects_missing_extra_reordered_modified_and_stale_seals(self) -> None:
        original = self.converter.render_documents(self.result)
        root = self._parse_root(original)
        catalog = "migration/macwin/generated/catalog.json"
        cases: dict[str, dict[str, bytes]] = {}
        cases["missing"] = {key: value for key, value in original.items() if key != catalog}
        cases["extra"] = {**original, "migration/macwin/generated/extra.json": b"{}\n"}
        reordered = copy.deepcopy(root)
        reordered["documents"] = list(reversed(reordered["documents"]))
        cases["reordered"] = {**original, self.INDEX_PATH: self.common.canonical_json_bytes(reordered)}
        cases["modified"] = {**original, catalog: original[catalog][:-2] + b" \n"}
        stale = copy.deepcopy(root)
        stale["documents"][0]["sha256"] = "0" * 64
        cases["stale"] = {**original, self.INDEX_PATH: self.common.canonical_json_bytes(stale)}
        unknown = copy.deepcopy(root)
        unknown["future"] = False
        cases["unknown"] = {**original, self.INDEX_PATH: self.common.canonical_json_bytes(unknown)}
        for name, documents in cases.items():
            with self.subTest(case=name), self.assertRaises(self.converter.ConversionError):
                self.converter.validate_generated_graph(documents, self.result.source_pack)

    def test_root_count_types_reject_canonical_float_and_boolean_mutants(self) -> None:
        original = self.converter.render_documents(self.result)
        paths = (
            ("recordCount",),
            ("documentCount",),
            ("categoryCounts", "catalog"),
            ("statusCounts", "quarantined"),
        )
        for path in paths:
            root_value = self._parse_root(original)
            target_value = root_value
            for component in path:
                target_value = target_value[component]
            for mutant_value in (float(target_value), True):
                with self.subTest(path=path, value=mutant_value):
                    root = copy.deepcopy(root_value)
                    target = root
                    for component in path[:-1]:
                        target = target[component]
                    target[path[-1]] = mutant_value
                    documents = {
                        **original,
                        self.INDEX_PATH: (
                            json.dumps(
                                root, ensure_ascii=False, indent=2, sort_keys=True
                            ).encode("utf-8")
                            + b"\n"
                        ),
                    }
                    with self.assertRaises(self.converter.ConversionError):
                        self.converter.validate_generated_graph(
                            documents, self.result.source_pack
                        )

    def test_dangling_duplicate_and_circular_references_reject(self) -> None:
        original = self.converter.render_documents(self.result)
        root = self._parse_root(original)
        paths = [entry["path"] for entry in root["documents"]]
        mutations = {}
        dangling = copy.deepcopy(root)
        dangling["documents"][0]["references"] = [
            "migration/macwin/generated/missing.json"
        ]
        mutations["dangling"] = dangling
        duplicate = copy.deepcopy(root)
        duplicate["documents"][0]["references"] = [paths[1], paths[1]]
        mutations["duplicate"] = duplicate
        circular = copy.deepcopy(root)
        circular["documents"][0]["references"] = [paths[1]]
        circular["documents"][1]["references"] = [paths[0]]
        mutations["circular"] = circular
        for name, mutant in mutations.items():
            documents = {
                **original,
                self.INDEX_PATH: self.common.canonical_json_bytes(mutant),
            }
            with self.subTest(case=name), self.assertRaises(self.converter.ConversionError):
                self.converter.validate_generated_graph(documents, self.result.source_pack)

    def test_self_consistent_resealed_semantic_forgery_rejects(self) -> None:
        original = self.converter.render_documents(self.result)
        quarantine_path = "migration/macwin/generated/quarantine.json"
        forged_quarantine = self.common.parse_json_bytes(
            original[quarantine_path], label="forged quarantine"
        )
        forged_quarantine["records"][0]["releaseCondition"] = "forged"
        forged_raw = self.common.canonical_json_bytes(forged_quarantine)
        root = self._parse_root(original)
        entry = next(item for item in root["documents"] if item["path"] == quarantine_path)
        entry["byteSize"] = len(forged_raw)
        entry["sha256"] = hashlib.sha256(forged_raw).hexdigest()
        documents = {
            **original,
            quarantine_path: forged_raw,
            self.INDEX_PATH: self.common.canonical_json_bytes(root),
        }
        with self.assertRaises(self.converter.ConversionError):
            self.converter.validate_generated_graph(documents, self.result.source_pack)

    def test_converted_recipe_catalog_digest_is_bound_to_the_recipe_leaf(self) -> None:
        helper = MacWinRecipeConversionTests(methodName="runTest")
        helper.converter = self.converter
        helper.common = self.common
        helper.result = self.result
        helper.assets = {
            asset.source_path: asset for asset in self.result.source_pack.assets
        }
        result = helper._synthetic_reviewed_recipe_result()
        original = self.converter.render_documents(result)
        catalog_path = "migration/macwin/generated/catalog.json"
        recipe_path = "migration/macwin/generated/recipes/7zip.json"
        cases = {}
        for name, mutation in {
            "wrong-digest": lambda entry: entry.update(recipeSha256="0" * 64),
            "wrong-path": lambda entry: entry.update(
                recipePath="migration/macwin/generated/recipes/missing.json"
            ),
            "missing-digest": lambda entry: entry.pop("recipeSha256"),
        }.items():
            catalog = self.common.parse_json_bytes(
                original[catalog_path], label="synthetic catalog"
            )
            converted = next(
                entry for entry in catalog["candidates"] if entry["status"] == "converted"
            )
            mutation(converted)
            catalog_raw = self.common.canonical_json_bytes(catalog)
            leaves = {
                path: raw
                for path, raw in original.items()
                if path != self.INDEX_PATH
            }
            leaves[catalog_path] = catalog_raw
            root = self.converter._render_generated_root_index(leaves, result)
            cases[name] = dict(
                sorted(
                    {
                        **leaves,
                        self.INDEX_PATH: self.common.canonical_json_bytes(root),
                    }.items(),
                    key=lambda item: item[0].encode("ascii"),
                )
            )
        self.assertIn(recipe_path, original)
        for name, documents in cases.items():
            with self.subTest(case=name), self.assertRaises(self.converter.ConversionError):
                self.converter.validate_generated_graph(documents, result.source_pack)

    def test_self_consistent_resealed_extra_document_rejects(self) -> None:
        original = self.converter.render_documents(self.result)
        cases = {
            "mapping": {
                "migration/macwin/generated/mappings/extra.json": b"{}\n"
            },
            "recipe": {
                "migration/macwin/generated/recipes/extra.json": b"{}\n"
            },
            "raw": {
                "migration/macwin/generated/probes/content/sha256/00/"
                + "0" * 62: b"extra"
            },
            "manifest-and-raw": {
                "migration/macwin/generated/probes/extra.json": (
                    b'{"contentPath":"migration/macwin/generated/probes/content/'
                    b'sha256/00/' + b'0' * 62
                    + b'","id":"extra","referencedAssetIds":[]}\n'
                ),
                "migration/macwin/generated/probes/content/sha256/00/"
                + "0" * 62: b"extra",
            },
        }
        for name, extras in cases.items():
            with self.subTest(case=name):
                leaves = {
                    path: raw
                    for path, raw in original.items()
                    if path != self.INDEX_PATH
                }
                leaves.update(extras)
                root = self.converter._render_generated_root_index(leaves, self.result)
                documents = dict(
                    sorted(
                        {
                            **leaves,
                            self.INDEX_PATH: self.common.canonical_json_bytes(root),
                        }.items(),
                        key=lambda item: item[0].encode("ascii"),
                    )
                )
                with self.assertRaises(self.converter.ConversionError):
                    self.converter.validate_generated_graph(
                        documents, self.result.source_pack
                    )

    def test_exhaustive_single_byte_drift_rejects_through_authenticated_seals(self) -> None:
        original = self.converter.render_documents(self.result)
        seal, _root = self.converter._authenticate_generated_graph_seal(
            original, self.result
        )
        mutations = 0
        for path, raw in original.items():
            self.assertTrue(path.endswith(".json"))
            for offset in range(len(raw)):
                mutant = bytearray(raw)
                mutant[offset] ^= 1
                documents = {**original, path: bytes(mutant)}
                with self.assertRaises(self.converter.ConversionError):
                    self.converter._validate_generated_graph_seal(documents, seal)
                mutations += 1
        self.assertEqual(mutations, sum(map(len, original.values())))

    def test_committed_generated_set_exactly_matches_renderer(self) -> None:
        documents = self.converter.render_documents(self.result)
        committed = {
            path.relative_to(ROOT).as_posix(): path.read_bytes()
            for path in (ROOT / "migration/macwin/generated").rglob("*")
            if path.is_file()
        }
        self.assertEqual(committed, documents)

    def _parse_root(self, documents: dict[str, bytes]) -> dict[str, object]:
        value = self.common.parse_json_bytes(
            documents[self.INDEX_PATH], label="generated root index"
        )
        self.assertIs(type(value), dict)
        self.assertEqual(documents[self.INDEX_PATH], self.common.canonical_json_bytes(value))
        return value


class MacWinMigrationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.result = cls.converter.build_conversion(ROOT)
        cls.documents = cls.converter.render_documents(cls.result)

    def test_default_and_check_compare_the_exact_generated_tree_read_only(self) -> None:
        before = {
            path: raw
            for path, raw in self.documents.items()
        }
        for arguments, expected_stdout in (
            ((), b'{"converted":2,"deferred":15,"documents":5,"quarantined":73,"records":90}\n'),
            (("--check",), b""),
        ):
            with self.subTest(arguments=arguments):
                completed = self._run_cli(*arguments)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, expected_stdout)
                self.assertEqual(completed.stderr, b"")
                self.assertEqual(
                    self.converter.read_generated_documents(ROOT), before
                )

    def test_default_summary_uses_the_dedicated_canonical_single_line_renderer(self) -> None:
        summary = {
            "records": 90,
            "quarantined": 73,
            "documents": 5,
            "converted": 2,
            "deferred": 15,
        }
        self.assertEqual(
            self.converter.render_summary(summary),
            b'{"converted":2,"deferred":15,"documents":5,"quarantined":73,"records":90}\n',
        )
        with self.assertRaises(self.converter.ConversionError):
            self.converter.render_summary({**summary, "future": 1})
        with self.assertRaises(self.converter.ConversionError):
            self.converter.render_summary({**summary, "records": True})

    def test_check_rejects_missing_extra_and_modified_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_documents(root, self.documents)
            self.converter.check_generated_documents(root, self.documents)
            catalog = root / "migration/macwin/generated/catalog.json"
            original = catalog.read_bytes()
            cases = {
                "missing": lambda: catalog.unlink(),
                "modified": lambda: catalog.write_bytes(original + b" "),
                "extra": lambda: (catalog.parent / "extra.json").write_bytes(b"{}\n"),
            }
            for name, mutate in cases.items():
                with self.subTest(case=name):
                    shutil.rmtree(root / "migration")
                    self._write_documents(root, self.documents)
                    mutate()
                    with self.assertRaises(self.converter.ConversionError):
                        self.converter.check_generated_documents(root, self.documents)

    def test_explain_accepts_source_and_output_ids_and_is_deterministic(self) -> None:
        source = "MacWinManager/Sources/MacWinManagerApp/Resources/Catalog/recipes/7zip.json"
        by_source = self.converter.explain_conversion(self.result, source)
        by_output = self.converter.explain_conversion(self.result, "7zip")
        self.assertEqual(by_source, by_output)
        self.assertLessEqual(len(by_source), 1024 * 1024)
        explanation = json.loads(by_source)
        self.assertEqual(explanation["schemaVersion"], "1")
        self.assertEqual(explanation["sourcePath"], source)
        self.assertEqual(explanation["status"], "quarantined")
        self.assertEqual(explanation["reason"], "missing-license")
        self.assertEqual(by_source, self.converter.explain_conversion(self.result, source))

    def test_explain_accepts_an_exact_unique_output_path_alias(self) -> None:
        helper = MacWinRecipeConversionTests(methodName="runTest")
        helper.converter = self.converter
        helper.common = _load_macwin_asset_common()
        helper.result = self.result
        helper.assets = {
            asset.source_path: asset for asset in self.result.source_pack.assets
        }
        result = helper._synthetic_reviewed_recipe_result()
        output = "migration/macwin/generated/recipes/7zip.json"
        explanation = json.loads(self.converter.explain_conversion(result, output))
        self.assertEqual(explanation["sourcePath"], "MacWinManager/Sources/MacWinManagerApp/Resources/Catalog/recipes/7zip.json")
        self.assertEqual(explanation["status"], "converted")

    def test_unknown_explain_identity_is_a_data_error_without_reflection(self) -> None:
        for hostile in ("\x1b[31mC:\\private\r\n", "\ud800"):
            with self.subTest(identity=repr(hostile)):
                with self.assertRaises(self.converter.ConversionError) as caught:
                    self.converter.explain_conversion(self.result, hostile)
                self.assertEqual(
                    str(caught.exception), "migration explanation identity is unknown"
                )
                self.assertNotIn("private", str(caught.exception))

    def test_unknown_abbreviated_and_hostile_argv_have_stable_usage(self) -> None:
        cases = (
            ("--ch",),
            ("--unknown",),
            ("\x1b[31mC:\\private\r\n",),
            ("--check", "extra"),
            ("--write", "--check"),
            ("--explain",),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                completed = self._run_cli(*arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, b"")
                self.assertEqual(
                    completed.stderr,
                    b"usage: convert_macwin_assets.py [--check | --write | --explain ID]\n",
                )
                self.assertNotIn(b"Traceback", completed.stderr)
                self.assertNotIn(b"private", completed.stderr)

    def test_generation_failure_is_one_bounded_line_and_only_conversion_errors_normalize(self) -> None:
        standard_output = io.StringIO()
        standard_error = io.StringIO()
        with mock.patch.object(
            self.converter, "build_conversion", side_effect=self.converter.ConversionError("hostile \x1b[31m private")
        ), contextlib.redirect_stdout(standard_output), contextlib.redirect_stderr(standard_error):
            self.assertEqual(self.converter.main(("--check",)), 1)
        self.assertEqual(standard_output.getvalue(), "")
        self.assertEqual(standard_error.getvalue(), "Mac-Win asset conversion failed.\n")

        with mock.patch.object(
            self.converter, "build_conversion", side_effect=OSError("programmer boundary")
        ), self.assertRaises(OSError):
            self.converter.main(("--check",))

        standard_output = io.StringIO()
        standard_error = io.StringIO()
        with mock.patch.object(
            self.converter, "write_generated_documents", side_effect=OSError("hostile write detail")
        ), contextlib.redirect_stdout(standard_output), contextlib.redirect_stderr(standard_error):
            self.assertEqual(self.converter.main(("--write",)), 1)
        self.assertEqual(standard_output.getvalue(), "")
        self.assertEqual(standard_error.getvalue(), "Mac-Win asset conversion failed.\n")

    def test_repository_validator_no_longer_skips_a_missing_converter(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            validator.ROOT = Path(directory)
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration converter path is not a regular file"],
            )

    @staticmethod
    def _write_documents(root: Path, documents: dict[str, bytes]) -> None:
        for relative, raw in documents.items():
            path = root / PurePosixPath(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    @staticmethod
    def _run_cli(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in IMPORT_PROBE_ENVIRONMENT_NAMES
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/convert_macwin_assets.py"), *arguments],
            cwd=ROOT,
            check=False,
            env=environment,
            executable=None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=120,
        )


class MacWinMigrationTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.result = cls.converter.build_conversion(ROOT)
        cls.documents = cls.converter.render_documents(cls.result)

    def test_write_is_exact_and_byte_identical_on_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "migration/macwin/generated").mkdir(parents=True)
            self.converter.write_generated_documents(root, self.documents)
            first = self.converter.read_generated_documents(root)
            self.assertEqual(first, self.documents)
            self.converter.write_generated_documents(root, self.documents)
            self.assertEqual(self.converter.read_generated_documents(root), first)
            self._assert_no_transaction_artifacts(root)

    def test_missing_generated_root_is_created_only_beneath_a_bound_parent_and_rolls_back(self) -> None:
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                parent = root / "migration/macwin"
                parent.mkdir(parents=True)
                if fail:
                    with mock.patch.object(
                        self.converter,
                        "_install_staged_leaf",
                        side_effect=OSError("first install failure"),
                    ), self.assertRaises(OSError):
                        self.converter.write_generated_documents(root, self.documents)
                    self.assertFalse((parent / "generated").exists())
                else:
                    self.converter.write_generated_documents(root, self.documents)
                    self.assertEqual(
                        self.converter.read_generated_documents(root), self.documents
                    )

    def test_missing_generated_root_is_removed_when_initial_scan_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "migration/macwin"
            parent.mkdir(parents=True)
            with mock.patch.object(
                self.converter,
                "_scan_generated_tree",
                side_effect=self.converter.ConversionError("injected initial scan failure"),
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertFalse((parent / "generated").exists())

    def test_new_transaction_binding_failure_removes_every_created_directory(self) -> None:
        for generated_exists in (True, False):
            with self.subTest(generated_exists=generated_exists), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                parent = root / "migration/macwin"
                parent.mkdir(parents=True)
                generated = parent / "generated"
                if generated_exists:
                    generated.mkdir()
                original = self.converter._hold_generated_directories

                def reject_transaction(paths):
                    if any(
                        path.name == ".compatforge-transaction" for path in paths
                    ):
                        raise self.converter.ConversionError(
                            "injected transaction binding failure"
                        )
                    return original(paths)

                with mock.patch.object(
                    self.converter,
                    "_hold_generated_directories",
                    side_effect=reject_transaction,
                ), self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertFalse(
                    (generated / ".compatforge-transaction").exists()
                )
                self.assertEqual(generated.exists(), generated_exists)

    def test_new_transaction_parent_revalidation_failure_removes_created_state(self) -> None:
        for generated_exists in (True, False):
            with self.subTest(generated_exists=generated_exists), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                parent = root / "migration/macwin"
                parent.mkdir(parents=True)
                generated = parent / "generated"
                if generated_exists:
                    generated.mkdir()
                original = self.converter._verify_held_generated_directories
                attacked = False

                def reject_after_create(held):
                    nonlocal attacked
                    if (
                        not attacked
                        and held[0].path.name == "generated"
                        and (generated / ".compatforge-transaction").exists()
                    ):
                        attacked = True
                        raise self.converter.ConversionError(
                            "injected parent revalidation failure"
                        )
                    return original(held)

                with mock.patch.object(
                    self.converter,
                    "_verify_held_generated_directories",
                    side_effect=reject_after_create,
                ), self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertTrue(attacked)
                self.assertFalse(
                    (generated / ".compatforge-transaction").exists()
                )
                self.assertEqual(generated.exists(), generated_exists)

    def test_new_generated_root_binding_failure_restores_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "migration/macwin"
            parent.mkdir(parents=True)
            original = self.converter._open_bound_child

            def reject_generated(parent_binding, name):
                if name == "generated":
                    raise self.converter.ConversionError(
                        "injected generated binding failure"
                    )
                return original(parent_binding, name)

            with mock.patch.object(
                self.converter,
                "_open_bound_child",
                side_effect=reject_generated,
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertFalse((parent / "generated").exists())

    def test_exact_repeat_is_a_true_noop_for_identity_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "migration/macwin/generated").mkdir(parents=True)
            self.converter.write_generated_documents(root, self.documents)
            before = self._metadata_snapshot(root)
            with mock.patch.object(
                self.converter, "_stage_transaction_leaf", wraps=self.converter._stage_transaction_leaf
            ) as stage, mock.patch.object(
                self.converter, "_install_staged_leaf", wraps=self.converter._install_staged_leaf
            ) as install:
                self.converter.write_generated_documents(root, self.documents)
            stage.assert_not_called()
            install.assert_not_called()
            self.assertEqual(self._metadata_snapshot(root), before)

    def test_success_removes_stale_and_builds_the_exact_nested_directory_set(self) -> None:
        documents = {
            "migration/macwin/generated/index.json": b"index\n",
            "migration/macwin/generated/probes/content/sha256/aa/" + "b" * 62: b"asset",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            (generated / "stale/empty").mkdir(parents=True)
            (generated / "stale.json").write_bytes(b"stale\n")
            self.converter.write_generated_documents(root, documents)
            self.assertEqual(self.converter.read_generated_documents(root), documents)
            self.assertEqual(
                self._directory_set(root),
                {
                    "migration/macwin/generated/probes",
                    "migration/macwin/generated/probes/content",
                    "migration/macwin/generated/probes/content/sha256",
                    "migration/macwin/generated/probes/content/sha256/aa",
                },
            )

    def test_check_rejects_extra_empty_directories_and_transaction_artifacts(self) -> None:
        for relative in ("extra/empty", ".compatforge-transaction"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                MacWinMigrationCliTests._write_documents(root, self.documents)
                (root / "migration/macwin/generated" / relative).mkdir(parents=True)
                with self.assertRaises(self.converter.ConversionError):
                    self.converter.check_generated_documents(root, self.documents)

    def test_scan_enforces_the_entry_limit_incrementally(self) -> None:
        consumed = 0

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            generated.mkdir(parents=True)

            entries = []
            for index in range(self.converter._MAX_GENERATED_ENTRIES):
                entry = type("Entry", (), {})()
                entry.name = f"entry-{index}"
                entry.path = str(generated / f"entry-{index}")
                entry.stat = mock.Mock(
                    return_value=type("Metadata", (), {"st_mode": stat.S_IFREG, "st_reparse_tag": 0})()
                )
                entries.append(entry)
            overflow = type("Entry", (), {})()
            overflow.name = "overflow"
            overflow.path = str(generated / "overflow")
            overflow.stat = mock.Mock(side_effect=AssertionError("overflow entry was inspected"))
            entries.append(overflow)

            def iter_entries():
                nonlocal consumed
                for entry in entries:
                    consumed += 1
                    yield entry

            with mock.patch.object(os, "scandir", return_value=iter_entries()), mock.patch.object(
                self.converter, "_read_generated_leaf", return_value=self.converter._GeneratedLeafBinding((0,0,0,1,0,0), b"")
            ), self.assertRaises(
                self.converter.ConversionError
            ):
                self.converter._scan_generated_tree(generated)
        self.assertEqual(consumed, self.converter._MAX_GENERATED_ENTRIES + 1)

    def test_scan_casefold_oracle_rejects_colliding_current_paths(self) -> None:
        with self.assertRaises(self.converter.ConversionError):
            self.converter._reject_generated_casefold_collisions(
                ("A.json", "a.json")
            )

    def test_scan_rejects_casefold_colliding_current_paths_on_case_sensitive_filesystem(self) -> None:
        if os.path.normcase("A") == os.path.normcase("a"):
            self.skipTest("case-colliding names cannot coexist on this filesystem")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            generated.mkdir(parents=True)
            (generated / "A.json").write_bytes(b"{}\n")
            (generated / "a.json").write_bytes(b"{}\n")
            with self.assertRaises(self.converter.ConversionError):
                self.converter.read_generated_documents(root)

    def test_output_map_rejects_case_collisions_reserved_paths_and_invalid_values_before_write(self) -> None:
        invalid = (
            {
                "migration/macwin/generated/A.json": b"{}\n",
                "migration/macwin/generated/a.json": b"{}\n",
            },
            {"migration/macwin/generated/.compatforge-transaction/new.json": b"{}\n"},
            {"migration/macwin/generated/../outside.json": b"{}\n"},
            {"migration/macwin/generated/value.json": bytearray(b"{}\n")},
            {"migration/macwin/generated/value.json": b"x" * (8 * 1024 * 1024 + 1)},
        )
        for documents in invalid:
            with self.subTest(paths=tuple(documents)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                generated = root / "migration/macwin/generated"
                generated.mkdir(parents=True)
                before = self._metadata_snapshot(root)
                with self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(root, documents)
                self.assertEqual(self._metadata_snapshot(root), before)

    def test_output_map_rejects_unrepresentable_depth_before_any_write(self) -> None:
        relative = "/".join(f"d{index}" for index in range(129))
        documents = {
            f"migration/macwin/generated/{relative}/value.json": b"{}\n"
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            generated.mkdir(parents=True)
            before = self._metadata_snapshot(root)
            with self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, documents)
            self.assertEqual(self._metadata_snapshot(root), before)

    def test_output_map_structural_depth_and_union_boundaries_are_exact(self) -> None:
        root = "migration/macwin/generated"
        maximum_depth = "/".join("d" for _ in range(128))
        self.converter._validate_output_document_map(
            {f"{root}/{maximum_depth}/value.json": b"{}\n"}
        )
        excessive_depth = "/".join("d" for _ in range(129))
        with self.assertRaises(self.converter.ConversionError):
            self.converter._validate_output_document_map(
                {f"{root}/{excessive_depth}/value.json": b"{}\n"}
            )
        maximum_union = {
            f"{root}/values/v{index}.json": b""
            for index in range(self.converter._MAX_GENERATED_ENTRIES - 1)
        }
        self.converter._validate_output_document_map(maximum_union)
        excessive_union = dict(maximum_union)
        excessive_union[f"{root}/values/overflow.json"] = b""
        with self.assertRaises(self.converter.ConversionError):
            self.converter._validate_output_document_map(excessive_union)

    def test_output_map_rejects_leaf_directory_and_union_case_collisions_prewrite(self) -> None:
        root_path = "migration/macwin/generated"
        invalid = (
            {
                f"{root_path}/A": b"leaf\n",
                f"{root_path}/A/x.json": b"child\n",
            },
            {
                f"{root_path}/A/x.json": b"one\n",
                f"{root_path}/a/y.json": b"two\n",
            },
            {
                f"{root_path}/a": b"leaf\n",
                f"{root_path}/A/x.json": b"child\n",
            },
        )
        for documents in invalid:
            with self.subTest(paths=tuple(documents)), tempfile.TemporaryDirectory() as directory:
                repository = Path(directory)
                generated = repository / root_path
                generated.mkdir(parents=True)
                (generated / "existing.json").write_bytes(b"existing\n")
                before = self._metadata_snapshot(repository)
                with mock.patch.object(
                    self.converter, "_bind_generated_root"
                ) as bind, mock.patch.object(
                    self.converter, "_stage_document_map"
                ) as stage, mock.patch.object(
                    self.converter, "_install_staged_leaf"
                ) as install, self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(repository, documents)
                bind.assert_not_called()
                stage.assert_not_called()
                install.assert_not_called()
                self.assertEqual(self._metadata_snapshot(repository), before)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor ownership contract")
    def test_open_bound_child_closes_descriptor_on_every_post_open_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent_path = Path(directory)
            (parent_path / "child").mkdir()
            parent_descriptor = os.open(parent_path, os.O_RDONLY | os.O_DIRECTORY)
            parent = self.converter._HeldGeneratedDirectory(
                parent_path,
                self.converter._generated_identity(os.fstat(parent_descriptor)),
                parent_descriptor,
            )
            try:
                before = len(os.listdir("/proc/self/fd"))
                with mock.patch.object(
                    self.converter.os,
                    "fstat",
                    side_effect=OSError("injected post-open failure"),
                ), self.assertRaises(self.converter.ConversionError):
                    self.converter._open_bound_child(parent, "child")
                self.assertEqual(len(os.listdir("/proc/self/fd")), before)
            finally:
                os.close(parent_descriptor)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor ownership contract")
    def test_posix_rename_closes_source_parent_when_destination_open_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_parent = root / "source"
            destination_parent = root / "destination"
            source_parent.mkdir()
            destination_parent.mkdir()
            (source_parent / "value").write_bytes(b"value")
            original_open = os.open
            calls = 0

            def fail_destination(path, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected destination parent open failure")
                return original_open(path, *args, **kwargs)

            before = len(os.listdir("/proc/self/fd"))
            with mock.patch.object(
                self.converter.os, "open", side_effect=fail_destination
            ), self.assertRaises(OSError):
                self.converter._posix_rename(
                    source_parent / "value",
                    destination_parent / "value",
                    exchange=False,
                )
            self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_every_install_failure_restores_the_exact_mixed_tree(self) -> None:
        initial = {
            path: b"old:" + raw
            for path, raw in self.documents.items()
            if not path.endswith("quarantine.json")
        }
        initial["migration/macwin/generated/stale.json"] = b"stale\n"
        expected_installs = len(self.documents)
        for failure_ordinal in range(1, expected_installs + 1):
            with self.subTest(failure=failure_ordinal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                MacWinMigrationCliTests._write_documents(root, initial)
                before_dirs = self._directory_set(root)
                calls = 0
                original = self.converter._install_staged_leaf

                def fail_at_ordinal(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == failure_ordinal:
                        raise OSError("injected destination failure")
                    return original(*args, **kwargs)

                with mock.patch.object(
                    self.converter, "_install_staged_leaf", side_effect=fail_at_ordinal
                ), self.assertRaises(OSError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertEqual(self._ordinary_documents(root), initial)
                self.assertEqual(self._directory_set(root), before_dirs)
                self._assert_no_transaction_artifacts(root)

    def test_base_exceptions_after_commit_restore_before_reraising(self) -> None:
        initial = {
            path: b"old:" + raw for path, raw in self.documents.items()
        }
        initial["migration/macwin/generated/stale.json"] = b"stale\n"
        for exception_type in (
            RuntimeError,
            self.converter.ConversionError,
            KeyboardInterrupt,
            SystemExit,
        ):
            with self.subTest(exception=exception_type.__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                MacWinMigrationCliTests._write_documents(root, initial)
                calls = 0
                original = self.converter._install_staged_leaf

                def fail_once(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise exception_type("injected post-commit failure")
                    return original(*args, **kwargs)

                with mock.patch.object(
                    self.converter, "_install_staged_leaf", side_effect=fail_once
                ), self.assertRaises(exception_type):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertEqual(self._ordinary_documents(root), initial)
                self._assert_no_transaction_artifacts(root)

    def test_every_stage_ordinal_failure_precedes_commit_and_leaves_no_artifacts(self) -> None:
        initial = {
            "migration/macwin/generated/index.json": b"old\n",
            "migration/macwin/generated/stale.json": b"stale\n",
        }
        expected_stages = len(self.documents) + len(initial)
        for failure_ordinal in range(1, expected_stages + 1):
            with self.subTest(failure=failure_ordinal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                MacWinMigrationCliTests._write_documents(root, initial)
                calls = 0
                original = self.converter._stage_transaction_leaf_bound

                def fail_once(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == failure_ordinal:
                        raise OSError("injected stage failure")
                    return original(*args, **kwargs)

                with mock.patch.object(
                    self.converter,
                    "_stage_transaction_leaf_bound",
                    side_effect=fail_once,
                ), mock.patch.object(
                    self.converter,
                    "_install_staged_leaf",
                    wraps=self.converter._install_staged_leaf,
                ) as install, self.assertRaises(OSError):
                    self.converter.write_generated_documents(root, self.documents)
                install.assert_not_called()
                self.assertEqual(self._ordinary_documents(root), initial)
                self._assert_no_transaction_artifacts(root)

    def test_all_new_and_rollback_leaves_are_staged_before_first_install(self) -> None:
        initial = {
            "migration/macwin/generated/index.json": b"old\n",
            "migration/macwin/generated/stale.json": b"stale\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MacWinMigrationCliTests._write_documents(root, initial)
            events: list[tuple[str, str]] = []
            original_stage = self.converter._stage_transaction_leaf_bound
            original_install = self.converter._install_staged_leaf

            def stage(parent, name, raw):
                binding = original_stage(parent, name, raw)
                events.append(("stage", (parent.path / name).as_posix()))
                return binding

            def install(*args, **kwargs):
                events.append(("install", args[1].as_posix()))
                return original_install(*args, **kwargs)

            with mock.patch.object(self.converter, "_stage_transaction_leaf_bound", side_effect=stage), mock.patch.object(
                self.converter, "_install_staged_leaf", side_effect=install
            ):
                self.converter.write_generated_documents(root, self.documents)
            first_install = next(index for index, event in enumerate(events) if event[0] == "install")
            staged_before = events[:first_install]
            self.assertEqual(len(staged_before), len(self.documents) + len(initial))
            self.assertTrue(all(event[0] == "stage" for event in staged_before))

    def test_install_failure_restores_complete_existing_and_absent_trees(self) -> None:
        old = {
            "migration/macwin/generated/index.json": b"old-index\n",
            "migration/macwin/generated/stale.json": b"old-stale\n",
        }
        for initial in (old, {}):
            with self.subTest(initial=bool(initial)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "migration/macwin/generated").mkdir(parents=True)
                MacWinMigrationCliTests._write_documents(root, initial)
                calls = 0
                original = self.converter._install_staged_leaf

                def fail_after_one(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise OSError("injected install failure")
                    return original(*args, **kwargs)

                with mock.patch.object(
                    self.converter, "_install_staged_leaf", side_effect=fail_after_one
                ), self.assertRaises(OSError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertEqual(self._ordinary_documents(root), initial)
                self._assert_no_transaction_artifacts(root)

    def test_hardlink_symlink_directory_and_linked_parent_reject_without_external_write(self) -> None:
        mutations = ("hardlink", "leaf-symlink", "leaf-directory", "parent-symlink")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                generated = root / "migration/macwin/generated"
                generated.mkdir(parents=True)
                outside = root / "outside.bin"
                outside.write_bytes(b"external sentinel")
                target = generated / "index.json"
                try:
                    if mutation == "hardlink":
                        os.link(outside, target)
                    elif mutation == "leaf-symlink":
                        target.symlink_to(outside)
                    elif mutation == "leaf-directory":
                        target.mkdir()
                    else:
                        saved = root / "saved-generated"
                        generated.rename(saved)
                        generated.symlink_to(saved, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"filesystem link primitive unavailable: {error}")
                with self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertEqual(outside.read_bytes(), b"external sentinel")

    def test_staged_substitution_and_destination_mutation_fail_closed_and_rollback(self) -> None:
        for attack in ("stage", "destination"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                initial = dict(self.documents)
                initial["migration/macwin/generated/catalog.json"] = b"old-catalog\n"
                MacWinMigrationCliTests._write_documents(root, initial)
                original_tree = self._ordinary_documents(root)
                original = self.converter._install_staged_leaf
                attacked = False

                def substitute(*args, **kwargs):
                    nonlocal attacked
                    if not attacked:
                        attacked = True
                        if attack == "stage":
                            staged = args[0]
                            staged.write_bytes(b"substituted stage")
                        else:
                            destination = args[1]
                            destination.write_bytes(b"substituted destination")
                    return original(*args, **kwargs)

                with mock.patch.object(
                    self.converter, "_install_staged_leaf", side_effect=substitute
                ), self.assertRaises(self.converter.ConversionError):
                    self.converter.write_generated_documents(root, self.documents)
                self.assertEqual(self._ordinary_documents(root), original_tree)
                self._assert_no_transaction_artifacts(root)

    def test_generated_root_replacement_before_install_fails_closed_without_external_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = dict(self.documents)
            initial["migration/macwin/generated/catalog.json"] = b"old-catalog\n"
            MacWinMigrationCliTests._write_documents(root, initial)
            generated = root / "migration/macwin/generated"
            saved = root / "saved-generated"
            external = root / "external"
            external.mkdir()
            sentinel = external / "sentinel.bin"
            sentinel.write_bytes(b"external sentinel")
            original = self.converter._install_staged_leaf
            attacked = False

            def replace_root(*args, **kwargs):
                nonlocal attacked
                if not attacked:
                    attacked = True
                    try:
                        generated.rename(saved)
                    except PermissionError:
                        raise self.converter.ConversionError(
                            "generated output directory replacement was blocked"
                        ) from None
                    try:
                        generated.symlink_to(external, target_is_directory=True)
                    except OSError as error:
                        saved.rename(generated)
                        self.skipTest(f"directory symlink unavailable: {error}")
                return original(*args, **kwargs)

            with mock.patch.object(
                self.converter, "_install_staged_leaf", side_effect=replace_root
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertEqual(sentinel.read_bytes(), b"external sentinel")

    def test_same_identity_destination_mutation_with_restored_mtime_rejects_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = dict(self.documents)
            initial["migration/macwin/generated/catalog.json"] = b"old-catalog\n"
            MacWinMigrationCliTests._write_documents(root, initial)
            destination = root / "migration/macwin/generated/catalog.json"
            original_tree = self._ordinary_documents(root)
            original = self.converter._install_staged_leaf
            attacked = False

            def mutate_same_inode(*args, **kwargs):
                nonlocal attacked
                if not attacked and args[1] == destination:
                    attacked = True
                    metadata = destination.stat()
                    with destination.open("r+b") as handle:
                        handle.seek(0)
                        handle.write(b"X")
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.utime(
                        destination,
                        ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
                    )
                return original(*args, **kwargs)

            with mock.patch.object(
                self.converter, "_install_staged_leaf", side_effect=mutate_same_inode
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertEqual(self._ordinary_documents(root), original_tree)

    def test_transaction_uses_platform_conditional_atomic_primitives(self) -> None:
        source = Path("source")
        destination = Path("destination")
        if os.name == "nt":
            with mock.patch.object(self.converter, "_MOVE_FILE", return_value=True) as move:
                self.converter._atomic_move_no_replace(source, destination)
            self.assertEqual(move.call_args.args[:2], (str(source), str(destination)))
            self.assertEqual(
                move.call_args.args[2], self.converter._MOVEFILE_WRITE_THROUGH
            )
        else:
            with mock.patch.object(self.converter, "_posix_rename") as rename:
                self.converter._atomic_move_no_replace(source, destination)
            rename.assert_called_once_with(
                source,
                destination,
                exchange=False,
                held_directories=None,
            )

    def test_stage_failure_occurs_before_any_destination_install_and_cleans_up(self) -> None:
        initial = {
            "migration/macwin/generated/index.json": b"old\n",
            "migration/macwin/generated/stale.json": b"stale\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MacWinMigrationCliTests._write_documents(root, initial)
            calls = 0
            original = self.converter._stage_transaction_leaf_bound

            def fail_during_rollback_stage(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == len(self.documents) + 1:
                    raise self.converter.ConversionError("injected stage failure")
                return original(*args, **kwargs)

            with mock.patch.object(
                self.converter,
                "_stage_transaction_leaf_bound",
                side_effect=fail_during_rollback_stage,
            ), mock.patch.object(
                self.converter, "_install_staged_leaf", wraps=self.converter._install_staged_leaf
            ) as install, self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            install.assert_not_called()
            self.assertEqual(self._ordinary_documents(root), initial)
            self._assert_no_transaction_artifacts(root)

    def test_final_verification_failure_retains_backups_and_restores_the_old_tree(self) -> None:
        initial = {"migration/macwin/generated/index.json": b"old\n"}
        replacement = {"migration/macwin/generated/index.json": b"new\n"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MacWinMigrationCliTests._write_documents(root, initial)
            calls = 0
            original = self.converter.check_generated_documents

            def fail_final(repository_root, expected, **options):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise self.converter.ConversionError(
                        "injected post-commit verification failure"
                    )
                return original(repository_root, expected, **options)

            with mock.patch.object(
                self.converter, "check_generated_documents", side_effect=fail_final
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, replacement)
            self.assertEqual(self._ordinary_documents(root), initial)
            self._assert_no_transaction_artifacts(root)

    def test_tampered_rollback_source_is_rejected_before_the_installed_tree_is_deleted(self) -> None:
        initial = {
            "migration/macwin/generated/index.json": b"old-index\n",
            "migration/macwin/generated/stale.json": b"old-stale\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MacWinMigrationCliTests._write_documents(root, initial)
            calls = 0
            original_install = self.converter._install_staged_leaf
            original_restore = self.converter._restore_generated_snapshot

            def fail_second_install(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected install failure")
                return original_install(*args, **kwargs)

            def tamper_before_restore(generated, transaction, rollback_root, *args):
                target = rollback_root / "index.json"
                target.write_bytes(b"tampered rollback\n")
                return original_restore(
                    generated, transaction, rollback_root, *args
                )

            with mock.patch.object(
                self.converter, "_install_staged_leaf", side_effect=fail_second_install
            ), mock.patch.object(
                self.converter,
                "_restore_generated_snapshot",
                side_effect=tamper_before_restore,
            ), self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            generated = root / "migration/macwin/generated"
            self.assertTrue((generated / "catalog.json").exists())
            self.assertTrue((generated / ".compatforge-transaction").exists())

    def test_rollback_source_mutation_after_preauth_restores_from_trusted_bytes(self) -> None:
        initial = {
            "migration/macwin/generated/index.json": b"old-index\n",
            "migration/macwin/generated/stale.json": b"old-stale\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MacWinMigrationCliTests._write_documents(root, initial)
            original_install = self.converter._install_staged_leaf
            install_calls = 0
            original_remove = self.converter._remove_entry_without_following
            original_remove_posix = self.converter._remove_child_posix
            attacked = False

            def fail_second_install(*args, **kwargs):
                nonlocal install_calls
                install_calls += 1
                if install_calls == 2:
                    raise OSError("injected install failure")
                return original_install(*args, **kwargs)

            def mutate_after_preauth(path, *args, **kwargs):
                nonlocal attacked
                rollback_leaf = (
                    root
                    / "migration/macwin/generated/.compatforge-transaction/rollback/index.json"
                )
                if not attacked and rollback_leaf.exists():
                    attacked = True
                    rollback_leaf.write_bytes(b"tampered-after-preauth\n")
                return original_remove(path, *args, **kwargs)

            def mutate_after_preauth_posix(*args, **kwargs):
                rollback_leaf = (
                    root
                    / "migration/macwin/generated/.compatforge-transaction/rollback/index.json"
                )
                nonlocal attacked
                if not attacked and rollback_leaf.exists():
                    attacked = True
                    rollback_leaf.write_bytes(b"tampered-after-preauth\n")
                return original_remove_posix(*args, **kwargs)

            with mock.patch.object(
                self.converter,
                "_install_staged_leaf",
                side_effect=fail_second_install,
            ), mock.patch.object(
                self.converter,
                "_remove_entry_without_following",
                side_effect=mutate_after_preauth,
            ), mock.patch.object(
                self.converter,
                "_remove_child_posix",
                side_effect=mutate_after_preauth_posix,
            ), self.assertRaises(OSError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertTrue(attacked)
            self.assertEqual(self._ordinary_documents(root), initial)
            self._assert_no_transaction_artifacts(root)

    def test_cleanup_directory_swap_never_deletes_an_external_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owned = root / "owned"
            owned.mkdir()
            (owned / "owned.bin").write_bytes(b"owned")
            saved = root / "saved-owned"
            external = root / "outside"
            external.mkdir()
            sentinel = external / "sentinel.bin"
            sentinel.write_bytes(b"external")
            original_scandir = os.scandir
            attacked = False

            def swap_before_enumeration(path):
                nonlocal attacked
                is_target = (
                    os.name == "nt" and Path(path) == owned
                ) or (os.name != "nt" and isinstance(path, int))
                if not attacked and is_target:
                    attacked = True
                    owned.rename(saved)
                    owned.symlink_to(external, target_is_directory=True)
                return original_scandir(path)

            with mock.patch.object(os, "scandir", side_effect=swap_before_enumeration):
                with self.assertRaises(self.converter.ConversionError):
                    self.converter._remove_entry_without_following(owned)
            self.assertEqual(sentinel.read_bytes(), b"external")

    def test_parent_swap_before_generated_root_creation_never_writes_outside(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "migration/macwin"
            parent.mkdir(parents=True)
            saved = root / "saved-macwin"
            external = root / "outside"
            external.mkdir()
            generated = parent / "generated"
            attacked = False
            if os.name == "nt":
                original_mkdir = Path.mkdir

                def swap_parent(path, *args, **kwargs):
                    nonlocal attacked
                    if not attacked and path == generated:
                        attacked = True
                        parent.rename(saved)
                        parent.symlink_to(external, target_is_directory=True)
                    return original_mkdir(path, *args, **kwargs)

                patcher = mock.patch.object(Path, "mkdir", new=swap_parent)
            else:
                original_mkdir = os.mkdir

                def swap_parent(path, *args, **kwargs):
                    nonlocal attacked
                    if not attacked and path == "generated":
                        attacked = True
                        parent.rename(saved)
                        parent.symlink_to(external, target_is_directory=True)
                    return original_mkdir(path, *args, **kwargs)

                patcher = mock.patch.object(os, "mkdir", side_effect=swap_parent)
            with patcher, self.assertRaises(self.converter.ConversionError):
                self.converter.write_generated_documents(root, self.documents)
            self.assertTrue(attacked)
            self.assertFalse((external / "generated").exists())

    def test_same_byte_new_inode_substitution_during_atomic_replace_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            transaction = generated / ".compatforge-transaction"
            staged = transaction / "new/index.json"
            displaced = transaction / "displaced/index.json"
            destination = generated / "index.json"
            staged.parent.mkdir(parents=True)
            displaced.parent.mkdir(parents=True)
            destination.write_bytes(b"old\n")
            staged.write_bytes(b"new\n")
            expected_stage = self.converter._read_generated_leaf(staged)
            expected_destination = self.converter._read_generated_leaf(destination)
            original = self.converter._atomic_replace_with_displaced

            def substitute_destination(source, target, backup, held=None):
                replacement = target.with_suffix(".replacement")
                replacement.write_bytes(expected_destination.raw)
                os.replace(replacement, target)
                return original(source, target, backup, held)

            with mock.patch.object(
                self.converter,
                "_atomic_replace_with_displaced",
                side_effect=substitute_destination,
            ), self.assertRaises(self.converter.ConversionError):
                self.converter._install_staged_leaf(
                    staged,
                    destination,
                    expected_stage,
                    expected_destination,
                )

    @staticmethod
    def _ordinary_documents(root: Path) -> dict[str, bytes]:
        documents, _directories, _metadata = (
            MacWinMigrationTransactionTests._exact_tree_oracle(root)
        )
        return documents

    @staticmethod
    def _exact_tree_oracle(
        root: Path,
    ) -> tuple[
        dict[str, bytes],
        set[str],
        dict[str, tuple[int, int, int, int, int, int]],
    ]:
        generated = root / "migration/macwin/generated"
        try:
            root_metadata = generated.lstat()
        except FileNotFoundError:
            return {}, set(), {}
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(root_metadata.st_mode)
            or getattr(root_metadata, "st_reparse_tag", 0)
        ):
            raise AssertionError("generated oracle root is unsafe")
        documents: dict[str, bytes] = {}
        directories: set[str] = set()
        metadata_snapshot: dict[
            str, tuple[int, int, int, int, int, int]
        ] = {}
        pending = [generated]
        while pending:
            directory = pending.pop()
            before = directory.lstat()
            relative_directory = directory.relative_to(root).as_posix()
            metadata_snapshot[relative_directory] = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_nlink,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    entry_metadata = path.lstat()
                    relative = path.relative_to(root).as_posix()
                    if stat.S_ISLNK(entry_metadata.st_mode) or getattr(
                        entry_metadata, "st_reparse_tag", 0
                    ):
                        raise AssertionError("generated oracle encountered a link")
                    identity = (
                        entry_metadata.st_dev,
                        entry_metadata.st_ino,
                        entry_metadata.st_size,
                        entry_metadata.st_nlink,
                        entry_metadata.st_mtime_ns,
                        entry_metadata.st_ctime_ns,
                    )
                    metadata_snapshot[relative] = identity
                    if stat.S_ISDIR(entry_metadata.st_mode):
                        directories.add(relative)
                        pending.append(path)
                        continue
                    if not stat.S_ISREG(entry_metadata.st_mode) or entry_metadata.st_nlink != 1:
                        raise AssertionError("generated oracle encountered a nonregular leaf")
                    descriptor = os.open(
                        path,
                        os.O_RDONLY
                        | getattr(os, "O_BINARY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        opened = os.fstat(descriptor)
                        raw_parts: list[bytes] = []
                        while True:
                            chunk = os.read(descriptor, 64 * 1024)
                            if not chunk:
                                break
                            raw_parts.append(chunk)
                        final = os.fstat(descriptor)
                    finally:
                        os.close(descriptor)
                    after = path.lstat()
                    after_identity = (
                        after.st_dev,
                        after.st_ino,
                        after.st_size,
                        after.st_nlink,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    )
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_nlink != 1
                        or opened.st_size != entry_metadata.st_size
                        or (
                            final.st_dev,
                            final.st_ino,
                            final.st_size,
                            final.st_nlink,
                            final.st_mtime_ns,
                            final.st_ctime_ns,
                        )
                        != (
                            opened.st_dev,
                            opened.st_ino,
                            opened.st_size,
                            opened.st_nlink,
                            opened.st_mtime_ns,
                            opened.st_ctime_ns,
                        )
                        or after_identity != identity
                    ):
                        raise AssertionError("generated oracle leaf identity changed")
                    documents[relative] = b"".join(raw_parts)
            after_directory = directory.lstat()
            if (after_directory.st_dev, after_directory.st_ino) != (
                before.st_dev,
                before.st_ino,
            ):
                raise AssertionError("generated oracle directory identity changed")
        return documents, directories, metadata_snapshot

    def _assert_no_transaction_artifacts(self, root: Path) -> None:
        documents, directories, _metadata = self._exact_tree_oracle(root)
        self.assertFalse(
            any(
                ".compatforge-transaction" in PurePosixPath(path).parts
                for path in (*documents, *directories)
            )
        )

    @staticmethod
    def _directory_set(root: Path) -> set[str]:
        _documents, directories, _metadata = (
            MacWinMigrationTransactionTests._exact_tree_oracle(root)
        )
        return directories

    @staticmethod
    def _metadata_snapshot(root: Path) -> dict[str, tuple[int, int, int, int, int, int]]:
        _documents, _directories, metadata = (
            MacWinMigrationTransactionTests._exact_tree_oracle(root)
        )
        return metadata


class MigrationLayoutTests(unittest.TestCase):
    APPROVED_LAYOUT = (
        "migration/macwin/source/index.json",
        "migration/macwin/source/objects/sha256/ab/cdef",
        "migration/macwin/generated/index.json",
        "migration/macwin/generated/catalog.json",
        "migration/macwin/generated/recipes/example.json",
        "migration/macwin/generated/probes/example.json",
        "migration/macwin/generated/fixtures/example.json",
        "migration/macwin/generated/mappings/patches.json",
        "migration/macwin/generated/mappings/bottle-schemas.json",
        "migration/macwin/generated/quarantine.json",
        "schemas/macwin-source-pack.schema.json",
        "schemas/migration-record.schema.json",
        "schemas/quarantine.schema.json",
        "schemas/portable-probe.schema.json",
        "schemas/portable-fixture.schema.json",
        "tools/import_macwin_source_pack.py",
        "tools/convert_macwin_assets.py",
        "tests/test_macwin_asset_migration.py",
    )

    def test_approved_layout_uses_repository_relative_posix_paths(self) -> None:
        for value in self.APPROVED_LAYOUT:
            with self.subTest(path=value):
                path = PurePosixPath(value)
                self.assertEqual(path.as_posix(), value)
                self.assertFalse(path.is_absolute())
                self.assertFalse(PureWindowsPath(value).is_absolute())
                self.assertNotIn("\\", value)
                self.assertTrue(path.parts)
                self.assertNotIn("..", path.parts)

    def test_json_contracts_are_lf_pinned_by_repository_attributes(self) -> None:
        self._git(ROOT, "ls-files", "--error-unmatch", ".gitattributes")
        attributes = self._git_bytes(ROOT, "show", "HEAD:.gitattributes")
        self.assertNotIn(b"\r", attributes)
        self.assertEqual(
            attributes.count(b"/migration/macwin/**/*.json text eol=lf\n"),
            1,
        )
        self.assertEqual(
            attributes.count(b"/schemas/macwin-*.schema.json text eol=lf\n"),
            1,
        )
        self.assertEqual(
            attributes.count(
                b"/migration/macwin/source/objects/sha256/** binary\n"
            ),
            1,
        )

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / ".gitattributes").write_bytes(attributes)
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.name", "Migration Contract Test")
            self._git(repository, "config", "user.email", "migration@example.invalid")
            self._git(repository, "config", "core.autocrlf", "true")
            self._git(repository, "add", ".gitattributes")
            self._git(repository, "commit", "--quiet", "-m", "attributes")
            self.assertEqual(
                self._git_bytes(repository, "show", "HEAD:.gitattributes"),
                attributes,
            )

            samples = (
                "migration/macwin/source/index.json",
                "migration/macwin/generated/mappings/patches.json",
                "schemas/macwin-source-pack.schema.json",
            )
            for value in samples:
                path = repository / PurePosixPath(value)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'{\r\n  "schemaVersion": "1"\r\n}\r\n')

            self._git(repository, "add", *samples)
            for value in samples:
                with self.subTest(path=value):
                    self.assertEqual(
                        self._git(repository, "check-attr", "--cached", "eol", "--", value),
                        f"{value}: eol: lf",
                    )
                    blob = self._git_bytes(repository, "show", f":{value}")
                    self.assertIn(b"\n", blob)
                    self.assertNotIn(b"\r", blob)

    def test_git_helpers_ignore_ambient_directories_and_numbered_signing(self) -> None:
        scenarios = (
            (
                "repository redirection",
                {
                    "GIT_DIR": "hostile.git",
                    "GIT_WORK_TREE": "hostile-work-tree",
                },
                ("status", "--short"),
            ),
            (
                "numbered signing configuration",
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "commit.gpgSign",
                    "GIT_CONFIG_VALUE_0": "true",
                },
                ("commit", "--quiet", "-m", "ambient configuration ignored"),
            ),
        )
        for name, environment, action in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                repository = Path(directory)
                self._prepare_staged_git_repository(repository)
                with mock.patch.dict(os.environ, environment, clear=False):
                    try:
                        self._git(repository, *action)
                    except subprocess.CalledProcessError as error:
                        self.fail(
                            f"Git helper inherited {name}: exit {error.returncode}"
                        )

    def test_git_helpers_disable_ambient_templates_and_config_includes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            template = root / "template"
            hooks = template / "hooks"
            hooks.mkdir(parents=True)
            hook = hooks / "pre-commit"
            hook.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8", newline="\n")
            hook.chmod(0o755)

            included = root / "included.config"
            included.write_text(
                "[commit]\n\tgpgSign = true\n", encoding="utf-8", newline="\n"
            )
            global_config = root / "global.config"
            global_config.write_text(
                f"[include]\n\tpath = {included.as_posix()}\n",
                encoding="utf-8",
                newline="\n",
            )
            hostile_environment = {
                "GIT_CONFIG_GLOBAL": str(global_config),
                "GIT_CONFIG_NOSYSTEM": "0",
                "GIT_CONFIG_SYSTEM": str(global_config),
                "GIT_TEMPLATE_DIR": str(template),
            }
            with mock.patch.dict(os.environ, hostile_environment, clear=False):
                try:
                    self._git(repository, "init", "--quiet")
                    self._git(repository, "config", "user.name", "Migration Test")
                    self._git(
                        repository,
                        "config",
                        "user.email",
                        "migration@example.invalid",
                    )
                    tracked = repository / "tracked.txt"
                    tracked.write_text("contract\n", encoding="utf-8", newline="\n")
                    self._git(repository, "add", "tracked.txt")
                    self._git(repository, "commit", "--quiet", "-m", "contract")
                except subprocess.CalledProcessError as error:
                    self.fail(
                        "Git helper inherited templates or included configuration: "
                        f"exit {error.returncode}"
                    )

            self.assertFalse((repository / ".git/hooks/pre-commit").exists())

    def test_git_helpers_allow_only_the_exact_repository_ownership_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            self._prepare_staged_git_repository(repository)
            try:
                result = self._git(
                    repository,
                    "status",
                    "--short",
                    assume_different_owner=True,
                )
            except (subprocess.CalledProcessError, TypeError) as error:
                self.fail(f"exact safe.directory ownership probe failed: {error}")
            self.assertEqual(result, "A  tracked.txt")

    def test_git_helpers_lock_the_subprocess_boundary(self) -> None:
        repository = ROOT.resolve()
        hostile_environment = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "hostile-hooks",
            "gIt_DiR": "mixed-case-hostile.git",
        }
        safe_git_environment = {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
        expected_prefix = [
            "git",
            "--no-replace-objects",
            "-c",
            f"safe.directory={repository}",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "tag.gpgSign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
        ]

        with mock.patch.dict(os.environ, hostile_environment, clear=False):
            for helper, output in ((self._git, ""), (self._git_bytes, b"")):
                with self.subTest(helper=helper.__name__), mock.patch.object(
                    subprocess, "run"
                ) as run:
                    run.return_value.stdout = output
                    helper(repository, "status", "--short")

                    command = run.call_args.args[0]
                    options = run.call_args.kwargs
                    self.assertEqual(command, [*expected_prefix, "status", "--short"])
                    self.assertEqual(
                        {
                            key: value
                            for key, value in options["env"].items()
                            if key.upper().startswith("GIT_")
                        },
                        safe_git_environment,
                    )
                    self.assertEqual(options["env"].get("PATH"), os.environ.get("PATH"))
                    self.assertIs(options["stdin"], subprocess.DEVNULL)
                    self.assertEqual(options["timeout"], 30)
                    self.assertFalse(options["shell"])
                    self.assertIsNone(options["executable"])

    def test_git_helpers_ignore_replace_refs_for_committed_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.name", "Migration Contract Test")
            self._git(
                repository,
                "config",
                "user.email",
                "migration@example.invalid",
            )
            attributes = repository / ".gitattributes"
            original = b"tests/fixtures/*.exe binary\n"
            replacement = original + (
                b"/migration/macwin/**/*.json text eol=lf\n"
                b"/schemas/macwin-*.schema.json text eol=lf\n"
            )
            attributes.write_bytes(original)
            self._git(repository, "add", ".gitattributes")
            self._git(repository, "commit", "--quiet", "-m", "original attributes")
            original_commit = self._git(repository, "rev-parse", "HEAD")

            attributes.write_bytes(replacement)
            self._git(repository, "add", ".gitattributes")
            replacement_tree = self._git(repository, "write-tree")
            replacement_commit = self._git(
                repository,
                "commit-tree",
                replacement_tree,
                "-m",
                "replacement attributes",
            )
            self._git(
                repository,
                "update-ref",
                f"refs/replace/{original_commit}",
                replacement_commit,
            )
            self.assertEqual(
                self._git(repository, "rev-parse", f"refs/replace/{original_commit}"),
                replacement_commit,
            )
            self.assertEqual(
                self._git_bytes(repository, "show", "HEAD:.gitattributes"),
                original,
            )

    def test_migration_python_imports_leave_no_repository_bytecode(self) -> None:
        before = self._repository_bytecode()
        self.assertEqual(before, set())

        modules = (
            ROOT / "scripts/validate_repository.py",
            ROOT / "tools/import_macwin_source_pack.py",
            ROOT / "tools/convert_macwin_assets.py",
        )
        for module in modules:
            if not module.is_file():
                continue
            with self.subTest(module=module.relative_to(ROOT).as_posix()):
                self._run_migration_import_probe(module)

        self.assertEqual(self._repository_bytecode(), before)

    def test_official_repository_validator_entry_leaves_no_bytecode(self) -> None:
        before = self._repository_bytecode()
        self.assertEqual(before, set())
        environment = dict(os.environ)
        for name in (
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONPYCACHEPREFIX",
        ):
            environment.pop(name, None)

        try:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/validate_repository.py")],
                cwd=ROOT,
                check=False,
                env=environment,
                executable=None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
            )
            after = self._repository_bytecode()
        finally:
            for relative in sorted(
                self._repository_bytecode() - before,
                key=lambda value: len(Path(value).parts),
                reverse=True,
            ):
                path = ROOT / PurePosixPath(relative)
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(after, before)

    def test_migration_import_probe_ignores_python_environment_injection(self) -> None:
        module = ROOT / "scripts/validate_repository.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hostile_modules = root / "hostile-modules"
            hostile_modules.mkdir()
            (hostile_modules / "hashlib.py").write_text(
                "raise RuntimeError('hostile PYTHONPATH imported')\n",
                encoding="utf-8",
                newline="\n",
            )
            scenarios = (
                ("PYTHONPATH", str(hostile_modules)),
                ("PYTHONHOME", str(root / "hostile-python-home")),
            )
            for key, value in scenarios:
                with self.subTest(variable=key), mock.patch.dict(
                    os.environ, {key: value}, clear=False
                ):
                    try:
                        self._run_migration_import_probe(module)
                    except subprocess.CalledProcessError as error:
                        self.fail(
                            f"migration import probe inherited {key}: "
                            f"exit {error.returncode}"
                        )

    def test_migration_import_probe_locks_the_subprocess_boundary(self) -> None:
        module = ROOT / "scripts/validate_repository.py"
        hostile_environment = {
            "PYTHONHOME": "hostile-python-home",
            "PYTHONINSPECT": "1",
            "PYTHONPATH": "hostile-python-path",
            "PYTHONSTARTUP": "hostile-startup.py",
        }
        allowed_names = {
            "COMSPEC",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "TMPDIR",
            "WINDIR",
        }
        with mock.patch.dict(os.environ, hostile_environment, clear=False), mock.patch.object(
            subprocess, "run"
        ) as run:
            self._run_migration_import_probe(module)

        command = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(
            command,
            [
                sys.executable,
                "-B",
                "-c",
                "import runpy, sys; runpy.run_path(sys.argv[1], "
                "run_name='migration_import_contract')",
                str(module),
            ],
        )
        expected_environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in allowed_names
        }
        expected_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        self.assertEqual(options["env"], expected_environment)
        self.assertEqual(options["cwd"], ROOT)
        self.assertIs(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stdout"], subprocess.DEVNULL)
        self.assertIs(options["stderr"], subprocess.DEVNULL)
        self.assertEqual(options["timeout"], IMPORT_PROBE_TIMEOUT_SECONDS)
        self.assertTrue(options["check"])
        self.assertFalse(options["shell"])
        self.assertIsNone(options["executable"])

    def test_repository_validation_requires_the_converter(self) -> None:
        validator = self._load_repository_validator()
        self.assertTrue(
            hasattr(validator, "validate_macwin_asset_migration"),
            "repository validator is missing the temporary migration-check hook",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator.ROOT = root
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration converter path is not a regular file"],
            )

            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text(
                "import sys\n"
                "print('intentional converter failure', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
                newline="\n",
            )
            errors = validator.validate_macwin_asset_migration()
            self.assertEqual(
                errors,
                ["Mac-Win asset migration check failed with exit 7"],
            )

    def test_repository_validation_locks_converter_process_boundary(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text("raise SystemExit(0)\n", encoding="utf-8", newline="\n")
            validator.ROOT = root

            hostile_environment = {
                "AWS_SECRET_ACCESS_KEY": "must-not-cross-boundary",
                "GIT_CONFIG_COUNT": "1",
                "HTTP_PROXY": "http://must-not-cross-boundary.invalid",
                "PYTHONPATH": "must-not-cross-boundary",
            }
            allowed_names = {
                "COMSPEC",
                "PATH",
                "PATHEXT",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
                "TMPDIR",
                "WINDIR",
            }
            with mock.patch.dict(os.environ, hostile_environment, clear=False), mock.patch.object(
                subprocess, "run"
            ) as run:
                run.return_value.returncode = 0
                self.assertEqual(validator.validate_macwin_asset_migration(), [])

            command = run.call_args.args[0]
            options = run.call_args.kwargs
            self.assertEqual(
                command,
                [
                    sys.executable,
                    "-B",
                    "-c",
                    validator.MIGRATION_CONVERTER_BOOTSTRAP,
                    str(converter),
                    "--check",
                ],
            )
            expected_environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in allowed_names
            }
            expected_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            self.assertEqual(options["env"], expected_environment)
            self.assertEqual(options["cwd"], root)
            self.assertEqual(
                options["input"], b"raise SystemExit(0)\n"
            )
            self.assertNotIn("stdin", options)
            self.assertIs(options["stdout"], subprocess.DEVNULL)
            self.assertIs(options["stderr"], subprocess.DEVNULL)
            self.assertEqual(options["timeout"], 120)
            self.assertFalse(options["check"])
            self.assertFalse(options["shell"])
            self.assertIsNone(options["executable"])

    def test_repository_validation_bounds_converter_runtime(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text(
                "import time\ntime.sleep(0.2)\n",
                encoding="utf-8",
                newline="\n",
            )
            validator.ROOT = root
            validator.MIGRATION_CHECK_TIMEOUT_SECONDS = 0.01
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration check timed out"],
            )

    def test_repository_validation_stabilizes_converter_launch_failures(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text("raise SystemExit(0)\n", encoding="utf-8", newline="\n")
            validator.ROOT = root

            with mock.patch.object(
                subprocess, "run", side_effect=OSError("hostile launch detail")
            ):
                try:
                    errors = validator.validate_macwin_asset_migration()
                except OSError as error:
                    self.fail(f"converter launch exception escaped: {error}")
            self.assertEqual(
                errors,
                ["Mac-Win asset migration check could not start"],
            )

    def test_repository_validation_never_reflects_converter_output(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text(
                "import os\n"
                "os.write(2, bytes([255, 254, 27]) + "
                "b'[31m hostile\\r\\nC:\\\\private')\n"
                "raise SystemExit(9)\n",
                encoding="utf-8",
                newline="\n",
            )
            validator.ROOT = root
            try:
                errors = validator.validate_macwin_asset_migration()
            except (AttributeError, UnicodeDecodeError) as error:
                self.fail(f"converter output destabilized validation: {error}")
            self.assertEqual(
                errors,
                ["Mac-Win asset migration check failed with exit 9"],
            )

    def test_repository_validation_rejects_a_dangling_converter_link(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            os.symlink(root / "missing-converter.py", converter)
            self.assertTrue(os.path.lexists(converter))
            self.assertFalse(converter.exists())

            validator.ROOT = root
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration converter path is not a regular file"],
            )

    def test_repository_validation_rejects_a_linked_tools_parent_without_execution(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside_directory:
            root = Path(directory)
            outside = Path(outside_directory)
            marker = outside / "executed.txt"
            converter = outside / "convert_macwin_assets.py"
            converter.write_text(
                "import pathlib\n"
                f"pathlib.Path({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
                newline="\n",
            )
            try:
                (root / "tools").symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlink unavailable: {error}")
            validator.ROOT = root
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration converter path is not a regular file"],
            )
            self.assertFalse(marker.exists())

    def test_repository_validation_executes_only_authenticated_converter_bytes(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.parent.mkdir(parents=True)
            converter.write_text("raise SystemExit(0)\n", encoding="utf-8", newline="\n")
            marker = root / "untrusted-executed.txt"
            original_read = validator._read_bound_converter
            attacked = False

            def substitute_after_read(*args, **options):
                nonlocal attacked
                result = original_read(*args, **options)
                replacement = converter.with_suffix(".replacement")
                replacement.write_text(
                    "from pathlib import Path\n"
                    f"Path({str(marker)!r}).write_text('executed')\n"
                    "raise SystemExit(0)\n",
                    encoding="utf-8",
                    newline="\n",
                )
                os.replace(replacement, converter)
                attacked = True
                return result

            validator.ROOT = root
            with mock.patch.object(
                validator,
                "_read_bound_converter",
                side_effect=substitute_after_read,
            ):
                self.assertEqual(validator.validate_macwin_asset_migration(), [])
            self.assertTrue(attacked)
            self.assertFalse(marker.exists())

    def test_repository_validation_rejects_ordinary_tools_parent_replacement(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            (tools / "convert_macwin_assets.py").write_text(
                "raise SystemExit(0)\n", encoding="utf-8", newline="\n"
            )
            attacker = root / "attacker-tools"
            attacker.mkdir()
            marker = root / "attacker-executed.txt"
            (attacker / "convert_macwin_assets.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed')\n"
                "raise SystemExit(0)\n",
                encoding="utf-8",
                newline="\n",
            )
            saved = root / "saved-tools"
            original_read = validator._read_bound_converter
            attacked = False

            def swap_before_leaf_read(*args, **options):
                nonlocal attacked
                if not attacked:
                    attacked = True
                    tools.rename(saved)
                    attacker.rename(tools)
                return original_read(*args, **options)

            validator.ROOT = root
            with mock.patch.object(
                validator,
                "_read_bound_converter",
                side_effect=swap_before_leaf_read,
            ):
                self.assertNotEqual(
                    validator.validate_macwin_asset_migration(), []
                )
            self.assertTrue(attacked)
            self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "Win32 validator handle declaration")
    def test_repository_validator_declares_and_closes_win32_directory_handles(self) -> None:
        validator = self._load_repository_validator()
        self.assertEqual(
            validator._VALIDATOR_CLOSE_HANDLE.argtypes,
            (validator.wintypes.HANDLE,),
        )
        self.assertIs(
            validator._VALIDATOR_CLOSE_HANDLE.restype,
            validator.wintypes.BOOL,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            descriptor, _identity = validator._bind_validator_directory(path)
            with mock.patch.object(
                validator,
                "_VALIDATOR_CLOSE_HANDLE",
                wraps=validator._VALIDATOR_CLOSE_HANDLE,
            ) as close:
                validator._close_validator_directory(descriptor)
            close.assert_called_once_with(descriptor)

    def test_repository_validation_rejects_a_nonregular_converter(self) -> None:
        validator = self._load_repository_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "tools/convert_macwin_assets.py"
            converter.mkdir(parents=True)

            validator.ROOT = root
            self.assertEqual(
                validator.validate_macwin_asset_migration(),
                ["Mac-Win asset migration converter path is not a regular file"],
            )

    def test_repository_validation_runs_converter_check_before_success(self) -> None:
        validator = self._load_repository_validator()
        self.assertTrue(
            hasattr(validator, "validate_macwin_asset_migration"),
            "repository validator is missing the temporary migration-check hook",
        )

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            self._write_minimal_valid_repository(root)
            validator.ROOT = root

            standard_output = io.StringIO()
            standard_error = io.StringIO()
            with contextlib.redirect_stdout(standard_output), contextlib.redirect_stderr(
                standard_error
            ):
                result = validator.main()

            self.assertEqual(result, 1, standard_error.getvalue())
            self.assertIn(
                "Mac-Win generated evidence validation failed",
                standard_error.getvalue(),
            )
            self.assertEqual(
                (root / "migration-check-invocation.json").read_text(encoding="utf-8"),
                '["--check"]',
            )
            self.assertFalse(
                (ROOT / "migration-check-invocation.json").exists(),
                "loading the legacy fake converter must not pollute the real repository",
            )

    @staticmethod
    def _load_repository_validator():
        path = ROOT / "scripts/validate_repository.py"
        spec = importlib.util.spec_from_file_location(
            "macwin_migration_repository_validator", path
        )
        if spec is None or spec.loader is None:
            raise AssertionError(f"could not load repository validator: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _repository_bytecode() -> set[str]:
        bytecode: set[str] = set()
        pending = [ROOT]
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                if path.name in {".git", "target"}:
                    continue
                if path.is_dir():
                    if path.name == "__pycache__":
                        bytecode.add(path.relative_to(ROOT).as_posix())
                    else:
                        pending.append(path)
                elif path.suffix in {".pyc", ".pyo"}:
                    bytecode.add(path.relative_to(ROOT).as_posix())
        return bytecode

    @staticmethod
    def _write_minimal_valid_repository(root: Path) -> None:
        (root / "Cargo.toml").write_text(
            "[workspace]\nmembers = [\n]\n", encoding="utf-8", newline="\n"
        )
        fixture = b"MZ-migration-contract"
        fixture_path = root / "tests/fixtures/hello-x86_64.exe"
        fixture_path.parent.mkdir(parents=True)
        fixture_path.write_bytes(fixture)

        report = {
            "fileDigest": "sha256:" + hashlib.sha256(fixture).hexdigest(),
            "fileSizeBytes": len(fixture),
            "importLibraries": [],
            "schemaVersion": "1",
        }
        example = root / "examples/executable-inspection.hello-x86_64.json"
        example.parent.mkdir(parents=True)
        example.write_text(
            json.dumps(report, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        converter = root / "tools/convert_macwin_assets.py"
        converter.parent.mkdir(parents=True)
        converter.write_text(
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            "if __name__ == '__main__':\n"
            "    Path('migration-check-invocation.json').write_text(\n"
            "        json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            "    )\n",
            encoding="utf-8",
            newline="\n",
        )
        source = ROOT / "migration/macwin/source"
        destination = root / "migration/macwin/source"
        destination.parent.mkdir(parents=True)
        shutil.copytree(source, destination)

    def _prepare_staged_git_repository(self, repository: Path) -> None:
        self._git(repository, "init", "--quiet")
        self._git(repository, "config", "user.name", "Migration Contract Test")
        self._git(
            repository,
            "config",
            "user.email",
            "migration@example.invalid",
        )
        tracked = repository / "tracked.txt"
        tracked.write_text("contract\n", encoding="utf-8", newline="\n")
        self._git(repository, "add", "tracked.txt")

    @staticmethod
    def _run_migration_import_probe(module: Path) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in IMPORT_PROBE_ENVIRONMENT_NAMES
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import runpy, sys; runpy.run_path(sys.argv[1], "
                "run_name='migration_import_contract')",
                str(module),
            ],
            cwd=ROOT,
            check=True,
            env=environment,
            executable=None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
        )

    @classmethod
    def _git(
        cls,
        repository: Path,
        *arguments: str,
        assume_different_owner: bool = False,
    ) -> str:
        return cls._run_git(
            repository,
            *arguments,
            assume_different_owner=assume_different_owner,
            text=True,
        ).stdout.strip()

    @classmethod
    def _git_bytes(
        cls,
        repository: Path,
        *arguments: str,
        assume_different_owner: bool = False,
    ) -> bytes:
        return cls._run_git(
            repository,
            *arguments,
            assume_different_owner=assume_different_owner,
            text=False,
        ).stdout

    @staticmethod
    def _run_git(
        repository: Path,
        *arguments: str,
        assume_different_owner: bool,
        text: bool,
    ):
        resolved = repository.resolve()
        command = [
            "git",
            "--no-replace-objects",
            "-c",
            f"safe.directory={resolved}",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "tag.gpgSign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
        ]
        if arguments and arguments[0] == "init":
            command.extend(("init", "--template=", *arguments[1:]))
        else:
            command.extend(arguments)

        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
            }
        )
        if assume_different_owner:
            environment["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"

        return subprocess.run(
            command,
            cwd=repository,
            check=True,
            env=environment,
            executable=None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=text,
            timeout=GIT_TIMEOUT_SECONDS,
        )


class MacWinSourcePackTests(unittest.TestCase):
    REPOSITORY = "a1112/Mac-Win"
    SOURCE_TAG = "mw-migration-baseline-db12d5e"
    SOURCE_TAG_OBJECT = "9f10d003382ce7ffbb269376c03477e17516302f"
    SOURCE_COMMIT = "db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527"
    INVENTORY_COMMIT = "97f8423094d25325d8f864eb6f49a9e8628dbb93"
    CATEGORY_COUNTS = {
        "catalog": 19,
        "patches": 11,
        "probes": 26,
        "fixtures": 30,
        "bottleSchema": 4,
    }

    @staticmethod
    def _temporary_directory():
        candidate = ROOT.parents[1] / ".codex-tmp"
        parent = candidate if candidate.is_dir() else None
        return tempfile.TemporaryDirectory(dir=parent)

    def test_committed_source_pack_has_exact_identity_and_complete_records(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        manifest = importer.validate_source_pack(source_root)

        self.assertEqual(manifest["schemaVersion"], "1")
        self.assertEqual(manifest["repository"], self.REPOSITORY)
        self.assertEqual(manifest["sourceTag"], self.SOURCE_TAG)
        self.assertEqual(manifest["sourceTagObject"], self.SOURCE_TAG_OBJECT)
        self.assertEqual(manifest["sourceCommit"], self.SOURCE_COMMIT)
        self.assertEqual(manifest["inventoryCommit"], self.INVENTORY_COMMIT)
        self.assertEqual(manifest["digestAlgorithm"], "sha256")
        self.assertEqual(manifest["assetCount"], 90)
        self.assertEqual(manifest["categoryCounts"], self.CATEGORY_COUNTS)

        assets = manifest["assets"]
        self.assertEqual(len(assets), 90)
        paths = [asset["sourcePath"] for asset in assets]
        self.assertEqual(paths, sorted(paths, key=lambda value: value.encode("ascii")))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(len(paths), len({value.casefold() for value in paths}))
        self.assertEqual(sum(asset["gitMode"] == "100755" for asset in assets), 11)
        self.assertTrue(
            all(
                asset["category"] == "probes"
                for asset in assets
                if asset["gitMode"] == "100755"
            )
        )

        expected_fields = {
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
        total_bytes = 0
        for asset in assets:
            with self.subTest(sourcePath=asset["sourcePath"]):
                self.assertEqual(set(asset), expected_fields)
                self.assertEqual(asset["sourceCommit"], self.SOURCE_COMMIT)
                self.assertEqual(asset["license"], {"status": "unresolved"})
                self.assertEqual(asset["provenance"], {"status": "unresolved"})
                self.assertEqual(
                    asset["objectPath"],
                    "objects/sha256/"
                    + asset["sha256"][:2]
                    + "/"
                    + asset["sha256"][2:],
                )
                raw = (source_root / PurePosixPath(asset["objectPath"])).read_bytes()
                self.assertEqual(len(raw), asset["byteSize"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), asset["sha256"])
                header = f"blob {len(raw)}\0".encode("ascii")
                self.assertEqual(hashlib.sha1(header + raw).hexdigest(), asset["gitBlobOid"])
                total_bytes += len(raw)
        self.assertLessEqual(total_bytes, importer.MAX_TOTAL_SOURCE_BYTES)

    def test_source_pack_index_and_objects_are_canonical_and_exact(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        manifest = importer.validate_source_pack(source_root)
        index_raw = (source_root / "index.json").read_bytes()
        common = _load_macwin_asset_common()
        self.assertEqual(index_raw, common.canonical_json_bytes(manifest))

        expected = {asset["objectPath"] for asset in manifest["assets"]}
        actual = {
            path.relative_to(source_root).as_posix()
            for path in (source_root / "objects/sha256").glob("*/*")
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 90)

    def test_source_object_attributes_preserve_raw_bytes_under_autocrlf(self) -> None:
        attribute_rule = b"/migration/macwin/source/objects/sha256/** binary\n"
        attributes = (ROOT / ".gitattributes").read_bytes()
        manifest = json.loads(
            (ROOT / "migration/macwin/source/index.json").read_text(encoding="utf-8")
        )
        text_samples: list[tuple[str, bytes]] = []
        binary_samples: list[tuple[str, bytes]] = []
        for record in manifest["assets"]:
            relative = "migration/macwin/source/" + record["objectPath"]
            raw = (ROOT / PurePosixPath(relative)).read_bytes()
            if b"\n" in raw and b"\r\n" not in raw and b"\x00" not in raw:
                try:
                    raw.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    pass
                else:
                    if len(text_samples) < 3:
                        text_samples.append((relative, raw))
            if b"\x00" in raw and len(binary_samples) < 2:
                binary_samples.append((relative, raw))
        self.assertEqual(len(text_samples), 3)
        if not binary_samples:
            binary_samples.extend(
                (
                    (
                        "migration/macwin/source/objects/sha256/00/" + ("0" * 62),
                        b"\x00\xffsynthetic-binary\r\n",
                    ),
                    (
                        "migration/macwin/source/objects/sha256/ff/" + ("f" * 62),
                        bytes(range(256)),
                    ),
                )
            )

        old_attributes = attributes.replace(attribute_rule, b"")
        old_staged, old_checked, _old_semantics = self._autocrlf_roundtrip(
            old_attributes, text_samples[:1]
        )
        old_path, old_raw = text_samples[0]
        self.assertEqual(old_staged[old_path], old_raw)
        self.assertNotEqual(old_checked[old_path], old_raw)

        self.assertEqual(attributes.count(attribute_rule), 1)
        samples = [*text_samples, *binary_samples]
        staged, checked, semantics = self._autocrlf_roundtrip(attributes, samples)
        for relative, raw in samples:
            with self.subTest(path=relative):
                self.assertEqual(staged[relative], raw)
                self.assertEqual(checked[relative], raw)
                header = f"blob {len(raw)}\0".encode("ascii")
                self.assertEqual(
                    hashlib.sha1(header + staged[relative]).hexdigest(),
                    hashlib.sha1(header + raw).hexdigest(),
                )
        self.assertEqual(semantics["binary"], "set")
        self.assertEqual(semantics["diff"], "unset")
        self.assertEqual(semantics["merge"], "unset")
        self.assertEqual(semantics["text"], "unset")

    def test_staged_source_pack_preserves_index_and_every_raw_blob_identity(self) -> None:
        source_root = ROOT / "migration/macwin/source"
        index_relative = "migration/macwin/source/index.json"
        index_raw = (source_root / "index.json").read_bytes()
        self.assertEqual(
            MigrationLayoutTests._git_bytes(ROOT, "show", f":{index_relative}"),
            index_raw,
        )
        manifest = json.loads(index_raw.decode("utf-8"))
        for record in manifest["assets"]:
            relative = "migration/macwin/source/" + record["objectPath"]
            with self.subTest(sourcePath=record["sourcePath"]):
                self.assertEqual(
                    self._git(ROOT, "rev-parse", f":{relative}"),
                    record["gitBlobOid"],
                )
                self.assertEqual(
                    MigrationLayoutTests._git_bytes(ROOT, "show", f":{relative}"),
                    (ROOT / PurePosixPath(relative)).read_bytes(),
                )

    def test_source_pack_rejects_missing_extra_and_mutated_objects(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        for mutation in ("missing", "extra", "byte-drift", "directory"):
            with self.subTest(mutation=mutation), self._temporary_directory() as directory:
                copied = self._copy_pack(source_root, Path(directory))
                object_path = self._first_object(copied)
                if mutation == "missing":
                    object_path.unlink()
                elif mutation == "extra":
                    extra = copied / "objects/sha256/00" / ("0" * 62)
                    extra.parent.mkdir(exist_ok=True)
                    extra.write_bytes(b"extra")
                elif mutation == "byte-drift":
                    raw = object_path.read_bytes()
                    object_path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                else:
                    object_path.unlink()
                    object_path.mkdir()
                with self.assertRaises(importer.SourcePackError):
                    importer.validate_source_pack(copied)

    def test_source_pack_rejects_index_mutations_and_duplicate_identities(self) -> None:
        importer = self._load_importer()
        common = _load_macwin_asset_common()
        source_root = ROOT / "migration/macwin/source"
        mutations = {
            "record-order": lambda value: value["assets"].reverse(),
            "duplicate-path": lambda value: value["assets"][1].__setitem__(
                "sourcePath", value["assets"][0]["sourcePath"]
            ),
            "case-folded-path": lambda value: value["assets"][1].__setitem__(
                "sourcePath", value["assets"][0]["sourcePath"].swapcase()
            ),
            "duplicate-digest": lambda value: (
                value["assets"][1].__setitem__("sha256", value["assets"][0]["sha256"]),
                value["assets"][1].__setitem__(
                    "objectPath", value["assets"][0]["objectPath"]
                ),
            ),
            "wrong-mode": lambda value: value["assets"][0].__setitem__(
                "gitMode", "120000"
            ),
            "unknown-field": lambda value: value.__setitem__("unexpected", True),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name), self._temporary_directory() as directory:
                copied = self._copy_pack(source_root, Path(directory))
                value = json.loads((copied / "index.json").read_text(encoding="utf-8"))
                mutate(value)
                (copied / "index.json").write_bytes(common.canonical_json_bytes(value))
                with self.assertRaises(importer.SourcePackError):
                    importer.validate_source_pack(copied)

        with self._temporary_directory() as directory:
            copied = self._copy_pack(source_root, Path(directory))
            (copied / "index.json").write_bytes(
                (copied / "index.json").read_bytes() + b" "
            )
            with self.assertRaises(importer.SourcePackError):
                importer.validate_source_pack(copied)

    def test_source_pack_rejects_a_self_consistent_offline_forgery(self) -> None:
        importer = self._load_importer()
        common = _load_macwin_asset_common()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            copied = self._copy_pack(source_root, Path(directory))
            manifest = json.loads((copied / "index.json").read_text(encoding="utf-8"))
            record = manifest["assets"][0]
            old_path = copied / PurePosixPath(record["objectPath"])
            forged = old_path.read_bytes() + b"\nforged"
            old_path.unlink()
            if not any(old_path.parent.iterdir()):
                old_path.parent.rmdir()
            digest = hashlib.sha256(forged).hexdigest()
            record["sha256"] = digest
            record["byteSize"] = len(forged)
            record["gitBlobOid"] = hashlib.sha1(
                f"blob {len(forged)}\0".encode("ascii") + forged
            ).hexdigest()
            record["objectPath"] = f"objects/sha256/{digest[:2]}/{digest[2:]}"
            new_path = copied / PurePosixPath(record["objectPath"])
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_path.write_bytes(forged)
            (copied / "index.json").write_bytes(common.canonical_json_bytes(manifest))
            with self.assertRaises(importer.SourcePackError):
                importer.validate_source_pack(copied)

    def test_source_pack_rejects_oversized_index_and_object_before_trusting_them(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        cases = ("index", "object")
        for case in cases:
            with self.subTest(case=case), self._temporary_directory() as directory:
                copied = self._copy_pack(source_root, Path(directory))
                if case == "index":
                    (copied / "index.json").write_bytes(
                        b" " * (importer.MAX_SOURCE_INDEX_BYTES + 1)
                    )
                else:
                    self._first_object(copied).write_bytes(
                        b"x" * (importer.MAX_SOURCE_OBJECT_BYTES + 1)
                    )
                with self.assertRaises(importer.SourcePackError):
                    importer.validate_source_pack(copied)

    def test_source_pack_rejects_linked_reparse_and_hardlinked_content(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        for kind in ("leaf-symlink", "parent-symlink", "hardlink"):
            with self.subTest(kind=kind), self._temporary_directory() as directory:
                root = Path(directory)
                copied = self._copy_pack(source_root, root)
                object_path = self._first_object(copied)
                outside = root / "outside"
                outside.write_bytes(object_path.read_bytes())
                try:
                    if kind == "leaf-symlink":
                        object_path.unlink()
                        os.symlink(outside, object_path)
                    elif kind == "parent-symlink":
                        shard = object_path.parent
                        saved = root / "saved-shard"
                        shard.rename(saved)
                        os.symlink(saved, shard, target_is_directory=True)
                    else:
                        object_path.unlink()
                        os.link(outside, object_path)
                except (OSError, NotImplementedError) as error:
                    self.skipTest(f"linked-file contract cannot be exercised: {error}")
                with self.assertRaises(importer.SourcePackError):
                    importer.validate_source_pack(copied)

    def test_source_pack_rejects_a_linked_root_before_resolution(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            root = Path(directory)
            copied = self._copy_pack(source_root, root)
            linked = root / "linked-source"
            try:
                os.symlink(copied, linked, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"linked-root contract cannot be exercised: {error}")
            with self.assertRaises(importer.SourcePackError):
                importer.validate_source_pack(linked)

    def test_git_subprocess_boundary_is_fixed_scrubbed_and_noninteractive(self) -> None:
        importer = self._load_importer()
        repository = ROOT.resolve()
        hostile = {
            "GIT_DIR": "hostile.git",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "include.path",
            "GIT_CONFIG_VALUE_0": "hostile.config",
            "HTTP_PROXY": "http://hostile.invalid",
        }
        with mock.patch.dict(os.environ, hostile, clear=False), mock.patch.object(
            importer.subprocess, "run"
        ) as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"ok", b"")
            completed = importer._run_git(repository, ("status", "--porcelain"))
        self.assertEqual(completed.stdout, b"ok")
        command = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(
            command,
            [
                "git",
                "--no-replace-objects",
                "-c",
                f"safe.directory={repository}",
                "-c",
                "commit.gpgSign=false",
                "-c",
                "tag.gpgSign=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-c",
                "core.fsmonitor=false",
                "status",
                "--porcelain",
            ],
        )
        self.assertEqual(
            {
                key: value
                for key, value in options["env"].items()
                if key.upper().startswith("GIT_")
            },
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        self.assertNotIn("HTTP_PROXY", options["env"])
        self.assertIs(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stdout"], subprocess.PIPE)
        self.assertIs(options["stderr"], subprocess.PIPE)
        self.assertFalse(options["shell"])
        self.assertIsNone(options["executable"])
        self.assertEqual(options["timeout"], importer.GIT_TIMEOUT_SECONDS)

    def test_git_binding_rejects_wrong_tag_forms_and_nonancestor_source(self) -> None:
        importer = self._load_importer()
        scenarios = (
            "missing",
            "lightweight",
            "symbolic",
            "case-variant",
            "wrong-target",
            "non-ancestor",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario), self._temporary_directory() as directory:
                repository, source, inventory = self._make_binding_repository(
                    Path(directory), scenario
                )
                with self.assertRaises(importer.SourcePackError):
                    importer._bind_repository(
                        repository,
                        tag="approved-tag",
                        tag_object="0" * 40,
                        source_commit=source,
                        inventory_commit=inventory,
                    )

    def test_git_binding_accepts_only_the_exact_annotated_ancestor_contract(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            repository, source, inventory = self._make_binding_repository(
                Path(directory), "valid"
            )
            binding = importer._bind_repository(
                repository,
                tag="approved-tag",
                tag_object=self._git(
                    repository, "rev-parse", "refs/tags/approved-tag"
                ),
                source_commit=source,
                inventory_commit=inventory,
            )
        self.assertEqual(binding.repository, repository.resolve())
        self.assertEqual(binding.source_tag, "approved-tag")
        self.assertEqual(binding.source_commit, source)
        self.assertEqual(binding.inventory_commit, inventory)

    def test_git_binding_rejects_a_linked_repository_root_before_resolution(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            root = Path(directory)
            repository, source, inventory = self._make_binding_repository(root, "valid")
            linked = root / "linked-repository"
            try:
                os.symlink(repository, linked, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"linked-repository contract cannot be exercised: {error}")
            with self.assertRaises(importer.SourcePackError):
                importer._bind_repository(
                    linked,
                    tag="approved-tag",
                    tag_object=self._git(
                        repository, "rev-parse", "refs/tags/approved-tag"
                    ),
                    source_commit=source,
                    inventory_commit=inventory,
                )

    def test_git_binding_rejects_a_graft_that_forges_source_ancestry(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            repository, source, inventory = self._make_binding_repository(
                Path(directory), "non-ancestor"
            )
            tag_object = self._git(
                repository, "rev-parse", "refs/tags/approved-tag"
            )
            grafts = repository / ".git/info/grafts"
            grafts.parent.mkdir(exist_ok=True)
            grafts.write_text(
                f"{inventory} {source}\n", encoding="ascii", newline="\n"
            )
            self._git(
                repository,
                "merge-base",
                "--is-ancestor",
                source,
                inventory,
            )

            with self.assertRaises(importer.SourcePackError):
                importer._bind_repository(
                    repository,
                    tag="approved-tag",
                    tag_object=tag_object,
                    source_commit=source,
                    inventory_commit=inventory,
                )

    def test_git_storage_rejects_an_external_reftable_directory(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            root = Path(directory)
            repository, _source, _inventory = self._make_binding_repository(
                root, "valid"
            )
            git_directory = repository / ".git"
            external = root / "external-reftable"
            external.mkdir()
            try:
                os.symlink(
                    external,
                    git_directory / "reftable",
                    target_is_directory=True,
                )
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"reftable link contract cannot be exercised: {error}")
            with (git_directory / "config").open(
                "a", encoding="utf-8", newline="\n"
            ) as stream:
                stream.write("[extensions]\n\trefStorage = reftable\n")

            with self.assertRaises(importer.SourcePackError):
                importer._validate_git_storage(repository)

    def test_git_binding_rejects_a_linked_worktree_common_directory(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            root = Path(directory)
            repository, source, inventory = self._make_binding_repository(
                root, "valid"
            )
            linked_worktree = root / "linked-worktree"
            self._git(
                repository,
                "worktree",
                "add",
                "--detach",
                str(linked_worktree),
                source,
            )
            common_directory = Path(
                self._git(linked_worktree, "rev-parse", "--git-common-dir")
            )
            if not common_directory.is_absolute():
                common_directory = linked_worktree / common_directory
            self.assertEqual(common_directory.resolve(), (repository / ".git").resolve())

            with self.assertRaises(importer.SourcePackError):
                importer._bind_repository(
                    linked_worktree,
                    tag="approved-tag",
                    tag_object=self._git(
                        repository, "rev-parse", "refs/tags/approved-tag"
                    ),
                    source_commit=source,
                    inventory_commit=inventory,
                )

    def test_git_binding_rejects_casefold_tag_collisions(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            repository, source, inventory = self._make_binding_repository(
                Path(directory), "valid"
            )
            tag_object = self._git(
                repository, "rev-parse", "refs/tags/approved-tag"
            )
            self._git(repository, "pack-refs", "--all")
            self._git(
                repository,
                "update-ref",
                "refs/tags/Approved-Tag",
                tag_object,
            )
            references = self._git(
                repository, "for-each-ref", "--format=%(refname)", "refs/tags/"
            ).splitlines()
            self.assertEqual(
                sum(
                    value.casefold() == "refs/tags/approved-tag"
                    for value in references
                ),
                2,
            )

            with self.assertRaises(importer.SourcePackError):
                importer._bind_repository(
                    repository,
                    tag="approved-tag",
                    tag_object=tag_object,
                    source_commit=source,
                    inventory_commit=inventory,
                )

    def test_git_binding_bounds_the_complete_tag_reference_enumeration(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            repository, source, inventory = self._make_binding_repository(
                Path(directory), "valid"
            )
            tag_object = self._git(
                repository, "rev-parse", "refs/tags/approved-tag"
            )
            self._git(repository, "tag", "-a", "other-tag", "-m", "other", source)

            with mock.patch.object(
                importer,
                "_validate_git_storage",
                return_value=repository / ".git",
            ), mock.patch.object(importer, "MAX_GIT_REF_NODES", 1):
                with self.assertRaises(importer.SourcePackError):
                    importer._bind_repository(
                        repository,
                        tag="approved-tag",
                        tag_object=tag_object,
                        source_commit=source,
                        inventory_commit=inventory,
                    )

    def test_repository_root_swap_never_binds_an_external_git_repository(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            root = Path(directory)
            inside_parent = root / "inside"
            outside_parent = root / "outside"
            inside_parent.mkdir()
            outside_parent.mkdir()
            repository, _inside_source, _inside_inventory = (
                self._make_binding_repository(inside_parent, "valid")
            )
            external, source, inventory = self._make_binding_repository(
                outside_parent, "valid"
            )
            tag_object = self._git(
                external, "rev-parse", "refs/tags/approved-tag"
            )
            requested = repository.absolute()
            saved = repository.with_name("saved-repository")
            real_validate_path_chain = importer._validate_path_chain
            swapped = False

            def swap_after_validation(path: Path) -> None:
                nonlocal swapped
                real_validate_path_chain(path)
                if path == requested and not swapped:
                    repository.rename(saved)
                    os.symlink(external, repository, target_is_directory=True)
                    swapped = True

            try:
                with mock.patch.object(
                    importer, "_validate_path_chain", swap_after_validation
                ):
                    with self.assertRaises(importer.SourcePackError):
                        importer._bind_repository(
                            repository,
                            tag="approved-tag",
                            tag_object=tag_object,
                            source_commit=source,
                            inventory_commit=inventory,
                        )
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"repository swap contract cannot be exercised: {error}")
            self.assertTrue(swapped)

    def test_source_pack_root_swap_never_validates_an_external_pack(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            root = Path(directory)
            inside_parent = root / "inside"
            outside_parent = root / "outside"
            inside_parent.mkdir()
            outside_parent.mkdir()
            copied = self._copy_pack(source_root, inside_parent)
            external = self._copy_pack(source_root, outside_parent)
            requested = copied.absolute()
            saved = copied.with_name("saved-source")
            real_validate_path_chain = importer._validate_path_chain
            swapped = False

            def swap_after_validation(path: Path) -> None:
                nonlocal swapped
                real_validate_path_chain(path)
                if path == requested and not swapped:
                    copied.rename(saved)
                    os.symlink(external, copied, target_is_directory=True)
                    swapped = True

            try:
                with mock.patch.object(
                    importer, "_validate_path_chain", swap_after_validation
                ):
                    with self.assertRaises(importer.SourcePackError):
                        importer.validate_source_pack(copied)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"source-pack swap contract cannot be exercised: {error}")
            self.assertTrue(swapped)

    def test_git_binding_rejects_external_object_and_linked_metadata_boundaries(self) -> None:
        importer = self._load_importer()
        for scenario in (
            "alternates",
            "promisor",
            "replace",
            "config-include",
            "linked-index",
            "linked-ref",
            "linked-object",
            "corrupt-object",
        ):
            with self.subTest(scenario=scenario), self._temporary_directory() as directory:
                repository, source, inventory = self._make_binding_repository(
                    Path(directory), "valid"
                )
                git_dir = repository / ".git"
                tag_object = self._git(
                    repository, "rev-parse", "refs/tags/approved-tag"
                )
                try:
                    if scenario == "alternates":
                        path = git_dir / "objects/info/alternates"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("../external\n", encoding="utf-8", newline="\n")
                    elif scenario == "promisor":
                        path = git_dir / "objects/pack/hostile.promisor"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"")
                    elif scenario == "replace":
                        self._git(
                            repository,
                            "update-ref",
                            f"refs/replace/{source}",
                            inventory,
                        )
                    elif scenario == "config-include":
                        included = Path(directory) / "included.config"
                        included.write_text(
                            "[core]\n\tfsmonitor = hostile\n",
                            encoding="utf-8",
                            newline="\n",
                        )
                        with (git_dir / "config").open(
                            "a", encoding="utf-8", newline="\n"
                        ) as stream:
                            stream.write(f"[include]\n\tpath = {included.as_posix()}\n")
                    elif scenario == "linked-index":
                        index = git_dir / "index"
                        outside = Path(directory) / "outside-index"
                        outside.write_bytes(index.read_bytes())
                        index.unlink()
                        os.symlink(outside, index)
                    elif scenario == "linked-ref":
                        reference = git_dir / "refs/tags/approved-tag"
                        outside = Path(directory) / "outside-ref"
                        reference.rename(outside)
                        os.symlink(outside, reference)
                    else:
                        object_path = git_dir / "objects" / source[:2] / source[2:]
                        if scenario == "linked-object":
                            outside = Path(directory) / "outside-object"
                            object_path.rename(outside)
                            os.symlink(outside, object_path)
                        else:
                            object_path.chmod(0o644)
                            raw = object_path.read_bytes()
                            object_path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                except (OSError, NotImplementedError) as error:
                    self.skipTest(f"Git metadata boundary cannot be exercised: {error}")
                with self.assertRaises(importer.SourcePackError):
                    importer._bind_repository(
                        repository,
                        tag="approved-tag",
                        tag_object=tag_object,
                        source_commit=source,
                        inventory_commit=inventory,
                    )

    def test_git_binding_rejects_rebuilt_tag_with_same_name_and_peeled_commit(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            repository, source, inventory = self._make_binding_repository(
                Path(directory), "valid"
            )
            approved_tag_object = self._git(
                repository, "rev-parse", "refs/tags/approved-tag"
            )
            self._git(repository, "tag", "-d", "approved-tag")
            self._git(
                repository,
                "tag",
                "-a",
                "approved-tag",
                "-m",
                "rebuilt annotation",
                source,
            )
            rebuilt_tag_object = self._git(
                repository, "rev-parse", "refs/tags/approved-tag"
            )
            self.assertNotEqual(rebuilt_tag_object, approved_tag_object)
            self.assertEqual(
                self._git(repository, "rev-parse", "approved-tag^{}"), source
            )
            with self.assertRaises(importer.SourcePackError):
                importer._bind_repository(
                    repository,
                    tag="approved-tag",
                    tag_object=approved_tag_object,
                    source_commit=source,
                    inventory_commit=inventory,
                )

    def test_importer_requires_explicit_identity_and_never_imports_on_module_load(self) -> None:
        importer = self._load_importer()
        with mock.patch.object(importer, "generate_source_pack") as generate:
            self.assertEqual(importer.main(()), 2)
        generate.assert_not_called()

    def test_importer_ignores_an_ambient_pythonpath_common_module(self) -> None:
        importer_path = ROOT / "tools/import_macwin_source_pack.py"
        common_path = ROOT / "tools/macwin_asset_common.py"
        with self._temporary_directory() as directory:
            hostile = Path(directory) / "hostile"
            hostile.mkdir()
            (hostile / "macwin_asset_common.py").write_text(
                "raise RuntimeError('ambient module imported')\n",
                encoding="utf-8",
                newline="\n",
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(hostile)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            code = (
                "import importlib.util, os, pathlib, sys; "
                "spec=importlib.util.spec_from_file_location('source_pack_probe', sys.argv[1]); "
                "module=importlib.util.module_from_spec(spec); "
                "sys.modules[spec.name]=module; "
                "spec.loader.exec_module(module); "
                "assert pathlib.Path(module._COMMON.__file__).absolute() == "
                "pathlib.Path(sys.argv[2]).absolute()"
            )
            completed = subprocess.run(
                [sys.executable, "-B", "-c", code, str(importer_path), str(common_path)],
                cwd=ROOT,
                check=False,
                env=environment,
                executable=None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_importer_rejects_a_linked_common_module_sibling(self) -> None:
        with self._temporary_directory() as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            importer_path = tools / "import_macwin_source_pack.py"
            importer_path.write_bytes(
                (ROOT / "tools/import_macwin_source_pack.py").read_bytes()
            )
            external = root / "external-common.py"
            external.write_bytes((ROOT / "tools/macwin_asset_common.py").read_bytes())
            try:
                os.symlink(external, tools / "macwin_asset_common.py")
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"common-module link contract cannot be exercised: {error}")
            code = (
                "import importlib.util, sys; "
                "spec=importlib.util.spec_from_file_location('source_pack_probe', sys.argv[1]); "
                "module=importlib.util.module_from_spec(spec); "
                "sys.modules[spec.name]=module; "
                "spec.loader.exec_module(module)"
            )
            completed = subprocess.run(
                [sys.executable, "-B", "-c", code, str(importer_path)],
                cwd=root,
                check=False,
                env={"PYTHONDONTWRITEBYTECODE": "1"},
                executable=None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("migration common module could not be loaded", completed.stderr)

    def test_source_pack_writer_creates_only_the_owned_parent_directories(self) -> None:
        importer = self._load_importer()
        with self._temporary_directory() as directory:
            root = Path(directory)
            destination = root / "migration/macwin/source"
            parent = importer._prepare_parent(destination)
            self.assertEqual(parent, root / "migration/macwin")
            self.assertTrue(parent.is_dir())
            self.assertFalse(destination.exists())

    def test_first_install_rolls_back_after_post_replace_failure(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        manifest = importer.validate_source_pack(source_root)
        documents = importer._document_bytes(source_root, manifest)

        for scenario in ("validation", "readback", "injected"):
            with self.subTest(scenario=scenario), self._temporary_directory() as directory:
                root = Path(directory)
                destination = root / "migration/macwin/source"
                real_validate = importer.validate_source_pack
                real_document_bytes = importer._document_bytes

                def injected_validate(path: Path):
                    if scenario == "validation" and path == destination:
                        raise importer.SourcePackError("injected installed validation failure")
                    return real_validate(path)

                def injected_document_bytes(path: Path, value: dict[str, object]):
                    if scenario == "readback" and path == destination:
                        raise importer.SourcePackError("injected installed readback failure")
                    if scenario == "injected" and path == destination:
                        raise RuntimeError("injected post-replace failure")
                    return real_document_bytes(path, value)

                with mock.patch.object(
                    importer, "SOURCE_PACK_ROOT", destination
                ), mock.patch.object(
                    importer, "validate_source_pack", injected_validate
                ), mock.patch.object(
                    importer, "_document_bytes", injected_document_bytes
                ):
                    expected = (
                        RuntimeError
                        if scenario == "injected"
                        else importer.SourcePackError
                    )
                    with self.assertRaises(expected):
                        importer._write_source_pack(destination, documents)

                self.assertFalse(destination.exists())
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_existing_install_rolls_back_every_post_replace_failure(self) -> None:
        importer = self._load_importer()
        scenarios = (
            ("validation-runtime", "validation", RuntimeError),
            ("readback-runtime", "readback", RuntimeError),
            ("validation-interrupt", "validation", KeyboardInterrupt),
            ("readback-system-exit", "readback", SystemExit),
        )
        new_documents = {"index.json": b"new source pack\n"}

        for name, injection_point, exception_type in scenarios:
            with self.subTest(scenario=name), self._temporary_directory() as directory:
                root = Path(directory)
                destination = root / "migration/macwin/source"
                destination.mkdir(parents=True)
                (destination / "index.json").write_bytes(b"old source pack\n")
                old_object = destination / "objects/old"
                old_object.parent.mkdir()
                old_object.write_bytes(b"old object bytes\x00\r\n")

                def read_tree(path: Path) -> dict[str, bytes]:
                    return {
                        value.relative_to(path).as_posix(): value.read_bytes()
                        for value in sorted(path.rglob("*"))
                        if value.is_file()
                    }

                old_documents = read_tree(destination)

                def injected_validate(path: Path) -> dict[str, object]:
                    if (
                        path == destination
                        and read_tree(path) == new_documents
                        and injection_point == "validation"
                    ):
                        raise exception_type("injected installed validation failure")
                    return {}

                def injected_document_bytes(
                    path: Path, _manifest: dict[str, object]
                ) -> dict[str, bytes]:
                    documents = read_tree(path)
                    if (
                        path == destination
                        and documents == new_documents
                        and injection_point == "readback"
                    ):
                        raise exception_type("injected installed readback failure")
                    return documents

                with mock.patch.object(
                    importer, "SOURCE_PACK_ROOT", destination
                ), mock.patch.object(
                    importer, "validate_source_pack", injected_validate
                ), mock.patch.object(
                    importer, "_document_bytes", injected_document_bytes
                ):
                    with self.assertRaises(exception_type):
                        importer._write_source_pack(destination, new_documents)

                self.assertEqual(read_tree(destination), old_documents)
                self.assertEqual(
                    {value.name for value in destination.parent.iterdir()},
                    {"source"},
                )

    def test_repository_validator_allows_only_the_validated_sealed_evidence(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        validator.ROOT = ROOT
        self.assertEqual(validator.validate_no_developer_paths(), [])

    def test_repository_validator_does_not_exempt_ordinary_or_unreferenced_files(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        source_root = ROOT / "migration/macwin/source"
        for case in ("ordinary", "unreferenced", "extra-object"):
            with self.subTest(case=case), self._temporary_directory() as directory:
                temporary_root = Path(directory)
                copied = temporary_root / "migration/macwin/source"
                copied.parent.mkdir(parents=True)
                shutil.copytree(source_root, copied)
                if case == "ordinary":
                    hostile = temporary_root / "ordinary.txt"
                elif case == "unreferenced":
                    hostile = copied / "unreferenced.txt"
                else:
                    hostile = copied / "objects/sha256/00" / ("0" * 62)
                    hostile.parent.mkdir(exist_ok=True)
                hostile.write_text(
                    "/Users/" + "a1-6/not-exempt\n",
                    encoding="utf-8",
                    newline="\n",
                )
                validator.ROOT = temporary_root
                errors = validator.validate_no_developer_paths()
                self.assertTrue(
                    any(
                        "contains developer path /Users/" + "a1-6/" in error
                        for error in errors
                    ),
                    errors,
                )
                self.assertTrue(
                    any(hostile.name in error for error in errors),
                    errors,
                )
                if case != "ordinary":
                    self.assertIn("Mac-Win source pack validation failed", errors)

    def test_repository_validator_grants_no_exemption_after_pack_mutation(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        source_root = ROOT / "migration/macwin/source"
        for case in ("index", "object"):
            with self.subTest(case=case), self._temporary_directory() as directory:
                temporary_root = Path(directory)
                copied = temporary_root / "migration/macwin/source"
                copied.parent.mkdir(parents=True)
                shutil.copytree(source_root, copied)
                target = copied / "index.json" if case == "index" else self._first_object(copied)
                raw = target.read_bytes()
                target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                validator.ROOT = temporary_root
                errors = validator.validate_no_developer_paths()
                self.assertIn("Mac-Win source pack validation failed", errors)
                index_display = str(Path("migration/macwin/source/index.json"))
                self.assertTrue(
                    any(index_display in error for error in errors), errors
                )

    def test_repository_validator_fails_when_the_source_pack_is_missing(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        with self._temporary_directory() as directory:
            validator.ROOT = Path(directory)
            self.assertEqual(
                validator.validate_no_developer_paths(),
                ["Mac-Win source pack validation failed"],
            )

    def test_repository_source_pack_validation_is_offline_and_neighbor_free(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        validator.ROOT = ROOT
        with mock.patch.object(
            subprocess, "run", side_effect=AssertionError("subprocess invoked")
        ), mock.patch("socket.create_connection", side_effect=AssertionError("network invoked")):
            self.assertEqual(validator.validate_no_developer_paths(), [])

    def test_source_pack_binding_rejects_same_byte_path_replacement(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            copied = self._copy_pack(source_root, Path(directory))
            target = self._developer_path_object(copied)
            raw = target.read_bytes()
            with importer.bind_source_pack(copied) as binding:
                replaced = copied / "replaced-object"
                target.replace(replaced)
                target.write_bytes(raw)
                with self.assertRaises(importer.SourcePackError):
                    binding.verify_path(target)

    def test_source_pack_binding_rejects_same_identity_content_mutation(self) -> None:
        importer = self._load_importer()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            copied = self._copy_pack(source_root, Path(directory))
            target = self._developer_path_object(copied)
            original = target.read_bytes()
            with importer.bind_source_pack(copied) as binding:
                metadata = target.stat()
                mutated = bytes([original[0] ^ 1]) + original[1:]
                target.write_bytes(mutated)
                os.utime(
                    target,
                    ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
                )
                with self.assertRaises(importer.SourcePackError):
                    binding.verify_path(target)

    def test_repository_validator_rejects_replacement_after_authentication(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            temporary_root = Path(directory)
            copied = temporary_root / "migration/macwin/source"
            copied.parent.mkdir(parents=True)
            shutil.copytree(source_root, copied)
            target = self._developer_path_object(copied)
            raw = target.read_bytes()
            original_rglob = Path.rglob
            injected = False

            def replace_before_scan(path: Path, pattern: str):
                nonlocal injected
                if path == temporary_root and not injected:
                    injected = True
                    replaced = copied / "replaced-object"
                    target.replace(replaced)
                    target.write_bytes(raw)
                return original_rglob(path, pattern)

            validator.ROOT = temporary_root
            with mock.patch.object(Path, "rglob", replace_before_scan):
                errors = validator.validate_no_developer_paths()
            self.assertIn("Mac-Win source pack validation failed", errors)
            self.assertTrue(
                any(target.name in error and "contains developer path" in error for error in errors),
                errors,
            )

    def test_repository_validator_revalidates_after_a_skipped_evidence_leaf(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            temporary_root = Path(directory)
            copied = temporary_root / "migration/macwin/source"
            copied.parent.mkdir(parents=True)
            shutil.copytree(source_root, copied)
            target = self._developer_path_object(copied)
            original_rglob = Path.rglob
            injected = False

            def mutate_during_scan(path: Path, pattern: str):
                nonlocal injected
                values = original_rglob(path, pattern)
                if path != temporary_root or injected:
                    yield from values
                    return
                for value in values:
                    yield value
                    if value == target:
                        raw = target.read_bytes()
                        target.write_bytes(raw + b"\nmutation-after-skip")
                        injected = True

            validator.ROOT = temporary_root
            with mock.patch.object(Path, "rglob", mutate_during_scan):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertIn("Mac-Win source pack validation failed", errors)
            self.assertTrue(
                any(target.name in error and "contains developer path" in error for error in errors),
                errors,
            )

    def test_repository_validator_revalidates_after_index_mutation_during_scan(self) -> None:
        validator = MigrationLayoutTests._load_repository_validator()
        source_root = ROOT / "migration/macwin/source"
        with self._temporary_directory() as directory:
            temporary_root = Path(directory)
            copied = temporary_root / "migration/macwin/source"
            copied.parent.mkdir(parents=True)
            shutil.copytree(source_root, copied)
            index = copied / "index.json"
            original_rglob = Path.rglob
            injected = False

            def mutate_index(path: Path, pattern: str):
                nonlocal injected
                values = original_rglob(path, pattern)
                if path != temporary_root or injected:
                    yield from values
                    return
                for value in values:
                    yield value
                    if value == index:
                        raw = index.read_bytes()
                        index.write_bytes(raw[:-1] + b" \n")
                        injected = True

            validator.ROOT = temporary_root
            with mock.patch.object(Path, "rglob", mutate_index):
                errors = validator.validate_no_developer_paths()
            self.assertTrue(injected)
            self.assertIn("Mac-Win source pack validation failed", errors)
            index_display = str(Path("migration/macwin/source/index.json"))
            self.assertTrue(
                any(
                    index_display in error and "contains developer path" in error
                    for error in errors
                ),
                errors,
            )

    @staticmethod
    def _load_importer():
        path = ROOT / "tools/import_macwin_source_pack.py"
        if not path.is_file():
            raise AssertionError("Mac-Win source-pack importer is missing")
        spec = importlib.util.spec_from_file_location("macwin_source_pack_importer", path)
        if spec is None or spec.loader is None:
            raise AssertionError("could not load Mac-Win source-pack importer")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        return module

    @staticmethod
    def _copy_pack(source_root: Path, temporary_root: Path) -> Path:
        copied = temporary_root / "source"
        shutil.copytree(source_root, copied)
        return copied

    @staticmethod
    def _first_object(source_root: Path) -> Path:
        return sorted((source_root / "objects/sha256").glob("*/*"))[0]

    @staticmethod
    def _developer_path_object(source_root: Path) -> Path:
        needle = b"/Users/" + b"a1-6/"
        for path in sorted((source_root / "objects/sha256").glob("*/*")):
            if needle in path.read_bytes():
                return path
        raise AssertionError("source pack has no developer-path evidence object")

    def _make_binding_repository(
        self, root: Path, scenario: str
    ) -> tuple[Path, str, str]:
        repository = root / "repository"
        repository.mkdir()
        self._git(repository, "init", "--quiet")
        self._git(repository, "config", "user.name", "Migration Test")
        self._git(repository, "config", "user.email", "migration@example.invalid")
        tracked = repository / "tracked.txt"
        tracked.write_text("source\n", encoding="utf-8", newline="\n")
        self._git(repository, "add", "tracked.txt")
        self._git(repository, "commit", "--quiet", "-m", "source")
        source = self._git(repository, "rev-parse", "HEAD")
        tracked.write_text("inventory\n", encoding="utf-8", newline="\n")
        self._git(repository, "add", "tracked.txt")
        self._git(repository, "commit", "--quiet", "-m", "inventory")
        inventory = self._git(repository, "rev-parse", "HEAD")

        if scenario == "lightweight":
            self._git(repository, "tag", "approved-tag", source)
        elif scenario == "symbolic":
            self._git(
                repository,
                "symbolic-ref",
                "refs/tags/approved-tag",
                "refs/heads/main",
            )
        elif scenario == "case-variant":
            self._git(repository, "tag", "-a", "Approved-Tag", "-m", "tag", source)
        elif scenario == "wrong-target":
            self._git(repository, "tag", "-a", "approved-tag", "-m", "tag", inventory)
        elif scenario == "non-ancestor":
            self._git(repository, "tag", "-a", "approved-tag", "-m", "tag", inventory)
            source, inventory = inventory, source
        elif scenario != "missing":
            self._git(repository, "tag", "-a", "approved-tag", "-m", "tag", source)
        return repository, source, inventory

    @classmethod
    def _git(cls, repository: Path, *arguments: str) -> str:
        return MigrationLayoutTests._git(repository, *arguments)

    def _autocrlf_roundtrip(
        self, attributes: bytes, samples: list[tuple[str, bytes]]
    ) -> tuple[dict[str, bytes], dict[str, bytes], dict[str, str]]:
        with self._temporary_directory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            (repository / ".gitattributes").write_bytes(attributes)
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.name", "Migration Test")
            self._git(repository, "config", "user.email", "migration@example.invalid")
            self._git(repository, "config", "core.autocrlf", "true")
            self._git(repository, "config", "core.eol", "crlf")
            paths = [relative for relative, _raw in samples]
            for relative, raw in samples:
                path = repository / PurePosixPath(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            self._git(repository, "add", ".gitattributes", *paths)
            staged = {
                relative: MigrationLayoutTests._git_bytes(repository, "show", f":{relative}")
                for relative in paths
            }
            outside = "migration/macwin/generated/not-a-source-object"
            outside_attributes = self._git(
                repository,
                "check-attr",
                "binary",
                "diff",
                "merge",
                "text",
                "--",
                outside,
            ).splitlines()
            self.assertTrue(
                all(line.endswith(": unspecified") for line in outside_attributes),
                outside_attributes,
            )
            source_attributes = self._git(
                repository,
                "check-attr",
                "binary",
                "diff",
                "merge",
                "text",
                "--",
                paths[0],
            ).splitlines()
            semantics = {
                line.split(": ", 2)[1]: line.rsplit(": ", 1)[1]
                for line in source_attributes
            }
            self._git(repository, "commit", "--quiet", "-m", "source objects")
            for relative in paths:
                (repository / PurePosixPath(relative)).unlink()
            self._git(repository, "checkout", "HEAD", "--", *paths)
            checked = {
                relative: (repository / PurePosixPath(relative)).read_bytes()
                for relative in paths
            }
            return staged, checked, semantics


class MacWinMigrationSideEffectTests(unittest.TestCase):
    DOCUMENT_PATHS = (
        "migration/macwin/generated/catalog.json",
        "migration/macwin/generated/index.json",
        "migration/macwin/generated/mappings/bottle-schemas.json",
        "migration/macwin/generated/mappings/patches.json",
        "migration/macwin/generated/quarantine.json",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = _load_macwin_asset_converter()
        cls.result = cls.converter.build_conversion(ROOT)
        cls.documents = cls.converter.render_documents(cls.result)

    def test_all_normal_modes_and_two_writes_preserve_external_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "external-sentinel"
            sentinel.write_bytes(b"must remain unchanged\n")
            commands = (
                self._converter_command(),
                self._converter_command("--check"),
                self._converter_command("--explain", "7zip"),
                (sys.executable, "-B", str(ROOT / "scripts/validate_repository.py")),
                self._converter_command("--write"),
                self._converter_command("--write"),
            )
            for command in commands:
                before = self._snapshot_boundary(sentinel)
                completed = self._run_audited(command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(self._snapshot_boundary(sentinel), before)
            self.assertEqual(
                tuple(self.converter.read_generated_documents(ROOT)),
                self.DOCUMENT_PATHS,
            )
            self.assertEqual(
                self.converter.read_generated_documents(ROOT), self.documents
            )

    def test_normal_modes_run_in_independent_isolated_processes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "external-sentinel"
            sentinel.write_bytes(b"guarded\n")
            before = self._snapshot_boundary(sentinel)
            commands = (
                self._converter_command(),
                self._converter_command("--check"),
                self._converter_command("--explain", "7zip"),
                (sys.executable, "-B", str(ROOT / "scripts/validate_repository.py")),
            )
            process_ids = []
            for command in commands:
                with self.subTest(command=command):
                    mode_before = self._snapshot_boundary(sentinel)
                    completed = self._run_audited(command, report_process_id=True)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    child_pid, _, child_stdout = completed.stdout.partition(b"\n")
                    self.assertRegex(child_pid, rb"\A[1-9][0-9]*\Z")
                    process_ids.append(int(child_pid))
                    if command[-1] == "--check":
                        self.assertEqual(child_stdout, b"")
                    self.assertEqual(self._snapshot_boundary(sentinel), mode_before)
            self.assertEqual(len(process_ids), len(set(process_ids)))
            self.assertEqual(self._snapshot_boundary(sentinel), before)

    def test_isolated_runner_seals_the_process_launch_contract(self) -> None:
        command = self._converter_command("--check")
        completed = subprocess.CompletedProcess(command, 0, b"", b"")
        with mock.patch.object(subprocess, "run", return_value=completed) as run:
            self.assertIs(self._run_audited(command), completed)
        arguments, options = run.call_args
        self.assertEqual(arguments, (command,))
        self.assertEqual(options["cwd"], ROOT)
        self.assertFalse(options["check"])
        self.assertIsNone(options["executable"])
        self.assertIs(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stdout"], subprocess.PIPE)
        self.assertIs(options["stderr"], subprocess.PIPE)
        self.assertFalse(options["shell"])
        self.assertEqual(options["timeout"], 180)
        self.assertTrue(options["close_fds"])
        self.assertEqual(
            set(options["env"]),
            {
                name
                for name in os.environ
                if name.upper() in IMPORT_PROBE_ENVIRONMENT_NAMES
            }
            | {
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "GIT_CONFIG_SYSTEM",
                "GIT_NO_LAZY_FETCH",
                "GIT_OPTIONAL_LOCKS",
                "GIT_TERMINAL_PROMPT",
                "PYTHONDONTWRITEBYTECODE",
            },
        )
        if os.name == "nt":
            self.assertEqual(
                options["startupinfo"].lpAttributeList, {"handle_list": []}
            )

    def test_controlled_mutants_turn_every_guard_family_red(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "external-sentinel"
            sentinel.write_bytes(b"guarded\n")
            bottle = ROOT / "examples/bottles/7zip-default.json"
            forbidden_locator = self._forbidden_locators()[0]
            second_locator = self._forbidden_locators()[1]
            mutants = {
                "dns": lambda: socket.getaddrinfo("example.invalid", 443),
                "dns-name": lambda: socket.gethostbyname("example.invalid"),
                "dns-name-ex": lambda: socket.gethostbyname_ex("example.invalid"),
                "dns-reverse": lambda: socket.gethostbyaddr("192.0.2.1"),
                "dns-info": lambda: socket.getnameinfo(("192.0.2.1", 443), 0),
                "socket": lambda: socket.socket(),
                "urlopen": lambda: urllib.request.urlopen("https://example.invalid"),
                "urlretrieve": lambda: urllib.request.urlretrieve("https://example.invalid"),
                "subprocess": lambda: subprocess.run(["asset"], check=False),
                "environment": lambda: os.getenv("HOME"),
                "environment-mapping": lambda: self.converter.os.environ["HOME"],
                "environment-global": lambda: os.environ.get("PATH"),
                "environment-items": lambda: tuple(os.environ.items()),
                "home-expansion": lambda: os.path.expanduser("~/asset"),
                "locator-probe": lambda: Path(forbidden_locator).exists(),
                "locator-stat": lambda: Path(forbidden_locator).stat(),
                "locator-open": lambda: Path(forbidden_locator).open("rb"),
                "locator-os-path-exists": lambda: os.path.exists(forbidden_locator),
                "locator-os-stat": lambda: os.stat(forbidden_locator),
                "locator-os-lstat": lambda: os.lstat(forbidden_locator),
                "locator-os-access": lambda: os.access(forbidden_locator, os.F_OK),
                "locator-os-open": lambda: os.open(forbidden_locator, os.O_RDONLY),
                "locator-builtin-open": lambda: builtins.open(forbidden_locator, "rb"),
                "locator-listdir": lambda: os.listdir(forbidden_locator),
                "locator-walk": lambda: next(os.walk(forbidden_locator)),
                "locator-iterdir": lambda: next(Path(forbidden_locator).iterdir()),
                "locator-glob": lambda: next(Path(forbidden_locator).glob("*")),
                "second-locator": lambda: os.path.exists(second_locator),
                "dynamic-import": lambda: importlib.util.spec_from_file_location(
                    "migrated_asset", forbidden_locator
                ),
                "module-import": lambda: importlib.import_module("migrated_asset"),
                "run-path": lambda: runpy.run_path(forbidden_locator),
                "asset-execution": lambda: os.system("asset"),
                "asset-popen": lambda: os.popen("asset"),
                "asset-exec": lambda: os.execv("asset", ("asset",)),
                "asset-compile": lambda: builtins.compile("x = 1", "asset", "exec"),
                "asset-eval": lambda: builtins.eval("1 + 1"),
                "asset-builtin-exec": lambda: builtins.exec("x = 1"),
                "asset-import": lambda: builtins.__import__("migrated_asset"),
                "bottle-access": lambda: bottle.read_bytes(),
                "external-write": lambda: sentinel.write_bytes(b"mutated\n"),
            }
            with self._guard_external_effects(sentinel):
                for family, mutant in mutants.items():
                    with self.subTest(family=family), mock.patch.object(
                        self.converter,
                        "build_conversion",
                        side_effect=lambda *_args, _mutant=mutant, **_kwargs: _mutant(),
                    ), self.assertRaisesRegex(AssertionError, "side effect blocked"):
                        self.converter.main(("--check",))

                code, stdout, stderr = self._run_main(("--check",))
                self.assertEqual((code, stdout, stderr), (0, b"", b""))

            with self._guard_external_effects(sentinel):
                for locator in self._forbidden_evidence_values():
                    with self.subTest(locator=locator), self.assertRaisesRegex(
                        AssertionError, "side effect blocked"
                    ):
                        os.path.exists(locator)

    def test_read_only_firewall_rejects_transient_and_persistent_write_mutants(self) -> None:
        generated = ROOT / "migration/macwin/generated"
        transient = generated / "transient-side-effect"
        persistent = generated / "persistent-side-effect"

        def transient_mutant(*_args, **_kwargs):
            transient.write_bytes(b"escaped")
            transient.unlink()
            return self.result

        def persistent_mutant(*_args, **_kwargs):
            persistent.write_bytes(b"escaped")
            return self.result

        try:
            for name, mutant in (
                ("transient", transient_mutant),
                ("persistent", persistent_mutant),
            ):
                with self.subTest(mutant=name), self._guard_read_only_writes(), mock.patch.object(
                    self.converter, "build_conversion", side_effect=mutant
                ), self.assertRaisesRegex(AssertionError, "side effect blocked"):
                    self.converter.main(("--check",))
        finally:
            transient.unlink(missing_ok=True)
            persistent.unlink(missing_ok=True)

        catalog = generated / "catalog.json"
        original_times = (catalog.stat().st_atime_ns, catalog.stat().st_mtime_ns)
        metadata_mutants = {
            "utime": lambda: (
                os.utime(catalog, ns=(original_times[0], original_times[1] - 1)),
                os.utime(catalog, ns=original_times),
            ),
            "chmod": lambda: os.chmod(catalog, catalog.stat().st_mode),
            "truncate": lambda: os.truncate(catalog, catalog.stat().st_size),
            "hardlink": lambda: (
                os.link(catalog, generated / "transient-hardlink"),
                os.unlink(generated / "transient-hardlink"),
            ),
            "symlink": lambda: (
                os.symlink(catalog, generated / "transient-symlink"),
                os.unlink(generated / "transient-symlink"),
            ),
        }
        for name, mutant in metadata_mutants.items():
            with self.subTest(mutant=name), self._guard_read_only_writes(), mock.patch.object(
                self.converter,
                "build_conversion",
                side_effect=lambda *_args, _mutant=mutant, **_kwargs: (
                    _mutant(),
                    self.result,
                )[1],
            ), self.assertRaisesRegex(AssertionError, "side effect blocked"):
                self.converter.main(("--check",))

    def test_tree_snapshot_binds_empty_directories_and_nonregular_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty"
            empty.mkdir()
            regular = root / "regular"
            regular.write_bytes(b"content")
            snapshot = self._snapshot_tree(root)
            self.assertTrue(
                any(record[:2] == ("empty", "directory") for record in snapshot)
            )
            before = snapshot
            empty.rmdir()
            empty.mkdir()
            self.assertNotEqual(self._snapshot_tree(root), before)
            linked = root / "linked"
            try:
                os.symlink(regular, linked)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink snapshot contract unavailable: {error}")
            if os.name == "nt":
                with self.assertRaisesRegex(AssertionError, "reparse point"):
                    self._snapshot_tree(root)
            else:
                snapshot = self._snapshot_tree(root)
                self.assertTrue(
                    any(record[:2] == ("linked", "symlink") for record in snapshot)
                )

    def test_snapshot_never_opens_a_linked_leaf_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            external = Path(directory).with_name(Path(directory).name + "-external")
            external.write_bytes(b"secret")
            linked = root / "linked-leaf"
            opened = False
            real_open = self.converter._open_source_leaf_descriptor
            try:
                os.symlink(external, linked)
            except (OSError, NotImplementedError) as error:
                external.unlink(missing_ok=True)
                self.skipTest(f"linked leaf contract unavailable: {error}")

            def observe_open(path):
                nonlocal opened
                if path == linked:
                    opened = True
                return real_open(path)

            try:
                with mock.patch.object(
                    self.converter, "_open_source_leaf_descriptor", observe_open
                ), self.assertRaisesRegex(AssertionError, "reparse point") if os.name == "nt" else contextlib.nullcontext():
                    snapshot = self._snapshot_tree(root)
                    if os.name != "nt":
                        self.assertTrue(any(row[:2] == ("linked-leaf", "symlink") for row in snapshot))
            finally:
                external.unlink(missing_ok=True)
            self.assertFalse(opened)

    def test_approved_write_scope_is_exact_and_repeat_is_a_no_op(self) -> None:
        before_repository = self._snapshot_tree(ROOT, exclude_generated=True)
        before_source = self._snapshot_tree(ROOT / "migration/macwin/source")
        first = self.converter.read_generated_documents(ROOT)
        with self._guard_read_only_writes():
            self.converter.write_generated_documents(ROOT, self.documents)
        second = self.converter.read_generated_documents(ROOT)
        with self._guard_read_only_writes():
            self.converter.write_generated_documents(ROOT, self.documents)
        third = self.converter.read_generated_documents(ROOT)
        self.assertEqual(first, self.documents)
        self.assertEqual(second, first)
        self.assertEqual(third, first)
        self.assertEqual(self._snapshot_tree(ROOT, exclude_generated=True), before_repository)
        self.assertEqual(self._snapshot_tree(ROOT / "migration/macwin/source"), before_source)
        self.assertFalse(
            any(
                ".compatforge-transaction" in path.as_posix()
                for path in (ROOT / "migration/macwin/generated").rglob("*")
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            generated.mkdir(parents=True)
            sentinel = root / "outside-generated"
            sentinel.write_bytes(b"unchanged\n")
            self._write_document_map(root, self.documents)
            (generated / "catalog.json").write_bytes(b"stale\n")
            outside_before = self._snapshot_tree(root, exclude_generated=True)
            with self._audit_write_scope(generated) as events:
                self.converter.write_generated_documents(root, self.documents)
            self.assertEqual(self.converter.read_generated_documents(root), self.documents)
            self.assertEqual(self._snapshot_tree(root, exclude_generated=True), outside_before)
            self.assertTrue(events)
            self.assertTrue(all(self._path_is_within(path, generated) for path in events))
            with self._audit_write_scope(generated) as repeat_events:
                self.converter.write_generated_documents(root, self.documents)
            self.assertEqual(repeat_events, [])

            outside = root / "transient-outside"

            def escape_then_write(*args, **kwargs):
                outside.write_bytes(b"escaped")
                outside.unlink()
                return self.converter.write_generated_documents(*args, **kwargs)

            with self._audit_write_scope(generated), self.assertRaisesRegex(
                AssertionError, "side effect blocked"
            ):
                escape_then_write(root, self.documents)

            original = outside.read_text(encoding="utf-8") if outside.exists() else None
            with self._audit_write_scope(generated), self.assertRaisesRegex(
                AssertionError, "side effect blocked"
            ):
                outside.write_text("mutated", encoding="utf-8")
                if original is not None:
                    outside.write_text(original, encoding="utf-8")

            external_directory = root / "external-directory"
            external_directory.mkdir()
            link = generated / "escape-link"
            try:
                os.symlink(external_directory, link, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"write audit symlink contract unavailable: {error}")
            with self._audit_write_scope(generated), self.assertRaisesRegex(
                AssertionError, "side effect blocked"
            ):
                (link / "escaped").write_bytes(b"escaped")
            self.assertFalse((external_directory / "escaped").exists())

            external_file = root / "external-file"
            external_file.write_bytes(b"original")
            linked_leaf = generated / "linked-leaf"
            try:
                os.symlink(external_file, linked_leaf)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"write audit leaf link contract unavailable: {error}")
            with self._audit_write_scope(generated), self.assertRaisesRegex(
                AssertionError, "side effect blocked"
            ):
                linked_leaf.write_bytes(b"escaped")
            self.assertEqual(external_file.read_bytes(), b"original")

            descriptor = os.open(external_file, os.O_RDWR)
            try:
                with self.assertRaisesRegex(AssertionError, "side effect blocked"):
                    with self._audit_write_scope(generated):
                        os.write(descriptor, b"mutated!")
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        os.write(descriptor, b"original")
            finally:
                os.close(descriptor)
            self.assertEqual(external_file.read_bytes(), b"original")

    def test_git_snapshot_distinguishes_missing_and_dangling_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git_directory = root / "worktree"
            common = root / "common"
            git_directory.mkdir()
            common.mkdir()
            with mock.patch.object(
                self, "_git_absolute_path", side_effect=(git_directory, common)
            ):
                missing = self._snapshot_git_metadata()
            dangling = common / "reftable"
            try:
                os.symlink(root / "missing-target", dangling, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"dangling git metadata contract unavailable: {error}")
            with mock.patch.object(
                self, "_git_absolute_path", side_effect=(git_directory, common)
            ):
                if os.name == "nt":
                    with self.assertRaisesRegex(AssertionError, "reparse point"):
                        self._snapshot_git_metadata()
                else:
                    linked = self._snapshot_git_metadata()
                    self.assertNotEqual(missing, linked)

    def test_write_audit_rejects_preopened_stream_and_native_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "migration/macwin/generated"
            generated.mkdir(parents=True)
            outside = root / "outside"
            outside.write_bytes(b"original")

            with outside.open("rb"):
                with self._audit_write_scope(generated) as events:
                    pass
            self.assertEqual(events, [])

            with outside.open("r+b", buffering=0) as stream:
                with self.assertRaisesRegex(AssertionError, "side effect blocked"):
                    with self._audit_write_scope(generated):
                        stream.write(b"mutated")
                        stream.seek(0)
                        stream.write(b"original")
            self.assertEqual(outside.read_bytes(), b"original")

            if os.name == "nt":
                import ctypes

                descriptor = os.open(outside, os.O_RDWR)
                try:
                    runtime = ctypes.CDLL("ucrtbase", use_errno=True)
                    native_write = runtime._write
                    native_write.argtypes = (
                        ctypes.c_int,
                        ctypes.c_void_p,
                        ctypes.c_uint,
                    )
                    native_write.restype = ctypes.c_int
                    mutated = ctypes.create_string_buffer(b"mutated")
                    original = ctypes.create_string_buffer(b"original")
                    with self.assertRaisesRegex(AssertionError, "side effect blocked"):
                        with self._audit_write_scope(generated):
                            self.assertEqual(
                                native_write(descriptor, mutated, len(b"mutated")),
                                len(b"mutated"),
                            )
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            self.assertEqual(
                                native_write(descriptor, original, len(b"original")),
                                len(b"original"),
                            )
                finally:
                    os.close(descriptor)
                self.assertEqual(outside.read_bytes(), b"original")

    def test_isolated_check_cannot_execute_parent_mapping_or_raw_handle_mutants(self) -> None:
        import mmap

        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "native-sentinel"
            sentinel.write_bytes(b"original")
            descriptor = os.open(sentinel, os.O_RDWR)
            try:
                mapping = mmap.mmap(descriptor, 0, access=mmap.ACCESS_WRITE)
            finally:
                os.close(descriptor)
            mapping_evidence = []

            def mapping_mutant(*_args, **_kwargs):
                mapping.seek(0)
                mapping.write(b"mutated!")
                mapping.flush()
                mapping_evidence.append(sentinel.read_bytes())
                mapping.seek(0)
                mapping.write(b"original")
                mapping.flush()
                return self.result

            try:
                mapping_mutant()
                self.assertEqual(mapping_evidence, [b"mutated!"])
                self.assertEqual(sentinel.read_bytes(), b"original")
                mapping_evidence.clear()
                before = self._snapshot_boundary(sentinel)
                with mock.patch.object(
                    self.converter, "build_conversion", side_effect=mapping_mutant
                ):
                    completed = self._run_audited(
                        self._converter_command("--check"), report_process_id=True
                    )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(mapping_evidence, [])
                self.assertEqual(self._snapshot_boundary(sentinel), before)
            finally:
                mapping.close()

            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                class SecurityAttributes(ctypes.Structure):
                    _fields_ = (
                        ("nLength", wintypes.DWORD),
                        ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", wintypes.BOOL),
                    )

                security = SecurityAttributes()
                security.nLength = ctypes.sizeof(security)
                security.bInheritHandle = True
                create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
                create_file.argtypes = (
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.POINTER(SecurityAttributes),
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.HANDLE,
                )
                create_file.restype = wintypes.HANDLE
                handle = create_file(
                    str(sentinel),
                    0x80000000 | 0x40000000,
                    0x1 | 0x2 | 0x4,
                    ctypes.byref(security),
                    3,
                    0x80,
                    None,
                )
                self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                write_file = kernel32.WriteFile
                write_file.argtypes = (
                    wintypes.HANDLE,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    ctypes.POINTER(wintypes.DWORD),
                    ctypes.c_void_p,
                )
                write_file.restype = wintypes.BOOL
                set_pointer = kernel32.SetFilePointer
                set_pointer.argtypes = (
                    wintypes.HANDLE,
                    wintypes.LONG,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                )
                set_pointer.restype = wintypes.DWORD
                handle_evidence = []

                def handle_write(raw: bytes) -> None:
                    self.assertNotEqual(set_pointer(handle, 0, None, 0), 0xFFFFFFFF)
                    buffer = ctypes.create_string_buffer(raw)
                    written = wintypes.DWORD()
                    self.assertTrue(
                        write_file(
                            handle,
                            buffer,
                            len(raw),
                            ctypes.byref(written),
                            None,
                        )
                    )
                    self.assertEqual(written.value, len(raw))

                def handle_mutant(*_args, **_kwargs):
                    handle_write(b"mutated!")
                    handle_evidence.append(sentinel.read_bytes())
                    handle_write(b"original")
                    return self.result

                try:
                    handle_mutant()
                    self.assertEqual(handle_evidence, [b"mutated!"])
                    self.assertEqual(sentinel.read_bytes(), b"original")
                    handle_evidence.clear()
                    before = self._snapshot_boundary(sentinel)
                    with mock.patch.object(
                        self.converter, "build_conversion", side_effect=handle_mutant
                    ):
                        completed = self._run_audited(
                            self._converter_command("--check"), report_process_id=True
                        )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(handle_evidence, [])
                    self.assertEqual(self._snapshot_boundary(sentinel), before)
                finally:
                    kernel32.CloseHandle(handle)

    def test_snapshot_rejects_a_directory_swap_before_external_content_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            external = root / "external"
            child.mkdir()
            external.mkdir()
            (child / "inside").write_bytes(b"inside")
            secret = external / "secret"
            secret.write_bytes(b"external-secret")
            saved = root / "saved-child"
            real_scandir = os.scandir
            real_reader = self._read_bound_snapshot_file
            external_read = False
            swapped = False
            swap_blocked = False
            scan_count = 0

            def swap_before_child_scan(target):
                nonlocal scan_count, swap_blocked, swapped
                scan_count += 1
                target_path = Path(target) if not isinstance(target, int) else None
                if (target_path == child or scan_count == 2) and not swapped:
                    try:
                        child.rename(saved)
                    except OSError:
                        swap_blocked = True
                        raise AssertionError("directory replacement blocked") from None
                    os.symlink(external, child, target_is_directory=True)
                    swapped = True
                return real_scandir(target)

            def observe_reader(path, **kwargs):
                nonlocal external_read
                if path == secret or external in path.parents:
                    external_read = True
                return real_reader(path, **kwargs)

            try:
                with mock.patch.object(os, "scandir", swap_before_child_scan), mock.patch.object(
                    self, "_read_bound_snapshot_file", observe_reader
                ), self.assertRaises((AssertionError, self.converter.ConversionError)):
                    self._snapshot_tree(root)
            except NotImplementedError as error:
                self.skipTest(f"directory swap contract unavailable: {error}")
            finally:
                if child.is_symlink():
                    child.unlink()
                if saved.exists():
                    saved.rename(child)
            self.assertTrue(swapped or swap_blocked)
            self.assertFalse(external_read)

    @staticmethod
    def _write_document_map(root: Path, documents: dict[str, bytes]) -> None:
        for relative, raw in documents.items():
            path = root / PurePosixPath(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    @contextlib.contextmanager
    def _guard_external_effects(
        self, sentinel: Path, *, allow_audited_environment_items: bool = False
    ):
        real_builtin_open = builtins.open
        real_io_open = io.open
        real_os_access = os.access
        real_os_lstat = os.lstat
        real_os_listdir = os.listdir
        real_os_open = os.open
        real_os_scandir = os.scandir
        real_os_stat = os.stat
        real_path_exists = os.path.exists
        real_path_isdir = os.path.isdir
        real_path_isfile = os.path.isfile
        real_path_lexists = os.path.lexists
        real_open = Path.open
        real_iterdir = Path.iterdir
        real_glob = Path.glob
        real_rglob = Path.rglob
        real_stat = Path.stat
        real_exists = Path.exists
        real_read_bytes = Path.read_bytes
        real_write_bytes = Path.write_bytes
        forbidden_roots = (
            (ROOT / "examples/bottles").absolute(),
            (ROOT / "examples/runtime-packs").absolute(),
            (ROOT / "tests/fixtures/runtime-packs").absolute(),
        )
        locator_values = self._forbidden_evidence_values()
        forbidden_values = frozenset({str(sentinel.absolute()), *locator_values})
        allowed_environment = tuple(
            (key, value)
            for key, value in os.environ.items()
            if key.upper() in IMPORT_PROBE_ENVIRONMENT_NAMES
        )

        def blocked(*_args, **_kwargs):
            raise AssertionError("side effect blocked")

        class GuardedEnvironment:
            def items(self):
                if not allow_audited_environment_items:
                    blocked()
                return allowed_environment

            def __getitem__(self, _key):
                blocked()

            def get(self, _key, _default=None):
                blocked()

            def __iter__(self):
                blocked()

            def __contains__(self, _key):
                blocked()

        def path_is_forbidden(path) -> bool:
            if isinstance(path, int):
                return False
            try:
                value = os.fsdecode(os.fspath(path))
            except TypeError:
                return False
            portable_value = value.replace("\\", "/")
            if value in forbidden_values or portable_value in forbidden_values:
                return True
            candidate = Path(value)
            absolute = candidate.absolute()
            return any(
                absolute == root or root in absolute.parents for root in forbidden_roots
            ) or (
                absolute != ROOT
                and ROOT not in absolute.parents
                and absolute not in ROOT.parents
            )

        def guard_path(path):
            if path_is_forbidden(path):
                blocked()

        def guarded_builtin_open(path, *args, **kwargs):
            guard_path(path)
            return real_builtin_open(path, *args, **kwargs)

        def guarded_io_open(path, *args, **kwargs):
            guard_path(path)
            return real_io_open(path, *args, **kwargs)

        def guarded_os_access(path, *args, **kwargs):
            guard_path(path)
            return real_os_access(path, *args, **kwargs)

        def guarded_os_lstat(path, *args, **kwargs):
            guard_path(path)
            return real_os_lstat(path, *args, **kwargs)

        def guarded_os_listdir(path="."):
            guard_path(path)
            return real_os_listdir(path)

        def guarded_os_open(path, *args, **kwargs):
            guard_path(path)
            return real_os_open(path, *args, **kwargs)

        def guarded_os_scandir(path="."):
            guard_path(path)
            return real_os_scandir(path)

        def guarded_os_stat(path, *args, **kwargs):
            guard_path(path)
            return real_os_stat(path, *args, **kwargs)

        def guarded_path_predicate(real_function):
            def wrapper(path):
                guard_path(path)
                return real_function(path)
            return wrapper

        def guarded_open(path: Path, *args, **kwargs):
            if path_is_forbidden(path):
                blocked()
            return real_open(path, *args, **kwargs)

        def guarded_stat(path: Path, *args, **kwargs):
            if path_is_forbidden(path):
                blocked()
            return real_stat(path, *args, **kwargs)

        def guarded_exists(path: Path, *args, **kwargs):
            if path_is_forbidden(path):
                blocked()
            return real_exists(path, *args, **kwargs)

        def guarded_read_bytes(path: Path):
            if path_is_forbidden(path):
                blocked()
            return real_read_bytes(path)

        def guarded_write_bytes(path: Path, data: bytes):
            if path_is_forbidden(path):
                blocked()
            return real_write_bytes(path, data)

        def guarded_iterdir(path: Path):
            guard_path(path)
            return real_iterdir(path)

        def guarded_glob(path: Path, pattern: str, *args, **kwargs):
            guard_path(path)
            return real_glob(path, pattern, *args, **kwargs)

        def guarded_rglob(path: Path, pattern: str, *args, **kwargs):
            guard_path(path)
            return real_rglob(path, pattern, *args, **kwargs)

        patches = [
            mock.patch.object(socket, "socket", side_effect=blocked),
            mock.patch.object(socket, "create_connection", side_effect=blocked),
            mock.patch.object(socket, "getaddrinfo", side_effect=blocked),
            mock.patch.object(socket, "gethostbyname", side_effect=blocked),
            mock.patch.object(socket, "gethostbyname_ex", side_effect=blocked),
            mock.patch.object(socket, "gethostbyaddr", side_effect=blocked),
            mock.patch.object(socket, "getnameinfo", side_effect=blocked),
            mock.patch.object(urllib.request, "urlopen", side_effect=blocked),
            mock.patch.object(urllib.request, "urlretrieve", side_effect=blocked),
            mock.patch.object(subprocess, "Popen", side_effect=blocked),
            mock.patch.object(subprocess, "run", side_effect=blocked),
            mock.patch.object(subprocess, "check_call", side_effect=blocked),
            mock.patch.object(subprocess, "check_output", side_effect=blocked),
            mock.patch.object(os, "getenv", side_effect=blocked),
            mock.patch.object(os, "environ", GuardedEnvironment()),
            mock.patch.object(os.path, "expanduser", side_effect=blocked),
            mock.patch.object(Path, "expanduser", side_effect=blocked),
            mock.patch.object(importlib.util, "spec_from_file_location", side_effect=blocked),
            mock.patch.object(importlib, "import_module", side_effect=blocked),
            mock.patch.object(runpy, "run_path", side_effect=blocked),
            mock.patch.object(self.converter.argparse, "_", lambda value: value),
            mock.patch.object(os, "system", side_effect=blocked),
            mock.patch.object(os, "popen", side_effect=blocked),
            mock.patch.object(os, "stat", guarded_os_stat),
            mock.patch.object(os, "lstat", guarded_os_lstat),
            mock.patch.object(os, "listdir", guarded_os_listdir),
            mock.patch.object(os, "walk", side_effect=blocked),
            mock.patch.object(os, "access", guarded_os_access),
            mock.patch.object(os, "open", guarded_os_open),
            mock.patch.object(os, "scandir", guarded_os_scandir),
            mock.patch.object(os.path, "exists", guarded_path_predicate(real_path_exists)),
            mock.patch.object(os.path, "lexists", guarded_path_predicate(real_path_lexists)),
            mock.patch.object(os.path, "isfile", guarded_path_predicate(real_path_isfile)),
            mock.patch.object(os.path, "isdir", guarded_path_predicate(real_path_isdir)),
            mock.patch.object(builtins, "open", guarded_builtin_open),
            mock.patch.object(io, "open", guarded_io_open),
            mock.patch.object(Path, "open", guarded_open),
            mock.patch.object(Path, "stat", guarded_stat),
            mock.patch.object(Path, "exists", guarded_exists),
            mock.patch.object(Path, "read_bytes", guarded_read_bytes),
            mock.patch.object(Path, "write_bytes", guarded_write_bytes),
            mock.patch.object(Path, "iterdir", guarded_iterdir),
            mock.patch.object(Path, "glob", guarded_glob),
            mock.patch.object(Path, "rglob", guarded_rglob),
            mock.patch.object(builtins, "compile", side_effect=blocked),
            mock.patch.object(builtins, "eval", side_effect=blocked),
            mock.patch.object(builtins, "exec", side_effect=blocked),
            mock.patch.object(builtins, "__import__", side_effect=blocked),
        ]
        for name in (
            "execl",
            "execle",
            "execlp",
            "execlpe",
            "execv",
            "execve",
            "execvp",
            "execvpe",
            "spawnl",
            "spawnle",
            "spawnlp",
            "spawnlpe",
            "spawnv",
            "spawnve",
            "spawnvp",
            "spawnvpe",
            "startfile",
        ):
            if hasattr(os, name):
                patches.append(mock.patch.object(os, name, side_effect=blocked))
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            yield

    @contextlib.contextmanager
    def _guard_read_only_writes(self):
        real_builtin_open = builtins.open
        real_io_open = io.open
        real_os_open = os.open
        write_flags = (
            os.O_WRONLY
            | os.O_RDWR
            | os.O_APPEND
            | os.O_CREAT
            | os.O_TRUNC
        )

        def blocked(*_args, **_kwargs):
            raise AssertionError("side effect blocked")

        def guarded_os_open(path, flags, *args, **kwargs):
            if flags & write_flags:
                blocked()
            return real_os_open(path, flags, *args, **kwargs)

        def guarded_stream_open(real_function):
            def wrapper(path, mode="r", *args, **kwargs):
                if any(character in mode for character in "wax+"):
                    blocked()
                return real_function(path, mode, *args, **kwargs)
            return wrapper

        patches = [
            mock.patch.object(os, "open", guarded_os_open),
            mock.patch.object(builtins, "open", guarded_stream_open(real_builtin_open)),
            mock.patch.object(io, "open", guarded_stream_open(real_io_open)),
        ]
        for owner, names in (
            (os, ("write", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "rmdir", "utime", "chmod", "chown", "truncate", "link", "symlink")),
            (Path, ("write_bytes", "write_text", "touch", "mkdir", "unlink", "rename", "replace", "rmdir")),
            (tempfile, ("NamedTemporaryFile", "TemporaryFile", "mkdtemp", "mkstemp")),
        ):
            for name in names:
                if hasattr(owner, name):
                    patches.append(mock.patch.object(owner, name, side_effect=blocked))
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            yield

    @contextlib.contextmanager
    def _audit_write_scope(self, approved_root: Path):
        approved_root = approved_root.absolute()
        self._reject_preexisting_writable_regular_descriptors()
        events: list[Path] = []
        patches = []
        root_metadata = os.lstat(approved_root)
        root_identity = self._snapshot_identity(root_metadata)
        descriptor_paths: dict[int, Path] = {}
        descriptor_identities: dict[int, tuple[int, int, int]] = {}

        def resolved_path(value, *, dir_fd=None):
            path = Path(os.fsdecode(os.fspath(value)))
            if not path.is_absolute():
                if dir_fd is None:
                    path = Path.cwd() / path
                elif dir_fd in descriptor_paths:
                    path = descriptor_paths[dir_fd] / path
                else:
                    raise AssertionError("side effect blocked")
            return path.absolute()

        def audit_path(value, *, dir_fd=None):
            if isinstance(value, int):
                return
            path = resolved_path(value, dir_fd=dir_fd)
            if not self._path_is_within(path, approved_root):
                raise AssertionError("side effect blocked")
            if self._snapshot_identity(os.lstat(approved_root)) != root_identity:
                raise AssertionError("side effect blocked")
            current = approved_root
            relative_parts = path.relative_to(approved_root).parts
            for component in relative_parts[:-1]:
                current = current / component
                try:
                    metadata = os.lstat(current)
                except FileNotFoundError:
                    break
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or getattr(metadata, "st_reparse_tag", 0)
                    or getattr(metadata, "st_file_attributes", 0) & 0x400
                ):
                    raise AssertionError("side effect blocked")
            if relative_parts:
                try:
                    final = os.lstat(path)
                except FileNotFoundError:
                    pass
                else:
                    if stat.S_ISLNK(final.st_mode) or getattr(
                        final, "st_reparse_tag", 0
                    ) or getattr(final, "st_file_attributes", 0) & 0x400:
                        raise AssertionError("side effect blocked")
            events.append(path)

        def wrap(owner, name, path_indexes=(0,)):
            real = getattr(owner, name)
            def guarded(*args, **kwargs):
                dir_fd = kwargs.get("dir_fd")
                for index in path_indexes:
                    if index < len(args):
                        audit_path(args[index], dir_fd=dir_fd)
                return real(*args, **kwargs)
            patches.append(mock.patch.object(owner, name, guarded))

        for name in ("unlink", "remove", "mkdir", "makedirs", "rmdir", "utime", "chmod", "chown", "truncate"):
            if hasattr(os, name):
                wrap(os, name)
        for name in ("replace", "rename", "link", "symlink"):
            if hasattr(os, name):
                wrap(os, name, (0, 1))
        real_os_open = os.open
        real_os_close = os.close
        real_os_write = os.write
        real_os_ftruncate = os.ftruncate
        real_os_fchmod = getattr(os, "fchmod", None)
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
        def guarded_os_open(path, flags, *args, **kwargs):
            dir_fd = kwargs.get("dir_fd")
            if flags & write_flags:
                audit_path(path, dir_fd=dir_fd)
            descriptor = real_os_open(path, flags, *args, **kwargs)
            try:
                metadata = os.fstat(descriptor)
                opened = resolved_path(path, dir_fd=dir_fd)
                if self._path_is_within(opened, approved_root) and (
                    flags & write_flags or stat.S_ISDIR(metadata.st_mode)
                ):
                    descriptor_paths[descriptor] = opened
                    descriptor_identities[descriptor] = self._snapshot_identity(metadata)
            except BaseException:
                real_os_close(descriptor)
                raise
            return descriptor
        def guarded_os_close(descriptor):
            descriptor_paths.pop(descriptor, None)
            descriptor_identities.pop(descriptor, None)
            return real_os_close(descriptor)
        def audit_descriptor(descriptor):
            if descriptor not in descriptor_paths or descriptor not in descriptor_identities:
                raise AssertionError("side effect blocked")
            if self._snapshot_identity(os.fstat(descriptor)) != descriptor_identities[descriptor]:
                raise AssertionError("side effect blocked")
            audit_path(descriptor_paths[descriptor])
        def guarded_os_write(descriptor, data):
            audit_descriptor(descriptor)
            return real_os_write(descriptor, data)
        def guarded_os_ftruncate(descriptor, length):
            audit_descriptor(descriptor)
            return real_os_ftruncate(descriptor, length)
        patches.append(mock.patch.object(os, "open", guarded_os_open))
        patches.append(mock.patch.object(os, "close", guarded_os_close))
        patches.append(mock.patch.object(os, "write", guarded_os_write))
        patches.append(mock.patch.object(os, "ftruncate", guarded_os_ftruncate))
        if real_os_fchmod is not None:
            def guarded_os_fchmod(descriptor, mode):
                audit_descriptor(descriptor)
                return real_os_fchmod(descriptor, mode)
            patches.append(mock.patch.object(os, "fchmod", guarded_os_fchmod))
        real_builtin_open = builtins.open
        real_io_open = io.open
        def guard_stream(real_function):
            def guarded(path, mode="r", *args, **kwargs):
                if any(character in mode for character in "wax+"):
                    audit_path(path)
                return real_function(path, mode, *args, **kwargs)
            return guarded
        patches.append(mock.patch.object(builtins, "open", guard_stream(real_builtin_open)))
        patches.append(mock.patch.object(io, "open", guard_stream(real_io_open)))
        real_move = getattr(self.converter, "_MOVE_FILE", None)
        real_replace = getattr(self.converter, "_REPLACE_FILE", None)
        if real_move is not None:
            def guarded_move(source, destination, *args):
                audit_path(source)
                audit_path(destination)
                return real_move(source, destination, *args)
            patches.append(mock.patch.object(self.converter, "_MOVE_FILE", guarded_move))
        if real_replace is not None:
            def guarded_replace(destination, replacement, *args):
                audit_path(destination)
                audit_path(replacement)
                return real_replace(destination, replacement, *args)
            patches.append(mock.patch.object(self.converter, "_REPLACE_FILE", guarded_replace))
        for name, path_count in (
            ("_posix_rename", 2),
            ("_atomic_move_no_replace", 2),
            ("_atomic_replace_with_displaced", 3),
            ("_install_staged_leaf", 2),
        ):
            real_function = getattr(self.converter, name)
            def make_guarded(function, count):
                def guarded(*args, **kwargs):
                    for value in args[:count]:
                        audit_path(value)
                    return function(*args, **kwargs)
                return guarded
            patches.append(
                mock.patch.object(
                    self.converter, name, make_guarded(real_function, path_count)
                )
            )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            yield events

    @staticmethod
    def _reject_preexisting_writable_regular_descriptors() -> None:
        if os.name == "nt":
            import ctypes
            import msvcrt

            runtime = ctypes.CDLL("ucrtbase")
            get_maximum = runtime._getmaxstdio
            get_maximum.argtypes = ()
            get_maximum.restype = ctypes.c_int
            candidates = range(get_maximum())
            ntdll = ctypes.WinDLL("ntdll")
            query = ntdll.NtQueryInformationFile
            query.argtypes = (
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_int,
            )
            query.restype = ctypes.c_long
            write_access = (
                0x0002
                | 0x0004
                | 0x0010
                | 0x0100
                | 0x00010000
                | 0x00040000
                | 0x00080000
            )

            def descriptor_is_writable(descriptor: int) -> bool:
                handle = msvcrt.get_osfhandle(descriptor)
                status = (ctypes.c_ubyte * (2 * ctypes.sizeof(ctypes.c_void_p)))()
                access = ctypes.c_uint32()
                if query(
                    ctypes.c_void_p(handle),
                    status,
                    ctypes.byref(access),
                    ctypes.sizeof(access),
                    8,
                ) != 0:
                    raise AssertionError("side effect blocked")
                return bool(access.value & write_access)
        else:
            import fcntl
            import resource

            candidates = None
            for directory in (Path("/proc/self/fd"), Path("/dev/fd")):
                try:
                    candidates = tuple(
                        int(entry.name)
                        for entry in os.scandir(directory)
                        if entry.name.isascii() and entry.name.isdecimal()
                    )
                except OSError:
                    continue
                break
            if candidates is None:
                maximum, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
                candidates = range(maximum)

            def descriptor_is_writable(descriptor: int) -> bool:
                flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
                return flags & os.O_ACCMODE != os.O_RDONLY

        for descriptor in candidates:
            try:
                metadata = os.fstat(descriptor)
                writable = descriptor_is_writable(descriptor)
            except (OSError, ValueError):
                continue
            if stat.S_ISREG(metadata.st_mode) and writable:
                raise AssertionError("side effect blocked")

    @staticmethod
    def _path_is_within(path: Path, root: Path) -> bool:
        path = path.absolute()
        root = root.absolute()
        return path == root or root in path.parents

    def _snapshot_boundary(self, sentinel: Path) -> dict[str, object]:
        return {
            "source": self._snapshot_tree(ROOT / "migration/macwin/source"),
            "generated": self._snapshot_tree(ROOT / "migration/macwin/generated"),
            "runtime": self._snapshot_tree(ROOT / "examples/runtime-packs"),
            "runtime-fixtures": self._snapshot_tree(ROOT / "tests/fixtures/runtime-packs"),
            "bottles": self._snapshot_tree(ROOT / "examples/bottles"),
            "git": self._snapshot_git_metadata(),
            "git-status": self._git_status(),
            "sentinel": sentinel.read_bytes(),
            "environment": tuple(sorted(os.environ.items())),
            "cwd": os.getcwd(),
            "argv": tuple(sys.argv),
            "caches": tuple(
                sorted(
                    path.relative_to(ROOT).as_posix()
                    for path in ROOT.rglob("*")
                    if path.name == "__pycache__"
                    or path.suffix in {".pyc", ".pyo"}
                )
            ),
        }

    def _snapshot_git_metadata(self) -> dict[str, object]:
        git_directory = self._git_absolute_path("--absolute-git-dir")
        common_directory = self._git_absolute_path("--git-common-dir")
        paths = {
            "worktree-admin": git_directory,
            "common-config": common_directory / "config",
            "common-objects": common_directory / "objects",
            "common-packed-refs": common_directory / "packed-refs",
            "common-refs": common_directory / "refs",
            "common-reftable": common_directory / "reftable",
            "worktree-config": git_directory / "config.worktree",
            "worktree-head": git_directory / "HEAD",
            "worktree-index": git_directory / "index",
            "worktree-refs": git_directory / "refs",
            "worktree-reftable": git_directory / "reftable",
        }
        result: dict[str, object] = {}
        for name, path in paths.items():
            try:
                os.lstat(path)
            except FileNotFoundError:
                result[name] = None
            else:
                result[name] = self._snapshot_tree(path)
        return result

    def _git_absolute_path(self, option: str) -> Path:
        completed = self._run_audited(
            ("git", "rev-parse", "--path-format=absolute", option)
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        path = Path(completed.stdout.decode("utf-8").strip())
        return path if path.is_absolute() else (ROOT / path).absolute()

    def _snapshot_tree(self, root: Path, *, exclude_generated: bool = False):
        root_metadata = os.lstat(root)
        self._reject_snapshot_reparse(root_metadata)
        if stat.S_ISLNK(root_metadata.st_mode):
            return ((root.name, "symlink", os.readlink(root)),)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raw, identity = self._read_bound_snapshot_file(root)
            return ((root.name, "file", len(raw), hashlib.sha256(raw).hexdigest(), identity),)
        root_identity = self._snapshot_identity(root_metadata)
        records: list[tuple[object, ...]] = [(".", "directory", root_identity)]
        generated = (root / "migration/macwin/generated").absolute()
        held_root = self.converter._hold_generated_directories([root])[0]

        def scan(directory, prefix: str) -> None:
            self.converter._verify_held_generated_directories([directory])
            scan_target = directory.handle if os.name != "nt" else directory.path
            with os.scandir(scan_target) as iterator:
                entries = sorted(list(iterator), key=lambda entry: os.fsencode(entry.name))
            self.converter._verify_held_generated_directories([directory])
            for entry in entries:
                path = directory.path / entry.name
                relative = f"{prefix}/{entry.name}" if prefix else entry.name
                absolute = path.absolute()
                if exclude_generated and (absolute == generated or generated in absolute.parents):
                    continue
                metadata = os.lstat(path)
                self._reject_snapshot_reparse(metadata)
                identity = self._snapshot_identity(metadata)
                if stat.S_ISDIR(metadata.st_mode):
                    records.append((relative, "directory", identity))
                    child = self.converter._open_bound_child(directory, entry.name)
                    try:
                        opened_identity = (
                            self._snapshot_identity(os.fstat(child.handle))
                            if os.name != "nt"
                            else (child.identity[0], child.identity[1], stat.S_IFDIR)
                        )
                        if opened_identity[:2] != identity[:2]:
                            raise AssertionError("snapshot directory identity changed")
                        scan(child, relative)
                    finally:
                        self.converter._close_generated_directories([child])
                elif stat.S_ISREG(metadata.st_mode):
                    raw, opened_identity = self._read_bound_snapshot_file(
                        path, parent=directory, name=entry.name
                    )
                    if opened_identity != identity:
                        raise AssertionError("snapshot file identity changed")
                    records.append((relative, "file", len(raw), hashlib.sha256(raw).hexdigest(), metadata.st_mode, identity))
                elif stat.S_ISLNK(metadata.st_mode):
                    records.append((relative, "symlink", os.readlink(path), identity))
                else:
                    records.append((relative, "nonregular", identity))
            self.converter._verify_held_generated_directories([directory])
        try:
            scan(held_root, "")
        finally:
            self.converter._close_generated_directories([held_root])
        return tuple(sorted(records, key=lambda record: os.fsencode(str(record[0]))))

    def _read_bound_snapshot_file(
        self,
        path: Path,
        *,
        parent=None,
        name: str | None = None,
    ) -> tuple[bytes, tuple[int, int, int]]:
        metadata = os.lstat(path)
        self._reject_snapshot_reparse(metadata)
        if not stat.S_ISREG(metadata.st_mode):
            raise AssertionError("snapshot leaf is not regular")
        if parent is not None:
            self.converter._verify_held_generated_directories([parent])
        if os.name == "nt":
            descriptor = self.converter._open_source_leaf_descriptor(path)
        else:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(
                name if parent is not None else path,
                flags,
                **({"dir_fd": parent.handle} if parent is not None else {}),
            )
        try:
            before = os.fstat(descriptor)
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if parent is not None:
            self.converter._verify_held_generated_directories([parent])
        identity = self._snapshot_identity(before)
        final_metadata = os.lstat(path)
        self._reject_snapshot_reparse(final_metadata)
        if identity != self._snapshot_identity(
            after
        ) or identity != self._snapshot_identity(metadata) or identity != self._snapshot_identity(final_metadata):
            raise AssertionError(f"snapshot file identity changed: {path}")
        return b"".join(chunks), identity

    @staticmethod
    def _snapshot_identity(metadata: os.stat_result) -> tuple[int, int, int]:
        return (metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode))

    @staticmethod
    def _reject_snapshot_reparse(metadata: os.stat_result) -> None:
        reparse_attribute = 0x400
        if getattr(metadata, "st_file_attributes", 0) & reparse_attribute:
            raise AssertionError("snapshot entry is a reparse point")

    @staticmethod
    def _run_audited(
        command: tuple[str, ...], *, report_process_id: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in IMPORT_PROBE_ENVIRONMENT_NAMES
        }
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        isolated_command = command
        if report_process_id:
            if command[:2] != (sys.executable, "-B") or len(command) < 3:
                raise AssertionError("isolated process command is not approved")
            script = Path(command[2])
            if script not in {
                ROOT / "tools/convert_macwin_assets.py",
                ROOT / "scripts/validate_repository.py",
            }:
                raise AssertionError("isolated process command is not approved")
            bootstrap = (
                "import os,runpy,sys\n"
                "os.write(1,(str(os.getpid())+'\\n').encode('ascii'))\n"
                "sys.argv=sys.argv[1:]\n"
                "try:\n"
                " runpy.run_path(sys.argv[0],run_name='__main__')\n"
                "except SystemExit:\n"
                " raise\n"
                "except BaseException:\n"
                " os.write(2,b'isolated process failed\\n')\n"
                " raise SystemExit(1)\n"
            )
            isolated_command = (
                sys.executable,
                "-B",
                "-c",
                bootstrap,
                *command[2:],
            )
        options = {
            "cwd": ROOT,
            "check": False,
            "env": environment,
            "executable": None,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
            "timeout": 180,
            "close_fds": True,
        }
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": []}
            options["startupinfo"] = startup
        return subprocess.run(
            isolated_command,
            **options,
        )

    @staticmethod
    def _converter_command(*arguments: str) -> tuple[str, ...]:
        return (
            sys.executable,
            "-B",
            str(ROOT / "tools/convert_macwin_assets.py"),
            *arguments,
        )

    def _git_status(self) -> bytes:
        completed = self._run_audited(
            (
                "git",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def _forbidden_locators(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            locator
            for record in self.result.records
            for locator in record.evidence_locators
            if locator.startswith("/") or re.match(r"^[A-Za-z]:", locator)
        ))

    def _forbidden_evidence_values(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            locator
            for record in self.result.records
            for locator in record.evidence_locators
        ))

    def _run_main(self, arguments: tuple[str, ...]) -> tuple[int, bytes, bytes]:
        stdout = mock.Mock()
        stdout.buffer = io.BytesIO()
        stderr = mock.Mock()
        stderr.buffer = io.BytesIO()
        with mock.patch.object(self.converter.sys, "stdout", stdout), mock.patch.object(
            self.converter.sys, "stderr", stderr
        ):
            code = self.converter.main(arguments)
        return code, stdout.buffer.getvalue(), stderr.buffer.getvalue()


class MacWinMigrationDocumentationTests(unittest.TestCase):
    DOCUMENT = ROOT / "docs/migration/macwin-portable-assets.md"
    DOCUMENT_SHA256 = "a89a2cbd56d2a27284dc2ac6d991ef3456d0e2b343cf6695ad59409813dec56f"
    MAX_DOCUMENT_BYTES = 1024 * 1024
    REQUIRED_FACTS = (
        "repository: `a1112/Mac-Win`",
        "source tag: `mw-migration-baseline-db12d5e`",
        "source commit: `db12d5ebc5ba0d5a29c9464d07c1a86ffbc47527`",
        "inventory commit: `97f8423094d25325d8f864eb6f49a9e8628dbb93`",
        "90 = 19 catalog + 11 patches + 26 probes + 30 fixtures + 4 bottle-schema",
        "2 converted + 15 deferred + 73 quarantined",
        "0 Recipes, 0 portable probes, and 0 portable fixtures",
        "`MW-ASSET-002`",
        "`MW-ASSET-003`",
        "1 MiB",
        "owner: `compatforge/migration`",
        "python -B tools/convert_macwin_assets.py",
        "python -B tools/convert_macwin_assets.py --check",
        "python -B tools/convert_macwin_assets.py --write",
        "python -B tools/convert_macwin_assets.py --explain 7zip",
        "python -B scripts/validate_repository.py",
        "does not claim application compatibility",
        "does not claim patch readiness",
        "does not migrate or mutate Bottles",
        "is not consumed by the CompatForge runtime",
    )

    def test_migration_document_seals_the_reviewed_boundary(self) -> None:
        raw = self.DOCUMENT.read_bytes()
        text = self._validate_document(raw)
        self.assertIn("# Mac-Win portable asset migration boundary", text)
        self.assertEqual(self._parse_output_rows(text), self._generated_rows())

    def test_readme_and_testing_docs_link_the_visible_boundary(self) -> None:
        readme = (ROOT / "README.md").read_bytes()
        testing = (ROOT / "docs/testing.md").read_bytes()
        for label, raw in (("README", readme), ("testing", testing)):
            with self.subTest(document=label):
                text = raw.decode("utf-8", "strict")
                self.assertNotIn("\r", text)
                self.assertIn("macwin-portable-assets.md", text)
        self.assertIn(b"> \xe5\xbd\x93\xe5\x89\x8d\xe7\x8a\xb6\xe6\x80\x81", readme)

    def test_document_attributes_pin_exact_lf_text(self) -> None:
        attributes = (ROOT / ".gitattributes").read_bytes()
        self.assertNotIn(b"\r", attributes)
        for line in (
            b"/README.md text eol=lf\n",
            b"/docs/testing.md text eol=lf\n",
            b"/docs/migration/macwin-portable-assets.md text eol=lf\n",
        ):
            self.assertIn(line, attributes)

    def test_raw_document_seal_rejects_transport_and_semantic_decoys(self) -> None:
        raw = self.DOCUMENT.read_bytes()
        catalog_digest = b"c0c5b93b97b3f3c6e9197d2e00645dc28b1163b3130fe3e73ec7d1fde9e8fa4a"
        bottle_digest = b"f99698eaf5e341a58c7f7b91299701481c38df8a31203064aab38822622041cb"
        swapped = raw.replace(catalog_digest, b"DIGEST-A", 1).replace(
            bottle_digest, catalog_digest, 1
        ).replace(b"DIGEST-A", bottle_digest, 1)
        catalog_row = next(
            line for line in raw.splitlines(keepends=True)
            if b"generated/catalog.json`" in line
        )
        mutants = {
            "crlf": raw.replace(b"\n", b"\r\n", 1),
            "mixed": raw[:20] + b"\r\n" + raw[20:],
            "lone-cr": raw[:20] + b"\r" + raw[20:],
            "comment": b"<!-- hidden semantic copy\n" + raw + b"-->\n",
            "non-utf8": raw + b"\xff",
            "oversize": raw + b"x" * (self.MAX_DOCUMENT_BYTES + 1 - len(raw)),
            "semantic-decoy": raw.replace(
                self.REQUIRED_FACTS[0].encode("utf-8"),
                b"<!-- repository: `a1112/Mac-Win` -->",
            ),
            "swapped-digests": swapped,
            "wrong-byte-size": raw.replace(b"| 7,603 |", b"| 7,604 |", 1),
            "duplicate-row": raw.replace(catalog_row, catalog_row + catalog_row, 1),
            "missing-row": raw.replace(catalog_row, b"", 1),
            "contradictory-status": raw + b"The sealed result has 3 converted records.\n",
            "contradictory-word-status": raw + b"There are three converted records.\n",
            "contradictory-count": raw + b"The governed inventory has 91 assets.\n",
            "contradictory-commit": raw + b"source commit: `0000000000000000000000000000000000000000`\n",
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name), self.assertRaises(ValueError):
                self._validate_document(mutant)
        self.assertEqual(self._validate_document(raw).encode("utf-8"), raw)

    def _validate_document(self, raw: bytes) -> str:
        if len(raw) > self.MAX_DOCUMENT_BYTES:
            raise ValueError("migration document is too large")
        if b"\r" in raw or b"<!--" in raw or b"-->" in raw:
            raise ValueError("migration document transport is invalid")
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise ValueError("migration document is not UTF-8") from error
        if not text.endswith("\n") or text.startswith("\ufeff"):
            raise ValueError("migration document framing is invalid")
        if hashlib.sha256(raw).hexdigest() != self.DOCUMENT_SHA256:
            raise ValueError("migration document whole-file seal changed")
        if any(fact not in text for fact in self.REQUIRED_FACTS):
            raise ValueError("migration document facts are incomplete")
        if self._parse_output_rows(text) != self._generated_rows():
            raise ValueError("migration document output seals are incomplete")
        numeric_statuses = {
            status: {
                int(value)
                for value in re.findall(rf"\b(\d+) {status}(?:\b| records?\b)", text)
            }
            for status in ("converted", "deferred", "quarantined")
        }
        if any(
            values - {expected}
            for status, values in numeric_statuses.items()
            for expected in ({"converted": 2, "deferred": 15, "quarantined": 73}[status],)
        ):
            raise ValueError("migration document status claims are contradictory")
        root = json.loads((ROOT / "migration/macwin/generated/index.json").read_bytes())
        dependent = {
            document["path"]: (document["byteSize"], document["sha256"])
            for document in root["documents"]
        }
        rows = self._generated_rows()
        if root["documentCount"] != len(dependent) or set(dependent) != set(rows) - {
            "migration/macwin/generated/index.json"
        }:
            raise ValueError("migration document root semantics are incomplete")
        if any(rows[path] != seal for path, seal in dependent.items()):
            raise ValueError("migration document dependent seals are incomplete")
        return text

    @staticmethod
    def _parse_output_rows(text: str) -> dict[str, tuple[int, str]]:
        matches = re.findall(
            r"^\| `(?P<path>migration/macwin/generated/[^`]+\.json)` "
            r"\| (?P<size>[0-9][0-9,]*) \| `(?P<digest>[0-9a-f]{64})` \|$",
            text,
            flags=re.MULTILINE,
        )
        rows: dict[str, tuple[int, str]] = {}
        for path, size, digest in matches:
            if path in rows:
                raise ValueError("migration document output row is duplicated")
            rows[path] = (int(size.replace(",", "")), digest)
        return rows

    @staticmethod
    def _generated_rows() -> dict[str, tuple[int, str]]:
        return {
            path.relative_to(ROOT).as_posix(): (
                len(path.read_bytes()),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted((ROOT / "migration/macwin/generated").rglob("*.json"))
        }


if __name__ == "__main__":
    unittest.main()
