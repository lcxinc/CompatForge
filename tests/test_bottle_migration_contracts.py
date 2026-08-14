import ast
import copy
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "bottle-snapshot.schema.json",
    "bottle-runtime-map.schema.json",
    "bottle-migration-plan.schema.json",
    "bottle-active-ref.schema.json",
)
DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)


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
                for value in ("manifest.json", "drive_c/Public/example.txt"):
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
                    "café/file",
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

    @classmethod
    def _walk(cls, value: object, location: str = "$"):
        if isinstance(value, dict):
            yield location, value
            for key, item in value.items():
                yield from cls._walk(item, f"{location}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from cls._walk(item, f"{location}/{index}")

    @classmethod
    def _assert_document_valid(
        cls, name: str, value: object, schema: dict[str, object]
    ) -> None:
        cls._assert_valid(value, schema, schema)
        if name == "bottle-snapshot.schema.json":
            entries = value["entries"]
            cls._assert_sorted_unique(entries, "path")
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
                cls._assert_sorted_unique(launcher["environment"], "name")

    @staticmethod
    def _assert_sorted_unique(records: list[object], key: str) -> None:
        values = [record[key] for record in records]
        if values != sorted(values) or len(values) != len(set(values)):
            raise AssertionError(f"records are not sorted and unique by {key}")

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

        if isinstance(value, str):
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
        elif isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise AssertionError("array too short")
            if len(value) > schema.get("maxItems", len(value)):
                raise AssertionError("array too long")
            if schema.get("uniqueItems"):
                rendered = [json.dumps(item, sort_keys=True) for item in value]
                if len(rendered) != len(set(rendered)):
                    raise AssertionError("array items are not unique")
            if isinstance(schema.get("items"), dict):
                for item in value:
                    cls._assert_valid(item, schema["items"], root)
        elif isinstance(value, dict):
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
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
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
