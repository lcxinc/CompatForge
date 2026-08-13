from __future__ import annotations

import ast
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
import shutil
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
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
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertNotIn("jsonschema", imported)

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
                    },
                )
                self.assertEqual(properties["source"], {"$ref": "#/$defs/sourceIdentity"})
                self.assertEqual(properties["license"], {"$ref": "#/$defs/reviewStatus"})
                self.assertEqual(properties["provenance"], {"$ref": "#/$defs/reviewStatus"})

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
        }
        review = {"status": "unresolved"}
        asset = {
            "category": "probes",
            "sourcePath": source["sourcePath"],
            "sourceCommit": source["sourceCommit"],
            "gitBlobOid": "b" * 40,
            "sha256": source["sourceSha256"],
            "byteSize": 1,
            "gitMode": "100755",
            "kind": "probe",
            "license": review,
            "provenance": review,
            "intendedOwner": "compatforge/probes",
            "externalRefs": [],
            "developmentDependencies": [],
            "objectPath": "objects/sha256/aa/" + ("a" * 62),
        }
        deferred = {
            "sourcePath": "patches/example.patch",
            "sourceCommit": "d" * 40,
            "sourceSha256": "a" * 64,
            "category": "patches",
            "status": "deferred",
            "targetIssue": "MW-ASSET-002",
            "intendedOwner": "compatforge/patches",
            "license": review,
            "provenance": review,
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
            "license": review,
            "provenance": review,
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

    def test_each_authenticated_source_object_enters_the_model_once(self) -> None:
        converter = self.converter
        seen: list[str] = []
        original = converter._load_authenticated_asset_bytes

        def observe(binding, source_root, record):
            seen.append(record["sourcePath"])
            return original(binding, source_root, record)

        with mock.patch.object(
            converter, "_load_authenticated_asset_bytes", side_effect=observe
        ):
            loaded = converter.load_source_pack(ROOT)
        self.assertEqual(len(loaded.assets), 90)
        self.assertEqual(len(seen), 90)
        self.assertEqual(len(set(seen)), 90)

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
        self.assertEqual(set(first), {"conversion-ledger.json"})
        common = _load_macwin_asset_common()
        ledger = common.parse_json_bytes(
            first["conversion-ledger.json"], label="conversion ledger"
        )
        self.assertEqual(ledger["assetCount"], 90)
        self.assertEqual(len(ledger["records"]), 90)
        self.assertEqual(common.canonical_json_bytes(ledger), first["conversion-ledger.json"])

    @staticmethod
    def _replace_record(result, record, **changes):
        replacement = dataclasses.replace(record, **changes)
        records = tuple(
            replacement if existing is record else existing for existing in result.records
        )
        return dataclasses.replace(result, records=records)


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

    def test_repository_validation_skips_only_an_absent_converter(self) -> None:
        validator = self._load_repository_validator()
        self.assertTrue(
            hasattr(validator, "validate_macwin_asset_migration"),
            "repository validator is missing the temporary migration-check hook",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator.ROOT = root
            self.assertEqual(validator.validate_macwin_asset_migration(), [])

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
                [sys.executable, "-B", str(converter), "--check"],
            )
            expected_environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in allowed_names
            }
            expected_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            self.assertEqual(options["env"], expected_environment)
            self.assertEqual(options["cwd"], root)
            self.assertIs(options["stdin"], subprocess.DEVNULL)
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

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_valid_repository(root)
            validator.ROOT = root

            standard_output = io.StringIO()
            standard_error = io.StringIO()
            with contextlib.redirect_stdout(standard_output), contextlib.redirect_stderr(
                standard_error
            ):
                result = validator.main()

            self.assertEqual(result, 0, standard_error.getvalue())
            self.assertEqual(
                (root / "migration-check-invocation.json").read_text(encoding="utf-8"),
                '["--check"]',
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
            "Path('migration-check-invocation.json').write_text(\n"
            "    json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            ")\n",
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


if __name__ == "__main__":
    unittest.main()
