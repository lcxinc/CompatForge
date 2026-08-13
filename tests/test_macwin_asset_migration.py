from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
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
        from jsonschema import Draft202012Validator

        for name in (*self.SCHEMA_NAMES, "recipe.schema.json"):
            schema = self._schema(name)
            Draft202012Validator.check_schema(schema)
            for location, node in self._walk_schema(schema):
                pattern = node.get("pattern")
                if pattern is None:
                    continue
                with self.subTest(schema=name, location=location):
                    self.assertFalse(pattern.endswith("$"))
                    validator = Draft202012Validator(node)
                    valid = self._valid_pattern_value(location, pattern)
                    self.assertFalse(list(validator.iter_errors(valid)), (location, valid))
                    for suffix in ("\n", "\r", "\x00"):
                        self.assertTrue(
                            list(validator.iter_errors(valid + suffix)),
                            (location, repr(valid + suffix)),
                        )

    def test_complete_schema_instances_reject_pattern_tail_mutants(self) -> None:
        from jsonschema import Draft202012Validator

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
            validator = Draft202012Validator(self._schema(name))
            with self.subTest(schema=name, case="valid"):
                self.assertFalse(list(validator.iter_errors(value)))
            mutant = copy.deepcopy(value)
            mutations[name](mutant)
            with self.subTest(schema=name, case="tail-mutant"):
                self.assertTrue(list(validator.iter_errors(mutant)))

    def test_schema_paths_match_portable_windows_segment_rules(self) -> None:
        from jsonschema import Draft202012Validator

        valid = ("safe/path.txt", ("a" * 255) + "/file")
        invalid = (
            "CON",
            "con.txt",
            "folder/PRN.log",
            "folder/aux",
            "folder/NUL.txt",
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
            validator = Draft202012Validator(contract)
            for value in valid:
                with self.subTest(schema=name, valid=value[:20]):
                    self.assertFalse(list(validator.iter_errors(value)))
            for value in invalid:
                with self.subTest(schema=name, invalid=value[:20]):
                    self.assertTrue(list(validator.iter_errors(value)))

    def test_source_pack_contract_captures_source_identities_and_dependencies(self) -> None:
        schema = self._schema("macwin-source-pack.schema.json")
        self.assertEqual(
            set(schema["required"]),
            {
                "schemaVersion",
                "repository",
                "sourceTag",
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


if __name__ == "__main__":
    unittest.main()
