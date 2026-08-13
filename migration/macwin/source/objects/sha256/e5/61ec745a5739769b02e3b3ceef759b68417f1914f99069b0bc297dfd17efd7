#!/usr/bin/env bash
set -uo pipefail

APP_PATH="${MACWIN_APP_PATH:-/Users/a1-6/project/Mac-Win/MacWinManager/.build/arm64-apple-macosx/debug/MacWinManagerApp}"
OUTPUT_DIR="${MACWIN_VISUAL_OUTPUT_DIR:-$HOME/Desktop/MacWinVisualAcceptance}"
WINDOW_TITLE_TOKEN="${MACWIN_WINDOW_TITLE_TOKEN:-MacWin}"
TIMEOUT_SECONDS="${MACWIN_VISUAL_WAIT_SECONDS:-20}"
SWEEP_SECONDS="${MACWIN_VISUAL_SWEEP_SECONDS:-1}"
OWNER_NAME="${MACWIN_WINDOW_OWNER:-MacWinManagerApp}"
ALLOW_NONPID_FALLBACK="${MACWIN_VISUAL_ALLOW_NONPID_FALLBACK:-0}"
SCREENSHOT_PATH="${MACWIN_VISUAL_SCREENSHOT:-$OUTPUT_DIR/macwin-ui.png}"
ANALYSIS_JSON="${MACWIN_VISUAL_ANALYSIS_JSON:-$OUTPUT_DIR/macwin-ui-analysis.json}"
RESULT_JSON="${MACWIN_VISUAL_RESULT_JSON:-$OUTPUT_DIR/macwin-visual-acceptance-result.json}"

mkdir -p "$OUTPUT_DIR"

if ! [[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]]; then
  TIMEOUT_SECONDS=20
