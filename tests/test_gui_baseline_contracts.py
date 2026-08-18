from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_TOOL = ROOT / "tools" / "download_gui_assets.py"
BASELINE_TOOL = ROOT / "tools" / "run_gui_baseline.py"
INTERACTION_TOOL = ROOT / "tools" / "prepare_gui_interaction_evidence.py"
SUMMARY_TOOL = ROOT / "tools" / "summarize_gui_compatibility.py"
SOAK_TOOL = ROOT / "tools" / "run_gui_soak.py"
DESKTOP = ROOT / "apps" / "desktop"
TAURI = DESKTOP / "src-tauri"


def load_tool(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


class GuiBaselineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = load_tool(ASSET_TOOL)
        cls.baseline = load_tool(BASELINE_TOOL)
        cls.summary_tool = load_tool(SUMMARY_TOOL)
        cls.soak_tool = load_tool(SOAK_TOOL)

    def test_fixed_official_asset_matrix_is_closed(self) -> None:
        self.assertEqual(
            [asset.app_id for asset in self.assets.BASELINE_ASSETS],
            ["7zip", "sumatrapdf", "notepad-plus-plus"],
        )
        self.assertEqual(
            [asset.sha256 for asset in self.assets.BASELINE_ASSETS],
            [
                "d64a0468f5b5b0b0fc5b2188450bcd655b70809d97b1c4535f2884635094377d",
                "1eee71cccd2ea6e94d5bcea54ee2f759844da3e1a0ee2f6045035b1d17b94381",
                "7c243203265ce8fdac76c839bf744ae35dcf620760eb97c2ea279af498560e45",
            ],
        )
        for asset in self.assets.ASSETS:
            self.assertTrue(asset.url.startswith("https://"))
            self.assertEqual(len(asset.sha256), 64)
            self.assertTrue(asset.window_title_tokens)
            self.assertIn(asset.package_kind, {"installer", "portable-zip"})
        self.assertEqual([asset.app_id for asset in self.assets.EXTENDED_ASSETS], ["firefox", "krita"])
        self.assertEqual(
            [asset.app_id for asset in self.assets.CERTIFICATION_ASSETS],
            ["7zip-x86", "vlc", "winmerge", "audacity-x86", "everything-x86"],
        )
        self.assertEqual(len(self.assets.ASSETS), 10)
        self.assertEqual(
            {asset.guest_architecture for asset in self.assets.CERTIFICATION_ASSETS},
            {"i386", "x86_64"},
        )
        self.assertEqual(self.assets.asset_for("winmerge").guest_architecture, "x86_64")
        self.assertEqual(self.assets.asset_for("winmerge").package_kind, "portable-zip")
        self.assertEqual(
            self.assets.asset_for("winmerge").installed_executable,
            "WinMerge/WinMergeU.exe",
        )
        self.assertEqual(self.assets.asset_for("everything-x86").launch_args, ("-nodb",))
        self.assertEqual(
            {asset.category for asset in self.assets.CERTIFICATION_ASSETS},
            {"win32", "multimedia", "developer-tool", "audio", "search"},
        )
        self.assertTrue(all(asset.launch_args for asset in self.assets.EXTENDED_ASSETS))
        self.assertEqual(
            [asset.install_wait_milliseconds for asset in self.assets.EXTENDED_ASSETS],
            [20_000, 45_000],
        )
        self.assertEqual([asset.screenshot_delay_seconds for asset in self.assets.EXTENDED_ASSETS], [35, 30])
        self.assertEqual(dict(self.assets.EXTENDED_ASSETS[1].runtime_environment)["QT_OPENGL"], "desktop")
        self.assertEqual(self.assets.EXTENDED_ASSETS[1].window_appearance_seconds, 55)

    def test_desktop_shell_is_tauri_and_qt_sources_are_removed(self) -> None:
        self.assertTrue((DESKTOP / "package-lock.json").is_file())
        self.assertTrue((TAURI / "Cargo.lock").is_file())
        self.assertFalse((DESKTOP / "CMakeLists.txt").exists())
        self.assertFalse((DESKTOP / "qml").exists())
        self.assertFalse((DESKTOP / "src" / "compatforgecontroller.cpp").exists())
        package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["dependencies"]["@tauri-apps/api"], "2.11.1")
        self.assertEqual(package["devDependencies"]["@tauri-apps/cli"], "2.11.4")
        config = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(config["identifier"], "dev.compatforge.desktop")
        self.assertEqual(config["app"]["windows"][0]["titleBarStyle"], "Overlay")
        self.assertIn("script-src 'self'", config["app"]["security"]["csp"])
        capability = json.loads((TAURI / "capabilities" / "default.json").read_text(encoding="utf-8"))
        self.assertEqual(
            capability["permissions"],
            ["core:default", "core:window:allow-start-dragging", "dialog:allow-open"],
        )

    def test_tauri_uses_the_shared_application_service(self) -> None:
        rust = (TAURI / "src" / "lib.rs").read_text(encoding="utf-8")
        for symbol in (
            "create_local_context",
            "AutomationService::new",
            "ServiceRequest",
            "service_call",
            "seed_default_applications",
            "open_settings",
        ):
            self.assertIn(symbol, rust)
        self.assertNotIn("std::process::Command", rust)
        self.assertNotIn("compatforge_ffi", rust)
        self.assertNotIn("BASELINE_SPECS", rust)
        service = (ROOT / "crates" / "compatforge-service" / "src" / "jobs.rs").read_text(encoding="utf-8")
        for symbol in ("PreparedLaunch::prepare", "ProcessSupervisor::start", "ExecutableMode::BottleInPlace", "NetworkPolicy::Deny"):
            self.assertIn(symbol, service)

    def test_application_grid_and_function_switches_are_stable(self) -> None:
        frontend = (DESKTOP / "src" / "main.ts").read_text(encoding="utf-8")
        for label in (
            'label: "应用程序"',
            'label: "安装器"',
            'label: "Bottle"',
            'label: "运行记录"',
            'label: "兼容环境"',
            'label: "已安装"',
            'label: "可安装"',
            'label: "运行中"',
            'label: "最近使用"',
            'placeholder="搜索应用"',
        ):
            self.assertIn(label, frontend)
        self.assertIn('class="app-grid"', frontend)
        self.assertIn('data-action="cancel-all"', frontend)
        self.assertIn('data-action="open-settings"', frontend)
        self.assertIn('"applications.list"', frontend)
        self.assertIn('"jobs.submit"', frontend)
        self.assertIn('"jobs.poll"', frontend)
        self.assertIn('getCurrentWindow } from "@tauri-apps/api/window"', frontend)
        self.assertIn("appWindow.startDragging()", frontend)
        self.assertIn("isTitlebarDragTarget", frontend)

    def test_settings_are_a_separate_macos_style_api_client(self) -> None:
        self.assertTrue((DESKTOP / "settings.html").is_file())
        settings = (DESKTOP / "src" / "settings.ts").read_text(encoding="utf-8")
        for label in ("通用", "运行环境", "Bottle", "自动化", "诊断", "辅助功能", "外观"):
            self.assertIn(label, settings)
        for operation in ("settings.get", "settings.update", "bottles.archives.list", "bottles.restore"):
            self.assertIn(operation, settings)
        vite = (DESKTOP / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn('settings: "settings.html"', vite)

    def test_download_requires_explicit_network_opt_in(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-gui-assets-") as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(ASSET_TOOL),
                    "fetch",
                    "7zip",
                    "--cache-root",
                    str(Path(temporary) / "cache"),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("--allow-network", result.stderr)

    def test_portable_zip_materialization_is_bounded_and_traversal_safe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-portable-zip-") as temporary:
            root = Path(temporary)
            archive = root / "winmerge.zip"
            bottle = root / "drive_c"
            bottle.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("WinMerge/WinMergeU.exe", b"MZ-fixed-fixture")
                bundle.writestr("WinMerge/Languages/ChineseSimplified.po", "中文")
            inspection = self.baseline.materialize_portable_zip(
                archive,
                bottle,
                self.baseline.file_sha256(archive),
            )
            self.assertEqual(inspection["format"], "zip")
            self.assertEqual(inspection["entryCount"], 2)
            self.assertEqual((bottle / "WinMerge" / "WinMergeU.exe").read_bytes(), b"MZ-fixed-fixture")

            malicious = root / "traversal.zip"
            with zipfile.ZipFile(malicious, "w") as bundle:
                bundle.writestr("../escape.exe", b"MZ")
            with self.assertRaises(self.baseline.AcceptanceError):
                self.baseline.materialize_portable_zip(
                    malicious,
                    root / "malicious-drive-c",
                    self.baseline.file_sha256(malicious),
                )
            self.assertFalse((root / "escape.exe").exists())

    def test_cache_and_evidence_tools_have_no_shell_or_repository_artifacts(self) -> None:
        source = BASELINE_TOOL.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("Path.home", source)
        self.assertNotIn("urllib", source)
        self.assertIn("bottleInPlace", source)
        self.assertIn('"unverified"', source)
        self.assertIn("WINDOW_APPEARANCE_SECONDS = 30", source)
        self.assertIn("process_group_ids", source)

    def test_acceptance_requires_complete_structured_interaction_evidence(self) -> None:
        with self.assertRaises(self.baseline.AcceptanceError):
            self.baseline.interaction_evidence(None, True)
        with tempfile.TemporaryDirectory(prefix="compatforge-interactions-") as temporary:
            path = Path(temporary) / "interactions.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "2",
                        "attestation": {
                            "mode": "human",
                            "observer": "Compatibility Lab",
                            "observedAt": "2026-08-18T10:00:00+08:00",
                        },
                        "applications": {
                            "7zip": {"fileList": True, "menus": True, "cjkTextReadable": True},
                            "sumatrapdf": {"mainWindow": True, "openDialog": True, "cjkTextReadable": True},
                            "notepad-plus-plus": {
                                "open": True,
                                "edit": True,
                                "saveUtf8Chinese": True,
                                "rereadMatches": True,
                                "cjkTextReadable": True,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            checks = self.baseline.interaction_evidence(path, True)
            self.assertTrue(checks["notepad-plus-plus"]["rereadMatches"])
            checks, attestation = self.baseline.load_interaction_evidence(path, True)
            self.assertTrue(checks["7zip"]["menus"])
            self.assertEqual(
                attestation,
                {
                    "mode": "human",
                    "observer": "Compatibility Lab",
                    "observedAt": "2026-08-18T10:00:00+08:00",
                },
            )

    def test_interaction_evidence_rejects_legacy_or_automated_attestations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-interactions-") as temporary:
            path = Path(temporary) / "interactions.json"
            for value in (
                {"schemaVersion": "1", "applications": {}},
                {
                    "schemaVersion": "2",
                    "attestation": {
                        "mode": "automation",
                        "observer": "runner",
                        "observedAt": "2026-08-18T10:00:00Z",
                    },
                    "applications": {},
                },
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(self.baseline.AcceptanceError):
                    self.baseline.interaction_evidence(path, True, {"7zip"})

    def test_interaction_evidence_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-interactions-") as temporary:
            target = Path(temporary) / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = Path(temporary) / "link.json"
            link.symlink_to(target)
            with self.assertRaises(self.baseline.AcceptanceError):
                self.baseline.interaction_evidence(link, True, {"7zip"})

    def test_interaction_worksheet_is_external_closed_and_fails_safe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-interaction-template-") as temporary:
            output = Path(temporary) / "worksheet.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(INTERACTION_TOOL),
                    "--output",
                    str(output),
                    "--observer",
                    "Compatibility Lab",
                    "--app",
                    "vlc",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            worksheet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(worksheet), {"schemaVersion", "attestation", "applications"})
            self.assertEqual(worksheet["attestation"]["observedAt"], "")
            self.assertTrue(all(value is False for value in worksheet["applications"]["vlc"].values()))
            with self.assertRaises(self.baseline.AcceptanceError):
                self.baseline.interaction_evidence(output, True, {"vlc"})

    def test_visual_observation_classifies_infrastructure_separately(self) -> None:
        self.assertEqual(
            self.baseline.observation_diagnostic(
                {
                    "available": False,
                    "reason": "desktop session is locked",
                    "failureClassification": "test-infrastructure",
                },
                {"available": False},
            )["failureClassification"],
            "test-infrastructure",
        )
        self.assertEqual(
            self.baseline.observation_diagnostic(
                {"available": False, "reason": "target window was not observed"},
                {"available": False},
            )["failureClassification"],
            "runtime-regression",
        )

    def test_compatibility_result_binds_matrix_and_failure_classification(self) -> None:
        asset = self.assets.asset_for("vlc")
        evidence = {
            "status": "unverified",
            "cleanup": True,
            "failureClassification": "test-infrastructure",
            "windows": {"available": False, "reason": "desktop session is locked"},
            "screenshot": {"available": False},
            "exit": {"present": True},
            "interactionChecks": {},
            "residualProcesses": [],
            "installerInspection": {"architecture": "x86_64"},
        }
        result = self.baseline.compatibility_result(
            asset,
            evidence,
            {"packDigest": "sha256:" + "a" * 64},
            "2026-08-18T10:00:00Z",
            "2026-08-18T10:01:00Z",
        )
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["failureClassification"], "test-infrastructure")
        self.assertEqual(result["installerDigest"], "sha256:" + asset.sha256)
        self.assertRegex(result["recipeDigest"], r"^sha256:[0-9a-f]{64}$")

    def test_compatibility_schema_requires_reproducibility_keys_and_closed_failures(self) -> None:
        schema = json.loads((ROOT / "schemas" / "compatibility-result.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(
            {"recipeDigest", "installerDigest", "testSuiteVersion"}.issubset(schema["required"])
        )
        self.assertEqual(
            set(schema["properties"]["failureClassification"]["enum"]),
            self.summary_tool.FAILURE_CLASSIFICATIONS,
        )

    def test_summary_separates_policy_and_infrastructure_blocks(self) -> None:
        assets = [self.assets.asset_for("7zip"), self.assets.asset_for("vlc")]
        results = []
        for asset, classification in zip(assets, ("policy-blocked", "test-infrastructure"), strict=True):
            results.append(
                self.baseline.compatibility_result(
                    asset,
                    {
                        "status": "unverified",
                        "cleanup": True,
                        "failureClassification": classification,
                        "windows": {"available": classification == "policy-blocked"},
                        "screenshot": {"available": classification == "policy-blocked"},
                        "exit": {"present": True},
                        "interactionChecks": {},
                        "residualProcesses": [],
                        "installerInspection": {"architecture": "x86_64"},
                    },
                    {"packDigest": "sha256:" + "b" * 64},
                    "2026-08-18T10:00:00Z",
                    "2026-08-18T10:01:00Z",
                )
            )
        report = self.summary_tool.aggregate(
            {
                "schemaVersion": "1",
                "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                "compatibilityResults": results,
            }
        )
        self.assertEqual(report["releaseGate"], "blocked")
        self.assertEqual(report["policyBlocked"], 1)
        self.assertEqual(report["infrastructureBlocked"], 1)

    def test_summary_fails_closed_for_skips_and_matrix_digest_drift(self) -> None:
        asset = self.assets.asset_for("7zip")
        result = self.baseline.compatibility_result(
            asset,
            {
                "status": "accepted",
                "cleanup": True,
                "windows": {"available": True},
                "screenshot": {"available": True, "path": "/external/7zip.png"},
                "exit": {"present": True},
                "interactionChecks": {
                    "fileList": True,
                    "menus": True,
                    "cjkTextReadable": True,
                },
                "residualProcesses": [],
                "installerInspection": {"architecture": "x86_64"},
            },
            {"packDigest": "sha256:" + "c" * 64},
            "2026-08-18T10:00:00Z",
            "2026-08-18T10:01:00Z",
        )
        result["outcome"] = "skipped"
        report = self.summary_tool.aggregate(
            {
                "schemaVersion": "1",
                "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                "compatibilityResults": [result],
            }
        )
        self.assertEqual(report["releaseGate"], "blocked")
        result["recipeDigest"] = "sha256:" + "0" * 64
        with self.assertRaises(self.baseline.AcceptanceError):
            self.summary_tool.aggregate(
                {
                    "schemaVersion": "1",
                    "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                    "compatibilityResults": [result],
                }
            )

    def test_soak_distinguishes_verified_lifecycle_from_acceptance_and_infrastructure(self) -> None:
        asset = self.assets.asset_for("everything-x86")

        def result(classification: str, visible: bool) -> dict[str, object]:
            return self.baseline.compatibility_result(
                asset,
                {
                    "status": "unverified",
                    "cleanup": True,
                    "failureClassification": classification,
                    "windows": {"available": visible},
                    "screenshot": {
                        "available": visible,
                        **({"path": "/external/everything.png"} if visible else {}),
                    },
                    "exit": {"present": True},
                    "interactionChecks": {},
                    "residualProcesses": [],
                    "installerInspection": {"format": "pe32"},
                },
                {"packDigest": "sha256:" + "d" * 64},
                "2026-08-18T10:00:00Z",
                "2026-08-18T10:01:00Z",
            )

        verified = self.soak_tool.classify_summary(
            {
                "schemaVersion": "1",
                "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                "compatibilityResults": [result("policy-blocked", True)],
            },
            {"everything-x86"},
        )
        self.assertEqual(verified["status"], "verified")
        self.assertFalse(verified["hardFailure"])
        self.assertEqual(verified["applications"][0]["outcome"], "blocked")

        duplicate_check = result("policy-blocked", True)
        duplicate_check["checks"].append(duplicate_check["checks"][0])
        with self.assertRaises(self.baseline.AcceptanceError):
            self.soak_tool.classify_summary(
                {
                    "schemaVersion": "1",
                    "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                    "compatibilityResults": [duplicate_check],
                },
                {"everything-x86"},
            )

        unavailable = self.soak_tool.classify_summary(
            {
                "schemaVersion": "1",
                "testSuiteVersion": self.baseline.TEST_SUITE_VERSION,
                "compatibilityResults": [result("test-infrastructure", False)],
            },
            {"everything-x86"},
        )
        self.assertEqual(unavailable["status"], "unverified")
        self.assertFalse(unavailable["hardFailure"])

    def test_soak_resume_configuration_is_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-soak-resume-") as temporary:
            path = Path(temporary) / "configuration.json"
            selected = {"winmerge", "everything-x86"}
            self.soak_tool.write_configuration(path, selected, 60)
            self.soak_tool.validate_configuration(path, selected, 60)
            with self.assertRaises(self.baseline.AcceptanceError):
                self.soak_tool.validate_configuration(path, {"winmerge"}, 60)
            self.assertEqual(
                self.soak_tool.cycle_application_ids(
                    {
                        "applications": [
                            {"recipeId": "winmerge"},
                            {"recipeId": "everything-x86"},
                        ]
                    }
                ),
                selected,
            )

    def test_soak_report_records_fail_fast_reason(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-soak-report-") as temporary:
            path = Path(temporary) / "summary.json"
            report = self.soak_tool.write_report(
                path,
                [
                    {
                        "status": "unverified",
                        "hardFailure": False,
                        "infrastructureBlocked": True,
                    }
                ],
                60,
                "cycle 1 completed with status unverified",
            )
            self.assertTrue(report["stoppedEarly"])
            self.assertEqual(report["releaseGate"], "blocked")
            self.assertEqual(report["stopReason"], "cycle 1 completed with status unverified")

    def test_residual_process_check_uses_the_launch_process_group(self) -> None:
        with (
            mock.patch.object(
                self.baseline,
                "process_table",
                return_value=[
                    (100, 100, "/runtime/wine unrelated.exe"),
                    (101, 777, "/runtime/wine target.exe"),
                    (102, 102, "/runtime/wine /external/bottle/drive_c/app.exe"),
                    (103, 103, "C:\\windows\\system32\\services.exe"),
                ],
            ),
            mock.patch.object(self.baseline, "prefix_process_ids", return_value={103}),
        ):
            residual = self.baseline.process_snapshot(Path("/external/bottle/drive_c"), 777)
        self.assertEqual(len(residual), 3)
        self.assertTrue(any(value.startswith("101 ") for value in residual))
        self.assertTrue(any(value.startswith("102 ") for value in residual))
        self.assertTrue(any(value.startswith("103 ") for value in residual))

    def test_cleanup_uses_digest_bound_wineserver_and_exact_prefix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-bottle-cleanup-") as temporary:
            root = Path(temporary)
            storage = root / "storage"
            bottle = storage / "bottles" / "probe-fixture"
            drive_c = bottle / "prefix" / "drive_c"
            drive_c.mkdir(parents=True)
            wineserver = root / "wineserver"
            wineserver.write_bytes(b"fixed-wineserver-fixture")
            wineserver.chmod(0o700)
            context = {
                "runtimeBindings": [
                    {
                        "wineserverExecutable": str(wineserver),
                        "environment": {
                            "COMPATFORGE_WINESERVER_EXECUTABLE_SHA256": (
                                "sha256:" + self.baseline.file_sha256(wineserver)
                            ),
                            "WINEDEBUG": "-all",
                        },
                    }
                ]
            }
            completed = subprocess.CompletedProcess([str(wineserver), "-k"], 0, "", "")
            with (
                mock.patch.object(self.baseline.subprocess, "run", return_value=completed) as run,
                mock.patch.object(self.baseline, "prefix_process_ids", return_value=set()),
                mock.patch.object(self.baseline, "process_table", return_value=[]),
                mock.patch.object(self.baseline.time, "sleep"),
            ):
                result = self.baseline.cleanup_bottle(context, storage, "probe-fixture")
            self.assertTrue(result["success"])
            self.assertFalse(bottle.exists())
            self.assertEqual(run.call_args.args[0], [str(wineserver), "-k"])
            self.assertEqual(run.call_args.kwargs["env"]["WINEPREFIX"], str(bottle / "prefix"))

    def test_cleanup_rejects_wineserver_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-bottle-cleanup-") as temporary:
            root = Path(temporary)
            storage = root / "storage"
            (storage / "bottles" / "probe-fixture").mkdir(parents=True)
            wineserver = root / "wineserver"
            wineserver.write_bytes(b"changed")
            wineserver.chmod(0o700)
            result = self.baseline.cleanup_bottle(
                {
                    "runtimeBindings": [
                        {
                            "wineserverExecutable": str(wineserver),
                            "environment": {
                                "COMPATFORGE_WINESERVER_EXECUTABLE_SHA256": "sha256:" + "0" * 64,
                            },
                        }
                    ]
                },
                storage,
                "probe-fixture",
            )
            self.assertFalse(result["success"])
            self.assertTrue((storage / "bottles" / "probe-fixture").exists())

    def test_desktop_session_requires_console_and_awake_display(self) -> None:
        def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(["fixture"], returncode, stdout, "")

        console = '"kCGSSessionOnConsoleKey"=Yes'
        awake = "Assertion status system-wide:\n   UserIsActive                 1\n"
        with mock.patch.object(self.baseline.subprocess, "run", side_effect=[completed(console), completed(awake)]):
            self.assertEqual(self.baseline.desktop_session_state()["state"], "interactive")

        asleep = "Assertion status system-wide:\n   UserIsActive                 0\n"
        with mock.patch.object(self.baseline.subprocess, "run", side_effect=[completed(console), completed(asleep)]):
            value = self.baseline.desktop_session_state()
        self.assertEqual(value["state"], "display-inactive")
        self.assertEqual(value["failureClassification"], "test-infrastructure")

        locked = (
            '"IOConsoleLocked" = No\n'
            '"IOConsoleUsers" = ({"kCGSSessionOnConsoleKey"=Yes,'
            '"CGSSessionScreenIsLocked"=Yes})\n'
        )
        with mock.patch.object(self.baseline.subprocess, "run", side_effect=[completed(locked), completed(awake)]):
            value = self.baseline.desktop_session_state()
        self.assertEqual(value["state"], "locked")
        self.assertFalse(value["observable"])

    def test_window_evidence_is_structured_and_title_bound(self) -> None:
        windows = self.baseline.matching_windows(
            (
                "48498|7-Zip|1288x711\n"
                "wine64-preloader|48499|7-Zip Child|900x700\n"
                "99|Unrelated|800x600\n"
                "100|7-Zip|0x600\n"
            ),
            ("7-Zip",),
        )
        self.assertEqual(
            windows,
            [
                {"processId": 48498, "title": "7-Zip", "width": 1288, "height": 711},
                {"processId": 48499, "title": "7-Zip Child", "width": 900, "height": 700},
            ],
        )

    def test_list_output_is_json_and_does_not_download(self) -> None:
        with tempfile.TemporaryDirectory(prefix="compatforge-gui-assets-") as temporary:
            cache = Path(temporary) / "cache"
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(ASSET_TOOL),
                    "list",
                    "--cache-root",
                    str(cache),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [item["appId"] for item in json.loads(result.stdout)],
                [
                    "7zip",
                    "sumatrapdf",
                    "notepad-plus-plus",
                    "firefox",
                    "krita",
                    "7zip-x86",
                    "vlc",
                    "winmerge",
                    "audacity-x86",
                    "everything-x86",
                ],
            )
            self.assertFalse(cache.exists())


if __name__ == "__main__":
    unittest.main()
