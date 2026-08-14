import ast
import copy
import json
import math
import re
import unicodedata
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "bottle-snapshot.schema.json",
    "bottle-runtime-map.schema.json",
    "bottle-migration-plan.schema.json",
    "bottle-active-ref.schema.json",
)
DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)
MAX_SNAPSHOT_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_SCALAR_CHARACTERS = 4096
MAX_DOCUMENT_COLLECTION_ITEMS = 100000
MAX_DOCUMENT_NODES = 1000000
MAX_DOCUMENT_DEPTH = 128
MAX_JSON_SAFE_INTEGER = (1 << 53) - 1
MAX_JSON_NUMBER_TEXT_CHARACTERS = 64
DOCUMENT_STRUCTURE_ERROR = "Bottle migration document exceeds structural limits"
DOCUMENT_MODEL_ERROR = "Bottle migration document is not exact JSON"
DOCUMENT_NUMBER_ERROR = "Bottle migration document contains an unsafe number"
DOCUMENT_GRAPH_ERROR = "Bottle migration document is not a JSON tree"
DOCUMENT_UNICODE_ERRORS = {
    "bottle-snapshot.schema.json": "snapshot manifest contains invalid Unicode",
    "bottle-runtime-map.schema.json": "runtime map contains invalid Unicode",
    "bottle-migration-plan.schema.json": "migration plan contains invalid Unicode",
    "bottle-active-ref.schema.json": "active reference contains invalid Unicode",
}
WINDOWS_SUPERSCRIPT_DEVICE_PATHS = (
    "COM¹",
    "COM².txt",
    "COM³",
    "LPT¹",
    "LPT².txt",
    "LPT³.log",
    "com¹",
    "cOm².TxT",
    "lPt³.LoG",
    "COM¹ .txt",
    "lpt²   .log",
)


