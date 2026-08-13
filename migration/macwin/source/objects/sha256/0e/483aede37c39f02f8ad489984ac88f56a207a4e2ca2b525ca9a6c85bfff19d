#!/usr/bin/env python3

import json
import sys


def fail(message):
    print(message)
    raise SystemExit(1)


if len(sys.argv) != 5:
    raise SystemExit(
        "usage: validate-chromium-page-report.py "
        "<sample-id> <cdp-report.json> <image-analysis.json> <proof.json>"
    )

sample_id, report_path, analysis_path, proof_path = sys.argv[1:]
with open(report_path, encoding="utf-8") as handle:
    report = json.load(handle)
with open(analysis_path, encoding="utf-8") as handle:
    image = json.load(handle)

diagnostics = report.get("diagnostics") or {}
failures = []

if sample_id == "lenovo-app-store":
    href = str(diagnostics.get("href") or "")
    title = str(diagnostics.get("title") or "")
    visible_text = str(diagnostics.get("visibleTextSample") or "")
    explore_entry = diagnostics.get("exploreEntry") or {}
    checks = {
        "targetURL": "store.lenovomm.cn" in href,
        "targetTitle": "联想应用商店" in title,
        "documentComplete": diagnostics.get("readyState") == "complete",
        "nativeCommandLineReady": diagnostics.get("nativeCommandLineReady") is True,
        "exploreEntryInitialized": explore_entry.get("initialized") is True,
        "bannerReady": int(diagnostics.get("bannerCount", -1)) >= 1,
        "cardsReady": int(diagnostics.get("cardCount", -1)) >= 1,
        "bannerResponse": diagnostics.get("bannerResponse") is True,
        "recommendIdle": diagnostics.get("recommendLoading") is False,
        "substantialDOM": int(diagnostics.get("visibleElementCount", 0)) >= 100,
        "expectedText": "推荐" in visible_text and ("打开" in visible_text or "游戏百宝箱" in visible_text),
        "imagesLoaded": int(diagnostics.get("completeImageCount", 0)) >= 1,
    }
elif sample_id == "openplc-editor":
    href = str(diagnostics.get("href") or "")
    title = str(diagnostics.get("title") or "")
    visible_text = str(diagnostics.get("visibleTextSample") or "")
    checks = {
        "targetURL": "openplc-editor" in href.lower()
        and href.lower().endswith("/dist/renderer/index.html"),
        "targetTitle": "openplc editor" in title.lower(),
        "documentComplete": diagnostics.get("readyState") == "complete",
        "substantialDOM": int(diagnostics.get("visibleElementCount", 0)) >= 30,
        "homeActionsReady": all(
            token in visible_text
            for token in ("New Project", "Open", "Tutorials", "Exit")
        ),
        "projectBrowserReady": "Projects" in visible_text
        and "Order by" in visible_text
        and "Recent" in visible_text,
    }
else:
    fail(f"unsupported-sample:{sample_id}")

classification = str(image.get("classification") or "")
checks["compositorImage"] = classification in {"rendered", "partial-render-window"}
checks["opaqueImage"] = float(image.get("transparentRatio", 1.0)) < 0.50

for name, passed in checks.items():
    if not passed:
        failures.append(name)

proof = {
    "sampleId": sample_id,
    "status": "rendered" if not failures else "failed",
    "checks": checks,
    "failedChecks": failures,
    "reportPath": report_path,
    "analysisPath": analysis_path,
    "href": diagnostics.get("href"),
    "title": diagnostics.get("title"),
    "visibleElementCount": diagnostics.get("visibleElementCount"),
    "bannerCount": diagnostics.get("bannerCount"),
    "cardCount": diagnostics.get("cardCount"),
    "imageClassification": classification,
}
with open(proof_path, "w", encoding="utf-8") as handle:
    json.dump(proof, handle, ensure_ascii=False, indent=2)
    handle.write("\n")

if failures:
    fail("failed:" + ",".join(failures))
print("rendered")