fi
if ! [[ "$SWEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  SWEEP_SECONDS=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log_file="$OUTPUT_DIR/macwin-visual-acceptance.log"
rm -f "$SCREENSHOT_PATH"
rm -f "$RESULT_JSON"
rm -f "$OUTPUT_DIR/macwin-visual-analysis-report.txt"

if [ ! -x "$APP_PATH" ]; then
  echo "APP_PATH not executable: $APP_PATH" >&2
  exit 1
fi

(
  "$APP_PATH" >"$log_file" 2>&1
) &
APP_PID=$!

analysis_status="not-run"
analysis_reason=""
analysis_resolution=""
analysis_dominant=""
analysis_center_std=""

cleanup() {
  local status=$?
  rm -f "$OUTPUT_DIR/macwin-visual-analysis-report.txt"
  if [ -n "${APP_PID-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    sleep 0.8
    kill -9 "$APP_PID" 2>/dev/null || true
  fi
  pkill -f -- "$APP_PATH" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

emit_status() {
  local status="$1"
  local reason="${2-}"
  echo "visual_acceptance_status=$status"
  [ -n "$reason" ] && echo "reason=$reason"
  echo "window_id=${window_id-}"
  echo "screenshot=$SCREENSHOT_PATH"
  echo "analysis_json=$ANALYSIS_JSON"
  echo "result_json=$RESULT_JSON"
  echo "log_file=$log_file"
  echo "owner=$OWNER_NAME"
  echo "app_path=$APP_PATH"

/usr/bin/python3 - "$RESULT_JSON" "$status" "$reason" "$window_id" "$analysis_status" "$analysis_resolution" "$analysis_dominant" "$analysis_center_std" "$ANALYSIS_JSON" "$SCREENSHOT_PATH" "$APP_PATH" "$OWNER_NAME" "$log_file" "$elapsed" <<'PY'
import json
import sys

result_path, status, reason, window_id, analysis_status, analysis_resolution, analysis_dominant, analysis_center_std, analysis_json, screenshot, app_path, owner, log_file, elapsed = sys.argv[1:15]
with open(result_path, "w", encoding="utf-8") as handle:
    json.dump({
        "status": status,
        "reason": reason,
        "windowId": window_id,
        "analysis": {
            "status": analysis_status if analysis_status not in ("", "-") else None,
            "resolution": analysis_resolution,
            "dominantRatio": analysis_dominant,
            "centerColorStd": analysis_center_std,
        },
        "artifacts": {
            "analysisJson": analysis_json,
            "screenshot": screenshot,
        },
        "process": {
            "owner": owner,
            "appPath": app_path,
            "log": log_file,
        },
        "timing": {
            "elapsedSeconds": int(elapsed) if str(elapsed).isdigit() else elapsed,
        },
    }, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
}

discover_window() {
  local owner="$1"
  local title_token="$2"
  local owner_pid="${3-}"
  if [ -n "$owner_pid" ]; then
    /usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" --discover-smallest "$owner" "$title_token" "$owner_pid" 2>/dev/null || true
  else
    /usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" --discover-smallest "$owner" "$title_token" 2>/dev/null || true
  fi
}

parse_window_id() {
  local line="$1"
  echo "$line" | awk 'NR==1{print $1}'
}

window_id=""
discovery_failures=0
elapsed=0
reason="no_window_found"

while [ "$elapsed" -lt "$TIMEOUT_SECONDS" ]; do
  if [ "$elapsed" -ge 1 ]; then
    sleep "$SWEEP_SECONDS"
  fi
  elapsed=$((elapsed + SWEEP_SECONDS))

  if ! ps -p "$APP_PID" >/dev/null 2>&1; then
    reason="app_process_exited"
    break
  fi

  candidate=""
  for owner in "$OWNER_NAME" "wine"; do
    for token in "$WINDOW_TITLE_TOKEN" ""; do
      candidate="$(discover_window "$owner" "$token" "$APP_PID")"
      if [ -z "$candidate" ] && [ "$ALLOW_NONPID_FALLBACK" = "1" ]; then
        candidate="$(discover_window "$owner" "$token")"
      fi
      if [ -n "$candidate" ]; then
        window_id="$(parse_window_id "$candidate")"
        if [ -n "$window_id" ]; then
          reason=""
          break 2
        fi
      fi
      discovery_failures=$((discovery_failures + 1))
    done
  done
done

if [ -z "$window_id" ]; then
  if [ -z "$reason" ]; then
    reason="no_window_found_after_${TIMEOUT_SECONDS}s_attempts_${discovery_failures}"
  fi
  emit_status failed "$reason"
  echo "elapsed_seconds=$elapsed"
  exit 2
fi

if ! /usr/bin/swift "$SCRIPT_DIR/capture-macos-window.swift" "$window_id" "$SCREENSHOT_PATH" >/dev/null 2>&1; then
  emit_status failed "capture_failed"
  echo "elapsed_seconds=$elapsed"
  exit 3
fi

if ! /usr/bin/python3 "$SCRIPT_DIR/analyze-window-image.py" "$SCREENSHOT_PATH" "$ANALYSIS_JSON" >/dev/null; then
  emit_status failed "analysis_failed"
  echo "elapsed_seconds=$elapsed"
  exit 4
fi

analysis_tmp="$OUTPUT_DIR/macwin-visual-analysis-report.txt"
python3 - "$SCREENSHOT_PATH" > "$analysis_tmp" <<'PY'
import struct
import zlib
import sys
from collections import Counter
from statistics import pstdev

path = sys.argv[1]
with open(path, "rb") as handle:
    data = handle.read()

if data[:8] != b"\x89PNG\r\n\x1a\n":
    print("analysis_status=fail")
    print("analysis_reason=invalid_png")
    sys.exit(3)

position = 8
width = height = None
idat = b""
while position < len(data):
    length = struct.unpack(">I", data[position:position + 4])[0]
    position += 4
    chunk_type = data[position:position + 4]
    position += 4
    chunk = data[position:position + length]
    position += length
    position += 4
    if chunk_type == b"IHDR":
        width, height = struct.unpack(">IIBBBBB", chunk)[:2]
    elif chunk_type == b"IDAT":
        idat += chunk
    elif chunk_type == b"IEND":
        break

raw = zlib.decompress(idat)
row_bytes = 4 * width
rows = []
prev = bytearray(row_bytes)
index = 0
for _ in range(height):
    filter_type = raw[index]
    index += 1
    row = bytearray(raw[index:index + row_bytes])
    index += row_bytes

    if filter_type == 1:
        for x in range(4, row_bytes):
            row[x] = (row[x] + row[x - 4]) & 0xFF
    elif filter_type == 2:
        for x in range(row_bytes):
            row[x] = (row[x] + prev[x]) & 0xFF
    elif filter_type == 3:
        for x in range(row_bytes):
            left = row[x - 4] if x >= 4 else 0
            up = prev[x]
            row[x] = (row[x] + (left + up) // 2) & 0xFF
    elif filter_type == 4:
        for x in range(row_bytes):
            a = row[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            if pa <= pb and pa <= pc:
                pred = a
            elif pb <= pc:
                pred = b
            else:
                pred = c
            row[x] = (row[x] + pred) & 0xFF

    rows.append(bytes(row))
    prev = bytearray(row)

pixels = []
for row in rows:
    for i in range(0, len(row), 4):
        pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))

if not pixels:
    print("analysis_status=fail")
    print("analysis_reason=no_pixels")
    sys.exit(4)

dominant_ratio = Counter(pixels)[pixels[0]] / len(pixels)
center_samples = []
x0, x1 = width // 6, width * 5 // 6
y0, y1 = height // 6, height * 5 // 6
for y in range(y0, y1):
    row = rows[y]
    for x in range(x0 * 4, x1 * 4, 4):
        center_samples.append((row[x], row[x + 1], row[x + 2]))

if center_samples:
    red = [c[0] for c in center_samples]
    green = [c[1] for c in center_samples]
    blue = [c[2] for c in center_samples]
    center_std = max(pstdev(red), pstdev(green), pstdev(blue))
else:
    center_std = 0.0

status = (
    "pass"
    if (width >= 320 and height >= 240 and dominant_ratio < 0.75 and center_std > 1.2)
    else "fail"
)

print(f"analysis_status={status}")
print(f"resolution={width}x{height}")
print(f"dominant_ratio={dominant_ratio:.6f}")
print(f"center_color_std={center_std:.4f}")

if status != "pass":
    print("analysis_reason=low_variance_or_small_capture")
    sys.exit(5)
PY

if [ -f "$ANALYSIS_JSON" ]; then
  classification="$(/usr/bin/python3 - "$ANALYSIS_JSON" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
print(data.get("classification", "unknown"))
PY
)"
fi

analysis_status="$(grep '^analysis_status=' "$analysis_tmp" | tail -n 1 | cut -d= -f2- || true)"
analysis_reason="$(grep '^analysis_reason=' "$analysis_tmp" | tail -n 1 | cut -d= -f2- || true)"
analysis_resolution="$(grep '^resolution=' "$analysis_tmp" | tail -n 1 | cut -d= -f2- || true)"
analysis_dominant="$(grep '^dominant_ratio=' "$analysis_tmp" | tail -n 1 | cut -d= -f2- || true)"
analysis_center_std="$(grep '^center_color_std=' "$analysis_tmp" | tail -n 1 | cut -d= -f2- || true)"

if [ -z "$analysis_status" ]; then
  emit_status failed "analysis_parse_failed"
  echo "elapsed_seconds=$elapsed"
  exit 7
fi

emit_status "$analysis_status" "$analysis_reason"
echo "resolution=$analysis_resolution"
echo "dominant_ratio=$analysis_dominant"
echo "center_color_std=$analysis_center_std"
echo "analysis_classification=${classification:-unknown}"
echo "elapsed_seconds=$elapsed"
rm -f "$analysis_tmp"
exit 0