class BottleMigrationSchemaTests(unittest.TestCase):
    def test_schemas_are_canonical_draft_2020_12_documents(self) -> None:
        identifiers = []
        for name in SCHEMA_NAMES:
            path = ROOT / "schemas" / name
            raw = path.read_bytes()
            schema = json.loads(raw)
            identifiers.append(schema["$id"])
            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertEqual(
                schema["$id"], f"https://compatforge.dev/schemas/{name}"
            )
            self.assertEqual(schema["properties"]["schemaVersion"], {"const": "1"})
            self.assertEqual(
                raw,
                (
                    json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8"),
            )
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_every_object_is_closed_and_every_value_is_bounded(self) -> None:
        for name, schema in self._schemas().items():
            for location, node in self._walk(schema):
                with self.subTest(schema=name, location=location):
                    if node.get("type") == "object":
                        self.assertIs(node.get("additionalProperties"), False)
                        self.assertIsInstance(node.get("properties"), dict)
                    elif node.get("type") == "array":
                        self.assertIn("maxItems", node)
                    elif node.get("type") == "string" and not any(
                        key in node for key in ("const", "enum", "$ref")
                    ):
                        self.assertIn("maxLength", node)
                    elif node.get("type") == "integer":
                        self.assertIn("minimum", node)
                        self.assertIn("maximum", node)

    def test_top_level_fields_and_entry_branches_are_exact(self) -> None:
        schemas = self._schemas()
        expected = {
            "bottle-snapshot.schema.json": {
                "schemaVersion",
                "legacyFormat",
                "bottleId",
                "entries",
                "entryCount",
                "totalFileBytes",
            },
            "bottle-runtime-map.schema.json": {"schemaVersion", "mappings"},
            "bottle-migration-plan.schema.json": {
                "schemaVersion",
                "snapshotDigest",
                "legacyFormat",
                "legacyEngineId",
                "bottle",
                "bottleDigest",
                "runtimePack",
                "launchers",
                "diagnostics",
                "planDigest",
            },
            "bottle-active-ref.schema.json": {
                "schemaVersion",
                "bottleId",
                "activePlanDigest",
                "history",
            },
        }
        for name, fields in expected.items():
            schema = schemas[name]
            self.assertEqual(set(schema["properties"]), fields)
            self.assertEqual(set(schema["required"]), fields)

        snapshot = schemas["bottle-snapshot.schema.json"]
        self.assertEqual(
            snapshot["properties"]["entries"]["items"]["oneOf"],
            [
                {"$ref": "#/$defs/fileEntry"},
                {"$ref": "#/$defs/directoryEntry"},
                {"$ref": "#/$defs/linkEntry"},
            ],
        )
        self.assertEqual(snapshot["properties"]["entries"]["maxItems"], 100_000)
        self.assertEqual(
            schemas["bottle-active-ref.schema.json"]["properties"]["history"][
                "maxItems"
            ],
            32,
        )

    def test_safe_identifier_digest_and_path_contracts(self) -> None:
        for name, schema in self._schemas().items():
            for value in ("bottle-1", "runtime.preview", "engine_9"):
                self._assert_valid(value, schema["$defs"]["id"], schema)
            for value in ("A", "Upper", "two/slash", "two:colon", "two\n"):
                with self.assertRaises(AssertionError, msg=(name, value)):
                    self._assert_valid(value, schema["$defs"]["id"], schema)

            self._assert_valid(DIGEST_A, schema["$defs"]["digest"], schema)
            for value in ("sha256:" + ("A" * 64), "sha256:abcd", "a" * 64):
                with self.assertRaises(AssertionError, msg=(name, value[:16])):
                    self._assert_valid(value, schema["$defs"]["digest"], schema)

            if "relativePath" in schema["$defs"]:
                path_contract = schema["$defs"]["relativePath"]
                for value in (
                    "manifest.json",
                    "drive_c/Public/example.txt",
                    "drive_c/应用/example.exe",
                    "café/file",
                ):
                    self._assert_valid(value, path_contract, schema)
                for value in (
                    "",
                    ".",
                    "..",
                    "/absolute",
                    "C:/drive",
                    "a\\b",
                    "a/../b",
                    "a//b",
                    "CON",
                    "folder/NUL.txt",
                    "folder/name.",
                    "folder/name ",
                ):
                    with self.assertRaises(AssertionError, msg=(name, value)):
                        self._assert_valid(value, path_contract, schema)
                self._assert_valid("/".join(["a"] * 128), path_contract, schema)
                with self.assertRaises(AssertionError, msg=(name, "depth")):
                    self._assert_valid("/".join(["a"] * 129), path_contract, schema)

            if "legacyEngineId" in schema["$defs"]:
                engine_id = schema["$defs"]["legacyEngineId"]
                self._assert_valid("WS11WineCX64Bit23.7.1-1", engine_id, schema)
                for value in ("", "engine/slash", "engine\\slash", "engine\n"):
                    with self.assertRaises(AssertionError, msg=(name, value)):
                        self._assert_valid(value, engine_id, schema)

    def test_portable_paths_use_utf8_byte_component_and_total_bounds(self) -> None:
        ascii_total_max = "/".join(
            (["a" * 255] * 15) + ["b" * 127, "c" * 128]
        )
        ascii_total_over = ascii_total_max + "c"
        multibyte_component_max = ("é" * 127) + "a"
        multibyte_component_over = "é" * 128
        multibyte_total_max = "/".join(
            ([multibyte_component_max] * 15)
            + [("é" * 63) + "a", "é" * 64]
        )
        multibyte_total_over = multibyte_total_max + "a"

        self.assertEqual(len(ascii_total_max.encode("utf-8")), 4096)
        self.assertEqual(len(ascii_total_over.encode("utf-8")), 4097)
        self.assertEqual(len(multibyte_component_max.encode("utf-8")), 255)
        self.assertEqual(len(multibyte_component_over.encode("utf-8")), 256)
        self.assertEqual(len(multibyte_total_max.encode("utf-8")), 4096)
        self.assertEqual(len(multibyte_total_over.encode("utf-8")), 4097)

        for name in (
            "bottle-snapshot.schema.json",
            "bottle-migration-plan.schema.json",
        ):
            schema = self._schema(name)
            contract = schema["$defs"]["relativePath"]
            for value in (
                "a" * 255,
                ascii_total_max,
                multibyte_component_max,
                multibyte_total_max,
            ):
                with self.subTest(
                    schema=name,
                    case="max",
                    bytes=len(value.encode("utf-8")),
                ):
                    self._assert_valid(value, contract, schema)
            for value in (
                "a" * 256,
                ascii_total_over,
                multibyte_component_over,
                multibyte_total_over,
            ):
                with self.subTest(
                    schema=name,
                    case="over",
                    bytes=len(value.encode("utf-8")),
                ), self.assertRaises(AssertionError):
                    self._assert_valid(value, contract, schema)

    def test_portable_paths_require_nfc_unicode_scalars(self) -> None:
        invalid_paths = (
            "cafe\u0301/file",
            "folder/\ud800/file",
            "folder/\u0085/file",
        )
        for name in (
            "bottle-snapshot.schema.json",
            "bottle-migration-plan.schema.json",
        ):
            schema = self._schema(name)
            contract = schema["$defs"]["relativePath"]
            self._assert_valid("café/应用.exe", contract, schema)
            for value in invalid_paths:
                with self.subTest(schema=name, value=repr(value)), self.assertRaises(
                    AssertionError
                ):
                    self._assert_valid(value, contract, schema)

    def test_portable_path_surrogates_have_a_fixed_unchained_error(self) -> None:
        for surrogate_kind, surrogate in (
            ("high", "\ud800"),
            ("low", "\udfff"),
        ):
            with self.subTest(surrogate=surrogate_kind):
                with self.assertRaises(AssertionError) as caught:
                    self._assert_portable_path(f"secret-{surrogate}")
                error = caught.exception
                self.assertIs(type(error), AssertionError)
                self.assertEqual(str(error), "path is not valid Unicode")
                self.assertNotIn("secret", str(error))
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

    def test_schema_patterns_reject_windows_superscript_device_aliases(self) -> None:
        for name in (
            "bottle-snapshot.schema.json",
            "bottle-migration-plan.schema.json",
        ):
            pattern = self._schema(name)["$defs"]["relativePath"]["pattern"]
            for value in WINDOWS_SUPERSCRIPT_DEVICE_PATHS:
                with self.subTest(schema=name, value=value):
                    self.assertIsNone(re.search(pattern, value))

    def test_oracle_rejects_windows_superscript_device_aliases(self) -> None:
        for value in WINDOWS_SUPERSCRIPT_DEVICE_PATHS:
            with self.subTest(value=value), self.assertRaises(AssertionError):
                self._assert_portable_path(value)

    def test_snapshot_paths_reject_casefold_collisions(self) -> None:
        name = "bottle-snapshot.schema.json"
        collision = copy.deepcopy(self._instances()[name])
        collision["entries"] = [
            {"path": "Drive", "kind": "directory"},
            {"path": "drive", "kind": "directory"},
        ]
        collision["entryCount"] = 2
        collision["totalFileBytes"] = 0
        with self.assertRaises(AssertionError):
            self._assert_document_valid(name, collision, self._schema(name))

    def test_complete_instances_and_closed_type_mutants(self) -> None:
        for name, instance in self._instances().items():
            schema = self._schema(name)
            with self.subTest(schema=name, case="valid"):
                self._assert_document_valid(name, instance, schema)

            extra = copy.deepcopy(instance)
            extra["unexpected"] = True
            with self.subTest(schema=name, case="extra"), self.assertRaises(
                AssertionError
            ):
                self._assert_document_valid(name, extra, schema)

        plan_name = "bottle-migration-plan.schema.json"
        plan_schema = self._schema(plan_name)
        integer_boolean = copy.deepcopy(self._instances()[plan_name])
        integer_boolean["launchers"][0]["showInHome"] = 1
        with self.assertRaises(AssertionError):
            self._assert_document_valid(plan_name, integer_boolean, plan_schema)

        nested_extra = copy.deepcopy(self._instances()[plan_name])
        nested_extra["launchers"][0]["unexpected"] = False
        with self.assertRaises(AssertionError):
            self._assert_document_valid(plan_name, nested_extra, plan_schema)

    def test_snapshot_entry_fields_are_disjoint_and_links_stay_inside(self) -> None:
        name = "bottle-snapshot.schema.json"
        schema = self._schema(name)
        valid = self._instances()[name]

        missing_file_fields = copy.deepcopy(valid)
        del missing_file_fields["entries"][1]["digest"]
        del missing_file_fields["entries"][1]["size"]
        directory_with_file_fields = copy.deepcopy(valid)
        directory_with_file_fields["entries"][0].update(
            {"digest": DIGEST_A, "size": 0}
        )
        absolute_link = copy.deepcopy(valid)
        absolute_link["entries"][2]["target"] = "/outside"
        escaping_link = copy.deepcopy(valid)
        escaping_link["entries"][2]["target"] = "../outside"

        for label, mutant in (
            ("file-fields", missing_file_fields),
            ("directory-file-fields", directory_with_file_fields),
            ("absolute-link", absolute_link),
            ("escaping-link", escaping_link),
        ):
            with self.subTest(case=label), self.assertRaises(AssertionError):
                self._assert_document_valid(name, mutant, schema)

    def test_snapshot_manifest_canonical_utf8_size_has_exact_64_mib_bound(self) -> None:
        name = "bottle-snapshot.schema.json"
        value = self._instances()[name]
        schema = self._schema(name)
        one_mib = "x" * (1024 * 1024)

        def controlled_chunks(canonical_size: int):
            payload_size = canonical_size - 1  # The canonical trailing LF.
            full_chunks, remainder = divmod(payload_size, len(one_mib))
            yield from (one_mib for _ in range(full_chunks))
            if remainder:
                yield "x" * remainder

        with mock.patch.object(
            type(self),
            "_canonical_json_chunks",
            return_value=controlled_chunks(MAX_SNAPSHOT_MANIFEST_BYTES),
            create=True,
        ):
            self._assert_document_valid(name, value, schema)

        with mock.patch.object(
            type(self),
            "_canonical_json_chunks",
            return_value=controlled_chunks(MAX_SNAPSHOT_MANIFEST_BYTES + 1),
            create=True,
        ), mock.patch.object(
            json,
            "dumps",
            side_effect=AssertionError("canonical output was materialized"),
        ), self.assertRaisesRegex(
            AssertionError,
            f"^snapshot manifest exceeds {MAX_SNAPSHOT_MANIFEST_BYTES} UTF-8 bytes$",
        ):
            self._assert_document_valid(name, value, schema)

    def test_snapshot_manifest_size_uses_canonical_pretty_lf_bytes(self) -> None:
        value = self._instances()["bottle-snapshot.schema.json"]
        value["entries"][0]["path"] = "drive_c/应用"
        expected = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        actual = "".join(self._canonical_json_chunks(value)).encode("utf-8") + b"\n"
        self.assertEqual(actual, expected)

    def test_structural_preflight_rejects_a_long_scalar_before_utf8_or_json(self) -> None:
        instances = self._instances()
        long_scalar_name = "bottle-snapshot.schema.json"
        long_scalar = instances[long_scalar_name]
        long_scalar["bottleId"] = "x" * (MAX_DOCUMENT_SCALAR_CHARACTERS + 1)
        long_key_name = "bottle-active-ref.schema.json"
        long_key = instances[long_key_name]
        long_key["x" * (MAX_DOCUMENT_SCALAR_CHARACTERS + 1)] = None

        for label, name, value in (
            ("value", long_scalar_name, long_scalar),
            ("key", long_key_name, long_key),
        ):
            with self.subTest(case=label), mock.patch.object(
                type(self),
                "_utf8_chunk_size",
                side_effect=AssertionError("UTF-8 encoding was attempted"),
            ), mock.patch.object(
                type(self),
                "_canonical_json_chunks",
                side_effect=AssertionError("JSONEncoder was constructed"),
            ), self.assertRaisesRegex(
                AssertionError,
                f"^{re.escape(DOCUMENT_STRUCTURE_ERROR)}$",
            ):
                self._assert_document_valid(name, value, self._schema(name))

    def test_structural_preflight_bounds_collections_nodes_and_depth(self) -> None:
        instances = self._instances()

        runtime_name = "bottle-runtime-map.schema.json"
        oversized_collection = copy.deepcopy(instances[runtime_name])
        oversized_collection["mappings"] = [None] * (
            MAX_DOCUMENT_COLLECTION_ITEMS + 1
        )

        active_name = "bottle-active-ref.schema.json"
        oversized_graph = copy.deepcopy(instances[active_name])
        wide_nested: object = None
        for _ in range(11):
            wide_nested = ([None] * (MAX_DOCUMENT_COLLECTION_ITEMS - 1)) + [
                wide_nested
            ]
        oversized_graph["nodes"] = wide_nested

        excessive_depth = copy.deepcopy(instances[active_name])
        nested: object = None
        for _ in range(MAX_DOCUMENT_DEPTH + 1):
            nested = [nested]
        excessive_depth["nested"] = nested

        for label, name, value in (
            ("collection", runtime_name, oversized_collection),
            ("nodes", active_name, oversized_graph),
            ("depth", active_name, excessive_depth),
        ):
            with self.subTest(case=label), mock.patch.object(
                type(self),
                "_utf8_chunk_size",
                side_effect=AssertionError("UTF-8 encoding was attempted"),
            ), self.assertRaisesRegex(
                AssertionError,
                f"^{re.escape(DOCUMENT_STRUCTURE_ERROR)}$",
            ):
                self._assert_document_valid(name, value, self._schema(name))

    def test_preflight_rejects_json_subclasses_without_calling_their_hooks(self) -> None:
        class LyingString(str):
            def __len__(self):
                raise AssertionError("lying string length was called")

            def encode(self, *args, **kwargs):
                raise AssertionError("lying string encode was called")

        class LyingList(list):
            def __len__(self):
                raise AssertionError("lying list length was called")

        class IteratorBombList(list):
            def __iter__(self):
                raise AssertionError("lying list iterator was called")

        class LyingDict(dict):
            def __len__(self):
                raise AssertionError("lying dict length was called")

        class IteratorBombDict(dict):
            def items(self):
                raise AssertionError("lying dict iterator was called")

        name = "bottle-active-ref.schema.json"
        cases = []

        string_value = self._instances()[name]
        string_value["activePlanDigest"] = LyingString(DIGEST_A)
        cases.append(("string-value", string_value))

        string_key = self._instances()[name]
        string_key[LyingString("secret-key")] = None
        cases.append(("string-key", string_key))

        list_value = self._instances()[name]
        list_value["history"] = LyingList([])
        cases.append(("list", list_value))

        iterator_list = self._instances()[name]
        iterator_list["history"] = IteratorBombList([])
        cases.append(("list-iterator", iterator_list))

        dict_value = LyingDict(self._instances()[name])
        cases.append(("dict", dict_value))

        iterator_dict = IteratorBombDict(self._instances()[name])
        cases.append(("dict-iterator", iterator_dict))

        for label, value in cases:
            with self.subTest(case=label):
                with self.assertRaises(AssertionError) as caught:
                    self._assert_document_valid(name, value, self._schema(name))
                error = caught.exception
                self.assertIs(type(error), AssertionError)
                self.assertEqual(str(error), DOCUMENT_MODEL_ERROR)
                self.assertNotIn("lying", str(error))
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

    def test_preflight_rejects_non_json_values_before_encoder_or_regex(self) -> None:
        name = "bottle-active-ref.schema.json"
        for label, hostile in (
            ("object", object()),
            ("bytes", b"secret"),
            ("tuple", ("secret",)),
            ("set", {"secret"}),
        ):
            value = self._instances()[name]
            value["hostile"] = hostile
            with self.subTest(case=label), mock.patch.object(
                re,
                "search",
                side_effect=AssertionError("regular expression was called"),
            ), mock.patch.object(
                type(self),
                "_canonical_json_chunks",
                side_effect=AssertionError("JSONEncoder was called"),
            ):
                with self.assertRaises(AssertionError) as caught:
                    self._assert_document_valid(name, value, self._schema(name))
                error = caught.exception
                self.assertIs(type(error), AssertionError)
                self.assertEqual(str(error), DOCUMENT_MODEL_ERROR)
                self.assertNotIn("secret", str(error))
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

    def test_preflight_bounds_exact_json_numbers_before_heavy_operations(self) -> None:
        name = "bottle-snapshot.schema.json"
        schema = self._schema(name)
        for label, hostile in (
            ("nan", float("nan")),
            ("positive-infinity", float("inf")),
            ("negative-infinity", float("-inf")),
            ("huge-integer", 1 << 1000000),
        ):
            value = self._instances()[name]
            value["entryCount"] = hostile
            with self.subTest(case=label), mock.patch.object(
                re,
                "search",
                side_effect=AssertionError("regular expression was called"),
            ), mock.patch.object(
                type(self),
                "_canonical_json_chunks",
                side_effect=AssertionError("JSONEncoder was called"),
            ):
                with self.assertRaises(AssertionError) as caught:
                    self._assert_document_valid(name, value, schema)
                error = caught.exception
                self.assertIs(type(error), AssertionError)
                self.assertEqual(str(error), DOCUMENT_NUMBER_ERROR)
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

        self._assert_document_preflight(name, {"number": 1.5})
        self._assert_document_preflight(name, {"number": MAX_JSON_SAFE_INTEGER})
        self.assertFalse(self._matches_type(True, "integer"))
        self.assertFalse(self._matches_type(1, "boolean"))

    def test_preflight_rejects_cycles_and_shared_containers(self) -> None:
        name = "bottle-active-ref.schema.json"

        cycle = []
        cycle.append(cycle)
        cyclic_document = self._instances()[name]
        cyclic_document["cycle"] = cycle

        shared = []
        shared_document = self._instances()[name]
        shared_document["left"] = shared
        shared_document["right"] = shared

        for label, value in (
            ("cycle", cyclic_document),
            ("shared", shared_document),
        ):
            with self.subTest(case=label):
                with self.assertRaises(AssertionError) as caught:
                    self._assert_document_valid(name, value, self._schema(name))
                error = caught.exception
                self.assertIs(type(error), AssertionError)
                self.assertEqual(str(error), DOCUMENT_GRAPH_ERROR)
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__suppress_context__)

    def test_preflight_checks_scheduled_budget_before_descending_width(self) -> None:
        name = "bottle-active-ref.schema.json"
        nested: object = "must-not-be-inspected"
        for _ in range(11):
            nested = ([None] * (MAX_DOCUMENT_COLLECTION_ITEMS - 1)) + [nested]
        value = self._instances()[name]
        value["nested"] = nested

        def reject_leaf_after_overflow(text: str) -> bool:
            if text == "must-not-be-inspected":
                raise AssertionError("a scalar was inspected after budget overflow")
            return False

        with mock.patch.object(
            type(self),
            "_contains_surrogate",
            side_effect=reject_leaf_after_overflow,
        ), self.assertRaisesRegex(
            AssertionError,
            f"^{re.escape(DOCUMENT_STRUCTURE_ERROR)}$",
        ):
            self._assert_document_valid(name, value, self._schema(name))

    def test_snapshot_encoder_chunks_are_utf8_counted_in_fixed_slices(self) -> None:
        class EncodeBomb(str):
            def encode(self, *args, **kwargs):
                raise AssertionError("the complete encoder chunk was encoded")

        observed_sizes = []

        def bounded_utf8_size(chunk: str) -> int:
            observed_sizes.append(len(chunk))
            if len(chunk) > 256:
                raise AssertionError("an oversized UTF-8 chunk was encoded")
            return len(str(chunk).encode("utf-8"))

        with mock.patch.object(
            type(self),
            "_canonical_json_chunks",
            return_value=[EncodeBomb("é" * 1024)],
        ), mock.patch.object(
            type(self),
            "_utf8_chunk_size",
            side_effect=bounded_utf8_size,
        ):
            self._assert_snapshot_manifest_size({})

        self.assertEqual(observed_sizes, [256, 256, 256, 256])

    def test_portable_path_length_precedes_utf8_encoding(self) -> None:
        class EncodeBomb(str):
            def encode(self, *args, **kwargs):
                raise AssertionError("portable path encoding was attempted")

        value = EncodeBomb("x" * (MAX_DOCUMENT_SCALAR_CHARACTERS + 1))
        with self.assertRaisesRegex(
            AssertionError,
            "^path exceeds the UTF-8 byte limit$",
        ):
            self._assert_portable_path(value)

    def test_rfc3339_length_precedes_regular_expression_matching(self) -> None:
        value = "x" * (MAX_DOCUMENT_SCALAR_CHARACTERS + 1)
        with mock.patch.object(
            re,
            "fullmatch",
            side_effect=AssertionError("regular expression matching was attempted"),
        ), self.assertRaisesRegex(
            AssertionError,
            "^RFC 3339 timestamp is invalid$",
        ):
            self._assert_rfc3339(value)

    def test_schema_items_are_validated_before_unique_canonicalization(self) -> None:
        name = "bottle-migration-plan.schema.json"
        schema = self._schema(name)
        value = [{"invented": True}]

        with mock.patch.object(
            json,
            "dumps",
            side_effect=AssertionError("unique item JSON was materialized"),
        ), self.assertRaisesRegex(AssertionError, "^enum mismatch$"):
            self._assert_valid(value, schema["properties"]["diagnostics"], schema)

    def test_snapshot_document_surrogates_use_fixed_non_reflecting_error(self) -> None:
        name = "bottle-snapshot.schema.json"
        schema = self._schema(name)
        string_fields = (
            ("schema-version", ("schemaVersion",)),
            ("legacy-format", ("legacyFormat",)),
            ("bottle-id", ("bottleId",)),
            ("entry-path", ("entries", 0, "path")),
            ("entry-kind", ("entries", 0, "kind")),
            ("file-digest", ("entries", 1, "digest")),
            ("link-target", ("entries", 2, "target")),
        )
        for surrogate_kind, surrogate in (
            ("high", "\ud800"),
            ("low", "\udfff"),
        ):
            for field, pointer in string_fields:
                value = copy.deepcopy(self._instances()[name])
                target = value
                for component in pointer[:-1]:
                    target = target[component]
                target[pointer[-1]] = f"secret-{surrogate}"

                with self.subTest(surrogate=surrogate_kind, field=field):
                    with self.assertRaises(AssertionError) as caught:
                        self._assert_document_valid(name, value, schema)
                    error = caught.exception
                    self.assertIs(type(error), AssertionError)
                    self.assertEqual(
                        str(error),
                        "snapshot manifest contains invalid Unicode",
                    )
                    self.assertNotIn("secret", str(error))
                    self.assertIsNone(error.__cause__)
                    self.assertTrue(error.__suppress_context__)

    def test_all_document_string_values_and_keys_reject_lone_surrogates(self) -> None:
        def locations(value: object, pointer=()):
            if isinstance(value, str):
                yield "value", pointer
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    yield from locations(item, (*pointer, index))
            elif isinstance(value, dict):
                yield "key", pointer
                for key, item in value.items():
                    yield from locations(item, (*pointer, key))

        for name, original in self._instances().items():
            schema = self._schema(name)
            for location_kind, pointer in locations(original):
                for surrogate_kind, surrogate in (
                    ("high", "\ud800"),
                    ("low", "\udfff"),
                ):
                    value = copy.deepcopy(original)
                    target = value
                    for component in pointer[:-1]:
                        target = target[component]
                    hostile = f"secret-{surrogate}"
                    if location_kind == "value":
                        target[pointer[-1]] = hostile
                    else:
                        for component in pointer[-1:]:
                            target = target[component]
                        target[hostile] = None

                    with self.subTest(
                        schema=name,
                        location=location_kind,
                        pointer=repr(pointer),
                        surrogate=surrogate_kind,
                    ):
                        with self.assertRaises(AssertionError) as caught:
                            self._assert_document_valid(name, value, schema)
                        error = caught.exception
                        self.assertIs(type(error), AssertionError)
                        self.assertEqual(str(error), DOCUMENT_UNICODE_ERRORS[name])
                        self.assertNotIn("secret", str(error))
                        self.assertIsNone(error.__cause__)
                        self.assertTrue(error.__suppress_context__)

    def test_records_are_sorted_and_unique(self) -> None:
        instances = self._instances()
        cases = []

        snapshot = copy.deepcopy(instances["bottle-snapshot.schema.json"])
        snapshot["entries"] = list(reversed(snapshot["entries"]))
        cases.append(("bottle-snapshot.schema.json", snapshot))

        runtime_map = copy.deepcopy(instances["bottle-runtime-map.schema.json"])
        duplicate_mapping = copy.deepcopy(runtime_map["mappings"][0])
        duplicate_mapping["runtimePackDigest"] = DIGEST_B
        runtime_map["mappings"].append(duplicate_mapping)
        cases.append(("bottle-runtime-map.schema.json", runtime_map))

        plan = copy.deepcopy(instances["bottle-migration-plan.schema.json"])
        duplicate_environment = copy.deepcopy(plan["launchers"][0]["environment"][0])
        duplicate_environment["value"] = "different"
        plan["launchers"][0]["environment"].append(duplicate_environment)
        cases.append(("bottle-migration-plan.schema.json", plan))

        for name, mutant in cases:
            with self.subTest(schema=name), self.assertRaises(AssertionError):
                self._assert_document_valid(name, mutant, self._schema(name))

    def test_history_bound_and_plan_runtime_binding_are_semantic(self) -> None:
        instances = self._instances()

        active_name = "bottle-active-ref.schema.json"
        active = copy.deepcopy(instances[active_name])
        active["history"] = [f"sha256:{index:064x}" for index in range(33)]
        with self.assertRaises(AssertionError):
            self._assert_document_valid(active_name, active, self._schema(active_name))

        plan_name = "bottle-migration-plan.schema.json"
        for field in ("id", "digest"):
            plan = copy.deepcopy(instances[plan_name])
            plan["runtimePack"][field] = (
                "different-runtime" if field == "id" else DIGEST_B
            )
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self._assert_document_valid(plan_name, plan, self._schema(plan_name))

    def test_active_plan_digest_is_disjoint_from_prior_history(self) -> None:
        name = "bottle-active-ref.schema.json"
        active = copy.deepcopy(self._instances()[name])
        active["history"].append(active["activePlanDigest"])
        with self.assertRaisesRegex(
            AssertionError,
            "^active plan digest must not appear in history$",
        ):
            self._assert_document_valid(name, active, self._schema(name))

    def test_rfc3339_schema_admits_domain_leap_second_syntax(self) -> None:
        schema = self._schema("bottle-migration-plan.schema.json")
        pattern = schema["$defs"]["rfc3339"]["pattern"]
        for timestamp in (
            "2016-12-31T23:59:60Z",
            "2017-01-01T00:59:60+01:00",
        ):
            with self.subTest(timestamp=timestamp):
                self.assertIsNotNone(re.search(pattern, timestamp))

    def test_rfc3339_oracle_accepts_domain_valid_boundaries(self) -> None:
        schema = self._schema("bottle-migration-plan.schema.json")
        contract = schema["$defs"]["rfc3339"]
        for timestamp in (
            "2000-02-29T23:59:59Z",
            "2024-02-29t12:34:56.123z",
            "2026-08-08T00:00:00.1234567890Z",
            "2026-08-08T00:00:00+23:59",
            "2016-12-31T23:59:60Z",
            "2017-01-01T00:59:60+01:00",
        ):
            with self.subTest(timestamp=timestamp):
                self._assert_valid(timestamp, contract, schema)

    def test_rfc3339_oracle_rejects_invalid_dates_and_leap_positions(self) -> None:
        schema = self._schema("bottle-migration-plan.schema.json")
        contract = schema["$defs"]["rfc3339"]
        for timestamp in (
            "2026-02-30T00:00:00Z",
            "1900-02-29T00:00:00Z",
            "2026-04-31T00:00:00Z",
            "2026-08-08T00:00:00+24:00",
            "2026-08-08T00:00:60Z",
            "2016-12-30T23:59:60Z",
            "2016-12-31T23:58:60Z",
            "2016-12-31T23:59:60+01:00",
            "2017-01-01T01:00:60+01:00",
        ):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(
                AssertionError, "^RFC 3339 timestamp is invalid$"
            ):
                self._assert_valid(timestamp, contract, schema)

    def test_launcher_bottle_id_must_match_embedded_bottle(self) -> None:
        name = "bottle-migration-plan.schema.json"
        plan = copy.deepcopy(self._instances()[name])
        plan["launchers"][0]["bottleId"] = "bottle-2"
        with self.assertRaises(AssertionError):
            self._assert_document_valid(name, plan, self._schema(name))

    def test_migration_plan_recipe_collection_is_fixed_empty(self) -> None:
        schema = self._schema("bottle-migration-plan.schema.json")
        recipes = schema["$defs"]["bottle"]["properties"]["recipes"]
        self.assertEqual(recipes["maxItems"], 0)
        self.assertIn("recipeReference", schema["$defs"])

    def test_oracle_rejects_invented_migration_plan_recipe(self) -> None:
        name = "bottle-migration-plan.schema.json"
        plan = copy.deepcopy(self._instances()[name])
        plan["bottle"]["recipes"] = [
            {
                "id": "invented-recipe",
                "version": "1",
                "digest": DIGEST_A,
            }
        ]
        with self.assertRaisesRegex(AssertionError, "^array too long$"):
            self._assert_document_valid(name, plan, self._schema(name))

    def test_oracle_uses_only_the_python_standard_library(self) -> None:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertNotIn("jsonschema", imported)

    def _schemas(self) -> dict[str, dict[str, object]]:
        return {name: self._schema(name) for name in SCHEMA_NAMES}

    def _schema(self, name: str) -> dict[str, object]:
        return json.loads((ROOT / "schemas" / name).read_bytes())

    @staticmethod
    def _canonical_json_chunks(value: object):
        return json.JSONEncoder(
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).iterencode(value)

    @staticmethod
    def _utf8_chunk_size(value: str) -> int:
        return len(value.encode("utf-8", errors="strict"))

    @classmethod
    def _utf8_text_size(cls, value: str) -> int:
        return sum(
            cls._utf8_chunk_size(value[start : start + 256])
            for start in range(0, len(value), 256)
        )

    @staticmethod
    def _contains_surrogate(value: str) -> bool:
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)

    @classmethod
    def _iter_document_strings(cls, value: object):
        value_type = type(value)
        if value_type is str:
            yield value
        elif value_type is dict:
            for key, item in value.items():
                yield key
                yield from cls._iter_document_strings(item)
        elif value_type is list:
            for index in range(len(value)):
                yield from cls._iter_document_strings(value[index])

    @classmethod
    def _assert_document_preflight(cls, name: str, value: object) -> None:
        allowed_types = {dict, list, str, int, float, bool, type(None)}
        value_type = type(value)
        if value_type not in allowed_types:
            raise AssertionError(DOCUMENT_MODEL_ERROR) from None

        scheduled_nodes = 1
        seen_containers = set()
        if value_type in (dict, list):
            seen_containers.add(id(value))

        def visit(current: object, depth: int) -> None:
            nonlocal scheduled_nodes
            current_type = type(current)
            if current_type is str:
                if len(current) > MAX_DOCUMENT_SCALAR_CHARACTERS:
                    raise AssertionError(DOCUMENT_STRUCTURE_ERROR) from None
                if cls._contains_surrogate(current):
                    raise AssertionError(DOCUMENT_UNICODE_ERRORS[name]) from None
            elif current_type is int:
                if current.bit_length() > 53 or not (
                    -MAX_JSON_SAFE_INTEGER <= current <= MAX_JSON_SAFE_INTEGER
                ):
                    raise AssertionError(DOCUMENT_NUMBER_ERROR) from None
            elif current_type is float:
                if (
                    not math.isfinite(current)
                    or abs(current) > MAX_JSON_SAFE_INTEGER
                    or len(repr(current)) > MAX_JSON_NUMBER_TEXT_CHARACTERS
                ):
                    raise AssertionError(DOCUMENT_NUMBER_ERROR) from None
            elif current_type is dict:
                if len(current) > MAX_DOCUMENT_COLLECTION_ITEMS:
                    raise AssertionError(DOCUMENT_STRUCTURE_ERROR) from None
                for key, item in current.items():
                    if type(key) is not str:
                        raise AssertionError(DOCUMENT_MODEL_ERROR) from None
                    if len(key) > MAX_DOCUMENT_SCALAR_CHARACTERS:
                        raise AssertionError(DOCUMENT_STRUCTURE_ERROR) from None
                    if cls._contains_surrogate(key):
                        raise AssertionError(DOCUMENT_UNICODE_ERRORS[name]) from None
                    schedule_and_visit(item, depth + 1)
            elif current_type is list:
                if len(current) > MAX_DOCUMENT_COLLECTION_ITEMS:
                    raise AssertionError(DOCUMENT_STRUCTURE_ERROR) from None
                for index in range(len(current)):
                    schedule_and_visit(current[index], depth + 1)

        def schedule_and_visit(child: object, depth: int) -> None:
            nonlocal scheduled_nodes
            child_type = type(child)
            if child_type not in allowed_types:
                raise AssertionError(DOCUMENT_MODEL_ERROR) from None
            if depth > MAX_DOCUMENT_DEPTH or scheduled_nodes >= MAX_DOCUMENT_NODES:
                raise AssertionError(DOCUMENT_STRUCTURE_ERROR) from None
            if child_type in (dict, list):
                identity = id(child)
                if identity in seen_containers:
                    raise AssertionError(DOCUMENT_GRAPH_ERROR) from None
                seen_containers.add(identity)
            scheduled_nodes += 1
            visit(child, depth)

        visit(value, 0)

        try:
            for text in cls._iter_document_strings(value):
                cls._utf8_text_size(text)
        except UnicodeEncodeError:
            raise AssertionError(DOCUMENT_UNICODE_ERRORS[name]) from None

    @classmethod
    def _assert_snapshot_manifest_size(cls, value: object) -> None:
        canonical_size = 1  # The canonical trailing LF.
        try:
            for chunk in cls._canonical_json_chunks(value):
                canonical_size += cls._utf8_text_size(chunk)
                if canonical_size > MAX_SNAPSHOT_MANIFEST_BYTES:
                    raise AssertionError(
                        "snapshot manifest exceeds "
                        f"{MAX_SNAPSHOT_MANIFEST_BYTES} UTF-8 bytes"
                    )
        except UnicodeEncodeError:
            raise AssertionError(
                "snapshot manifest contains invalid Unicode"
            ) from None

    @classmethod
    def _walk(cls, value: object, location: str = "$"):
        if type(value) is dict:
            yield location, value
            for key, item in value.items():
                yield from cls._walk(item, f"{location}/{key}")
        elif type(value) is list:
            for index, item in enumerate(value):
                yield from cls._walk(item, f"{location}/{index}")

    @classmethod
    def _assert_document_valid(
        cls, name: str, value: object, schema: dict[str, object]
    ) -> None:
        cls._assert_document_preflight(name, value)
        if name == "bottle-snapshot.schema.json":
            cls._assert_snapshot_manifest_size(value)
        cls._assert_valid(value, schema, schema)
        if name == "bottle-snapshot.schema.json":
            entries = value["entries"]
            cls._assert_sorted_unique(entries, "path")
            cls._assert_casefold_unique(entry["path"] for entry in entries)
            if value["entryCount"] != len(entries):
                raise AssertionError("snapshot entry count mismatch")
            file_bytes = sum(
                entry["size"] for entry in entries if entry["kind"] == "file"
            )
            if value["totalFileBytes"] != file_bytes:
                raise AssertionError("snapshot byte count mismatch")
        elif name == "bottle-runtime-map.schema.json":
            cls._assert_sorted_unique(value["mappings"], "legacyEngineId")
        elif name == "bottle-migration-plan.schema.json":
            if value["runtimePack"] != value["bottle"]["runtimePack"]:
                raise AssertionError("plan Runtime binding mismatch")
            cls._assert_sorted_unique(value["launchers"], "id")
            cls._assert_sorted_unique(value["bottle"].get("recipes", []), "id")
            for launcher in value["launchers"]:
                if launcher["bottleId"] != value["bottle"]["id"]:
                    raise AssertionError("launcher Bottle binding mismatch")
                cls._assert_sorted_unique(launcher["environment"], "name")
        elif name == "bottle-active-ref.schema.json":
            if value["activePlanDigest"] in value["history"]:
                raise AssertionError(
                    "active plan digest must not appear in history"
                )

    @staticmethod
    def _assert_sorted_unique(records: list[object], key: str) -> None:
        values = [record[key] for record in records]
        if values != sorted(values) or len(values) != len(set(values)):
            raise AssertionError(f"records are not sorted and unique by {key}")

    @staticmethod
    def _assert_casefold_unique(paths) -> None:
        folded = [unicodedata.normalize("NFC", path.casefold()) for path in paths]
        if len(folded) != len(set(folded)):
            raise AssertionError("paths collide after Unicode case folding")

    @classmethod
    def _assert_portable_path(cls, value: str) -> None:
        if len(value) > MAX_DOCUMENT_SCALAR_CHARACTERS:
            raise AssertionError("path exceeds the UTF-8 byte limit")
        try:
            encoded_size = cls._utf8_text_size(value)
        except UnicodeEncodeError:
            raise AssertionError("path is not valid Unicode") from None
        if encoded_size > 4096:
            raise AssertionError("path exceeds the UTF-8 byte limit")
        if unicodedata.normalize("NFC", value) != value:
            raise AssertionError("path is not NFC")

        components = value.split("/")
        if not 1 <= len(components) <= 128:
            raise AssertionError("path depth is invalid")
        serial_suffixes = tuple(str(index) for index in range(1, 10)) + (
            "¹",
            "²",
            "³",
        )
        reserved = {
            "con",
            "prn",
            "aux",
            "nul",
            "conin$",
            "conout$",
            *(f"com{suffix}" for suffix in serial_suffixes),
            *(f"lpt{suffix}" for suffix in serial_suffixes),
        }
        forbidden = set('<>:"\\|?*')
        for component in components:
            if not component or component in (".", ".."):
                raise AssertionError("path component is ambiguous")
            if cls._utf8_text_size(component) > 255:
                raise AssertionError("path component exceeds the UTF-8 byte limit")
            if component.endswith((".", " ")):
                raise AssertionError("path component has an ambiguous suffix")
            if any(
                character in forbidden
                or unicodedata.category(character).startswith("C")
                for character in component
            ):
                raise AssertionError("path component contains an unsafe scalar")
            device_stem = component.split(".", 1)[0].rstrip(" ").casefold()
            if device_stem in reserved:
                raise AssertionError("path component is a reserved device name")

    @staticmethod
    def _assert_rfc3339(value: str) -> None:
        if not 20 <= len(value) <= MAX_DOCUMENT_SCALAR_CHARACTERS:
            raise AssertionError("RFC 3339 timestamp is invalid")
        match = re.fullmatch(
            r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
            r"[Tt](?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
            r"(?:\.[0-9]+)?(?P<timezone>[Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        )
        if match is None:
            raise AssertionError("RFC 3339 timestamp is invalid")

        year, month, day, hour, minute, second = (
            int(match[name])
            for name in ("year", "month", "day", "hour", "minute", "second")
        )
        leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        days_in_month = {
            1: 31,
            2: 29 if leap_year else 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31,
        }.get(month)
        if (
            days_in_month is None
            or not 1 <= day <= days_in_month
            or hour > 23
            or minute > 59
            or second > 60
        ):
            raise AssertionError("RFC 3339 timestamp is invalid")

        timezone = match["timezone"]
        timezone_offset = 0
        if timezone not in ("Z", "z"):
            offset_hour = int(timezone[1:3])
            offset_minute = int(timezone[4:6])
            if offset_hour > 23 or offset_minute > 59:
                raise AssertionError("RFC 3339 timestamp is invalid")
            timezone_offset = offset_hour * 60 + offset_minute
            if timezone[0] == "-":
                timezone_offset = -timezone_offset

        if second < 60:
            return
        utc_day_delta, utc_minute = divmod(
            hour * 60 + minute - timezone_offset, 24 * 60
        )
        if utc_minute != 23 * 60 + 59 or (
            utc_day_delta,
            month,
            day,
        ) not in {
            (0, 6, 30),
            (0, 12, 31),
            (-1, 7, 1),
            (-1, 1, 1),
        }:
            raise AssertionError("RFC 3339 timestamp is invalid")

    @classmethod
    def _assert_valid(
        cls,
        value: object,
        schema: dict[str, object],
        root: dict[str, object],
    ) -> None:
        reference = schema.get("$ref")
        if reference is not None:
            if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
                raise AssertionError("only local schema references are supported")
            target = root["$defs"][reference.removeprefix("#/$defs/")]
            cls._assert_valid(value, target, root)
            return

        one_of = schema.get("oneOf")
        if one_of is not None:
            matches = sum(cls._matches(value, branch, root) for branch in one_of)
            if matches != 1:
                raise AssertionError("oneOf must match exactly one branch")
            return

        if "const" in schema and not cls._json_equal(value, schema["const"]):
            raise AssertionError("const mismatch")
        if "enum" in schema and not any(
            cls._json_equal(value, member) for member in schema["enum"]
        ):
            raise AssertionError("enum mismatch")

        declared_type = schema.get("type")
        if declared_type is not None and not cls._matches_type(value, declared_type):
            raise AssertionError("type mismatch")

        if schema is root.get("$defs", {}).get("relativePath"):
            cls._assert_portable_path(value)
        if schema is root.get("$defs", {}).get("rfc3339"):
            cls._assert_rfc3339(value)

        if type(value) is str:
            if len(value) < schema.get("minLength", 0):
                raise AssertionError("string too short")
            if len(value) > schema.get("maxLength", len(value)):
                raise AssertionError("string too long")
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                raise AssertionError("pattern mismatch")
        elif type(value) is int:
            if value < schema.get("minimum", value):
                raise AssertionError("integer too small")
            if value > schema.get("maximum", value):
                raise AssertionError("integer too large")
        elif type(value) is list:
            if len(value) < schema.get("minItems", 0):
                raise AssertionError("array too short")
            if len(value) > schema.get("maxItems", len(value)):
                raise AssertionError("array too long")
            if isinstance(schema.get("items"), dict):
                for item in value:
                    cls._assert_valid(item, schema["items"], root)
            if schema.get("uniqueItems"):
                rendered = [json.dumps(item, sort_keys=True) for item in value]
                if len(rendered) != len(set(rendered)):
                    raise AssertionError("array items are not unique")
        elif type(value) is dict:
            required = schema.get("required", [])
            if any(key not in value for key in required):
                raise AssertionError("required property missing")
            properties = schema.get("properties", {})
            for key, item in value.items():
                if key not in properties:
                    if schema.get("additionalProperties") is False:
                        raise AssertionError("additional property forbidden")
                    continue
                cls._assert_valid(item, properties[key], root)

    @classmethod
    def _matches(
        cls, value: object, schema: dict[str, object], root: dict[str, object]
    ) -> bool:
        try:
            cls._assert_valid(value, schema, root)
        except AssertionError:
            return False
        return True

    @staticmethod
    def _matches_type(value: object, declared: object) -> bool:
        return {
            "object": type(value) is dict,
            "array": type(value) is list,
            "string": type(value) is str,
            "integer": type(value) is int,
            "boolean": type(value) is bool,
            "null": value is None,
        }.get(declared, False)

    @staticmethod
    def _json_equal(left: object, right: object) -> bool:
        if type(left) is not type(right):
            return False
        return left == right

    @staticmethod
    def _instances() -> dict[str, dict[str, object]]:
        bottle = {
            "schemaVersion": "1",
            "id": "bottle-1",
            "name": "Example Bottle",
            "guest": {"windowsVersion": "win10", "architecture": "x86_64"},
            "runtimePack": {"id": "runtime-preview", "digest": DIGEST_A},
            "recipes": [],
            "storage": {"layoutVersion": 1, "state": "ready"},
            "createdAt": "2026-08-08T00:00:00Z",
            "updatedAt": "2026-08-08T00:00:01Z",
        }
        return {
            "bottle-snapshot.schema.json": {
                "schemaVersion": "1",
                "legacyFormat": "macwin-bottle-v1",
                "bottleId": "bottle-1",
                "entries": [
                    {"path": "drive_c/Public", "kind": "directory"},
                    {
                        "path": "drive_c/Public/example.txt",
                        "kind": "file",
                        "size": 15,
                        "digest": DIGEST_A,
                    },
                    {
                        "path": "example-link",
                        "kind": "link",
                        "target": "drive_c/Public/example.txt",
                    },
                    {
                        "path": "manifest.json",
                        "kind": "file",
                        "size": 100,
                        "digest": DIGEST_B,
                    },
                ],
                "entryCount": 4,
                "totalFileBytes": 115,
            },
            "bottle-runtime-map.schema.json": {
                "schemaVersion": "1",
                "mappings": [
                    {
                        "legacyEngineId": "wine-9",
                        "runtimePackId": "runtime-preview",
                        "runtimePackDigest": DIGEST_A,
                    }
                ],
            },
            "bottle-migration-plan.schema.json": {
                "schemaVersion": "1",
                "snapshotDigest": DIGEST_B,
                "legacyFormat": "macwin-bottle-v1",
                "legacyEngineId": "wine-9",
                "bottle": bottle,
                "bottleDigest": DIGEST_B,
                "runtimePack": {"id": "runtime-preview", "digest": DIGEST_A},
                "launchers": [
                    {
                        "id": "launcher-1",
                        "appId": "app-1",
                        "bottleId": "bottle-1",
                        "displayName": "Example",
                        "executable": "drive_c/Example/example.exe",
                        "arguments": ["--safe"],
                        "iconPath": "icons/example.png",
                        "environment": [{"name": "LANG", "value": "en_US.UTF-8"}],
                        "showInHome": True,
                    }
                ],
                "diagnostics": [],
                "planDigest": DIGEST_A,
            },
            "bottle-active-ref.schema.json": {
                "schemaVersion": "1",
                "bottleId": "bottle-1",
                "activePlanDigest": DIGEST_A,
                "history": [DIGEST_B],
            },
        }


if __name__ == "__main__":
    unittest.main()
