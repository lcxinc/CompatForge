#!/usr/bin/env python3
import json
import sys


def fail(message: str) -> None:
    raise SystemExit(message)


if len(sys.argv) != 4:
    fail("usage: validate-pgadmin-page-report.py <report.json> <analysis.json> <proof.json>")

report_path, analysis_path, proof_path = sys.argv[1:]
with open(report_path, encoding="utf-8") as report_file:
    report = json.load(report_file)
with open(analysis_path, encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)

diagnostics = report.get("diagnostics", {})
href = str(diagnostics.get("href", ""))
visible_text = str(diagnostics.get("visibleTextSample", ""))
required_text = ("Object Explorer", "Servers", "Dashboard", "pgAdmin")

if not href.startswith("http://127.0.0.1:") or not href.endswith("/browser/"):
    fail("pgAdmin page URL was not the local browser endpoint")
if diagnostics.get("readyState") != "complete":
    fail("pgAdmin document did not finish loading")
if int(diagnostics.get("bodyHTMLLength", 0)) < 50_000:
    fail("pgAdmin document HTML is unexpectedly small")
if int(diagnostics.get("visibleElementCount", 0)) < 100:
    fail("pgAdmin visible DOM is unexpectedly sparse")
if not all(token in visible_text for token in required_text):
    fail("pgAdmin navigation and dashboard text were not all visible")
if int(diagnostics.get("resourceCount", 0)) < 20:
    fail("pgAdmin resource graph is incomplete")
if int(diagnostics.get("visibleLoadingElementCount", 0)) != 0:
    fail("pgAdmin loading overlay remained visible")

if int(analysis.get("width", 0)) < 900 or int(analysis.get("height", 0)) < 600:
    fail("pgAdmin compositor screenshot is too small")
if float(analysis.get("luminanceStdDev", 0)) < 25:
    fail("pgAdmin compositor screenshot lacks visual structure")
if int(analysis.get("nonBrightPixelCount", 0)) < 5_000:
    fail("pgAdmin compositor screenshot is effectively blank")
if int(analysis.get("quantizedColorCount", 0)) < 30:
    fail("pgAdmin compositor screenshot has insufficient color detail")

proof = {
    "status": "passed",
    "href": href,
    "readyState": diagnostics.get("readyState"),
    "visibleElementCount": diagnostics.get("visibleElementCount"),
    "requiredText": list(required_text),
    "resourceCount": diagnostics.get("resourceCount"),
    "screenshot": {
        "width": analysis.get("width"),
        "height": analysis.get("height"),
        "luminanceStdDev": analysis.get("luminanceStdDev"),
        "nonBrightPixelCount": analysis.get("nonBrightPixelCount"),
        "quantizedColorCount": analysis.get("quantizedColorCount"),
    },
}
with open(proof_path, "w", encoding="utf-8") as proof_file:
    json.dump(proof, proof_file, ensure_ascii=False, indent=2)
    proof_file.write("\n")

print("MACWIN_PGADMIN_CDP=PASS")
print(f"MACWIN_PGADMIN_VISIBLE_ELEMENTS={proof['visibleElementCount']}")
print(f"MACWIN_PGADMIN_RESOURCES={proof['resourceCount']}")
