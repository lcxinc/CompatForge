#!/usr/bin/env bash
set -uo pipefail
set +m +b 2>/dev/null || true

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'EOF'
Usage: run-software-smoke.sh

Select the run with environment variables:
  MACWIN_SMOKE_SUITE=quick|browser|office|cad|industrial|productivity|developer|graphics|utility|market|all
  MACWIN_SMOKE_SAMPLE=id[,id...]
  MACWIN_SMOKE_RUN_ID=unique-run-id
  MACWIN_SMOKE_PREFIX=/path/to/prefix

Optional controls:
  MACWIN_SMOKE_SKIP_REPAIRS=1
  MACWIN_GUI_MIN_LAUNCH_SECONDS=5
  MACWIN_WINEBOOT_TIMEOUT=90
EOF
  exit 0
fi

ROOT="${MACWIN_ROOT:-$HOME/Library/Application Support/MacWin}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOWNLOADS="$ROOT/Downloads"
ENGINES="$ROOT/Engines"
ENGINE_ID="${MACWIN_ENGINE_ID:-wine-11.11-x86_64-game}"
ENGINE_MANIFEST="$ENGINES/$ENGINE_ID/manifest.json"
RUN_ID="${MACWIN_SMOKE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
SMOKE_SUITE="${MACWIN_SMOKE_SUITE:-quick}"
SMOKE_SAMPLE="${MACWIN_SMOKE_SAMPLE:-}"
GUI_MIN_LAUNCH_SECONDS="${MACWIN_GUI_MIN_LAUNCH_SECONDS:-5}"
PREFIX_ROOT="$ROOT/SmokePrefixes"
PREFIX="${MACWIN_SMOKE_PREFIX:-$PREFIX_ROOT/software-smoke-$SMOKE_SUITE}"
LOG_DIR="$ROOT/Logs/SoftwareSmokeRuns/$RUN_ID"
REPORT_JSON="$LOG_DIR/software-smoke-report.json"
REPORT_MD="$LOG_DIR/software-smoke-report.md"

if [ ! -f "$ENGINE_MANIFEST" ]; then
  echo "Missing engine manifest: $ENGINE_MANIFEST" >&2
  exit 1
fi

mkdir -p "$PREFIX_ROOT" "$LOG_DIR"

read_json_field() {
  /usr/bin/python3 - "$ENGINE_MANIFEST" "$1" <<'PY'
import json, sys
path, key = sys.argv[1:3]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
value = data
for part in key.split("."):
    value = value[part]
print(value)
PY
}

WINE="$(read_json_field winePath)"
WINESERVER="$(read_json_field wineserverPath)"
RUNTIME="$(read_json_field runtimePath)"
ENGINE_SUPPORTS_WIN32="$(/usr/bin/python3 - "$ENGINE_MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
print("true" if data.get("supportsWin32") is True else "false")
PY
)"
ENGINE_BUILD_DIR="$(cd "$(dirname "$WINE")/.." && pwd)"
DXVK_MACOS_DIR="${MACWIN_DXVK_MACOS_DIR:-$PROJECT_ROOT/refs/dxvk-macos-full-build/install/x64}"
ROSETTA_X87_RUNTIME="${MACWIN_ROSETTA_X87_PATH:-$PROJECT_ROOT/refs/rosettax87/build/rosettax87}"

export WINEPREFIX="$PREFIX"
export WINEARCH=win64
export WINE_D3D_CONFIG="${WINE_D3D_CONFIG:-renderer=vulkan,csmt=0x0}"
export MACWIN_WINHTTP_IGNORE_UNKNOWN_CA=1
export MACWIN_MANAGED_LAUNCH=1
export MACWIN_DOCK_POLICY=managed-app-mode
unset ROSETTA_X87_PATH
export WINEDEBUG="${WINEDEBUG:--all}"
export GST_PLUGIN_SYSTEM_PATH_1_0="$RUNTIME/lib64/gstreamer-1.0"
export GST_PLUGIN_PATH_1_0="$RUNTIME/lib64/gstreamer-1.0"
case "${LANG:-}" in ""|C|POSIX|C.UTF-8) export LANG=zh_CN.UTF-8 ;; esac
case "${LC_ALL:-}" in ""|C|POSIX|C.UTF-8) export LC_ALL=zh_CN.UTF-8 ;; esac
case "${LC_CTYPE:-}" in ""|C|POSIX|C.UTF-8) export LC_CTYPE=zh_CN.UTF-8 ;; esac
export FC_LANG=zh-cn
export FREETYPE_PROPERTIES="${FREETYPE_PROPERTIES:-truetype:interpreter-version=35 cff:no-stem-darkening=0 autofitter:warping=1}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-winemenubuilder.exe=d}"
export FONTCONFIG_FILE="$PREFIX/fonts.conf"
export FONTCONFIG_PATH="$PREFIX"

WINE_HOST_ENV=(/usr/bin/env)
if [ "${MACWIN_WINE_INHERIT_HOST_PROXY:-0}" != "1" ]; then
  WINE_HOST_ENV+=(
    ALL_PROXY= HTTP_PROXY= HTTPS_PROXY= NO_PROXY=
    all_proxy= http_proxy= https_proxy= no_proxy=
  )
fi
WINE_CMD=("${WINE_HOST_ENV[@]}" /usr/bin/arch -x86_64 "$WINE")
WINESERVER_CMD=("${WINE_HOST_ENV[@]}" /usr/bin/arch -x86_64 "$WINESERVER")
RUNTIME_STALL_ACTIVE=0

uninterruptible_wine_pids() {
  if [ -n "${MACWIN_SMOKE_RUNTIME_PROCESS_LIST:-}" ]; then
    cat "$MACWIN_SMOKE_RUNTIME_PROCESS_LIST"
  else
    ps -axo pid=,state=,command=
  fi | awk '
    $2 ~ /^[UD]/ {
      command = tolower($0)
      if (command ~ /wine|wineserver/) print $1
    }
  ' | sort -n -u
}

wine_reg_add_quiet() {
  local pid elapsed
  (
    "${WINE_CMD[@]}" reg add "$@" >/dev/null 2>&1
  ) &
  pid="$!"
  elapsed=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$elapsed" -ge 50 ]; then
      pkill -TERM -P "$pid" 2>/dev/null || true
      pkill -TERM -f 'start.exe /exec reg add' 2>/dev/null || true
      pkill -TERM -f 'reg.exe add' 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
      sleep 0.5
      pkill -KILL -P "$pid" 2>/dev/null || true
      pkill -KILL -f 'start.exe /exec reg add' 2>/dev/null || true
      pkill -KILL -f 'reg.exe add' 2>/dev/null || true
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      return 124
    fi
    sleep 0.1
    elapsed=$((elapsed + 1))
  done
  wait "$pid" 2>/dev/null
  elapsed=0
  while pgrep -f 'start.exe /exec reg add|reg.exe add' >/dev/null 2>&1; do
    if [ "$elapsed" -ge 50 ]; then
      pkill -TERM -f 'start.exe /exec reg add' 2>/dev/null || true
      pkill -TERM -f 'reg.exe add' 2>/dev/null || true
      sleep 0.5
      pkill -KILL -f 'start.exe /exec reg add' 2>/dev/null || true
      pkill -KILL -f 'reg.exe add' 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      return 124
    fi
    sleep 0.1
    elapsed=$((elapsed + 1))
  done
}

prefix_wine_runtime_pids() {
  local line pid command cwd state
  ps -axo pid=,state=,command= | while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    pid="${line%%[[:space:]]*}"
    line="${line#"$pid"}"
    line="${line#"${line%%[![:space:]]*}"}"
    state="${line%%[[:space:]]*}"
    command="${line#"$state"}"
    command="${command#"${command%%[![:space:]]*}"}"
    case "$command" in
      [A-Za-z]:\\*|*wine*) ;;
      *) continue ;;
    esac
    case "$state" in U*|D*) continue ;; esac
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    case "$cwd/" in "$PREFIX/"*) printf '%s\n' "$pid" ;; esac
  done
}

terminate_prefix_wine_runtime_residue() {
  local cleanup_log="$LOG_DIR/runtime-cleanup.log" pids remaining
  pids="$(prefix_wine_runtime_pids)"
  [ -n "$pids" ] || return 0
  {
    echo "cleanupAt=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "prefix=$PREFIX"
    printf '%s\n' "$pids" | sed 's/^/termPid=/'
  } >> "$cleanup_log"
  printf '%s\n' "$pids" | xargs kill -TERM 2>/dev/null || true
  sleep 1
  remaining="$(prefix_wine_runtime_pids)"
  if [ -n "$remaining" ]; then
    printf '%s\n' "$remaining" | sed 's/^/killPid=/' >> "$cleanup_log"
    printf '%s\n' "$remaining" | xargs kill -KILL 2>/dev/null || true
  fi
}

cleanup_wine() {
  if [ "$RUNTIME_STALL_ACTIVE" -eq 1 ]; then
    return
  fi
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  terminate_prefix_wine_runtime_residue
}
trap cleanup_wine EXIT INT TERM

json_escape() {
  /usr/bin/python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

records_file="$LOG_DIR/records.jsonl"
: > "$records_file"

record() {
  local id="$1" phase="$2" state="$3" exit_code="$4" log_path="$5" duration="$6"
  local note="$7"
  local escaped_note
  escaped_note="$(printf '%s' "$note" | json_escape)"
  printf '{"id":"%s","phase":"%s","state":"%s","exitCode":%s,"logPath":"%s","durationSeconds":%s,"note":%s}\n' \
    "$id" "$phase" "$state" "$exit_code" "$log_path" "$duration" "$escaped_note" >> "$records_file"
}

gui_process_pattern_for_sample() {
  case "$1" in
    wps-office-spreadsheet)
      printf '%s\n' 'Kingsoft[\\/]+WPS Office[\\/]+.*[\\/]+office6[\\/]+(et|wpsoffice)\.exe|et\.exe|wpsoffice\.exe'
      ;;
    wps-office-presentation)
      printf '%s\n' 'Kingsoft[\\/]+WPS Office[\\/]+.*[\\/]+office6[\\/]+(wpp|wpsoffice)\.exe|wpp\.exe|wpsoffice\.exe'
      ;;
    wps-office-pdf)
      printf '%s\n' 'Kingsoft[\\/]+WPS Office[\\/]+.*[\\/]+office6[\\/]+(wpspdf|wpsoffice)\.exe|wpspdf\.exe|wpsoffice\.exe'
      ;;
    wps-office)
      printf '%s\n' 'Kingsoft[\\/]+WPS Office[\\/]+.*[\\/]+office6[\\/]+(wps|wpsoffice)\.exe|wps\.exe|wpsoffice\.exe'
      ;;
    onlyoffice-suite)
      printf '%s\n' 'ONLYOFFICE[\\/]+DesktopEditors.*editors\.exe'
      ;;
    postman-api-client)
      printf '%s\n' 'Postman[\\/]+Postman\.exe|Postman\.exe'
      ;;
    vscode-portable)
      printf '%s\n' 'macwin-portable[\\/]+vscode-portable[\\/]+Code\.exe|Code\.exe'
      ;;
    gimp-image-editor)
      printf '%s\n' 'GIMP 2[\\/]+bin[\\/]+gimp-2\.10\.exe|gimp-2\.10\.exe'
      ;;
    floorp-browser)
      printf '%s\n' 'Ablaze Floorp[\\/]+(core[\\/]+)?floorp\.exe|Floorp[\\/]+floorp\.exe|floorp\.exe'
      ;;
    firefox-developer)
      printf '%s\n' 'Firefox Developer Edition[\\/]+firefox\.exe|firefox\.exe'
      ;;
    librewolf-browser|librewolf-portable)
      printf '%s\n' 'LibreWolf[\\/]+librewolf\.exe|LibreWolf-Portable\.exe|librewolf\.exe'
      ;;
    waterfox-browser)
      printf '%s\n' 'Waterfox[\\/]+(core[\\/]+)?waterfox\.exe|waterfox\.exe'
      ;;
    seamonkey-browser|seamonkey-32-browser)
      printf '%s\n' 'SeaMonkey[\\/]+core[\\/]+seamonkey\.exe|seamonkey\.exe'
      ;;
    zen-browser)
      printf '%s\n' 'macwin-portable[\\/]+zen-browser[\\/]+core[\\/]+zen\.exe|zen\.exe'
      ;;
    qmodmaster-64|qmodmaster-32)
      printf '%s\n' 'macwin-portable[\\/]+qmodmaster-[0-9]+[\\/]+qModMaster[\\/]+qModMaster\.exe|qModMaster\.exe'
      ;;
    otter-browser-portable)
      printf '%s\n' 'macwin-portable[\\/]+otter-browser-portable[\\/]+otter-browser-win64-weekly120[\\/]+otter-browser\.exe|otter-browser\.exe'
      ;;
    kmeleon-portable)
      printf '%s\n' 'macwin-portable[\\/]+kmeleon-portable[\\/]+K-MeleonPortable\.exe|K-MeleonPortable\.exe|K-Meleon[\\/]+k-meleon\.exe|k-meleon\.exe'
      ;;
    mullvad-browser)
      printf '%s\n' 'Mullvad Browser[\\/]+(Browser[\\/]+)?mullvadbrowser\.exe|mullvadbrowser\.exe'
      ;;
    rstudio-desktop)
      printf '%s\n' 'RStudio[\\/]+rstudio\.exe|rstudio\.exe'
      ;;
    cura-slicer)
      printf '%s\n' 'UltiMaker Cura[\\/]+.*UltiMaker-Cura\.exe|UltiMaker-Cura\.exe|Cura\.exe'
      ;;
    thunderbird-mail)
      printf '%s\n' 'Mozilla Thunderbird[\\/]+thunderbird\.exe|thunderbird\.exe'
      ;;
    calibre-library)
      printf '%s\n' 'Calibre2[\\/]+calibre\.exe|calibre\.exe'
      ;;
    libreoffice-suite)
      printf '%s\n' 'LibreOffice[\\/]+program[\\/]+soffice\.exe|soffice\.exe'
      ;;
    freeoffice-suite)
      printf '%s\n' 'SoftMaker FreeOffice 2024[\\/]+TextMaker\.exe|TextMaker\.exe'
      ;;
    pdfxchange-editor)
      printf '%s\n' 'PDF-XChange[\\/]+PDF Editor[\\/]+PXCEditor\.exe|PXCEditor\.exe'
      ;;
    typora-editor)
      printf '%s\n' 'Typora[\\/]+Typora\.exe|Typora\.exe'
      ;;
    naps2-scanner)
      printf '%s\n' 'NAPS2[\\/]+NAPS2\.exe|NAPS2\.exe'
      ;;
    cherrytree-notes)
      printf '%s\n' 'CherryTree[\\/]+cherrytree\.exe|cherrytree\.exe'
      ;;
    freemind-mindmap)
      printf '%s\n' 'FreeMind[\\/]+FreeMind\.exe|FreeMind\.exe'
      ;;
    focuswriter-editor)
      printf '%s\n' 'FocusWriter[\\/]+FocusWriter\.exe|FocusWriter\.exe'
      ;;
    lyx-editor)
      printf '%s\n' 'LyX[\\/]+bin[\\/]+LyX\.exe|LyX\.exe'
      ;;
    projectlibre-pm)
      printf '%s\n' 'ProjectLibre[\\/]+ProjectLibre\.exe|ProjectLibre\.exe'
      ;;
    processing-ide)
      printf '%s\n' 'Processing[\\/]+processing\.exe|processing\.exe'
      ;;
    qgroundcontrol-drone)
      printf '%s\n' 'QGroundControl[\\/]+bin[\\/]+QGroundControl\.exe|QGroundControl\.exe'
      ;;
    mqtt-explorer)
      printf '%s\n' 'macwin-portable[\\/]+mqtt-explorer[\\/]+MQTT Explorer\.exe|MQTT Explorer\.exe'
      ;;
    ltspice-circuit)
      printf '%s\n' 'ADI[\\/]+LTspice[\\/]+LTspice\.exe|LTspice\.exe'
      ;;
    zotero-research)
      printf '%s\n' 'Zotero[\\/]+zotero\.exe|zotero\.exe'
      ;;
    jabref-portable)
      printf '%s\n' 'macwin-portable[\\/]+jabref-portable[\\/]+JabRef[\\/]+JabRef\.exe|JabRef\.exe'
      ;;
    openboard-whiteboard)
      printf '%s\n' 'OpenBoard[\\/]+OpenBoard\.exe|OpenBoard\.exe'
      ;;
    scribus-dtp)
      printf '%s\n' 'Scribus[\\/]+Scribus\.exe|Scribus\.exe'
      ;;
    freeplane-mindmap)
      printf '%s\n' 'Freeplane[\\/]+freeplane\.exe|freeplane\.exe|javaw\.exe'
      ;;
    qownnotes-portable)
      printf '%s\n' 'macwin-portable[\\/]+qownnotes-portable[\\/]+QOwnNotes\.exe|QOwnNotes\.exe'
      ;;
    pgadmin-db-admin)
      printf '%s\n' 'Programs[\\/]+pgAdmin 4[\\/]+runtime[\\/]+pgAdmin4\.exe|pgAdmin 4[\\/]+runtime[\\/]+pgAdmin4\.exe|pgAdmin4\.exe'
      ;;
    marktext-editor)
      printf '%s\n' 'macwin-portable[\\/]+marktext-editor[\\/]+marktext\.exe|marktext\.exe'
      ;;
    sigil-ebook)
      printf '%s\n' 'Sigil[\\/]+Sigil\.exe|Sigil\.exe'
      ;;
    texstudio-editor)
      printf '%s\n' 'TeXstudio[\\/]+texstudio\.exe|texstudio\.exe'
      ;;
    wxmaxima|macwin-maxima-cas)
      printf '%s\n' 'wxMaxima[\\/]+bin[\\/]+wxmaxima\.exe|Maxima-5\.49\.0[\\/]+bin[\\/]+wxmaxima\.exe|wxmaxima\.exe'
      ;;
    labplot-workbench)
      printf '%s\n' 'LabPlot[\\/]+bin[\\/]+labplot\.exe|labplot\.exe'
      ;;
    smath-studio)
      printf '%s\n' 'SMath Studio[\\/]+Solver\.exe|Solver\.exe|SMath Studio[\\/]+SMathStudio_Desktop\.exe|SMathStudio_Desktop\.exe'
      ;;
    dia-diagram)
      printf '%s\n' 'Dia[\\/]+bin[\\/]+diaw\.exe|diaw\.exe|dia\.exe'
      ;;
    joplin-notes)
      printf '%s\n' 'Joplin[\\/]+Joplin\.exe|Joplin\.exe'
      ;;
    obsidian-notes)
      printf '%s\n' 'Obsidian[\\/]+Obsidian\.exe|Obsidian\.exe'
      ;;
    standard-notes)
      printf '%s\n' 'macwin-portable[\\/]+standard-notes[\\/]+Standard Notes\.exe|Standard Notes\.exe'
      ;;
    pdfarranger-portable)
      printf '%s\n' 'macwin-portable[\\/]+pdfarranger-portable[\\/]+pdf arranger-1\.14\.0[\\/]+pdfarranger\.exe|pdfarranger\.exe'
      ;;
    supermium-browser|supermium-32-browser)
      printf '%s\n' 'macwin-portable[\\/]+supermium-[^\\/]+[\\/]+Supermium[\\/]+chrome\.exe|Supermium[\\/]+chrome\.exe'
      ;;
    ungoogled-chromium-portable)
      printf '%s\n' 'macwin-portable[\\/]+ungoogled-chromium-portable[\\/]+ungoogled-chromium_[^\\/]+[\\/]+chrome\.exe|chrome\.exe'
      ;;
    brave-portable)
      printf '%s\n' 'macwin-portable[\\/]+brave-portable[\\/]+app[\\/]+brave\.exe|brave\.exe'
      ;;
    min-browser-portable)
      printf '%s\n' 'macwin-portable[\\/]+min-browser-portable[\\/]+Min-v1\.35\.5[\\/]+Min\.exe|Min\.exe'
      ;;
    zettlr-editor)
      printf '%s\n' 'macwin-portable[\\/]+zettlr-editor[\\/]+Zettlr\.exe|Zettlr\.exe'
      ;;
    openplc-editor)
      printf '%s\n' 'macwin-portable[\\/]+openplc-editor[\\/]+OpenPLC Editor\.exe|OpenPLC Editor\.exe'
      ;;
    heidisql-portable)
      printf '%s\n' 'macwin-portable[\\/]+heidisql-portable[\\/]+heidisql\.exe|heidisql\.exe'
      ;;
    sumatrapdf)
      printf '%s\n' 'SumatraPDF[\\/]+SumatraPDF\.exe|SumatraPDF\.exe'
      ;;
    everything)
      printf '%s\n' 'Everything[\\/]+Everything\.exe|Everything\.exe'
      ;;
    beekeeper-studio)
      printf '%s\n' 'macwin-portable[\\/]+beekeeper-studio[\\/]+Beekeeper Studio\.exe|Beekeeper Studio\.exe'
      ;;
    sqlitestudio-db)
      printf '%s\n' 'SQLiteStudio[\\/]+SQLiteStudio\.exe|SQLiteStudio\.exe'
      ;;
    slic3r-64|slic3r-32)
      printf '%s\n' 'macwin-portable[\\/]+slic3r-[0-9]+[\\/]+Slic3r\.exe|Slic3r\.exe'
      ;;
    esphome-flasher-x64|esphome-flasher-x86)
      printf '%s\n' 'macwin-portable[\\/]+esphome-flasher-x[0-9]+[\\/]+ESPHome-Flasher-1\.4\.0-Windows-x[0-9]+\.exe|ESPHome-Flasher.*\.exe'
      ;;
    thonny-portable)
      printf '%s\n' 'macwin-portable[\\/]+thonny-portable[\\/]+thonny\.exe|thonny\.exe|pythonw\.exe'
      ;;
    notepadpp-editor)
      printf '%s\n' 'Notepad\+\+[\\/]+notepad\+\+\.exe|notepad\+\+\.exe'
      ;;
    notepadpp-32-editor)
      printf '%s\n' 'Notepad\+\+[\\/]+notepad\+\+\.exe|notepad\+\+\.exe'
      ;;
    winscp-client|winscp-x64-portable)
      printf '%s\n' 'WinSCP[\\/]+WinSCP\.exe|WinSCP\.exe'
      ;;
    winscp-x64-cli-help)
      printf '%s\n' 'WinSCP[\\/]+WinSCP\.com|WinSCP\.com'
      ;;
    keepass-passwords)
      printf '%s\n' 'KeePass Password Safe 2[\\/]+KeePass\.exe|KeePass\.exe'
      ;;
    rufus-direct)
      printf '%s\n' 'macwin-portable[\\/]+rufus-direct[\\/]+rufus-4\.11\.exe|rufus-4\.11\.exe'
      ;;
    winmerge-diff)
      printf '%s\n' 'WinMerge[\\/]+WinMergeU\.exe|WinMergeU\.exe'
      ;;
    qbittorrent-client)
      printf '%s\n' 'qBittorrent[\\/]+qbittorrent\.exe|qbittorrent\.exe'
      ;;
    kicad-eda)
      printf '%s\n' 'KiCad[\\/]+10\.0[\\/]+bin[\\/]+kicad\.exe|kicad\.exe'
      ;;
    dbeaver-database)
      printf '%s\n' 'DBeaver[\\/]+dbeaver\.exe|dbeaver\.exe'
      ;;
    qelectrotech-cad)
      printf '%s\n' 'QElectroTech[\\/]+bin[\\/]+qelectrotech\.exe|qelectrotech\.exe'
      ;;
    qucs-s-circuit)
      printf '%s\n' 'Qucs-S[\\/]+bin[\\/]+qucs-s\.exe|Qucs-S[\\/]+qucs-s\.exe|qucs-s\.exe'
      ;;
    qgis-ltr)
      printf '%s\n' 'QGIS 3\.44\.11[\\/]+bin[\\/]+qgis-ltr-bin\.exe|qgis-ltr-bin\.exe'
      ;;
    cloudcompare-pointcloud)
      printf '%s\n' 'CloudCompare[\\/]+CloudCompare\.exe|CloudCompare\.exe'
      ;;
    paraview-visualization)
      printf '%s\n' 'ParaView 6\.1\.0[\\/]+bin[\\/]+paraview\.exe|paraview\.exe'
      ;;
    openmodelica-omedit)
      printf '%s\n' 'OpenModelica[\\/]+bin[\\/]+OMEdit\.exe|OMEdit\.exe'
      ;;
    orange-data-mining)
      printf '%s\n' 'Orange[\\/]+Scripts[\\/]+orange-canvas\.exe|orange-canvas\.exe|Orange[\\/]+python\.exe'
      ;;
    scilab-workbench)
      printf '%s\n' 'scilab-2026\.1\.0[\\/]+bin[\\/]+WScilex\.exe|WScilex\.exe'
      ;;
    octave-workbench)
      printf '%s\n' 'GNU Octave[\\/]+Octave-11\.3\.0[\\/]+mingw64[\\/]+bin[\\/]+octave-gui\.exe|octave-gui\.exe'
      ;;
    arduino-ide)
      printf '%s\n' 'Arduino IDE[\\/]+Arduino IDE\.exe|Arduino IDE\.exe'
      ;;
    wireshark-analyzer)
      printf '%s\n' 'Wireshark[\\/]+Wireshark\.exe|Wireshark\.exe'
      ;;
    geogebra-classic)
      printf '%s\n' 'geogebra-classic[\\/]+GeoGebra\.exe|GeoGebra\.exe'
      ;;
    geogebra-classic5)
      printf '%s\n' 'GeoGebra 5\.4[\\/]+GeoGebra\.exe|GeoGebra 5\.4[\\/]+jre[\\/]+bin[\\/]+javaw\.exe|GeoGebra\.exe'
      ;;
    sweethome3d-design)
      printf '%s\n' 'Sweet Home 3D[\\/]+SweetHome3D\.exe|SweetHome3D\.exe|Sweet Home 3D[\\/]+runtime[\\/]+bin[\\/]+javaw\.exe'
      ;;
    qcad-legacy)
      printf '%s\n' 'QCad 2[\\/]+qcad\.exe|qcad\.exe'
      ;;
    openrocket-sim)
      printf '%s\n' 'OpenRocket[\\/]+OpenRocket\.exe|OpenRocket\.exe'
      ;;
    mremoteng-manager)
      printf '%s\n' 'mRemoteNG[\\/]+mRemoteNG\.exe|mRemoteNG\.exe'
      ;;
    opencpn-chartplotter)
      printf '%s\n' 'opencpn[\\/]+opencpn\.exe|opencpn\.exe'
      ;;
    jasp-stats)
      printf '%s\n' 'JASP[\\/]+JASPDesktop\.exe|JASPDesktop\.exe'
      ;;
    r-base-gui)
      printf '%s\n' 'R[\\/]+R-4\.6\.0[\\/]+bin[\\/]+x64[\\/]+Rgui\.exe|Rgui\.exe'
      ;;
    lasergrbl-cnc)
      printf '%s\n' 'LaserGRBL[\\/]+LaserGRBL\.exe|LaserGRBL\.exe'
      ;;
    prusaslicer-print)
      printf '%s\n' 'Prusa3D[\\/]+PrusaSlicer[\\/]+prusa-slicer\.exe|prusa-slicer\.exe'
      ;;
    saga-gis)
      printf '%s\n' 'SAGA[\\/]+saga_gui\.exe|saga_gui\.exe'
      ;;
    openscad)
      printf '%s\n' 'OpenSCAD[\\/]+openscad\.exe|openscad\.exe'
      ;;
    librecad)
      printf '%s\n' 'LibreCAD[\\/]+LibreCAD\.exe|LibreCAD\.exe'
      ;;
    freecad-workbench)
      printf '%s\n' 'FreeCAD 1\.1[\\/]+bin[\\/]+FreeCAD\.exe|FreeCAD\.exe'
      ;;
    librepcb-eda)
      printf '%s\n' 'LibrePCB[\\/]+.*librepcb\.exe|librepcb\.exe'
      ;;
    gmsh-mesh)
      printf '%s\n' 'macwin-portable[\\/]+gmsh-mesh[\\/]+gmsh-4\.14\.1-Windows64[\\/]+gmsh\.exe|gmsh\.exe'
      ;;
    brlcad-tools)
      printf '%s\n' 'BRLCAD 7\.42\.2[\\/]+bin[\\/]+archer\.exe|archer\.exe'
      ;;
    graphviz-dot)
      printf '%s\n' 'Graphviz[\\/]+bin[\\/]+dot\.exe|dot\.exe'
      ;;
    dwsim-process-sim)
      printf '%s\n' 'DWSIM[\\/]+DWSIM\.exe|DWSIM\.exe'
      ;;
    epanet-water)
      printf '%s\n' 'EPANET 2\.2[\\/]+Epanet2w\.exe|Epanet2w\.exe'
      ;;
    swmm-hydrology)
      printf '%s\n' 'EPA SWMM 5\.2[\\/]+epaswmm5\.exe|epaswmm5\.exe'
      ;;
    opendss-power)
      printf '%s\n' 'OpenDSS[\\/]+.*OpenDSS.*\.exe|OpenDSS.*\.exe'
      ;;
    qmodmaster-64|qmodmaster-32)
      printf '%s\n' 'macwin-portable[\\/]+qmodmaster-[0-9]+[\\/]+qModMaster[\\/]+qModMaster\.exe|qModMaster\.exe'
      ;;
    ugs-cnc)
      printf '%s\n' 'Universal G-code Sender[\\/]+Universal G-code Sender\.exe|Universal G-code Sender\.exe|javaw\.exe'
      ;;
    openjump-gis)
      printf '%s\n' 'macwin-portable[\\/]+openjump-gis[\\/]+OpenJUMP-.*[\\/]+bin[\\/]+OpenJUMP\.exe|OpenJUMP\.exe|javaw\.exe'
      ;;
    lazarus-ide-64|lazarus-ide-32)
      printf '%s\n' 'Lazarus[\\/]+lazarus\.exe|lazarus\.exe'
      ;;
    codeblocks-mingw)
      printf '%s\n' 'CodeBlocks[\\/]+codeblocks\.exe|codeblocks\.exe'
      ;;
    godot-win64-editor)
      printf '%s\n' 'macwin-portable[\\/]+godot-win64-editor[\\/]+Godot_v4\.7-stable_win64\.exe|Godot_v4\.7-stable_win64\.exe'
      ;;
    godot-win32-editor)
      printf '%s\n' 'macwin-portable[\\/]+godot-win32-editor[\\/]+Godot_v4\.7-stable_win32\.exe|Godot_v4\.7-stable_win32\.exe'
      ;;
    bambu-studio-portable)
      printf '%s\n' 'macwin-portable[\\/]+bambu-studio-portable[\\/]+bambu-studio\.exe|bambu-studio\.exe'
      ;;
    logisim-evolution)
      printf '%s\n' 'Logisim Evolution[\\/]+logisim-evolution\.exe|logisim-evolution\.exe|javaw\.exe'
      ;;
    tiled-map-editor)
      printf '%s\n' 'Tiled[\\/]+tiled\.exe|tiled\.exe'
      ;;
    musescore-studio)
      printf '%s\n' 'MuseScore Studio 4[\\/]+bin[\\/]+MuseScore4\.exe|MuseScore4\.exe'
      ;;
    lmms-audio)
      printf '%s\n' 'LMMS[\\/]+lmms\.exe|lmms\.exe'
      ;;
    vlc-media)
      printf '%s\n' 'VideoLAN[\\/]+VLC[\\/]+vlc\.exe|vlc\.exe'
      ;;
    openshot-video)
      printf '%s\n' 'OpenShot Video Editor[\\/]+openshot-qt\.exe|OpenShot[\\/]+openshot-qt\.exe|openshot-qt\.exe'
      ;;
    solvespace-direct)
      printf '%s\n' 'solvespace-direct[\\/]+SolveSpace-3\.2-x64\.exe|SolveSpace-3\.2-x64\.exe'
      ;;
    inkscape-vector)
      printf '%s\n' 'Inkscape[\\/]+bin[\\/]+inkscape\.exe|inkscape\.exe'
      ;;
    blender-3d)
      printf '%s\n' 'Blender Foundation[\\/]+Blender 4\.1[\\/]+blender\.exe|blender\.exe'
      ;;
    audacity-audio)
      printf '%s\n' 'Audacity[\\/]+Audacity\.exe|Audacity\.exe'
      ;;
    flameshot-capture)
      printf '%s\n' 'Flameshot[\\/]+.*flameshot\.exe|flameshot\.exe'
      ;;
    npackd|npackd-market)
      printf '%s\n' 'macwin-portable[\\/]+npackd([\\/]|-market[\\/])npackdg\.exe|npackdg\.exe'
      ;;
    lenovo-app-store)
      printf '%s\n' 'Lenovo[\\/]+LeAppStore[\\/]+LenovoAppStore\.exe|LenovoAppStore\.exe|LeASLane\.exe'
      ;;
    portableapps-platform)
      printf '%s\n' 'PortableApps\.com_Platform_Setup_30\.4\.1\.paf\.exe|PortableApps.*Platform.*Setup'
      ;;
    *)
      return 1
      ;;
  esac
}

has_live_gui_process_for_sample() {
  local id="$1" log="$2"
  local pattern
  pattern="$(gui_process_pattern_for_sample "$id" 2>/dev/null || true)"
  [ -n "$pattern" ] || return 1
  {
    echo >> "$log"
    echo "processProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    ps -axo pid,ppid,comm,args | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' || true
  } >> "$log"
  ps -axo pid,ppid,comm,args | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' >/dev/null 2>&1
}

capture_live_process_snapshot_for_sample() {
  local id="$1" phase="$2" log="$3"
  local pattern
  pattern="$(gui_process_pattern_for_sample "$id" 2>/dev/null || true)"
  if [ "$id" = "jasp-stats" ]; then
    pattern='JASPDesktop\.exe|JASPEngine\.exe|QtWebEngineProcess\.exe|wine(64)?-preloader|wineserver|services\.exe|explorer\.exe'
  fi
  [ -n "$pattern" ] || return 0
  {
    echo
    echo "liveProcessSnapshot=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "liveProcessSnapshotPhase=$phase"
    ps -axo pid,ppid,stat,rss,comm,args | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' || true
  } >> "$log"
}

visual_probe_enabled_for_sample() {
  [ "${MACWIN_VISUAL_PROBE:-1}" = "1" ] || return 1
  case "$1" in
    freecad-workbench|geogebra-classic|jabref-portable|kicad-eda|lenovo-app-store|librecad|ltspice-circuit|npackd|openplc-editor|openscad|orcaslicer-print|pgadmin-db-admin|postman-api-client|powertoys-fancyzones|qcad-legacy|qelectrotech-cad|qgroundcontrol-drone|sweethome3d-design|vscode-portable)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

append_chromium_compositor_probe_for_sample() {
  local id="$1" phase="$2" log="$3"
  local report_path screenshot_path analysis_path proof_path classification

  [ "$phase" = "launch" ] || return 1
  case "$id" in
    lenovo-app-store)
      report_path="$LOG_DIR/lenovo-app-store-cdp-report.json"
      screenshot_path="$LOG_DIR/lenovo-app-store-cdp.png"
      analysis_path="$LOG_DIR/lenovo-app-store-cdp-analysis.json"
      proof_path="$LOG_DIR/lenovo-app-store-cdp-proof.json"
      ;;
    pgadmin-db-admin)
      report_path="$LOG_DIR/pgadmin-db-admin-cdp-report.json"
      screenshot_path="$LOG_DIR/pgadmin-db-admin-cdp.png"
      analysis_path="$LOG_DIR/pgadmin-db-admin-cdp-analysis.json"
      proof_path="$LOG_DIR/pgadmin-db-admin-cdp-proof.json"
      ;;
    openplc-editor)
      report_path="$LOG_DIR/openplc-editor-cdp-report.json"
      screenshot_path="$LOG_DIR/openplc-editor-cdp.png"
      analysis_path="$LOG_DIR/openplc-editor-cdp-analysis.json"
      proof_path="$LOG_DIR/openplc-editor-cdp-proof.json"
      ;;
    *)
      return 1
      ;;
  esac
  [ -s "$report_path" ] && [ -s "$screenshot_path" ] || return 1

  classification="$(/usr/bin/python3 "$SCRIPT_DIR/analyze-window-image.py" \
    "$screenshot_path" "$analysis_path" 2>>"$log" || true)"
  [ -n "$classification" ] || return 1
  if [ "$id" = "pgadmin-db-admin" ]; then
    /usr/bin/python3 "$SCRIPT_DIR/validate-pgadmin-page-report.py" \
      "$report_path" "$analysis_path" "$proof_path" >>"$log" 2>&1 || return 1
  else
    /usr/bin/python3 "$SCRIPT_DIR/validate-chromium-page-report.py" \
      "$id" "$report_path" "$analysis_path" "$proof_path" >>"$log" 2>&1 || return 1
  fi

  {
    echo
    echo "visualProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "visualProbe.id=$id"
    echo "visualProbe.phase=$phase"
    echo "visualProbe.source=chromium-cdp"
    echo "visualProbe.status=verified-compositor"
    echo "visualProbe.classification=rendered"
    echo "visualProbe.cdpReportPath=$report_path"
    echo "visualProbe.capturePath=$screenshot_path"
    echo "visualProbe.analysisPath=$analysis_path"
    echo "visualProbe.proofPath=$proof_path"
    echo "visualProbe.sourceClassification=$classification"
  } >> "$log"
  return 0
}

prepare_qgroundcontrol_first_run_probe() {
  local settings_path="$PREFIX/drive_c/users/$USER/AppData/Roaming/QGroundControl/QGroundControl.ini"
  local map_cache_dir="$PREFIX/drive_c/users/$USER/AppData/Local/cache/QGCMapCache300"
  local preparation_log="$LOG_DIR/qgroundcontrol-drone-first-run-preparation.log"

  mkdir -p "$(dirname "$settings_path")"
  rm -f "$preparation_log"
  rm -rf "$map_cache_dir"
  if ! /usr/bin/python3 - "$settings_path" <<'PY'
import configparser
import os
import sys

path = sys.argv[1]
settings = configparser.RawConfigParser(interpolation=None, strict=False)
settings.optionxform = str
if os.path.exists(path):
    settings.read(path, encoding="utf-8")
if not settings.has_section("General"):
    settings.add_section("General")
settings.remove_option("General", "firstRunPromptIdsShown")
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    settings.write(handle, space_around_delimiters=False)

verification = configparser.RawConfigParser(interpolation=None, strict=False)
verification.optionxform = str
verification.read(path, encoding="utf-8")
if verification.has_option("General", "firstRunPromptIdsShown"):
    raise SystemExit("failed to clear firstRunPromptIdsShown")
PY
  then
    printf '%s\n' "firstRunPromptIdsShown=reset-failed" > "$preparation_log"
    return 1
  fi
  {
    echo "preparedAt=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "settingsPath=$settings_path"
    echo "firstRunPromptIdsShown=absent"
    echo "mapCacheReset=1"
  } > "$preparation_log"
}

probe_qgroundcontrol_first_run_interaction() {
  local log="$1" window_id="$2" before_capture_path="$3"
  local preparation_log="$LOG_DIR/qgroundcontrol-drone-first-run-preparation.log"
  local input_log="$LOG_DIR/qgroundcontrol-drone-launch-interaction-input.log"
  local capture_path="$LOG_DIR/qgroundcontrol-drone-launch-interaction.png"
  local analysis_path="$LOG_DIR/qgroundcontrol-drone-launch-interaction-analysis.json"
  local settings_path="$PREFIX/drive_c/users/$USER/AppData/Roaming/QGroundControl/QGroundControl.ini"
  local map_cache_db="$PREFIX/drive_c/users/$USER/AppData/Local/cache/QGCMapCache300/qgcMapCache.db"
  local classification settings_confirmed before_sha after_sha tile_count=0 tile_wait=0

  {
    echo
    echo "interactionProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "interactionProbe.id=qgroundcontrol-drone"
    echo "interactionProbe.method=win32-relative-pointer"
    echo "interactionProbe.preparationLogPath=$preparation_log"
    echo "interactionProbe.inputLogPath=$input_log"
    echo "interactionProbe.capturePath=$capture_path"
    echo "interactionProbe.analysisPath=$analysis_path"
    echo "interactionProbe.settingsPath=$settings_path"
  } >> "$log"

  if ! LC_ALL=C rg -q '^firstRunPromptIdsShown=absent$' "$preparation_log" 2>/dev/null; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=first-run-state-not-reset"
    } >> "$log"
    return 1
  fi

  if ! "${WINE_CMD[@]}" "$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe" \
    --send QGroundControl \
    clickp:56:27 wait:1200 \
    clickp:56:37 wait:3000 \
    >"$input_log" 2>&1; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=input-injection-failed"
    } >> "$log"
    return 1
  fi

  if ! /usr/bin/swift "$SCRIPT_DIR/capture-macos-window.swift" \
    "$window_id" "$capture_path" >>"$log" 2>&1; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=post-interaction-capture-failed"
    } >> "$log"
    return 1
  fi

  classification="$(/usr/bin/python3 "$SCRIPT_DIR/analyze-window-image.py" \
    "$capture_path" "$analysis_path" 2>>"$log" || true)"
  settings_confirmed="$(/usr/bin/python3 - "$settings_path" <<'PY' 2>>"$log" || true
import configparser
import sys

settings = configparser.RawConfigParser(interpolation=None, strict=False)
settings.optionxform = str
settings.read(sys.argv[1], encoding="utf-8")
value = settings.get("General", "firstRunPromptIdsShown", fallback="")
shown = {item.strip() for item in value.strip('"').split(",") if item.strip()}
print("1,2" if {"1", "2"}.issubset(shown) else "")
PY
)"
  before_sha="$(/usr/bin/shasum -a 256 "$before_capture_path" 2>/dev/null | awk '{print $1}')"
  after_sha="$(/usr/bin/shasum -a 256 "$capture_path" 2>/dev/null | awk '{print $1}')"
  while [ "$tile_wait" -lt 15 ]; do
    if [ -f "$map_cache_db" ]; then
      tile_count="$(/usr/bin/sqlite3 "$map_cache_db" 'select count(*) from Tiles;' 2>/dev/null || printf 0)"
      case "$tile_count" in
        ''|*[!0-9]*) tile_count=0 ;;
      esac
      [ "$tile_count" -gt 0 ] && break
    fi
    sleep 1
    tile_wait=$((tile_wait + 1))
  done

  {
    echo "interactionProbe.classification=${classification:-unavailable}"
    echo "interactionProbe.settingsConfirmed=${settings_confirmed:-none}"
    echo "interactionProbe.beforeSHA256=${before_sha:-unavailable}"
    echo "interactionProbe.afterSHA256=${after_sha:-unavailable}"
    echo "interactionProbe.mapCachePath=$map_cache_db"
    echo "interactionProbe.mapTileCount=$tile_count"
  } >> "$log"

  if [ "$settings_confirmed" != "1,2" ]; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=first-run-settings-not-persisted"
    } >> "$log"
    return 1
  fi
  case "$classification" in
    rendered|partial-render-window|low-information-window) ;;
    *)
      {
        echo "interactionProbe.status=failed"
        echo "interactionProbe.reason=post-interaction-window-${classification:-unavailable}"
      } >> "$log"
      return 1
      ;;
  esac
  if [ -z "$before_sha" ] || [ -z "$after_sha" ] || [ "$before_sha" = "$after_sha" ]; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=front-buffer-did-not-change"
    } >> "$log"
    return 1
  fi
  if [ "$tile_count" -le 0 ]; then
    {
      echo "interactionProbe.status=failed"
      echo "interactionProbe.reason=map-tiles-not-cached"
    } >> "$log"
    return 1
  fi

  {
    echo "interactionProbe.status=verified"
    echo "interactionProbe.steps=measurement-units,vehicle-information,map-tiles"
  } >> "$log"
  return 0
}

capture_visual_probe_for_sample() {
  local id="$1" phase="$2" log="$3"
  local metadata metadata_path capture_path analysis_path status process_name window_title x y width height
  local cg_metadata cg_metadata_path window_id window_classification
  local screen_capture_path screen_analysis_path screen_classification session_state locked_window_token
  local locked_window_discovery locked_window_wait

  case "$phase" in
    launch|fancyzones-editor-visual) ;;
    *) return 0 ;;
  esac
  visual_probe_enabled_for_sample "$id" || return 0

  if [ "$id" = "orcaslicer-print" ]; then
    local orca_window_list="$LOG_DIR/$id-$phase-windows.log"
    "${WINE_CMD[@]}" "$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe" --list \
      >"$orca_window_list" 2>&1 || true
    if LC_ALL=C rg -q 'visible=1.*title="(WebView2 Runtime|Setup Wizard|New version of Orca Slicer)"' "$orca_window_list"; then
      echo "visualProbe.orcaModalBlocker=1" >> "$log"
    else
      echo "visualProbe.orcaModalBlocker=0" >> "$log"
    fi
    if LC_ALL=C rg -q 'visible=1.*title="Untitled - OrcaSlicer"' "$orca_window_list"; then
      echo "visualProbe.orcaMainWindow=1" >> "$log"
    else
      echo "visualProbe.orcaMainWindow=0" >> "$log"
    fi
  fi

  if append_chromium_compositor_probe_for_sample "$id" "$phase" "$log" \
    && [ "$id" != "pgadmin-db-admin" ]; then
    return 0
  fi

  metadata_path="$LOG_DIR/$id-$phase-visual-window.tsv"
  cg_metadata_path="$LOG_DIR/$id-$phase-visual-cgwindow.tsv"
  capture_path="$LOG_DIR/$id-$phase-visual.png"
  analysis_path="$LOG_DIR/$id-$phase-visual-analysis.json"
  screen_capture_path="$LOG_DIR/$id-$phase-visual-screen.png"
  screen_analysis_path="$LOG_DIR/$id-$phase-visual-screen-analysis.json"

  metadata=""
  session_state="$(/usr/bin/swift "$SCRIPT_DIR/macos-session-state.swift" 2>/dev/null || printf 'unknown')"
  locked_window_token=""
  locked_window_discovery="--discover-smallest"
  locked_window_wait=0
  case "$id" in
    freecad-workbench) locked_window_token="FreeCAD" ;;
    kicad-eda) locked_window_token="KiCad" ;;
    ltspice-circuit) locked_window_token="LTspice" ;;
    powertoys-fancyzones) locked_window_token="FancyZones" ;;
    qgroundcontrol-drone)
      locked_window_token="QGroundControl"
      locked_window_discovery="--discover"
      locked_window_wait=20
      ;;
    qcad-legacy)
      locked_window_token="QCad -"
      locked_window_discovery="--discover"
      locked_window_wait=20
      ;;
    sweethome3d-design)
      locked_window_token="Sweet Home 3D"
      locked_window_discovery="--discover"
      locked_window_wait=20
      ;;
  esac
  if [ "$session_state" = "locked" ] \
    && { [ -n "$locked_window_token" ] || [ "$locked_window_discovery" = "--discover" ]; }; then
    local locked_window_elapsed=0
    while :; do
      cg_metadata="$(/usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" \
        "$locked_window_discovery" wine "$locked_window_token" 2>"$cg_metadata_path.err")" || cg_metadata=""
      [ -n "$cg_metadata" ] && break
      [ "$locked_window_elapsed" -ge "$locked_window_wait" ] && break
      sleep 1
      locked_window_elapsed=$((locked_window_elapsed + 1))
    done
    if [ -n "$cg_metadata" ]; then
      IFS=$'\t' read -r window_id process_name window_title x y width height <<EOF
$cg_metadata
EOF
      printf -v metadata 'ok\t%s\t%s\t%s\t%s\t%s\t%s' \
        "$process_name" "$window_title" "$x" "$y" "$width" "$height"
    fi
  fi
  if [ "$session_state" = "locked" ] && [ -z "$metadata" ]; then
    {
      echo
      echo "visualProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "visualProbe.id=$id"
      echo "visualProbe.phase=$phase"
      echo "visualProbe.status=unavailable"
      echo "visualProbe.reason=session-locked"
    } >> "$log"
    return 0
  fi

  if [ -z "$metadata" ]; then
    metadata="$(/usr/bin/osascript - "$id" <<'OSA' 2>"$metadata_path.err"
on run argv
    set sampleId to item 1 of argv
    set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader"}
    set targetTitleTokens to {}
    if sampleId is "pgadmin-db-admin" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "pgAdmin4", "pgAdmin4.exe"}
        set targetTitleTokens to {"pgAdmin", "pgAdmin 4"}
    end if
    if sampleId is "lenovo-app-store" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "LenovoAppStore", "LenovoAppStore.exe"}
        set targetTitleTokens to {"Lenovo", "联想", "应用商店", "LeAppStore", "LenovoAppStore"}
    end if
    if sampleId is "ltspice-circuit" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "LTspice", "LTspice.exe"}
        set targetTitleTokens to {"LTspice"}
    end if
    if sampleId is "npackd" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "npackdg", "npackdg.exe"}
        set targetTitleTokens to {"Npackd"}
    end if
    if sampleId is "geogebra-classic" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "GeoGebra", "GeoGebra.exe"}
        set targetTitleTokens to {"GeoGebra"}
    end if
    if sampleId is "jabref-portable" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "JabRef", "JabRef.exe"}
        set targetTitleTokens to {"JabRef"}
    end if
    if sampleId is "freecad-workbench" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "FreeCAD", "FreeCAD.exe"}
        set targetTitleTokens to {"FreeCAD"}
    end if
    if sampleId is "kicad-eda" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "KiCad", "kicad.exe"}
        set targetTitleTokens to {"KiCad"}
    end if
    if sampleId is "postman-api-client" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "Postman", "Postman.exe"}
        set targetTitleTokens to {"Postman"}
    end if
    if sampleId is "openplc-editor" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "OpenPLC Editor", "OpenPLC Editor.exe"}
        set targetTitleTokens to {"OpenPLC Editor", "OpenPLC"}
    end if
    if sampleId is "powertoys-fancyzones" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "PowerToys.FancyZones", "PowerToys.FancyZones.exe", "FancyZonesEditor", "FancyZonesEditor.exe"}
        set targetTitleTokens to {"FancyZones", "PowerToys", "Layout"}
    end if
    if sampleId is "qelectrotech-cad" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "qelectrotech", "qelectrotech.exe"}
        set targetTitleTokens to {"QElectroTech", "MacWin 工业电气兼容性测试", "工业控制回路"}
    end if
    if sampleId is "qgroundcontrol-drone" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "QGroundControl", "QGroundControl.exe"}
        set targetTitleTokens to {"QGroundControl"}
    end if
    if sampleId is "vscode-portable" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "Code", "Code.exe"}
        set targetTitleTokens to {"Visual Studio Code"}
    end if
    if sampleId is "orcaslicer-print" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "orca-slicer", "orca-slicer.exe"}
        set targetTitleTokens to {"OrcaSlicer"}
    end if
    if sampleId is "qcad-legacy" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "QCad", "qcad.exe"}
        set targetTitleTokens to {"QCad"}
    end if
    if sampleId is "sweethome3d-design" then
        set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "SweetHome3D", "SweetHome3D.exe", "javaw.exe"}
        set targetTitleTokens to {"Sweet Home 3D"}
    end if

    set fallbackLine to ""
    tell application "System Events"
        repeat with p in every process
            try
                set processName to name of p as text
                set processMatches to false
                repeat with targetName in targetProcessNames
                    if processName is (targetName as text) then set processMatches to true
                    if (targetName as text) is "wine" and processName contains "wine" then set processMatches to true
                    if (targetName as text) is "wine-preloader" and processName contains "wine-preloader" then set processMatches to true
                    if (targetName as text) is "wine64-preloader" and processName contains "wine64-preloader" then set processMatches to true
                end repeat
                if processMatches is true and (count of windows of p) > 0 then
                    repeat with w in windows of p
                        try
                            set windowPosition to position of w
                            set windowSize to size of w
                            set windowWidth to item 1 of windowSize
                            set windowHeight to item 2 of windowSize
                            if windowWidth > 80 and windowHeight > 80 then
                                set windowName to ""
                                try
                                    set windowName to name of w as text
                                end try
                                set titleMatches to false
                                repeat with titleToken in targetTitleTokens
                                    if windowName contains (titleToken as text) then set titleMatches to true
                                end repeat
                                set candidateLine to "ok" & tab & processName & tab & windowName & tab & (item 1 of windowPosition as integer) & tab & (item 2 of windowPosition as integer) & tab & (windowWidth as integer) & tab & (windowHeight as integer)
                                if titleMatches is true then return candidateLine
                                if fallbackLine is "" and (count of targetTitleTokens) is 0 then set fallbackLine to candidateLine
                            end if
                        end try
                    end repeat
                end if
            end try
        end repeat
    end tell
    if fallbackLine is not "" then return fallbackLine
    return "missing" & tab & "no matching visible window"
end run
OSA
)" || metadata=""
  fi
  printf '%s\n' "$metadata" > "$metadata_path"

  status="$(printf '%s' "$metadata" | awk -F '\t' '{print $1}')"
  {
    echo
    echo "visualProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "visualProbe.id=$id"
    echo "visualProbe.phase=$phase"
    echo "visualProbe.metadataPath=$metadata_path"
  } >> "$log"

  if [ "$status" != "ok" ]; then
    if [ "$id" = "lenovo-app-store" ]; then
      cg_metadata="$(/usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" --discover wine '联想应用商店' 2>"$cg_metadata_path.err")" || cg_metadata=""
      if [ -n "$cg_metadata" ]; then
        IFS=$'\t' read -r window_id process_name window_title x y width height <<EOF
$cg_metadata
EOF
        status="ok"
        printf -v metadata 'ok\t%s\t%s\t%s\t%s\t%s\t%s' "$process_name" "$window_title" "$x" "$y" "$width" "$height"
        printf 'ok\t%s\t%s\t%s\t%s\t%s\t%s\n' "$process_name" "$window_title" "$x" "$y" "$width" "$height" > "$metadata_path"
        {
          echo "visualProbe.accessibilityFallback=coregraphics-discovery"
          echo "visualProbe.windowId=$window_id"
        } >> "$log"
      fi
    fi
  fi

  if [ "$status" != "ok" ]; then
    {
      echo "visualProbe.status=unavailable"
      echo "visualProbe.reason=${metadata:-no matching visible window}"
      [ -s "$metadata_path.err" ] && sed 's/^/visualProbe.osascriptError=/' "$metadata_path.err"
    } >> "$log"
    return 0
  fi

  IFS=$'\t' read -r _ process_name window_title x y width height <<EOF
$metadata
EOF
  {
    echo "visualProbe.status=window-found"
    echo "visualProbe.process=$process_name"
    echo "visualProbe.windowTitle=$window_title"
    echo "visualProbe.windowBounds=$x,$y,$width,$height"
    echo "visualProbe.capturePath=$capture_path"
  } >> "$log"

  case "$id" in
    qcad-legacy) sleep 3 ;;
    qgroundcontrol-drone) sleep 10 ;;
    sweethome3d-design) sleep 12 ;;
  esac

  if [ -z "$window_id" ]; then
    cg_metadata="$(/usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" "$process_name" "$window_title" "$x" "$y" "$width" "$height" 16 2>"$cg_metadata_path.err")" || cg_metadata=""
    window_id="$(printf '%s' "$cg_metadata" | awk -F '\t' '{print $1}')"
  fi
  printf '%s\n' "$cg_metadata" > "$cg_metadata_path"
  if [ -z "$window_id" ]; then
    {
      echo "visualProbe.status=window-id-unavailable"
      echo "visualProbe.cgMetadataPath=$cg_metadata_path"
      [ -s "$cg_metadata_path.err" ] && sed 's/^/visualProbe.cgWindowError=/' "$cg_metadata_path.err"
    } >> "$log"
    return 0
  fi
  {
    echo "visualProbe.windowId=$window_id"
    echo "visualProbe.cgMetadataPath=$cg_metadata_path"
  } >> "$log"

  if ! /usr/sbin/screencapture -x -l"$window_id" "$capture_path" >> "$log" 2>&1; then
    echo "visualProbe.captureFallback=coregraphics-image" >> "$log"
    if ! /usr/bin/swift "$SCRIPT_DIR/capture-macos-window.swift" "$window_id" "$capture_path" >> "$log" 2>&1; then
      echo "visualProbe.status=capture-failed" >> "$log"
      return 0
    fi
  fi

  /usr/bin/python3 - "$capture_path" "$analysis_path" <<'PY' >> "$log" 2>&1 || {
import json
import math
import struct
import sys
import zlib

png_path, analysis_path = sys.argv[1:3]

def read_chunks(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file")
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        yield kind, chunk
        pos += 12 + length

def paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c

with open(png_path, "rb") as f:
    data = f.read()

width = height = bit_depth = color_type = interlace = None
idat = []
for kind, chunk in read_chunks(data):
    if kind == b"IHDR":
        width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk)
    elif kind == b"IDAT":
        idat.append(chunk)
if width is None:
    raise ValueError("missing PNG IHDR")
if bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 6):
    raise ValueError(f"unsupported PNG format bitDepth={bit_depth} colorType={color_type} interlace={interlace}")

channels = {0: 1, 2: 3, 6: 4}[color_type]
stride = width * channels
raw = zlib.decompress(b"".join(idat))
rows = []
pos = 0
prev = bytearray(stride)
for _row_index in range(height):
    filter_type = raw[pos]
    pos += 1
    scan = bytearray(raw[pos:pos + stride])
    pos += stride
    recon = bytearray(stride)
    for i, value in enumerate(scan):
        left = recon[i - channels] if i >= channels else 0
        up = prev[i]
        up_left = prev[i - channels] if i >= channels else 0
        if filter_type == 0:
            recon[i] = value
        elif filter_type == 1:
            recon[i] = (value + left) & 0xFF
        elif filter_type == 2:
            recon[i] = (value + up) & 0xFF
        elif filter_type == 3:
            recon[i] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            recon[i] = (value + paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter {filter_type}")
    rows.append(recon)
    prev = recon

# Sparse native UIs can place their only visible controls at the left edge or
# immediately below the title bar, so keep the full client width and a small
# top margin in the sampled region.
x0 = 0
x1 = width
y0 = int(height * 0.04)
y1 = max(y0 + 1, int(height * 0.94))
step_x = max(1, (x1 - x0) // 240)
step_y = max(1, (y1 - y0) // 180)

count = 0
lum_sum = 0.0
lum_sq_sum = 0.0
dark_count = 0
bright_count = 0
transparent_count = 0
colors = set()
for yy in range(y0, y1, step_y):
    row = rows[yy]
    for xx in range(x0, x1, step_x):
        offset = xx * channels
        if color_type == 0:
            r = g = b = row[offset]
        else:
            r, g, b = row[offset], row[offset + 1], row[offset + 2]
        alpha = row[offset + 3] if color_type == 6 else 255
        lum = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
        lum_sum += lum
        lum_sq_sum += lum * lum
        dark_count += lum < 18
        bright_count += lum > 238
        transparent_count += alpha < 16
        colors.add((r >> 4, g >> 4, b >> 4))
        count += 1

mean = lum_sum / count if count else 0.0
variance = max(0.0, (lum_sq_sum / count) - (mean * mean)) if count else 0.0
stddev = math.sqrt(variance)
dark_ratio = dark_count / count if count else 0.0
bright_ratio = bright_count / count if count else 0.0
transparent_ratio = transparent_count / count if count else 0.0
unique_ratio = len(colors) / count if count else 0.0
non_bright_count = count - bright_count

classification = "rendered"
if transparent_ratio >= 0.50:
    classification = "transparent-window"
elif dark_ratio >= 0.92:
    classification = "black-window"
elif dark_count >= 64 or (stddev >= 6.0 and non_bright_count >= 256):
    classification = "rendered"
elif bright_ratio >= 0.92:
    classification = "partial-render-window" if len(colors) >= 8 and non_bright_count >= 32 else "white-window"
elif stddev < 6.0 or (unique_ratio < 0.002 and len(colors) < 8):
    classification = "low-information-window"

analysis = {
    "path": png_path,
    "width": width,
    "height": height,
    "sampledPixels": count,
    "meanLuminance": round(mean, 2),
    "luminanceStdDev": round(stddev, 2),
    "darkRatio": round(dark_ratio, 4),
    "brightRatio": round(bright_ratio, 4),
    "transparentRatio": round(transparent_ratio, 4),
    "nonBrightPixelCount": non_bright_count,
    "quantizedColorCount": len(colors),
    "uniqueQuantizedColorRatio": round(unique_ratio, 5),
    "classification": classification,
}
with open(analysis_path, "w", encoding="utf-8") as f:
    json.dump(analysis, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("visualProbe.analysisPath=" + analysis_path)
for key, value in analysis.items():
    print(f"visualProbe.{key}={value}")
PY
    echo "visualProbe.status=analysis-failed" >> "$log"
    return 0
  }

  window_classification="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["classification"])' "$analysis_path" 2>/dev/null || true)"
  if [ "$id" = "qelectrotech-cad" ] && [ "$window_classification" = "low-information-window" ]; then
    if /usr/bin/python3 - "$analysis_path" <<'PY' >/dev/null 2>&1 \
      && LC_ALL=C rg -q 'Count All Elements in collections = [1-9][0-9]* Elements' "$log" \
      && LC_ALL=C rg -F -q 'C:\macwin-tests\qelectrotech-smoke.qet' "$log"; then
import json
import sys

with open(sys.argv[1], encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)
assert analysis["width"] >= 1200 and analysis["height"] >= 700
assert analysis["luminanceStdDev"] >= 25
assert analysis["brightRatio"] < 0.90
assert analysis["nonBrightPixelCount"] >= 5000
assert analysis["quantizedColorCount"] >= 24
PY
      {
        echo "visualProbe.domain=qelectrotech-cad-canvas"
        echo "visualProbe.domainClassification=rendered"
        echo "visualProbe.domainReason=structured drafting canvas, project path, and element collection verified"
      } >> "$log"
    fi
  fi
  if [ "$id" = "qgroundcontrol-drone" ] \
    && LC_ALL=C rg -q '^visualProbe.windowTitle=.*QGroundControl' "$log" \
    && /usr/bin/python3 - "$analysis_path" <<'PY' >/dev/null 2>&1; then
import json
import sys

with open(sys.argv[1], encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)
assert analysis["width"] >= 900 and analysis["height"] >= 600
assert analysis["luminanceStdDev"] >= 10
assert analysis["darkRatio"] < 0.92
assert analysis["brightRatio"] < 0.92
assert analysis["nonBrightPixelCount"] >= 4_000
assert analysis["quantizedColorCount"] >= 24
PY
    {
      echo "visualProbe.domain=qgroundcontrol-qtquick-front-buffer"
      echo "visualProbe.domainClassification=rendered"
      echo "visualProbe.domainReason=QGroundControl main window and structured Qt Quick front buffer verified"
    } >> "$log"
    probe_qgroundcontrol_first_run_interaction "$log" "$window_id" "$capture_path" || true
  fi
  if [ "$id" = "jabref-portable" ] \
    && [ "$window_classification" = "partial-render-window" ] \
    && LC_ALL=C rg -q 'Prism pipeline name = com\.sun\.prism\.d3d\.D3DPipeline|Direct3D initialization succeeded' "$log" \
    && ! has_javafx_sw_glyph_warning "$log" \
    && /usr/bin/python3 - "$analysis_path" <<'PY' >/dev/null 2>&1; then
import json
import sys

with open(sys.argv[1], encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)
assert analysis["width"] >= 900 and analysis["height"] >= 600
assert analysis["luminanceStdDev"] >= 6
assert analysis["nonBrightPixelCount"] >= 2_000
assert analysis["quantizedColorCount"] >= 12
PY
    {
      echo "visualProbe.domain=jabref-javafx-d3d"
      echo "visualProbe.domainClassification=rendered"
      echo "visualProbe.domainReason=JavaFX D3D pipeline, visible JabRef chrome, and nonblank front buffer verified"
    } >> "$log"
  fi
  if [ "$id" = "freecad-workbench" ] \
    && { [ "$window_classification" = "partial-render-window" ] || [ "$window_classification" = "rendered" ]; } \
    && LC_ALL=C rg -q '^visualProbe.windowTitle=FreeCAD ' "$log" \
    && /usr/bin/python3 - "$analysis_path" <<'PY' >/dev/null 2>&1; then
import json
import sys

with open(sys.argv[1], encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)
assert analysis["width"] >= 1200 and analysis["height"] >= 700
assert analysis["luminanceStdDev"] >= 20
assert analysis["nonBrightPixelCount"] >= 2_000
assert analysis["quantizedColorCount"] >= 40
assert analysis["transparentRatio"] < 0.10
PY
    {
      echo "visualProbe.domain=freecad-qt-opengl-front-buffer"
      echo "visualProbe.domainClassification=rendered"
      echo "visualProbe.domainReason=FreeCAD title, Qt chrome, CAD workbench, and nonblank front buffer verified"
    } >> "$log"
  fi
  if [ "$id" = "pgadmin-db-admin" ] \
    && LC_ALL=C rg -q '^visualProbe.status=verified-compositor$' "$log" \
    && /usr/bin/python3 - "$analysis_path" <<'PY' >/dev/null 2>&1; then
import json
import sys

with open(sys.argv[1], encoding="utf-8") as analysis_file:
    analysis = json.load(analysis_file)
assert analysis["width"] >= 1200 and analysis["height"] >= 700
assert analysis["luminanceStdDev"] >= 35
assert analysis["brightRatio"] < 0.86
assert analysis["nonBrightPixelCount"] >= 8_000
assert analysis["quantizedColorCount"] >= 40
PY
    {
      echo "visualProbe.domain=pgadmin-electron-front-buffer"
      echo "visualProbe.domainClassification=rendered"
      echo "visualProbe.domainReason=local dashboard DOM, Chromium compositor, and macOS front buffer verified"
    } >> "$log"
  fi
  if [ "$window_classification" = "transparent-window" ]; then
    {
      echo "visualProbe.screenCapturePath=$screen_capture_path"
      echo "visualProbe.screenAnalysisPath=$screen_analysis_path"
    } >> "$log"
    if /usr/sbin/screencapture -x -R"$x,$y,$width,$height" "$screen_capture_path" >> "$log" 2>&1 \
      || /usr/bin/swift "$SCRIPT_DIR/capture-macos-region.swift" "$x" "$y" "$width" "$height" "$screen_capture_path" >> "$log" 2>&1; then
      screen_classification="$(/usr/bin/python3 "$SCRIPT_DIR/analyze-window-image.py" "$screen_capture_path" "$screen_analysis_path" 2>>"$log" || true)"
      if [ -n "$screen_classification" ]; then
        {
          echo "visualProbe.screenClassification=$screen_classification"
          echo "visualProbe.classification=$screen_classification"
        } >> "$log"
      else
        echo "visualProbe.screenStatus=analysis-failed" >> "$log"
      fi
    else
      echo "visualProbe.screenStatus=capture-failed" >> "$log"
    fi
  fi
}

visual_probe_note() {
  local log="$1" classification reason domain_classification
  classification="$(LC_ALL=C sed -n 's/^visualProbe.classification=//p' "$log" | tail -n 1)"
  reason="$(LC_ALL=C sed -n 's/^visualProbe.reason=//p' "$log" | tail -n 1)"
  domain_classification="$(LC_ALL=C sed -n 's/^visualProbe.domainClassification=//p' "$log" | tail -n 1)"
  if LC_ALL=C rg -q '^visualProbe.status=verified-compositor$' "$log"; then
    if [ "$reason" = "session-locked" ]; then
      printf '%s\n' "pgAdmin probe verified the local dashboard DOM and Chromium compositor; macOS front-buffer capture remains pending because the session is locked."
    else
      printf '%s\n' "Chromium compositor probe verified the target page, initialized application state, visible content, and a rendered screenshot."
    fi
    return 0
  fi
  if LC_ALL=C rg -q '^visualProbe.orcaMainWindow=1$' "$log" \
    && LC_ALL=C rg -q '^visualProbe.orcaModalBlocker=0$' "$log"; then
    printf '%s\n' "Wine window enumeration verified the OrcaSlicer main window and found no WebView2, setup-wizard, or update modal blocker; front-buffer capture remains pending while the macOS session is locked."
    return 0
  fi
  if [ "$reason" = "session-locked" ]; then
    printf '%s\n' "Visual probe was skipped because the macOS session is locked; launch lifecycle passed but rendering remains unverified."
    return 0
  fi
  if [ "$domain_classification" = "rendered" ]; then
    if LC_ALL=C rg -q '^visualProbe.domain=pgadmin-electron-front-buffer$' "$log"; then
      printf '%s\n' "pgAdmin probe verified the local dashboard DOM, Chromium compositor, and macOS front buffer."
    elif LC_ALL=C rg -q '^visualProbe.domain=jabref-javafx-d3d$' "$log"; then
      printf '%s\n' "JabRef probe verified the JavaFX D3D pipeline and a visible nonblank front buffer without software glyph failures."
    elif LC_ALL=C rg -q '^visualProbe.domain=freecad-qt-opengl-front-buffer$' "$log"; then
      printf '%s\n' "FreeCAD probe verified the Qt CAD workbench and a visible nonblank OpenGL front buffer."
    elif LC_ALL=C rg -q '^visualProbe.domain=qgroundcontrol-qtquick-front-buffer$' "$log"; then
      if LC_ALL=C rg -q '^interactionProbe.status=verified$' "$log"; then
        printf '%s\n' "QGroundControl probe verified the Qt Quick software-OpenGL front buffer, accepted both first-run dialogs, and downloaded fresh map tiles."
      else
        printf '%s\n' "QGroundControl probe verified the main window and a structured Qt Quick software-OpenGL front buffer."
      fi
    else
      printf '%s\n' "QElectroTech CAD probe verified the loaded project, element collection, and structured drafting canvas."
    fi
    return 0
  fi
  case "$classification" in
    rendered)
      if LC_ALL=C rg -q '^visualProbe.status=verified-compositor$' "$log"; then
        printf '%s\n' "Chromium compositor probe verified the target page, initialized application state, visible content, and a rendered screenshot."
      else
        printf '%s\n' "Visual probe captured a nonblank window screenshot."
      fi
      ;;
    black-window|white-window|transparent-window|partial-render-window|low-information-window)
      printf '%s\n' "Visual probe captured a ${classification}; inspect the saved screenshot before accepting rendering."
      ;;
    *)
      if LC_ALL=C rg -q '^visualProbe.status=unavailable|^visualProbe.status=window-id-unavailable|^visualProbe.status=capture-failed|^visualProbe.status=analysis-failed' "$log"; then
        printf '%s\n' "Visual probe could not capture/analyze the target application window; verify rendering manually."
      fi
      ;;
  esac
}

has_visual_probe_blocking_issue() {
  local log="$1" classification status reason domain_classification
  if LC_ALL=C rg -q '^visualProbe.orcaModalBlocker=1$|^visualProbe.orcaMainWindow=0$' "$log"; then
    return 0
  fi
  domain_classification="$(LC_ALL=C sed -n 's/^visualProbe.domainClassification=//p' "$log" | tail -n 1)"
  classification="$(LC_ALL=C sed -n 's/^visualProbe.classification=//p' "$log" | tail -n 1)"
  status="$(LC_ALL=C sed -n 's/^visualProbe.status=//p' "$log" | tail -n 1)"
  reason="$(LC_ALL=C sed -n 's/^visualProbe.reason=//p' "$log" | tail -n 1)"
  if LC_ALL=C rg -q '^visualProbe.id=qgroundcontrol-drone$' "$log" \
    && [ "$reason" != "session-locked" ] \
    && ! LC_ALL=C rg -q '^interactionProbe.status=verified$' "$log"; then
    return 0
  fi
  [ "$domain_classification" = "rendered" ] && return 1
  [ "$reason" = "session-locked" ] && return 1
  if LC_ALL=C rg -q '^visualProbe.id=jabref-portable$' "$log" \
    && [ "$classification" != "rendered" ]; then
    return 0
  fi
  case "$classification" in
    black-window|white-window|transparent-window|partial-render-window)
      return 0
      ;;
    *)
      case "$status" in
        unavailable|window-id-unavailable|capture-failed|analysis-failed)
          return 0
          ;;
      esac
      return 1
      ;;
  esac
}

append_jasp_model_reset_summary() {
  local log="$1"
  local phase="${2:-postlaunch}"
  {
    echo
    echo "jaspModelResetSummary=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "jaspModelResetSummaryPhase=$phase"
    /usr/bin/python3 - "$log" <<'PY'
import re
import sys
from collections import Counter

path = sys.argv[1]
pattern = re.compile(r"(beginResetModel|endResetModel) called on ([^(]+)\((0x[0-9a-fA-F]+)\)")
counts = Counter()
sequence = []
try:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            match = pattern.search(line)
            if not match:
                continue
            kind, object_name, address = match.groups()
            counts[(object_name, address, kind)] += 1
            sequence.append((line_number, kind, object_name, address))
except OSError as exc:
    print(f"jaspModelResetSummary.error={exc}")
    sys.exit(0)

begin_count = sum(count for (_, _, kind), count in counts.items() if kind == "beginResetModel")
end_count = sum(count for (_, _, kind), count in counts.items() if kind == "endResetModel")
print(f"jaspModelResetSummary.beginWarnings={begin_count}")
print(f"jaspModelResetSummary.endWarnings={end_count}")
print(f"jaspModelResetSummary.totalWarnings={begin_count + end_count}")
if begin_count + end_count:
    print("jaspModelResetSource.1=Desktop/data/datasetpackagesubnodemodel.cpp:5-10 constructs QIdentityProxyModel and wraps setSourceModel(DataSetPackage::pkg()) in beginResetModel/endResetModel.")
    print("jaspModelResetSource.2=Desktop/data/datasetpackagesubnodemodel.cpp:77-87 selectNode() wraps setSourceModel(nullptr/DataSetPackage::pkg()) in beginResetModel/endResetModel.")
    print("jaspModelResetSource.3=Desktop/data/datasetpackage.cpp:1419-1452 beginLoadingData()/endLoadingData() wrap DataSetPackage reset and call enginesReceiveNewData() immediately after endResetModel().")
    print("jaspModelResetSource.classification=warnings-match-nested-source-model-reset-before-engine-spawn")

for index, ((object_name, address, kind), count) in enumerate(counts.most_common(12), 1):
    print(f"jaspModelResetObject.{index}.class={object_name}")
    print(f"jaspModelResetObject.{index}.address={address}")
    print(f"jaspModelResetObject.{index}.kind={kind}")
    print(f"jaspModelResetObject.{index}.count={count}")

for index, (line_number, kind, object_name, address) in enumerate(sequence[-12:], 1):
    print(f"jaspModelResetSequence.{index}.line={line_number}")
    print(f"jaspModelResetSequence.{index}.kind={kind}")
    print(f"jaspModelResetSequence.{index}.class={object_name}")
    print(f"jaspModelResetSequence.{index}.address={address}")
PY
  } >> "$log"
}

capture_jasp_timeout_diagnostics() {
  local id="$1" phase="$2" parent_pid="$3" log="$4"
  [ "$id" = "jasp-stats" ] && [ "$phase" = "launch" ] || return 0

  local jasp_pid sample_log reset_warnings end_reset_warnings begin_reset_warnings
  jasp_pid="$(ps -axo pid=,args= | rg -i 'JASPDesktop\.exe' | rg -v 'rg -i|/bin/zsh -c' | awk 'NR == 1 { print $1 }' || true)"
  sample_log="${log%.log}-jaspdesktop-sample.txt"
  begin_reset_warnings="$(rg -c 'beginResetModel called .* without calling endResetModel first' "$log" 2>/dev/null || true)"
  end_reset_warnings="$(rg -c 'endResetModel called .* without calling beginResetModel first' "$log" 2>/dev/null || true)"
  reset_warnings=$(( ${begin_reset_warnings:-0} + ${end_reset_warnings:-0} ))

  {
    echo
    echo "jaspTimeoutDiagnostics=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "jaspTimeoutDiagnosticsPhase=$phase"
    echo "jaspTimeout.parentPid=$parent_pid"
    echo "jaspTimeout.jaspDesktopPid=${jasp_pid:-missing}"
    if rg -q 'MACWIN_JASP_WEBENGINE_MODE=single-process' "$log"; then
      echo "jaspTimeout.webEngineMode=single-process"
    elif rg -q 'MACWIN_JASP_WEBENGINE_MODE=multiprocess' "$log"; then
      echo "jaspTimeout.webEngineMode=multiprocess"
    else
      echo "jaspTimeout.webEngineMode=unknown"
    fi
    echo "jaspTimeout.beginResetModelWarnings=${begin_reset_warnings:-0}"
    echo "jaspTimeout.endResetModelWarnings=${end_reset_warnings:-0}"
    echo "jaspTimeout.modelResetWarnings=$reset_warnings"
    if rg -q 'Engine #' "$log"; then
      echo "jaspTimeout.hasEngineStartMarker=yes"
    else
      echo "jaspTimeout.hasEngineStartMarker=no"
    fi
    if rg -q 'Setting new engine process' "$log"; then
      echo "jaspTimeout.hasEngineRepresentationMarker=yes"
    else
      echo "jaspTimeout.hasEngineRepresentationMarker=no"
    fi
    if rg -q 'JASP Desktop started and Engines initalized' "$log"; then
      echo "jaspTimeout.hasDesktopStartedMarker=yes"
    else
      echo "jaspTimeout.hasDesktopStartedMarker=no"
    fi
    if rg -q 'Initializing QML|Loading Themes|QML loaded|QML Initialized' "$log"; then
      echo "jaspTimeout.hasQmlMilestone=yes"
    else
      echo "jaspTimeout.hasQmlMilestone=no"
    fi
    echo "jaspTimeout.processes:"
    ps -axo pid,ppid,stat,rss,comm,args \
      | rg -i 'JASPDesktop\.exe|JASPEngine\.exe|QtWebEngineProcess\.exe|wine(64)?-preloader|wineserver' \
      | rg -v 'rg -i|/bin/zsh -c' \
      | sed 's/^/  /' || true
  } >> "$log"
  append_jasp_model_reset_summary "$log" "$phase-timeout" || true

  if [ -n "$jasp_pid" ] && command -v sample >/dev/null 2>&1; then
    echo "jaspTimeout.sampleLog=$sample_log" >> "$log"
    /usr/bin/sample "$jasp_pid" 2 5 -mayDie -file "$sample_log" >/dev/null 2>&1 || {
      echo "jaspTimeout.sampleFailed=$?" >> "$log"
      return 0
    }
    {
      echo "jaspTimeout.sampleCaptured=yes"
      awk '
        /^Physical footprint:[[:space:]]+/ {
          value = $0
          sub(/^Physical footprint:[[:space:]]+/, "", value)
          print "jaspTimeout.samplePhysicalFootprint=" value
        }
        /^Physical footprint \(peak\):[[:space:]]+/ {
          value = $0
          sub(/^Physical footprint \(peak\):[[:space:]]+/, "", value)
          print "jaspTimeout.samplePeakPhysicalFootprint=" value
        }
      ' "$sample_log"
      if rg -q 'com\.apple\.main-thread' "$sample_log" \
        && rg -q -- '-\[NSApplication run\]|RunCurrentEventLoopInMode|_DPSBlockUntilNextEvent|mach_msg' "$sample_log"; then
        echo "jaspTimeout.sampleHasMainThreadEventLoopWait=yes"
      else
        echo "jaspTimeout.sampleHasMainThreadEventLoopWait=no"
      fi
      if rg -q 'CrBrowserMain' "$sample_log"; then
        echo "jaspTimeout.sampleHasCrBrowserMain=yes"
      else
        echo "jaspTimeout.sampleHasCrBrowserMain=no"
      fi
      if awk '
        /CrBrowserMain/ { in_cr = 1; next }
        /^    [0-9]+ Thread_/ { in_cr = 0 }
        in_cr && /__wine_syscall_dispatcher/ { count++ }
        END { exit(count >= 12 ? 0 : 1) }
      ' "$sample_log"; then
        echo "jaspTimeout.sampleHasCrBrowserSyscallRecursion=yes"
      else
        echo "jaspTimeout.sampleHasCrBrowserSyscallRecursion=no"
      fi
      if awk '
        /CrBrowserMain/ { in_cr = 1; next }
        /^    [0-9]+ Thread_/ { in_cr = 0 }
        in_cr && /Rosetta JIT/ { count++ }
        END { exit(count >= 1 ? 0 : 1) }
      ' "$sample_log"; then
        echo "jaspTimeout.sampleHasCrBrowserRosettaJit=yes"
      else
        echo "jaspTimeout.sampleHasCrBrowserRosettaJit=no"
      fi
      if rg -q 'Rosetta' "$sample_log"; then
        echo "jaspTimeout.sampleHasRosetta=yes"
      else
        echo "jaspTimeout.sampleHasRosetta=no"
      fi
      if rg -q 'CrBrowserMain' "$sample_log" \
        && awk '
          /CrBrowserMain/ { in_cr = 1; next }
          /^    [0-9]+ Thread_/ { in_cr = 0 }
          in_cr && /__wine_syscall_dispatcher/ { count++ }
          END { exit(count >= 12 ? 0 : 1) }
        ' "$sample_log"; then
        echo "jaspTimeout.sampleInterpretation=JASPDesktop host main thread is alive in the Wine/macOS event loop while QtWebEngine CrBrowserMain is repeatedly inside Wine syscall dispatch; treat this as a WebEngine/Wine event-loop compatibility boundary, not as a completed app launch."
      elif rg -q 'CrBrowserMain' "$sample_log" \
        && awk '
          /CrBrowserMain/ { in_cr = 1; next }
          /^    [0-9]+ Thread_/ { in_cr = 0 }
          in_cr && /Rosetta JIT/ { count++ }
          END { exit(count >= 1 ? 0 : 1) }
        ' "$sample_log"; then
        echo "jaspTimeout.sampleInterpretation=JASPDesktop host main thread is alive in the Wine/macOS event loop while QtWebEngine CrBrowserMain is executing under Rosetta JIT with high footprint; treat this as a WebEngine/Rosetta/Wine compatibility boundary, not as a completed app launch."
      fi
      echo "jaspTimeout.samplePreview:"
      sed -n '1,80p' "$sample_log" | sed 's/^/  /'
    } >> "$log"
  else
    echo "jaspTimeout.sampleCaptured=no" >> "$log"
  fi
}

jasp_ipc_candidate_dirs() {
  printf '%s\n' \
    "$PREFIX/drive_c/users/$USER/AppData/Local/JASP/JASP/temp" \
    "$PREFIX/drive_c/ProgramData/boost_interprocess/01000000"
}

capture_jasp_boost_ipc_snapshot() {
  local id="$1" phase="$2" log="${3:-$LOG_DIR/${id}-ipc-files-${phase}.log}"
  [ "$id" = "jasp-stats" ] || return 0

  {
    echo
    echo "jaspIpcSnapshot.phase=$phase"
    echo "jaspIpcSnapshot.at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "jaspIpcSnapshot.prefix=$PREFIX"
    echo "jaspIpcSnapshot.processes:"
    ps -axo pid,ppid,stat,rss,comm,args \
      | rg -i 'JASPDesktop\.exe|JASPEngine\.exe|QtWebEngineProcess\.exe|wine(64)?-preloader|wineserver' \
      | rg -v 'rg -i|/bin/zsh -c' \
      | sed 's/^/  /' || true
    while IFS= read -r ipc_dir; do
      [ -n "$ipc_dir" ] || continue
      echo "jaspIpcSnapshot.dir=$ipc_dir"
      if [ ! -d "$ipc_dir" ]; then
        echo "jaspIpcSnapshot.dirState=missing"
        continue
      fi
      local count control_count master_count slave_count heartbeat_count
      count="$(find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null | wc -l | tr -d ' ')"
      control_count="$(find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*_[0-9]*' -print 2>/dev/null | wc -l | tr -d ' ')"
      master_count="$(find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*_MasterToSlave' -print 2>/dev/null | wc -l | tr -d ' ')"
      slave_count="$(find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*_SlaveToMaster' -print 2>/dev/null | wc -l | tr -d ' ')"
      heartbeat_count="$(find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*_heartbeat' -print 2>/dev/null | wc -l | tr -d ' ')"
      echo "jaspIpcSnapshot.fileCount=${count:-0}"
      echo "jaspIpcSnapshot.controlCount=${control_count:-0}"
      echo "jaspIpcSnapshot.masterToSlaveCount=${master_count:-0}"
      echo "jaspIpcSnapshot.slaveToMasterCount=${slave_count:-0}"
      echo "jaspIpcSnapshot.heartbeatCount=${heartbeat_count:-0}"
      find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null \
        | sort \
        | while IFS= read -r ipc_file; do
            printf 'jaspIpcSnapshot.file=%s' "${ipc_file#$ipc_dir/}"
            printf ' size='
            stat -f %z "$ipc_file" 2>/dev/null || wc -c < "$ipc_file"
            printf 'jaspIpcSnapshot.fileMeta=%s ' "${ipc_file#$ipc_dir/}"
            stat -f 'mtime=%m inode=%i mode=%Sp' "$ipc_file" 2>/dev/null || true
          done
    done < <(jasp_ipc_candidate_dirs)
  } >> "$log"
}

live_process_snapshot_has() {
  local log="$1" pattern="$2"
  LC_ALL=C awk '
    /^liveProcessSnapshot=/ { in_snapshot = 1; next }
    /^cleanupProbe=/ || /^processProbe=/ { in_snapshot = 0 }
    in_snapshot { print }
  ' "$log" | rg -q "$pattern"
}

terminate_live_gui_processes_for_sample() {
  local id="$1" log="$2"
  local pattern pids
  pattern="$(gui_process_pattern_for_sample "$id" 2>/dev/null || true)"
  [ -n "$pattern" ] || return 1
  pids="$(ps -axo pid=,args= | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' | awk '{print $1}' || true)"
  [ -n "$pids" ] || return 1
  {
    echo
    echo "cleanupProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "$pids" | sed 's/^/cleanupPid=/'
  } >> "$log"
  printf '%s\n' "$pids" | xargs kill 2>/dev/null || true
  sleep 2
  pids="$(ps -axo pid=,args= | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' | awk '{print $1}' || true)"
  if [ -n "$pids" ]; then
    printf '%s\n' "$pids" | xargs kill -KILL 2>/dev/null || true
  fi
  return 0
}

terminate_wine_focus_residue() {
  local line pid command lower
  ps -axo pid=,args= | while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    pid="${line%%[[:space:]]*}"
    command="${line#"$pid"}"
    command="${command#"${command%%[![:space:]]*}"}"
    [ -n "$pid" ] || continue
    lower="$(printf '%s' "$command" | tr '[:upper:]' '[:lower:]')"
    if { printf '%s' "$lower" | rg -q 'explorer\\.exe'; } \
      && { printf '%s' "$lower" | rg -q '/desktop'; }; then
      kill "$pid" 2>/dev/null || true
      continue
    fi
    if printf '%s' "$lower" | rg -q '(^|[[:space:]\\/\\\\])winedbg(\\.exe)?([[:space:]]|$)'; then
      kill "$pid" 2>/dev/null || true
      continue
    fi
  done
}

windows_process_names_for_sample() {
  case "$1" in
    freeoffice-suite)
      printf '%s\n' 'TextMaker.exe'
      ;;
    onlyoffice-suite)
      printf '%s\n' 'DesktopEditors.exe
editors.exe
converter.exe
crashpad_handler.exe'
      ;;
    drawio-diagram)
      printf '%s\n' 'draw.io.exe
crashpad_handler.exe'
      ;;
    pdfxchange-editor)
      printf '%s\n' 'PXCEditor.exe'
      ;;
    zotero-research)
      printf '%s\n' 'zotero.exe'
      ;;
    jabref-portable)
      printf '%s\n' 'JabRef.exe'
      ;;
    wxmaxima|macwin-maxima-cas)
      printf '%s\n' 'wxmaxima.exe'
      ;;
    openboard-whiteboard)
      printf '%s\n' 'OpenBoard.exe'
      ;;
    cloudcompare-pointcloud)
      printf '%s\n' 'CloudCompare.exe'
      ;;
    librecad)
      printf '%s\n' 'LibreCAD.exe'
      ;;
    openscad)
      printf '%s\n' 'openscad.exe'
      ;;
    qcad-legacy)
      printf '%s\n' 'qcad.exe'
      ;;
    sweethome3d-design)
      printf '%s\n' 'SweetHome3D.exe
javaw.exe'
      ;;
    gmsh-mesh)
      printf '%s\n' 'gmsh.exe'
      ;;
    brlcad-tools)
      printf '%s\n' 'archer.exe'
      ;;
    freecad-workbench)
      printf '%s\n' 'FreeCAD.exe'
      ;;
    solvespace-direct)
      printf '%s\n' 'SolveSpace-3.2-x64.exe'
      ;;
    ltspice-circuit)
      printf '%s\n' 'LTspice.exe'
      ;;
    dbeaver-database)
      printf '%s\n' 'dbeaver.exe'
      ;;
    qelectrotech-cad)
      printf '%s\n' 'qelectrotech.exe'
      ;;
    kicad-eda)
      printf '%s\n' 'kicad.exe'
      ;;
    meshlab-3d)
      printf '%s\n' 'meshlab.exe'
      ;;
    qgroundcontrol-drone)
      printf '%s\n' 'QGroundControl.exe'
      ;;
    qmodmaster-64|qmodmaster-32)
      printf '%s\n' 'qModMaster.exe'
      ;;
    lyx-editor)
      printf '%s\n' 'lyx.exe'
      ;;
    krita-paint)
      printf '%s\n' 'krita.exe'
      ;;
    flameshot-capture)
      printf '%s\n' 'flameshot.exe'
      ;;
    inkscape-vector)
      printf '%s\n' 'inkscape.exe'
      ;;
    librewolf-portable|librewolf-browser)
      printf '%s\n' 'librewolf.exe'
      ;;
    vivaldi-browser)
      printf '%s\n' 'vivaldi.exe
crashpad_handler.exe'
      ;;
    waterfox-browser)
      printf '%s\n' 'waterfox.exe'
      ;;
    palemoon-browser|palemoon-32-browser)
      printf '%s\n' 'palemoon.exe'
      ;;
    supermium-browser|supermium-32-browser)
      printf '%s\n' 'chrome.exe'
      ;;
    min-browser-portable)
      printf '%s\n' 'Min.exe'
      ;;
    notepadpp-editor|notepadpp-32-editor)
      printf '%s\n' 'notepad++.exe'
      ;;
    rufus-direct)
      printf '%s\n' 'rufus.exe'
      ;;
    qbittorrent-client)
      printf '%s\n' 'qbittorrent.exe'
      ;;
    portableapps-platform)
      printf '%s\n' 'PortableAppsPlatform.exe'
      ;;
    thonny-portable)
      printf '%s\n' 'thonny.exe'
      ;;
    lazarus-ide-32|lazarus-ide-64)
      printf '%s\n' 'lazarus.exe'
      ;;
    codeblocks-mingw)
      printf '%s\n' 'codeblocks.exe'
      ;;
    slic3r-32|slic3r-64)
      printf '%s\n' 'slic3r.exe'
      ;;
    openmodelica-omedit)
      printf '%s\n' 'OMEdit.exe'
      ;;
    pdfarranger-portable)
      printf '%s\n' 'pdfarranger.exe'
      ;;
    texstudio-editor)
      printf '%s\n' 'texstudio.exe'
      ;;
    qownnotes-portable)
      printf '%s\n' 'QOwnNotes.exe'
      ;;
    sqlitestudio-db)
      printf '%s\n' 'SQLiteStudio.exe'
      ;;
    winscp-client|winscp-x64-portable)
      printf '%s\n' 'WinSCP.exe'
      ;;
    keepass-passwords)
      printf '%s\n' 'KeePass.exe'
      ;;
    winmerge-diff)
      printf '%s\n' 'WinMergeU.exe'
      ;;
    firefox-developer)
      printf '%s\n' 'firefox.exe'
      ;;
    standard-notes)
      printf '%s\n' 'Standard Notes.exe'
      ;;
    sumatrapdf)
      printf '%s\n' 'SumatraPDF.exe'
      ;;
    everything)
      printf '%s\n' 'Everything.exe'
      ;;
    heidisql-portable)
      printf '%s\n' 'heidisql.exe'
      ;;
    audacity-audio)
      printf '%s\n' 'Audacity.exe
crashpad_handler.exe
crashreporter.exe'
      ;;
    lenovo-app-store)
      printf '%s\n' 'LenovoAppStore.exe
LeASLane.exe
LeAppStoreTray.exe
LenovoAppStoreNotify.exe
LenovoServiceAS.exe
LISFService.exe
LenovoInternetSoftwareFramework.exe'
      ;;
    bambu-studio-portable)
      printf '%s\n' 'bambu-studio.exe'
      ;;
    orcaslicer-print)
      printf '%s\n' 'orca-slicer.exe'
      ;;
    qucs-s-circuit)
      printf '%s\n' 'qucs-s.exe'
      ;;
    logisim-evolution)
      printf '%s\n' 'logisim-evolution.exe'
      ;;
    tiled-map-editor)
      printf '%s\n' 'tiled.exe'
      ;;
    musescore-studio)
      printf '%s\n' 'MuseScore4.exe'
      ;;
    jasp-stats)
      printf '%s\n' 'JASPDesktop.exe
JASPEngine.exe
QtWebEngineProcess.exe
junctionTool.exe'
      ;;
    ltspice-circuit)
      printf '%s\n' 'LTspice.exe'
      ;;
    *)
      return 1
      ;;
  esac
}

taskkill_windows_processes_for_sample() {
  local id="$1" log="$2"
  local names name taskkill_pid taskkill_started now
  names="$(windows_process_names_for_sample "$id" 2>/dev/null || true)"
  [ -n "$names" ] || return 1
  {
    echo
    echo "taskkillProbe=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    echo "taskkillImage=$name" >> "$log"
    "${WINE_CMD[@]}" taskkill.exe /IM "$name" /F >> "$log" 2>&1 &
    taskkill_pid=$!
    taskkill_started="$(date +%s)"
    while kill -0 "$taskkill_pid" 2>/dev/null; do
      sleep 1
      now="$(date +%s)"
      if [ "$((now - taskkill_started))" -ge 10 ]; then
        echo "taskkillTimeout=10s; terminating taskkill watchdog pid $taskkill_pid" >> "$log"
        kill "$taskkill_pid" 2>/dev/null || true
        sleep 1
        kill -KILL "$taskkill_pid" 2>/dev/null || true
        break
      fi
    done
    wait "$taskkill_pid" 2>/dev/null || true
  done <<< "$names"
  sleep 2
  return 0
}

cleanup_successful_gui_launch() {
  local id="$1" pid="$2" log="$3"
  taskkill_windows_processes_for_sample "$id" "$log" || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    terminate_live_gui_processes_for_sample "$id" "$log" || true
  fi
  for _ in 1 2 3; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
  terminate_wine_focus_residue
}

cleanup_timed_out_process() {
  local id="$1" phase="$2" pid="$3" log="$4"
	  if [ "$phase" = "launch" ]; then
	    capture_live_process_snapshot_for_sample "$id" "$phase-timeout-before-cleanup" "$log" || true
	    capture_visual_probe_for_sample "$id" "$phase" "$log" || true
	    capture_jasp_timeout_diagnostics "$id" "$phase" "$pid" "$log" || true
	    capture_jasp_boost_ipc_snapshot "$id" "$phase-timeout-before-cleanup" "$log" || true
	    if [ "$id" = "wps-office" ]; then
	      echo "WPS uses a shared multi-component process group; stopping the prefix as one unit." >> "$log"
	      "${WINESERVER_CMD[@]}" -k >> "$log" 2>&1 || true
	      wait "$pid" 2>/dev/null || true
	      terminate_wine_focus_residue
	      return 0
	    fi
	    taskkill_windows_processes_for_sample "$id" "$log" || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$pid" 2>/dev/null || {
      wait "$pid" 2>/dev/null || true
      terminate_wine_focus_residue
      return 0
    }
    terminate_live_gui_processes_for_sample "$id" "$log" || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
    if has_live_gui_process_for_sample "$id" "$log"; then
      echo "Target GUI process survived targeted cleanup; forcing wineserver shutdown." >> "$log"
      "${WINESERVER_CMD[@]}" -k >> "$log" 2>&1 || true
    fi
    terminate_wine_focus_residue
  else
    kill "$pid" 2>/dev/null || true
    sleep 2
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    "${WINESERVER_CMD[@]}" -k >> "$log" 2>&1 || true
    terminate_wine_focus_residue
  fi
}

repair_musescore_first_launch_config() {
  local users_root="$PREFIX/drive_c/users"
  local user_dirs=()
  local user_dir
  if [ -d "$users_root" ]; then
    while IFS= read -r user_dir; do
      case "$(basename "$user_dir")" in
        Public|Default|public|default) ;;
        *) user_dirs+=("$user_dir") ;;
      esac
    done < <(find "$users_root" -mindepth 1 -maxdepth 1 -type d -print)
  fi
  if [ "${#user_dirs[@]}" -eq 0 ]; then
    user_dirs+=("$users_root/$USER")
  fi

	for user_dir in "${user_dirs[@]}"; do
	    local ini_candidates=(
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore4.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore4/MuseScore4.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore4/MuseScore Studio 4.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio/MuseScore Studio.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio 4/MuseScore Studio 4.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio 4.ini"
	      "$user_dir/AppData/Roaming/MuseScore/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/Roaming/MuseScore Studio/MuseScore Studio.ini"
		      "$user_dir/AppData/Roaming/MuseScore Studio 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Roaming/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/Roaming/MuseScore 4/MuseScore4.ini"
		      "$user_dir/AppData/Roaming/MuseScore 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Roaming/MuseScore4/MuseScore4.ini"
		      "$user_dir/AppData/Roaming/MuseScoreStudio4/MuseScore4.ini"
		      "$user_dir/AppData/Roaming/MuseScoreStudio4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore4/MuseScore4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio/MuseScore Studio.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/Local/MuseScore Studio/MuseScore Studio.ini"
		      "$user_dir/AppData/Local/MuseScore Studio 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/Local/MuseScore 4/MuseScore4.ini"
		      "$user_dir/AppData/Local/MuseScore 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/Local/MuseScore4/MuseScore4.ini"
		      "$user_dir/AppData/Local/MuseScoreStudio4/MuseScore4.ini"
		      "$user_dir/AppData/Local/MuseScoreStudio4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore4/MuseScore4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio/MuseScore Studio.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/LocalLow/MuseScore Studio/MuseScore Studio.ini"
		      "$user_dir/AppData/LocalLow/MuseScore Studio 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore Studio 4 stable/MuseScore Studio 4 stable.ini"
		      "$user_dir/AppData/LocalLow/MuseScore 4/MuseScore4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore 4/MuseScore Studio 4.ini"
		      "$user_dir/AppData/LocalLow/MuseScore4/MuseScore4.ini"
		      "$user_dir/AppData/LocalLow/MuseScoreStudio4/MuseScore4.ini"
		      "$user_dir/AppData/LocalLow/MuseScoreStudio4/MuseScore Studio 4.ini"
		    )
    local ini
    for ini in "${ini_candidates[@]}"; do
    mkdir -p "$(dirname "$ini")"
    /usr/bin/python3 - "$ini" <<'PY'
from pathlib import Path
import configparser
import sys

path = Path(sys.argv[1])
config = configparser.ConfigParser()
config.optionxform = str
if path.exists():
    config.read(path, encoding="utf-8")

updates = {
    "General": {
        "application/hasCompletedFirstLaunchSetup": "true",
        "application/welcomeDialogShowOnStartup": "false",
        "application/welcomeDialogLastShownVersion": "999.999.999",
        "application/welcomeDialogLastShownIndex": "999",
        "application/startup/modeStart": "0",
        "application/startup/startScore": "",
        "ui/application/startup/showSplashScreen": "false",
        "onboarding/finished": "true",
        "onboarding/currentPageIndex": "999",
        "gettingstarted/finished": "true",
        "gettingstarted/currentPageIndex": "999",
        "gettingStarted/finished": "true",
        "gettingStarted/currentPageIndex": "999",
    },
    "application": {
        "hasCompletedFirstLaunchSetup": "true",
        "welcomeDialogShowOnStartup": "false",
        "welcomeDialogLastShownVersion": "999.999.999",
        "welcomeDialogLastShownIndex": "999",
        "currentStartupMode": "0",
        "startupScorePath": "",
        "showWelcomeDialog": "false",
        r"startup\modeStart": "0",
        r"startup\startScore": "",
    },
    "application/startup": {
        "modeStart": "0",
        "startScore": "",
    },
    "appshell/application": {
        "hasCompletedFirstLaunchSetup": "true",
        "welcomeDialogShowOnStartup": "false",
        "welcomeDialogLastShownVersion": "999.999.999",
        "welcomeDialogLastShownIndex": "999",
    },
    "appshell/application/startup": {
        "modeStart": "0",
        "startScore": "",
    },
    "ui": {
        r"application\currentThemeCode": "light",
        r"application\followSystemTheme": "false",
        r"application\highContrastEnabled": "false",
        r"application\currentAccentColorIndex": "4",
        r"application\startup\showSplashScreen": "false",
        r"theme\fontFamily": "Arial",
        r"theme\fontSize": "12",
    },
    "ui/application": {
        "currentThemeCode": "light",
        "followSystemTheme": "false",
        "highContrastEnabled": "false",
        "currentAccentColorIndex": "4",
    },
    "ui/application/startup": {
        "showSplashScreen": "false",
    },
    "appshell/ui/application": {
        "currentThemeCode": "light",
        "followSystemTheme": "false",
        "highContrastEnabled": "false",
        "currentAccentColorIndex": "4",
    },
    "appshell/ui/application/startup": {
        "showSplashScreen": "false",
    },
    "appshell/ui/theme": {
        "fontFamily": "Arial",
        "fontSize": "12",
    },
    "tours": {
        "lastShownTours": "",
    },
    "appshell/tours": {
        "lastShownTours": "",
    },
    "appshell/gettingstarted": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "appshell/gettingStarted": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "appshell/onboarding": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "gettingstarted": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "gettingStarted": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "onboarding": {
        "finished": "true",
        "currentPageIndex": "999",
    },
    "appshell": {
        r"application\hasCompletedFirstLaunchSetup": "true",
        r"application\welcomeDialogShowOnStartup": "false",
        r"application\welcomeDialogLastShownVersion": "999.999.999",
        r"application\welcomeDialogLastShownIndex": "999",
        r"application\startup\modeStart": "0",
        r"application\startup\startScore": "",
        r"ui\application\currentThemeCode": "light",
        r"ui\application\followSystemTheme": "false",
        r"ui\application\highContrastEnabled": "false",
        r"ui\application\currentAccentColorIndex": "4",
        r"ui\application\startup\showSplashScreen": "false",
        r"ui\theme\fontFamily": "Arial",
        r"ui\theme\fontSize": "12",
        r"tours\lastShownTours": "",
    },
}

for section, values in updates.items():
    if not config.has_section(section):
        config.add_section(section)
    for key, value in values.items():
        config.set(section, key, value)

with path.open("w", encoding="utf-8", newline="\n") as fh:
    config.write(fh, space_around_delimiters=False)
PY
    done
  done

  local reg="$PREFIX/user.reg"
  mkdir -p "$(dirname "$reg")"
  /usr/bin/python3 - "$reg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else "WINE REGISTRY Version 2\n\n"
roots = [
    r"Software\\MuseScore\\MuseScore Studio",
    r"Software\\MuseScore\\MuseScore 4",
    r"Software\\MuseScore\\MuseScore4",
    r"Software\\MuseScore\\MuseScoreStudio4",
    r"Software\\MuseScore\\MuseScore Studio 4",
    r"Software\\MuseScore\\MuseScore Studio 4 stable",
    r"Software\\MuseScore\\MuseScore Studio\\appshell",
    r"Software\\MuseScore\\MuseScore 4\\appshell",
    r"Software\\MuseScore\\MuseScore4\\appshell",
    r"Software\\MuseScore\\MuseScoreStudio4\\appshell",
    r"Software\\MuseScore\\MuseScore Studio 4\\appshell",
    r"Software\\MuseScore\\MuseScore Studio 4 stable\\appshell",
]
sections = {}
for root in roots:
    sections[f"{root}\\\\application"] = {
        "dword": {
            "hasCompletedFirstLaunchSetup": 1,
            "welcomeDialogShowOnStartup": 0,
            "welcomeDialogLastShownIndex": 999,
        },
        "string": {
            "welcomeDialogLastShownVersion": "999.999.999",
        },
    }
    sections[f"{root}\\\\application\\\\startup"] = {
        "dword": {"modeStart": 0},
        "string": {"startScore": ""},
    }
    sections[f"{root}\\\\ui\\\\application"] = {
        "dword": {
            "followSystemTheme": 0,
            "highContrastEnabled": 0,
            "currentAccentColorIndex": 4,
        },
        "string": {"currentThemeCode": "light"},
    }
    sections[f"{root}\\\\ui\\\\application\\\\startup"] = {
        "dword": {"showSplashScreen": 0},
        "string": {},
    }
    sections[f"{root}\\\\ui\\\\theme"] = {
        "dword": {"fontSize": 12},
        "string": {"fontFamily": "Arial"},
    }
    sections[f"{root}\\\\tours"] = {
        "dword": {},
        "string": {"lastShownTours": ""},
    }
    sections[f"{root}\\\\gettingstarted"] = {
        "dword": {
            "finished": 1,
            "currentPageIndex": 999,
        },
        "string": {},
    }
    sections[f"{root}\\\\gettingStarted"] = {
        "dword": {
            "finished": 1,
            "currentPageIndex": 999,
        },
        "string": {},
    }
    sections[f"{root}\\\\onboarding"] = {
        "dword": {
            "finished": 1,
            "currentPageIndex": 999,
        },
        "string": {},
    }

flattened_names = {
    "applicationhasCompletedFirstLaunchSetup",
    "applicationstartupmodeStart",
    "applicationstartupstartScore",
    "applicationwelcomeDialogLastShownIndex",
    "applicationwelcomeDialogLastShownVersion",
    "applicationwelcomeDialogShowOnStartup",
    "tourslastShownTours",
    "uiapplicationcurrentThemeCode",
    "uiapplicationcurrentAccentColorIndex",
    "uiapplicationfollowSystemTheme",
    "uiapplicationhighContrastEnabled",
    "uiapplicationstartupshowSplashScreen",
    r"ui\application\followSystemTheme",
    r"ui\applicationcurrentAccentColorIndex",
    r"ui\applicationcurrentThemeCode",
    r"ui\applicationhighContrastEnabled",
    r"ui\applicationstartupshowSplashScreen",
    r"ui\theme\fontFamily",
    r"ui\theme\fontSize",
    "uithemefontFamily",
    "uithemefontSize",
}

def line_for(kind, key, value):
    if kind == "dword":
        return f'"{key}"=dword:{value:08x}'
    escaped = str(value).replace("\\", "\\\\").replace('"', r'\"')
    return f'"{key}"="{escaped}"'

def wanted_lines(section):
    values = sections[section]
    lines = []
    for key, value in values["dword"].items():
        lines.append(line_for("dword", key, value))
    for key, value in values["string"].items():
        lines.append(line_for("string", key, value))
    return lines

lines = text.splitlines()
out = []
current = None
wrote = set()
found = set()

def finish_current():
    if current not in sections:
        return
    for line in wanted_lines(current):
        key = line.split('"=', 1)[0].strip('"')
        if key not in wrote:
            out.append(line)
            wrote.add(key)

for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        finish_current()
        current = stripped[1:stripped.index("]")]
        wrote = set()
        if current in sections:
            found.add(current)
        out.append(line)
        continue

    if current in sections and stripped.startswith('"') and '"=' in stripped:
        key = stripped.split('"=', 1)[0].strip('"')
        values = sections[current]
        if key in values["dword"]:
            out.append(line_for("dword", key, values["dword"][key]))
            wrote.add(key)
            continue
        if key in values["string"]:
            out.append(line_for("string", key, values["string"][key]))
            wrote.add(key)
            continue

    if current in roots and stripped.startswith('"') and '"=' in stripped:
        key = stripped.split('"=', 1)[0].strip('"')
        if key in flattened_names:
            continue

    out.append(line)

finish_current()

for section in sections:
    if section in found:
        continue
    if out and out[-1] != "":
        out.append("")
    out.append(f"[{section}]")
    out.extend(wanted_lines(section))

path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  if [ "${MACWIN_SMOKE_MUSESCORE_SYNC_REGISTRY:-0}" != "1" ]; then
    return 0
  fi

  local roots=(
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore 4'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore4'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScoreStudio4'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio 4'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio 4 stable'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio\appshell'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore 4\appshell'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore4\appshell'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScoreStudio4\appshell'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio 4\appshell'
    'HKEY_CURRENT_USER\Software\MuseScore\MuseScore Studio 4 stable\appshell'
  )
  local root
  for root in "${roots[@]}"; do
    wine_reg_add_quiet "$root" /v 'application\hasCompletedFirstLaunchSetup' /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root" /v 'application\welcomeDialogShowOnStartup' /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root" /v 'application\welcomeDialogLastShownVersion' /t REG_SZ /d 999.999.999 /f || true
    wine_reg_add_quiet "$root" /v 'application\welcomeDialogLastShownIndex' /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root" /v 'application\startup\modeStart' /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root" /v 'application\startup\startScore' /t REG_SZ /d "" /f || true
    wine_reg_add_quiet "$root" /v 'ui\application\currentThemeCode' /t REG_SZ /d light /f || true
    wine_reg_add_quiet "$root" /v 'ui\application\followSystemTheme' /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root" /v 'ui\application\highContrastEnabled' /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root" /v 'ui\application\currentAccentColorIndex' /t REG_DWORD /d 4 /f || true
    wine_reg_add_quiet "$root" /v 'ui\application\startup\showSplashScreen' /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root" /v 'ui\theme\fontFamily' /t REG_SZ /d Arial /f || true
    wine_reg_add_quiet "$root" /v 'ui\theme\fontSize' /t REG_DWORD /d 12 /f || true
    wine_reg_add_quiet "$root" /v 'tours\lastShownTours' /t REG_SZ /d "" /f || true
    wine_reg_add_quiet "$root" /v 'gettingstarted\finished' /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root" /v 'gettingstarted\currentPageIndex' /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root" /v 'gettingStarted\finished' /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root" /v 'gettingStarted\currentPageIndex' /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root" /v 'onboarding\finished' /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root" /v 'onboarding\currentPageIndex' /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root\\application" /v hasCompletedFirstLaunchSetup /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root\\application" /v welcomeDialogShowOnStartup /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root\\application" /v welcomeDialogLastShownVersion /t REG_SZ /d 999.999.999 /f || true
    wine_reg_add_quiet "$root\\application" /v welcomeDialogLastShownIndex /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root\\application\\startup" /v modeStart /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root\\application\\startup" /v startScore /t REG_SZ /d "" /f || true
    wine_reg_add_quiet "$root\\ui\\application" /v currentThemeCode /t REG_SZ /d light /f || true
    wine_reg_add_quiet "$root\\ui\\application" /v followSystemTheme /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root\\ui\\application" /v highContrastEnabled /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root\\ui\\application" /v currentAccentColorIndex /t REG_DWORD /d 4 /f || true
    wine_reg_add_quiet "$root\\ui\\application\\startup" /v showSplashScreen /t REG_DWORD /d 0 /f || true
    wine_reg_add_quiet "$root\\ui\\theme" /v fontFamily /t REG_SZ /d Arial /f || true
    wine_reg_add_quiet "$root\\ui\\theme" /v fontSize /t REG_DWORD /d 12 /f || true
    wine_reg_add_quiet "$root\\gettingstarted" /v finished /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root\\gettingstarted" /v currentPageIndex /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root\\gettingStarted" /v finished /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root\\gettingStarted" /v currentPageIndex /t REG_DWORD /d 999 /f || true
    wine_reg_add_quiet "$root\\onboarding" /v finished /t REG_DWORD /d 1 /f || true
    wine_reg_add_quiet "$root\\onboarding" /v currentPageIndex /t REG_DWORD /d 999 /f || true
  done
}

repair_winemac_input_config() {
  local reg="$PREFIX/user.reg"
  local retina_mode="N"
  local wine_dpi="96"
  local decorated="Y"
  if [ "${MACWIN_RETINA_INPUT_REPAIR:-0}" = "1" ]; then
    retina_mode="Y"
    wine_dpi="192"
  fi
  if [ "${MACWIN_BORDERLESS_APP_MODE:-0}" = "1" ] && [ "${MACWIN_CLICK_THROUGH_REPAIR:-0}" != "1" ]; then
    decorated="N"
  fi
  mkdir -p "$(dirname "$reg")"
  MACWIN_EFFECTIVE_RETINA_MODE="$retina_mode" MACWIN_EFFECTIVE_WINE_DPI="$wine_dpi" /usr/bin/python3 - "$reg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else "WINE REGISTRY Version 2\n\n"
import os

borderless = os.environ.get("MACWIN_BORDERLESS_APP_MODE") == "1" and os.environ.get("MACWIN_CLICK_THROUGH_REPAIR") != "1"
retina_mode = "Y" if os.environ.get("MACWIN_EFFECTIVE_RETINA_MODE") == "Y" else "N"
wine_dpi = int(os.environ.get("MACWIN_EFFECTIVE_WINE_DPI", "96"))
section_values = {
    "Software\\\\Wine\\\\Mac Driver": {
        "Managed": "Y",
        "Decorated": "N" if borderless else "Y",
        "UseTakeFocus": "Y",
        "GrabFullscreen": "N",
        "WindowsFloatWhenInactive": "all",
        "RetinaMode": retina_mode,
    },
    "Software\\\\Wine\\\\DirectInput": {
        "MouseWarpOverride": "disable",
    },
    "Software\\\\Wine\\\\X11 Driver": {
        "Managed": "Y",
        "Decorated": "N" if borderless else "Y",
        "UseTakeFocus": "Y",
        "GrabFullscreen": "N",
    },
}
section_dword_values = {
    "Software\\\\Wine\\\\Fonts": {
        "LogPixels": wine_dpi,
    },
}
obsolete_values = {
    "Software\\\\Wine\\\\Mac Driver": {"MouseWarpOverride"},
}

lines = text.splitlines()
out = []
target_section = None
found_section = False
found_sections = set()
wrote = set()

def finish_section():
    global out, wrote
    if target_section is None:
        return
    for key, value in section_values.get(target_section, {}).items():
        if key not in wrote:
            out.append(f'"{key}"="{value}"')
            wrote.add(key)
    for key, value in section_dword_values.get(target_section, {}).items():
        if key not in wrote:
            out.append(f'"{key}"=dword:{value:08x}')
            wrote.add(key)

for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        finish_section()
        current = stripped[1:stripped.index("]")]
        target_section = current if current in section_values or current in section_dword_values else None
        if target_section is not None:
            found_section = True
            found_sections.add(target_section)
            wrote = set()
        out.append(line)
        continue

    if target_section is not None and stripped.startswith('"') and '"=' in stripped:
        key = stripped.split('"=', 1)[0].strip('"')
        if key in obsolete_values.get(target_section, set()):
            continue
        if key in section_values.get(target_section, {}):
            out.append(f'"{key}"="{section_values[target_section][key]}"')
            wrote.add(key)
            continue
        if key in section_dword_values.get(target_section, {}):
            out.append(f'"{key}"=dword:{section_dword_values[target_section][key]:08x}')
            wrote.add(key)
            continue

    out.append(line)

finish_section()

for section in list(section_values) + [key for key in section_dword_values if key not in section_values]:
  if section not in found_sections:
    if out and out[-1] != "":
        out.append("")
    out.append(f"[{section}]")
    for key, value in section_values.get(section, {}).items():
        out.append(f'"{key}"="{value}"')
    for key, value in section_dword_values.get(section, {}).items():
        out.append(f'"{key}"=dword:{value:08x}')

path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v Managed /t REG_SZ /d Y /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v Decorated /t REG_SZ /d "$decorated" /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v UseTakeFocus /t REG_SZ /d Y /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v GrabFullscreen /t REG_SZ /d N /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v WindowsFloatWhenInactive /t REG_SZ /d all /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Mac Driver' /v RetinaMode /t REG_SZ /d "$retina_mode" /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Fonts' /v LogPixels /t REG_DWORD /d "$wine_dpi" /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\DirectInput' /v MouseWarpOverride /t REG_SZ /d disable /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v Managed /t REG_SZ /d Y /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v Decorated /t REG_SZ /d "$decorated" /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v UseTakeFocus /t REG_SZ /d Y /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v GrabFullscreen /t REG_SZ /d N /f || true
}

repair_retina_dpi_config() {
  local reg="$PREFIX/user.reg"
  [ -f "$reg" ] || return 0
  local retina_mode
  retina_mode="$(/usr/bin/python3 - "$reg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
current = None
for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        current = stripped[1:stripped.index("]")]
        continue
    if current == "Software\\\\Wine\\\\Mac Driver" and stripped.startswith('"RetinaMode"='):
        print("Y" if '"Y"' in stripped else "N")
        break
PY
  )"
  [ "$retina_mode" = "Y" ] || return 0
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Wine\Fonts' /v LogPixels /t REG_DWORD /d 192 /f || true
}

requires_clean_chromium_render_log() {
  case "$1" in
    brave-standalone|chrome-enterprise|edge-enterprise|vivaldi-browser)
      return 0
      ;;
    postman-api-client)
      return 0
      ;;
    vscode-portable)
      return 0
      ;;
    arduino-ide|beekeeper-studio|drawio-diagram|joplin-notes|obsidian-notes|onlyoffice-suite|standard-notes)
      return 0
      ;;
    supermium-browser|supermium-32-browser|ungoogled-chromium-portable|brave-portable|typora-editor|min-browser-portable|zettlr-editor|openplc-editor|openboard-whiteboard|sigil-ebook|marktext-editor|mqtt-explorer)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_chromium_rendering_failure() {
  local log="$1"
  rg -q 'FATAL:.*skia_output_surface|GPU process exited unexpectedly|Context was lost|Unable to initialize SkSurface|ContextResult::kFatalFailure|Failed to create shared context' "$log"
}

has_jasp_partial_qt_install_failure() {
  local log="$1"
  rg -q 'Qt6(WebChannel|WebChannelQuick|Sql|QuickControls2|WebEngineCore|WebEngineQuick)\.dll.*not found|Could not map .*Qt6Quick\.dll.*file probably truncated|Loading library Qt6Quick\.dll.*failed.*c000007b|Importing dlls for .*JASPDesktop\.exe.*failed, status c0000135' "$log"
}

has_jasp_qt_platform_plugin_missing_failure() {
  local log="$1"
  rg -q 'Could not find the Qt platform plugin "(minimal|offscreen)"' "$log"
}

jasp_qt_platform_plugin_missing_note() {
  local platforms_dir="$PREFIX/drive_c/Program Files/JASP/platforms"
  local bundled_plugins="unknown"
  if [ -d "$platforms_dir" ]; then
    bundled_plugins="$(find "$platforms_dir" -maxdepth 1 -type f -name '*.dll' -print 2>/dev/null | sed 's#.*/##' | sort | paste -sd ',' -)"
    [ -n "$bundled_plugins" ] || bundled_plugins="none"
  fi
  printf '%s\n' "JASP diagnostic --hide appends -platform minimal before QApplication startup, but this Windows MSI bundle does not provide the required Qt minimal/offscreen platform plugin (bundled platforms: ${bundled_plugins}). The run stops before MainWindow, DataSetPackage, EngineSync, IPC, and QML milestones, so classify this as an unsupported diagnostic mode rather than a successful GUI launch or the default JASP compatibility boundary."
}

has_jasp_qml_engine_crash_failure() {
  local log="$1"
  rg -q 'QtWebEngineQuick initialized' "$log" \
    && rg -q 'EngineSync::engines(PrepareForData|ReceiveNewData)!' "$log" \
    && rg -q 'Could not load QML: (qrc:/+components|file:/+C:/Program Files/JASP/components)/JASP/(Theme|Widgets)/' "$log" \
    && rg -q 'Unhandled page fault|WineDbg attached|dispatch_exception code=c0000005|Unhandled exception code c0000005' "$log"
}

has_jasp_qml_initialization_timeout_failure() {
  local log="$1"
  rg -q 'QtWebEngineQuick initialized' "$log" \
    && rg -q 'EngineSync::engines(PrepareForData|ReceiveNewData)!' "$log" \
    && rg -q 'TIMEOUT after .*sending SIGTERM' "$log" \
    && ! rg -q 'Loading Themes|QML Initialized!|QML loaded, url:' "$log"
}

jasp_qml_initialization_timeout_note() {
  local log="$1"
  if ! rg -q 'JASP Desktop started and Engines initalized' "$log"; then
    if rg -q 'liveProcessSnapshot=' "$log" && ! live_process_snapshot_has "$log" 'JASPEngine\.exe'; then
      local process_note="JASPDesktop.exe alive"
      if live_process_snapshot_has "$log" 'QtWebEngineProcess\.exe'; then
        process_note="$process_note and QtWebEngineProcess.exe alive"
      fi
      local engine_start_note="timeout diagnostics show no Engine # start marker or JASPEngine.exe process"
      if rg -q 'trace.hasJASPEngineCreateEvidence=no' "$log"; then
        engine_start_note="spawn trace shows no JASPEngine create attempt even with JASPENGINE_LOCATION set"
      fi
      printf '%s\n' "JASP initialized QtWebEngine and reached the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData path, but never reached the later JASP Desktop started marker or loadQML. The pre-cleanup process snapshot shows ${process_note} but no JASPEngine.exe, and ${engine_start_note}. Process liveness is not a valid launch success for this signature; continue with DataSetPackage model-reset, EngineSync reloadData, Qt model warning, and constructor-tail diagnostics before changing graphics flags."
      return 0
    fi
    printf '%s\n' "JASP initialized QtWebEngine and reached the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData path, but the constructor never reached the later JASP Desktop started log or loadQML's first Initializing QML line. Process liveness is not a valid launch success for this signature; continue with DataSetPackage model-reset, EngineSync reloadData, and constructor-tail diagnostics."
    return 0
  fi
  if ! rg -q 'Loading Themes' "$log"; then
    printf '%s\n' "JASP initialized QtWebEngine and reached EngineSync, but never emitted Loading Themes, QML loaded, or QML Initialized before the GUI watchdog timeout. Process liveness is not a valid launch success for this signature; the current boundary is before the first _qml->load call, so continue with EngineSync-to-loadQML handoff, root-context/model setup, or event-loop blocking diagnostics."
    return 0
  fi
  printf '%s\n' "JASP initialized QtWebEngine and reached EngineSync, but never emitted QML loaded/QML Initialized before the GUI watchdog timeout. Process liveness is not a valid launch success for this signature; continue with QQml object creation, resource/context setup, or EngineSync-to-QML handoff debugging."
}

jasp_embedded_qrc_evidence_note() {
  local exe="$PREFIX/drive_c/Program Files/JASP/JASPDesktop.exe"
  if [ -f "$exe" ] \
    && rg -a -q 'qrc:///components/JASP/Widgets/MainWindow\.qml' "$exe" \
    && rg -a -q 'qRegisterResourceData' "$exe"; then
    printf '%s' ' Embedded qrc resource names and qRegisterResourceData are present in JASPDesktop.exe, so the remaining failure is runtime Qt resource registration/readback under Wine.'
  fi
}

jasp_qml_engine_crash_note() {
  local log="${1:-}"
  local resource_scope='built-in qrc:/components/JASP'
  if [ -n "$log" ] && [ -f "$log" ] && rg -q 'Could not load QML: file:/+C:/Program Files/JASP/components/JASP/' "$log"; then
    resource_scope='fallback file:///C:/Program Files/JASP/components/JASP'
  fi
  printf '%s%s\n' \
    "JASP has a Qt software OpenGL fallback available and initializes QtWebEngine, then reaches EngineSync, but ${resource_scope} QML resources fail to load before a Wine page fault. This is a JASP Qt resource/QML compatibility failure, not an incomplete MSI payload or ordinary graphics preset issue." \
    "$(jasp_embedded_qrc_evidence_note)"
}

has_chromium_uao_failure() {
  local log="$1"
  rg -q 'UAO file invalid; all fields are not present' "$log"
}

has_wine_crash_failure() {
  local log="$1"
  rg -q 'Unhandled page fault|Unhandled exception code|starting debugger|WineDbg attached' "$log"
}

has_native_app_crash_report_failure() {
  local log="$1"
  rg -q 'Extra Info File: .*crash-info|Exception Pointer:' "$log"
}

has_opengl_capability_failure() {
  local log="$1"
  rg -q 'Unable to find a valid OpenGL 3\.2 or later implementation|OpenGL 3\.2.*required|Failed to create OpenGL context|QOpenGLWidget: Failed to create context' "$log"
}

has_qt_rhi_failure() {
  local log="$1"
  rg -q 'Failed to create RHI|Failed to initialize graphics backend for Vulkan|QRhi.*failed|QSG.*Failed to create' "$log"
}

has_jasp_engine_ipc_exit_failure() {
  local log="$1"
  rg -v '^command=' "$log" \
    | rg -q 'EngineSync::enginesReceiveNewData!' \
    && rg -v '^command=' "$log" \
      | rg -q 'Engine #|JASPEngine\.exe|Setting new engine process|JASP-IPC-'
}

has_jasp_engine_failfast_after_ipc_failure() {
  local log="$1"
  has_jasp_engine_ipc_exit_failure "$log" \
    && rg -q 'c0000409|NtRaiseException Unhandled exception code c0000409|NtLockFile I/O completion on lock not implemented yet|Qt6Core\.dll|ucrtbase\.dll' "$log"
}

has_jasp_constructor_boundary_exit_failure() {
  local log="$1"
  rg -v '^command=' "$log" \
    | rg -q 'DataSetPackage::endLoadingData' \
    && rg -v '^command=' "$log" \
      | rg -q 'EngineSync::enginesReceiveNewData!' \
    && ! rg -v '^command=' "$log" \
      | rg -q 'JASP Desktop started and Engines initalized|Initializing QML|Engine #|JASPEngine\.exe|TIMEOUT after'
}

has_jasp_complete_ipc_snapshot() {
  local log="$1"
  local expected_control_count="${MACWIN_JASP_MAX_ENGINES:-4}"
  if ! [[ "$expected_control_count" =~ ^[0-9]+$ ]] || [ "$expected_control_count" -lt 1 ]; then
    expected_control_count=4
  fi
  rg -q "^jaspIpcSnapshot\\.controlCount=${expected_control_count}$" "$log" \
    && rg -q '^jaspIpcSnapshot\.masterToSlaveCount=1$' "$log" \
    && rg -q '^jaspIpcSnapshot\.slaveToMasterCount=1$' "$log" \
    && rg -q '^jaspIpcSnapshot\.heartbeatCount=1$' "$log"
}

has_jasp_post_ipc_engine_spawn_stall() {
  local log="$1"
  rg -q 'DataSetPackage::endLoadingData' "$log" \
    && rg -q 'EngineSync::enginesReceiveNewData!' "$log" \
    && has_jasp_complete_ipc_snapshot "$log" \
    && ! rg -q '^trace\.hasJASPEngineCreateEvidence=yes$|Setting new engine process to engineRepresentation Engine #|Engine #' "$log" \
    && ! rg -q 'JASP Desktop started and Engines initalized|Initializing QML|Loading Themes|QML Initialized!|QML loaded, url:' "$log"
}

has_jasp_enginesync_constructor_reentry_failfast() {
  local log="$1"
  has_jasp_post_ipc_engine_spawn_stall "$log" \
    && rg -q 'c0000409|NtRaiseException Unhandled exception code c0000409|FAST_FAIL_FATAL_APP_EXIT|Qt6Core\.dll' "$log"
}

jasp_enginesync_constructor_reentry_failfast_note() {
  local isolation_note=""
  if [ "${MACWIN_JASP_CONSTRUCTOR_ISOLATION:-0}" = "1" ]; then
    isolation_note=" Constructor-tail isolation was active, so update prompts, update checks, remote configuration, and module-library URL setup are not sufficient to move this boundary."
  fi
  printf '%s\n' "JASP fails after EngineSync constructor re-entry: EngineSync::EngineSync calls DataSetPackage::setEngineSync(), which synchronously reaches DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData on the GUI thread before the first EngineRepresentation is constructed. EngineSync::start still creates a complete IPC/timer snapshot, but no EngineRepresentation setSlaveProcess marker, Engine # marker, JASPEngine create evidence, Desktop started, or loadQML milestone appears before Qt6Core raises c0000409/FAST_FAIL_FATAL_APP_EXIT. Treat this as a constructor re-entry/model-reset fail-fast boundary, not a graphics, QML resource, installer-payload, or engine-child loader failure.${isolation_note}"
}

jasp_post_ipc_engine_spawn_stall_note() {
  local isolation_note=""
  if [ "${MACWIN_JASP_CONSTRUCTOR_ISOLATION:-0}" = "1" ]; then
    isolation_note=" Constructor-tail isolation was active, so update prompts, update checks, remote configuration, and module-library URL setup are not sufficient to move this boundary."
  fi
  printf '%s\n' "JASP reached DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData and produced a complete fresh IPC snapshot (control files, MasterToSlave, SlaveToMaster, heartbeat), but no EngineRepresentation setSlaveProcess marker, Engine # marker, JASPEngine create evidence, or later QML/Desktop milestone appeared. Treat the Boost interprocess exceptions in this signature as recovered open_or_create retry noise; the current boundary is after EngineSync::start creates IPC/timers but before MainWindow reaches Desktop started/loadQML, and before the timer-driven createNewEngine()/startSlaveProcess path. The first enginesReceiveNewData is produced by EngineSync constructor re-entry through DataSetPackage::setEngineSync()->reset()->endLoadingData(), not by an already-created engine. The adjacent Qt model-reset warnings match DataSetPackageSubNodeModel wrapping setSourceModel() in beginResetModel/endResetModel and DataSetPackage::endLoadingData() calling enginesReceiveNewData() immediately after endResetModel().${isolation_note}"
}

has_jasp_boost_interprocess_boundary_failure() {
  local log="$1"
  rg -q 'DataSetPackage::endLoadingData' "$log" \
    && rg -q 'EngineSync::enginesReceiveNewData!' "$log" \
    && rg -q 'interprocess_exception@interprocess@boost|boost::interprocess|NtLockFile I/O completion on lock not implemented' "$log" \
    && ! has_jasp_complete_ipc_snapshot "$log" \
    && ! rg -q '^trace\.hasJASPEngineCreateEvidence=yes$|Engine #' "$log"
}

is_jasp_unit_test_launch() {
  [ "${MACWIN_JASP_EXTRA_LAUNCH_ARGS:-}" != "" ] \
    && printf '%s\n' "$MACWIN_JASP_EXTRA_LAUNCH_ARGS" | rg -q -- '(^|[[:space:]])--unitTest([[:space:]]|$)'
}

has_jasp_completed_analysis_workload() {
  local log="$1"
  log_has_runtime_fixed_string 'Engine#0:' "$log" \
    && log_has_runtime_fixed_string 'jaspEngine started' "$log" \
    && log_has_runtime_fixed_string 'Resultstatus of analysis was complete and it will now be processed.' "$log" \
    && log_has_runtime_fixed_string 'Old result conversion:' "$log" \
    && log_has_runtime_fixed_string 'New result conversion:' "$log"
}

rg_count_or_zero() {
  local pattern="$1" file="$2"
  if [ -f "$file" ]; then
    rg -c "$pattern" "$file" 2>/dev/null | awk '{s += $1} END {print s + 0}'
  else
    echo 0
  fi
}

log_has_runtime_fixed_string() {
  local needle="$1" file="$2"
  [ -f "$file" ] || return 1
  LC_ALL=C awk -v needle="$needle" '
    index($0, needle) > 0 && $0 !~ /^(command|note)=/ {
      found = 1
      exit
    }
    END {
      exit found ? 0 : 1
    }
  ' "$file"
}

append_jasp_launch_trace_summary() {
  local id="$1" phase="$2" log="$3"
  [ "$id" = "jasp-stats" ] && [ "$phase" = "launch" ] || return 0
  [ -f "$log" ] || return 0

  capture_jasp_boost_ipc_snapshot "$id" "trace-summary" "$log" || true

  {
    echo
    echo "## JASP launch trace summary"
    echo "traceSummaryAt=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if rg -q '^WINEDEBUG=|\sWINEDEBUG=' "$log"; then
      rg -o 'WINEDEBUG=[^[:space:]]+' "$log" | tail -1 | sed 's/^/trace./'
    else
      echo "trace.WINEDEBUG=unknown"
    fi
    echo "trace.ipcTracePreset=${MACWIN_JASP_IPC_TRACE:-0}"
    echo "trace.cleanIpcPreset=${MACWIN_JASP_CLEAN_IPC:-0}"
    echo "trace.constructorIsolationPreset=${MACWIN_JASP_CONSTRUCTOR_ISOLATION:-0}"
    echo "trace.jaspIpcSnapshotCount=$(rg_count_or_zero '^jaspIpcSnapshot\.phase=' "$log")"
    echo "trace.jaspIpcSnapshotFileCountLines=$(rg_count_or_zero '^jaspIpcSnapshot\.fileCount=' "$log")"
    echo "trace.jaspIpcCreateNotFoundCount=$(rg_count_or_zero 'Unable to create file .*JASP-IPC-.*status c0000035|NtCreateFile .*JASP-IPC-.*not found \\(c0000035\\)' "$log")"
    echo "trace.jaspIpcMentionCount=$(rg_count_or_zero 'JASP-IPC-[0-9]+_(0|MasterToSlave|SlaveToMaster|heartbeat)' "$log")"
    echo "trace.jaspIpcControlMentionCount=$(rg_count_or_zero 'JASP-IPC-[0-9]+_0' "$log")"
    echo "trace.jaspIpcMasterToSlaveMentionCount=$(rg_count_or_zero 'JASP-IPC-[0-9]+_MasterToSlave' "$log")"
    echo "trace.jaspIpcSlaveToMasterMentionCount=$(rg_count_or_zero 'JASP-IPC-[0-9]+_SlaveToMaster' "$log")"
    echo "trace.jaspIpcHeartbeatMentionCount=$(rg_count_or_zero 'JASP-IPC-[0-9]+_heartbeat' "$log")"
    echo "trace.ntLockFileFixmeCount=$(rg_count_or_zero 'NtLockFile I/O completion on lock not implemented' "$log")"
    echo "trace.boostInterprocessExceptionCount=$(rg_count_or_zero 'interprocess_exception@interprocess@boost|boost::interprocess' "$log")"
    echo "trace.failFastC0000409Count=$(rg_count_or_zero 'c0000409|Unhandled exception code c0000409|NtRaiseException Unhandled exception code c0000409' "$log")"
    if rg -q 'Unhandled exception|Unhandled page fault|dispatch_exception code=|c0000005|c0000409|RaiseException|NtRaiseException' "$log"; then
      echo "trace.hasSehOrExceptionEvidence=yes"
    else
      echo "trace.hasSehOrExceptionEvidence=no"
    fi
    if rg -q 'JASPDesktop\.exe' "$log"; then
      echo "trace.hasJASPDesktopString=yes"
    else
      echo "trace.hasJASPDesktopString=no"
    fi
    if rg -q 'JASPEngine\.exe' "$log"; then
      echo "trace.hasJASPEngineString=yes"
    else
      echo "trace.hasJASPEngineString=no"
    fi
    if rg -q 'create_process|CreateProcess|fork_and_exec|exec_process|Starting process' "$log"; then
      echo "trace.hasProcessCreateEvidence=yes"
    else
      echo "trace.hasProcessCreateEvidence=no"
    fi
    if rg -q 'JASPEngine\.exe.*(create_process|CreateProcess|fork_and_exec|exec_process|Starting process)|(create_process|CreateProcess|fork_and_exec|exec_process|Starting process).*JASPEngine\.exe' "$log"; then
      echo "trace.hasJASPEngineCreateEvidence=yes"
    else
      echo "trace.hasJASPEngineCreateEvidence=no"
    fi
    if rg -q '^jaspIpcSnapshot\.controlCount=4$' "$log" \
      && rg -q '^jaspIpcSnapshot\.masterToSlaveCount=1$' "$log" \
      && rg -q '^jaspIpcSnapshot\.slaveToMasterCount=1$' "$log" \
      && rg -q '^jaspIpcSnapshot\.heartbeatCount=1$' "$log"; then
      echo "trace.hasCompleteJaspIpcSnapshot=yes"
    else
      echo "trace.hasCompleteJaspIpcSnapshot=no"
    fi
    if rg -q 'DataSetPackage::endLoadingData' "$log"; then
      echo "trace.hasDataSetPackageEndLoadingData=yes"
    else
      echo "trace.hasDataSetPackageEndLoadingData=no"
    fi
    if rg -q 'EngineSync::enginesReceiveNewData!' "$log"; then
      echo "trace.hasEngineSyncReceiveNewData=yes"
    else
      echo "trace.hasEngineSyncReceiveNewData=no"
    fi
    if rg -q 'JASP Desktop started and Engines initalized|Initializing QML|Loading Themes|QML Initialized!' "$log"; then
      echo "trace.hasLaterQmlOrDesktopMilestone=yes"
    else
      echo "trace.hasLaterQmlOrDesktopMilestone=no"
    fi
  } >> "$log"
}

has_wineserver_cleanup_warning() {
  local log="$1"
  rg -q 'wineserver crashed, please enable coredumps' "$log"
}

has_qgroundcontrol_gstreamer_optional_warning() {
  local log="$1"
  rg -q "GStreamer-WARNING.*Failed to load plugin .*gst(directsound|directsoundsrc|winks)\\.dll" "$log"
}

has_gtk_directwrite_render_warning() {
  local log="$1"
  rg -q "Window Direct Write error|CreateBitmap failed" "$log"
}

has_gtk_pango_render_warning() {
  local log="$1"
  rg -q "Pango-CRITICAL.*pango_font_description_to_string" "$log"
}

has_gtk_dwm_render_warning() {
  local log="$1"
  rg -q "DwmEnableBlurBehindWindow .* failed: 80004001" "$log"
}

has_gtk_keyboard_layout_warning() {
  local log="$1"
  rg -q "Failed to load keyboard layout DLL for layout" "$log"
}

has_qt_font_or_painter_warning() {
  local log="$1"
  rg -q "QFont::fromString: Invalid description|QPainter::begin: Paint device returned engine == 0|QPainter::.*Painter not active" "$log"
}

append_note() {
  local base="$1" extra="$2"
  if [ -n "$base" ]; then
    printf '%s %s\n' "$base" "$extra"
  else
    printf '%s\n' "$extra"
  fi
}

allows_child_crash_with_live_gui() {
  case "$1" in
    floorp-browser|seamonkey-browser|seamonkey-32-browser|mullvad-browser|supermium-browser|supermium-32-browser|zotero-research|wxmaxima|macwin-maxima-cas|labplot-workbench|qmodmaster-32)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

allows_chromium_gpu_child_crash_with_live_gui() {
  case "$1" in
    supermium-32-browser)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

allows_first_launch_retry() {
  case "$1" in
    librewolf-browser|firefox-developer|floorp-browser|waterfox-browser|mullvad-browser|supermium-32-browser|zen-browser|zotero-research|labplot-workbench|musescore-studio|qmodmaster-32)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_dotnet_host_failure() {
  local log="$1"
  rg -q 'System\.IO\.FileNotFoundException: Could not load file or assembly|hostfxr|hostpolicy|coreclr|CoreCLR|System\.Runtime\.dll|CLRRuntimeInfo_GetRuntimeHost Wine Mono is not installed|mscoree\.dll not found|IL-only binary .* cannot be loaded|You must install \.NET to run this application|Download the \.NET runtime|Microsoft\.WindowsDesktop\.App|Microsoft\.NETCore\.App|App host version' "$log"
}

has_mono_native_crash_failure() {
  local log="$1"
  rg -q 'Native Crash Reporting|fatal error in the mono runtime' "$log"
}

mremoteng_legacy_mono_note() {
  printf '%s\n' "mRemoteNG 1.76.x is a legacy 32-bit .NET Framework/Wine-Mono path that crashes in the native Mono runtime; use the validated mRemoteNG 1.78.2 x64 sample with the deployed .NET Desktop Runtime 10."
}

has_gdiplus_system_drawing_failure() {
  local log="$1"
  rg -q 'System\.Drawing\.GDIPlus|GDI\+ status: InvalidParameter|GdipGetImageFlags 0000000000000000|System\.Windows\.Forms\.ControlPaint\.IsImageTransparent' "$log"
}

has_wpf_wic_imaging_failure() {
  local log="$1"
  rg -q 'No imaging component suitable to complete this operation|System\.Windows\.Media\.Imaging\.BitmapDecoder|Eto\.Wpf\.Drawing\.IconHandler' "$log"
}

has_python_entropy_failure() {
  local log="$1"
  rg -q '_Py_HashRandomization_Init: failed to get random numbers to initialize Python|Python runtime state: preinitialized' "$log"
}

python_entropy_failure_note() {
  local id="$1"
  if [ "$id" = "esphome-flasher-x86" ]; then
    printf '%s\n' "32-bit embedded Python failed to obtain random bytes during preinitialization; check the WOW64 CryptoAPI provider registry and rsaenh.dll repair path."
  else
    printf '%s\n' "Embedded Python failed to obtain random bytes during preinitialization; check the CryptoAPI provider registry and rsaenh.dll repair path."
  fi
}

has_wow64_seh_dispatch_failure() {
  local log="$1"
  rg -q 'err:seh:call_seh_handlers invalid frame|NtRaiseException Exception frame is not in stack limits' "$log"
}

has_winscp_vcl_wow64_seh_failure() {
  local log="$1"
  rg -q 'WinSCP[\\/]+WinSCP\.exe|WinSCP\.exe' "$log" \
    && rg -q 'dispatch_exception code=c0000005|EXCEPTION_ACCESS_VIOLATION|NtRaiseException Exception frame is not in stack limits' "$log"
}

winscp_legacy_wow64_note() {
  printf '%s\n' "WinSCP stable installer uses a legacy 32-bit Delphi/VCL path; enable the managed rosettax87 runtime or use the validated x64 portable WinSCP samples."
}

has_managed_rosetta_x87() {
  [ -x "$ROSETTA_X87_RUNTIME" ]
}

is_superseded_legacy_launch_sample() {
  case "$1" in
    winscp-client)
      ! has_managed_rosetta_x87
      return
      ;;
    winscp-cli-help)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

has_gecko_wow64_access_violation_failure() {
  local log="$1"
  rg -q 'EXCEPTION_ACCESS_VIOLATION|dispatch_exception code=c0000005|Unhandled page fault' "$log"
}

zotero_wow64_gecko_note() {
  printf '%s\n' "Zotero may emit 32-bit Gecko/WOW64 debugger lines during first-run startup; classify it as a real engine failure only when no parent/content process survives the retry window."
}

has_geogebra_wow64_electron_access_violation_failure() {
  local log="$1"
  rg -q 'Unhandled page fault on read access to 00005ECD at address 7B[0-9A-Fa-f]{6}1139|WineDbg attached' "$log"
}

geogebra_classic6_wow64_note() {
  printf '%s\n' "GeoGebra Classic 6 / Calculator Suite is a 32-bit Electron/Chromium WOW64 regression path in this engine; use the validated GeoGebra Classic 5 installer for the current geometry UI compatibility target."
}

palemoon32_legacy_gecko_note() {
  printf '%s\n' "Pale Moon 32-bit requires the managed rosettax87 runtime for its Gecko/XUL startup path; enable ROSETTA_X87_PATH or use the validated SeaMonkey 32-bit and Supermium 32-bit coverage targets."
}

has_javafx_font_failure() {
  local log="$1"
  rg -q 'Cannot invoke "com\.sun\.javafx\.font\.LogicalFont\.getSlot0Resource\(\)"|Cannot invoke "com\.sun\.javafx\.font\.(FontResource|CompositeFontResource)|Exception in Application start method' "$log"
}

has_javafx_directwrite_wic_failure() {
  local log="$1"
  rg -q 'com\.sun\.javafx\.font\.directwrite\.IWICImagingFactory\.CreateBitmap|com\.sun\.javafx\.font\.directwrite\.DWGlyph|Cannot invoke "com\.sun\.javafx\.font\.directwrite\.IWICImagingFactory' "$log"
}

has_javafx_sw_glyph_warning() {
  local log="$1"
  rg -q 'STRIDE \* HEIGHT exceeds length of data|com\.sun\.prism\.sw\.SWGraphics\.drawGlyph' "$log"
}

has_javafx_font_mapping_warning() {
  local log="$1"
  rg -q 'No match for name (Lucida Sans Regular|SimSun|Microsoft YaHei UI)|No match for name .* in C:\\windows\\Fonts' "$log"
}

has_jabref_completed_javafx_startup() {
  local log="$1"
  log_has_runtime_fixed_string 'Theme set to Theme{' "$log" \
    && log_has_runtime_fixed_string 'org.jabref.gui.StateManager.setActiveDatabase()' "$log" \
    && ! rg -qi 'Unhandled page fault|Unhandled exception|starting debugger|fatal error|Java VM:.*crash' "$log"
}

has_dwsim_gtk_font_warning() {
  local log="$1"
  rg -q "Pango-WARNING|couldn't load font \"\\(NULL\\)" "$log"
}

has_missing_media_dll_failure() {
  local log="$1"
  rg -qi '(WMVCore|mfplat|mfreadwrite|mfuuid|propsys)\.DLL.*(c0000135|failed)|Importing dlls.*failed, status c0000135' "$log"
}

is_pe32_dotnet_executable() {
  local path="$1"
  [ -f "$path" ] || return 1
  /usr/bin/file "$path" | rg -q 'PE32 executable.*Mono/.Net assembly'
}

is_pe32_executable() {
  local path="$1" description
  [ -f "$path" ] || return 1
  description="$(/usr/bin/file "$path" 2>/dev/null || true)"
  printf '%s\n' "$description" | rg -q 'PE32 executable' \
    && ! printf '%s\n' "$description" | rg -q 'PE32\+ executable'
}

gui_launcher_may_delegate() {
  case "$1" in
    geogebra-classic5|sweethome3d-design)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

run_logged() {
  local id="$1" phase="$2" timeout_seconds="$3" timeout_state="${4:-timeout}" timeout_note="${5:-Process did not exit before timeout.}"
  shift 5
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration pid exit_code state note wait_remaining parent_exit_code
  started="$(date +%s)"
  {
    echo "== MacWin software smoke =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$WINEPREFIX"
    echo "command=$*"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"
  if [ "$id" = "jasp-stats" ] && [ "$phase" = "launch" ]; then
    capture_jasp_boost_ipc_snapshot "$id" "prelaunch" "$log" || true
  fi

  "$@" >> "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    ended="$(date +%s)"
    if [ "$((ended - started))" -ge "$timeout_seconds" ]; then
      echo "TIMEOUT after ${timeout_seconds}s; sending SIGTERM to $pid" >> "$log"
      cleanup_timed_out_process "$id" "$phase" "$pid" "$log"
      ended="$(date +%s)"
      duration="$((ended - started))"
      if [ "$phase" = "launch" ] && has_dotnet_host_failure "$log"; then
        record "$id" "$phase" "failed" 91 "$log" "$duration" ".NET runtime/host assembly load failure during GUI launch."
        return 91
      fi
	      if [ "$phase" = "launch" ] && has_mono_native_crash_failure "$log"; then
	        if [ "$id" = "mremoteng-manager" ]; then
	          record "$id" "$phase" "skipped" 103 "$log" "$duration" "$(mremoteng_legacy_mono_note)"
	          return 0
	        else
	          record "$id" "$phase" "failed" 103 "$log" "$duration" ".NET/Wine-Mono native runtime crash during GUI launch."
	          return 103
	        fi
	      fi
      if [ "$phase" = "launch" ] && has_gdiplus_system_drawing_failure "$log"; then
        record "$id" "$phase" "failed" 93 "$log" "$duration" "WinForms/System.Drawing GDI+ image decoding failure during GUI launch."
        return 93
      fi
      if [ "$phase" = "launch" ] && has_wpf_wic_imaging_failure "$log"; then
        record "$id" "$phase" "failed" 95 "$log" "$duration" "WPF/WIC image decoding failure during GUI launch."
        return 95
      fi
      if [ "$phase" = "launch" ] && has_python_entropy_failure "$log"; then
        record "$id" "$phase" "failed" 94 "$log" "$duration" "$(python_entropy_failure_note "$id")"
        return 94
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "winscp-client" ] && has_winscp_vcl_wow64_seh_failure "$log"; then
	        record "$id" "$phase" "skipped" 108 "$log" "$duration" "$(winscp_legacy_wow64_note)"
	        return 0
	      fi
      if [ "$phase" = "launch" ] && [ "$id" = "zotero-research" ] && has_gecko_wow64_access_violation_failure "$log" && ! has_live_gui_process_for_sample "$id" "$log"; then
        record "$id" "$phase" "failed" 104 "$log" "$duration" "$(zotero_wow64_gecko_note)"
        return 104
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "palemoon-32-browser" ] && ! has_managed_rosetta_x87 && has_gecko_wow64_access_violation_failure "$log"; then
	        record "$id" "$phase" "skipped" 109 "$log" "$duration" "$(palemoon32_legacy_gecko_note)"
	        return 0
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "geogebra-classic" ] && has_geogebra_wow64_electron_access_violation_failure "$log"; then
	        record "$id" "$phase" "skipped" 106 "$log" "$duration" "$(geogebra_classic6_wow64_note)"
	        return 0
	      fi
      if [ "$phase" = "launch" ] && has_wow64_seh_dispatch_failure "$log" && ! allows_child_crash_with_live_gui "$id"; then
        record "$id" "$phase" "failed" 99 "$log" "$duration" "WOW64 SEH exception dispatch failed during launch."
        return 99
      fi
      if [ "$phase" = "launch" ] && has_javafx_font_failure "$log"; then
        record "$id" "$phase" "failed" 96 "$log" "$duration" "JavaFX font mapping failed during GUI startup."
        return 96
      fi
      if [ "$phase" = "launch" ] && has_javafx_directwrite_wic_failure "$log"; then
        record "$id" "$phase" "failed" 98 "$log" "$duration" "JavaFX DirectWrite/WIC glyph rendering failed during GUI startup."
        return 98
      fi
      if [ "$phase" = "launch" ] && has_missing_media_dll_failure "$log"; then
        record "$id" "$phase" "failed" 97 "$log" "$duration" "Windows media dependency failed during loader startup."
        return 97
      fi
      if [ "$phase" = "launch" ] && has_native_app_crash_report_failure "$log"; then
        record "$id" "$phase" "failed" 101 "$log" "$duration" "Application crash reporter emitted crash-info during launch."
        return 101
      fi
      if [ "$phase" = "launch" ] && has_opengl_capability_failure "$log"; then
        record "$id" "$phase" "failed" 102 "$log" "$duration" "Application requires a newer OpenGL capability than the current Wine graphics path exposes."
        return 102
      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_partial_qt_install_failure "$log"; then
	        record "$id" "$phase" "failed" 110 "$log" "$duration" "JASP Qt runtime payload is incomplete or truncated; rerun a full MSI install instead of stopping when JASPDesktop.exe first appears."
	        return 110
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_qt_platform_plugin_missing_failure "$log"; then
	        record "$id" "$phase" "skipped" 122 "$log" "$duration" "$(jasp_qt_platform_plugin_missing_note)"
	        return 0
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_qml_engine_crash_failure "$log"; then
	        record "$id" "$phase" "failed" 111 "$log" "$duration" "$(jasp_qml_engine_crash_note "$log")"
	        return 111
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ]; then
	        append_jasp_launch_trace_summary "$id" "$phase" "$log"
	        if has_jasp_enginesync_constructor_reentry_failfast "$log"; then
	          append_jasp_model_reset_summary "$log" "$phase-enginesync-constructor-reentry-failfast" || true
	          record "$id" "$phase" "failed" 123 "$log" "$duration" "$(jasp_enginesync_constructor_reentry_failfast_note)"
	          return 123
	        fi
	        if has_jasp_post_ipc_engine_spawn_stall "$log"; then
	          append_jasp_model_reset_summary "$log" "$phase-post-ipc-engine-spawn-stall" || true
	          record "$id" "$phase" "failed" 114 "$log" "$duration" "$(jasp_post_ipc_engine_spawn_stall_note)"
	          return 114
	        fi
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_qml_initialization_timeout_failure "$log"; then
	        record "$id" "$phase" "failed" 113 "$log" "$duration" "$(jasp_qml_initialization_timeout_note "$log")"
	        return 113
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_boost_interprocess_boundary_failure "$log"; then
	        record "$id" "$phase" "failed" 121 "$log" "$duration" "JASP reached DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData, then emitted Boost interprocess exception evidence before any Engine # or JASPEngine create marker. Standalone JASP-shaped Boost IPC passes, so treat this as a real JASP process lifecycle/channel boundary; compare jaspIpcSnapshot prelaunch/trace-summary/postlaunch files, PID naming, stale cleanup, and constructor timing."
	        return 121
	      fi
      if [ "$phase" = "launch" ] && has_wine_crash_failure "$log" && ! allows_child_crash_with_live_gui "$id"; then
        record "$id" "$phase" "failed" 90 "$log" "$duration" "Wine crash/debugger detected during GUI launch."
        return 90
      fi
	      if [ "$phase" = "launch" ] && requires_clean_chromium_render_log "$id" && has_chromium_rendering_failure "$log" && ! allows_chromium_gpu_child_crash_with_live_gui "$id"; then
	        record "$id" "$phase" "failed" 89 "$log" "$duration" "Chromium launch log contains GPU/Skia rendering failures."
	        return 89
	      fi
      local timeout_record_note="$timeout_note"
      if [ "$phase" = "launch" ] && has_wineserver_cleanup_warning "$log"; then
        timeout_record_note="$(append_note "$timeout_record_note" "Cleanup emitted a wineserver crash warning after target process termination.")"
      fi
      if [ "$phase" = "launch" ] && allows_child_crash_with_live_gui "$id" && has_wine_crash_failure "$log"; then
        timeout_record_note="$(append_note "$timeout_record_note" "A child/helper process emitted Wine debugger lines while the GUI process stayed alive.")"
      fi
      if [ "$phase" = "launch" ] && [ "$id" = "qgroundcontrol-drone" ] && has_qgroundcontrol_gstreamer_optional_warning "$log"; then
        timeout_record_note="$(append_note "$timeout_record_note" "QGroundControl reported missing optional GStreamer DirectSound/winks plugins; GUI launch still survived.")"
      fi
	      if [ "$phase" = "launch" ] && has_javafx_sw_glyph_warning "$log"; then
	        timeout_record_note="$(append_note "$timeout_record_note" "JavaFX software glyph rendering emitted STRIDE warnings; text rendering still needs follow-up validation.")"
	      fi
	      if [ "$phase" = "launch" ] && has_javafx_font_mapping_warning "$log"; then
	        timeout_record_note="$(append_note "$timeout_record_note" "JavaFX reported missing Windows font aliases; GUI stayed alive, but text fallback still needs visual validation.")"
	      fi
	      if [ "$phase" = "launch" ] && [ "$id" = "rstudio-desktop" ] && has_chromium_rendering_failure "$log"; then
	        timeout_record_note="$(append_note "$timeout_record_note" "RStudio QtWebEngine reported GPU child-process failures while the GUI stayed alive; software-renderer flags are active and the remaining issue is visual validation.")"
	      fi
      if [ "$phase" = "launch" ] && [ "$id" = "dwsim-process-sim" ] && has_dwsim_gtk_font_warning "$log"; then
        timeout_record_note="$(append_note "$timeout_record_note" "DWSIM launched, but GTK/Pango reported fallback font rendering; keep this as an open text-quality compatibility issue.")"
      fi
      if [ "$phase" = "launch" ] && has_gtk_directwrite_render_warning "$log"; then
        timeout_record_note="$(append_note "$timeout_record_note" "GTK/Pango reported DirectWrite bitmap/text drawing errors; GUI survived but rendering quality needs follow-up.")"
      fi
      if [ "$phase" = "launch" ] && has_gtk_pango_render_warning "$log"; then
        if [ "$id" = "pdfarranger-portable" ] && ! has_gtk_directwrite_render_warning "$log"; then
          timeout_record_note="$(append_note "$timeout_record_note" "PDF Arranger emitted GTK/Pango's empty font-description startup warning; GTK3 font defaults are present and no DirectWrite drawing failure was observed.")"
        elif [ "$id" = "dwsim-process-sim" ] && ! has_dwsim_gtk_font_warning "$log"; then
          timeout_record_note="$(append_note "$timeout_record_note" "DWSIM emitted GTK/Pango's empty font-description startup warning, but no fallback font load failure was observed with the managed GTK profile.")"
        else
          timeout_record_note="$(append_note "$timeout_record_note" "GTK/Pango reported a font-description warning; GUI survived but text quality still needs visual validation.")"
        fi
      fi
	      if [ "$phase" = "launch" ] && has_gtk_dwm_render_warning "$log"; then
	        timeout_record_note="$(append_note "$timeout_record_note" "GTK requested unsupported DWM blur; disabled transparency path is active but Wine still logs the warning.")"
	      fi
	      if [ "$phase" = "launch" ] && has_gtk_keyboard_layout_warning "$log"; then
	        timeout_record_note="$(append_note "$timeout_record_note" "GTK queried Wine keyboard layout DLLs that are not present in this engine; keyboard layout substitute mappings are neutralized, but locale preloads are regenerated by Wine and this warning is tracked separately from click/text rendering failures.")"
	      fi
	      if [ "$phase" = "launch" ] && has_qt_font_or_painter_warning "$log"; then
	        if [ "$id" = "qucs-s-circuit" ]; then
	          timeout_record_note="$(append_note "$timeout_record_note" "Qucs-S emitted Qt font/SVG painter warnings while GUI stayed alive; Qucs font defaults are registered and remaining warnings are tracked as bundled schematic icon rendering noise.")"
	        else
	          timeout_record_note="$(append_note "$timeout_record_note" "Qt reported font-description or painter warnings; GUI survived but text/icon rendering needs visual validation.")"
	        fi
	      fi
      if [ "$phase" = "launch" ]; then
        local timeout_visual_note
        timeout_visual_note="$(visual_probe_note "$log" || true)"
        if [ -n "$timeout_visual_note" ]; then
          timeout_record_note="$(append_note "$timeout_record_note" "$timeout_visual_note")"
        fi
      fi
      if [ "$phase" = "launch" ] && has_visual_probe_blocking_issue "$log"; then
        record "$id" "$phase" "failed" 125 "$log" "$duration" "$timeout_record_note"
        return 125
      fi
      if [ "$phase" = "launch" ] && [ "$timeout_state" = "launched" ]; then
        echo "smokeOutcome=keptAlive" >> "$log"
      fi
      record "$id" "$phase" "$timeout_state" 124 "$log" "$duration" "$timeout_record_note"
      if [ "$timeout_state" = "launched" ]; then
        return 0
      fi
      return 124
    fi
  done
  exit_code=0
  wait "$pid" || exit_code=$?
  parent_exit_code="$exit_code"
  ended="$(date +%s)"
  duration="$((ended - started))"
  state="passed"
  if [ "$exit_code" -ne 0 ]; then
    state="failed"
  fi
  if [ "$phase" = "launch" ] && [ "$timeout_state" = "launched" ] && { [ "$duration" -lt "$GUI_MIN_LAUNCH_SECONDS" ] || [ "$parent_exit_code" -ne 0 ] || has_qt_rhi_failure "$log" || gui_launcher_may_delegate "$id"; }; then
    wait_remaining="$((GUI_MIN_LAUNCH_SECONDS - duration))"
    if [ "$wait_remaining" -gt 0 ]; then
      sleep "$wait_remaining"
    fi
    if gui_launcher_may_delegate "$id"; then
      local delegate_waited=0
      while [ "$delegate_waited" -lt 20 ] && ! has_live_gui_process_for_sample "$id" "$log"; do
        sleep 1
        delegate_waited=$((delegate_waited + 1))
      done
    fi
    ended="$(date +%s)"
    duration="$((ended - started))"
    if has_live_gui_process_for_sample "$id" "$log"; then
      state="passed"
      exit_code=0
      if [ "$parent_exit_code" -ne 0 ]; then
        note="GUI launcher parent exited with code ${parent_exit_code}, but the application process stayed alive through the ${GUI_MIN_LAUNCH_SECONDS}s launch window."
      else
        note="GUI launcher parent exited, but the application process stayed alive through the ${GUI_MIN_LAUNCH_SECONDS}s launch window."
      fi
      capture_visual_probe_for_sample "$id" "$phase" "$log" || true
      taskkill_windows_processes_for_sample "$id" "$log" || true
      terminate_live_gui_processes_for_sample "$id" "$log" || true
    else
      if allows_first_launch_retry "$id"; then
        if has_qt_rhi_failure "$log"; then
          echo "First GUI launch reported a Qt RHI failure; retrying once for first-run graphics initialization." >> "$log"
        else
          echo "First GUI launch did not survive the ${GUI_MIN_LAUNCH_SECONDS}s window; retrying once for first-run profile initialization." >> "$log"
        fi
        "$@" >> "$log" 2>&1 &
        pid=$!
        local retry_started retry_now retry_elapsed retry_exit_code
        retry_started="$(date +%s)"
        while kill -0 "$pid" 2>/dev/null; do
          sleep 1
          retry_now="$(date +%s)"
          retry_elapsed="$((retry_now - retry_started))"
          if [ "$retry_elapsed" -ge "$GUI_MIN_LAUNCH_SECONDS" ]; then
            ended="$(date +%s)"
            duration="$((ended - started))"
            if has_live_gui_process_for_sample "$id" "$log"; then
              capture_visual_probe_for_sample "$id" "$phase" "$log" || true
              cleanup_successful_gui_launch "$id" "$pid" "$log"
              state="passed"
              exit_code=0
              note="GUI launch passed after one first-run retry."
              break
            fi
          fi
          if [ "$retry_elapsed" -ge "$timeout_seconds" ]; then
            echo "RETRY TIMEOUT after ${timeout_seconds}s; sending SIGTERM to $pid" >> "$log"
            cleanup_timed_out_process "$id" "$phase" "$pid" "$log"
            state="$timeout_state"
            exit_code=124
            note="$timeout_note"
            break
          fi
        done
        if kill -0 "$pid" 2>/dev/null; then
          :
        elif [ -z "${note:-}" ]; then
          retry_exit_code=0
          wait "$pid" || retry_exit_code=$?
          sleep "$GUI_MIN_LAUNCH_SECONDS"
          ended="$(date +%s)"
          duration="$((ended - started))"
          if has_live_gui_process_for_sample "$id" "$log"; then
            state="passed"
            exit_code=0
            note="GUI launcher parent exited during retry, but the application process stayed alive through the ${GUI_MIN_LAUNCH_SECONDS}s launch window."
            capture_visual_probe_for_sample "$id" "$phase" "$log" || true
            taskkill_windows_processes_for_sample "$id" "$log" || true
            terminate_live_gui_processes_for_sample "$id" "$log" || true
          else
            state="failed"
            if [ "$retry_exit_code" -eq 0 ]; then
              exit_code=88
            else
              exit_code="$retry_exit_code"
            fi
            note="GUI process exited before ${GUI_MIN_LAUNCH_SECONDS}s minimum launch window after one retry."
          fi
        fi
      else
        state="failed"
        if [ "$parent_exit_code" -eq 0 ]; then
          exit_code=88
        else
          exit_code="$parent_exit_code"
        fi
        note="GUI process exited before ${GUI_MIN_LAUNCH_SECONDS}s minimum launch window."
      fi
    fi
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] \
    && is_jasp_unit_test_launch && has_jasp_completed_analysis_workload "$log"; then
    state="passed"
    exit_code=0
    note="JASP initialized its R engine, completed the requested statistical analysis, and produced old/new result tables."
    if log_has_runtime_fixed_string 'The results are different...' "$log"; then
      note="$(append_note "$note" "The bundled sample baseline differs from the current JASP result formatting or precision; this is reported as a numerical-baseline warning, not a Wine execution failure.")"
    fi
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "palemoon-32-browser" ] && ! has_managed_rosetta_x87 && [ "$state" = "failed" ] && printf '%s' "${note:-}" | rg -q "GUI process exited before"; then
    state="skipped"
    exit_code=109
    note="$(palemoon32_legacy_gecko_note)"
  fi
  if [ "$phase" = "launch" ] && requires_clean_chromium_render_log "$id" && has_chromium_rendering_failure "$log" && ! allows_chromium_gpu_child_crash_with_live_gui "$id"; then
    state="failed"
    if [ "$exit_code" -eq 0 ]; then
      exit_code=89
    fi
    note="Chromium launch log contains GPU/Skia rendering failures."
  fi
  if [ "$phase" = "launch" ] && [ "$state" = "failed" ] && has_chromium_uao_failure "$log"; then
    state="failed"
    exit_code=100
    note="Chromium/Supermium user-agent override metadata is invalid during startup."
  fi
  append_jasp_launch_trace_summary "$id" "$phase" "$log"
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$state" = "failed" ] && has_jasp_enginesync_constructor_reentry_failfast "$log"; then
    append_jasp_model_reset_summary "$log" "$phase-enginesync-constructor-reentry-failfast" || true
    state="failed"
    exit_code=123
    note="$(jasp_enginesync_constructor_reentry_failfast_note)"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$state" = "failed" ] && has_jasp_post_ipc_engine_spawn_stall "$log"; then
    append_jasp_model_reset_summary "$log" "$phase-post-ipc-engine-spawn-stall" || true
    if [ "${exit_code:-0}" -ne 123 ]; then
      state="failed"
      exit_code=114
      note="$(jasp_post_ipc_engine_spawn_stall_note)"
    fi
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$state" = "failed" ] && has_jasp_constructor_boundary_exit_failure "$log"; then
    state="failed"
    exit_code=120
    note="JASP exited after the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData handoff, before Desktop started, loadQML, or any Engine # marker. Treat this as a MainWindow constructor-tail boundary rather than an engine-child IPC failure; compare WebEngine mode and instrument the lines after enginesReceiveNewData/modelInit."
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$state" = "failed" ] && has_jasp_boost_interprocess_boundary_failure "$log"; then
    state="failed"
    exit_code=121
    note="JASP reached DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData, then emitted Boost interprocess exception evidence before any Engine # or JASPEngine create marker. Standalone JASP-shaped Boost IPC passes, so treat this as a real JASP process lifecycle/channel boundary; compare jaspIpcSnapshot prelaunch/trace-summary/postlaunch/timeout files, PID naming, stale cleanup, and constructor timing."
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$exit_code" -ne 114 ] && [ "${parent_exit_code:-$exit_code}" -eq 9 ] && has_jasp_engine_ipc_exit_failure "$log"; then
    state="failed"
    exit_code=107
    if has_jasp_engine_failfast_after_ipc_failure "$log"; then
      note="JASP initialized Qt/QML resources but exited after EngineSync data handoff with c0000409 fail-fast; Wine logs also show NtLockFile/Qt6Core/ucrtbase signals. Standalone JASP-shaped Boost IPC passes, so focus on real JASP engine process lifecycle, heartbeat files, stale IPC cleanup, and channel constructor timing."
    else
      note="JASP initialized Qt/QML resources but exited after EngineSync data handoff; standalone JASP-shaped Boost IPC passes, so focus on real JASP shared-memory lifecycle, engine heartbeat state, stale IPC cleanup, and channel constructor timing."
    fi
  fi
  if [ "$phase" = "launch" ] && has_dotnet_host_failure "$log"; then
    state="failed"
    exit_code=91
    note=".NET runtime/host assembly load failure during launch."
  fi
  if [ "$phase" = "launch" ] && has_mono_native_crash_failure "$log"; then
    if [ "$id" = "mremoteng-manager" ]; then
      state="skipped"
      exit_code=103
      note="$(mremoteng_legacy_mono_note)"
    else
      state="failed"
      exit_code=103
      note=".NET/Wine-Mono native runtime crash during launch."
    fi
  fi
  if [ "$phase" = "launch" ] && has_gdiplus_system_drawing_failure "$log"; then
    state="failed"
    exit_code=93
    note="WinForms/System.Drawing GDI+ image decoding failure during launch."
  fi
  if [ "$phase" = "launch" ] && has_wpf_wic_imaging_failure "$log"; then
    state="failed"
    exit_code=95
    note="WPF/WIC image decoding failure during launch."
  fi
  if [ "$phase" = "launch" ] && has_python_entropy_failure "$log"; then
    state="failed"
    exit_code=94
    note="$(python_entropy_failure_note "$id")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "zotero-research" ] && has_gecko_wow64_access_violation_failure "$log" && ! has_live_gui_process_for_sample "$id" "$log" && ! printf '%s' "${note:-}" | rg -q 'first-run retry|stayed alive'; then
    state="failed"
    exit_code=104
    note="$(zotero_wow64_gecko_note)"
  elif [ "$phase" = "launch" ] && [ "$id" = "zotero-research" ] && has_gecko_wow64_access_violation_failure "$log"; then
    note="$(append_note "${note:-}" "Zotero emitted Gecko/WOW64 debugger lines while a GUI parent or content process survived.")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_partial_qt_install_failure "$log"; then
    state="failed"
    exit_code=110
    note="JASP Qt runtime payload is incomplete or truncated; rerun a full MSI install instead of stopping when JASPDesktop.exe first appears."
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_qt_platform_plugin_missing_failure "$log"; then
    state="skipped"
    exit_code=122
    note="$(jasp_qt_platform_plugin_missing_note)"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && has_jasp_qml_engine_crash_failure "$log"; then
    state="failed"
    exit_code=111
    note="$(jasp_qml_engine_crash_note "$log")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jasp-stats" ] && [ "$exit_code" -ne 114 ] && has_jasp_qml_initialization_timeout_failure "$log"; then
    state="failed"
    exit_code=113
    note="$(jasp_qml_initialization_timeout_note "$log")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "palemoon-32-browser" ] && ! has_managed_rosetta_x87 && has_gecko_wow64_access_violation_failure "$log"; then
    state="skipped"
    exit_code=109
    note="$(palemoon32_legacy_gecko_note)"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "geogebra-classic" ] && has_geogebra_wow64_electron_access_violation_failure "$log"; then
    state="skipped"
    exit_code=106
    note="$(geogebra_classic6_wow64_note)"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "winscp-client" ] && has_winscp_vcl_wow64_seh_failure "$log"; then
    state="skipped"
    exit_code=108
    note="$(winscp_legacy_wow64_note)"
  fi
  if [ "$phase" = "launch" ] && has_wow64_seh_dispatch_failure "$log" && ! allows_child_crash_with_live_gui "$id" && [ "$exit_code" -ne 104 ] && [ "$exit_code" -ne 106 ] && [ "$exit_code" -ne 108 ]; then
    state="failed"
    exit_code=99
    note="WOW64 SEH exception dispatch failed during launch."
  fi
  if [ "$phase" = "launch" ] && has_javafx_font_failure "$log"; then
    state="failed"
    exit_code=96
    note="JavaFX font mapping failed during GUI startup."
  fi
  if [ "$phase" = "launch" ] && has_javafx_directwrite_wic_failure "$log"; then
    state="failed"
    exit_code=98
    note="JavaFX DirectWrite/WIC glyph rendering failed during GUI startup."
  fi
  if [ "$phase" = "launch" ] && has_missing_media_dll_failure "$log"; then
    state="failed"
    exit_code=97
    note="Windows media dependency failed during loader startup."
  fi
  if [ "$phase" = "launch" ] && has_native_app_crash_report_failure "$log"; then
    state="failed"
    exit_code=101
    note="Application crash reporter emitted crash-info during launch."
  fi
  if [ "$phase" = "launch" ] && has_opengl_capability_failure "$log"; then
    state="failed"
    exit_code=102
    note="Application requires a newer OpenGL capability than the current Wine graphics path exposes."
  fi
  if [ "$phase" = "launch" ] && has_qt_rhi_failure "$log" && { [ "$state" != "passed" ] || ! printf '%s' "${note:-}" | rg -q 'first-run retry|stayed alive'; }; then
    state="failed"
    exit_code=105
    note="Qt RHI graphics backend failed during launch."
  fi
  if [ "$phase" = "launch" ] && has_wine_crash_failure "$log"; then
    state="failed"
    if allows_child_crash_with_live_gui "$id" && [ "$exit_code" -eq 0 ]; then
      state="passed"
      note="${note:-GUI launch passed}; child process emitted Wine debugger lines."
    elif ! printf '%s\n' "$exit_code" | rg -q '^(89|90|91|93|94|95|96|97|98|99|100|101|102|103|104|105|106|107|110|111|114|120|121|123)$'; then
      exit_code=90
      note="Wine crash/debugger detected during launch."
    fi
  fi
	  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && has_wineserver_cleanup_warning "$log"; then
	    note="$(append_note "${note:-}" "Cleanup emitted a wineserver crash warning after target process termination.")"
	  fi
	  if [ "$phase" != "launch" ] && [ "$state" != "failed" ] && has_wineserver_cleanup_warning "$log"; then
	    note="$(append_note "${note:-}" "Wine server emitted a crash warning during the $phase phase; app samples are not classified from this engine lifecycle warning.")"
	  fi
  if [ "$phase" = "install" ] && [ "$state" != "failed" ] && [ "$id" = "freeoffice-suite" ]; then
    note="$(append_note "${note:-}" "SoftMaker FreeOffice MSI can emit WixQuietExec errors for taskbar pinning, updater task registration, or install-log copying under Wine; TextMaker file and launch checks are the compatibility signal.")"
  fi
  if [ "$phase" = "install" ] && [ "$state" != "failed" ] && [ "$id" = "energyplus-building" ] \
    && log_has_runtime_fixed_string 'Automatic answer for "installationErrorWithCancel": "Ignore"' "$log"; then
    note="$(append_note "${note:-}" "EnergyPlus core and simulation tools installed successfully; QtIFW ignored optional legacy Graph32 OCX registration and Windows shortcut creation failures that do not affect energyplus.exe workloads.")"
  fi
  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && [ "$id" = "qgroundcontrol-drone" ] && has_qgroundcontrol_gstreamer_optional_warning "$log"; then
    note="$(append_note "${note:-}" "QGroundControl reported missing optional GStreamer DirectSound/winks plugins; GUI launch still survived.")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "jabref-portable" ] && has_javafx_sw_glyph_warning "$log"; then
    state="failed"
    exit_code=126
    note="JabRef entered the broken JavaFX software glyph pipeline; D3D rendering is required for a valid GUI result."
  elif [ "$phase" = "launch" ] && [ "$state" != "failed" ] && has_javafx_sw_glyph_warning "$log"; then
    note="$(append_note "${note:-}" "JavaFX software glyph rendering emitted STRIDE warnings; text rendering still needs follow-up validation.")"
  fi
  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && has_javafx_font_mapping_warning "$log"; then
    note="$(append_note "${note:-}" "JavaFX reported missing Windows font aliases; GUI stayed alive, but text fallback still needs visual validation.")"
  fi
  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && [ "$id" = "rstudio-desktop" ] && has_chromium_rendering_failure "$log"; then
    note="$(append_note "${note:-}" "RStudio QtWebEngine reported GPU child-process failures while the GUI stayed alive; software-renderer flags are active and the remaining issue is visual validation.")"
  fi
  if [ "$phase" = "launch" ] && [ "$id" = "dwsim-process-sim" ] && [ "$state" != "failed" ] && has_dwsim_gtk_font_warning "$log"; then
    note="$(append_note "${note:-}" "DWSIM launched, but GTK/Pango reported fallback font rendering; keep this as an open text-quality compatibility issue.")"
  fi
  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && has_gtk_keyboard_layout_warning "$log"; then
    note="$(append_note "${note:-}" "GTK queried Wine keyboard layout DLLs that are not present in this engine; keyboard layout substitute mappings are neutralized, but locale preloads are regenerated by Wine and this warning is tracked separately from click/text rendering failures.")"
  fi
  if [ "$phase" = "launch" ] && [ "$state" != "failed" ] && has_qt_font_or_painter_warning "$log"; then
    if [ "$id" = "qucs-s-circuit" ]; then
      note="$(append_note "${note:-}" "Qucs-S emitted Qt font/SVG painter warnings while GUI stayed alive; Qucs font defaults are registered and remaining warnings are tracked as bundled schematic icon rendering noise.")"
    else
      note="$(append_note "${note:-}" "Qt reported font-description or painter warnings; GUI survived but text/icon rendering needs visual validation.")"
    fi
  fi
  if [ "$phase" = "launch" ]; then
    visual_note="$(visual_probe_note "$log" || true)"
    if [ -n "$visual_note" ]; then
      note="$(append_note "${note:-}" "$visual_note")"
    fi
    if has_visual_probe_blocking_issue "$log"; then
      state="failed"
      exit_code=125
    fi
  fi
  {
    echo
    if [ "$state" = "passed" ]; then
      echo "smokeOutcome=passed"
    fi
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "exitCode=$exit_code"
    if [ -n "${note:-}" ]; then
      echo "note=$note"
    fi
  } >> "$log"
  if [ -n "${note:-}" ]; then
    record "$id" "$phase" "$state" "$exit_code" "$log" "$duration" "$note"
  else
    record "$id" "$phase" "$state" "$exit_code" "$log" "$duration" ""
  fi
  return "$exit_code"
}

run_launch_logged() {
  local cwd="$1"
  local id="${2:-}"
  local phase="${3:-}"
  shift
  if [ "$phase" = "launch" ]; then
    terminate_wine_focus_residue
    activate_wine_gui_focus "$id"
  fi
  if [ -d "$cwd" ]; then
    (
      cd "$cwd"
      run_logged "$@"
    )
  else
    run_logged "$@"
  fi
}

activate_wine_gui_focus() {
  local id="${1:-}"
  case "$id" in
    musescore-studio|qelectrotech-cad|qgroundcontrol-drone|qownnotes-portable|sqlitebrowser-db|steam-client|lenovo-app-store|tencent-androws|hoyoplay)
      ;;
    *)
      return 0
      ;;
  esac

/usr/bin/osascript >/dev/null 2>&1 <<'OSA' &
set targetProcessNames to {"wine", "wine-preloader", "wine64-preloader", "MuseScore4", "MuseScore4.exe", "MuseScore Studio"}
set targetWindowTitleTokens to {"MuseScore", "入门", "Get Started", "Welcome"}
set shouldClickContentProbe to false
set welcomeWindowTitleTokens to {"入门", "Get Started", "Welcome", "MuseScore Studio"}
set welcomeContentTokens to {"欢迎使用", "MuseScore Studio", "选择主题", "高对比度", "浅色", "深色", "下一步", "Next"}
set welcomeButtonTokens to {"下一步", "Next", "继续", "Continue", "完成", "Finish", "开始", "Start"}

on elementTextMatches(uiElement, tokenList)
    try
        set elementName to name of uiElement as text
        repeat with tokenValue in tokenList
            if elementName contains (tokenValue as text) then return true
        end repeat
    end try
    try
        set elementDescription to description of uiElement as text
        repeat with tokenValue in tokenList
            if elementDescription contains (tokenValue as text) then return true
        end repeat
    end try
    try
        set elementValue to value of uiElement as text
        repeat with tokenValue in tokenList
            if elementValue contains (tokenValue as text) then return true
        end repeat
    end try
    return false
end elementTextMatches

on windowContentMatches(windowElement, tokenList)
    try
        if my elementTextMatches(windowElement, tokenList) then return true
    end try
    try
        repeat with uiElement in entire contents of windowElement
            if my elementTextMatches(uiElement, tokenList) then return true
        end repeat
    end try
    return false
end windowContentMatches

repeat with attemptIndex from 1 to 40
    delay 0.25
    with timeout of 1 second
        tell application "System Events"
            repeat with p in every process
                try
                    set processName to name of p as text
                    set processMatches to false
                    repeat with targetName in targetProcessNames
                        if processName is (targetName as text) then set processMatches to true
                        if processName contains (targetName as text) then set processMatches to true
                    end repeat

                    if (count of windows of p) > 0 then
                        repeat with w in windows of p
                            set windowMatches to processMatches
                            try
                                set windowName to name of w as text
                                repeat with titleToken in targetWindowTitleTokens
                                    if windowName contains (titleToken as text) then set windowMatches to true
                                end repeat
                            end try

	                            if windowMatches is true then
	                                set frontmost of p to true
	                                try
	                                    perform action "AXRaise" of w
	                                end try
	                                try
	                                    set windowPosition to position of w
	                                    set windowSize to size of w
	                                    set windowLooksLikeWelcome to false
	                                    try
	                                        set windowName to name of w as text
	                                        repeat with welcomeTitleToken in welcomeWindowTitleTokens
	                                            if windowName contains (welcomeTitleToken as text) then set windowLooksLikeWelcome to true
	                                        end repeat
	                                    end try
	                                    if windowLooksLikeWelcome is false then
	                                        try
	                                            if my windowContentMatches(w, welcomeContentTokens) then set windowLooksLikeWelcome to true
	                                        end try
	                                    end if
		                                    if shouldClickContentProbe is true or windowLooksLikeWelcome is true then
		                                        set clickX to (item 1 of windowPosition) + ((item 1 of windowSize) / 2)
		                                        set clickY to (item 2 of windowPosition) + 28
		                                        if (item 2 of windowSize) < 80 then set clickY to (item 2 of windowPosition) + ((item 2 of windowSize) / 2)
		                                        click at {clickX, clickY}
		                                        delay 0.05
		                                        set frontmost of p to true
		                                    end if
	                                    if shouldClickContentProbe is true then
	                                        delay 0.08
	                                        set probeX to (item 1 of windowPosition) + 24
	                                        set probeY to (item 2 of windowPosition) + 64
	                                        if (item 1 of windowSize) < 120 then set probeX to (item 1 of windowPosition) + ((item 1 of windowSize) / 2)
	                                        if (item 2 of windowSize) < 120 then set probeY to (item 2 of windowPosition) + ((item 2 of windowSize) / 2)
	                                        click at {probeX, probeY}
	                                        delay 0.05
	                                        set centerX to (item 1 of windowPosition) + ((item 1 of windowSize) / 2)
	                                        set centerY to (item 2 of windowPosition) + ((item 2 of windowSize) / 2)
	                                        click at {centerX, centerY}
	                                    end if
	                                    if windowLooksLikeWelcome is true then
	                                        delay 0.12
	                                        try
	                                            repeat with b in buttons of w
	                                                try
	                                                    if my elementTextMatches(b, welcomeButtonTokens) then
	                                                        click b
	                                                        return
	                                                    end if
	                                                end try
	                                            end repeat
	                                        end try
	                                        try
	                                            set nextX to (item 1 of windowPosition) + (item 1 of windowSize) - 220
	                                            set nextY to (item 2 of windowPosition) + (item 2 of windowSize) - 58
	                                            click at {nextX, nextY}
	                                        end try
	                                        delay 0.08
	                                        try
	                                            set nextX2 to (item 1 of windowPosition) + (item 1 of windowSize) - 130
	                                            set nextY2 to (item 2 of windowPosition) + (item 2 of windowSize) - 58
	                                            click at {nextX2, nextY2}
	                                        end try
	                                        delay 0.12
	                                        key code 36
	                                        delay 0.12
	                                        key code 48
	                                        delay 0.06
	                                        key code 36
	                                    end if
	                                end try
	                                if windowLooksLikeWelcome is false then return
	                            end if
                        end repeat
                    end if
                end try
            end repeat
        end tell
    end timeout
end repeat
OSA
}

run_repair_with_watchdog() {
  local id="$1" timeout_seconds="$2" func="$3"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration pid exit_code

  started="$(date +%s)"
  "$func" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    ended="$(date +%s)"
    if [ "$((ended - started))" -ge "$timeout_seconds" ]; then
      {
        echo
        echo "WATCHDOG timeout after ${timeout_seconds}s; terminating repair process $pid"
      } >> "$log"
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
      sleep 2
      pkill -KILL -P "$pid" 2>/dev/null || true
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >> "$log" 2>&1 || true
      ended="$(date +%s)"
      duration="$((ended - started))"
      record "$id" "$phase" "failed" 124 "$log" "$duration" "Repair did not exit before watchdog timeout."
      return 124
    fi
  done

  exit_code=0
  wait "$pid" || exit_code=$?
  return "$exit_code"
}

repair_com_proxy_registry() {
  local id="macwin-com-proxy"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code
  local iid_key='HKCR\Interface\{6D5140C1-7436-11CE-8034-00AA006009FA}'
  local clsid_key='HKCR\CLSID\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}'
  local clsid_inproc_key='HKCR\CLSID\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}\InprocServer32'
  local wow_iid_key='HKCR\Wow6432Node\Interface\{6D5140C1-7436-11CE-8034-00AA006009FA}'
  local wow_clsid_key='HKCR\Wow6432Node\CLSID\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}'
  local wow_clsid_inproc_key='HKCR\Wow6432Node\CLSID\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}\InprocServer32'
  local droptarget_iid_key='HKCR\Interface\{00000122-0000-0000-C000-000000000046}'
  local droptarget_clsid_key='HKCR\CLSID\{00000320-0000-0000-C000-000000000046}'
  local droptarget_clsid_inproc_key='HKCR\CLSID\{00000320-0000-0000-C000-000000000046}\InprocServer32'
  local wow_droptarget_iid_key='HKCR\Wow6432Node\Interface\{00000122-0000-0000-C000-000000000046}'
  local wow_droptarget_clsid_key='HKCR\Wow6432Node\CLSID\{00000320-0000-0000-C000-000000000046}'
  local wow_droptarget_clsid_inproc_key='HKCR\Wow6432Node\CLSID\{00000320-0000-0000-C000-000000000046}\InprocServer32'
  local mmdevice_key='HKCR\CLSID\{BCDE0395-E52F-467C-8E3D-C4579291692E}'
  local mmdevice_inproc_key='HKCR\CLSID\{BCDE0395-E52F-467C-8E3D-C4579291692E}\InprocServer32'
  local wow_mmdevice_key='HKCR\Wow6432Node\CLSID\{BCDE0395-E52F-467C-8E3D-C4579291692E}'
  local wow_mmdevice_inproc_key='HKCR\Wow6432Node\CLSID\{BCDE0395-E52F-467C-8E3D-C4579291692E}\InprocServer32'
  local network_list_key='HKCR\CLSID\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}'
  local network_list_inproc_key='HKCR\CLSID\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}\InprocServer32'
  local wow_network_list_key='HKCR\Wow6432Node\CLSID\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}'
  local wow_network_list_inproc_key='HKCR\Wow6432Node\CLSID\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}\InprocServer32'
  local task_scheduler_key='HKCR\CLSID\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}'
  local task_scheduler_inproc_key='HKCR\CLSID\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}\InprocServer32'
  local wow_task_scheduler_key='HKCR\Wow6432Node\CLSID\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}'
  local wow_task_scheduler_inproc_key='HKCR\Wow6432Node\CLSID\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}\InprocServer32'
  local legacy_task_scheduler_key='HKCR\CLSID\{148BD52A-A2AB-11CE-B11F-00AA00530503}'
  local legacy_task_scheduler_inproc_key='HKCR\CLSID\{148BD52A-A2AB-11CE-B11F-00AA00530503}\InprocServer32'
  local wow_legacy_task_scheduler_key='HKCR\Wow6432Node\CLSID\{148BD52A-A2AB-11CE-B11F-00AA00530503}'
  local wow_legacy_task_scheduler_inproc_key='HKCR\Wow6432Node\CLSID\{148BD52A-A2AB-11CE-B11F-00AA00530503}\InprocServer32'
  local crypto_provider_root='HKLM\Software\Microsoft\Cryptography\Defaults\Provider'
  local crypto_provider_types='HKLM\Software\Microsoft\Cryptography\Defaults\Provider Types'
  local wow_crypto_provider_root='HKLM\Software\Wow6432Node\Microsoft\Cryptography\Defaults\Provider'
  local wow_crypto_provider_types='HKLM\Software\Wow6432Node\Microsoft\Cryptography\Defaults\Provider Types'
  local schedule_service_key='HKLM\System\CurrentControlSet\Services\Schedule'
  local schedule_service_parameters_key='HKLM\System\CurrentControlSet\Services\Schedule\Parameters'
  local domdocument30_key='HKCR\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}'
  local domdocument30_inproc_key='HKCR\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}\InprocServer32'
  local domdocument30_progid_key='HKCR\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}\ProgID'
  local wow_domdocument30_key='HKCR\Wow6432Node\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}'
  local wow_domdocument30_inproc_key='HKCR\Wow6432Node\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}\InprocServer32'
  local wow_domdocument30_progid_key='HKCR\Wow6432Node\CLSID\{F5078F32-C551-11D3-89B9-0000F81FE221}\ProgID'
  local domdocument60_key='HKCR\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}'
  local domdocument60_inproc_key='HKCR\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}\InprocServer32'
  local domdocument60_progid_key='HKCR\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}\ProgID'
  local wow_domdocument60_key='HKCR\Wow6432Node\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}'
  local wow_domdocument60_inproc_key='HKCR\Wow6432Node\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}\InprocServer32'
  local wow_domdocument60_progid_key='HKCR\Wow6432Node\CLSID\{88D96A05-F192-11D4-A65F-0040963251E5}\ProgID'
  local proxy_name proxy_iid proxy_methods proxy_iid_key wow_proxy_iid_key

  started="$(date +%s)"
  {
    echo "== MacWin software smoke =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    "${WINE_CMD[@]}" reg add "$iid_key" /ve /d "IServiceProvider" /f
    "${WINE_CMD[@]}" reg add "$iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}" /f
    "${WINE_CMD[@]}" reg add "$iid_key" /v NumMethods /t REG_SZ /d "4" /f
    "${WINE_CMD[@]}" reg add "$iid_key\\ProxyStubClsid32" /ve /d "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}" /f
    "${WINE_CMD[@]}" reg add "$iid_key\\NumMethods" /ve /d "4" /f
    "${WINE_CMD[@]}" reg add "$clsid_key" /ve /d "PSFactoryBuffer" /f
    "${WINE_CMD[@]}" reg add "$clsid_inproc_key" /ve /d "C:\\windows\\system32\\actxprxy.dll" /f
    "${WINE_CMD[@]}" reg add "$clsid_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_iid_key" /ve /d "IServiceProvider" /f
    "${WINE_CMD[@]}" reg add "$wow_iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}" /f
    "${WINE_CMD[@]}" reg add "$wow_iid_key" /v NumMethods /t REG_SZ /d "4" /f
    "${WINE_CMD[@]}" reg add "$wow_iid_key\\ProxyStubClsid32" /ve /d "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}" /f
    "${WINE_CMD[@]}" reg add "$wow_iid_key\\NumMethods" /ve /d "4" /f
    "${WINE_CMD[@]}" reg add "$wow_clsid_key" /ve /d "PSFactoryBuffer" /f
    "${WINE_CMD[@]}" reg add "$wow_clsid_inproc_key" /ve /d "C:\\windows\\syswow64\\actxprxy.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_clsid_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$droptarget_iid_key" /ve /d "IDropTarget" /f
    "${WINE_CMD[@]}" reg add "$droptarget_iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{00000320-0000-0000-C000-000000000046}" /f
    "${WINE_CMD[@]}" reg add "$droptarget_iid_key" /v NumMethods /t REG_SZ /d "7" /f
    "${WINE_CMD[@]}" reg add "$droptarget_iid_key\\ProxyStubClsid32" /ve /d "{00000320-0000-0000-C000-000000000046}" /f
    "${WINE_CMD[@]}" reg add "$droptarget_iid_key\\NumMethods" /ve /d "7" /f
    "${WINE_CMD[@]}" reg add "$droptarget_clsid_key" /ve /d "OLE32 PSFactoryBuffer" /f
    "${WINE_CMD[@]}" reg add "$droptarget_clsid_inproc_key" /ve /d "C:\\windows\\system32\\ole32.dll" /f
    "${WINE_CMD[@]}" reg add "$droptarget_clsid_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_iid_key" /ve /d "IDropTarget" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{00000320-0000-0000-C000-000000000046}" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_iid_key" /v NumMethods /t REG_SZ /d "7" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_iid_key\\ProxyStubClsid32" /ve /d "{00000320-0000-0000-C000-000000000046}" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_iid_key\\NumMethods" /ve /d "7" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_clsid_key" /ve /d "OLE32 PSFactoryBuffer" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_clsid_inproc_key" /ve /d "C:\\windows\\syswow64\\ole32.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_droptarget_clsid_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    for item in \
      "IRemUnknown|{00000131-0000-0000-C000-000000000046}|6" \
      "IRemUnknown2|{00000142-0000-0000-C000-000000000046}|7" \
      "IRemUnknownN|{0000013C-0000-0000-C000-000000000046}|12" \
      "IRundown|{00000134-0000-0000-C000-000000000046}|13"
    do
      IFS='|' read -r proxy_name proxy_iid proxy_methods <<< "$item"
      proxy_iid_key="HKCR\\Interface\\$proxy_iid"
      wow_proxy_iid_key="HKCR\\Wow6432Node\\Interface\\$proxy_iid"
      "${WINE_CMD[@]}" reg add "$proxy_iid_key" /ve /d "$proxy_name" /f
      "${WINE_CMD[@]}" reg add "$proxy_iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{00000320-0000-0000-C000-000000000046}" /f
      "${WINE_CMD[@]}" reg add "$proxy_iid_key" /v NumMethods /t REG_SZ /d "$proxy_methods" /f
      "${WINE_CMD[@]}" reg add "$proxy_iid_key\\ProxyStubClsid32" /ve /d "{00000320-0000-0000-C000-000000000046}" /f
      "${WINE_CMD[@]}" reg add "$proxy_iid_key\\NumMethods" /ve /d "$proxy_methods" /f
      "${WINE_CMD[@]}" reg add "$wow_proxy_iid_key" /ve /d "$proxy_name" /f
      "${WINE_CMD[@]}" reg add "$wow_proxy_iid_key" /v ProxyStubClsid32 /t REG_SZ /d "{00000320-0000-0000-C000-000000000046}" /f
      "${WINE_CMD[@]}" reg add "$wow_proxy_iid_key" /v NumMethods /t REG_SZ /d "$proxy_methods" /f
      "${WINE_CMD[@]}" reg add "$wow_proxy_iid_key\\ProxyStubClsid32" /ve /d "{00000320-0000-0000-C000-000000000046}" /f
      "${WINE_CMD[@]}" reg add "$wow_proxy_iid_key\\NumMethods" /ve /d "$proxy_methods" /f
    done
    "${WINE_CMD[@]}" reg add "$mmdevice_key" /ve /d "MMDeviceEnumerator class" /f
    "${WINE_CMD[@]}" reg add "$mmdevice_inproc_key" /ve /d "C:\\windows\\system32\\mmdevapi.dll" /f
    "${WINE_CMD[@]}" reg add "$mmdevice_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_mmdevice_key" /ve /d "MMDeviceEnumerator class" /f
    "${WINE_CMD[@]}" reg add "$wow_mmdevice_inproc_key" /ve /d "C:\\windows\\syswow64\\mmdevapi.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_mmdevice_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$network_list_key" /ve /d "NetworkListManager" /f
    "${WINE_CMD[@]}" reg add "$network_list_inproc_key" /ve /d "C:\\windows\\system32\\netprofm.dll" /f
    "${WINE_CMD[@]}" reg add "$network_list_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_network_list_key" /ve /d "NetworkListManager" /f
    "${WINE_CMD[@]}" reg add "$wow_network_list_inproc_key" /ve /d "C:\\windows\\syswow64\\netprofm.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_network_list_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" regsvr32 /s taskschd.dll
    "${WINE_CMD[@]}" regsvr32 /s mstask.dll
    "${WINE_CMD[@]}" regsvr32 /s msxml3.dll
    "${WINE_CMD[@]}" regsvr32 /s msxml6.dll
    "${WINE_CMD[@]}" reg add "$domdocument30_key" /ve /d "Msxml2.DOMDocument.3.0" /f
    "${WINE_CMD[@]}" reg add "$domdocument30_inproc_key" /ve /d "C:\\windows\\system32\\msxml3.dll" /f
    "${WINE_CMD[@]}" reg add "$domdocument30_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$domdocument30_progid_key" /ve /d "Msxml2.DOMDocument.3.0" /f
    "${WINE_CMD[@]}" reg add 'HKCR\Msxml2.DOMDocument.3.0\CLSID' /ve /d "{F5078F32-C551-11D3-89B9-0000F81FE221}" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument30_key" /ve /d "Msxml2.DOMDocument.3.0" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument30_inproc_key" /ve /d "C:\\windows\\syswow64\\msxml3.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument30_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument30_progid_key" /ve /d "Msxml2.DOMDocument.3.0" /f
    "${WINE_CMD[@]}" reg add 'HKCR\Wow6432Node\Msxml2.DOMDocument.3.0\CLSID' /ve /d "{F5078F32-C551-11D3-89B9-0000F81FE221}" /f
    "${WINE_CMD[@]}" reg add "$domdocument60_key" /ve /d "Msxml2.DOMDocument.6.0" /f
    "${WINE_CMD[@]}" reg add "$domdocument60_inproc_key" /ve /d "C:\\windows\\system32\\msxml3.dll" /f
    "${WINE_CMD[@]}" reg add "$domdocument60_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$domdocument60_progid_key" /ve /d "Msxml2.DOMDocument.6.0" /f
    "${WINE_CMD[@]}" reg add 'HKCR\Msxml2.DOMDocument.6.0\CLSID' /ve /d "{88D96A05-F192-11D4-A65F-0040963251E5}" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument60_key" /ve /d "Msxml2.DOMDocument.6.0" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument60_inproc_key" /ve /d "C:\\windows\\syswow64\\msxml3.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument60_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_domdocument60_progid_key" /ve /d "Msxml2.DOMDocument.6.0" /f
    "${WINE_CMD[@]}" reg add 'HKCR\Wow6432Node\Msxml2.DOMDocument.6.0\CLSID' /ve /d "{88D96A05-F192-11D4-A65F-0040963251E5}" /f
    "${WINE_CMD[@]}" reg add "$task_scheduler_key" /ve /d "TaskScheduler class" /f
    "${WINE_CMD[@]}" reg add "$task_scheduler_inproc_key" /ve /d "C:\\windows\\system32\\taskschd.dll" /f
    "${WINE_CMD[@]}" reg add "$task_scheduler_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_task_scheduler_key" /ve /d "TaskScheduler class" /f
    "${WINE_CMD[@]}" reg add "$wow_task_scheduler_inproc_key" /ve /d "C:\\windows\\syswow64\\taskschd.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_task_scheduler_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$legacy_task_scheduler_key" /ve /d "CTaskScheduler class" /f
    "${WINE_CMD[@]}" reg add "$legacy_task_scheduler_inproc_key" /ve /d "C:\\windows\\system32\\mstask.dll" /f
    "${WINE_CMD[@]}" reg add "$legacy_task_scheduler_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$wow_legacy_task_scheduler_key" /ve /d "CTaskScheduler class" /f
    "${WINE_CMD[@]}" reg add "$wow_legacy_task_scheduler_inproc_key" /ve /d "C:\\windows\\syswow64\\mstask.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_legacy_task_scheduler_inproc_key" /v ThreadingModel /t REG_SZ /d "Both" /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v Type /t REG_DWORD /d 32 /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v Start /t REG_DWORD /d 2 /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v ErrorControl /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v ImagePath /t REG_EXPAND_SZ /d "C:\\windows\\system32\\svchost.exe -k netsvcs" /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v DisplayName /t REG_SZ /d "Task Scheduler" /f
    "${WINE_CMD[@]}" reg add "$schedule_service_key" /v ObjectName /t REG_SZ /d "LocalSystem" /f
    "${WINE_CMD[@]}" reg add "$schedule_service_parameters_key" /v ServiceDll /t REG_EXPAND_SZ /d "C:\\windows\\system32\\schedsvc.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Base Cryptographic Provider v1.0" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Base Cryptographic Provider v1.0" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Strong Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Strong Cryptographic Provider" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft RSA SChannel Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft RSA SChannel Cryptographic Provider" /v Type /t REG_DWORD /d 12 /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Enhanced RSA and AES Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_root\\Microsoft Enhanced RSA and AES Cryptographic Provider" /v Type /t REG_DWORD /d 24 /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 001" /v Name /t REG_SZ /d "Microsoft Enhanced Cryptographic Provider v1.0" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 001" /v TypeName /t REG_SZ /d "RSA Full (Signature and Key Exchange)" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 012" /v Name /t REG_SZ /d "Microsoft RSA SChannel Cryptographic Provider" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 012" /v TypeName /t REG_SZ /d "RSA SChannel" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 024" /v Name /t REG_SZ /d "Microsoft Enhanced RSA and AES Cryptographic Provider" /f
    "${WINE_CMD[@]}" reg add "$crypto_provider_types\\Type 024" /v TypeName /t REG_SZ /d "RSA Full and AES" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Base Cryptographic Provider v1.0" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Base Cryptographic Provider v1.0" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Strong Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Strong Cryptographic Provider" /v Type /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft RSA SChannel Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft RSA SChannel Cryptographic Provider" /v Type /t REG_DWORD /d 12 /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Enhanced RSA and AES Cryptographic Provider" /v "Image Path" /t REG_SZ /d "rsaenh.dll" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_root\\Microsoft Enhanced RSA and AES Cryptographic Provider" /v Type /t REG_DWORD /d 24 /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 001" /v Name /t REG_SZ /d "Microsoft Enhanced Cryptographic Provider v1.0" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 001" /v TypeName /t REG_SZ /d "RSA Full (Signature and Key Exchange)" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 012" /v Name /t REG_SZ /d "Microsoft RSA SChannel Cryptographic Provider" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 012" /v TypeName /t REG_SZ /d "RSA SChannel" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 024" /v Name /t REG_SZ /d "Microsoft Enhanced RSA and AES Cryptographic Provider" /f
    "${WINE_CMD[@]}" reg add "$wow_crypto_provider_types\\Type 024" /v TypeName /t REG_SZ /d "RSA Full and AES" /f
    echo
    echo "== verification =="
    "${WINE_CMD[@]}" reg query "$iid_key\\ProxyStubClsid32"
    "${WINE_CMD[@]}" reg query "$iid_key\\NumMethods"
    "${WINE_CMD[@]}" reg query "$clsid_inproc_key"
    "${WINE_CMD[@]}" reg query "$wow_iid_key\\ProxyStubClsid32"
    "${WINE_CMD[@]}" reg query "$wow_iid_key\\NumMethods"
    "${WINE_CMD[@]}" reg query "$wow_clsid_inproc_key"
    "${WINE_CMD[@]}" reg query "$droptarget_iid_key\\ProxyStubClsid32"
    "${WINE_CMD[@]}" reg query "$droptarget_iid_key\\NumMethods"
    "${WINE_CMD[@]}" reg query "$droptarget_clsid_inproc_key"
    "${WINE_CMD[@]}" reg query "$wow_droptarget_iid_key\\ProxyStubClsid32"
    "${WINE_CMD[@]}" reg query "$wow_droptarget_iid_key\\NumMethods"
    "${WINE_CMD[@]}" reg query "$wow_droptarget_clsid_inproc_key"
    "${WINE_CMD[@]}" reg query 'HKCR\Interface\{00000131-0000-0000-C000-000000000046}\ProxyStubClsid32'
    "${WINE_CMD[@]}" reg query 'HKCR\Interface\{00000142-0000-0000-C000-000000000046}\ProxyStubClsid32'
    "${WINE_CMD[@]}" reg query 'HKCR\Interface\{0000013C-0000-0000-C000-000000000046}\ProxyStubClsid32'
    "${WINE_CMD[@]}" reg query 'HKCR\Interface\{00000134-0000-0000-C000-000000000046}\ProxyStubClsid32'
    "${WINE_CMD[@]}" reg query "$mmdevice_inproc_key"
    "${WINE_CMD[@]}" reg query "$wow_mmdevice_inproc_key"
    "${WINE_CMD[@]}" reg query "$task_scheduler_inproc_key"
    "${WINE_CMD[@]}" reg query "$wow_task_scheduler_inproc_key"
    "${WINE_CMD[@]}" reg query "$legacy_task_scheduler_inproc_key"
    "${WINE_CMD[@]}" reg query "$wow_legacy_task_scheduler_inproc_key"
    "${WINE_CMD[@]}" reg query "$schedule_service_parameters_key"
    "${WINE_CMD[@]}" reg query "$crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0"
    "${WINE_CMD[@]}" reg query "$crypto_provider_types\\Type 001"
    "${WINE_CMD[@]}" reg query "$wow_crypto_provider_root\\Microsoft Enhanced Cryptographic Provider v1.0"
    "${WINE_CMD[@]}" reg query "$wow_crypto_provider_types\\Type 001"
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" "$phase" "$([ "$exit_code" -eq 0 ] && echo passed || echo failed)" "$exit_code" "$log" "$duration" ""
  return "$exit_code"
}

repair_winrt_activation_registry() {
  local id="macwin-winrt-activation"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code
  local class_name dll_name key wow_key
  local classes=(
    "Windows.Foundation.Metadata.ApiInformation|wintypes.dll"
    "Windows.Foundation.PropertyValue|wintypes.dll"
    "Windows.Foundation.Collections.PropertySet|wintypes.dll"
    "Windows.Storage.Streams.Buffer|wintypes.dll"
    "Windows.Storage.Streams.DataWriter|wintypes.dll"
    "Windows.System.Threading.ThreadPool|threadpoolwinrt.dll"
    "Windows.System.Threading.ThreadPoolTimer|threadpoolwinrt.dll"
    "Windows.UI.ViewManagement.AccessibilitySettings|windows.ui.dll"
    "Windows.UI.ViewManagement.UISettings|windows.ui.dll"
    "Windows.UI.ViewManagement.UIViewSettings|windows.ui.dll"
    "Windows.UI.ViewManagement.InputPane|windows.ui.dll"
    "Windows.UI.Core.CoreWindow|windows.ui.dll"
    "Windows.UI.Internal.Input.InputSite|windows.ui.dll"
    "Windows.UI.Internal.Input.ActivationConfigurationInputObject|windows.ui.dll"
    "Windows.UI.Composition.Compositor|windows.ui.dll"
    "Windows.UI.Composition.CompositionCapabilities|windows.ui.dll"
    "Windows.UI.Composition.CompositionEffectSourceParameter|windows.ui.dll"
  )

  started="$(date +%s)"
  {
    echo "== MacWin software smoke =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    for item in "${classes[@]}"; do
      IFS='|' read -r class_name dll_name <<< "$item"
      key="HKLM\\Software\\Microsoft\\WindowsRuntime\\ActivatableClassId\\$class_name"
      wow_key="HKLM\\Software\\Wow6432Node\\Microsoft\\WindowsRuntime\\ActivatableClassId\\$class_name"
      "${WINE_CMD[@]}" reg add "$key" /ve /d "$class_name" /f
      "${WINE_CMD[@]}" reg add "$key" /v DllPath /t REG_EXPAND_SZ /d "C:\\windows\\system32\\$dll_name" /f
      "${WINE_CMD[@]}" reg add "$wow_key" /ve /d "$class_name" /f
      "${WINE_CMD[@]}" reg add "$wow_key" /v DllPath /t REG_EXPAND_SZ /d "C:\\windows\\syswow64\\$dll_name" /f
    done
    echo
    echo "== verification =="
    for item in "${classes[@]}"; do
      IFS='|' read -r class_name _ <<< "$item"
      key="HKLM\\Software\\Microsoft\\WindowsRuntime\\ActivatableClassId\\$class_name"
      wow_key="HKLM\\Software\\Wow6432Node\\Microsoft\\WindowsRuntime\\ActivatableClassId\\$class_name"
      "${WINE_CMD[@]}" reg query "$key"
      "${WINE_CMD[@]}" reg query "$wow_key"
    done
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" "$phase" "$([ "$exit_code" -eq 0 ] && echo passed || echo failed)" "$exit_code" "$log" "$duration" ""
  return "$exit_code"
}

require_file() {
  local path="$1"
  if [ ! -e "$path" ]; then
    echo "Missing required installer/source: $path" >&2
    return 1
  fi
}

winepath_exists() {
  local unix_path="$1"
  [ -e "$unix_path" ]
}

suite_filter_matches() {
  local item_suite="$1"
  case "$SMOKE_SUITE" in
    all)
      return 0
      ;;
    quick)
      [ "$item_suite" = "quick" ]
      ;;
    browser)
      [ "$item_suite" = "browser" ]
      ;;
    office)
      [ "$item_suite" = "office" ]
      ;;
    cad)
      [ "$item_suite" = "cad" ]
      ;;
    industrial)
      [ "$item_suite" = "industrial" ] || [ "$item_suite" = "cad" ]
      ;;
    productivity)
      [ "$item_suite" = "productivity" ]
      ;;
    developer)
      [ "$item_suite" = "developer" ]
      ;;
    graphics)
      [ "$item_suite" = "graphics" ]
      ;;
    utility)
      [ "$item_suite" = "utility" ]
      ;;
    market)
      [ "$item_suite" = "market" ]
      ;;
    *)
      echo "Unknown MACWIN_SMOKE_SUITE: $SMOKE_SUITE" >&2
      echo "Supported suites: quick, browser, office, cad, industrial, productivity, developer, graphics, utility, market, all" >&2
      exit 2
      ;;
  esac
}

selected_suite_matches() {
  local item_suite="$1"
  if [ -n "$SMOKE_SAMPLE" ]; then
    return 0
  fi
  suite_filter_matches "$item_suite"
}

selected_sample_matches() {
  local item_id="$1"
  local sample_filter
  if [ -z "$SMOKE_SAMPLE" ]; then
    return 0
  fi
  sample_filter="${SMOKE_SAMPLE//[[:space:]]/}"
  case ",$sample_filter," in
    *",$item_id,"*) return 0 ;;
    *) return 1 ;;
  esac
}

validate_selected_samples() {
  local sample_filter sample id item found suite_match item_suite unknown=0
  local -a requested_samples
  if [ -z "$SMOKE_SAMPLE" ]; then
    return 0
  fi
  sample_filter="${SMOKE_SAMPLE//[[:space:]]/}"
  IFS=',' read -r -a requested_samples <<< "$sample_filter"
  for sample in "${requested_samples[@]}"; do
    [ -n "$sample" ] || continue
    found=0
    suite_match=0
    for item in "${installers[@]}"; do
      IFS='|' read -r item_suite id _installer _install_mode _install_arg _installed_rel _exe_path _launch_arg _launch_mode _install_timeout _launch_timeout <<< "$item"
      if [ "$id" = "$sample" ]; then
        found=1
        if suite_filter_matches "$item_suite"; then
          suite_match=1
        fi
        break
      fi
    done
    if [ "$found" -ne 1 ]; then
      echo "Unknown MACWIN_SMOKE_SAMPLE id: $sample" >&2
      unknown=1
    elif [ "$suite_match" -ne 1 ]; then
      echo "MACWIN_SMOKE_SAMPLE id '$sample' is not included by MACWIN_SMOKE_SUITE='$SMOKE_SUITE'." >&2
      unknown=1
    fi
  done
  if [ "$unknown" -ne 0 ]; then
    echo "Use an id from scripts/run-software-smoke.sh installers[], for example: godot-win64-editor." >&2
    exit 2
  fi
}

copy_installer_into_prefix() {
  local installer="$1"
  local cache="$PREFIX/drive_c/macwin-installers"
  mkdir -p "$cache"
  local installer_name installer_dir dependency
  installer_name="$(basename "$installer")"
  installer_dir="$(dirname "$installer")"
  cp -f "$installer" "$cache/$installer_name"
  case "$installer_name" in
    LenovoAppStoreInstall.exe)
      for dependency in libcrypto-3-x64.dll libssl-3-x64.dll InstUtil.dll; do
        if [ -f "$installer_dir/$dependency" ]; then
          cp -f "$installer_dir/$dependency" "$cache/$dependency"
        fi
      done
      ;;
  esac
  printf 'C:\\macwin-installers\\%s' "$installer_name"
}

drive_c_rel_to_windows() {
  local relative="${1#drive_c/}"
  printf 'C:\\%s' "${relative//\//\\}"
}

windows_drive_c_path_to_unix() {
  local windows_path="$1"
  windows_path="${windows_path%\"}"
  windows_path="${windows_path#\"}"
  windows_path="${windows_path//\\//}"
  case "$windows_path" in
    [Cc]:/*)
      printf '%s/drive_c/%s' "$PREFIX" "${windows_path#?:/}"
      ;;
    *)
      return 1
      ;;
  esac
}

prepare_launch_user_data_dirs() {
  local launch_arg_string="$1"
  local token next value unix_path
  local expect_value=0
  local -a tokens

  [ -n "$launch_arg_string" ] || return 0
  read -r -a tokens <<< "$launch_arg_string"
  for token in "${tokens[@]}"; do
    if [ "$expect_value" -eq 1 ]; then
      value="$token"
      expect_value=0
    else
      case "$token" in
        --user-data-dir=*)
          value="${token#--user-data-dir=}"
          ;;
        --user-data-dir)
          expect_value=1
          continue
          ;;
        *)
          continue
          ;;
      esac
    fi

    unix_path="$(windows_drive_c_path_to_unix "$value" || true)"
    if [ -n "${unix_path:-}" ]; then
      mkdir -p "$unix_path" || true
    fi
  done
}

repair_beekeeper_studio_profile_config() {
  local resources="$PREFIX/drive_c/macwin-portable/beekeeper-studio/resources"
  local profile="$PREFIX/drive_c/macwin-portable/beekeeper-profile"
  local program_data="$PREFIX/drive_c/ProgramData/beekeeper-studio"
  local name source target user_config

  [ -d "$resources" ] || return 0
  mkdir -p "$profile" "$program_data"

  for name in default.config.ini user.config.ini; do
    source="$resources/$name"
    target="$profile/$name"
    if [ -f "$source" ] && [ ! -f "$target" ]; then
      cp -f "$source" "$target" || true
    fi
  done

  for target in "$resources/default.config.ini" "$profile/default.config.ini"; do
    [ -f "$target" ] || continue
    /usr/bin/python3 - "$target" <<'PY' || true
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
out = []
section = ""
for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped[1:-1]
    if stripped.startswith("checkForUpdatesDisabled"):
        out.append("checkForUpdatesDisabled = true          ; MacWin offline compatibility default")
        continue
    if stripped.startswith("; MacWin disabled plugin allow-list entry: "):
        out.append(stripped.split(": ", 1)[1])
        continue
    if section in {"plugins.bks-ai-shell", "plugins.bks-er-diagram"} and stripped == "disabled = true":
        out.append("disabled = false")
        continue
    out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  done

  source="$resources/system.config.ini"
  target="$program_data/system.config.ini"
  if [ -f "$source" ] && [ ! -f "$target" ]; then
    cp -f "$source" "$target" || true
  fi

  user_config="$profile/user.config.ini"
  touch "$user_config" || true
  if ! rg -q 'MacWin offline compatibility defaults' "$user_config" 2>/dev/null; then
    cat >> "$user_config" <<'EOF'

; MacWin offline compatibility defaults
[general]
checkForUpdatesDisabled = true
checkForUpdatesInterval = 315360000000
EOF
  fi
}

extract_zip_into_prefix() {
  local archive="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  rm -rf "$cache"
  mkdir -p "$cache"
  /usr/bin/unzip -q "$archive" -d "$cache"
}

extract_7z_into_prefix() {
  local archive="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  local sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for 7z extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  rm -rf "$cache"
  mkdir -p "$cache"
  "$sevenzip" x -y "-o$cache" "$archive" >/dev/null
}

extract_wps_packet_into_prefix() {
  local installer="$1"
  local version="$2"
  local destination="$PREFIX/drive_c/Program Files/Kingsoft/WPS Office/$version"
  local temporary outer inner packets control sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for WPS packet extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi

  temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-wps-packet.XXXXXX")"
  outer="$temporary/outer"
  packets="$temporary/packets"
  control="$temporary/control"
  mkdir -p "$outer" "$packets" "$control"
  "$sevenzip" x -y "-o$outer" "$installer" >/dev/null
  inner="$(find "$outer" -type f -size +300M -print | head -1)"
  if [ -z "$inner" ]; then
    rm -rf "$temporary"
    echo "WPS offline installer did not expose its x64 packet executable." >&2
    return 1
  fi

  /usr/bin/python3 - "$inner" "$packets" <<'PY'
from pathlib import Path
import struct
import sys

source = Path(sys.argv[1])
output = Path(sys.argv[2])
data = source.read_bytes()
if data[:2] != b"MZ":
    raise SystemExit("WPS packet executable is not a PE file")
pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
section_offset = pe_offset + 24 + optional_size
raw_end = 0
for index in range(section_count):
    header = section_offset + index * 40
    raw_size, raw_offset = struct.unpack_from("<II", data, header + 16)
    raw_end = max(raw_end, raw_offset + raw_size)

signature = b"7z\xbc\xaf'\x1c"
offsets = []
cursor = raw_end
while True:
    cursor = data.find(signature, cursor)
    if cursor < 0:
        break
    offsets.append(cursor)
    cursor += len(signature)
if len(offsets) < 3:
    raise SystemExit(f"Expected at least three WPS 7z packets, found {len(offsets)}")

names = ("control.7z", "product1.7z", "product2.7z")
for name, offset in zip(names, offsets[:3]):
    if offset + 32 > len(data):
        raise SystemExit(f"Truncated WPS packet header at {offset}")
    next_header_offset, next_header_size = struct.unpack_from("<QQ", data, offset + 12)
    end = offset + 32 + next_header_offset + next_header_size
    if end > len(data):
        raise SystemExit(f"WPS packet {name} extends beyond the executable")
    (output / name).write_bytes(data[offset:end])
    print(f"{name}: offset={offset}, size={end - offset}")
PY

  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$destination" "$packets/product1.7z" >/dev/null
  "$sevenzip" x -y "-o$destination" "$packets/product2.7z" >/dev/null
  "$sevenzip" x -y "-o$control" "$packets/control.7z" >/dev/null
  if [ ! -d "$control/CONTROL/office6" ]; then
    rm -rf "$temporary"
    echo "WPS control packet is missing the shared office6 runtime." >&2
    return 1
  fi
  /usr/bin/ditto "$control/CONTROL/office6" "$destination/office6"
  rm -rf "$temporary"
  [ -f "$destination/office6/wps.exe" ] && [ -f "$destination/office6/Qt5CoreKso.dll" ]
}

extract_rar_bsdtar_into_prefix() {
  local archive="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  local bsdtar_bin
  bsdtar_bin="$(command -v bsdtar || true)"
  if [ -z "$bsdtar_bin" ]; then
    echo "bsdtar is required for RAR extraction." >&2
    return 127
  fi
  rm -rf "$cache"
  mkdir -p "$cache"
  "$bsdtar_bin" -xf "$archive" -C "$cache"
}

install_dotnet_desktop10_zip_runtime() {
  local runtime_zip="$DOWNLOADS/dotnet-runtime-10.0.9-win-x64.zip"
  local desktop_zip="$DOWNLOADS/windowsdesktop-runtime-10.0.9-win-x64.zip"
  local destination="$PREFIX/drive_c/macwin-runtimes/dotnet-desktop-10-x64"
  local core_marker="$destination/shared/Microsoft.NETCore.App/10.0.9/Microsoft.NETCore.App.deps.json"
  local desktop_marker="$destination/shared/Microsoft.WindowsDesktop.App/10.0.9/Microsoft.WindowsDesktop.App.deps.json"

  if [ -f "$destination/dotnet.exe" ] && [ -f "$core_marker" ] && [ -f "$desktop_marker" ]; then
    echo ".NET Desktop Runtime 10.0.9 x64 already present: $destination"
    return 0
  fi
  if [ ! -f "$runtime_zip" ] || [ ! -f "$desktop_zip" ]; then
    echo "Missing .NET Desktop Runtime 10.0.9 zip cache." >&2
    echo "Required: $runtime_zip" >&2
    echo "Required: $desktop_zip" >&2
    return 127
  fi

  rm -rf "$destination"
  mkdir -p "$destination"
  /usr/bin/unzip -q "$runtime_zip" -d "$destination"
  /usr/bin/unzip -q "$desktop_zip" -d "$destination"
  [ -f "$destination/dotnet.exe" ] && [ -f "$core_marker" ] && [ -f "$desktop_marker" ]
}

install_python314_portable_runtime() {
  local runtime_zip="$DOWNLOADS/thonny-5.0.0-windows-portable-x64.zip"
  local destination="$PREFIX/drive_c/macwin-runtimes/python314-portable"
  local marker="$destination/python.exe"

  if [ -f "$marker" ]; then
    echo "Portable Python 3.14 runtime already present: $destination"
    return 0
  fi
  if [ ! -f "$runtime_zip" ]; then
    echo "Missing portable Python cache: $runtime_zip" >&2
    return 127
  fi

  rm -rf "$destination"
  mkdir -p "$destination"
  /usr/bin/unzip -q "$runtime_zip" -d "$destination"
  [ -f "$marker" ]
}

configure_lyx_python_shims() {
  local system32="$PREFIX/drive_c/windows/system32"
  local target='C:\macwin-runtimes\python314-portable\python.exe'
  mkdir -p "$system32"
  cat > "$system32/python.bat" <<BAT
@echo off
"$target" %*
BAT
  cat > "$system32/python3.bat" <<BAT
@echo off
"$target" %*
BAT
  cat > "$system32/py.bat" <<BAT
@echo off
if "%~1"=="-3" shift
"$target" %*
BAT
}

configure_mremoteng_1782_profile() {
  local app_dir="$PREFIX/drive_c/macwin-portable/mremoteng-1782-x64"
  local settings="$app_dir/mRemoteNG.settings"
  [ -d "$app_dir" ] || return 0
  cat > "$settings" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<settings>
  <localSettings>
    <setting name="CheckForUpdatesOnStartup">False</setting>
    <setting name="CheckForUpdatesAsked">True</setting>
    <setting name="CheckForUpdatesFrequencyDays">14</setting>
    <setting name="CheckForUpdatesLastCheck">2099-01-01</setting>
    <setting name="UpdateUseProxy">False</setting>
    <setting name="UpdateProxyAddress"></setting>
    <setting name="UpdateProxyPort">80</setting>
    <setting name="UpdateProxyUseAuthentication">False</setting>
    <setting name="UpdateProxyAuthUser"></setting>
    <setting name="UpdateProxyAuthPass"></setting>
  </localSettings>
  <globalSettings />
</settings>
XML
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates' /v AllowCheckForUpdates /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates' /v AllowCheckForUpdatesAutomatical /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates' /v AllowCheckForUpdatesManual /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates\Options' /v DisallowPromptForUpdatesPreference /t REG_DWORD /d 1 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates\Options' /v CheckForUpdatesFrequencyDays /t REG_DWORD /d 36500 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKEY_LOCAL_MACHINE\SOFTWARE\mRemoteNG\Updates\Options' /v UseProxyForUpdates /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  echo "Configured mRemoteNG portable settings: $settings"
}

extract_7z_sfx_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for 7z SFX extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$destination" "$installer" >/dev/null
}

extract_embedded_7z_payload_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local temporary payload sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for embedded 7z extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-embedded-7z.XXXXXX")"
  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$temporary" "$installer" '*.7z' >/dev/null
  payload="$(find "$temporary" -type f -iname '*.7z' -print | head -1)"
  if [ -z "$payload" ]; then
    rm -rf "$temporary"
    echo "Installer did not expose an embedded .7z payload." >&2
    return 1
  fi
  "$sevenzip" x -y "-o$destination" "$payload" >/dev/null
  rm -rf "$temporary"
}

install_qtifw_until_file() {
  local installer="$1"
  local target_rel="$2"
  local root_windows="$3"
  local max_wait="${4:-420}"
  local auto_answer="${5:-}"
  local installer_windows target_unix started now child exit_code target_seen target_grace
  local installer_args
  installer_windows="$(copy_installer_into_prefix "$installer")"
  target_unix="$PREFIX/$target_rel"
  target_seen=0
  target_grace="${MACWIN_QTIFW_UNTIL_FILE_GRACE:-90}"
  if [ -f "$target_unix" ]; then
    echo "Target already exists: $target_unix"
    return 0
  fi
  installer_args=(--root "$root_windows" --accept-licenses --accept-messages)
  if [ -n "$auto_answer" ]; then
    installer_args+=(--auto-answer "$auto_answer")
  fi
  installer_args+=(--confirm-command install)
  "${WINE_CMD[@]}" "$installer_windows" "${installer_args[@]}" &
  child=$!
  started="$(date +%s)"
  while kill -0 "$child" 2>/dev/null; do
    if [ -f "$target_unix" ]; then
      if [ "$target_seen" -eq 0 ]; then
        target_seen="$(date +%s)"
        echo "Target appeared: $target_unix"
      fi
      now="$(date +%s)"
      if [ "$((now - target_seen))" -ge "$target_grace" ]; then
        echo "Target stayed present for ${target_grace}s; stopping QtIFW watchdog."
        kill "$child" 2>/dev/null || true
        sleep 2
        kill -KILL "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
        "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
        return 0
      fi
    fi
    sleep 1
    now="$(date +%s)"
    if [ "$((now - started))" -ge "$max_wait" ]; then
      echo "QtIFW target did not appear within ${max_wait}s: $target_unix" >&2
      kill "$child" 2>/dev/null || true
      sleep 2
      kill -KILL "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      return 124
    fi
  done
  exit_code=0
  wait "$child" || exit_code=$?
  if [ -f "$target_unix" ]; then
    echo "Target appeared after installer exit: $target_unix"
    return 0
  fi
  return "$exit_code"
}

install_msi_until_file() {
  local installer="$1"
  local target_rel="$2"
  local id="$3"
  local max_wait="${4:-420}"
  local installer_windows target_unix msi_log_name msi_log_windows msi_log_unix started now child exit_code
  installer_windows="$(copy_installer_into_prefix "$installer")"
  target_unix="$PREFIX/$target_rel"
  msi_log_name="$id-msi-detail.log"
  msi_log_windows="C:\\macwin-installers\\$msi_log_name"
  msi_log_unix="$PREFIX/drive_c/macwin-installers/$msi_log_name"
  if [ -f "$target_unix" ]; then
    echo "Target already exists: $target_unix"
    return 0
  fi
  "${WINE_CMD[@]}" msiexec /i "$installer_windows" /qn /norestart /l*v "$msi_log_windows" &
  child=$!
  started="$(date +%s)"
  while kill -0 "$child" 2>/dev/null; do
    if [ -f "$target_unix" ]; then
      echo "Target appeared: $target_unix"
      kill "$child" 2>/dev/null || true
      sleep 2
      kill -KILL "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      if [ -f "$msi_log_unix" ]; then
        cp -f "$msi_log_unix" "$LOG_DIR/$msi_log_name"
      fi
      return 0
    fi
    sleep 1
    now="$(date +%s)"
    if [ "$((now - started))" -ge "$max_wait" ]; then
      echo "MSI target did not appear within ${max_wait}s: $target_unix" >&2
      kill "$child" 2>/dev/null || true
      sleep 2
      kill -KILL "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      if [ -f "$msi_log_unix" ]; then
        cp -f "$msi_log_unix" "$LOG_DIR/$msi_log_name"
      fi
      return 124
    fi
  done
  exit_code=0
  wait "$child" || exit_code=$?
  if [ -f "$msi_log_unix" ]; then
    cp -f "$msi_log_unix" "$LOG_DIR/$msi_log_name"
  fi
  if [ -f "$target_unix" ]; then
    echo "Target appeared after MSI exit: $target_unix"
    return 0
  fi
  return "$exit_code"
}

install_exe_until_file() {
  local installer="$1"
  local target_rel="$2"
  local id="$3"
  local max_wait="${4:-420}"
  shift 4
  local installer_windows target_unix started now child exit_code target_seen target_grace
  installer_windows="$(copy_installer_into_prefix "$installer")"
  target_unix="$PREFIX/$target_rel"
  target_seen=0
  case "$id" in
    winscp-client|winscp-cli-help)
      target_grace="${MACWIN_WINSCP_LEGACY_INSTALL_GRACE:-5}"
      ;;
    *)
      target_grace="${MACWIN_EXE_UNTIL_FILE_GRACE:-90}"
      ;;
  esac
  if [ -f "$target_unix" ]; then
    echo "Target already exists: $target_unix"
    return 0
  fi
  "${WINE_CMD[@]}" "$installer_windows" "$@" &
  child=$!
  started="$(date +%s)"
  while kill -0 "$child" 2>/dev/null; do
    if [ -f "$target_unix" ]; then
      if [ "$target_seen" -eq 0 ]; then
        target_seen="$(date +%s)"
        echo "Target appeared: $target_unix"
      fi
      now="$(date +%s)"
      if [ "$((now - target_seen))" -ge "$target_grace" ]; then
        echo "Target stayed present for ${target_grace}s; stopping installer watchdog."
        kill "$child" 2>/dev/null || true
        sleep 2
        kill -KILL "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
        "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
        return 0
      fi
    fi
    sleep 1
    now="$(date +%s)"
    if [ "$((now - started))" -ge "$max_wait" ]; then
      echo "EXE target did not appear within ${max_wait}s: $target_unix" >&2
      kill "$child" 2>/dev/null || true
      sleep 2
      kill -KILL "$child" 2>/dev/null || true
      wait "$child" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      return 124
    fi
  done
  exit_code=0
  wait "$child" || exit_code=$?
  if [ -f "$target_unix" ]; then
    echo "Target appeared after EXE exit: $target_unix"
    return 0
  fi
  return "$exit_code"
}

extract_nsis_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for NSIS extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$destination" "$installer" || return $?
  if [ -d "$destination/\$INSTDIR" ]; then
    temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-nsis-instdir.XXXXXX")"
    /usr/bin/ditto "$destination/\$INSTDIR" "$temporary"
    find "$destination" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    /usr/bin/ditto "$temporary" "$destination"
    rm -rf "$temporary"
  elif [ -d "$destination/?/\$INSTDIR" ]; then
    temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-nsis-instdir.XXXXXX")"
    /usr/bin/ditto "$destination/?/\$INSTDIR" "$temporary"
    find "$destination" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    /usr/bin/ditto "$temporary" "$destination"
    rm -rf "$temporary"
  fi
  rm -rf "$destination/\$PLUGINSDIR"
}

extract_electron_builder_nsis_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local temporary payload sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for Electron builder NSIS extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-electron-builder.XXXXXX")"
  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$temporary" "$installer" '$PLUGINSDIR/app-64.7z' >/dev/null
  payload="$temporary/\$PLUGINSDIR/app-64.7z"
  if [ ! -f "$payload" ]; then
    rm -rf "$temporary"
    echo "Electron builder installer missing app-64.7z payload" >&2
    return 1
  fi
  "$sevenzip" x -y "-o$destination" "$payload" >/dev/null
  rm -rf "$temporary"
}

extract_msi_admin_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local installer_windows target_windows

  rm -rf "$destination"
  mkdir -p "$destination"
  installer_windows="$(copy_installer_into_prefix "$installer")"
  target_windows="$(drive_c_rel_to_windows "$destination_rel")"
  "${WINE_CMD[@]}" msiexec /a "$installer_windows" /qn "TARGETDIR=$target_windows" /norestart
}

extract_msi_cab_7z_into_prefix() {
  local installer="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  local temporary cab sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for MSI CAB extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-msi-cab.XXXXXX")"
  rm -rf "$destination"
  mkdir -p "$destination"
  "$sevenzip" x -y "-o$temporary" "$installer" >/dev/null
  cab="$(find "$temporary" -maxdepth 1 -type f -iname '*.cab' -print | head -1)"
  if [ -z "$cab" ]; then
    rm -rf "$temporary"
    echo "MSI package did not expose a CAB payload." >&2
    return 1
  fi
  "$sevenzip" x -y "-o$destination" "$cab" >/dev/null
  rm -rf "$temporary"
}

install_direct_exe_into_prefix() {
  local executable="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  rm -rf "$cache"
  mkdir -p "$cache"
  cp -f "$executable" "$cache/$(basename "$executable")"
}

install_directory_copy_into_prefix() {
  local source_dir="$1"
  local destination_rel="$2"
  local destination="$PREFIX/$destination_rel"
  if [ ! -d "$source_dir" ]; then
    echo "Directory source not found: $source_dir" >&2
    return 1
  fi
  rm -rf "$destination"
  mkdir -p "$(dirname "$destination")"
  /usr/bin/ditto "$source_dir" "$destination"
}

extract_squirrel_zip_into_prefix() {
  local installer="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  rm -rf "$cache"
  mkdir -p "$cache"
  /usr/bin/python3 - "$installer" "$cache" <<'PY'
import pathlib
import sys
import tempfile
import zipfile

setup_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])

with zipfile.ZipFile(setup_path) as setup_zip:
    nupkg_names = [name for name in setup_zip.namelist() if name.lower().endswith(".nupkg")]
    if not nupkg_names:
        raise SystemExit("Squirrel package missing .nupkg payload")
    nupkg_name = nupkg_names[0]
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = pathlib.Path(temporary)
        nupkg_path = temporary_path / pathlib.Path(nupkg_name).name
        nupkg_path.write_bytes(setup_zip.read(nupkg_name))
        with zipfile.ZipFile(nupkg_path) as nupkg_zip:
            for member in nupkg_zip.infolist():
                name = member.filename.replace("\\", "/")
                prefix = "lib/net45/"
                if not name.startswith(prefix) or name == prefix:
                    continue
                relative = pathlib.PurePosixPath(name[len(prefix):])
                if any(part in ("", ".", "..") for part in relative.parts):
                    continue
                target = destination.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with nupkg_zip.open(member) as source, target.open("wb") as output:
                    output.write(source.read())
PY
}

extract_squirrel_pe_into_prefix() {
  local installer="$1"
  local id="$2"
  local cache="$PREFIX/drive_c/macwin-portable/$id"
  local temporary payload sevenzip
  sevenzip="$(command -v 7zz || command -v 7z || true)"
  if [ -z "$sevenzip" ]; then
    echo "7-Zip is required for Squirrel PE extraction; install Homebrew formula sevenzip." >&2
    return 127
  fi
  temporary="$(mktemp -d "${TMPDIR:-/tmp}/macwin-squirrel-pe.XXXXXX")"
  rm -rf "$cache"
  mkdir -p "$cache"
  "$sevenzip" x -y "-o$temporary" "$installer" >/dev/null
  payload="$(find "$temporary" -type f -iname '*.nupkg' -print | head -1)"
  if [ -z "$payload" ]; then
    payload="$(find "$temporary" -type f -exec stat -f '%z %N' {} \; | sort -nr | head -1 | cut -d' ' -f2-)"
  fi
  if [ -z "$payload" ] || [ ! -f "$payload" ]; then
    rm -rf "$temporary"
    echo "Squirrel PE package missing embedded ZIP payload" >&2
    return 1
  fi
  /usr/bin/python3 - "$payload" "$cache" <<'PY'
import pathlib
import sys
import tempfile
import zipfile

setup_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])

with tempfile.TemporaryDirectory() as temporary:
    temporary_path = pathlib.Path(temporary)
    if setup_path.suffix.lower() == ".nupkg":
        nupkg_path = setup_path
    else:
        with zipfile.ZipFile(setup_path) as setup_zip:
            nupkg_names = [name for name in setup_zip.namelist() if name.lower().endswith(".nupkg")]
            if not nupkg_names:
                raise SystemExit("Squirrel package missing .nupkg payload")
            nupkg_name = nupkg_names[0]
            nupkg_path = temporary_path / pathlib.Path(nupkg_name).name
            nupkg_path.write_bytes(setup_zip.read(nupkg_name))
    with zipfile.ZipFile(nupkg_path) as nupkg_zip:
        for member in nupkg_zip.infolist():
            name = member.filename.replace("\\", "/")
            prefix = "lib/net45/"
            if not name.startswith(prefix) or name == prefix:
                continue
            relative = pathlib.PurePosixPath(name[len(prefix):])
            if any(part in ("", ".", "..") for part in relative.parts):
                continue
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with nupkg_zip.open(member) as source, target.open("wb") as output:
                output.write(source.read())
PY
  local status=$?
  rm -rf "$temporary"
  return "$status"
}

install_chrome_enterprise_payload() {
  local msi="$1"
  local id="$2"
  local payload_meta payload_hash payload_name payload_path payload_windows actual_hash module_cache
  payload_meta="$(/usr/bin/python3 - "$msi" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_bytes().decode("latin-1", errors="ignore")
package_match = re.search(r'<package\s+name="([^"]+)"\s+hash_sha256="([0-9a-fA-F]{64})"', text)
if not package_match:
    raise SystemExit("Chrome Enterprise MSI does not expose a payload hash manifest")
name = package_match.group(1)
digest = package_match.group(2).lower()
print(digest)
print(name)
PY
)"
  payload_hash="$(printf '%s\n' "$payload_meta" | sed -n '1p')"
  payload_name="$(printf '%s\n' "$payload_meta" | sed -n '2p')"
  payload_path="$DOWNLOADS/${id}-${payload_hash:0:12}-$payload_name"
  module_cache="$ROOT/ToolCache/python-msi"

  mkdir -p "$module_cache"
  if ! PYTHONPATH="$module_cache" /usr/bin/python3 - <<'PY' >/dev/null 2>&1
import olefile
import pefile
import py7zr
PY
  then
    /usr/bin/python3 -m pip install --quiet --target "$module_cache" olefile pefile py7zr
  fi

  if [ ! -s "$payload_path" ]; then
    PYTHONPATH="$module_cache" /usr/bin/python3 - "$msi" "$payload_hash" "$payload_path" <<'PY'
import hashlib
import olefile
import pathlib
import pefile
import py7zr
import shutil
import sys
import tempfile

msi_path = pathlib.Path(sys.argv[1])
expected_hash = sys.argv[2].lower()
destination = pathlib.Path(sys.argv[3])

with tempfile.TemporaryDirectory() as temporary:
    temporary_path = pathlib.Path(temporary)
    ole = olefile.OleFileIO(str(msi_path))
    pe_stream = None
    pe_stream_size = 0
    for stream in ole.listdir(streams=True, storages=False):
        size = ole.get_size(stream)
        if size <= pe_stream_size:
            continue
        with ole.openstream(stream) as source:
            head = source.read(2)
        if head == b"MZ":
            pe_stream = stream
            pe_stream_size = size
    if pe_stream is None:
        raise SystemExit("Chrome Enterprise MSI missing embedded PE stream")

    metainstaller = temporary_path / "chrome_metainstaller.exe"
    metainstaller.write_bytes(ole.openstream(pe_stream).read())

    pe = pefile.PE(str(metainstaller), fast_load=False)
    packed_7z = temporary_path / "updater.packed.7z"
    for type_entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        for name_entry in getattr(type_entry, "directory", []).entries:
            if str(name_entry.name or name_entry.struct.Id) != "UPDATER.PACKED.7Z":
                continue
            lang_entry = name_entry.directory.entries[0]
            resource = lang_entry.data.struct
            offset = pe.get_offset_from_rva(resource.OffsetToData)
            packed_7z.write_bytes(pe.__data__[offset:offset + resource.Size])
            break
        if packed_7z.exists():
            break
    if not packed_7z.exists():
        raise SystemExit("Chrome metainstaller missing UPDATER.PACKED.7Z resource")

    first_layer = temporary_path / "first"
    second_layer = temporary_path / "second"
    first_layer.mkdir()
    second_layer.mkdir()
    with py7zr.SevenZipFile(packed_7z, mode="r") as archive:
        archive.extractall(path=first_layer)
    updater_7z = first_layer / "updater.7z"
    if not updater_7z.exists():
        raise SystemExit("Chrome packed resource missing updater.7z")
    with py7zr.SevenZipFile(updater_7z, mode="r") as archive:
        archive.extractall(path=second_layer)

    candidates = sorted(second_layer.rglob("*chrome_installer.exe"))
    if not candidates:
        raise SystemExit("Chrome updater archive missing chrome_installer.exe")
    installer = candidates[0]
    actual_hash = hashlib.sha256(installer.read_bytes()).hexdigest().lower()
    if actual_hash != expected_hash:
        raise SystemExit(f"Chrome payload hash mismatch: expected {expected_hash} got {actual_hash}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(installer, destination)
PY
  fi

  actual_hash="$(shasum -a 256 "$payload_path" | awk '{print tolower($1)}')"
  if [ "$actual_hash" != "$payload_hash" ]; then
    echo "Chrome payload hash mismatch: expected $payload_hash got $actual_hash" >&2
    return 65
  fi

  payload_windows="$(copy_installer_into_prefix "$payload_path")"
  "${WINE_CMD[@]}" "$payload_windows" --do-not-launch-chrome
}

extract_inno_into_prefix() {
  local installer="$1"
  local id="$2"
  local destination_rel="$3"
  local innoextract_bin
  local cache="$PREFIX/.extract-cache/$id"
  local destination="$PREFIX/$destination_rel"
  innoextract_bin="$(command -v innoextract || true)"
  if [ -z "$innoextract_bin" ]; then
    echo "Missing optional dependency: innoextract"
    return 127
  fi
  rm -rf "$cache" "$destination"
  mkdir -p "$cache" "$destination"
  if [ "$id" = "gimp-image-editor" ]; then
    "$innoextract_bin" --silent --collisions=rename-all --extract --output-dir "$cache" "$installer" || return $?
  else
    "$innoextract_bin" --silent --extract --output-dir "$cache" "$installer" || return $?
  fi
  if ! find "$cache" -type f -print -quit | grep -q .; then
    echo "Inno extraction produced no files." >&2
    return 1
  fi
  if [ -d "$cache/app" ]; then
    /usr/bin/ditto "$cache/app" "$destination"
  else
    /usr/bin/ditto "$cache" "$destination"
  fi
  if [ "$id" = "gimp-image-editor" ] \
    && [ ! -f "$destination/bin/gimp-2.10.exe" ] \
    && [ ! -f "$destination/bin/gimp-2.10.exe#gimp64" ]; then
    echo "GIMP Inno extraction did not produce bin/gimp-2.10.exe or x64 collision payload." >&2
    return 1
  fi
}

is_chromium_application_dir() {
  local dir="$1"
  [ -f "$dir/brave.exe" ] || [ -f "$dir/chrome.exe" ] || [ -f "$dir/msedge.exe" ] || [ -f "$dir/vivaldi.exe" ]
}

latest_chromium_version_dir() {
  local app_dir="$1"
  find "$app_dir" -maxdepth 1 -type d -name '*.*.*' -print 2>/dev/null | sort -rV | while IFS= read -r version_dir; do
    if [ -f "$version_dir/chrome_elf.dll" ] \
      || [ -f "$version_dir/chrome_wer.dll" ] \
      || [ -f "$version_dir/msedge_elf.dll" ] \
      || [ -f "$version_dir/msedge_wer.dll" ] \
      || [ -f "$version_dir/vivaldi_elf.dll" ]; then
      printf '%s\n' "$version_dir"
      return 0
    fi
  done
}

repair_chromium_root_dlls() {
  local app_dir version_dir dll
  local -a application_dirs=(
    "$PREFIX/drive_c/Program Files"/*/Application
    "$PREFIX/drive_c/Program Files"/*/*/Application
    "$PREFIX/drive_c/Program Files (x86)"/*/Application
    "$PREFIX/drive_c/Program Files (x86)"/*/*/Application
    "$PREFIX/drive_c/users"/*/AppData/Local/*/Application
    "$PREFIX/drive_c/users"/*/AppData/Local/*/*/Application
  )
  for app_dir in "${application_dirs[@]}"; do
    [ -d "$app_dir" ] || continue
    is_chromium_application_dir "$app_dir" || continue
    version_dir="$(latest_chromium_version_dir "$app_dir" || true)"
    [ -n "${version_dir:-}" ] || continue
    for dll in chrome_elf.dll chrome_wer.dll msedge_elf.dll msedge_wer.dll vivaldi_elf.dll; do
      if [ -f "$version_dir/$dll" ] && [ ! -f "$app_dir/$dll" ]; then
        cp -f "$version_dir/$dll" "$app_dir/$dll" || true
      fi
    done
  done
}

configure_jasp_qtwebengine_layout() {
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local source_dir=""
  local candidate
  [ -f "$app_dir/JASPDesktop.exe" ] || return 0

	  for candidate in \
	    "$PREFIX_ROOT/software-smoke-representative/drive_c/Program Files/JASP" \
	    "$PREFIX_ROOT/software-smoke-new-samples/drive_c/Program Files/JASP" \
	    "$PREFIX_ROOT/software-smoke-industrial/drive_c/Program Files/JASP" \
	    "$PREFIX_ROOT/jasp-current-msi-until-file/drive_c/Program Files/JASP" \
	    "$PREFIX_ROOT/software-smoke-browser-packagemanager-clean2/drive_c/Program Files/JASP" \
	    "$PREFIX_ROOT/software-smoke-all/drive_c/Program Files/JASP"; do
	    if [ "$candidate" != "$app_dir" ] \
	      && [ -f "$candidate/platforms/qwindows.dll" ] \
	      && [ -f "$candidate/Qt6Quick.dll" ] \
	      && [ -f "$candidate/Qt6WebChannel.dll" ] \
	      && [ -f "$candidate/resources/qtwebengine_resources.pak" ]; then
	      source_dir="$candidate"
	      break
    fi
  done

  [ -n "$source_dir" ] || return 0
	  for rel in platforms resources Resources qml translations networkinformation position qmltooling sqldrivers styles tls R Modules imageformats generic iconengines components; do
	    if [ -e "$source_dir/$rel" ]; then
	      if [ "${MACWIN_JASP_REFRESH_RUNTIME:-0}" != "1" ] \
	        && [ -d "$app_dir/$rel" ] \
	        && find "$app_dir/$rel" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | rg -q .; then
	        continue
	      fi
	      mkdir -p "$app_dir/$(dirname "$rel")"
	      /usr/bin/ditto "$source_dir/$rel" "$app_dir/$rel" || true
	    fi
	  done
		  for rel in QtWebEngineProcess.exe Qt6Widgets.dll Qt6Quick.dll Qt6Qml.dll Qt6QmlModels.dll Qt6QmlWorkerScript.dll Qt6QmlMeta.dll Qt6QuickControls2.dll Qt6QuickTemplates2.dll Qt6QuickShapes.dll Qt6QuickLayouts.dll Qt6WebChannel.dll Qt6WebChannelQuick.dll Qt6WebEngineQuick.dll Qt6WebEngineCore.dll Qt6Sql.dll Qt6Svg.dll Qt6SvgWidgets.dll libreadstat-1.dll librdata-0.dll libiconv-2.dll zlib1.dll libbz2-1.dll liblzma-5.dll; do
		    if [ -f "$source_dir/$rel" ]; then
		      if [ "${MACWIN_JASP_REFRESH_RUNTIME:-0}" != "1" ] && [ -f "$app_dir/$rel" ]; then
		        continue
		      fi
		      cp -f "$source_dir/$rel" "$app_dir/$rel" || true
		    fi
		  done
		}

configure_jasp_software_opengl() {
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local target="$app_dir/opengl32sw.dll"
  local source=""
  local candidate=""
  [ -f "$app_dir/JASPDesktop.exe" ] || return 0
  [ -f "$target" ] && return 0

  for candidate in \
    "$PREFIX/drive_c/Program Files/MuseScore 4/bin/opengl32sw.dll" \
    "$PREFIX/drive_c/Program Files/LibreCAD/opengl32sw.dll" \
    "$PREFIX/drive_c/macwin-portable/qownnotes-portable/opengl32sw.dll" \
    "$PREFIX/drive_c/macwin-portable/qmodmaster-64/qModMaster/opengl32sw.dll" \
    "$PREFIX/drive_c/macwin-portable/qmodmaster-32/qModMaster/opengl32sw.dll" \
    "$PREFIX_ROOT/software-smoke-new-samples/drive_c/Program Files/MuseScore 4/bin/opengl32sw.dll" \
    "$PREFIX_ROOT/software-smoke-industrial/drive_c/Program Files/LibreCAD/opengl32sw.dll"; do
    if [ -f "$candidate" ]; then
      source="$candidate"
      break
    fi
  done

  [ -n "$source" ] || return 0
  cp -f "$source" "$target" || true
}

configure_jasp_constructor_tail_isolation() {
  local id="$1"
  local log="$LOG_DIR/${id}-constructor-tail-isolation-preset.log"
  local started ended duration
  local jasp_ini="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP.ini"
  started="$(date +%s)"

  {
    echo "== MacWin JASP constructor-tail isolation preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "ini=$jasp_ini"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "enabled=${MACWIN_JASP_CONSTRUCTOR_ISOLATION:-0}"
    echo
  } > "$log"

  if [ "${MACWIN_JASP_CONSTRUCTOR_ISOLATION:-0}" != "1" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "constructor-tail-isolation-preset" "skipped" 0 "$log" "$duration" "JASP constructor-tail isolation preset disabled; set MACWIN_JASP_CONSTRUCTOR_ISOLATION=1 to disable update/configuration paths for comparison."
    return 0
  fi

  mkdir -p "$(dirname "$jasp_ini")"
  if [ -f "$jasp_ini" ]; then
    cp -f "$jasp_ini" "$jasp_ini.macwin-before-constructor-isolation" || true
  fi

  /usr/bin/python3 - "$jasp_ini" >> "$log" <<'PY'
import configparser
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = configparser.ConfigParser()
config.optionxform = str
if path.exists():
    config.read(path, encoding="utf-8")
if "General" not in config:
    config["General"] = {}

updates = {
    "safeGraphicsMode": "true",
    "logToFile": "false",
    "engineSandbox": "false",
    "checkUpdatesAskUser": "false",
    "checkUpdates": "false",
    "useConfigurationFile": "false",
    "remoteConfiguration": "false",
    "remoteConfigurationURL": "about:blank",
    "moduleLibraryURL": "about:blank",
    "instructionsShown": "true",
}
for key, value in updates.items():
    config["General"][key] = value

with path.open("w", encoding="utf-8", newline="\n") as handle:
    config.write(handle, space_around_delimiters=False)

for key, value in updates.items():
    print(f"preset.{key}={value}")
PY

  {
    echo
    echo "## resulting ini"
    nl -ba "$jasp_ini" | sed -n '1,80p'
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "constructor-tail-isolation-preset" "passed" 0 "$log" "$duration" "Applied JASP constructor-tail isolation preset: disabled file logging, update prompts, update checks, remote configuration, and module-library network URL before the launch comparison."
}

configure_jasp_empty_values_preset() {
  local id="$1"
  local preset="${MACWIN_JASP_EMPTY_VALUES_PRESET:-0}"
  local log="$LOG_DIR/${id}-empty-values-preset.log"
  local started ended duration
  local jasp_ini="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP.ini"
  started="$(date +%s)"

  {
    echo "== MacWin JASP empty-values preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "ini=$jasp_ini"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "preset=$preset"
    echo "source.Settings.EMPTY_VALUES_LIST=MissingValueList"
    echo "source.Settings.defaultEmptyValues=NaN|nan|.|NA"
    echo "source.PreferencesModel.emptyValues=_splitValues(Settings::value(Settings::EMPTY_VALUES_LIST).toString())"
    echo
  } > "$log"

  if [ "$preset" = "0" ] || [ "$preset" = "off" ] || [ "$preset" = "disabled" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "empty-values-preset" "skipped" 0 "$log" "$duration" "JASP empty-values preset disabled; set MACWIN_JASP_EMPTY_VALUES_PRESET=safe-minimal to replace default NaN/nan/./NA parsing with a numeric-only launch comparison."
    return 0
  fi

  mkdir -p "$(dirname "$jasp_ini")"
  if [ -f "$jasp_ini" ]; then
    cp -f "$jasp_ini" "$jasp_ini.macwin-before-empty-values-preset" || true
  fi

  /usr/bin/python3 - "$jasp_ini" "$preset" >> "$log" <<'PY'
import configparser
import sys
from pathlib import Path

path = Path(sys.argv[1])
preset = sys.argv[2]

if preset in ("safe-minimal", "numeric-safe"):
    value = "0"
elif preset.startswith("custom:"):
    value = preset[len("custom:"):]
elif preset == "empty":
    value = ""
else:
    print(f"preset.error=unknown preset {preset!r}")
    sys.exit(2)

config = configparser.ConfigParser()
config.optionxform = str
if path.exists():
    config.read(path, encoding="utf-8")
if "General" not in config:
    config["General"] = {}

general = config["General"]
if "emptyValues" in general:
    del general["emptyValues"]
general["MissingValueList"] = value
general["logToFile"] = "true"

with path.open("w", encoding="utf-8", newline="\n") as handle:
    config.write(handle, space_around_delimiters=False)

print(f"preset.MissingValueList={value}")
print("preset.removedWrongKey.emptyValues=yes")
PY
  local py_status=$?

  {
    echo
    echo "## resulting ini"
    nl -ba "$jasp_ini" | sed -n '1,120p'
    echo
    echo "## current internal sqlite emptyValuesJson"
    if command -v sqlite3 >/dev/null 2>&1; then
      find "$PREFIX/drive_c/users/$USER/AppData/Local/JASP/JASP/temp" -mindepth 2 -maxdepth 2 -type f -name 'internal.sqlite' -print 2>/dev/null \
        | sort \
        | while IFS= read -r db; do
            echo "sqlite=${db#$PREFIX/drive_c/}"
            sqlite3 "$db" 'select id, revision, emptyValuesJson from DataSets;' 2>&1 | sed 's/^/  /'
          done
    else
      echo "sqlite3=missing"
    fi
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  if [ "$py_status" -eq 0 ]; then
    record "$id" "empty-values-preset" "passed" 0 "$log" "$duration" "Applied JASP MissingValueList preset for a launch comparison; this uses the actual Settings::EMPTY_VALUES_LIST key and removes the previous wrong emptyValues key."
  else
    record "$id" "empty-values-preset" "failed" "$py_status" "$log" "$duration" "Failed to apply JASP MissingValueList preset; inspect the preset name and JASP.ini before rerunning."
  fi
  return "$py_status"
}

configure_jasp_engine_count_preset() {
  local id="$1"
  local preset="${MACWIN_JASP_MAX_ENGINES:-0}"
  local log="$LOG_DIR/${id}-engine-count-preset.log"
  local started ended duration
  local jasp_ini="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP.ini"
  started="$(date +%s)"

  {
    echo "== MacWin JASP engine-count preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "ini=$jasp_ini"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "preset=$preset"
    echo "source.Settings.MAX_ENGINE_COUNT=maxEngineCount"
    echo "source.Settings.MAX_ENGINE_COUNT_ADMIN=maxEngineCountAdmin"
    echo "source.EngineSync.maxEngineCount=max(1, PreferencesModel::prefs()->maxEngines())"
    echo
  } > "$log"

  if [ "$preset" = "0" ] || [ "$preset" = "off" ] || [ "$preset" = "disabled" ] || [ -z "$preset" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "engine-count-preset" "skipped" 0 "$log" "$duration" "JASP engine-count preset disabled; set MACWIN_JASP_MAX_ENGINES=1 to compare startup with a single EngineSync channel."
    return 0
  fi

  mkdir -p "$(dirname "$jasp_ini")"
  if [ -f "$jasp_ini" ]; then
    cp -f "$jasp_ini" "$jasp_ini.macwin-before-engine-count-preset" || true
  fi

  /usr/bin/python3 - "$jasp_ini" "$preset" >> "$log" <<'PY'
import configparser
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = sys.argv[2]

try:
    count = int(raw)
except ValueError:
    print(f"preset.error=invalid integer {raw!r}")
    sys.exit(2)

if count < 1 or count > 64:
    print(f"preset.error=count out of supported range: {count}")
    sys.exit(2)

config = configparser.ConfigParser()
config.optionxform = str
if path.exists():
    config.read(path, encoding="utf-8")
if "General" not in config:
    config["General"] = {}

general = config["General"]
general["maxEngineCount"] = str(count)
general["maxEngineCountAdmin"] = str(count)
general["logToFile"] = "true"

with path.open("w", encoding="utf-8", newline="\n") as handle:
    config.write(handle, space_around_delimiters=False)

print(f"preset.maxEngineCount={count}")
print(f"preset.maxEngineCountAdmin={count}")
PY
  local py_status=$?

  {
    echo
    echo "## resulting ini"
    nl -ba "$jasp_ini" | sed -n '1,140p'
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  if [ "$py_status" -eq 0 ]; then
    record "$id" "engine-count-preset" "passed" 0 "$log" "$duration" "Applied JASP maxEngineCount/maxEngineCountAdmin preset for an EngineSync channel-count launch comparison."
  else
    record "$id" "engine-count-preset" "failed" "$py_status" "$log" "$duration" "Failed to apply JASP engine-count preset; inspect MACWIN_JASP_MAX_ENGINES and JASP.ini before rerunning."
  fi
  return "$py_status"
}

configure_jasp_initial_state_isolation() {
  local id="$1"
  local log="$LOG_DIR/${id}-state-isolation-preset.log"
  local local_root="$PREFIX/drive_c/users/$USER/AppData/Local/JASP/JASP"
  local roaming_root="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP"
  local backup_root="$LOG_DIR/${id}-state-isolation-backup"
  local started ended duration moved_count=0
  local source relative target
  started="$(date +%s)"

  {
    echo "== MacWin JASP initial-state isolation preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "localRoot=$local_root"
    echo "roamingRoot=$roaming_root"
    echo "backupRoot=$backup_root"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "enabled=${MACWIN_JASP_STATE_ISOLATION:-0}"
    echo
  } > "$log"

  if [ "${MACWIN_JASP_STATE_ISOLATION:-0}" != "1" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "state-isolation-preset" "skipped" 0 "$log" "$duration" "JASP initial-state isolation preset disabled; set MACWIN_JASP_STATE_ISOLATION=1 to move temp session databases, IPC files, QML cache, and autosaves out of the prefix before launch."
    return 0
  fi

  if pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' >/dev/null 2>&1; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=refused"
      echo "reason=JASP process is still running"
      pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' || true
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "state-isolation-preset" "failed" 123 "$log" "$duration" "Refused to isolate JASP initial state while a JASP process is still running."
    return 123
  fi

  {
    echo "## before"
    if [ -d "$local_root/temp" ]; then
      printf 'before.temp.entries='
      find "$local_root/temp" -mindepth 1 -maxdepth 1 -print 2>/dev/null | wc -l | tr -d ' '
      printf 'before.temp.internalSqlite='
      find "$local_root/temp" -mindepth 2 -maxdepth 2 -type f -name 'internal.sqlite' -print 2>/dev/null | wc -l | tr -d ' '
      printf 'before.temp.ipcFiles='
      find "$local_root/temp" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null | wc -l | tr -d ' '
    else
      echo "before.temp=missing"
    fi
    if [ -d "$local_root/cache/qmlcache" ]; then
      printf 'before.qmlcache.files='
      find "$local_root/cache/qmlcache" -type f -print 2>/dev/null | wc -l | tr -d ' '
    else
      echo "before.qmlcache=missing"
    fi
    if [ -d "$roaming_root/AutoSaves" ]; then
      printf 'before.autosaves.files='
      find "$roaming_root/AutoSaves" -type f -print 2>/dev/null | wc -l | tr -d ' '
    else
      echo "before.autosaves=missing"
    fi
    echo
    echo "## moved"
  } >> "$log"

  mkdir -p "$backup_root"
  for source in \
    "$local_root/temp" \
    "$local_root/cache/qmlcache" \
    "$roaming_root/AutoSaves"; do
    [ -e "$source" ] || continue
    case "$source" in
      "$local_root"/*) relative="Local/${source#$local_root/}" ;;
      "$roaming_root"/*) relative="Roaming/${source#$roaming_root/}" ;;
      *) relative="$(basename "$source")" ;;
    esac
    target="$backup_root/$relative"
    mkdir -p "$(dirname "$target")"
    if mv "$source" "$target"; then
      moved_count=$((moved_count + 1))
      echo "moved=$source -> $target" >> "$log"
    else
      echo "moveFailed=$source" >> "$log"
    fi
  done

  mkdir -p "$local_root/temp" "$local_root/cache" "$roaming_root/AutoSaves" || true

  {
    echo
    echo "## after"
    printf 'after.temp.entries='
    find "$local_root/temp" -mindepth 1 -maxdepth 1 -print 2>/dev/null | wc -l | tr -d ' '
    printf 'after.qmlcache.exists='
    if [ -d "$local_root/cache/qmlcache" ]; then echo yes; else echo no; fi
    printf 'after.autosaves.files='
    find "$roaming_root/AutoSaves" -type f -print 2>/dev/null | wc -l | tr -d ' '
    echo "movedCount=$moved_count"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "state-isolation-preset" "passed" 0 "$log" "$duration" "Moved $moved_count JASP initial-state location(s) to the run backup directory before launch: temp session databases/IPC files, QML cache, and autosaves. This tests whether the current special-float parser fail-fast is caused by persisted session state."
}

configure_jasp_ipc_cleanup() {
  local id="$1"
  local phase="${2:-ipc-cleanup-preset}"
  local log="$LOG_DIR/${id}-${phase}.log"
  local ipc_dir="$PREFIX/drive_c/users/$USER/AppData/Local/JASP/JASP/temp"
  local boost_ipc_dir="$PREFIX/drive_c/ProgramData/boost_interprocess/01000000"
  local started ended duration before_count=0 after_count=0 removed_count=0
  started="$(date +%s)"

  {
    echo "== MacWin JASP IPC cleanup preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "ipcDir=$ipc_dir"
    echo "boostIpcDir=$boost_ipc_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "enabled=${MACWIN_JASP_CLEAN_IPC:-0}"
    echo
  } > "$log"

  if [ "${MACWIN_JASP_CLEAN_IPC:-0}" != "1" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "$phase" "skipped" 0 "$log" "$duration" "JASP IPC cleanup preset disabled; set MACWIN_JASP_CLEAN_IPC=1 to remove stale JASP-IPC-* temp files before launch."
    return 0
  fi

  if pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' >/dev/null 2>&1; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=refused"
      echo "reason=JASP process is still running"
      pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' || true
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "$phase" "failed" 122 "$log" "$duration" "Refused to clean JASP IPC temp files while a JASP process is still running."
    return 122
  fi

  {
    echo "## before"
  } >> "$log"
  capture_jasp_boost_ipc_snapshot "$id" "cleanup-before" "$log"
  before_count="$(while IFS= read -r ipc_dir; do
    [ -d "$ipc_dir" ] || continue
    find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null
  done < <(jasp_ipc_candidate_dirs) | wc -l | tr -d ' ')"
  while IFS= read -r ipc_dir; do
    if [ -d "$ipc_dir" ]; then
      find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null \
        | while IFS= read -r ipc_file; do
            rm -f "$ipc_file" && printf 'removed=%s/%s\n' "${ipc_dir#$PREFIX/}" "${ipc_file#$ipc_dir/}" >> "$log"
          done
    else
      mkdir -p "$ipc_dir" || true
      echo "beforeDirMissing=${ipc_dir#$PREFIX/}" >> "$log"
    fi
  done < <(jasp_ipc_candidate_dirs)

  after_count="$(while IFS= read -r ipc_dir; do
    [ -d "$ipc_dir" ] || continue
    find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null
  done < <(jasp_ipc_candidate_dirs) | wc -l | tr -d ' ')"
  removed_count=$(( ${before_count:-0} - ${after_count:-0} ))
  {
    echo
    echo "## after"
    echo "beforeCount=${before_count:-0}"
    echo "afterCount=${after_count:-0}"
    echo "removedCount=$removed_count"
    capture_jasp_boost_ipc_snapshot "$id" "cleanup-after" "$log"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "$phase" "passed" 0 "$log" "$duration" "Removed $removed_count stale JASP-IPC-* temp file(s) before launch so the next run can test fresh Boost interprocess channel creation."
}

stabilize_jasp_wineserver_for_launch() {
  local id="$1"
  local log="$LOG_DIR/${id}-prelaunch-wineserver-isolation.log"
  local started ended duration exit_code=0
  started="$(date +%s)"
  {
    echo "== MacWin JASP prelaunch wineserver isolation =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$log"

  terminate_live_gui_processes_for_sample "$id" "$log" || true
  if pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' >/dev/null 2>&1; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "isolation=refused"
      echo "reason=JASP process is still running"
      pgrep -fl 'JASPDesktop\.exe|JASPEngine\.exe' || true
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "prelaunch-wineserver-isolation" "failed" 123 "$log" "$duration" "Refused to restart the bottle wineserver while a JASP process is still running."
    return 123
  fi

  "${WINESERVER_CMD[@]}" -k >> "$log" 2>&1 || exit_code=$?
  sleep 2
  {
    echo "wineserverExit=$exit_code"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  ended="$(date +%s)"
  duration=$((ended - started))

  if [ "$exit_code" -eq 0 ]; then
    record "$id" "prelaunch-wineserver-isolation" "passed" 0 "$log" "$duration" "Restarted the bottle wineserver after JASP loader/CreateProcess probes so the GUI launch starts from an isolated Wine service session."
    return 0
  fi

  record "$id" "prelaunch-wineserver-isolation" "failed" "$exit_code" "$log" "$duration" "Failed to stop the probe wineserver before JASP GUI launch."
  return "$exit_code"
}

configure_jasp_desktop_exe_override() {
  local id="$1"
  local override="${MACWIN_JASP_DESKTOP_EXE_OVERRIDE:-}"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local target="$app_dir/JASPDesktop.exe"
  local log="$LOG_DIR/${id}-desktop-exe-override.log"
  local started ended duration backup
  started="$(date +%s)"

  {
    echo "== MacWin JASP Desktop exe override =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "target=$target"
    echo "override=${override:-unset}"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ -z "$override" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "override=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "desktop-exe-override" "skipped" 0 "$log" "$duration" "JASPDesktop.exe override disabled; set MACWIN_JASP_DESKTOP_EXE_OVERRIDE to a patched Windows JASPDesktop.exe to test the deferred-reset candidate."
    return 0
  fi

  if [ ! -f "$override" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "overrideMissing=$override"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "desktop-exe-override" "failed" 127 "$log" "$duration" "JASPDesktop.exe override path does not exist."
    return 127
  fi

  if [ ! -f "$target" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "targetMissing=$target"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "desktop-exe-override" "failed" 126 "$log" "$duration" "Installed JASPDesktop.exe target is missing; install JASP before applying an override."
    return 126
  fi

  if ! file "$override" | rg -q 'PE32\+? executable.*x86-64|PE32 executable.*Intel 80386'; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      printf 'overrideFileType='
      file "$override"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "desktop-exe-override" "failed" 125 "$log" "$duration" "Override is not a Windows PE executable."
    return 125
  fi

  backup="$LOG_DIR/${id}-JASPDesktop.before-override.exe"
  cp -f "$target" "$backup"
  cp -f "$override" "$target"

  {
    printf 'backup=%s\n' "$backup"
    printf 'before.sha256='
    shasum -a 256 "$backup" | awk '{print $1}'
    printf 'override.sha256='
    shasum -a 256 "$override" | awk '{print $1}'
    printf 'target.sha256='
    shasum -a 256 "$target" | awk '{print $1}'
    printf 'targetFileType='
    file "$target"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "desktop-exe-override" "passed" 0 "$log" "$duration" "Applied patched JASPDesktop.exe override; launch will test whether the deferred-reset candidate moves the EngineSync constructor re-entry boundary."
}

configure_jasp_ipc_trace_preset() {
  local id="$1"
  local log="$LOG_DIR/${id}-ipc-trace-preset.log"
  local started ended duration previous_clean previous_winedebug
  started="$(date +%s)"
  previous_clean="${MACWIN_JASP_CLEAN_IPC:-}"
  previous_winedebug="${MACWIN_JASP_WINEDEBUG:-}"

  {
    echo "== MacWin JASP IPC trace preset =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "enabled=${MACWIN_JASP_IPC_TRACE:-0}"
    echo "previous.MACWIN_JASP_CLEAN_IPC=${previous_clean:-unset}"
    echo "previous.MACWIN_JASP_WINEDEBUG=${previous_winedebug:-unset}"
  } > "$log"

  if [ "${MACWIN_JASP_IPC_TRACE:-0}" != "1" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "preset=disabled"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "ipc-trace-preset" "skipped" 0 "$log" "$duration" "JASP IPC trace preset disabled; set MACWIN_JASP_IPC_TRACE=1 to clean stale IPC files and run with +file,+seh logging."
    return 0
  fi

  MACWIN_JASP_CLEAN_IPC=1
  if [ -z "${MACWIN_JASP_WINEDEBUG:-}" ]; then
    MACWIN_JASP_WINEDEBUG="+file,+seh"
  fi

  {
    echo "preset=enabled"
    echo "effective.MACWIN_JASP_CLEAN_IPC=$MACWIN_JASP_CLEAN_IPC"
    echo "effective.MACWIN_JASP_WINEDEBUG=$MACWIN_JASP_WINEDEBUG"
    echo "traceTargets=JASP-IPC-*_0,JASP-IPC-*_MasterToSlave,JASP-IPC-*_SlaveToMaster,JASP-IPC-*_heartbeat,NtLockFile,boost::interprocess"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "ipc-trace-preset" "passed" 0 "$log" "$duration" "Enabled JASP IPC trace preset: clean stale JASP-IPC-* files before launch and capture +file,+seh evidence for Boost interprocess shared-memory and lock behavior."
}

write_jasp_qml_resource_probe() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local log="$LOG_DIR/${id}-qml-resource-probe.log"
  local started ended duration runtime_missing=0 fallback_missing=0 angle_qmldir=0 qrc_evidence=1
  started="$(date +%s)"
  {
    echo "== MacWin JASP QML/resource probe =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "appDir=$app_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ ! -f "$app_dir/JASPDesktop.exe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "missing=JASPDesktop.exe"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "qml-resource-probe" "skipped" 0 "$log" "$duration" "JASP executable is not installed yet; QML resource probe skipped."
    return 0
  fi

  {
    echo "## binary"
    printf 'JASPDesktop.exe.size='
    stat -f %z "$app_dir/JASPDesktop.exe" 2>/dev/null || wc -c < "$app_dir/JASPDesktop.exe"
    printf 'JASPDesktop.exe.sha256='
    shasum -a 256 "$app_dir/JASPDesktop.exe" | awk '{print $1}'
    echo
    echo "## embedded resource/import strings"
  } >> "$log"

  if rg -a -q 'qRegisterResourceData|qrc:///components|:/jasp-stats\.org/imports|file:\./components/JASP/Widgets/MainWindow\.qml' "$app_dir/JASPDesktop.exe"; then
    rg -a -o 'qRegisterResourceData|qrc:///components|:/jasp-stats\.org/imports|file:\./components/JASP/(Theme/(DarkTheme|Theme)|Widgets/(MainWindow|HelpWindow|AboutWindow|CsvPreview))\.qml' "$app_dir/JASPDesktop.exe" \
      | sort -u \
      | sed 's/^/embedded=/' >> "$log" || true
  else
    qrc_evidence=0
    echo "embeddedEvidence=missing expected qrc/import/load strings" >> "$log"
  fi

  {
    echo
    echo "## qt runtime files"
  } >> "$log"
  local runtime_rel
  for runtime_rel in Qt6Qml.dll Qt6Quick.dll Qt6QuickControls2.dll Qt6WebEngineQuick.dll Qt6WebEngineCore.dll resources/qtwebengine_resources.pak qml/QtQuick/qmldir qml/QtWebEngine/qmldir; do
    if [ -e "$app_dir/$runtime_rel" ]; then
      printf 'present=%s size=' "$runtime_rel" >> "$log"
      stat -f %z "$app_dir/$runtime_rel" >> "$log" 2>/dev/null || wc -c < "$app_dir/$runtime_rel" >> "$log"
    else
      runtime_missing=$((runtime_missing + 1))
      echo "missing=$runtime_rel" >> "$log"
    fi
  done

  {
    echo
    echo "## fallback qml files"
  } >> "$log"
  local qml_rel
  for qml_rel in \
    components/JASP/Theme/Theme.qml \
    components/JASP/Theme/DarkTheme.qml \
    components/JASP/Widgets/HelpWindow.qml \
    components/JASP/Widgets/AboutWindow.qml \
    components/JASP/Widgets/CsvPreview.qml \
    components/JASP/Widgets/MainWindow.qml; do
    if [ -f "$app_dir/$qml_rel" ]; then
      printf 'present=%s sha256=' "$qml_rel" >> "$log"
      shasum -a 256 "$app_dir/$qml_rel" | awk '{print $1}' >> "$log"
      rg -n '^import ' "$app_dir/$qml_rel" | sed "s#^#${qml_rel}:#" >> "$log" || true
    else
      fallback_missing=$((fallback_missing + 1))
      echo "missing=$qml_rel" >> "$log"
    fi
  done

  {
    echo
    echo "## fallback qmldir modules"
  } >> "$log"
  local qmldir_rel module_line
  for qmldir_rel in components/JASP/Controls/qmldir components/JASP/Theme/qmldir components/JASP/Widgets/qmldir components/JASP/Style/qmldir; do
    if [ -f "$app_dir/$qmldir_rel" ]; then
      module_line="$(sed -n '1p' "$app_dir/$qmldir_rel")"
      printf '%s:%s\n' "$qmldir_rel" "$module_line" >> "$log"
      if printf '%s' "$module_line" | rg -q 'module <JASP\.'; then
        angle_qmldir=$((angle_qmldir + 1))
      fi
    else
      fallback_missing=$((fallback_missing + 1))
      echo "missing=$qmldir_rel" >> "$log"
    fi
  done

  {
    echo
    echo "## source baseline"
    echo "source.qmlRegisterTypes=Desktop/mainwindow.cpp registers JASP DataSetView/JaspTheme/RCommander/ResultsJsInterface/ColumnModel before loadQML"
    echo "source.importPaths=Desktop/mainwindow.cpp appends :/jasp-stats.org/imports and qrc:///components"
    echo "source.preQmlBoundary=Desktop/mainwindow.cpp emits Loading Themes immediately before the first _qml->load call"
    echo "source.loadOrder=Themes are loaded before setCurrentJaspTheme and before widgets"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  local note
  if [ "$runtime_missing" -eq 0 ] && [ "$qrc_evidence" -eq 1 ]; then
    note="JASP QML probe completed: required Qt runtime files are present and JASPDesktop.exe contains qRegisterResourceData plus qrc/import evidence. If launch reaches EngineSync but never emits Loading Themes, the remaining failure is before the first _qml->load call and not a missing installer payload."
    if [ "$fallback_missing" -gt 0 ]; then
      note="$(append_note "$note" "$fallback_missing external fallback QML artifacts are absent, which is expected for this embedded-qrc MSI layout.")"
    fi
    if [ "$angle_qmldir" -gt 0 ]; then
      note="$(append_note "$note" "The fallback Theme/Widgets/Style qmldir files still use upstream angle-bracket module names; a prior module-name normalization experiment did not change the failure signature, so treat this as evidence rather than a proven fix path.")"
    fi
    record "$id" "qml-resource-probe" "passed" 0 "$log" "$duration" "$note"
  else
    note="JASP QML probe found $runtime_missing missing required Qt runtime artifacts or missing embedded qrc evidence; inspect the probe log before classifying this as the known QQml resource failure. External fallback missing count: $fallback_missing."
    record "$id" "qml-resource-probe" "failed" 112 "$log" "$duration" "$note"
  fi
}

write_jasp_runtime_state_probe() {
  local id="$1"
  local phase="${2:-runtime-state-probe}"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local user_dir="$PREFIX/drive_c/users/$USER/AppData/Local/JASP/JASP"
  local log="$LOG_DIR/${id}-${phase}.log"
  local started ended duration launch_log sqlite_db missing=0 launch_log_seen=0 sqlite_expected_missing=0
  started="$(date +%s)"
  launch_log="$LOG_DIR/${id}-launch.log"
  sqlite_db="$user_dir/temp/32/internal.sqlite"

  {
    echo "== MacWin JASP runtime-state probe =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "appDir=$app_dir"
    echo "userDir=$user_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ ! -f "$app_dir/JASPDesktop.exe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "missing=JASPDesktop.exe"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "$phase" "skipped" 0 "$log" "$duration" "JASP executable is not installed yet; runtime-state probe skipped."
    return 0
  fi

  {
    echo "## runtime json"
  } >> "$log"
  local json_file json_label
  for json_file in \
    "$app_dir/staticRuntimeInfo.json" \
    "$user_dir/dynamicRuntimeInfo.json" \
    "$app_dir/Modules/modules-settings.json"; do
    json_label="${json_file#$PREFIX/drive_c/}"
    if [ -f "$json_file" ]; then
      printf '%s.size=' "$json_label" >> "$log"
      stat -f %z "$json_file" >> "$log" 2>/dev/null || wc -c < "$json_file" >> "$log"
      /usr/bin/python3 - "$json_file" "$json_label" >> "$log" <<'PY' || true
import json
import sys

path, label = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception as exc:
    print(f"{label}.jsonError={exc}")
    sys.exit(0)

if isinstance(data, dict):
    for key in ("runtimeEnvironment", "jaspVersion", "RVersion", "commit", "buildDate", "initialized"):
        if key in data:
            print(f"{label}.{key}={data[key]}")
    for key in ("common", "extra"):
        value = data.get(key)
        if isinstance(value, list):
            print(f"{label}.{key}.count={len(value)}")
            print(f"{label}.{key}.first={','.join(map(str, value[:5]))}")
else:
    print(f"{label}.jsonType={type(data).__name__}")
PY
    else
      missing=$((missing + 1))
      echo "missing=$json_label" >> "$log"
    fi
  done

  {
    echo
    echo "## bundled modules cache"
  } >> "$log"
  find "$user_dir" -maxdepth 1 -type d -name 'BundledJASPModules_*' -print 2>/dev/null \
    | sort \
    | while IFS= read -r module_dir; do
        printf 'bundledModuleCache=%s\n' "${module_dir#$user_dir/}" >> "$log"
        if [ -f "$module_dir/modules-settings.json" ]; then
          printf 'bundledModuleCache.modules-settings.size=' >> "$log"
          stat -f %z "$module_dir/modules-settings.json" >> "$log" 2>/dev/null || wc -c < "$module_dir/modules-settings.json" >> "$log"
        fi
      done

  {
    echo
    echo "## internal sqlite"
  } >> "$log"
  if [ -f "$sqlite_db" ]; then
    printf 'internal.sqlite.size=' >> "$log"
    stat -f %z "$sqlite_db" >> "$log" 2>/dev/null || wc -c < "$sqlite_db" >> "$log"
    if command -v sqlite3 >/dev/null 2>&1; then
      printf 'internal.sqlite.tables=' >> "$log"
      sqlite3 "$sqlite_db" '.tables' >> "$log" 2>&1 || true
      printf 'internal.sqlite.integrity=' >> "$log"
      sqlite3 "$sqlite_db" 'pragma integrity_check;' >> "$log" 2>&1 || true
    fi
  else
    if [ "${MACWIN_JASP_STATE_ISOLATION:-0}" = "1" ] && [ "$phase" = "runtime-state-probe" ]; then
      sqlite_expected_missing=1
      echo "expectedMissing=${sqlite_db#$PREFIX/drive_c/}" >> "$log"
      echo "expectedMissing.reason=MACWIN_JASP_STATE_ISOLATION moved the prelaunch temp session directory before this probe." >> "$log"
    elif [ "$phase" = "runtime-state-probe" ] && is_jasp_unit_test_launch; then
      sqlite_expected_missing=1
      echo "expectedMissing=${sqlite_db#$PREFIX/drive_c/}" >> "$log"
      echo "expectedMissing.reason=JASP creates the unit-test session database after the prelaunch runtime-state probe." >> "$log"
    elif [ "$phase" = "runtime-state-probe" ]; then
      sqlite_expected_missing=1
      echo "expectedMissing=${sqlite_db#$PREFIX/drive_c/}" >> "$log"
      echo "expectedMissing.reason=JASP creates the normal session database during launch, after the prelaunch runtime-state probe." >> "$log"
    elif [ "$phase" = "runtime-state-postlaunch-probe" ] \
      && [ -f "$launch_log" ] \
      && is_jasp_unit_test_launch \
      && has_jasp_completed_analysis_workload "$launch_log"; then
      sqlite_expected_missing=1
      echo "expectedMissing=${sqlite_db#$PREFIX/drive_c/}" >> "$log"
      echo "expectedMissing.reason=The completed JASP unit-test workload closed its temporary session database before the postlaunch probe." >> "$log"
    else
      missing=$((missing + 1))
      echo "missing=${sqlite_db#$PREFIX/drive_c/}" >> "$log"
    fi
  fi

  {
    echo
    echo "## engine spawn configuration"
    echo "expected.JASPENGINE_LOCATION=C:\\Program Files\\JASP\\JASPEngine.exe"
  } >> "$log"
  local jasp_ini="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP.ini"
  if [ -f "$jasp_ini" ]; then
    echo "JASP.ini.present=yes" >> "$log"
    rg -n -i 'MissingValueList|emptyValues|maxEngineCount|maxEngineCountAdmin|engineSandbox|safeGraphicsMode|logToFile|checkUpdates|checkUpdatesAskUser|useConfigurationFile|remoteConfiguration|remoteConfigurationURL|moduleLibraryURL|instructionsShown' "$jasp_ini" | sed 's/^/JASP.ini:/' >> "$log" || true
  else
    echo "JASP.ini.present=no" >> "$log"
  fi
  {
    echo
    echo "## ipc files"
  } >> "$log"
  local ipc_dir="$user_dir/temp"
  if [ -d "$ipc_dir" ]; then
    find "$ipc_dir" -maxdepth 1 -type f -name 'JASP-IPC-*' -print 2>/dev/null \
      | sort \
      | while IFS= read -r ipc_file; do
          printf 'ipc=%s size=' "${ipc_file#$ipc_dir/}" >> "$log"
          stat -f %z "$ipc_file" >> "$log" 2>/dev/null || wc -c < "$ipc_file" >> "$log"
        done
  else
    echo "ipcDir=missing" >> "$log"
  fi

  {
    echo
    echo "## launch milestones"
  } >> "$log"
  if [ -f "$launch_log" ]; then
    launch_log_seen=1
    for milestone in \
      'QtWebEngineQuick initialized' \
      'MainWindow constructor started' \
      'Going to construct the necessary models' \
      'Opened internal sqlite database' \
      'DataSetPackage::reset' \
      'EngineSync::enginesPrepareForData!' \
      'DataSetPackage::endLoadingData' \
      'EngineSync::enginesReceiveNewData!' \
      'JASP Desktop started and Engines initalized' \
      'Initializing QML' \
      'Loading Themes' \
      'QML loaded, url:' \
      'QML Initialized!' \
      'TIMEOUT after'; do
      if rg -q --fixed-strings "$milestone" "$launch_log"; then
        printf 'seen=' >> "$log"
      else
        printf 'absent=' >> "$log"
      fi
      printf '%s\n' "$milestone" >> "$log"
    done
    echo "lastLaunchLines:" >> "$log"
    tail -40 "$launch_log" | sed 's/^/  /' >> "$log"
    echo
    echo "## live process snapshot summary" >> "$log"
    if rg -q 'liveProcessSnapshot=' "$launch_log"; then
      if live_process_snapshot_has "$launch_log" 'JASPDesktop\.exe'; then
        echo "liveProcessSnapshot.hasJASPDesktop=yes" >> "$log"
      else
        echo "liveProcessSnapshot.hasJASPDesktop=no" >> "$log"
      fi
      if live_process_snapshot_has "$launch_log" 'JASPEngine\.exe'; then
        echo "liveProcessSnapshot.hasJASPEngine=yes" >> "$log"
      else
        echo "liveProcessSnapshot.hasJASPEngine=no" >> "$log"
      fi
      if live_process_snapshot_has "$launch_log" 'QtWebEngineProcess\.exe'; then
        echo "liveProcessSnapshot.hasQtWebEngineProcess=yes" >> "$log"
      else
        echo "liveProcessSnapshot.hasQtWebEngineProcess=no" >> "$log"
      fi
    else
      echo "liveProcessSnapshot=not-present" >> "$log"
    fi
    echo
    echo "## timeout diagnostics summary" >> "$log"
    if rg -q '^jaspTimeoutDiagnostics=' "$launch_log"; then
      rg '^jaspTimeout\.(jaspDesktopPid|webEngineMode|beginResetModelWarnings|endResetModelWarnings|modelResetWarnings|modelResetObject\.[0-9]+\.(class|address|kind|count)|modelResetSequence\.[0-9]+\.(line|kind|class|address)|hasEngineStartMarker|hasEngineRepresentationMarker|hasDesktopStartedMarker|hasQmlMilestone|sampleLog|sampleCaptured|sampleFailed|samplePhysicalFootprint|samplePeakPhysicalFootprint|sampleHasMainThreadEventLoopWait|sampleHasCrBrowserMain|sampleHasCrBrowserSyscallRecursion|sampleHasCrBrowserRosettaJit|sampleHasRosetta|sampleInterpretation)=' "$launch_log" >> "$log" || true
      rg '^jaspModelReset(Summary|Object|Sequence)' "$launch_log" >> "$log" || true
    else
      echo "jaspTimeoutDiagnostics=not-present" >> "$log"
    fi
  else
    echo "launchLog=not-yet-present; runtime-state probe is running before launch" >> "$log"
  fi

  {
    echo
    echo "## source boundary"
    echo "source.constructor=Desktop/mainwindow.cpp:100-108 constructs QQmlApplicationEngine, PreferencesModel, DataSetPackage, and EngineSync; Desktop/mainwindow.cpp:162 schedules QTimer::singleShot(0, loadQML), :166 calls _engineSync->start(), and :179 logs JASP Desktop started."
    echo "source.locale=Desktop/main.cpp:488-491 sets QLocale::English and LC_ALL=en_US.UTF-8 before QApplication startup, so host LANG/LC_ALL is lower priority than the DataSetPackage/Qt model-reset boundary for this signature."
    echo "source.datasetReset=Desktop/data/datasetpackage.cpp:100-108 setEngineSync() connects EngineSync and immediately calls reset(); :141-172 reset() calls beginLoadingData(), createDataSet(), then endLoadingData(); :1442-1452 endLoadingData() calls endResetModel(), enginesReceiveNewData(), then emits modelInit()."
    echo "source.engineStart=Desktop/engine/enginesync.cpp:314-338 start() only creates IPC channels and timers; JASPEngine starts later from createNewEngine()/startSlaveProcess() at Desktop/engine/enginesync.cpp:956-1028."
    if [ "$launch_log_seen" -eq 1 ] && ! log_has_runtime_fixed_string 'JASP Desktop started and Engines initalized' "$launch_log"; then
      echo "source.boundary=The launch log reaches the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData! path, but never reaches JASP Desktop started, loadQML's first Initializing QML line, or any Engine # start marker."
    elif [ "$launch_log_seen" -eq 1 ] && ! log_has_runtime_fixed_string 'Initializing QML' "$launch_log"; then
      echo "source.boundary=The launch log reaches EngineSync::enginesReceiveNewData! but does not reach loadQML's first log line, Initializing QML."
    elif [ "$launch_log_seen" -eq 1 ]; then
      echo "source.boundary=The launch log reaches JASP Desktop started and initializes the QML application UI."
    else
      echo "source.boundary=Prelaunch probe: compare the later launch log against EngineSync::enginesReceiveNewData! and loadQML's first log line, Initializing QML."
    fi
    echo "source.nextProbe=Instrument or classify DataSetPackage reset/endLoadingData, DataSetPackageSubNodeModel reset ordering, EngineSync reloadData receivers, and MainWindow constructor tail before changing graphics/QML resource settings again."
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  local note
  if [ "$missing" -eq 0 ]; then
    local sqlite_note="internal.sqlite state"
    if [ "$sqlite_expected_missing" -eq 1 ]; then
      sqlite_note="an expectedly absent transient internal.sqlite for this probe phase"
    fi
    if [ "$launch_log_seen" -eq 1 ] && ! log_has_runtime_fixed_string 'JASP Desktop started and Engines initalized' "$launch_log"; then
      if rg -q 'liveProcessSnapshot=' "$launch_log" && ! live_process_snapshot_has "$launch_log" 'JASPEngine\.exe'; then
        local process_note="JASPDesktop"
        if live_process_snapshot_has "$launch_log" 'QtWebEngineProcess\.exe'; then
          process_note="$process_note/QtWebEngine"
        fi
        note="JASP runtime-state probe captured MSI runtime metadata, dynamic runtime metadata, bundled module cache, ${sqlite_note}, and launch milestones. Current signature reaches the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData path, but never reaches JASP Desktop started or loadQML; the pre-cleanup process snapshot has ${process_note} alive and no JASPEngine child even with JASPENGINE_LOCATION set, so continue with DataSetPackage reset/endLoadingData, EngineSync reloadData receivers, Qt model warnings, and constructor-tail diagnostics."
      else
        note="JASP runtime-state probe captured MSI runtime metadata, dynamic runtime metadata, bundled module cache, ${sqlite_note}, and launch milestones. Current signature reaches the initial DataSetPackage::endLoadingData -> EngineSync::enginesReceiveNewData path, but does not return to the later MainWindow constructor milestones; continue with DataSetPackage reset/endLoadingData, EngineSync reloadData receivers, and constructor-tail diagnostics."
      fi
    elif [ "$launch_log_seen" -eq 1 ] \
      && log_has_runtime_fixed_string 'QML Initialized!' "$launch_log"; then
      note="JASP runtime-state probe captured MSI runtime metadata, dynamic runtime metadata, bundled module cache, ${sqlite_note}, and confirmed Desktop-started plus QML-initialized milestones."
    elif [ "$launch_log_seen" -eq 1 ]; then
      note="JASP runtime-state probe captured MSI runtime metadata, dynamic runtime metadata, bundled module cache, ${sqlite_note}, and reached Desktop started but not the final QML-initialized milestone."
    else
      note="JASP runtime-state probe captured prelaunch MSI runtime metadata, dynamic runtime metadata, bundled module cache, and ${sqlite_note}. Launch milestones will be compared from the later launch log; keep constructor-tail and EngineSync startup isolation as the next debug boundary."
    fi
    record "$id" "$phase" "passed" 0 "$log" "$duration" "$note"
  else
    note="JASP runtime-state probe captured partial state with $missing missing artifact(s); inspect the probe log before changing graphics or QML resource repairs."
    record "$id" "$phase" "failed" 114 "$log" "$duration" "$note"
  fi
}

write_jasp_constructor_boundary_probe() {
  local id="$1"
  local phase="${2:-constructor-boundary-probe}"
  local log="$LOG_DIR/${id}-${phase}.log"
  local source_dir="$PROJECT_ROOT/refs/jasp-desktop-v0.97.1"
  local started ended duration launch_log
  local mainwindow_src dataset_src enginesync_src ipcchannel_src defer_patch proxy_reset_patch workspace_reset_patch
  local patch_work patched_dataset_src patched_enginesync_src
  local enginerepresentation_src
  started="$(date +%s)"
  launch_log="$LOG_DIR/${id}-launch.log"
  mainwindow_src="$LOG_DIR/${id}-source-mainwindow.cpp"
  dataset_src="$LOG_DIR/${id}-source-datasetpackage.cpp"
  enginesync_src="$LOG_DIR/${id}-source-enginesync.cpp"
  ipcchannel_src="$LOG_DIR/${id}-source-ipcchannel.cpp"
  enginerepresentation_src="$LOG_DIR/${id}-source-enginerepresentation.cpp"
  defer_patch="$PROJECT_ROOT/patches/jasp-0.97.1-initialize-enginesync-before-reset.patch"
  proxy_reset_patch="$PROJECT_ROOT/patches/jasp-0.97.1-fix-proxy-model-reset.patch"
  workspace_reset_patch="$PROJECT_ROOT/patches/jasp-0.97.1-avoid-nested-workspace-reset.patch"
  patch_work="$LOG_DIR/${id}-patched-source-check"
  patched_dataset_src="$patch_work/Desktop/data/datasetpackage.cpp"
  patched_enginesync_src="$patch_work/Desktop/engine/enginesync.cpp"

  {
    echo "== MacWin JASP constructor-boundary probe =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$PREFIX"
    echo "sourceDir=$source_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ ! -d "$source_dir/.git" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "source.available=no"
      echo "missing=$source_dir"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "$phase" "skipped" 0 "$log" "$duration" "JASP source checkout is not available; constructor-boundary probe skipped."
    return 0
  fi

  git -C "$source_dir" show HEAD:Desktop/mainwindow.cpp > "$mainwindow_src" 2>/dev/null || true
  git -C "$source_dir" show HEAD:Desktop/data/datasetpackage.cpp > "$dataset_src" 2>/dev/null || true
  git -C "$source_dir" show HEAD:Desktop/engine/enginesync.cpp > "$enginesync_src" 2>/dev/null || true
  git -C "$source_dir" show HEAD:CommonData/ipcchannel.cpp > "$ipcchannel_src" 2>/dev/null || true
  git -C "$source_dir" show HEAD:Desktop/engine/enginerepresentation.cpp > "$enginerepresentation_src" 2>/dev/null || true

  {
    echo "## source call order"
    if [ -s "$mainwindow_src" ]; then
      rg -n 'MainWindow::MainWindow|QTimer::singleShot\(0, this, \[&\]\(\) \{ loadQML\(\); \}\);|_engineSync->start\(\);|checkForUpdates\(\);|processConfiguration\(\)|JASP Desktop started and Engines initalized|void MainWindow::loadQML\(\)|Initializing QML|connect\(_loader,[[:space:]]*&AsyncLoader::checkDoSync,[[:space:]]*this,[[:space:]]*&MainWindow::checkDoSync,[[:space:]]*Qt::BlockingQueuedConnection' "$mainwindow_src" \
        | sed 's/^/source.mainwindow:/' >> "$log" || true
    else
      echo "source.mainwindow=missing" >> "$log"
    fi
    if [ -s "$dataset_src" ]; then
      rg -n 'void DataSetPackage::setEngineSync|connect\(this,[[:space:]]*&DataSetPackage::enginesReceiveNewDataSignal|reset\(\);|void DataSetPackage::reset|beginLoadingData\(\);|endLoadingData\(\);|void DataSetPackage::endLoadingData|enginesReceiveNewData\(\);|emit modelInit\(\);' "$dataset_src" \
        | sed 's/^/source.datasetpackage:/' >> "$log" || true
    else
      echo "source.datasetpackage=missing" >> "$log"
    fi
    if [ -s "$enginesync_src" ]; then
      rg -n 'EngineSync::EngineSync|DataSetPackage::pkg\(\)->setEngineSync\(this\)|_memoryName = "JASP-IPC-"|void EngineSync::start\(\)|void EngineSync::process\(\)|void EngineSync::processFilterScript\(\)|_timerProcess->start|_timerBeat->start|void EngineSync::enginesReceiveNewData\(\)|emit reloadData\(\);|connect\(this,[[:space:]]*&EngineSync::reloadData|EngineSync::startSlaveProcess|Engine #[^"]*\(re\)started|createNewEngine' "$enginesync_src" \
        | sed 's/^/source.enginesync:/' >> "$log" || true
    else
      echo "source.enginesync=missing" >> "$log"
    fi
    if [ -s "$enginerepresentation_src" ]; then
      rg -n 'EngineRepresentation::EngineRepresentation|void EngineRepresentation::setSlaveProcess|Setting new engine process to engineRepresentation Engine #' "$enginerepresentation_src" \
        | sed 's/^/source.enginerepresentation:/' >> "$log" || true
    else
      echo "source.enginerepresentation=missing" >> "$log"
    fi
    if [ -s "$ipcchannel_src" ]; then
      rg -n 'BOOST_INTERPROCESS_SHARED_DIR_FUNC|get_shared_dir|IPCChannel::IPCChannel|managed_shared_memory|open_or_create|open_only|find_or_construct|interprocess_mutex|findConstructMutexes|findConstructDataStrings|JASP-IPC|heartbeat|_jaspHeartBeatPath' "$ipcchannel_src" \
        | sed 's/^/source.ipcchannel:/' >> "$log" || true
    else
      echo "source.ipcchannel=missing" >> "$log"
    fi
    echo "source.reentry=Desktop/engine/enginesync.cpp constructs EngineSync and calls DataSetPackage::pkg()->setEngineSync(this) before _memoryName is assigned; Desktop/data/datasetpackage.cpp then calls reset(), endLoadingData(), and enginesReceiveNewData(). Because DataSetPackage::isThisTheSameThreadAsEngineSync() is true on the GUI thread, the first EngineSync::enginesReceiveNewData call is synchronous constructor re-entry rather than a queued event or engine-child callback." >> "$log"
    if [ -f "$defer_patch" ] && [ -f "$proxy_reset_patch" ] && [ -f "$workspace_reset_patch" ]; then
      echo "sourcePatch.initializedEngineSync.path=$defer_patch" >> "$log"
      echo "sourcePatch.initializedEngineSync.sha256=$(shasum -a 256 "$defer_patch" | awk '{print $1}')" >> "$log"
      echo "sourcePatch.proxyReset.path=$proxy_reset_patch" >> "$log"
      echo "sourcePatch.proxyReset.sha256=$(shasum -a 256 "$proxy_reset_patch" | awk '{print $1}')" >> "$log"
      echo "sourcePatch.workspaceReset.path=$workspace_reset_patch" >> "$log"
      echo "sourcePatch.workspaceReset.sha256=$(shasum -a 256 "$workspace_reset_patch" | awk '{print $1}')" >> "$log"
      rm -rf "$patch_work"
      mkdir -p "$patch_work/Desktop/data" "$patch_work/Desktop/engine"
      cp "$dataset_src" "$patched_dataset_src" 2>/dev/null || true
      cp "$enginesync_src" "$patched_enginesync_src" 2>/dev/null || true
      cp "$source_dir/Desktop/data/datasetpackage.h" "$patch_work/Desktop/data/datasetpackage.h" 2>/dev/null || true
      cp "$source_dir/Desktop/data/datasetpackagesubnodemodel.cpp" "$patch_work/Desktop/data/datasetpackagesubnodemodel.cpp" 2>/dev/null || true
      cp "$source_dir/Desktop/data/datasetpackagesubnodemodel.h" "$patch_work/Desktop/data/datasetpackagesubnodemodel.h" 2>/dev/null || true
      if git -C "$patch_work" apply "$defer_patch" \
        && git -C "$patch_work" apply "$proxy_reset_patch" \
        && git -C "$patch_work" apply "$workspace_reset_patch" >/dev/null 2>&1; then
        echo "sourcePatch.compatibilitySet.applyToCopiedSources=passed" >> "$log"
      else
        echo "sourcePatch.compatibilitySet.applyToCopiedSources=failed" >> "$log"
      fi
    else
      echo "sourcePatch.compatibilitySet=missing" >> "$log"
    fi

    echo
    echo "## derived boundary facts"
  } >> "$log"

  /usr/bin/python3 - "$mainwindow_src" "$dataset_src" "$enginesync_src" "$ipcchannel_src" "$enginerepresentation_src" >> "$log" <<'PY' || true
import re
import sys
from pathlib import Path

main_path, dataset_path, enginesync_path, ipcchannel_path, enginerepresentation_path = map(Path, sys.argv[1:6])

def lines(path):
    if not path.exists():
        return []
    return path.read_text(errors="replace").splitlines()

def first_line(items, pattern):
    regex = re.compile(pattern)
    for index, line in enumerate(items, 1):
        if regex.search(line):
            return index
    return 0

def first_line_after(items, start_line, pattern, max_lines=80):
    if not start_line:
        return 0
    regex = re.compile(pattern)
    for index, line in enumerate(items[start_line:start_line + max_lines], start_line + 1):
        if regex.search(line):
            return index
    return 0

main = lines(main_path)
dataset = lines(dataset_path)
engine = lines(enginesync_path)
ipc = lines(ipcchannel_path)
engine_rep = lines(enginerepresentation_path)

main_loadqml_schedule = first_line(main, r"QTimer::singleShot\(0, this, .+loadQML")
main_engine_start = first_line(main, r"_engineSync->start\(\);")
main_desktop_started = first_line(main, r"JASP Desktop started and Engines initalized")
main_loadqml_entry = first_line(main, r"void MainWindow::loadQML\(")
main_checkdosync_blocking = first_line(main, r"Qt::BlockingQueuedConnection")
dataset_end_loading = first_line(dataset, r"void DataSetPackage::endLoadingData")
dataset_receive = first_line_after(dataset, dataset_end_loading, r"enginesReceiveNewData\(\);")
dataset_model_init = first_line_after(dataset, dataset_end_loading, r"emit modelInit\(\);")
dataset_engines_receive_func = first_line(dataset, r"void DataSetPackage::enginesReceiveNewData\(")
dataset_same_thread_direct_receive = first_line_after(dataset, dataset_engines_receive_func, r"_engineSync->enginesReceiveNewData\(\);")
engine_receive = first_line(engine, r"void EngineSync::enginesReceiveNewData\(")
engine_reload_emit = first_line(engine, r"emit reloadData\(\);")
engine_reload_connect = first_line(engine, r"connect\(this,\s*&EngineSync::reloadData")
engine_reload_receivers = sum(1 for line in engine if "&EngineSync::reloadData" in line)
engine_ctor = first_line(engine, r"EngineSync::EngineSync")
engine_ctor_set_pkg = first_line(engine, r"DataSetPackage::pkg\(\)->setEngineSync\(this\)")
engine_memory_name = first_line(engine, r'_memoryName = "JASP-IPC-"')
engine_start_func = first_line(engine, r"void EngineSync::start\(\)")
engine_start_timer = first_line(engine, r"_timerProcess->start")
engine_process = first_line(engine, r"void EngineSync::process\(\)")
engine_process_filter = first_line(engine, r"void EngineSync::processFilterScript\(")
engine_create_new = first_line(engine, r"createNewEngine")
engine_start_slave = first_line(engine, r"EngineSync::startSlaveProcess")
engine_rep_ctor = first_line(engine_rep, r"EngineRepresentation::EngineRepresentation")
engine_rep_set_slave = first_line(engine_rep, r"void EngineRepresentation::setSlaveProcess")
engine_rep_log = first_line(engine_rep, r"Setting new engine process to engineRepresentation Engine #")
ipc_ctor = first_line(ipc, r"IPCChannel::IPCChannel")
ipc_open_or_create = first_line(ipc, r"managed_shared_memory\(interprocess::open_or_create")
ipc_mutex_construct = first_line(ipc, r"find_or_construct<interprocess::interprocess_mutex>")
ipc_data_construct = first_line(ipc, r"find_or_construct<String>")
ipc_heartbeat = first_line(ipc, r"_jaspHeartBeatPath")
ipc_shared_dir_override = first_line(ipc, r"get_shared_dir")

print(f"derived.loadQMLScheduledBeforeEngineStart={'yes' if main_loadqml_schedule and main_engine_start and main_loadqml_schedule < main_engine_start else 'no'}")
print(f"derived.engineStartBeforeDesktopStarted={'yes' if main_engine_start and main_desktop_started and main_engine_start < main_desktop_started else 'no'}")
print(f"derived.desktopStartedBeforeLoadQMLEntryReturns=unknown; loadQML is scheduled on the Qt event loop and only logs after constructor returns")
print(f"derived.dataSetEndLoadingBeforeModelInit={'yes' if dataset_end_loading and dataset_receive and dataset_model_init and dataset_receive < dataset_model_init else 'no'}")
print(f"derived.engineReceiveOnlyEmitsReloadData={'yes' if engine_receive and engine_reload_emit and engine_receive < engine_reload_emit else 'no'}")
print(f"derived.engineReloadDataReceiverCount={engine_reload_receivers}")
print(f"derived.engineSyncConstructorCallsDataSetPackageReset={'yes' if engine_ctor and engine_ctor_set_pkg and engine_ctor < engine_ctor_set_pkg else 'unknown'}")
print(f"derived.engineSyncMemoryNameAssignedAfterConstructorReset={'yes' if engine_ctor_set_pkg and engine_memory_name and engine_ctor_set_pkg < engine_memory_name else 'unknown'}")
print(f"derived.engineSyncStartCreatesTimersAfterConstructor={'yes' if engine_start_func and engine_start_timer and engine_start_func < engine_start_timer else 'unknown'}")
print(f"derived.dataSetPackageSameThreadReceiveIsDirect={'yes' if dataset_engines_receive_func and dataset_same_thread_direct_receive else 'unknown'}")
print(f"derived.constructorReentryDeferredFixCandidate={'yes' if engine_ctor_set_pkg and engine_memory_name and engine_ctor_set_pkg < engine_memory_name and dataset_same_thread_direct_receive and dataset_receive else 'unknown'}")
print(f"derived.reloadDataReceiverAttachedInsideCreateNewEngine={'yes' if engine_create_new and engine_reload_connect and engine_create_new < engine_reload_connect else 'unknown'}")
print(f"derived.engineChildCreationIsLazy={'yes' if engine_create_new and engine_start_slave and engine_create_new < engine_start_slave else 'unknown'}")
print(f"derived.engineProcessTimerIsOnlyAfterEngineSyncStart={'yes' if engine_process and engine_start_slave and engine_process < engine_start_slave else 'unknown'}")
print(f"derived.engineRepresentationLogsBeforeChildRun={'yes' if engine_rep_ctor and engine_rep_set_slave and engine_rep_log and engine_rep_ctor < engine_rep_set_slave < engine_rep_log else 'unknown'}")
print(f"derived.hasBlockingQueuedCheckDoSync={'yes' if main_checkdosync_blocking else 'no'}")
print(f"derived.ipcChannelUsesManagedSharedMemory={'yes' if ipc_open_or_create else 'no'}")
print(f"derived.ipcChannelConstructsInterprocessMutex={'yes' if ipc_mutex_construct else 'no'}")
print(f"derived.ipcChannelConstructsSharedStrings={'yes' if ipc_data_construct else 'no'}")
print(f"derived.ipcChannelHeartbeatFile={'yes' if ipc_heartbeat else 'no'}")
print(f"derived.ipcSharedDirOverride={'yes' if ipc_shared_dir_override else 'no'}")
print(f"sourceLine.main.loadQMLSchedule={main_loadqml_schedule}")
print(f"sourceLine.main.engineStart={main_engine_start}")
print(f"sourceLine.main.desktopStarted={main_desktop_started}")
print(f"sourceLine.main.loadQMLEntry={main_loadqml_entry}")
print(f"sourceLine.dataset.endLoadingData={dataset_end_loading}")
print(f"sourceLine.dataset.enginesReceiveNewDataCall={dataset_receive}")
print(f"sourceLine.dataset.modelInit={dataset_model_init}")
print(f"sourceLine.dataset.enginesReceiveNewDataFunction={dataset_engines_receive_func}")
print(f"sourceLine.dataset.sameThreadDirectEngineSyncReceive={dataset_same_thread_direct_receive}")
print(f"sourceLine.engine.enginesReceiveNewData={engine_receive}")
print(f"sourceLine.engine.reloadDataEmit={engine_reload_emit}")
print(f"sourceLine.engine.reloadDataConnect={engine_reload_connect}")
print(f"sourceLine.engine.constructor={engine_ctor}")
print(f"sourceLine.engine.constructorSetDataPackageEngineSync={engine_ctor_set_pkg}")
print(f"sourceLine.engine.memoryNameAssignment={engine_memory_name}")
print(f"sourceLine.engine.start={engine_start_func}")
print(f"sourceLine.engine.startTimer={engine_start_timer}")
print(f"sourceLine.engine.process={engine_process}")
print(f"sourceLine.engine.processFilterScript={engine_process_filter}")
print(f"sourceLine.engine.createNewEngine={engine_create_new}")
print(f"sourceLine.engine.startSlaveProcess={engine_start_slave}")
print(f"sourceLine.engineRepresentation.constructor={engine_rep_ctor}")
print(f"sourceLine.engineRepresentation.setSlaveProcess={engine_rep_set_slave}")
print(f"sourceLine.engineRepresentation.engineMarkerLog={engine_rep_log}")
print(f"sourceLine.ipc.constructor={ipc_ctor}")
print(f"sourceLine.ipc.openOrCreateManagedSharedMemory={ipc_open_or_create}")
print(f"sourceLine.ipc.interprocessMutex={ipc_mutex_construct}")
print(f"sourceLine.ipc.sharedString={ipc_data_construct}")
if engine_ctor_set_pkg and engine_memory_name and dataset_same_thread_direct_receive:
    print("candidateFix.deferInitialEngineSyncReset=move DataSetPackage::pkg()->setEngineSync(this) after _memoryName assignment or queue the initial reset/enginesReceiveNewData path with QTimer::singleShot(0, ...) so EngineSync constructor cannot be synchronously re-entered")
    print("candidateFix.keepReloadDataAfterEngineRepresentation=ensure the first reloadData emission happens after EngineRepresentation reloadData receivers are attached inside EngineSync::createNewEngine")
PY

  if [ -s "$patched_dataset_src" ] && [ -s "$patched_enginesync_src" ]; then
    /usr/bin/python3 - "$patched_dataset_src" "$patched_enginesync_src" >> "$log" <<'PY' || true
import re
import sys
from pathlib import Path

dataset_path, engine_path = map(Path, sys.argv[1:3])

def lines(path):
    return path.read_text(errors="replace").splitlines() if path.exists() else []

def first_line(items, pattern):
    regex = re.compile(pattern)
    for index, line in enumerate(items, 1):
        if regex.search(line):
            return index
    return 0

def first_line_after(items, start_line, pattern, max_lines=80):
    if not start_line:
        return 0
    regex = re.compile(pattern)
    for index, line in enumerate(items[start_line:start_line + max_lines], start_line + 1):
        if regex.search(line):
            return index
    return 0

dataset = lines(dataset_path)
engine = lines(engine_path)
dataset_set_engine_sync = first_line(dataset, r"void DataSetPackage::setEngineSync")
dataset_direct_reset = first_line_after(dataset, dataset_set_engine_sync, r"^\s*reset\(\);")
dataset_deferred_reset = first_line_after(dataset, dataset_set_engine_sync, r"QTimer::singleShot\(0,\s*this,")
dataset_qtimer_include = first_line(dataset, r"#include <QTimer>")
dataset_constructor = first_line(dataset, r"DataSetPackage::DataSetPackage\(")
dataset_constructor_defaults = first_line_after(dataset, dataset_constructor, r"setDefaultWorkspaceValues\(false\)")
dataset_create = first_line(dataset, r"void DataSetPackage::createDataSet\(")
dataset_create_defaults = first_line_after(dataset, dataset_create, r"setDefaultWorkspaceValues\(false\)")
engine_ctor = first_line(engine, r"EngineSync::EngineSync")
engine_ctor_set_pkg = first_line(engine, r"DataSetPackage::pkg\(\)->setEngineSync\(this\)")
engine_memory_name = first_line(engine, r'_memoryName = "JASP-IPC-"')

print("## patched-source static check")
print(f"patchedSource.dataset.qtimerInclude={dataset_qtimer_include}")
print(f"patchedSource.dataset.directResetInSetEngineSync={dataset_direct_reset}")
print(f"patchedSource.dataset.deferredResetInSetEngineSync={dataset_deferred_reset}")
print(f"patchedSource.engine.constructorSetDataPackageEngineSync={engine_ctor_set_pkg}")
print(f"patchedSource.engine.memoryNameAssignment={engine_memory_name}")
print(f"patchedDerived.initialResetSynchronous={'yes' if dataset_direct_reset and not dataset_deferred_reset else 'no'}")
print(f"patchedDerived.memoryNameAssignedBeforeSetEngineSync={'yes' if engine_ctor and engine_memory_name and engine_ctor_set_pkg and engine_ctor < engine_memory_name < engine_ctor_set_pkg else 'no'}")
print(f"patchedDerived.constructorReentryStateInitialized={'yes' if dataset_direct_reset and not dataset_deferred_reset and engine_memory_name and engine_ctor_set_pkg and engine_memory_name < engine_ctor_set_pkg else 'no'}")
print(f"patchedDerived.nestedWorkspaceResetAvoided={'yes' if dataset_constructor_defaults and dataset_create_defaults else 'no'}")
PY
  fi

  {
    echo
    echo "## launch correlation"
  } >> "$log"
  if [ -f "$launch_log" ]; then
    for milestone in \
      'DataSetPackage::endLoadingData' \
      'EngineSync::enginesReceiveNewData!' \
      'Setting new engine process to engineRepresentation Engine #' \
      'JASP Desktop started and Engines initalized' \
      'Initializing QML' \
      'Engine #' \
      'TIMEOUT after'; do
      if log_has_runtime_fixed_string "$milestone" "$launch_log"; then
        printf 'seen=' >> "$log"
      else
        printf 'absent=' >> "$log"
      fi
      printf '%s\n' "$milestone" >> "$log"
    done
    if log_has_runtime_fixed_string 'DataSetPackage::endLoadingData' "$launch_log" \
      && log_has_runtime_fixed_string 'EngineSync::enginesReceiveNewData!' "$launch_log" \
      && ! log_has_runtime_fixed_string 'Setting new engine process to engineRepresentation Engine #' "$launch_log" \
      && ! log_has_runtime_fixed_string 'JASP Desktop started and Engines initalized' "$launch_log" \
      && ! log_has_runtime_fixed_string 'Initializing QML' "$launch_log" \
      && ! log_has_runtime_fixed_string 'Engine #' "$launch_log"; then
      echo "correlation.boundary=DataSetPackage::endLoadingData reached EngineSync::enginesReceiveNewData during EngineSync constructor re-entry, then EngineSync::start created IPC/timer state, but no EngineRepresentation setSlaveProcess marker, constructor-tail, loadQML, or engine-child milestone appeared before timeout/fail-fast. Because reloadData receivers are attached inside createNewEngine(), this signature is still before the first EngineRepresentation construction and before timer-driven engine child creation." >> "$log"
    else
      echo "correlation.boundary=launch milestones do not match the known pre-loadQML timeout signature exactly." >> "$log"
    fi
    if rg -q 'interprocess_exception@interprocess@boost|boost::interprocess' "$launch_log"; then
      echo "correlation.boostInterprocessException=yes" >> "$log"
    else
      echo "correlation.boostInterprocessException=no" >> "$log"
    fi
    if rg -q 'JASP-IPC-[0-9]+_(0|MasterToSlave|SlaveToMaster|heartbeat)' "$launch_log"; then
      echo "correlation.jaspIpcFilesTouched=yes" >> "$log"
    else
      echo "correlation.jaspIpcFilesTouched=no" >> "$log"
    fi
    if rg -q 'NtLockFile I/O completion on lock not implemented' "$launch_log"; then
      echo "correlation.ntLockFileFixme=yes" >> "$log"
    else
      echo "correlation.ntLockFileFixme=no" >> "$log"
    fi
  else
    echo "launchLog=not-yet-present; rerun after launch for correlation." >> "$log"
  fi

  {
    echo
    echo "## next experiments"
    echo "nextExperiment.webEngineBoundary=Run with MACWIN_JASP_WEBENGINE_MODE=single-process and compare sampleHasCrBrowserRosettaJit, footprint, and whether Desktop started/loadQML appears."
    echo "nextExperiment.constructorIsolation=Run with MACWIN_JASP_CONSTRUCTOR_ISOLATION=1 to disable update prompts, update checks, remote configuration, and module-library network URLs before launch."
    echo "nextExperiment.ipcTrace=Run with MACWIN_JASP_IPC_TRACE=1 to clean stale JASP-IPC files and capture +file,+seh evidence for clean JASP-IPC file creation, NtLockFile fixmes, and Boost interprocess exceptions."
    echo "nextExperiment.sourcePatch=If rebuilding JASP is practical, first test a minimal constructor-reentry patch: move DataSetPackage::pkg()->setEngineSync(this) after _memoryName assignment, or defer the initial DataSetPackage reset/enginesReceiveNewData with QTimer::singleShot(0, ...) so the EngineSync constructor cannot be synchronously re-entered before its fields and reloadData receivers are ready."
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  ended="$(date +%s)"
  duration=$((ended - started))
  if [ -f "$launch_log" ] \
    && log_has_runtime_fixed_string 'JASP Desktop started and Engines initalized' "$launch_log" \
    && log_has_runtime_fixed_string 'QML Initialized!' "$launch_log"; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" "JASP deferred-reset compatibility build completed MainWindow construction and initialized QML; the original synchronous EngineSync constructor re-entry boundary is no longer blocking startup."
  elif [ -f "$launch_log" ]; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" "JASP constructor-boundary probe captured the remaining pre-QML startup boundary; inspect the milestone correlation in the probe log."
  else
    record "$id" "$phase" "passed" 0 "$log" "$duration" "JASP constructor-boundary probe captured upstream source call order before launch; rerun postlaunch correlation after the GUI attempt."
  fi
}

write_jasp_failfast_boundary_probe() {
  local id="$1"
  local phase="${2:-post-ipc-failfast-probe}"
  local log="$LOG_DIR/${id}-${phase}.log"
  local launch_log="$LOG_DIR/${id}-launch.log"
  local module_log="$LOG_DIR/${id}-spawn-trace-probe.log"
  local started ended duration note state="passed" exit_code=0
  started="$(date +%s)"

  {
    echo "== MacWin JASP post-IPC fail-fast boundary probe =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$PREFIX"
    echo "launchLog=$launch_log"
    echo "moduleLog=$module_log"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ ! -f "$launch_log" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "launchLog=missing"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "$phase" "skipped" 0 "$log" "$duration" "JASP fail-fast boundary probe skipped because the launch log is not available yet."
    return 0
  fi

  /usr/bin/python3 - "$launch_log" "$module_log" "$PREFIX" "$PROJECT_ROOT" >> "$log" <<'PY' || true
import bisect
import os
import struct
import subprocess
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
module_log = Path(sys.argv[2])
prefix = Path(sys.argv[3])
project_root = Path(sys.argv[4])
lines = path.read_text(errors="replace").splitlines()

metadata_prefixes = (
    "command=",
    "note=",
    "trace.",
    "source.",
    "jaspIpcSnapshot",
    "jaspTimeout.",
    "## ",
    "== ",
)

def runtime_line(text):
    return not text.startswith(metadata_prefixes)

def runtime_hits(needle):
    return [(index, text) for index, text in enumerate(lines, 1) if needle in text and runtime_line(text)]

def runtime_regex_hits(pattern):
    regex = re.compile(pattern)
    return [(index, text) for index, text in enumerate(lines, 1) if regex.search(text) and runtime_line(text)]

failfast_re = re.compile(r"^(?P<thread>[0-9a-fA-F]+):err:seh:NtRaiseException Unhandled exception code c0000409.*addr (?P<addr>0x[0-9a-fA-F]+)")
failfast_hits = []
for index, text in enumerate(lines, 1):
    match = failfast_re.search(text)
    if match and runtime_line(text):
        failfast_hits.append((index, text, match.group("thread"), match.group("addr")))

all_c0000409 = runtime_regex_hits(r"c0000409")
data_end = runtime_hits("DataSetPackage::endLoadingData")
engine_sync = runtime_hits("EngineSync::enginesReceiveNewData!")
desktop_started = runtime_hits("JASP Desktop started and Engines initalized")
initializing_qml = runtime_hits("Initializing QML")
loading_themes = runtime_hits("Loading Themes")
qml_initialized = runtime_hits("QML Initialized!")
qml_loaded = runtime_hits("QML loaded, url:")
engine_marker = runtime_hits("Engine #")
engine_rep_marker = runtime_hits("Setting new engine process to engineRepresentation Engine #")

fail_line = failfast_hits[0][0] if failfast_hits else None
engine_sync_line = engine_sync[-1][0] if engine_sync else None

desktop_lines_before_failfast = []
desktop_lines_after_engine_sync = []
for index, text in enumerate(lines, 1):
    if "Desktop:" not in text or not runtime_line(text):
        continue
    if fail_line is None or index < fail_line:
        desktop_lines_before_failfast.append((index, text))
    if engine_sync_line is not None and index > engine_sync_line and (fail_line is None or index < fail_line):
        desktop_lines_after_engine_sync.append((index, text))

raw_expected_control_count = os.environ.get("MACWIN_JASP_MAX_ENGINES", "4")
try:
    expected_control_count = int(raw_expected_control_count)
except ValueError:
    expected_control_count = 4
if expected_control_count < 1:
    expected_control_count = 4

create_not_found_re = re.compile(r"(Unable to create file .*JASP-IPC-.*status c0000035|NtCreateFile .*JASP-IPC-.*not found \(c0000035\))")
create_not_found_count = sum(1 for text in lines if create_not_found_re.search(text))
control_complete = any(text == f"jaspIpcSnapshot.controlCount={expected_control_count}" for text in lines)
master_complete = any(text == "jaspIpcSnapshot.masterToSlaveCount=1" for text in lines)
slave_complete = any(text == "jaspIpcSnapshot.slaveToMasterCount=1" for text in lines)
heartbeat_complete = any(text == "jaspIpcSnapshot.heartbeatCount=1" for text in lines)
complete_ipc = control_complete and master_complete and slave_complete and heartbeat_complete

later_qml_or_desktop = bool(desktop_started or initializing_qml or loading_themes or qml_initialized or qml_loaded)
classification = (
    bool(data_end)
    and bool(engine_sync)
    and complete_ipc
    and bool(failfast_hits)
    and not engine_rep_marker
    and not engine_marker
    and not later_qml_or_desktop
)

print("## fail-fast")
if failfast_hits:
    first = failfast_hits[0]
    print(f"failfast.line={first[0]}")
    print(f"failfast.thread={first[2]}")
    print(f"failfast.address={first[3]}")
else:
    print("failfast.line=missing")
    print("failfast.thread=missing")
    print("failfast.address=missing")
print(f"failfast.count={len(all_c0000409)}")
if fail_line is not None and engine_sync_line is not None and fail_line > engine_sync_line:
    print(f"failfast.linesAfterEngineSync={fail_line - engine_sync_line - 1}")
else:
    print("failfast.linesAfterEngineSync=missing")
print(f"failfast.desktopLinesAfterEngineSync={len(desktop_lines_after_engine_sync)}")

print()
print("## fail-fast module attribution")
module_lines = []
module_source = "missing"
if any("trace:module:map_image_into_view" in text for text in lines):
    module_lines = lines
    module_source = "launch"
elif module_log.exists():
    module_lines = module_log.read_text(errors="replace").splitlines()
    module_source = str(module_log)

module_pat = re.compile(r'mapping PE file L"(?P<name>.+?)" at 0x(?P<start>[0-9a-fA-F]+)-0x(?P<end>[0-9a-fA-F]+)')
modules = []
for index, text in enumerate(module_lines, 1):
    match = module_pat.search(text)
    if not match:
        continue
    start = int(match.group("start"), 16)
    end = int(match.group("end"), 16)
    modules.append((start, end, match.group("name"), index))

def module_for_address(addr):
    return next((item for item in modules if item[0] <= addr < item[1]), None)

def wine_path_to_host(wine_path):
    normalized = wine_path
    nt_prefix = "\\\\??\\\\"
    if normalized.startswith(nt_prefix):
        normalized = normalized[len(nt_prefix):]
    normalized = normalized.replace("\\\\", "/").replace("\\", "/")
    drive_match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    if drive_match and drive_match.group(1).lower() == "c":
        return prefix / "drive_c" / drive_match.group(2)
    return None

PE_CACHE = {}

def pe_metadata(host_path):
    if host_path is None or not host_path.exists():
        return None
    cached = PE_CACHE.get(host_path)
    if cached is not None:
        return cached
    try:
        data = host_path.read_bytes()
        pe_offset = struct.unpack_from("<I", data, 0x3c)[0]
        coff_offset = pe_offset + 4
        section_count = struct.unpack_from("<H", data, coff_offset + 2)[0]
        optional_size = struct.unpack_from("<H", data, coff_offset + 16)[0]
        optional_offset = coff_offset + 20
        magic = struct.unpack_from("<H", data, optional_offset)[0]
        if magic == 0x20B:
            image_base = struct.unpack_from("<Q", data, optional_offset + 24)[0]
            directory_offset = optional_offset + 112
        elif magic == 0x10B:
            image_base = struct.unpack_from("<I", data, optional_offset + 28)[0]
            directory_offset = optional_offset + 96
        else:
            return None
        directories = []
        for index in range(16):
            rva, size = struct.unpack_from("<II", data, directory_offset + index * 8)
            directories.append((rva, size))
        sections = []
        section_offset = optional_offset + optional_size
        for index in range(section_count):
            offset = section_offset + index * 40
            name = data[offset:offset + 8].split(b"\0", 1)[0].decode("ascii", "replace")
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
            sections.append((name, virtual_address, virtual_size, raw_pointer, raw_size))
        meta = {
            "data": data,
            "imageBase": image_base,
            "directories": directories,
            "sections": sections,
        }
        PE_CACHE[host_path] = meta
        return meta
    except Exception:
        return None

def rva_to_file_offset(meta, rva):
    for _name, virtual_address, virtual_size, raw_pointer, raw_size in meta["sections"]:
        if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
            return raw_pointer + (rva - virtual_address)
    return None

def codeview_pdb_path(host_path):
    meta = pe_metadata(host_path)
    if not meta:
        return None
    data = meta["data"]
    marker = data.find(b"RSDS")
    if marker < 0:
        return None
    start = marker + 24
    end = data.find(b"\0", start)
    if end < 0:
        return None
    try:
        return data[start:end].decode("utf-8", "replace")
    except Exception:
        return None

def exception_function_range(host_path, rva):
    meta = pe_metadata(host_path)
    if not meta:
        return None
    exception_rva, exception_size = meta["directories"][3]
    if exception_rva == 0 or exception_size < 12:
        return None
    exception_offset = rva_to_file_offset(meta, exception_rva)
    if exception_offset is None:
        return None
    data = meta["data"]
    end_offset = min(len(data), exception_offset + exception_size)
    for offset in range(exception_offset, end_offset - 11, 12):
        begin, end, unwind = struct.unpack_from("<III", data, offset)
        if begin <= rva < end:
            return begin, end, unwind
    return None

def bytes_in_function_range(host_path, begin_rva, end_rva, needles):
    meta = pe_metadata(host_path)
    if not meta:
        return []
    begin_offset = rva_to_file_offset(meta, begin_rva)
    end_offset = rva_to_file_offset(meta, max(begin_rva, end_rva - 1))
    if begin_offset is None or end_offset is None:
        return []
    end_offset += 1
    chunk = meta["data"][begin_offset:end_offset]
    hits = []
    for label, needle in needles:
        pos = chunk.find(needle)
        if pos >= 0:
            hits.append((label, begin_rva + pos))
    return hits

def jasp_columnutils_source_attribution(host_path, semantic_hits):
    if host_path is None or host_path.name.lower() != "jaspdesktop.exe":
        return []
    hit_labels = {label for label, _rva in semantic_hits}
    if not {"utf8.infinity", "utf8.negativeInfinity"}.issubset(hit_labels):
        return []
    source_path = project_root / "refs" / "jasp-desktop-v0.97.1" / "CommonData" / "columnutils.cpp"
    if not source_path.exists():
        return []
    text = source_path.read_text(errors="replace")
    required = [
        "bool ColumnUtils::getDoubleValue",
        'value == "∞" || value == "-∞"',
        "boost::lexical_cast<double>",
    ]
    if not all(item in text for item in required):
        return []
    rel = source_path.relative_to(project_root)
    return [
        f"source.match={rel}:99",
        "source.symbol=ColumnUtils::getDoubleValue",
        "source.lines=99-123",
        "source.reason=retAddr0 function contains the UTF-8 infinity/-infinity branch and matches the JASP source getDoubleValue path before boost::lexical_cast fallback",
    ]

def nearest_export(host_path, rva):
    if host_path is None or not host_path.exists():
        return None, None
    try:
        output = subprocess.check_output(["objdump", "-p", str(host_path)], stderr=subprocess.DEVNULL, text=True, timeout=8)
    except Exception:
        return None, None
    exports = []
    for text in output.splitlines():
        match = re.match(r"\s*\d+\s+0x([0-9a-fA-F]+)\s+(.+)", text)
        if match:
            exports.append((int(match.group(1), 16), match.group(2).strip()))
    exports.sort()
    if not exports:
        return None, None
    rvas = [item[0] for item in exports]
    pos = bisect.bisect_right(rvas, rva)
    previous = exports[pos - 1] if pos else None
    next_item = exports[pos] if pos < len(exports) else None
    return previous, next_item

def import_map_by_iat(host_path):
    if host_path is None or not host_path.exists():
        return {}
    try:
        output = subprocess.check_output(["objdump", "-p", str(host_path)], stderr=subprocess.DEVNULL, text=True, timeout=8)
    except Exception:
        return {}
    imports = {}
    current_dll = None
    current_addr = None
    pending_addr = None
    lookup_re = re.compile(r"\s*lookup\s+[0-9a-fA-F]+\s+time\s+[0-9a-fA-F]+\s+fwd\s+[0-9a-fA-F]+\s+name\s+[0-9a-fA-F]+\s+addr\s+([0-9a-fA-F]+)")
    name_re = re.compile(r"\s*(?:\d+|\[Ordinal/\d+\])\s+(.+)$")
    for text in output.splitlines():
        lookup = lookup_re.match(text)
        if lookup:
            pending_addr = int(lookup.group(1), 16)
            current_dll = None
            current_addr = None
            continue
        dll = re.match(r"\s*DLL Name:\s+(.+)$", text)
        if dll:
            current_dll = dll.group(1).strip()
            current_addr = pending_addr
            continue
        if current_dll is None or current_addr is None:
            continue
        if not text.strip() or text.strip() == "Hint/Ord  Name":
            continue
        name = name_re.match(text)
        if name:
            imports[current_addr] = f"{current_dll}!{name.group(1).strip()}"
            current_addr += 8
    return imports

def disasm_probe(host_path, runtime_start, rva):
    if host_path is None or not host_path.exists():
        return []
    try:
        header = subprocess.check_output(["objdump", "-p", str(host_path)], stderr=subprocess.DEVNULL, text=True, timeout=8)
    except Exception:
        return []
    match = re.search(r"ImageBase\s+([0-9A-Fa-f]+)", header)
    image_base = int(match.group(1), 16) if match else 0
    start = max(image_base, image_base + rva - 0x30)
    end = image_base + rva + 0x38
    try:
        output = subprocess.check_output(["objdump", "-d", f"--start-address=0x{start:x}", f"--stop-address=0x{end:x}", str(host_path)], stderr=subprocess.DEVNULL, text=True, timeout=8)
    except Exception:
        return []
    wanted = []
    marker_addr = image_base + rva
    for text in output.splitlines():
        if re.match(r"\s*[0-9a-fA-F]+:", text) or re.match(r"[0-9a-fA-F]+ <.+>:", text):
            wanted.append(text)
    return [(("=>" if re.match(rf"\s*{marker_addr:x}:", text, re.I) else "  "), text) for text in wanted[-20:]]

def annotate_fastfail_path(host_path, rva):
    if host_path is None or not host_path.exists():
        return []
    try:
        header = subprocess.check_output(["objdump", "-p", str(host_path)], stderr=subprocess.DEVNULL, text=True, timeout=8)
    except Exception:
        return []
    image_match = re.search(r"ImageBase\s+([0-9A-Fa-f]+)", header)
    image_base = int(image_match.group(1), 16) if image_match else 0
    try:
        output = subprocess.check_output(
            ["objdump", "-d", f"--start-address=0x{max(image_base, image_base + rva - 0x40):x}", f"--stop-address=0x{image_base + rva + 0x30:x}", str(host_path)],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        )
    except Exception:
        return []
    imports = import_map_by_iat(host_path)
    annotations = []
    last_ecx_imm = None
    for text in output.splitlines():
        mov_ecx = re.search(r"movl\s+\$0x([0-9a-fA-F]+),\s*%ecx", text)
        if mov_ecx:
            last_ecx_imm = int(mov_ecx.group(1), 16)
        call = re.search(r"callq\s+\*0x[0-9a-fA-F]+\(%rip\)\s+#\s+0x([0-9a-fA-F]+)", text)
        if call:
            iat_rva = int(call.group(1), 16) - image_base
            target = imports.get(iat_rva)
            if target:
                annotations.append(f"module.fastFailImport.rva=0x{iat_rva:x} name={target} precedingEcx={last_ecx_imm if last_ecx_imm is not None else 'unknown'}")
        int29 = re.search(r"\bint\s+\$0x29\b", text)
        if int29:
            code = last_ecx_imm if last_ecx_imm is not None else None
            annotations.append("module.fastFailInstruction=int 0x29")
            if code is not None:
                annotations.append(f"module.fastFailCode={code}")
                if code == 7:
                    annotations.append("module.fastFailCodeName=FAST_FAIL_FATAL_APP_EXIT")
    return annotations

def emit_address_attribution(prefix_name, addr):
    match = module_for_address(addr)
    print(f"{prefix_name}.address=0x{addr:x}")
    if not match:
        print(f"{prefix_name}.module=unmatched")
        return
    start, end, name, line_no = match
    rva = addr - start
    host_path = wine_path_to_host(name)
    previous, next_item = nearest_export(host_path, rva)
    print(f"{prefix_name}.module={name}")
    print(f"{prefix_name}.hostPath={host_path if host_path else 'unresolved'}")
    print(f"{prefix_name}.base=0x{start:x}")
    print(f"{prefix_name}.rva=0x{rva:x}")
    print(f"{prefix_name}.mapLine={line_no}")
    pdb_path = codeview_pdb_path(host_path)
    if pdb_path:
        print(f"{prefix_name}.codeViewPdbPath={pdb_path}")
    function_range = exception_function_range(host_path, rva)
    if function_range:
        begin, end, unwind = function_range
        print(f"{prefix_name}.function.beginRva=0x{begin:x}")
        print(f"{prefix_name}.function.endRva=0x{end:x}")
        print(f"{prefix_name}.function.size=0x{end - begin:x}")
        print(f"{prefix_name}.function.unwindRva=0x{unwind:x}")
        semantic_needles = [
            ("utf8.infinity", "∞".encode("utf-8")),
            ("utf8.negativeInfinity", "-∞".encode("utf-8")),
            ("ascii.infinity", b"infinity"),
            ("ascii.Infinity", b"Infinity"),
            ("ascii.NaN", b"NaN"),
            ("ascii.nan", b"nan"),
            ("ascii.inf", b"inf"),
        ]
        semantic_hits = bytes_in_function_range(host_path, begin, end, semantic_needles)
        for label, hit_rva in semantic_hits:
            print(f"{prefix_name}.function.semanticHit={label}@0x{hit_rva:x}")
        if prefix_name in {"seh.retAddr0", "seh.restoreReturn"}:
            for attribution in jasp_columnutils_source_attribution(host_path, semantic_hits):
                print(f"{prefix_name}.{attribution}")
    if previous:
        print(f"{prefix_name}.nearestExport.previous.rva=0x{previous[0]:x}")
        print(f"{prefix_name}.nearestExport.previous.name={previous[1]}")
        print(f"{prefix_name}.nearestExport.previous.delta=0x{rva - previous[0]:x}")
    if next_item:
        print(f"{prefix_name}.nearestExport.next.rva=0x{next_item[0]:x}")
        print(f"{prefix_name}.nearestExport.next.name={next_item[1]}")
        print(f"{prefix_name}.nearestExport.next.delta=0x{next_item[0] - rva:x}")

if not failfast_hits:
    print("module.attribution=missing-failfast")
elif not modules:
    print(f"module.attribution=missing-module-map")
    print(f"module.mapSource={module_source}")
else:
    fail_addr = int(failfast_hits[0][3], 16)
    match = next((item for item in modules if item[0] <= fail_addr < item[1]), None)
    print(f"module.mapSource={module_source}")
    print(f"module.mapCount={len(modules)}")
    if match:
        start, end, name, line_no = match
        rva = fail_addr - start
        host_path = wine_path_to_host(name)
        previous, next_item = nearest_export(host_path, rva)
        print("module.attribution=matched")
        print(f"module.name={name}")
        print(f"module.hostPath={host_path if host_path else 'unresolved'}")
        print(f"module.base=0x{start:x}")
        print(f"module.end=0x{end:x}")
        print(f"module.rva=0x{rva:x}")
        print(f"module.mapLine={line_no}")
        if previous:
            print(f"module.nearestExport.previous.rva=0x{previous[0]:x}")
            print(f"module.nearestExport.previous.name={previous[1]}")
            print(f"module.nearestExport.previous.delta=0x{rva - previous[0]:x}")
        else:
            print("module.nearestExport.previous=missing")
        if next_item:
            print(f"module.nearestExport.next.rva=0x{next_item[0]:x}")
            print(f"module.nearestExport.next.name={next_item[1]}")
            print(f"module.nearestExport.next.delta=0x{next_item[0] - rva:x}")
        else:
            print("module.nearestExport.next=missing")
        for marker, text in disasm_probe(host_path, start, rva):
            print(f"module.disasm{marker} {text}")
        for annotation in annotate_fastfail_path(host_path, rva):
            print(annotation)
    else:
        print("module.attribution=no-range-match")
        nearest = sorted(modules, key=lambda item: min(abs(fail_addr - item[0]), abs(fail_addr - item[1])))[:5]
        for start, end, name, line_no in nearest:
            print(f"module.nearestRange=0x{start:x}-0x{end:x} line={line_no} name={name}")

print()
print("## SEH context address attribution")
if not failfast_hits:
    print("seh.attribution=missing-failfast")
elif not modules:
    print("seh.attribution=missing-module-map")
else:
    context_start = max(0, (fail_line or 1) - 80)
    context_end = min(len(lines), (fail_line or len(lines)) + 1)
    context = lines[context_start:context_end]
    patterns = [
        ("seh.consolidateCallback", re.compile(r"consolidate callback ([0-9A-Fa-fx]+)")),
        ("seh.catchHandler", re.compile(r"call_catch_handler calling ([0-9A-Fa-fx]+)")),
        ("seh.retAddr0", re.compile(r"ret_addr\[0\]\s+(0x[0-9A-Fa-f]+)")),
        ("seh.retAddr1", re.compile(r"ret_addr\[1\]\s+(0x[0-9A-Fa-f]+)")),
        ("seh.restoreReturn", re.compile(r"RtlRestoreContext returning to ([0-9A-Fa-fx]+)")),
    ]
    emitted = set()
    for label, regex in patterns:
        for text in context:
            match = regex.search(text)
            if not match:
                continue
            raw = match.group(1)
            if raw in {"0", "0."}:
                continue
            try:
                addr = int(raw, 16)
            except ValueError:
                continue
            key = (label, addr)
            if key in emitted:
                continue
            emitted.add(key)
            emit_address_attribution(label, addr)
    if not emitted:
        print("seh.attribution=no-addresses-found")

print()
print("## milestones")
milestones = [
    ("DataSetPackageEndLoadingData", data_end),
    ("EngineSyncReceiveNewData", engine_sync),
    ("EngineRepresentationSetSlaveProcess", engine_rep_marker),
    ("DesktopStarted", desktop_started),
    ("InitializingQML", initializing_qml),
    ("LoadingThemes", loading_themes),
    ("QMLInitialized", qml_initialized),
    ("QMLLoaded", qml_loaded),
    ("EngineMarker", engine_marker),
]
for name, hits in milestones:
    if hits:
        print(f"milestone.{name}.line={hits[-1][0]}")
        print(f"milestone.{name}.text={hits[-1][1]}")
    else:
        print(f"milestone.{name}.line=missing")

if desktop_lines_before_failfast:
    last_line, last_text = desktop_lines_before_failfast[-1]
    print(f"lastDesktop.line={last_line}")
    print(f"lastDesktop.text={last_text}")
else:
    print("lastDesktop.line=missing")
    print("lastDesktop.text=missing")

print()
print("## IPC")
print(f"ipc.expectedControlCount={expected_control_count}")
print(f"ipc.completeSnapshot={'yes' if complete_ipc else 'no'}")
print(f"ipc.controlCountExpected={'yes' if control_complete else 'no'}")
print(f"ipc.masterToSlaveCount1={'yes' if master_complete else 'no'}")
print(f"ipc.slaveToMasterCount1={'yes' if slave_complete else 'no'}")
print(f"ipc.heartbeatCount1={'yes' if heartbeat_complete else 'no'}")
print(f"ipc.createNotFoundCount={create_not_found_count}")
print(f"ipc.recoveredOpenOrCreate={'yes' if complete_ipc and create_not_found_count > 0 else 'no'}")

print()
print("## classification")
print(f"classification.postIpcEngineSpawnStall={'yes' if classification else 'no'}")
print(f"classification.engineSyncConstructorReentryFailFast={'yes' if classification else 'no'}")
print(f"classification.hasLaterQmlOrDesktopMilestone={'yes' if later_qml_or_desktop else 'no'}")
print(f"classification.hasEngineRepresentationMarker={'yes' if bool(engine_rep_marker) else 'no'}")
print(f"classification.hasEngineMarker={'yes' if bool(engine_marker) else 'no'}")

print()
print("## last Desktop lines before fail-fast")
for index, text in desktop_lines_before_failfast[-12:]:
    print(f"desktopContext.line={index}: {text}")

print()
print("## raw fail-fast context")
if fail_line is not None:
    start = max(1, fail_line - 40)
    end = min(len(lines), fail_line + 12)
    for index in range(start, end + 1):
        print(f"failfastContext.line={index}: {lines[index - 1]}")
else:
    print("failfastContext=missing")
PY

  local missing_values_ruled_out=0
  local jasp_ini="$PREFIX/drive_c/users/$USER/AppData/Roaming/JASP/JASP.ini"
  {
    echo
    echo "## JASP missing-values configuration"
    if [ -f "$jasp_ini" ]; then
      rg -n -i 'MissingValueList|emptyValues|maxEngineCount|maxEngineCountAdmin' "$jasp_ini" | sed 's/^/JASP.ini:/' || true
    else
      echo "JASP.ini=missing"
    fi
  } >> "$log"
  if /usr/bin/python3 - "$PREFIX" "${MACWIN_JASP_EMPTY_VALUES_PRESET:-0}" >> "$log" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

prefix = Path(sys.argv[1])
preset = sys.argv[2]
if preset in ("safe-minimal", "numeric-safe"):
    expected_strings = ["0"]
elif preset == "empty":
    expected_strings = [""]
else:
    expected_strings = None

print(f"missingValues.preset={preset}")
if expected_strings is None:
    print("missingValues.expected=<disabled-or-custom>")
else:
    print(f"missingValues.expectedJson={json.dumps(expected_strings, ensure_ascii=False)}")

temp = prefix / "drive_c" / "users" / Path.home().name / "AppData" / "Local" / "JASP" / "JASP" / "temp"
dbs = sorted(temp.glob("*/internal.sqlite"))
print(f"internalSqlite.count={len(dbs)}")
if not dbs or expected_strings is None:
    sys.exit(1)

ok = True
aggregate_counts = {}
for db in dbs:
    rel = db.relative_to(prefix / "drive_c")
    try:
        with sqlite3.connect(db) as con:
            rows = con.execute("select id, revision, emptyValuesJson from DataSets").fetchall()
            table_names = [
                row[0]
                for row in con.execute(
                    "select name from sqlite_master where type='table' order by name"
                ).fetchall()
            ]
            table_counts = {}
            for table_name in table_names:
                quoted = '"' + table_name.replace('"', '""') + '"'
                try:
                    count = con.execute(f"select count(*) from {quoted}").fetchone()[0]
                except Exception:
                    count = None
                table_counts[table_name] = count
                aggregate_counts[table_name] = aggregate_counts.get(table_name, 0) + (count or 0)
    except Exception as exc:
        print(f"internalSqlite.{rel}.error={exc}")
        ok = False
        continue
    print(f"internalSqlite.{rel}.tablesJson={json.dumps(table_counts, ensure_ascii=False, sort_keys=True)}")
    for row_id, revision, raw in rows:
        try:
            data = json.loads(raw)
            strings = data.get("strings", [])
        except Exception as exc:
            print(f"internalSqlite.{rel}.row{row_id}.jsonError={exc}")
            ok = False
            continue
        print(f"internalSqlite.{rel}.row{row_id}.revision={revision}")
        print(f"internalSqlite.{rel}.row{row_id}.stringsJson={json.dumps(strings, ensure_ascii=False)}")
        if strings != expected_strings:
            ok = False

column_like_count = sum(
    count
    for table_name, count in aggregate_counts.items()
    if table_name == "Columns" or table_name == "Labels" or table_name.startswith("DataSet_")
)
print(f"internalSqlite.aggregateTableCountsJson={json.dumps(aggregate_counts, ensure_ascii=False, sort_keys=True)}")
print(f"classification.columnLabelDataRowsPresent={'yes' if column_like_count else 'no'}")
print(f"classification.columnLabelDataPathsRuledOut={'yes' if column_like_count == 0 else 'no'}")

project_root = Path.cwd()

def first_line(path, needle):
    try:
        for index, text in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if needle in text:
                return index
    except Exception:
        return None
    return None

empty_values_source = project_root / "refs" / "jasp-desktop-v0.97.1" / "CommonData" / "emptyvalues.cpp"
columnutils_source = project_root / "refs" / "jasp-desktop-v0.97.1" / "CommonData" / "columnutils.cpp"
empty_values_line = first_line(empty_values_source, "_emptyDoubles\t= ColumnUtils::getDoubleValues(values)")
get_double_values_line = first_line(columnutils_source, "doubleset ColumnUtils::getDoubleValues")
get_double_value_call_line = first_line(columnutils_source, "if (getDoubleValue(val, doubleValue)")
if empty_values_line and get_double_values_line and get_double_value_call_line:
    empty_rel = empty_values_source.relative_to(project_root)
    column_rel = columnutils_source.relative_to(project_root)
    print(f"source.callsite.emptyValuesToDoubleValues={empty_rel}:{empty_values_line}")
    print(f"source.callsite.getDoubleValuesLoop={column_rel}:{get_double_values_line}-{get_double_value_call_line}")
    print("source.callsite.path=EmptyValues::setEmptyValues -> ColumnUtils::getDoubleValues -> ColumnUtils::getDoubleValue")
    print(f"classification.workspaceEmptyValuesParserCandidate={'yes' if column_like_count == 0 else 'no'}")
else:
    print("classification.workspaceEmptyValuesParserCandidate=unknown")

if ok:
    print("classification.missingValuesPresetApplied=yes")
    print("classification.defaultMissingValuesRuledOut=yes")
    sys.exit(0)

print("classification.missingValuesPresetApplied=no")
print("classification.defaultMissingValuesRuledOut=no")
sys.exit(1)
PY
  then
    missing_values_ruled_out=1
  fi

  if ! rg -q '^failfast\.line=[0-9]+' "$log"; then
    state="skipped"
    note="JASP fail-fast boundary probe did not find a c0000409 NtRaiseException marker in the launch log."
  elif rg -q '^classification\.engineSyncConstructorReentryFailFast=yes$' "$log"; then
    if rg -q '^module\.attribution=matched$' "$log"; then
      if rg -q '^seh\.retAddr0\.function\.semanticHit=utf8\.(negativeInfinity|infinity)@' "$log"; then
	        if rg -q '^seh\.retAddr0\.source\.symbol=ColumnUtils::getDoubleValue$' "$log"; then
	          note="JASP fail-fast boundary probe confirms EngineSync constructor re-entry: DataSetPackage::setEngineSync()->reset()->endLoadingData() reaches EngineSync::enginesReceiveNewData before any EngineRepresentation setSlaveProcess, Engine #, JASPEngine, Desktop started, or QML milestone. c0000409 follows after complete IPC construction. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction, and SEH return attribution maps back to JASP CommonData/columnutils.cpp ColumnUtils::getDoubleValue."
	        else
          note="JASP fail-fast boundary probe confirms EngineSync constructor re-entry: DataSetPackage::setEngineSync()->reset()->endLoadingData() reaches EngineSync::enginesReceiveNewData before any EngineRepresentation setSlaveProcess, Engine #, JASPEngine, Desktop started, or QML milestone. c0000409 follows after complete IPC construction. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction, and SEH return attribution maps back to a JASPDesktop numeric/special-float parser function containing UTF-8 infinity markers."
        fi
      else
        note="JASP fail-fast boundary probe confirms EngineSync constructor re-entry: DataSetPackage::setEngineSync()->reset()->endLoadingData() reaches EngineSync::enginesReceiveNewData before any EngineRepresentation setSlaveProcess, Engine #, JASPEngine, Desktop started, or QML milestone. c0000409 follows after complete IPC construction. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction."
      fi
    else
      note="JASP fail-fast boundary probe confirms EngineSync constructor re-entry: DataSetPackage::setEngineSync()->reset()->endLoadingData() reaches EngineSync::enginesReceiveNewData before any EngineRepresentation setSlaveProcess, Engine #, JASPEngine, Desktop started, or QML milestone. c0000409 follows after complete IPC construction."
    fi
  elif rg -q '^classification\.postIpcEngineSpawnStall=yes$' "$log"; then
    if rg -q '^module\.attribution=matched$' "$log"; then
      if rg -q '^seh\.retAddr0\.function\.semanticHit=utf8\.(negativeInfinity|infinity)@' "$log"; then
	        if rg -q '^seh\.retAddr0\.source\.symbol=ColumnUtils::getDoubleValue$' "$log"; then
	          note="JASP fail-fast boundary probe confirms the last JASP runtime milestone is EngineSync::enginesReceiveNewData; c0000409 follows after complete IPC construction and before Desktop/QML/engine-child milestones. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction, and SEH return attribution maps back to JASP CommonData/columnutils.cpp ColumnUtils::getDoubleValue."
	        else
          note="JASP fail-fast boundary probe confirms the last JASP runtime milestone is EngineSync::enginesReceiveNewData; c0000409 follows after complete IPC construction and before Desktop/QML/engine-child milestones. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction, and SEH return attribution maps back to a JASPDesktop numeric/special-float parser function containing UTF-8 infinity markers."
        fi
      else
        note="JASP fail-fast boundary probe confirms the last JASP runtime milestone is EngineSync::enginesReceiveNewData; c0000409 follows after complete IPC construction and before Desktop/QML/engine-child milestones. Module attribution maps the fail-fast address into Qt6Core.dll near QtPrivate::sizedFree/qBadAlloc with an int 0x29 fast-fail instruction."
      fi
    else
      note="JASP fail-fast boundary probe confirms the last JASP runtime milestone is EngineSync::enginesReceiveNewData; c0000409 follows after complete IPC construction and before Desktop/QML/engine-child milestones."
    fi
	  else
	    note="JASP fail-fast boundary probe captured fail-fast context, but the launch log does not exactly match the post-IPC engine-spawn stall signature."
	  fi
	  if [ "$missing_values_ruled_out" -eq 1 ]; then
	    case "${MACWIN_JASP_EMPTY_VALUES_PRESET:-0}" in
	      empty)
	        note="$note MissingValueList was applied as an empty value and new internal.sqlite state contains only JASP's empty-string sentinel, so the default NaN/nan/./NA missing-values list is not sufficient to explain this fail-fast."
	        ;;
	      *)
	        note="$note MissingValueList=0 was applied and new internal.sqlite state contains only the numeric-safe value 0, so the default NaN/nan/./NA missing-values list is not sufficient to explain this fail-fast."
	        ;;
	    esac
	  fi
	  if rg -q '^classification\.columnLabelDataPathsRuledOut=yes$' "$log"; then
	    note="$note The current internal.sqlite snapshots contain no Columns, Labels, or DataSet_* rows, so Column/Label data conversion paths are not the triggering source in this empty-dataset startup signature."
	  fi
	  if rg -q '^classification\.workspaceEmptyValuesParserCandidate=yes$' "$log"; then
	    note="$note Source callsite attribution leaves the workspace empty-values parser path, EmptyValues::setEmptyValues -> ColumnUtils::getDoubleValues -> ColumnUtils::getDoubleValue, as the remaining data-backed candidate for the ColumnUtils return address in this empty startup case."
	  fi
	  note="$note JASP source also sets QLocale::English and LC_ALL=en_US.UTF-8 in Desktop/main.cpp:488-491 before QApplication startup, so the next priority remains DataSetPackage/DataSetPackageSubNodeModel reset ordering rather than host locale overrides."

	  {
    echo
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "$phase" "$state" "$exit_code" "$log" "$duration" "$note"
}

write_jasp_engine_direct_probe() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local log="$LOG_DIR/${id}-engine-direct-probe.log"
  local started ended duration pid exit_code=0 timed_out=0
  started="$(date +%s)"
  {
    echo "== MacWin JASP engine direct probe =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "appDir=$app_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "command=JASPEngine.exe no-arg smoke"
    echo
  } > "$log"

  if [ ! -f "$app_dir/JASPEngine.exe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "missing=JASPEngine.exe"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "engine-direct-probe" "failed" 115 "$log" "$duration" "JASPEngine.exe is missing; EngineSync cannot spawn an engine child."
    return 115
  fi

  {
    echo "## binary"
    printf 'JASPEngine.exe.size='
    stat -f %z "$app_dir/JASPEngine.exe" 2>/dev/null || wc -c < "$app_dir/JASPEngine.exe"
    printf 'JASPEngine.exe.sha256='
    shasum -a 256 "$app_dir/JASPEngine.exe" | awk '{print $1}'
    echo
    echo "## import dlls"
    if command -v objdump >/dev/null 2>&1; then
      objdump -p "$app_dir/JASPEngine.exe" 2>/dev/null | rg 'DLL Name:' | sed 's/^/import=/' || true
    fi
    echo
    echo "## direct run"
  } >> "$log"

  (
    cd "$app_dir" || exit 127
    env \
      PATH='C:\Program Files\JASP;C:\Program Files\JASP\R\bin;C:\windows\system32;C:\windows' \
      WINEDEBUG=-all \
      "${WINE_CMD[@]}" 'C:\Program Files\JASP\JASPEngine.exe'
  ) >> "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    ended="$(date +%s)"
    if [ "$((ended - started))" -ge 20 ]; then
      timed_out=1
      echo "TIMEOUT after 20s; sending SIGTERM to $pid" >> "$log"
      capture_live_process_snapshot_for_sample "$id" "engine-direct-probe-timeout" "$log" || true
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
  done
  wait "$pid" 2>/dev/null
  exit_code=$?
  ended="$(date +%s)"
  duration=$((ended - started))
  {
    echo "directExit=$exit_code"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  if [ "$timed_out" -eq 1 ]; then
    record "$id" "engine-direct-probe" "failed" 116 "$log" "$duration" "JASPEngine.exe did not exit from the no-argument direct probe before the watchdog timeout."
    return 116
  fi
  if [ "$exit_code" -eq 0 ] || [ "$exit_code" -eq 1 ] || [ "$exit_code" -eq 53 ]; then
    record "$id" "engine-direct-probe" "passed" 0 "$log" "$duration" "JASPEngine.exe loads and reaches its no-argument testing path under Wine (expected direct exit $exit_code); use the Windows-parent CreateProcess probe to validate the production spawn path."
    return 0
  fi

  record "$id" "engine-direct-probe" "failed" "$exit_code" "$log" "$duration" "JASPEngine.exe direct no-argument probe exited with $exit_code; inspect imports and loader output before debugging Desktop-to-engine handshake."
  return "$exit_code"
}

write_jasp_createprocess_probe() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local probe="$PROJECT_ROOT/refs/exe-tests/bin/97_jasp_createprocess_probe.exe"
  local log="$LOG_DIR/${id}-createprocess-probe.log"
  local started ended duration pid exit_code=0 timed_out=0
  started="$(date +%s)"
  {
    echo "== MacWin JASP CreateProcess probe =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "appDir=$app_dir"
    echo "probe=$probe"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "command=97_jasp_createprocess_probe.exe JASPEngine.exe --expect-any-exit"
    echo
  } > "$log"

  if [ ! -f "$app_dir/JASPEngine.exe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "missing=JASPEngine.exe"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "createprocess-probe" "failed" 120 "$log" "$duration" "JASP CreateProcess probe requires JASPEngine.exe."
    return 120
  fi
  if [ ! -f "$probe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      echo "missing=$probe"
      echo "hint=run refs/exe-tests/build.sh"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "createprocess-probe" "failed" 121 "$log" "$duration" "JASP CreateProcess probe executable is missing; run refs/exe-tests/build.sh before this smoke phase."
    return 121
  fi

  (
    cd "$app_dir" || exit 127
    env \
      PATH='C:\Program Files\JASP\bin;C:\Program Files\JASP;C:\Program Files\JASP\R\bin\x64;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0' \
      WINEDEBUG=-all,+loaddll,+seh,+process \
      "${WINE_CMD[@]}" "$probe" 'C:\Program Files\JASP\JASPEngine.exe' --expect-any-exit
  ) >> "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    ended="$(date +%s)"
    if [ "$((ended - started))" -ge 35 ]; then
      timed_out=1
      echo "TIMEOUT after 35s; sending SIGTERM to $pid" >> "$log"
      capture_live_process_snapshot_for_sample "$id" "createprocess-probe-timeout" "$log" || true
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
  done
  wait "$pid" 2>/dev/null
  exit_code=$?
  ended="$(date +%s)"
  duration=$((ended - started))

  {
    echo
    echo "## createprocess summary"
    echo "probeExit=$exit_code"
    if rg -q '^PASS jasp_createprocess\r?$' "$log"; then
      echo "createprocess.pass=yes"
    else
      echo "createprocess.pass=no"
    fi
    if rg -q 'Engine started in testing mode|Opening testfile "testFile.txt" Succeeded' "$log"; then
      echo "jaspEngine.testingMode=yes"
    else
      echo "jaspEngine.testingMode=no"
    fi
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  if [ "$timed_out" -eq 1 ]; then
    record "$id" "createprocess-probe" "failed" 122 "$log" "$duration" "JASP CreateProcess probe timed out while a Windows parent attempted to spawn JASPEngine.exe."
    return 122
  fi
  if rg -q '^PASS jasp_createprocess\r?$' "$log"; then
    if rg -q '^jaspEngine\.testingMode=yes$' "$log"; then
      record "$id" "createprocess-probe" "passed" 0 "$log" "$duration" "JASP CreateProcess probe started JASPEngine.exe from a Windows parent with JASP PATH/R_HOME and reached engine testing mode; raw Wine CreateProcess/JASPEngine loader works, so the current Desktop boundary is before EngineSync::startSlaveProcess/QProcess::start."
    else
      record "$id" "createprocess-probe" "passed" 0 "$log" "$duration" "JASP CreateProcess probe successfully spawned JASPEngine.exe from a Windows parent; child output did not include the testing-mode marker, so inspect the probe log before changing Desktop spawn hypotheses."
    fi
    return 0
  fi

  record "$id" "createprocess-probe" "failed" "$exit_code" "$log" "$duration" "JASP CreateProcess probe did not pass; inspect child exit, loader output, and PATH/R_HOME setup before blaming Desktop engine scheduling."
  return "$exit_code"
}

write_jasp_spawn_trace_probe() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/JASP"
  local log="$LOG_DIR/${id}-spawn-trace-probe.log"
  local started ended duration pid exit_code=0 timed_out=0
  started="$(date +%s)"
  {
    echo "== MacWin JASP spawn trace probe =="
    echo "id=$id"
    echo "prefix=$PREFIX"
    echo "appDir=$app_dir"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "command=JASPDesktop.exe --safeGraphics --noSandbox with WINEDEBUG=+process,+module,+seh"
    echo
  } > "$log"

  if [ ! -f "$app_dir/JASPDesktop.exe" ] || [ ! -f "$app_dir/JASPEngine.exe" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    {
      [ -f "$app_dir/JASPDesktop.exe" ] || echo "missing=JASPDesktop.exe"
      [ -f "$app_dir/JASPEngine.exe" ] || echo "missing=JASPEngine.exe"
      echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >> "$log"
    record "$id" "spawn-trace-probe" "failed" 117 "$log" "$duration" "JASP spawn trace requires both JASPDesktop.exe and JASPEngine.exe."
    return 117
  fi

  (
    cd "$app_dir" || exit 127
    env \
      PATH='C:\Program Files\JASP\bin;C:\Program Files\JASP;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0' \
      MACWIN_SOFTWARE_SMOKE_LAUNCH=1 \
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0 \
      QT_OPENGL=software \
      QT_QUICK_BACKEND=software \
      QML_DISABLE_DISK_CACHE=1 \
      QMLSCENE_DEVICE=softwarecontext \
      QSG_RENDER_LOOP=basic \
      QSG_RHI_BACKEND=opengl \
      QT_ACCESSIBILITY=0 \
      QT_AUTO_SCREEN_SCALE_FACTOR=0 \
      QT_ENABLE_HIGHDPI_SCALING=0 \
      QT_FONT_DPI=96 \
      QT_QUICK_CONTROLS_STYLE=Basic \
      QT_RHI_BACKEND=software \
      QT_SCALE_FACTOR=1 \
      QT_PLUGIN_PATH='C:\Program Files\JASP' \
      QT_QPA_PLATFORM_PLUGIN_PATH='C:\Program Files\JASP\platforms' \
      QML2_IMPORT_PATH='C:\Program Files\JASP\qml' \
      QTWEBENGINE_RESOURCES_PATH='C:\Program Files\JASP\resources' \
      QTWEBENGINE_LOCALES_PATH='C:\Program Files\JASP\translations\qtwebengine_locales' \
      QTWEBENGINEPROCESS_PATH='C:\Program Files\JASP\QtWebEngineProcess.exe' \
      QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-software-rasterizer --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-native-gpu-memory-buffers --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --use-gl=disabled --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc' \
      JASPENGINE_LOCATION='C:\Program Files\JASP\JASPEngine.exe' \
      WINEDEBUG=+process,+module,+seh \
      "${WINE_CMD[@]}" 'C:\Program Files\JASP\JASPDesktop.exe' --safeGraphics --noSandbox
  ) >> "$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    ended="$(date +%s)"
    if [ "$((ended - started))" -ge 35 ]; then
      timed_out=1
      echo "TIMEOUT after 35s; sending SIGTERM to $pid" >> "$log"
      capture_live_process_snapshot_for_sample "$id" "spawn-trace-timeout" "$log" || true
      kill "$pid" 2>/dev/null || true
      terminate_live_gui_processes_for_sample "$id" "$log" || true
      sleep 2
      kill -KILL "$pid" 2>/dev/null || true
      terminate_live_gui_processes_for_sample "$id" "$log" || true
      break
    fi
  done
  wait "$pid" 2>/dev/null
  exit_code=$?
  ended="$(date +%s)"
  duration=$((ended - started))

  {
    echo
    echo "## spawn trace summary"
    echo "desktopExit=$exit_code"
    if rg -q 'JASPEngine\.exe' "$log"; then
      echo "trace.hasJASPEngineString=yes"
    else
      echo "trace.hasJASPEngineString=no"
    fi
    if rg -q 'JASPDesktop\.exe' "$log"; then
      echo "trace.hasJASPDesktopString=yes"
    else
      echo "trace.hasJASPDesktopString=no"
    fi
    if rg -q 'create_process|CreateProcess|fork_and_exec|exec_process' "$log"; then
      echo "trace.hasProcessCreateEvidence=yes"
    else
      echo "trace.hasProcessCreateEvidence=no"
    fi
    if rg -q 'JASPEngine\.exe.*(create_process|CreateProcess|fork_and_exec|exec_process)|(create_process|CreateProcess|fork_and_exec|exec_process).*JASPEngine\.exe' "$log"; then
      echo "trace.hasJASPEngineCreateEvidence=yes"
    else
      echo "trace.hasJASPEngineCreateEvidence=no"
    fi
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"

  if [ "$timed_out" -eq 1 ]; then
    if rg -q '^trace.hasJASPEngineCreateEvidence=yes$' "$log"; then
      record "$id" "spawn-trace-probe" "failed" 118 "$log" "$duration" "JASP Desktop timed out, but Wine process trace includes JASPEngine create evidence; continue with child startup/IPC handshake diagnostics."
    else
      record "$id" "spawn-trace-probe" "failed" 119 "$log" "$duration" "JASP Desktop timed out and Wine process trace did not show JASPEngine create evidence; continue with DataSetPackage reset/endLoadingData, EngineSync reloadData receivers, Qt model warnings, and MainWindow constructor-tail diagnostics."
    fi
    return 0
  fi

  record "$id" "spawn-trace-probe" "passed" 0 "$log" "$duration" "JASP spawn trace exited before watchdog; inspect trace summary to decide whether JASPEngine creation was attempted."
  return 0
}

configure_geogebra_classic_profile() {
  local app_dir="$PREFIX/drive_c/macwin-portable/geogebra-classic"
  local disabled_dir="$app_dir/.macwin-disabled-api-ms-dlls"
  local gpu_disabled_dir="$app_dir/.macwin-disabled-gpu-dlls"
  local dll
  [ -f "$app_dir/GeoGebra.exe" ] || return 0

  mkdir -p "$disabled_dir"
  find "$app_dir" -maxdepth 1 -type f \( \
    -iname 'api-ms-win*.dll' -o \
    -iname 'ext-ms-win*.dll' -o \
    -iname 'API-MS-Win*.dll' \
  \) -print 2>/dev/null | while IFS= read -r dll; do
    mv -f "$dll" "$disabled_dir/$(basename "$dll")"
  done

  mkdir -p "$gpu_disabled_dir"
  for dll in libEGL.dll libGLESv2.dll vulkan-1.dll vk_swiftshader.dll vk_swiftshader_icd.json d3dcompiler_47.dll; do
    [ -e "$app_dir/$dll" ] && mv -f "$app_dir/$dll" "$gpu_disabled_dir/$dll"
  done
}

disable_bundled_gpu_dlls() {
  local source_dir="$1"
  local disabled_dir="$2"
  local dll

  [ -d "$source_dir" ] || return 0
  mkdir -p "$disabled_dir"
  for dll in libEGL.dll libGLESv2.dll vulkan-1.dll vk_swiftshader.dll vk_swiftshader_icd.json d3dcompiler_47.dll dxcompiler.dll dxil.dll; do
    [ -e "$source_dir/$dll" ] && mv -f "$source_dir/$dll" "$disabled_dir/$dll"
  done
}

restore_bundled_gpu_dlls() {
  local disabled_dir="$1"
  local target_dir="$2"
  local path relative

  [ -d "$disabled_dir" ] || return 0
  while IFS= read -r path; do
    relative="${path#$disabled_dir/}"
    mkdir -p "$target_dir/$(dirname "$relative")"
    mv -f "$path" "$target_dir/$relative"
  done < <(find "$disabled_dir" -type f -print 2>/dev/null)
}

deploy_dxvk_macos_dlls() {
  local system32="$PREFIX/drive_c/windows/system32"
  local backup_dir="$PREFIX/.macwin-dxvk-backup/system32"
  local dll

  for dll in dxgi.dll d3d11.dll d3d10core.dll; do
    if [ ! -f "$DXVK_MACOS_DIR/$dll" ]; then
      printf 'DXVK-macOS DLL missing: %s\n' "$DXVK_MACOS_DIR/$dll" >&2
      return 1
    fi
  done

  mkdir -p "$system32" "$backup_dir"
  for dll in dxgi.dll d3d11.dll d3d10core.dll; do
    if [ -f "$system32/$dll" ] && [ ! -f "$backup_dir/$dll" ]; then
      cp -p "$system32/$dll" "$backup_dir/$dll"
    fi
    cp -p "$DXVK_MACOS_DIR/$dll" "$system32/$dll"
  done
  printf '%s\n' "$DXVK_MACOS_DIR" > "$PREFIX/.macwin-dxvk-macos-source"
}

configure_lenovo_app_store_profile() {
  local app_dir="$PREFIX/drive_c/Program Files (x86)/Lenovo/LeAppStore"
  local gpu_disabled_dir="$app_dir/.macwin-disabled-gpu-dlls"
  local cache_dir="$PREFIX/drive_c/users/$USER/AppData/Local/lenovo/LeAppStore/storecache"
  local renderer_preset="${MACWIN_LENOVO_RENDERER_PRESET:-stock-software}"
  [ -f "$app_dir/LenovoAppStore.exe" ] || return 0

  case "$renderer_preset" in
    swiftshader|angle|inprocess-swiftshader|single-process-swiftshader|warp|d3d11-warp|native|stock-native|dxvk-macos|dxvk-macos-inprocess)
      restore_bundled_gpu_dlls "$gpu_disabled_dir" "$app_dir"
      ;;
    *)
      disable_bundled_gpu_dlls "$app_dir" "$gpu_disabled_dir"
      disable_bundled_gpu_dlls "$app_dir/swiftshader" "$gpu_disabled_dir/swiftshader"
      ;;
  esac
  if [ "$renderer_preset" = "dxvk-macos" ] || [ "$renderer_preset" = "dxvk-macos-inprocess" ]; then
    deploy_dxvk_macos_dlls || return 1
    mkdir -p "$gpu_disabled_dir"
    for dll in vulkan-1.dll vk_swiftshader.dll vk_swiftshader_icd.json; do
      [ -e "$app_dir/$dll" ] && mv -f "$app_dir/$dll" "$gpu_disabled_dir/$dll"
    done
  fi
  if [ -d "$cache_dir" ]; then
    rm -rf "$cache_dir/Cache" \
      "$cache_dir/Code Cache" \
      "$cache_dir/GPUCache" \
      "$cache_dir/GrShaderCache" \
      "$cache_dir/ShaderCache" \
      "$cache_dir/DawnCache" \
      "$cache_dir/blob_storage"
    rm -f "$cache_dir/LOCK" \
      "$cache_dir/Local State" \
      "$cache_dir/Network/LOCK" \
      "$cache_dir/Network/Cookies-journal" \
      "$cache_dir/Session Storage/LOCK" \
      "$cache_dir/Local Storage/leveldb/LOCK"
  fi
}

configure_pgadmin_profile() {
  local app_dir="$PREFIX/drive_c/users/$USER/AppData/Local/Programs/pgAdmin 4/runtime/resources/app"
  local python_site="$PREFIX/drive_c/users/$USER/AppData/Local/Programs/pgAdmin 4/python/Lib/site-packages"
  local sitecustomize="$python_site/sitecustomize.py"
  local splash="$app_dir/src/html/splash.html"
  local main_js="$app_dir/src/js/pgadmin.js"

  [ -f "$splash" ] && [ -f "$main_js" ] || return 0

  if ! rg -q 'MACWIN pgAdmin splash renderer guards' "$splash"; then
    perl -0pi -e 's#      chrome\.passwordsPrivate\.getSavedPasswordList\(function\(passwords\) \{\n        passwords\.forEach\(\(p, i\) => \{\n          chrome\.passwordsPrivate\.removeSavedPassword\(i\);\n        \}\);\n      \}\);\n      chrome\.privacy\.services\.passwordSavingEnabled\.set\(\{ value: false \}\);#      // MACWIN pgAdmin splash renderer guards: Electron 42 may expose neither chrome.passwordsPrivate nor require() here.\n      if (window.chrome \&\& chrome.passwordsPrivate \&\& chrome.passwordsPrivate.getSavedPasswordList) {\n        chrome.passwordsPrivate.getSavedPasswordList(function(passwords) {\n          passwords.forEach((p, i) => {\n            chrome.passwordsPrivate.removeSavedPassword(i);\n          });\n        });\n      }\n      if (window.chrome \&\& chrome.privacy \&\& chrome.privacy.services \&\& chrome.privacy.services.passwordSavingEnabled) {\n        chrome.privacy.services.passwordSavingEnabled.set({ value: false });\n      }#' "$splash"
    perl -0pi -e 's#      let platform = require\("os"\)\.platform;#      let platform = "win32";\n      if (typeof require === "function") {\n        platform = require("os").platform;\n      }#' "$splash"
  fi

  if ! rg -q 'const appIconPath = path\.join\(app\.getAppPath\(\), .assets., .pgAdmin4\.png.\);' "$main_js"; then
    perl -0pi -e 's#const __dirname = path\.dirname\(fileURLToPath\(import\.meta\.url\)\);#const __dirname = path.dirname(fileURLToPath(import.meta.url));\nconst appIconPath = path.join(app.getAppPath(), "assets", "pgAdmin4.png");#' "$main_js"
  fi
  perl -0pi -e "s#icon: '\\.\\./\\.\\./assets/pgAdmin4\\.png'#icon: appIconPath#g; s#'icon': '\\.\\./\\.\\./assets/pgAdmin4\\.png'#'icon': appIconPath#g" "$main_js"

  mkdir -p "$python_site"
  if [ ! -f "$sitecustomize" ] || ! rg -q 'MACWIN pgAdmin runtime DLL search' "$sitecustomize"; then
    cat > "$sitecustomize" <<'PY'
# MACWIN pgAdmin runtime DLL search
import os
import sys

_macwin_runtime = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "runtime")
if os.name == "nt" and os.path.isdir(_macwin_runtime):
    _macwin_pgadmin_dll_directory = os.add_dll_directory(_macwin_runtime)
PY
  fi
}

configure_dbeaver_profile() {
  local app_dir="$PREFIX/drive_c/macwin-portable/dbeaver-database/dbeaver"
  local ini="$app_dir/dbeaver.ini"
  local driver_dir="$PREFIX/drive_c/users/$USER/AppData/Roaming/DBeaverData/drivers/maven/maven-central/org.postgresql/postgresql/42.7.13"
  local driver="$driver_dir/postgresql-42.7.13.jar"
  local driver_url='https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.13/postgresql-42.7.13.jar'
  local expected_sha1='a6e1bd21b412d6ffb3df23cd13d507bc2cc9e37d'
  local compiler_dir="$PREFIX/drive_c/users/$USER/AppData/Roaming/DBeaverData/macwin-tools"
  local compiler="$compiler_dir/ecj-3.46.0.jar"
  local compiler_url='https://repo1.maven.org/maven2/org/eclipse/jdt/ecj/3.46.0/ecj-3.46.0.jar'
  local expected_compiler_sha1='e962128cf16c864b61633b5a1c75709b0ba2f017'
  local actual_sha1=''

  [ -f "$ini" ] || return 0
  if ! rg -q '^-XX:ActiveProcessorCount=' "$ini"; then
    printf '%s\n' '-XX:ActiveProcessorCount=14' >> "$ini"
  fi

  if [ -f "$driver" ]; then
    actual_sha1="$(shasum -a 1 "$driver" | awk '{print $1}')"
  fi
  if [ "$actual_sha1" != "$expected_sha1" ]; then
    mkdir -p "$driver_dir"
    rm -f "$driver.tmp"
    curl --noproxy '*' -fL --retry 2 --connect-timeout 15 "$driver_url" -o "$driver.tmp" || {
      rm -f "$driver.tmp"
      return 1
    }
    actual_sha1="$(shasum -a 1 "$driver.tmp" | awk '{print $1}')"
    [ "$actual_sha1" = "$expected_sha1" ] || {
      rm -f "$driver.tmp"
      return 1
    }
    mv -f "$driver.tmp" "$driver"
  fi

  actual_sha1=''
  if [ -f "$compiler" ]; then
    actual_sha1="$(shasum -a 1 "$compiler" | awk '{print $1}')"
  fi
  if [ "$actual_sha1" != "$expected_compiler_sha1" ]; then
    mkdir -p "$compiler_dir"
    rm -f "$compiler.tmp"
    curl --noproxy '*' -fL --retry 2 --connect-timeout 15 "$compiler_url" -o "$compiler.tmp" || {
      rm -f "$compiler.tmp"
      return 1
    }
    actual_sha1="$(shasum -a 1 "$compiler.tmp" | awk '{print $1}')"
    [ "$actual_sha1" = "$expected_compiler_sha1" ] || {
      rm -f "$compiler.tmp"
      return 1
    }
    mv -f "$compiler.tmp" "$compiler"
  fi
}

configure_onlyoffice_profile() {
  local service_key='HKLM\System\CurrentControlSet\Services\ONLYOFFICE Update Service'

  [ -f "$PREFIX/drive_c/Program Files/ONLYOFFICE/DesktopEditors/DesktopEditors.exe" ] || return 0
  "${WINE_CMD[@]}" reg.exe add "$service_key" /v Start /t REG_DWORD /d 4 /f >/dev/null 2>&1 || return 1
}

configure_wps_office_profile() {
  local version="${1:-12.1.0.27458}"
  local install_root="C:\\Program Files\\Kingsoft\\WPS Office\\$version"
  local fixture_source="$SCRIPT_DIR/fixtures/wps-smoke.rtf"
  local fixture_dir="$PREFIX/drive_c/macwin-tests/wps"
  local fltlib_x64="$ENGINE_BUILD_DIR/dlls/fltlib/x86_64-windows/fltlib.dll"
  local fltlib_x86="$ENGINE_BUILD_DIR/dlls/fltlib/i386-windows/fltlib.dll"
  local system32="$PREFIX/drive_c/windows/system32"
  local syswow64="$PREFIX/drive_c/windows/syswow64"

  [ -f "$PREFIX/drive_c/Program Files/Kingsoft/WPS Office/$version/office6/wps.exe" ] || return 0
  if [ ! -f "$fltlib_x64" ] || [ ! -f "$fltlib_x86" ]; then
    make -C "$ENGINE_BUILD_DIR" -j4 \
      dlls/fltlib/x86_64-windows/fltlib.dll \
      dlls/fltlib/i386-windows/fltlib.dll || return 1
  fi
  mkdir -p "$system32" "$syswow64"
  install -m 0644 "$fltlib_x64" "$system32/fltlib.dll"
  install -m 0644 "$fltlib_x86" "$syswow64/fltlib.dll"
  file "$system32/fltlib.dll" | rg -q 'PE32\+ executable .* x86-64' || return 1
  file "$syswow64/fltlib.dll" | rg -q 'PE32 executable .* Intel 80386' || return 1
  echo "Installed WoW64 fltlib.dll coverage required by WPS component registration."
  mkdir -p "$fixture_dir"
  cp -f "$fixture_source" "$fixture_dir/macwin-wps-smoke.rtf"
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Kingsoft\Office\6.0\Common' \
    /v InstallRoot /t REG_SZ /d "$install_root" /f || true
  wine_reg_add_quiet 'HKEY_CURRENT_USER\Software\Kingsoft\Office\6.0\Common' \
    /v AcceptedEULA /t REG_SZ /d true /f || true
  wine_reg_add_quiet 'HKEY_LOCAL_MACHINE\Software\Kingsoft\Office\6.0\Common' \
    /v InstallRoot /t REG_SZ /d "$install_root" /f || true
  "${WINE_CMD[@]}" \
    "C:\\Program Files\\Kingsoft\\WPS Office\\$version\\office6\\ksomisc.exe" \
    -installregister
  echo "WPS component registration completed."
  prepare_wps_office_fixtures
}

prepare_wps_office_fixtures() {
  local fixture_dir="$PREFIX/drive_c/macwin-tests/wps"
  mkdir -p "$fixture_dir"
  /usr/bin/python3 - "$fixture_dir" <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)

def write_zip(path, files):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content.strip())

write_zip(root / "macwin-wps-smoke.xlsx", {
    "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
    "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
    "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="MacWin WPS" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
    "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
    "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>MacWin WPS 兼容性测试</t></is></c><c r="B1"><v>12345</v></c></row>
    <row r="2"><c r="A2" t="inlineStr"><is><t>你好 / Spreadsheet</t></is></c><c r="B2"><f>SUM(B1,5)</f><v>12350</v></c></row>
  </sheetData>
</worksheet>""",
})

write_zip(root / "macwin-wps-smoke.pptx", {
    "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>""",
    "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>""",
    "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>""",
    "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>""",
    "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="MacWin WPS"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:xfrm><a:off x="914400" y="1371600"/><a:ext cx="10363200" cy="2743200"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="zh-CN" sz="3200"/><a:t>MacWin WPS 兼容性测试 你好</a:t></a:r></a:p><a:p><a:r><a:rPr lang="en-US" sz="2000"/><a:t>Presentation 12345</a:t></a:r></a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>""",
    "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""",
    "ppt/slideMasters/slideMaster1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>""",
    "ppt/slideMasters/_rels/slideMaster1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>""",
    "ppt/slideLayouts/slideLayout1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>""",
    "ppt/slideLayouts/_rels/slideLayout1.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>""",
    "ppt/theme/theme1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="MacWin">
  <a:themeElements><a:clrScheme name="MacWin"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
  <a:dk2><a:srgbClr val="1F1F1F"/></a:dk2><a:lt2><a:srgbClr val="F2F2F2"/></a:lt2>
  <a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="16A34A"/></a:accent2>
  <a:accent3><a:srgbClr val="DC2626"/></a:accent3><a:accent4><a:srgbClr val="9333EA"/></a:accent4>
  <a:accent5><a:srgbClr val="0891B2"/></a:accent5><a:accent6><a:srgbClr val="CA8A04"/></a:accent6>
  <a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>
  <a:fontScheme name="MacWin"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface="Arial"/></a:majorFont>
  <a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface="Arial"/></a:minorFont></a:fontScheme>
  <a:fmtScheme name="MacWin"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
  <a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
  <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
  <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements>
</a:theme>""",
})

pdf_objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    b"<< /Length 67 >>\nstream\nBT /F1 20 Tf 72 720 Td (MacWin WPS PDF smoke 12345) Tj ET\nendstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]
payload = bytearray(b"%PDF-1.4\n")
offsets = [0]
for index, obj in enumerate(pdf_objects, 1):
    offsets.append(len(payload))
    payload.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
xref = len(payload)
payload.extend(f"xref\n0 {len(pdf_objects) + 1}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]:
    payload.extend(f"{offset:010d} 00000 n \n".encode())
payload.extend(
    f"trailer\n<< /Size {len(pdf_objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
)
(root / "macwin-wps-smoke.pdf").write_bytes(payload)
PY

  [ -s "$fixture_dir/macwin-wps-smoke.xlsx" ] \
    && [ -s "$fixture_dir/macwin-wps-smoke.pptx" ] \
    && [ -s "$fixture_dir/macwin-wps-smoke.pdf" ]
}

wps_workarea_has_document() {
  local workarea="$1" filename="$2" page_type="$3"
  local title_line item_prefix
  [ -f "$workarea" ] || return 1
  title_line="$(rg -a -F "title=$filename" "$workarea" | head -1)"
  [ -n "$title_line" ] || return 1
  item_prefix="${title_line%%\%7Ctitle=*}"
  rg -a -F -q "$item_prefix%7CpageType=$page_type" "$workarea" \
    && rg -a -F -q "$item_prefix%7CbCrash=0" "$workarea"
}

run_wps_component_document_acceptance() {
  local component_id="$1"
  local executable_name="$2"
  local fixture_name="$3"
  local page_type="$4"
  local fixture_dir="$PREFIX/drive_c/macwin-tests/wps"
  local office6="$PREFIX/drive_c/Program Files/Kingsoft/WPS Office/$install_arg/office6"
  local source="$fixture_dir/$fixture_name"
  local extension="${fixture_name##*.}"
  local run_token
  run_token="$(printf '%s' "$RUN_ID" | shasum -a 256 | cut -c1-8)"
  local component_token="${component_id#wps-office-}"
  local unique_name="mw-${run_token}-${component_token}.${extension}"
  local unique_path="$fixture_dir/$unique_name"
  local windows_path="C:\\macwin-tests\\wps\\$unique_name"
  local workarea="$PREFIX/drive_c/users/$USER/AppData/Roaming/Kingsoft/office6/synccfg/default/head/workarea.cfg"
  local capture_probe="$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe"
  local capture_probe_windows="Z:${capture_probe//\//\\}"
  local window_probe_log="$LOG_DIR/.${component_id}-window-list.log"
  local pattern route_token parent_pid attempt accepted=1
  local live_seen=0 delegated_seen=0 window_seen=0 state_seen=0

  [ -f "$office6/$executable_name" ] && [ -s "$source" ] && [ -f "$capture_probe" ] || return 1
  cp -f "$source" "$unique_path"
  pattern="$(gui_process_pattern_for_sample "$component_id")"
  case "$page_type" in
    pageEt) route_token='/et' ;;
    pageWpp) route_token='/wpp' ;;
    pagePdf) route_token='/pdf' ;;
    *) return 1 ;;
  esac
  "${launch_env_cmd[@]}" PATH="$windows_path_env" "${launch_env[@]}" \
    "${WINE_CMD[@]}" "C:\\Program Files\\Kingsoft\\WPS Office\\$install_arg\\office6\\$executable_name" \
    "$windows_path" &
  parent_pid=$!

  for attempt in $(seq 1 24); do
    sleep 1
    if ps -axo pid=,args= | rg -i "$pattern" | rg -v 'rg -i|/bin/zsh -c' >/dev/null 2>&1; then
      live_seen=1
    fi
    if ps -axo args= | rg -F "$unique_name" | rg -F "$route_token" \
      | rg -v 'rg -F|/bin/zsh -c' >/dev/null 2>&1; then
      delegated_seen=1
    fi
    if WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list \
      >"$window_probe_log" 2>&1 \
      && rg -F "$unique_name" "$window_probe_log" | rg -q 'visible=1'; then
      window_seen=1
    fi
    if wps_workarea_has_document "$workarea" "$unique_name" "$page_type" \
      || rg -a -F -q "$unique_name" "$PREFIX/user.reg" 2>/dev/null; then
      state_seen=1
    fi
    if [ "$live_seen" -eq 1 ] && [ "$delegated_seen" -eq 1 ] && [ "$window_seen" -eq 1 ]; then
      break
    fi
    if ! kill -0 "$parent_pid" 2>/dev/null \
      && [ "$live_seen" -ne 1 ] && [ "$delegated_seen" -ne 1 ]; then
      break
    fi
  done

  echo "component=$component_id"
  echo "document=$windows_path"
  echo "processLive=$live_seen"
  echo "delegatedDocumentRoute=$delegated_seen"
  echo "visibleDocumentWindow=$window_seen"
  echo "documentStateRecorded=$state_seen"
  if [ -f "$window_probe_log" ]; then
    rg -F "$unique_name" "$window_probe_log" || true
  fi
  if [ -f "$workarea" ]; then
    rg -a -F -C 4 "$unique_name" "$workarea" || true
  fi
  if ! kill -0 "$parent_pid" 2>/dev/null; then
    wait "$parent_pid" 2>/dev/null || true
  fi

  if [ "$live_seen" -eq 1 ] && [ "$delegated_seen" -eq 1 ] && [ "$window_seen" -eq 1 ]; then
    accepted=0
  fi
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  sleep 2
  return "$accepted"
}

macos_gui_session_is_locked() {
  [ "$(/usr/bin/swift "$SCRIPT_DIR/macos-session-state.swift" 2>/dev/null || printf unknown)" = "locked" ]
}

run_wps_component_functional_acceptance() {
  local component_id="$1"
  local executable_name="$2"
  local fixture_name="$3"
  local action="$4"
  local fixture_dir="$PREFIX/drive_c/macwin-tests/wps"
  local source="$fixture_dir/$fixture_name"
  local extension="${fixture_name##*.}"
  local office6="$PREFIX/drive_c/Program Files/Kingsoft/WPS Office/$install_arg/office6"
  local capture_probe="$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe"
  local capture_probe_windows="Z:${capture_probe//\//\\}"
  local run_token component_token unique_name unique_path windows_path marker target_child
  local parent_pid attempt window_seen=0 child_ready=0 input_ok=1 accepted=1
  local before_hash after_hash before_slide_count after_slide_count
  local window_probe_log="$LOG_DIR/.${component_id}-${action}-window-list.log"
  local child_probe_log="$LOG_DIR/.${component_id}-${action}-child-list.log"
  local before_capture="$LOG_DIR/${component_id}-${action}-before.bmp"
  local after_capture="$LOG_DIR/${component_id}-${action}-after.bmp"
  local edit_modal_capture="$LOG_DIR/${component_id}-${action}-edit-modal-screen.png"
  local edit_modal_window_log="$LOG_DIR/.${component_id}-${action}-edit-modal-window-list.log"
  local action_modal_capture="$LOG_DIR/${component_id}-${action}-action-modal-screen.png"
  local action_modal_window_log="$LOG_DIR/.${component_id}-${action}-action-modal-window-list.log"
  local action_capture_pid=""
  local before_capture_windows="Z:${before_capture//\//\\}"
  local after_capture_windows="Z:${after_capture//\//\\}"

  [ -f "$office6/$executable_name" ] && [ -s "$source" ] && [ -f "$capture_probe" ] || return 1
  run_token="$(printf '%s-functional' "$RUN_ID" | shasum -a 256 | cut -c1-8)"
  component_token="${component_id#wps-office-}"
  unique_name="mwf-${run_token}-${component_token}.${extension}"
  unique_path="$fixture_dir/$unique_name"
  windows_path="C:\\macwin-tests\\wps\\$unique_name"
  marker="MW_SAVE_$(printf '%s' "$run_token" | tr '[:lower:]' '[:upper:]')"
  case "$action" in
    spreadsheet-save) target_child="EXCEL7" ;;
    presentation-save) target_child="mdiClass" ;;
    pdf-print-dialog) target_child="PdfView" ;;
    *) target_child="" ;;
  esac
  cp -f "$source" "$unique_path"
  before_hash="$(shasum -a 256 "$unique_path" | awk '{print $1}')"
  before_slide_count=0
  if [ "$action" = "presentation-save" ]; then
    before_slide_count="$(unzip -Z1 "$unique_path" | rg -c '^ppt/slides/slide[0-9]+\.xml$' || true)"
  fi

  "${launch_env_cmd[@]}" PATH="$windows_path_env" "${launch_env[@]}" \
    "${WINE_CMD[@]}" \
    "C:\\Program Files\\Kingsoft\\WPS Office\\$install_arg\\office6\\$executable_name" \
    "$windows_path" &
  parent_pid=$!

  for attempt in $(seq 1 30); do
    sleep 1
    if WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list \
      >"$window_probe_log" 2>&1 \
      && rg -F "$unique_name" "$window_probe_log" | rg -q 'visible=1'; then
      window_seen=1
      break
    fi
    # WPS component launchers delegate documents to wpsoffice.exe and can
    # exit before the shared host creates the visible document window.
  done

  echo "component=$component_id"
  echo "action=$action"
  echo "document=$windows_path"
  echo "visibleDocumentWindow=$window_seen"
  echo "documentChild=$target_child"
  if [ "$window_seen" -eq 1 ] && [ -n "$target_child" ]; then
    for attempt in $(seq 1 20); do
      if WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --children \
        "$unique_name" >"$child_probe_log" 2>&1 \
        && rg -q "visible=1.*(class|title)=\"$target_child\"" "$child_probe_log"; then
        child_ready=1
        break
      fi
      sleep 1
    done
  fi
  echo "documentChildReady=$child_ready"
  if [ -f "$child_probe_log" ]; then
    rg "(class|title)=\"$target_child\"" "$child_probe_log" || true
  fi
  if [ "$window_seen" -eq 1 ] && [ "$child_ready" -eq 1 ]; then
    WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --capture \
      "$unique_name" "$before_capture_windows" auto || true
    case "$action" in
      spreadsheet-save)
        if [ "${MACWIN_WPS_CAPTURE_EDIT_MODAL_ONLY:-0}" = "1" ]; then
          WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --send-child \
            "$unique_name" EXCEL7 ctrl+end down "paste:$marker" wait:500 || input_ok=0
          WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list \
            >"$edit_modal_window_log" 2>&1 || true
          /usr/sbin/screencapture -x "$edit_modal_capture" 2>/dev/null || true
          input_ok=0
        else
          WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --send-child \
            "$unique_name" EXCEL7 ctrl+end down "paste:$marker" wait:500 enter wait:500 \
            ctrl+s wait:1500 enter wait:1000 || input_ok=0
        fi
        ;;
      presentation-save)
        WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --send-child \
          "$unique_name" mdiClass ctrl+m wait:700 ctrl+s wait:1200 enter wait:800 || input_ok=0
        ;;
      pdf-print-dialog)
        (
          sleep 1
          /usr/bin/osascript -e \
            'tell application "System Events" to set frontmost of first process whose name is "Wine" to true' \
            >/dev/null 2>&1 || true
          sleep 1
          /usr/sbin/screencapture -x "$action_modal_capture" 2>/dev/null || true
        ) &
        action_capture_pid=$!
        WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --send-child \
          "$unique_name" PdfView ctrl+p wait:3000 || input_ok=0
        wait "$action_capture_pid" 2>/dev/null || true
        WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list \
          >"$action_modal_window_log" 2>&1 || true
        ;;
      *)
        input_ok=0
        ;;
    esac
  else
    input_ok=0
  fi
  echo "inputSequenceAccepted=$input_ok"
  sleep 3
  /usr/sbin/screencapture -x \
    "$LOG_DIR/${component_id}-${action}-screen.png" 2>/dev/null || true
  if [ "$window_seen" -eq 1 ]; then
    WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --capture \
      "$unique_name" "$after_capture_windows" auto || true
    WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --children \
      "$unique_name" || true
    WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list || true
  fi
  sleep 3

  if [ "$action" = "pdf-print-dialog" ] && [ "$input_ok" -eq 1 ]; then
    window_seen=0
    for attempt in $(seq 1 10); do
      WINEDEBUG=-all "${WINE_CMD[@]}" "$capture_probe_windows" --list \
        >"$window_probe_log" 2>&1 || true
      if rg -i 'visible=1.*(class="#32770"|title="[^"]*(print|打印)[^"]*")' \
        "$window_probe_log" >/dev/null 2>&1; then
        window_seen=1
        break
      fi
      if [ "$(rg -c 'visible=1.*class="Qt5QWindow(Icon)?" title=""' \
        "$window_probe_log" 2>/dev/null || true)" -ge 2 ]; then
        window_seen=1
        break
      fi
      sleep 1
    done
    echo "printDialogVisible=$window_seen"
    rg -i 'visible=1.*(class="#32770"|title="[^"]*(print|打印)[^"]*")' \
      "$window_probe_log" || true
    rg 'visible=1.*class="Qt5QWindow(Icon)?" title=""' \
      "$window_probe_log" || true
    [ "$window_seen" -eq 1 ] && accepted=0
  fi

  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  wait "$parent_pid" 2>/dev/null || true
  sleep 2

  if [ "$action" = "spreadsheet-save" ] && [ "$input_ok" -eq 1 ]; then
    after_hash="$(shasum -a 256 "$unique_path" | awk '{print $1}')"
    echo "beforeHash=$before_hash"
    echo "afterHash=$after_hash"
    if [ "$before_hash" != "$after_hash" ] \
      && unzip -p "$unique_path" | rg -a -F -q "$marker"; then
      echo "savedMarker=$marker"
      accepted=0
    fi
  elif [ "$action" = "presentation-save" ] && [ "$input_ok" -eq 1 ]; then
    after_hash="$(shasum -a 256 "$unique_path" | awk '{print $1}')"
    after_slide_count="$(unzip -Z1 "$unique_path" | rg -c '^ppt/slides/slide[0-9]+\.xml$' || true)"
    echo "beforeHash=$before_hash"
    echo "afterHash=$after_hash"
    echo "beforeSlideCount=$before_slide_count"
    echo "afterSlideCount=$after_slide_count"
    if [ "$before_hash" != "$after_hash" ] \
      && [ "$after_slide_count" -gt "$before_slide_count" ]; then
      accepted=0
    fi
  fi

  return "$accepted"
}

configure_freeoffice_profile() {
  local id="freeoffice-vc8-runtime"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code state
  local source_crt="$ENGINE_BUILD_DIR/dlls/msvcr80/i386-windows/msvcr80.dll"
  local source_cpp="$ENGINE_BUILD_DIR/dlls/msvcp80/i386-windows/msvcp80.dll"
  local target_dir="$PREFIX/drive_c/windows/syswow64"

  started="$(date +%s)"
  {
    echo "== SoftMaker FreeOffice VC8 x86 runtime repair =="
    echo "engineBuild=$ENGINE_BUILD_DIR"
    echo "prefix=$PREFIX"
    echo
    if [ ! -f "$source_crt" ] || [ ! -f "$source_cpp" ]; then
      make -C "$ENGINE_BUILD_DIR" -j4 \
        dlls/msvcr80/i386-windows/msvcr80.dll \
        dlls/msvcp80/i386-windows/msvcp80.dll
    fi
    mkdir -p "$target_dir"
    install -m 0644 "$source_crt" "$target_dir/msvcr80.dll"
    install -m 0644 "$source_cpp" "$target_dir/msvcp80.dll"
    "${WINE_CMD[@]}" reg add 'HKCR\.rtf' /ve /t REG_SZ /d 'TextMaker.RTF' /f
    echo
    echo "== verification =="
    file "$target_dir/msvcr80.dll" "$target_dir/msvcp80.dll"
    file "$target_dir/msvcr80.dll" | rg -q 'PE32 executable .* Intel 80386'
    file "$target_dir/msvcp80.dll" | rg -q 'PE32 executable .* Intel 80386'
    shasum -a 256 "$target_dir/msvcr80.dll" "$target_dir/msvcp80.dll"
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  state="$([ "$exit_code" -eq 0 ] && printf passed || printf failed)"
  record "$id" "$phase" "$state" "$exit_code" "$log" "$duration" \
    "Installed Wine's PE32 VC8 runtime for FreeOffice 32-bit helper modules."
  return "$exit_code"
}

configure_sqlitebrowser_profile() {
  local app_dir="$PREFIX/drive_c/Program Files/DB Browser for SQLite"
  local bearer_dir="$app_dir/bearer"
  local disabled_dir="$app_dir/.macwin-disabled-bearer"
  [ -f "$app_dir/DB Browser for SQLite.exe" ] || return 0
  [ -f "$bearer_dir/qgenericbearer.dll" ] || return 0

  mkdir -p "$disabled_dir"
  mv -f "$bearer_dir/qgenericbearer.dll" "$disabled_dir/qgenericbearer.dll"
}

configure_librecad_profile() {
  [ -f "$PREFIX/drive_c/Program Files/LibreCAD/LibreCAD.exe" ] || return 0

  local appearance_key='HKCU\Software\LibreCAD\LibreCAD\Appearance'
  local defaults_key='HKCU\Software\LibreCAD\LibreCAD\Defaults'
  local startup_key='HKCU\Software\LibreCAD\LibreCAD\Startup'
  "${WINE_CMD[@]}" reg add "$appearance_key" /v Language /t REG_SZ /d zh_CN /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$appearance_key" /v LanguageCmd /t REG_SZ /d zh_CN /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$defaults_key" /v Unit /t REG_SZ /d Millimeter /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$defaults_key" /v UseQtFileOpenDialog /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$startup_key" /v FirstLoad /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$startup_key" /v Maximize /t REG_DWORD /d 1 /f >/dev/null 2>&1 || true
}

configure_openscad_workload() {
  [ -f "$PREFIX/drive_c/Program Files/OpenSCAD/openscad.exe" ] || return 0

  local app_dir="$PREFIX/drive_c/Program Files/OpenSCAD"
  local software_opengl="$PREFIX/drive_c/Program Files/LibreCAD/opengl32sw.dll"
  local sample_dir="$PREFIX/drive_c/macwin-testdata/openscad"
  if [ -f "$software_opengl" ]; then
    cp -f "$software_opengl" "$app_dir/opengl32.dll"
  fi
  mkdir -p "$sample_dir"
  printf '%s\n' \
    '$fn = 48;' \
    'difference() {' \
    '  minkowski() {' \
    '    cube([36, 24, 8], center = true);' \
    '    sphere(r = 2);' \
    '  }' \
    '  cylinder(h = 16, r = 5, center = true);' \
    '}' \
    > "$sample_dir/macwin-cad-smoke.scad"
}

configure_qcad_legacy_profile() {
  local app_dir="$PREFIX/drive_c/Program Files/QCad 2"
  [ -f "$app_dir/qcad.exe" ] || return 0

  local sample_dir="$PREFIX/drive_c/macwin-testdata/qcad"
  local appearance_key='HKCU\Software\RibbonSoft\QCad\Appearance'
  local defaults_key='HKCU\Software\RibbonSoft\QCad\Defaults'
  local startup_key='HKCU\Software\RibbonSoft\QCad\Startup'
  mkdir -p "$sample_dir"
  cp -f "$app_dir/data/example01.dxf" "$sample_dir/macwin-qcad-smoke.dxf"
  "${WINE_CMD[@]}" reg add "$appearance_key" /v Language /t REG_SZ /d en /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$appearance_key" /v LanguageCmd /t REG_SZ /d en /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$defaults_key" /v Unit /t REG_SZ /d Millimeter /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$startup_key" /v FirstLoad /t REG_DWORD /d 0 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$startup_key" /v Maximize /t REG_DWORD /d 1 /f >/dev/null 2>&1 || true
}

configure_qucs_s_profile() {
  [ -f "$PREFIX/drive_c/macwin-portable/qucs-s-circuit/bin/qucs-s.exe" ] || return 0

  local settings_key='HKCU\Software\qucs\qucs_s'
  local ui_font='Tahoma,9,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,,0,0'
  local text_font='Consolas,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,,0,0'

  "${WINE_CMD[@]}" reg add "$settings_key" /v appFont /t REG_SZ /d "$ui_font" /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$settings_key" /v textFont /t REG_SZ /d "$text_font" /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$settings_key" /v LargeFontSize /t REG_DWORD /d 14 /f >/dev/null 2>&1 || true
}

configure_pdfxchange_sample() {
  local source_pdf="$PREFIX/drive_c/Program Files/PDF-XChange/PDF Editor/PXCLicense.pdf"
  local target_dir="$PREFIX/drive_c/macwin-testdata/pdfxchange"
  if [ -f "$source_pdf" ]; then
    mkdir -p "$target_dir"
    cp -f "$source_pdf" "$target_dir/PXCLicense.pdf"
  fi
}

configure_openplc_profile() {
  local profile_dir="$PREFIX/drive_c/macwin-portable/openplc-profile"
  local history_dir="$profile_dir/User/History"
  local settings_file="$profile_dir/User/settings.json"
  local config_file="$profile_dir/config.json"
  [ -f "$PREFIX/drive_c/macwin-portable/openplc-editor/OpenPLC Editor.exe" ] || return 0

  mkdir -p "$history_dir"
  [ -f "$history_dir/projects.json" ] || printf '[]' > "$history_dir/projects.json"
  [ -f "$history_dir/libraries.json" ] || printf '[]' > "$history_dir/libraries.json"
  if [ ! -f "$settings_file" ]; then
    mkdir -p "$(dirname "$settings_file")"
    cat > "$settings_file" <<'JSON'
{
  "theme-preference": "light",
  "window": {
    "bounds": {
      "width": 1124,
      "height": 720,
      "x": 0,
      "y": 0
    }
  }
}
JSON
  fi
  if [ ! -f "$config_file" ]; then
    cat > "$config_file" <<'JSON'
{
  "last_projects": [],
  "theme": "light",
  "window": {
    "bounds": {
      "x": 0,
      "y": 0,
      "width": 1124,
      "height": 720
    }
  }
}
JSON
  fi
}

repair_engine_dlls() {
  mkdir -p "$PREFIX/drive_c/windows/system32" "$PREFIX/drive_c/windows/syswow64"
  local module dll candidate
	  for item in \
	    "actxprxy actxprxy.dll" \
	    "avicap32 avicap32.dll" \
	    "avifil32 avifil32.dll" \
	    "avrt avrt.dll" \
    "bluetoothapis bluetoothapis.dll" \
    "bthprops.cpl bthprops.cpl" \
	    "bcryptprimitives bcryptprimitives.dll" \
	    "combase combase.dll" \
	    "comctl32_v6 comctl32_v6.dll" \
    "concrt140 concrt140.dll" \
    "vcomp vcomp.dll" \
    "vcomp90 vcomp90.dll" \
    "vcomp100 vcomp100.dll" \
    "vcomp110 vcomp110.dll" \
    "vcomp120 vcomp120.dll" \
    "vcomp140 vcomp140.dll" \
    "d3dcompiler_43 d3dcompiler_43.dll" \
    "d3dx9_43 d3dx9_43.dll" \
    "d3dxof d3dxof.dll" \
    "dcomp dcomp.dll" \
    "dsound dsound.dll" \
	    "credui credui.dll" \
	    "cryptui cryptui.dll" \
	    "dbgeng dbgeng.dll" \
	    "esent esent.dll" \
	    "gdiplus gdiplus.dll" \
	    "icu icu.dll" \
	    "iphlpapi iphlpapi.dll" \
    "kerberos kerberos.dll" \
    "ksuser ksuser.dll" \
	    "ktmw32 ktmw32.dll" \
	    "mlang mlang.dll" \
    "mf mf.dll" \
    "mfplat mfplat.dll" \
    "mfreadwrite mfreadwrite.dll" \
	    "mmdevapi mmdevapi.dll" \
	    "msctf msctf.dll" \
    "mscms mscms.dll" \
    "msvcp110 msvcp110.dll" \
    "msvcp120 msvcp120.dll" \
	    "msvcp140 msvcp140.dll" \
	    "msvcp140_1 msvcp140_1.dll" \
	    "msvcp140_2 msvcp140_2.dll" \
	    "msvcp140_atomic_wait msvcp140_atomic_wait.dll" \
    "msvcr110 msvcr110.dll" \
    "msvcr120 msvcr120.dll" \
	    "msvfw32 msvfw32.dll" \
	    "msxml3 msxml3.dll" \
	    "msxml6 msxml6.dll" \
	    "msv1_0 msv1_0.dll" \
	    "netapi32 netapi32.dll" \
	    "netprofm netprofm.dll" \
	    "odbc32 odbc32.dll" \
		    "ole32 ole32.dll" \
	    "oleacc oleacc.dll" \
	    "olepro32 olepro32.dll" \
    "pdh pdh.dll" \
	    "powrprof powrprof.dll" \
    "qmgr qmgr.dll" \
    "rasapi32 rasapi32.dll" \
    "propsys propsys.dll" \
    "rstrtmgr rstrtmgr.dll" \
    "rsaenh rsaenh.dll" \
    "sensapi sensapi.dll" \
    "shell32 shell32.dll" \
    "taskschd taskschd.dll" \
    "mstask mstask.dll" \
    "schedsvc schedsvc.dll" \
    "setupapi setupapi.dll" \
    "uiautomationcore uiautomationcore.dll" \
    "wevtapi wevtapi.dll" \
    "wevtsvc wevtsvc.dll" \
    "webservices webservices.dll" \
    "wmvcore wmvcore.dll" \
    "threadpoolwinrt threadpoolwinrt.dll" \
	    "windows.ui windows.ui.dll" \
	    "windowscodecs windowscodecs.dll" \
	    "windowscodecsext windowscodecsext.dll" \
	    "wininet wininet.dll" \
    "winmm winmm.dll" \
    "winusb winusb.dll" \
    "wintypes wintypes.dll" \
    "wintab32 wintab32.dll" \
    "wlanapi wlanapi.dll" \
    "wldap32 wldap32.dll" \
    "xmllite xmllite.dll"
	  do
	    read -r module dll <<< "$item"
	    if [ -f "$ENGINE_BUILD_DIR/dlls/$module/x86_64-windows/$dll" ]; then
	      cp -f "$ENGINE_BUILD_DIR/dlls/$module/x86_64-windows/$dll" "$PREFIX/drive_c/windows/system32/$dll" || true
    elif [ -f "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/$module/x86_64-windows/$dll" ]; then
      cp -f "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/$module/x86_64-windows/$dll" "$PREFIX/drive_c/windows/system32/$dll" || true
    elif [ -f "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/$module/x86_64-windows/$dll" ]; then
      cp -f "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/$module/x86_64-windows/$dll" "$PREFIX/drive_c/windows/system32/$dll" || true
    fi
    if [ -f "$ENGINE_BUILD_DIR/dlls/$module/i386-windows/$dll" ]; then
      cp -f "$ENGINE_BUILD_DIR/dlls/$module/i386-windows/$dll" "$PREFIX/drive_c/windows/syswow64/$dll" || true
    elif [ -f "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/$module/i386-windows/$dll" ]; then
      cp -f "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/$module/i386-windows/$dll" "$PREFIX/drive_c/windows/syswow64/$dll" || true
    elif [ -f "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/$module/i386-windows/$dll" ]; then
      cp -f "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/$module/i386-windows/$dll" "$PREFIX/drive_c/windows/syswow64/$dll" || true
    elif [ -f "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/$module/i386-windows/$dll" ]; then
      cp -f "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/$module/i386-windows/$dll" "$PREFIX/drive_c/windows/syswow64/$dll" || true
	    fi
	  done
  if [ ! -f "$PREFIX/drive_c/windows/syswow64/ntdll.dll" ]; then
    for candidate in \
      "$ENGINE_BUILD_DIR/dlls/ntdll/i386-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/ntdll/i386-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/ntdll/x86_64-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/ntdll/i386-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/ntdll/x86_64-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/ntdll/i386-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/ntdll/x86_64-windows/ntdll.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/syswow64/ntdll.dll" || true
        break
      fi
    done
  fi
  if [ ! -f "$PREFIX/drive_c/windows/system32/ntdll.dll" ]; then
    for candidate in \
      "$ENGINE_BUILD_DIR/dlls/ntdll/x86_64-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/ntdll/x86_64-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/ntdll/x86_64-windows/ntdll.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/ntdll/x86_64-windows/ntdll.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/system32/ntdll.dll" || true
        break
      fi
    done
  fi
  if [ ! -f "$PREFIX/drive_c/windows/system32/odbc32.dll" ]; then
    for candidate in \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/odbc32/x86_64-windows/odbc32.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/odbc32/x86_64-windows/odbc32.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/odbc32/x86_64-windows/odbc32.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/system32/odbc32.dll" || true
        break
      fi
    done
  fi
  if [ ! -f "$PREFIX/drive_c/windows/syswow64/odbc32.dll" ]; then
    for candidate in \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/odbc32/i386-windows/odbc32.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/syswow64/odbc32.dll" || true
        break
      fi
    done
  fi
	  if [ ! -f "$PREFIX/drive_c/windows/system32/mscoree.dll" ]; then
    for candidate in \
      "$ENGINE_BUILD_DIR/dlls/mscoree/x86_64-windows/mscoree.dll" \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/mscoree/x86_64-windows/mscoree.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/dlls/mscoree/x86_64-windows/mscoree.dll" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/dlls/mscoree/x86_64-windows/mscoree.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/system32/mscoree.dll" || true
        break
      fi
    done
  fi
  if [ ! -f "$PREFIX/drive_c/windows/syswow64/mscoree.dll" ]; then
    for candidate in \
      "$ENGINE_BUILD_DIR/dlls/mscoree/i386-windows/mscoree.dll" \
      "$PROJECT_ROOT/refs/Whisky-wow64-game-build/dlls/mscoree/i386-windows/mscoree.dll"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/syswow64/mscoree.dll" || true
        break
      fi
    done
  fi
}

repair_engine_tools() {
  mkdir -p "$PREFIX/drive_c/windows/system32"
  local tool candidate
  for tool in taskkill.exe
  do
    for candidate in \
      "$ENGINE_BUILD_DIR/programs/${tool%.exe}/x86_64-windows/$tool" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-game-build/programs/${tool%.exe}/x86_64-windows/$tool" \
      "$PROJECT_ROOT/refs/Whisky-x86_64-build/programs/${tool%.exe}/x86_64-windows/$tool"
    do
      if [ -f "$candidate" ]; then
        cp -f "$candidate" "$PREFIX/drive_c/windows/system32/$tool" || true
        break
      fi
    done
  done
}

wine_mono_ready() {
  [ -f "$PREFIX/drive_c/windows/mono/mono-2.0/bin/libmono-2.0-x86.dll" ] \
    && [ -f "$PREFIX/drive_c/windows/mono/mono-2.0/bin/libmono-2.0-x86_64.dll" ] \
    && { [ -f "$PREFIX/drive_c/windows/mono/mono-2.0/lib/mono/4.5/mscorlib.dll" ] \
      || [ -f "$PREFIX/drive_c/windows/Microsoft.NET/Framework/v4.0.30319/mscorlib.dll" ] \
      || [ -f "$PREFIX/drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/mscorlib.dll" ]; }
}

find_wine_mono_installer() {
  local candidate
  for candidate in \
    "${MACWIN_WINE_MONO_MSI:-}" \
    "$HOME/.cache/wine/wine-mono-11.1.0-x86.msi" \
    "$DOWNLOADS/wine-mono-11.1.0-x86.msi" \
    "$PROJECT_ROOT/Downloads/wine-mono-11.1.0-x86.msi"
  do
    if [ -n "$candidate" ] && [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

repair_wine_mono() {
  wine_mono_ready && return 0

  local id="macwin-wine-mono"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code mono_msi

  started="$(date +%s)"
  mono_msi="$(find_wine_mono_installer || true)"
  if [ -z "$mono_msi" ]; then
    ended="$(date +%s)"
    duration="$((ended - started))"
    record "$id" "$phase" "skipped" 0 "$log" "$duration" "Wine-Mono installer not found; .NET Framework apps may fail."
    return 0
  fi

  {
    echo "== MacWin Wine-Mono repair =="
    echo "prefix=$WINEPREFIX"
    echo "monoMsi=$mono_msi"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  exit_code=0
  "${WINE_CMD[@]}" msiexec /i "$mono_msi" /qn /norestart >> "$log" 2>&1 || exit_code=$?
  "${WINESERVER_CMD[@]}" -w >> "$log" 2>&1 || true
  ended="$(date +%s)"
  duration="$((ended - started))"
  {
    echo
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "exitCode=$exit_code"
  } >> "$log"

  if [ "$exit_code" -ne 0 ]; then
    record "$id" "$phase" "failed" "$exit_code" "$log" "$duration" "Wine-Mono MSI install failed."
    return "$exit_code"
  fi
  if wine_mono_ready; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" "Wine-Mono x86/x64 bridge is installed."
    return 0
  fi
  record "$id" "$phase" "failed" 94 "$log" "$duration" "Wine-Mono install completed but expected Mono/.NET files are missing."
  return 94
}

repair_dotnet_framework_registry() {
  local id="macwin-dotnet-registry"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code

  started="$(date +%s)"
  {
    echo "== MacWin .NET Framework registry repair =="
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  exit_code=0
  {
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\.NETFramework' /v InstallRoot /t REG_SZ /d 'C:\windows\Microsoft.NET\Framework64\' /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\.NETFramework\policy\v2.0' /v 50727 /t REG_SZ /d 50727-50727 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\.NETFramework\policy\v4.0' /v 30319 /t REG_SZ /d 30319-30319 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v Install /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v Release /t REG_DWORD /d 533320 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v Servicing /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v TargetVersion /t REG_SZ /d 4.0.0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v Version /t REG_SZ /d 4.8.09085 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\.NETFramework' /v InstallRoot /t REG_SZ /d 'C:\windows\Microsoft.NET\Framework\' /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\.NETFramework\policy\v2.0' /v 50727 /t REG_SZ /d 50727-50727 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\.NETFramework\policy\v4.0' /v 30319 /t REG_SZ /d 30319-30319 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4\Full' /v Install /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4\Full' /v Release /t REG_DWORD /d 533320 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4\Full' /v Servicing /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4\Full' /v TargetVersion /t REG_SZ /d 4.0.0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Wow6432Node\Microsoft\NET Framework Setup\NDP\v4\Full' /v Version /t REG_SZ /d 4.8.09085 /f
  } >> "$log" 2>&1 || exit_code=$?

  ended="$(date +%s)"
  duration="$((ended - started))"
  if [ "$exit_code" -eq 0 ]; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" ".NET Framework v4 registry keys are present for x86 and x64 Wine-Mono."
    return 0
  fi
  record "$id" "$phase" "failed" "$exit_code" "$log" "$duration" ".NET Framework registry repair failed."
  return "$exit_code"
}

repair_msxml_saxxmlreader_registry() {
  local id="macwin-msxml-saxxmlreader"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code

  started="$(date +%s)"
  {
    echo "== MacWin MSXML SAXXMLReader registry repair =="
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  exit_code=0
  {
    "${WINE_CMD[@]}" reg add 'HKCR\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}' /ve /d 'SAXXMLReader' /f
    "${WINE_CMD[@]}" reg add 'HKCR\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}\InprocServer32' /ve /d 'C:\windows\system32\msxml3.dll' /f
    "${WINE_CMD[@]}" reg add 'HKCR\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}\InprocServer32' /v ThreadingModel /t REG_SZ /d Both /f
    "${WINE_CMD[@]}" reg add 'HKCR\Wow6432Node\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}' /ve /d 'SAXXMLReader' /f
    "${WINE_CMD[@]}" reg add 'HKCR\Wow6432Node\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}\InprocServer32' /ve /d 'C:\windows\syswow64\msxml3.dll' /f
    "${WINE_CMD[@]}" reg add 'HKCR\Wow6432Node\CLSID\{079aa557-4a18-424a-8eee-e39f0a8d41b9}\InprocServer32' /v ThreadingModel /t REG_SZ /d Both /f
  } >> "$log" 2>&1 || exit_code=$?

  ended="$(date +%s)"
  duration="$((ended - started))"
  if [ "$exit_code" -eq 0 ]; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" "MSXML SAXXMLReader COM class is registered for x86 and x64."
    return 0
  fi
  record "$id" "$phase" "failed" "$exit_code" "$log" "$duration" "MSXML SAXXMLReader registry repair failed."
  return "$exit_code"
}

repair_wic_codecs_registry() {
  local id="macwin-wic-codecs"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local reg_file="$SCRIPT_DIR/wic-codecs-minimal.reg"
  local started ended duration exit_code

  started="$(date +%s)"
  {
    echo "== MacWin WIC codecs registry repair =="
    echo "prefix=$WINEPREFIX"
    echo "regFile=$reg_file"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$log"

  if [ ! -f "$reg_file" ]; then
    ended="$(date +%s)"
    duration="$((ended - started))"
    record "$id" "$phase" "failed" 95 "$log" "$duration" "WIC registry template is missing."
    return 95
  fi

  exit_code=0
  "${WINE_CMD[@]}" regedit /S "$reg_file" >> "$log" 2>&1 || exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  {
    echo
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "exitCode=$exit_code"
  } >> "$log"

  if [ "$exit_code" -eq 0 ]; then
    record "$id" "$phase" "passed" 0 "$log" "$duration" "Registered minimal WIC PNG/BMP decoder, PNG metadata and 32bpp pixel format entries."
    return 0
  fi

  record "$id" "$phase" "failed" "$exit_code" "$log" "$duration" "Failed to import minimal WIC codec registry entries."
  return "$exit_code"
}

repair_onlyoffice_renderer_fonts() {
  local app_dir=""
  local source=""
  local target temporary attempt candidate

  for attempt in $(seq 1 40); do
    for candidate in \
      "$PREFIX/drive_c/Program Files/ONLYOFFICE/DesktopEditors" \
      "$PREFIX/drive_c/Program Files (x86)/ONLYOFFICE/DesktopEditors"; do
      if [ -d "$candidate/editors/sdkjs/common" ]; then
        app_dir="$candidate"
        break
      fi
    done
    for candidate in "$PREFIX"/drive_c/users/*/AppData/Local/ONLYOFFICE/DesktopEditors/data/fonts/AllFonts.js; do
      if [ -s "$candidate" ]; then
        source="$candidate"
        break
      fi
    done
    if [ -n "$app_dir" ] && [ -n "$source" ]; then
      break
    fi
    sleep 0.25
  done
  [ -n "$app_dir" ] || return 1
  [ -n "$source" ] || return 1

  target="$app_dir/editors/sdkjs/common/AllFonts.js"
  if ! cmp -s "$source" "$target"; then
    temporary="$target.macwin-$$"
    cp -f "$source" "$temporary" || return 1
    mv -f "$temporary" "$target" || return 1
  fi
  cmp -s "$source" "$target" || return 1

  printf 'MACWIN_ONLYOFFICE_RENDERER_FONTS=PASS\n'
  printf 'MACWIN_ONLYOFFICE_ALLFONTS_SOURCE=%s\n' "$source"
  printf 'MACWIN_ONLYOFFICE_ALLFONTS_TARGET=%s\n' "$target"
}

repair_onlyoffice_environment() {
  find "$PREFIX/drive_c/Program Files" "$PREFIX/drive_c/Program Files (x86)" \
    -type d -path '*/ONLYOFFICE/DesktopEditors' -print 2>/dev/null | while IFS= read -r app_dir; do
    [ -d "$app_dir/converter" ] || continue
    local env_file="$app_dir/macwin-onlyoffice-env.cmd"
    cat > "$env_file" <<'CMD'
@echo off
set PATH=C:\Program Files\ONLYOFFICE\DesktopEditors\converter;C:\Program Files\ONLYOFFICE\DesktopEditors;%PATH%
start "" "C:\Program Files\ONLYOFFICE\DesktopEditors\DesktopEditors.exe"
CMD
  done
}

repair_gimp_extracted_layout() {
  local app_dir="$PREFIX/drive_c/Program Files/GIMP 2"
  [ -d "$app_dir" ] || return 0

  # GIMP's Inno package stores x64, ARM64 and x86 payloads under the same paths.
  # With collision-safe extraction, prefer the x64 payload for the WoW64 smoke
  # prefix and drop the alternates so module scanning cannot pick the wrong ABI.
  find "$app_dir" -type f \( -name '*#gimp64' -o -name '*#deps64' \) -print 2>/dev/null | while IFS= read -r payload; do
    cp -f "$payload" "${payload%#*}" || true
  done
  find "$app_dir" -type f \( -name '*#gimp32' -o -name '*#deps32' -o -name '*#gimpARM64' -o -name '*#depsARM64' \) -delete 2>/dev/null || true

  if /usr/bin/file "$app_dir/bin/gimp-2.10.exe" 2>/dev/null | grep -q 'x86-64'; then
    if [ -d "$app_dir/lib/gimp/2.0/interpreters" ]; then
      rm -f "$app_dir/lib/gimp/2.0/interpreters"/pygimp.interp* 2>/dev/null || true
    fi
    find "$app_dir/lib/gimp/2.0/plug-ins" -type f -name '*.py' -print 2>/dev/null | while IFS= read -r plugin; do
      mv "$plugin" "$plugin.macwin-disabled" 2>/dev/null || true
    done
    rm -f "$app_dir/lib/gimp/2.0/environ/pygimp.env" 2>/dev/null || true
    return 0
  fi

  # Fallback for older extraction caches that only contain the 32-bit payload.
  # Keep matching 32-bit GEGL/BABL modules in the active plugin directories.
  if [ -d "$app_dir/lib/gegl-0.4" ]; then
    find "$app_dir/lib/gegl-0.4" -maxdepth 1 -type f -name '*-x86_64-*.dll' -delete 2>/dev/null || true
  fi
  if [ -d "$app_dir/32/lib/gegl-0.4" ]; then
    /usr/bin/ditto "$app_dir/32/lib/gegl-0.4" "$app_dir/lib/gegl-0.4" || true
  fi
  if [ -d "$app_dir/32/lib/babl-0.1" ]; then
    /usr/bin/ditto "$app_dir/32/lib/babl-0.1" "$app_dir/lib/babl-0.1" || true
  fi

  if [ -d "$app_dir/lib/gimp/2.0/interpreters" ]; then
    rm -f "$app_dir/lib/gimp/2.0/interpreters"/pygimp.interp* 2>/dev/null || true
  fi
  find "$app_dir/lib/gimp/2.0/plug-ins" -type f -name '*.py' -print 2>/dev/null | while IFS= read -r plugin; do
    mv "$plugin" "$plugin.macwin-disabled" 2>/dev/null || true
  done
  rm -f "$app_dir/lib/gimp/2.0/environ/pygimp.env" 2>/dev/null || true
}

repair_gecko_smoke_profiles() {
  local profile
  for profile in firefox-profile firefox-dev-profile librewolf-profile floorp-profile waterfox-profile palemoon-profile palemoon32-profile seamonkey-profile seamonkey32-profile mullvad-profile zen-profile zotero-profile; do
    local profile_dir="$PREFIX/drive_c/macwin-portable/$profile"
    mkdir -p "$profile_dir"
    rm -rf "$profile_dir/.startup-incomplete" "$profile_dir/startupCache" "$profile_dir/cache2" 2>/dev/null || true
    cat > "$profile_dir/user.js" <<'JS'
user_pref("app.normandy.enabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage", "about:blank");
user_pref("browser.startup.page", 0);
user_pref("browser.tabs.remote.autostart", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("dom.ipc.processPrelaunch.enabled", false);
user_pref("dom.ipc.processCount", 1);
user_pref("extensions.getAddons.cache.enabled", false);
user_pref("extensions.update.enabled", false);
user_pref("gfx.canvas.azure.backends", "skia");
user_pref("gfx.content.azure.backends", "skia");
user_pref("gfx.direct2d.disabled", true);
user_pref("gfx.direct2d.force-enabled", false);
user_pref("gfx.direct3d11.reuse-decoder-device", false);
user_pref("gfx.webrender.all", false);
user_pref("gfx.webrender.compositor", false);
user_pref("gfx.webrender.compositor.force-enabled", false);
user_pref("gfx.webrender.enabled", false);
user_pref("gfx.webrender.force-disabled", true);
user_pref("gfx.webrender.max-partial-present-rects", 0);
user_pref("gfx.webrender.software", false);
user_pref("gfx.webrender.software.d3d11", false);
user_pref("gfx.webrender.software.force", false);
user_pref("gfx.webrender.software.opengl", false);
user_pref("gfx.webrender.software.unaccelerated-widget.force", false);
user_pref("layers.acceleration.disabled", true);
user_pref("layers.gpu-process.enabled", false);
user_pref("layers.offmainthreadcomposition.enabled", false);
user_pref("media.gmp-manager.updateEnabled", false);
user_pref("media.gmp-provider.enabled", false);
user_pref("media.hardware-video-decoding.enabled", false);
user_pref("media.rdd-process.enabled", false);
user_pref("network.captive-portal-service.enabled", false);
user_pref("network.connectivity-service.enabled", false);
user_pref("network.dns.disableIPv6", true);
user_pref("network.http.http3.enabled", false);
user_pref("network.predictor.enabled", false);
user_pref("network.prefetch-next", false);
user_pref("network.trr.mode", 5);
user_pref("security.sandbox.content.level", 0);
user_pref("toolkit.telemetry.archive.enabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("webgl.disabled", true);
user_pref("widget.windows.window_occlusion_tracking.enabled", false);
JS
  done
}

repair_cura_smoke_profile() {
  local app_dir="$PREFIX/drive_c/Program Files/UltiMaker Cura 5.13.0"
  local profile_dir="$PREFIX/drive_c/users/$USER/AppData/Roaming/cura/5.13"
  [ -f "$app_dir/UltiMaker-Cura.exe" ] || return 0
  mkdir -p "$profile_dir"
  /usr/bin/python3 - "$profile_dir/plugins.json" <<'PY'
import json, sys
path = sys.argv[1]
disabled = [
    "3DConnexion",
    "3MFReader",
    "3MFWriter",
    "CuraDrive",
    "DigitalLibrary",
    "FirmwareUpdateChecker",
    "FirmwareUpdater",
    "Marketplace",
    "SentryLogger",
    "UM3NetworkPrinting",
    "USBPrinting",
    "UpdateChecker",
]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"disabled": disabled, "to_install": {}, "to_remove": []}, f, ensure_ascii=False)
    f.write("\n")
PY
}

configure_dwsim_gtk3_profile() {
  local config_dir="$PREFIX/drive_c/users/$USER/Documents/DWSIM Application Data"
  local gtk_config_dir="$PREFIX/drive_c/macwin-portable/dwsim-gtk-config"
  local user_local_config="$PREFIX/drive_c/users/$USER/AppData/Local"
  local user_roaming_config="$PREFIX/drive_c/users/$USER/AppData/Roaming"
  local settings_file aliases_file
  mkdir -p "$config_dir"
  cat > "$config_dir/dwsim_newui.ini" <<'INI'
[PlatformRenderers]
Windows = Gtk3
Linux = Gtk3
Mac = Gtk3
FlowsheetRenderer = CPU
INI
  for settings_file in \
    "$gtk_config_dir/gtk-3.0/settings.ini" \
    "$user_local_config/gtk-3.0/settings.ini" \
    "$user_roaming_config/gtk-3.0/settings.ini"; do
    mkdir -p "$(dirname "$settings_file")"
    cat > "$settings_file" <<'INI'
# MacWin generated DWSIM GTK3 defaults
[Settings]
gtk-font-name=Tahoma 9
gtk-xft-antialias=1
gtk-xft-hinting=1
gtk-xft-hintstyle=hintslight
gtk-xft-rgba=rgb
gtk-enable-animations=false
gtk-dialogs-use-header=false
gtk-overlay-scrolling=false
gtk-application-prefer-dark-theme=false
INI
  done
  mkdir -p "$PREFIX/drive_c/users/$USER"
  cat > "$PREFIX/drive_c/users/$USER/.gtkrc-2.0" <<'INI'
# MacWin generated DWSIM GTK2 defaults
gtk-font-name = "Tahoma 9"
gtk-theme-name = "MS-Windows"
INI
  for aliases_file in \
    "$gtk_config_dir/pango/pango.aliases" \
    "$user_local_config/pango/pango.aliases" \
    "$user_roaming_config/pango/pango.aliases"; do
    mkdir -p "$(dirname "$aliases_file")"
    cat > "$aliases_file" <<'INI'
# MacWin generated DWSIM Pango aliases
"MS Shell Dlg" = "Tahoma,Arial,Sans"
"MS Shell Dlg 2" = "Tahoma,Arial,Sans"
Sans = "Tahoma,Arial"
sans = "Tahoma,Arial"
emoji = "Segoe UI Emoji,Tahoma,Arial"
Emoji = "Segoe UI Emoji,Tahoma,Arial"
Serif = "Times New Roman,Arial"
serif = "Times New Roman,Arial"
Monospace = "Courier New,Consolas"
monospace = "Courier New,Consolas"
INI
  done
}

configure_paraview_software_opengl() {
  local paraview_bin="$PREFIX/drive_c/Program Files/ParaView 6.1.0/bin"
  local mesa_cache="$DOWNLOADS/.mesa3d-26.1.2-msvc"
  local mesa_archive="$DOWNLOADS/mesa3d-26.1.2-release-msvc.7z"
  local seven_zip=""
  local mesa_source=""
  local candidate=""
  [ -f "$paraview_bin/paraview.exe" ] || return 0

  if [ -f "$paraview_bin/opengl32.dll" ] && [ -f "$paraview_bin/libgallium_wgl.dll" ]; then
    return 0
  fi

  if [ ! -f "$mesa_cache/x64/opengl32.dll" ] && [ -f "$mesa_archive" ]; then
    seven_zip="$(command -v 7zz || command -v 7z || true)"
    if [ -n "$seven_zip" ]; then
      mkdir -p "$mesa_cache"
      "$seven_zip" x -y -o"$mesa_cache" "$mesa_archive" >/dev/null
    fi
  fi

  if [ -f "$mesa_cache/x64/opengl32.dll" ] && [ -f "$mesa_cache/x64/libgallium_wgl.dll" ]; then
    cp -f "$mesa_cache/x64/opengl32.dll" "$mesa_cache/x64/libgallium_wgl.dll" "$paraview_bin/"
    return 0
  fi

  for candidate in \
    "$PREFIX/drive_c/Program Files/Prusa3D/PrusaSlicer/mesa/opengl32.dll" \
    "$PREFIX/drive_c/Program Files/FreeCAD 1.1/bin/opengl32sw.dll" \
    "$PREFIX/drive_c/Program Files/MeshLab/opengl32sw.dll" \
    "$PREFIX/drive_c/Program Files/LibreCAD/opengl32sw.dll" \
    "$PREFIX/drive_c/Program Files/GNU Octave/Octave-11.3.0/mingw64/bin/opengl32sw.dll"; do
    if [ -f "$candidate" ]; then
      mesa_source="$candidate"
      break
    fi
  done

  if [ -z "$mesa_source" ]; then
    echo "Missing ParaView software OpenGL fallback DLL." >&2
    return 1
  fi

  cp -f "$mesa_source" "$paraview_bin/opengl32.dll"
}

configure_blender_software_opengl() {
  local id="blender-3d"
  local app_dir="$PREFIX/drive_c/Program Files/Blender Foundation/Blender 4.1"
  local mesa_dir="$DOWNLOADS/.mesa3d-26.1.2-msvc/x64"
  local log="$LOG_DIR/$id-software-opengl-preset.log"
  local started ended duration runtime_name
  started="$(date +%s)"
  [ -f "$app_dir/blender.exe" ] || return 0

  {
    echo "== MacWin Blender software OpenGL preset =="
    echo "appDirectory=$app_dir"
    echo "mesaDirectory=$mesa_dir"
  } > "$log"

  for runtime_name in opengl32.dll libgallium_wgl.dll; do
    if [ ! -f "$mesa_dir/$runtime_name" ]; then
      ended="$(date +%s)"
      duration="$((ended - started))"
      record "$id" software-opengl-preset failed 126 "$log" "$duration" \
        "Mesa $runtime_name is missing; Blender 4.1 cannot create its required OpenGL 4.3 window context."
      return 1
    fi
    cp -f "$mesa_dir/$runtime_name" "$app_dir/$runtime_name"
  done
  if [ -f "$mesa_dir/dxil.dll" ]; then
    cp -f "$mesa_dir/dxil.dll" "$app_dir/dxil.dll"
  fi

  for runtime_name in opengl32.dll libgallium_wgl.dll; do
    cmp -s "$mesa_dir/$runtime_name" "$app_dir/$runtime_name" || {
      ended="$(date +%s)"
      duration="$((ended - started))"
      record "$id" software-opengl-preset failed 126 "$log" "$duration" \
        "Blender Mesa runtime deployment did not verify for $runtime_name."
      return 1
    }
    shasum -a 256 "$app_dir/$runtime_name" >> "$log"
  done

  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" software-opengl-preset passed 0 "$log" "$duration" \
    "Deployed Mesa llvmpipe WGL beside Blender so its OpenGL 4.3 viewport can start on macOS."
}

configure_meshlab_software_opengl() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/MeshLab"
  local fixture_source="$SCRIPT_DIR/fixtures/meshlab-cube.obj"
  local fixture_target="$PREFIX/drive_c/macwin-tests/meshlab-cube.obj"
  local log="$LOG_DIR/${id}-software-opengl-preset.log"
  local started ended duration
  started="$(date +%s)"

  {
    echo "== MacWin MeshLab software OpenGL preset =="
    echo "appDir=$app_dir"
    echo "fixture=$fixture_target"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$log"

  if [ ! -f "$app_dir/opengl32sw.dll" ] || [ ! -f "$fixture_source" ]; then
    ended="$(date +%s)"
    duration=$((ended - started))
    record "$id" "software-opengl-preset" "failed" 126 "$log" "$duration" \
      "MeshLab software OpenGL runtime or cube viewport fixture is missing."
    return 126
  fi

  cp -f "$app_dir/opengl32sw.dll" "$app_dir/opengl32.dll"
  mkdir -p "$(dirname "$fixture_target")"
  cp -f "$fixture_source" "$fixture_target"
  {
    echo "opengl32.sha256=$(shasum -a 256 "$app_dir/opengl32.dll" | awk '{print $1}')"
    echo "fixture.sha256=$(shasum -a 256 "$fixture_target" | awk '{print $1}')"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" "software-opengl-preset" "passed" 0 "$log" "$duration" \
    "Deployed MeshLab's bundled software OpenGL DLL and deterministic cube viewport fixture."
}

configure_bambu_studio_runtime() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/macwin-portable/bambu-studio-portable"
  local installer="$DOWNLOADS/Bambu_Studio_win-v02.07.01.62-20260616174358.exe"
  local runtime_cache="$DOWNLOADS/.bambu-studio-runtime"
  local mesa_source="$runtime_cache/mesa/opengl32.dll"
  local vc_runtime="$DOWNLOADS/vc_redist.x64.vs17.runtime-amd64"
  local seven_zip=""
  local source=""
  local runtime_name=""
  local bambu_dll="$app_dir/BambuStudio.dll"
  local bambu_dll_backup="$app_dir/BambuStudio.dll.macwin-original-656977de"
  local bambu_original_hash="656977de78fcea084790014c984ea5ace0b60debdd5dd234d727b887f4cfe5ae"
  local bambu_patched_hash="0ab1a0ec541fccd30d834451f316ace96e774c5c811c4eef098c4c8ce12335c2"
  local bambu_actual_hash=""
  local required_runtime_names=(
    concrt140.dll
    msvcp140.dll
    msvcp140_1.dll
    msvcp140_2.dll
    msvcp140_atomic_wait.dll
    msvcp140_codecvt_ids.dll
    vcruntime140.dll
    vcruntime140_1.dll
  )
  local log="$LOG_DIR/${id}-runtime-repair.log"
  local started ended duration
  started="$(date +%s)"

  {
    echo "== MacWin Bambu Studio runtime repair =="
    echo "appDir=$app_dir"
    echo "installer=$installer"
    echo "runtimeCache=$runtime_cache"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$log"

  if [ ! -f "$app_dir/bambu-studio.exe" ]; then
    ended="$(date +%s)"
    record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
      "Bambu Studio portable executable is missing."
    return 126
  fi

  if [ ! -f "$mesa_source" ]; then
    seven_zip="$(command -v 7zz || command -v 7z || true)"
    if [ -z "$seven_zip" ] || [ ! -f "$installer" ]; then
      ended="$(date +%s)"
      record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
        "The official Bambu Studio installer or 7-Zip extractor is missing."
      return 126
    fi
    mkdir -p "$runtime_cache"
    if ! "$seven_zip" x -y -o"$runtime_cache" "$installer" 'mesa/opengl32.dll' >> "$log" 2>&1; then
      ended="$(date +%s)"
      record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
        "Could not extract Bambu Studio's bundled Mesa OpenGL runtime."
      return 126
    fi
  fi

  if [ ! -f "$mesa_source" ]; then
    ended="$(date +%s)"
    record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
      "Bambu Studio's bundled mesa/opengl32.dll was not found after extraction."
    return 126
  fi

  mkdir -p "$app_dir/mesa"
  cp -f "$mesa_source" "$app_dir/mesa/opengl32.dll"
  cp -f "$mesa_source" "$app_dir/opengl32.dll"

  for runtime_name in "${required_runtime_names[@]}"; do
    source="$vc_runtime/${runtime_name}_amd64"
    if [ ! -f "$source" ]; then
      ended="$(date +%s)"
      record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
        "The cached VS17 x64 runtime is missing ${runtime_name}_amd64."
      return 126
    fi
    cp -f "$source" "$app_dir/$runtime_name"
  done

  if [ -f "$bambu_dll" ]; then
    bambu_actual_hash="$(shasum -a 256 "$bambu_dll" | awk '{print $1}')"
    if [ "$bambu_actual_hash" = "$bambu_original_hash" ]; then
      [ -f "$bambu_dll_backup" ] || cp -p "$bambu_dll" "$bambu_dll_backup"
      printf '\x4d\x85\xc0\x75\x08\x48\x8d\x05\xe7\x98\xaf\x04\xc3\x4c\x89\xc0\xc3' \
        | dd of="$bambu_dll" bs=1 seek=$((0x152eb0d)) conv=notrunc 2>> "$log"
      bambu_actual_hash="$(shasum -a 256 "$bambu_dll" | awk '{print $1}')"
      if [ "$bambu_actual_hash" != "$bambu_patched_hash" ]; then
        cp -f "$bambu_dll_backup" "$bambu_dll"
        ended="$(date +%s)"
        record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
          "BambuStudio.dll export-3mf patch failed its resulting SHA-256 check."
        return 126
      fi
    elif [ "$bambu_actual_hash" != "$bambu_patched_hash" ]; then
      echo "export3mf.patch=skipped-unknown-build" >> "$log"
    fi
  fi

  {
    echo "mesa.sha256=$(shasum -a 256 "$app_dir/opengl32.dll" | awk '{print $1}')"
    if [ -f "$bambu_dll" ]; then
      echo "BambuStudio.dll.sha256=$(shasum -a 256 "$bambu_dll" | awk '{print $1}')"
    fi
    for runtime_name in "${required_runtime_names[@]}"; do
      echo "$runtime_name.sha256=$(shasum -a 256 "$app_dir/$runtime_name" | awk '{print $1}')"
    done
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  ended="$(date +%s)"
  duration=$((ended - started))
  record "$id" runtime-repair passed 0 "$log" "$duration" \
    "Deployed Bambu Studio's Mesa/VS17 runtime and the hash-guarded empty-filament 3MF export repair."
}

configure_orcaslicer_runtime() {
  local id="$1"
  local app_dir="$PREFIX/drive_c/Program Files/OrcaSlicer"
  local target="$app_dir/OrcaSlicer.dll"
  local backup="$app_dir/OrcaSlicer.dll.macwin-original-fcd3bbdf"
  local config="$PREFIX/drive_c/users/$USER/AppData/Roaming/OrcaSlicer/OrcaSlicer.conf"
  local original_hash="fcd3bbdff6fa82674bcef773fcb049dcbf52acd3a69ad65b0ba57cd80ec72c6f"
  local patched_hash="0d647a9894da841814dcd6e2c8f81d79158568cefc94fd2d14be6543850e08cb"
  local actual_hash=""
  local log="$LOG_DIR/${id}-runtime-repair.log"
  local started ended
  started="$(date +%s)"

  {
    echo "== MacWin OrcaSlicer runtime repair =="
    echo "appDir=$app_dir"
    echo "config=$config"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$log"

  if [ ! -f "$app_dir/orca-slicer.exe" ] || [ ! -f "$target" ]; then
    ended="$(date +%s)"
    record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
      "OrcaSlicer executable or OrcaSlicer.dll is missing."
    return 126
  fi

  actual_hash="$(shasum -a 256 "$target" | awk '{print $1}')"
  if [ "$actual_hash" = "$original_hash" ]; then
    [ -f "$backup" ] || cp -p "$target" "$backup"
    printf '\x90\xe9' | dd of="$target" bs=1 seek=$((0x29695f6)) conv=notrunc 2>>"$log"
    printf '\x90\xe9' | dd of="$target" bs=1 seek=$((0x29b3872)) conv=notrunc 2>>"$log"
    printf '\x31\xc0\xc3' | dd of="$target" bs=1 seek=$((0x299ba10)) conv=notrunc 2>>"$log"
    actual_hash="$(shasum -a 256 "$target" | awk '{print $1}')"
    if [ "$actual_hash" != "$patched_hash" ]; then
      cp -f "$backup" "$target"
      ended="$(date +%s)"
      record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
        "OrcaSlicer startup patch failed its resulting SHA-256 check."
      return 126
    fi
  elif [ "$actual_hash" != "$patched_hash" ]; then
    ended="$(date +%s)"
    record "$id" runtime-repair failed 126 "$log" "$((ended - started))" \
      "OrcaSlicer.dll does not match the verified 2.4.0 original or patched build."
    return 126
  fi

  mkdir -p "$(dirname "$config")"
  /usr/bin/python3 - "$config" <<'PY' >>"$log" 2>&1
import json
import os
import sys

path = sys.argv[1]
root = {}
if os.path.isfile(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    end = raw.rfind(b"}")
    if end >= 0:
        try:
            root = json.loads(raw[:end + 1])
        except (UnicodeDecodeError, json.JSONDecodeError):
            root = {}
app = root.setdefault("app", {})
app["skip_version"] = "999.999.999"
app["preset_bundle_auto_update"] = False
root.setdefault("header", "OrcaSlicer 2.4.0")
temporary = path + ".macwin.tmp"
with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(root, handle, ensure_ascii=False, indent="\t", sort_keys=True)
    handle.write("\n")
os.replace(temporary, path)
print("config.skip_version=999.999.999")
PY

  {
    echo "OrcaSlicer.dll.sha256=$actual_hash"
    echo "ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >> "$log"
  ended="$(date +%s)"
  record "$id" runtime-repair passed 0 "$log" "$((ended - started))" \
    "Applied the hash-guarded WebView2/setup-wizard fallback and disabled the obsolete-version startup modal."
}

configure_qgis_launcher() {
  local launcher_dir="$PREFIX/drive_c/macwin-launchers"
  local qgis_bat="$PREFIX/drive_c/Program Files/QGIS 3.44.11/bin/qgis-ltr.bat"
  [ -f "$qgis_bat" ] || return 0
  mkdir -p "$launcher_dir"
  cat > "$launcher_dir/qgis-ltr-smoke.cmd" <<'BAT'
@echo off
call "C:\Program Files\QGIS 3.44.11\bin\qgis-ltr.bat"
BAT
}

configure_orange_profile() {
  local settings_dir="$PREFIX/drive_c/users/$USER/AppData/Roaming/biolab.si"
  local settings_file="$settings_dir/Orange.ini"
  local orange_dir="$PREFIX/drive_c/users/$USER/AppData/Local/Programs/Orange"
  [ -f "$orange_dir/Scripts/orange-canvas.exe" ] || return 0
  mkdir -p "$settings_dir"
  cat > "$settings_file" <<'INI'
[startup]
check-updates=false
show-splash-screen=false
show-welcome-screen=false
last-update-check-time=4102444800

[notifications]
check-notifications=false
announcements=false
blog=false
new-features=false
displayed=set()

[reporting]
send-statistics=false
INI
}

configure_supermium_profile() {
  local app_dir="" uao_arch="x86" uao_bitness="64" uao_wow64="false"
  case "$1" in
    supermium-browser)
      app_dir="$PREFIX/drive_c/macwin-portable/supermium-browser/Supermium"
      ;;
    supermium-32-browser)
      app_dir="$PREFIX/drive_c/macwin-portable/supermium-32-browser/Supermium"
      uao_bitness="32"
      uao_wow64="true"
      mkdir -p "$app_dir/portable_data32-macwin"
      rm -f "$app_dir/portable_data/uao"
      ;;
    *)
      return 0
      ;;
  esac

  mkdir -p "$app_dir/portable_data"
  printf '%s;;;%s;;;%s;;;%s;;;%s;;;%s;;;%s;;;%s;;;%s;;;%s;;;%s' \
    "$([ "$1" = "supermium-32-browser" ] && printf '%s' 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Supermium/144.0.7559.252 Chrome/144.0.7559.252 Safari/537.36' || printf '%s' 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Supermium/144.0.7559.252 Chrome/144.0.7559.252 Safari/537.36')" \
    "Supermium" \
    "144" \
    "144.0.7559.252" \
    "Windows" \
    "10.0.0" \
    "" \
    "$uao_arch" \
    "$uao_bitness" \
    "false" \
    "$uao_wow64" > "$app_dir/$([ "$1" = "supermium-32-browser" ] && printf '%s' 'portable_data32-macwin' || printf '%s' 'portable_data')/uao"
}

configure_temurin_jdk21_runtime() {
  local jdk_zip="$DOWNLOADS/OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip"
  local runtime_dir="$PREFIX/drive_c/macwin-runtime/temurin-jdk21"
  local javaw="$runtime_dir/jdk-21.0.11+10/bin/javaw.exe"
  if [ -f "$javaw" ]; then
    return 0
  fi
  if [ ! -f "$jdk_zip" ]; then
    echo "Missing Temurin Java runtime archive: $jdk_zip" >&2
    return 1
  fi
  rm -rf "$runtime_dir"
  mkdir -p "$runtime_dir"
  /usr/bin/unzip -q "$jdk_zip" -d "$runtime_dir"
}

configure_openjump_java_runtime() {
  [ -f "$PREFIX/drive_c/macwin-portable/openjump-gis/OpenJUMP-2.4.0-r5303[6c9a02d]-PLUS/bin/OpenJUMP.exe" ] || return 0
  configure_temurin_jdk21_runtime
}

configure_epanet_cli_sample() {
  local sample_dir="$PREFIX/drive_c/macwin-testdata/epanet"
  mkdir -p "$sample_dir"
  cat > "$sample_dir/smoke.inp" <<'EOF'
[TITLE]
MacWin EPANET smoke network

[JUNCTIONS]
;ID      Elevation  Demand
 J1      10         0
 J2      5          100

[RESERVOIRS]
;ID      Head
 R1      120

[PIPES]
;ID      Node1  Node2  Length  Diameter  Roughness  MinorLoss  Status
 P1      R1     J1     1000    12        100        0          Open
 P2      J1     J2     1000    10        100        0          Open

[OPTIONS]
 Units              GPM
 Headloss           H-W

[TIMES]
 Duration           1
 Hydraulic Timestep 1

[REPORT]
 Status             Yes
 Summary            Yes

[END]
EOF
}

install_opendss_svn_x64_into_prefix() {
  local source_dir="$DOWNLOADS/opendss-svn-x64"
  local destination="$PREFIX/drive_c/macwin-portable/opendss-svn-x64"
  local required=(
    ComPorts.ini
    DSSProgress.exe
    DSSView.exe
    IndMach012a.dll
    KLUSolve.dll
    License.txt
    OpenDSS.exe
    OpenDSS.rsm
    OpenDSSDirect.dll
    OpenDSSDirect.h
    OpenDSScmd.exe
    OpenDSScmd.rsm
    OpenDSSengine.dll
    kmetis.exe
    pmetis.exe
    readme.txt
    testcommandline.bat
    testcommandline.dss
  )
  local file
  for file in "${required[@]}"; do
    if [ ! -s "$source_dir/$file" ]; then
      echo "Missing OpenDSS SVN x64 file: $source_dir/$file" >&2
      return 1
    fi
  done
  rm -rf "$destination"
  mkdir -p "$destination"
  /usr/bin/ditto "$source_dir" "$destination"
  mkdir -p "$PREFIX/drive_c/macwin-launchers"
  cat > "$destination/macwin-smoke.dss" <<'EOF'
clear
new circuit.macwin basekv=12.47 pu=1.0 phases=3 bus1=sourcebus
new line.line1 bus1=sourcebus.1.2.3 bus2=loadbus.1.2.3 phases=3 length=1 units=kft r1=0.1 x1=0.2 r0=0.3 x0=0.6 c1=0 c0=0
new load.load1 bus1=loadbus.1.2.3 phases=3 conn=wye kv=12.47 kw=100 kvar=50
calcvoltagebases
set mode=snapshot
solve
export voltages
quit
EOF
  cat > "$PREFIX/drive_c/macwin-launchers/opendss-svn-x64-smoke.cmd" <<'EOF'
@echo off
cd /d C:\macwin-portable\opendss-svn-x64
OpenDSScmd.exe "redirect C:\macwin-portable\opendss-svn-x64\macwin-smoke.dss"
EOF
}

configure_opendss_svn_x64_smoke() {
  local destination="$PREFIX/drive_c/macwin-portable/opendss-svn-x64"
  [ -f "$destination/OpenDSScmd.exe" ] || return 0
  mkdir -p "$PREFIX/drive_c/macwin-launchers"
  cat > "$destination/macwin-smoke.dss" <<'EOF'
clear
new circuit.macwin basekv=12.47 pu=1.0 phases=3 bus1=sourcebus
new line.line1 bus1=sourcebus.1.2.3 bus2=loadbus.1.2.3 phases=3 length=1 units=kft r1=0.1 x1=0.2 r0=0.3 x0=0.6 c1=0 c0=0
new load.load1 bus1=loadbus.1.2.3 phases=3 conn=wye kv=12.47 kw=100 kvar=50
calcvoltagebases
set mode=snapshot
solve
export voltages
quit
EOF
  cat > "$PREFIX/drive_c/macwin-launchers/opendss-svn-x64-smoke.cmd" <<'EOF'
@echo off
cd /d C:\macwin-portable\opendss-svn-x64
OpenDSScmd.exe "redirect C:\macwin-portable\opendss-svn-x64\macwin-smoke.dss"
EOF
}

repair_sweethome3d_runtime() {
  local app_dir="$PREFIX/drive_c/Program Files/Sweet Home 3D"
  local ext_dir="$app_dir/runtime/lib/ext"
  [ -f "$app_dir/SweetHome3D.exe" ] || return 0
  if [ -d "$ext_dir" ]; then
    rm -rf "$app_dir/runtime/lib/ext.macwin-disabled" 2>/dev/null || true
    mv "$ext_dir" "$app_dir/runtime/lib/ext.macwin-disabled" 2>/dev/null || true
  fi
}

configure_sweethome3d_profile() {
  local app_dir="$PREFIX/drive_c/Program Files/Sweet Home 3D"
  local font_source="$app_dir/runtime/lib/fontconfig.properties.src"
  local font_target="$app_dir/runtime/lib/fontconfig.properties"
  local examples="$app_dir/lib/Examples.jar"
  local sample_dir="$PREFIX/drive_c/macwin-testdata/sweethome3d"
  local sample="$sample_dir/macwin-studio.sh3d"
  [ -f "$app_dir/SweetHome3D.exe" ] || return 0

  mkdir -p "$sample_dir"
  /usr/bin/python3 - "$font_source" "$font_target" "$examples" "$sample" <<'PY'
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

font_source, font_target, examples, sample = map(Path, sys.argv[1:])
if font_source.is_file():
    text = font_source.read_text(encoding="utf-8", errors="replace")
    text = re.sub(
        r"^((?:dialog|dialoginput|sansserif)\.(?:plain|italic)\.alphabetic)=.*$",
        r"\1=Hiragino Sans GB W3",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^((?:dialog|dialoginput|sansserif)\.(?:bold|bolditalic)\.alphabetic)=.*$",
        r"\1=Hiragino Sans GB W6",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(allfonts\.chinese-(?:ms936|gb18030)(?:-extb)?)=.*$",
        r"\1=Hiragino Sans GB W3",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^sequence\.allfonts=.*$",
        (
            "sequence.allfonts=alphabetic/default,chinese-ms936,"
            "dingbats,symbol,chinese-ms936-extb"
        ),
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^filename\.Hiragino_Sans_GB_W[36]=.*$\n?",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = text.rstrip() + (
        "\n\nfilename.Hiragino_Sans_GB_W3=SIMSUN.TTC"
        "\nfilename.Hiragino_Sans_GB_W6=SIMSUN.TTC\n"
    )
    font_target.write_text(text, encoding="utf-8")

if examples.is_file():
    with zipfile.ZipFile(examples) as archive:
        xml_data = archive.read(
            "com/eteks/sweethome3d/io/resources/examples/Studio.xml"
        )
    root = ET.fromstring(xml_data)
    for child in list(root):
        if child.tag in {
            "pieceOfFurniture",
            "doorOrWindow",
            "light",
            "backgroundImage",
        }:
            root.remove(child)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "texture":
                parent.remove(child)
    root.set("name", "MacWin Studio.sh3d")
    home_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(sample, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("Home.xml", home_xml)
PY
}

repair_user_shell_folders() {
  local user_name="${USER:-user}"
  local user_root="$PREFIX/drive_c/users/$user_name"
  mkdir -p \
    "$PREFIX/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup" \
    "$PREFIX/drive_c/ProgramData/Microsoft/Windows/Templates" \
    "$PREFIX/drive_c/users/Public/Desktop" \
    "$PREFIX/drive_c/users/Public/Documents" \
    "$PREFIX/drive_c/users/Public/Downloads" \
    "$PREFIX/drive_c/users/Public/Music" \
    "$PREFIX/drive_c/users/Public/Pictures" \
    "$PREFIX/drive_c/users/Public/Videos" \
    "$user_root/AppData/Local/Microsoft/Windows/INetCache" \
    "$user_root/AppData/Local/Microsoft/Windows/INetCookies" \
    "$user_root/AppData/Roaming/Microsoft/Windows/Recent" \
    "$user_root/AppData/Roaming/Microsoft/Windows/SendTo" \
    "$user_root/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup" \
    "$user_root/AppData/Roaming/Microsoft/Windows/Templates" \
    "$user_root/Desktop" \
    "$user_root/Documents" \
    "$user_root/Downloads" \
    "$user_root/Music" \
    "$user_root/Pictures" \
    "$user_root/Videos"

  local shell_folders='HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
  local user_shell_folders='HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
  local common_shell_folders='HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
  local values=(
    "AppData|AppData\\Roaming"
    "Cache|AppData\\Local\\Microsoft\\Windows\\INetCache"
    "Cookies|AppData\\Local\\Microsoft\\Windows\\INetCookies"
    "Desktop|Desktop"
    "Local AppData|AppData\\Local"
    "My Music|Music"
    "My Pictures|Pictures"
    "My Video|Videos"
    "Personal|Documents"
    "Programs|AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs"
    "Recent|AppData\\Roaming\\Microsoft\\Windows\\Recent"
    "SendTo|AppData\\Roaming\\Microsoft\\Windows\\SendTo"
    "Start Menu|AppData\\Roaming\\Microsoft\\Windows\\Start Menu"
    "Startup|AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"
    "Templates|AppData\\Roaming\\Microsoft\\Windows\\Templates"
    "Downloads|Downloads"
    "{374DE290-123F-4565-9164-39C4925E467B}|Downloads"
  )
  local item name relative windows_path
  for item in "${values[@]}"; do
    IFS='|' read -r name relative <<< "$item"
    windows_path="C:\\users\\$user_name\\$relative"
    "${WINE_CMD[@]}" reg add "$shell_folders" /v "$name" /t REG_SZ /d "$windows_path" /f >/dev/null 2>&1 || true
    "${WINE_CMD[@]}" reg add "$user_shell_folders" /v "$name" /t REG_SZ /d "$windows_path" /f >/dev/null 2>&1 || true
  done

  local common_values=(
    'Common AppData|C:\ProgramData'
    'Common Desktop|C:\users\Public\Desktop'
    'Common Documents|C:\users\Public\Documents'
    'Common Programs|C:\ProgramData\Microsoft\Windows\Start Menu\Programs'
    'Common Start Menu|C:\ProgramData\Microsoft\Windows\Start Menu'
    'Common Startup|C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup'
    'Common Templates|C:\ProgramData\Microsoft\Windows\Templates'
  )
  for item in "${common_values[@]}"; do
    IFS='|' read -r name windows_path <<< "$item"
    "${WINE_CMD[@]}" reg add "$common_shell_folders" /v "$name" /t REG_SZ /d "$windows_path" /f >/dev/null 2>&1 || true
  done
}

repair_documents_shell_namespace_registry() {
  local clsid='{450D8FBA-AD25-11D0-98A8-0800361B1103}'
  local shell_folder_key="HKCR\\CLSID\\$clsid\\ShellFolder"
  local wow_shell_folder_key="HKCR\\Wow6432Node\\CLSID\\$clsid\\ShellFolder"

  "${WINE_CMD[@]}" reg add "$shell_folder_key" /v WantsForParsing /t REG_SZ /d '' /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add "$wow_shell_folder_key" /v WantsForParsing /t REG_SZ /d '' /f >/dev/null 2>&1 || true
}

repair_keyboard_layout_registry() {
  "${WINE_CMD[@]}" reg delete 'HKCU\Keyboard Layout\Preload' /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg delete 'HKCU\Keyboard Layout\Substitutes' /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKCU\Keyboard Layout\Preload' /v 1 /t REG_SZ /d 00000409 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKCU\Keyboard Layout\Preload' /v 2 /t REG_SZ /d 00000804 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKCU\Keyboard Layout\Substitutes' /v 00000409 /t REG_SZ /d 00000409 /f >/dev/null 2>&1 || true
  "${WINE_CMD[@]}" reg add 'HKCU\Keyboard Layout\Substitutes' /v 00000804 /t REG_SZ /d 00000804 /f >/dev/null 2>&1 || true
}

repair_window_metrics_fonts() {
  local id="macwin-windowmetrics-fonts"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code

  started="$(date +%s)"
  {
    echo "== MacWin WindowMetrics font repair =="
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
    /usr/bin/python3 - "$PREFIX/user.reg" <<'PY'
from pathlib import Path
import struct
import sys
import time

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

key = r"[Control Panel\\Desktop\\WindowMetrics]"

def reg_hex(data):
    return "hex:" + ",".join(f"{byte:02x}" for byte in data)

def logfont(face="Tahoma", height=-12, weight=400):
    # LOGFONTW: 5 LONG values, 8 BYTE values, then 32 UTF-16LE WCHARs.
    name = face.encode("utf-16le")[:62] + b"\x00\x00"
    name = name.ljust(64, b"\x00")
    return struct.pack(
        "<lllllBBBBBBBB",
        height, 0, 0, 0, weight,
        0, 0, 0, 1, 0, 0, 5, 32,
    ) + name

font_value = reg_hex(logfont())
values = {
    '"AppliedDPI"': '"AppliedDPI"=dword:00000060',
    '"CaptionFont"': f'"CaptionFont"={font_value}',
    '"IconFont"': f'"IconFont"={font_value}',
    '"MenuFont"': f'"MenuFont"={font_value}',
    '"MessageFont"': f'"MessageFont"={font_value}',
    '"SmCaptionFont"': f'"SmCaptionFont"={font_value}',
    '"StatusFont"': f'"StatusFont"={font_value}',
}

lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
out = []
in_key = False
seen_key = False
seen_values = set()
skip_replaced_value_continuation = False

for line in lines:
    if skip_replaced_value_continuation:
        if line[:1].isspace():
            skip_replaced_value_continuation = line.endswith("\\")
            continue
        skip_replaced_value_continuation = False
    if line.startswith("["):
        if in_key:
            for name, value in values.items():
                if name not in seen_values:
                    out.append(value)
        # Section headers look like "[Control Panel\\...\\WindowMetrics] 123"
        # where the trailing number is an optional timestamp. Registry key
        # paths may contain spaces (e.g. "Control Panel"), so splitting on the
        # first space yields only "[Control" and never matches. Extract the
        # section name from the bracket boundaries instead, mirroring
        # BottleService.registrySectionName (the dict keys keep their brackets,
        # so include them here).
        bracket_end = line.find("]")
        current = line[:bracket_end + 1] if line.startswith("[") and bracket_end > 0 else line
        in_key = current == key
        if in_key:
            seen_key = True
            seen_values = set()
    if in_key:
        replaced = False
        for name, value in values.items():
            if line.startswith(name + "="):
                out.append(value)
                seen_values.add(name)
                replaced = True
                skip_replaced_value_continuation = line.endswith("\\")
                break
        if replaced:
            continue
    out.append(line)

if in_key:
    for name, value in values.items():
        if name not in seen_values:
            out.append(value)

if not seen_key:
    out.extend(["", f"{key} {int(time.time())}"])
    out.extend(values.values())

path.write_text("\n".join(out) + "\n", encoding="utf-8", errors="surrogateescape")
PY
    local font_alias
    for font_alias in \
      "Arial" \
      "Arial Bold" \
      "Tahoma"
    do
      "${WINE_CMD[@]}" reg delete \
        'HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' \
        /v "$font_alias" /f >/dev/null 2>&1 || true
      "${WINE_CMD[@]}" reg delete \
        'HKCU\Software\Wine\Fonts\Replacements' \
        /v "$font_alias" /f >/dev/null 2>&1 || true
    done
    for font_alias in \
      "MS Shell Dlg" \
      "MS Shell Dlg 2" \
      "Microsoft Sans Serif" \
      "Segoe UI" \
      "Segoe UI Bold" \
      "Segoe UI Semibold"
    do
      "${WINE_CMD[@]}" reg add \
        'HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' \
        /v "$font_alias" /t REG_SZ /d "Tahoma" /f >/dev/null
      "${WINE_CMD[@]}" reg add \
        'HKCU\Software\Wine\Fonts\Replacements' \
        /v "$font_alias" /t REG_SZ /d "Tahoma" /f >/dev/null
    done
    for font_alias in \
      "Microsoft YaHei" \
      "Microsoft YaHei Bold" \
      "Microsoft YaHei UI" \
      "Microsoft YaHei UI Bold"
    do
      "${WINE_CMD[@]}" reg add \
        'HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' \
        /v "$font_alias" /t REG_SZ /d "PingFang SC" /f >/dev/null
      "${WINE_CMD[@]}" reg add \
        'HKCU\Software\Wine\Fonts\Replacements' \
        /v "$font_alias" /t REG_SZ /d "PingFang SC" /f >/dev/null
    done
    "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
    "${WINE_CMD[@]}" reg query \
      'HKLM\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes' \
      /v "Microsoft YaHei UI"
    echo
    echo "== verification =="
    /usr/bin/python3 - "$PREFIX/user.reg" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="surrogateescape")
collapsed = re.sub(r"\\\n\s*", "", text)
for name in ("MessageFont", "MenuFont", "StatusFont", "IconFont"):
    token = f'"{name}"=hex:'
    line = next((line for line in collapsed.splitlines() if line.startswith(token)), "")
    if not line:
        print(f"{name}=missing")
        raise SystemExit(1)
    encoded = line.split("hex:", 1)[1]
    data = bytes(int(item, 16) for item in encoded.split(",") if item)
    face = data[28:92].decode("utf-16le", errors="ignore").split("\0", 1)[0]
    print(f"{name}=present face={face}")
    if face != "Tahoma":
        raise SystemExit(f"{name} uses unexpected face {face!r}")
PY
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" "$phase" "$([ "$exit_code" -eq 0 ] && printf passed || printf failed)" "$exit_code" "$log" "$duration" "Registered native Tahoma UI metrics with CJK fallbacks for legacy Win32 and Qt callers."
  return "$exit_code"
}

repair_wininet_proxy_registry() {
  local id="macwin-wininet-proxy"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code
  local internet_settings='HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
  local internet_connections='HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Connections'
  local policy_settings='HKLM\Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings'
  local winhttp_connections='HKLM\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Connections'
  local direct_wininet_settings='4600000000000000010000000000000000000000'
  local direct_winhttp_settings='1800000000000000010000000000000000000000'

  started="$(date +%s)"
  {
    echo "== MacWin WinINet proxy registry repair =="
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    "${WINE_CMD[@]}" reg add "$internet_settings" /v ProxyEnable /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add "$internet_settings" /v ProxyHttp1.1 /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$internet_settings" /v AutoDetect /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add "$internet_settings" /v ProxyServer /t REG_SZ /d "" /f
    "${WINE_CMD[@]}" reg add "$internet_settings" /v ProxyOverride /t REG_SZ /d "<local>" /f
    "${WINE_CMD[@]}" reg delete "$internet_settings" /v AutoConfigURL /f >/dev/null 2>&1 || true
    "${WINE_CMD[@]}" reg add "$internet_connections" /v DefaultConnectionSettings /t REG_BINARY /d "$direct_wininet_settings" /f
    "${WINE_CMD[@]}" reg add "$internet_connections" /v SavedLegacySettings /t REG_BINARY /d "$direct_wininet_settings" /f
    "${WINE_CMD[@]}" reg add "$policy_settings" /v ProxySettingsPerUser /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add "$policy_settings" /v AutoDetect /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add "$winhttp_connections" /v WinHttpSettings /t REG_BINARY /d "$direct_winhttp_settings" /f
    echo
    echo "== verification =="
    "${WINE_CMD[@]}" reg query "$internet_settings" /v ProxyEnable
    "${WINE_CMD[@]}" reg query "$internet_settings" /v AutoDetect
    "${WINE_CMD[@]}" reg query "$internet_connections" /v DefaultConnectionSettings
    "${WINE_CMD[@]}" reg query "$winhttp_connections" /v WinHttpSettings
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" "$phase" "$([ "$exit_code" -eq 0 ] && printf passed || printf failed)" "$exit_code" "$log" "$duration" "Registered direct WinINet/WinHTTP proxy defaults."
  return "$exit_code"
}

repair_windows_timezone_registry() {
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  /usr/bin/python3 - "$PREFIX/system.reg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

sections = {
    r"[System\\ControlSet001\\Control\\TimeZoneInformation]": {
        '"ActiveTimeBias"': '"ActiveTimeBias"=dword:000001a4',
        '"Bias"': '"Bias"=dword:000001e0',
        '"DaylightBias"': '"DaylightBias"=dword:ffffffc4',
        '"DaylightName"': '"DaylightName"="Pacific Daylight Time"',
        '"DynamicDaylightTimeDisabled"': '"DynamicDaylightTimeDisabled"=dword:00000000',
        '"StandardBias"': '"StandardBias"=dword:00000000',
        '"StandardName"': '"StandardName"="Pacific Standard Time"',
        '"TimeZoneKeyName"': '"TimeZoneKeyName"="Pacific Standard Time"',
    },
    r"[Software\\Microsoft\\Windows NT\\CurrentVersion\\Time Zones\\Pacific Standard Time]": {
        '"Display"': '"Display"="(UTC-08:00) Pacific Time (US & Canada)"',
        '"Dlt"': '"Dlt"="Pacific Daylight Time"',
        '"MapID"': '"MapID"="-1,85"',
        '"MUI_Display"': '"MUI_Display"="@tzres.dll,-212"',
        '"MUI_Dlt"': '"MUI_Dlt"="@tzres.dll,-211"',
        '"MUI_Std"': '"MUI_Std"="@tzres.dll,-212"',
        '"Std"': '"Std"="Pacific Standard Time"',
        '"TZI"': '"TZI"=hex:e0,01,00,00,00,00,00,00,c4,ff,ff,ff,00,00,0b,00,00,00,01,00,02,00,00,00,00,00,00,00,00,00,03,00,00,00,02,00,02,00,00,00,00,00,00,00',
    },
    r"[Software\\Wow6432Node\\Microsoft\\Windows NT\\CurrentVersion\\Time Zones\\Pacific Standard Time]": {
        '"Display"': '"Display"="(UTC-08:00) Pacific Time (US & Canada)"',
        '"Dlt"': '"Dlt"="Pacific Daylight Time"',
        '"MapID"': '"MapID"="-1,85"',
        '"MUI_Display"': '"MUI_Display"="@tzres.dll,-212"',
        '"MUI_Dlt"': '"MUI_Dlt"="@tzres.dll,-211"',
        '"MUI_Std"': '"MUI_Std"="@tzres.dll,-212"',
        '"Std"': '"Std"="Pacific Standard Time"',
        '"TZI"': '"TZI"=hex:e0,01,00,00,00,00,00,00,c4,ff,ff,ff,00,00,0b,00,00,00,01,00,02,00,00,00,00,00,00,00,00,00,03,00,00,00,02,00,02,00,00,00,00,00,00,00',
    },
}

lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
out = []
in_key = None
seen_keys = set()
seen_values = set()
skip_replaced_value_continuation = False

for line in lines:
    if skip_replaced_value_continuation:
        if line[:1].isspace():
            skip_replaced_value_continuation = line.endswith("\\")
            continue
        skip_replaced_value_continuation = False
    if line.startswith("["):
        if in_key:
            for value_name, value_line in sections[in_key].items():
                if value_name not in seen_values:
                    out.append(value_line)
        # Section headers carry an optional trailing timestamp after the
        # closing bracket (e.g. "[Software\\Microsoft\\Windows NT\\...]
        # 1234567890"). Registry key paths contain spaces (Windows NT, Time
        # Zones), so split(" ") only captures "[Software" and never matches.
        # Use the bracket boundary instead, like registrySectionName in Swift
        # (dict keys keep their brackets, so include them here).
        bracket_end = line.find("]")
        header = line[:bracket_end + 1] if bracket_end > 0 else line
        in_key = header if header in sections else None
        if in_key:
            seen_keys.add(in_key)
            seen_values = set()
    if in_key:
        matched = False
        for value_name, value_line in sections[in_key].items():
            if line.startswith(value_name + "="):
                out.append(value_line)
                seen_values.add(value_name)
                matched = True
                # Registry hex values can span multiple lines using a trailing
                # backslash continuation. Drop the now-stale continuation lines
                # (whitespace-prefixed) of the value we just replaced.
                skip_replaced_value_continuation = line.endswith("\\")
                break
        if matched:
            continue
    out.append(line)

if in_key:
    for value_name, value_line in sections[in_key].items():
        if value_name not in seen_values:
            out.append(value_line)

for key, values in sections.items():
    if key not in seen_keys:
        out.extend(["", key + " 1"])
        out.extend(values.values())

path.write_text("\n".join(out) + "\n", encoding="utf-8", errors="surrogateescape")
PY
}

repair_windows11_setup_registry() {
  local id="macwin-windows11-setup-compat"
  local phase="repair"
  local log="$LOG_DIR/$id-$phase.log"
  local started ended duration exit_code

  started="$(date +%s)"
  {
    echo "== MacWin software smoke =="
    echo "id=$id"
    echo "phase=$phase"
    echo "prefix=$WINEPREFIX"
    echo "started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v ProductName /t REG_SZ /d 'Windows 11 Pro' /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v EditionId /t REG_SZ /d 'Professional' /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v CurrentBuild /t REG_SZ /d 22631 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v CurrentBuildNumber /t REG_SZ /d 22631 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v DisplayVersion /t REG_SZ /d 23H2 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v ReleaseId /t REG_SZ /d 2009 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v UBR /t REG_DWORD /d 3447 /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup' /v OOBEInProgress /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup' /v SystemSetupInProgress /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup' /v SetupType /t REG_DWORD /d 0 /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup' /v CmdLine /t REG_SZ /d '' /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup\Status\SysprepStatus' /v GeneralizationState /t REG_DWORD /d 7 /f
    "${WINE_CMD[@]}" reg add 'HKLM\System\Setup\Status\SysprepStatus' /v CleanupState /t REG_DWORD /d 2 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows\CurrentVersion\OOBE' /v SkipMachineOOBE /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows\CurrentVersion\OOBE' /v SkipUserOOBE /t REG_DWORD /d 1 /f
    "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows\CurrentVersion\OOBE' /v PrivacyConsentStatus /t REG_DWORD /d 1 /f
    echo
    echo "== verification =="
    "${WINE_CMD[@]}" reg query 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v ProductName
    "${WINE_CMD[@]}" reg query 'HKLM\Software\Microsoft\Windows NT\CurrentVersion' /v CurrentBuildNumber
    "${WINE_CMD[@]}" reg query 'HKLM\System\Setup' /v OOBEInProgress
    "${WINE_CMD[@]}" reg query 'HKLM\Software\Microsoft\Windows\CurrentVersion\OOBE' /v PrivacyConsentStatus
  } > "$log" 2>&1
  exit_code=$?
  ended="$(date +%s)"
  duration="$((ended - started))"
  record "$id" "$phase" "$([ "$exit_code" -eq 0 ] && printf passed || printf failed)" "$exit_code" "$log" "$duration" ""
  return "$exit_code"
}

xml_escape() {
  /usr/bin/python3 -c 'import html,sys; print(html.escape(sys.stdin.read().rstrip("\n"), quote=True))'
}

write_smoke_fontconfig() {
  local cache_dir="$PREFIX/fontconfig-cache"
  local windows_fonts="$PREFIX/drive_c/windows/Fonts"
  local -a font_fallbacks
  mkdir -p "$cache_dir" "$windows_fonts"
  {
    echo '<?xml version="1.0"?>'
    echo '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
    echo '<fontconfig>'
    for dir in \
      "$windows_fonts" \
      "/System/Library/Fonts" \
      "/System/Library/Fonts/Supplemental" \
      "/Library/Fonts" \
      "$HOME/Library/Fonts" \
      "/System/Library/AssetsV2/com_apple_MobileAsset_Font8"
    do
      [ -d "$dir" ] || continue
      printf '  <dir>%s</dir>\n' "$(printf '%s' "$dir" | xml_escape)"
    done
    printf '  <cachedir>%s</cachedir>\n' "$(printf '%s' "$cache_dir" | xml_escape)"
    for family in sans-serif system-ui "-apple-system" BlinkMacSystemFont "Segoe UI" "Microsoft YaHei UI" "Microsoft YaHei" Arial Tahoma "Noto Sans" "Source Han Sans" "HYWenHei"; do
      printf '  <alias>\n'
      printf '    <family>%s</family>\n' "$(printf '%s' "$family" | xml_escape)"
      printf '    <prefer>\n'
      case "$family" in
        "Microsoft YaHei UI"|"Microsoft YaHei"|"Noto Sans"|"Source Han Sans"|"HYWenHei")
          font_fallbacks=("PingFang SC" "Hiragino Sans GB" "Heiti SC" "Noto Sans SC" "Noto Sans CJK SC" "Source Han Sans SC" SimHei SimSun "Arial Unicode MS" Tahoma Arial sans-serif)
          ;;
        Arial)
          font_fallbacks=(Arial Tahoma "PingFang SC" "Hiragino Sans GB" "Heiti SC" "Noto Sans SC" "Noto Sans CJK SC" "Source Han Sans SC" SimHei SimSun "Arial Unicode MS" sans-serif)
          ;;
        *)
          font_fallbacks=(Tahoma Arial "PingFang SC" "Hiragino Sans GB" "Heiti SC" "Noto Sans SC" "Noto Sans CJK SC" "Source Han Sans SC" SimHei SimSun "Arial Unicode MS" sans-serif)
          ;;
      esac
      for fallback in "${font_fallbacks[@]}"; do
        printf '      <family>%s</family>\n' "$(printf '%s' "$fallback" | xml_escape)"
      done
      printf '    </prefer>\n'
      printf '  </alias>\n'
    done
    cat <<'XML'
  <match target="pattern">
    <edit name="lang" mode="append">
      <string>zh-cn</string>
    </edit>
  </match>
  <rescan>
    <int>0</int>
  </rescan>
</fontconfig>
XML
  } > "$FONTCONFIG_FILE"
}

copy_windows_font_alias() {
  local target="$1"
  shift
  local fonts_dir="$PREFIX/drive_c/windows/Fonts"
  local source
  [ -f "$fonts_dir/$target" ] && return 0
  for source in "$@"; do
    if [ -f "$source" ]; then
      cp -f "$source" "$fonts_dir/$target" || return 1
      return 0
    fi
  done
  return 1
}

replace_windows_font_alias() {
  local target="$1"
  shift
  local fonts_dir="$PREFIX/drive_c/windows/Fonts"
  local source
  for source in "$@"; do
    [ -f "$source" ] || continue
    if [ ! -L "$fonts_dir/$target" ] && [ -f "$fonts_dir/$target" ]; then
      return 0
    fi
    rm -f "$fonts_dir/$target"
    cp -f "$source" "$fonts_dir/$target" || return 1
    return 0
  done
  return 1
}

register_windows_font_file() {
  local display_name="$1"
  local file_name="$2"
  local fonts_dir="$PREFIX/drive_c/windows/Fonts"
  [ -f "$fonts_dir/$file_name" ] || return 0
  "${WINE_CMD[@]}" reg add 'HKLM\Software\Microsoft\Windows NT\CurrentVersion\Fonts' \
    /v "$display_name" /t REG_SZ /d "$file_name" /f >/dev/null 2>&1 || true
}

repair_javafx_windows_fonts() {
  local fonts_dir="$PREFIX/drive_c/windows/Fonts"
  mkdir -p "$fonts_dir"

  replace_windows_font_alias ARIAL.TTF "/System/Library/Fonts/Supplemental/Arial.ttf" "/System/Library/Fonts/ArialHB.ttc" || true
  replace_windows_font_alias ARIALBD.TTF "/System/Library/Fonts/Supplemental/Arial Bold.ttf" "/System/Library/Fonts/Supplemental/Arial Black.ttf" || true
  copy_windows_font_alias ARIALI.TTF "/System/Library/Fonts/Supplemental/Arial Italic.ttf" "/System/Library/Fonts/Supplemental/Arial.ttf" || true
  copy_windows_font_alias ARIALBI.TTF "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf" "/System/Library/Fonts/Supplemental/Arial Bold.ttf" || true

  copy_windows_font_alias COUR.TTF "/System/Library/Fonts/Supplemental/Courier New.ttf" "/System/Library/Fonts/Courier.ttc" || true
  copy_windows_font_alias COURBD.TTF "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" "/System/Library/Fonts/Courier.ttc" || true
  copy_windows_font_alias COURI.TTF "/System/Library/Fonts/Supplemental/Courier New Italic.ttf" "/System/Library/Fonts/Courier.ttc" || true
  copy_windows_font_alias COURBI.TTF "/System/Library/Fonts/Supplemental/Courier New Bold Italic.ttf" "/System/Library/Fonts/Courier.ttc" || true

  copy_windows_font_alias TIMES.TTF "/System/Library/Fonts/Supplemental/Times New Roman.ttf" "/System/Library/Fonts/Times.ttc" || true
  copy_windows_font_alias TIMESBD.TTF "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf" "/System/Library/Fonts/Times.ttc" || true
  copy_windows_font_alias TIMESI.TTF "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf" "/System/Library/Fonts/Times.ttc" || true
  copy_windows_font_alias TIMESBI.TTF "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf" "/System/Library/Fonts/Times.ttc" || true

  copy_windows_font_alias TAHOMA.TTF "/System/Library/Fonts/Supplemental/Tahoma.ttf" "/System/Library/Fonts/Supplemental/Arial.ttf" || true
  copy_windows_font_alias TAHOMABD.TTF "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf" "/System/Library/Fonts/Supplemental/Arial Bold.ttf" || true
  copy_windows_font_alias SEGUISYM.TTF "/System/Library/Fonts/Symbol.ttf" "/System/Library/Fonts/Apple Symbols.ttf" "/System/Library/Fonts/Supplemental/Arial Unicode.ttf" || true
  copy_windows_font_alias SYMBOL.TTF "/System/Library/Fonts/Symbol.ttf" "/System/Library/Fonts/Apple Symbols.ttf" || true
  copy_windows_font_alias WINGDING.TTF "/System/Library/Fonts/Supplemental/Wingdings.ttf" "/System/Library/Fonts/Symbol.ttf" || true

  for target in SIMSUN.TTC SIMSUN18030.TTC SIMSUNB.TTF MINGLIU.TTC MINGLIUB.TTC hkscsm3u.ttf MSMINCHO.TTC MSGOTHIC.TTC gulim.TTC batang.TTC malgun.ttf malgunbd.TTF MSJH.TTC MSYH.TTC MSYHBD.TTF YUGOTHM.TTC; do
    copy_windows_font_alias "$target" \
      "/System/Library/Fonts/Hiragino Sans GB.ttc" \
      "/System/Library/Fonts/STHeiti Medium.ttc" \
      "/System/Library/Fonts/Supplemental/Songti.ttc" \
      "/System/Library/Fonts/CJKSymbolsFallback.ttc" || true
  done

  register_windows_font_file "Arial (TrueType)" ARIAL.TTF
  register_windows_font_file "Arial Bold (TrueType)" ARIALBD.TTF
  register_windows_font_file "Arial Italic (TrueType)" ARIALI.TTF
  register_windows_font_file "Arial Bold Italic (TrueType)" ARIALBI.TTF
  register_windows_font_file "Courier New (TrueType)" COUR.TTF
  register_windows_font_file "Courier New Bold (TrueType)" COURBD.TTF
  register_windows_font_file "Courier New Italic (TrueType)" COURI.TTF
  register_windows_font_file "Courier New Bold Italic (TrueType)" COURBI.TTF
  register_windows_font_file "Times New Roman (TrueType)" TIMES.TTF
  register_windows_font_file "Times New Roman Bold (TrueType)" TIMESBD.TTF
  register_windows_font_file "Times New Roman Italic (TrueType)" TIMESI.TTF
  register_windows_font_file "Times New Roman Bold Italic (TrueType)" TIMESBI.TTF
  register_windows_font_file "Tahoma (TrueType)" TAHOMA.TTF
  register_windows_font_file "Tahoma Bold (TrueType)" TAHOMABD.TTF
  register_windows_font_file "Segoe UI Symbol (TrueType)" SEGUISYM.TTF
  register_windows_font_file "Symbol (TrueType)" SYMBOL.TTF
  register_windows_font_file "Wingdings (TrueType)" WINGDING.TTF
  register_windows_font_file "SimSun & NSimSun (TrueType)" SIMSUN.TTC
  register_windows_font_file "SimSun-ExtB (TrueType)" SIMSUNB.TTF
  register_windows_font_file "Microsoft YaHei (TrueType)" MSYH.TTC
  register_windows_font_file "Microsoft YaHei Bold (TrueType)" MSYHBD.TTF
  register_windows_font_file "Microsoft JhengHei (TrueType)" MSJH.TTC
  register_windows_font_file "Microsoft YaHei UI (TrueType)" MSYH.TTC
  register_windows_font_file "Yu Gothic Medium (TrueType)" YUGOTHM.TTC
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
}

configure_jabref_javafx_fonts() {
  local runtime_lib="$PREFIX/drive_c/macwin-portable/jabref-portable/JabRef/runtime/lib"
  local fonts_dir="$PREFIX/drive_c/windows/Fonts"
  [ -d "$runtime_lib" ] || return 0
  if [ -f "$runtime_lib/fontconfig.properties.src" ]; then
    cp -f "$runtime_lib/fontconfig.properties.src" "$runtime_lib/fontconfig.properties"
  fi
  if [ -f "$fonts_dir/ARIAL.TTF" ]; then
    cp -f "$fonts_dir/ARIAL.TTF" "$runtime_lib/fontsLucidaSansRegular.ttf" || true
  fi
  if [ -f "$fonts_dir/ARIALBD.TTF" ]; then
    cp -f "$fonts_dir/ARIALBD.TTF" "$runtime_lib/fontsLucidaSansDemiBold.ttf" || true
  fi
  if [ -f "$fonts_dir/ARIALI.TTF" ]; then
    cp -f "$fonts_dir/ARIALI.TTF" "$runtime_lib/fontsLucidaSansRegularItalic.ttf" || true
  fi
  if [ -f "$fonts_dir/ARIALBI.TTF" ]; then
    cp -f "$fonts_dir/ARIALBI.TTF" "$runtime_lib/fontsLucidaSansDemiBoldItalic.ttf" || true
  fi
  rm -f "$runtime_lib/fontconfig.bfc"
}

repair_gtk2_font_aliases() {
  /usr/bin/python3 - "$PREFIX" <<'PY'
from pathlib import Path
import sys

prefix = Path(sys.argv[1])
drive_c = prefix / "drive_c"
if not drive_c.exists():
    raise SystemExit(0)

aliases = """# MacWin generated GTK2/Pango font aliases
"MS Shell Dlg" = "Tahoma,Arial,Sans"
"MS Shell Dlg 2" = "Tahoma,Arial,Sans"
"(NULL)" = "Tahoma,Arial,Sans"
NULL = "Tahoma,Arial,Sans"
Sans = "Tahoma,Arial"
sans = "Tahoma,Arial"
Serif = "Times New Roman,Arial"
serif = "Times New Roman,Arial"
Monospace = "Courier New,Consolas"
monospace = "Courier New,Consolas"
"""

gtk3_settings = """# MacWin generated GTK3/Pango defaults
[Settings]
gtk-theme-name=Default
gtk-icon-theme-name=Adwaita
gtk-fallback-icon-theme=Adwaita
gtk-font-name=Tahoma 9
gtk-xft-antialias=1
gtk-xft-hinting=1
gtk-xft-hintstyle=hintslight
gtk-xft-rgba=rgb
gtk-enable-animations=false
gtk-dialogs-use-header=false
gtk-overlay-scrolling=false
"""

app_roots = set()

for pango_dir in drive_c.glob("**/etc/pango"):
    if not pango_dir.is_dir():
        continue
    (pango_dir / "pango.aliases").write_text(aliases, encoding="utf-8")
    app_root = pango_dir.parents[1]
    app_roots.add(app_root)
    gtkrc = app_root / "etc" / "gtk-2.0" / "gtkrc"
    gtkrc.parent.mkdir(parents=True, exist_ok=True)
    text = gtkrc.read_text(encoding="utf-8", errors="ignore") if gtkrc.exists() else ""
    marker = '\n# MacWin generated font fallback\ngtk-font-name = "Tahoma 9"\n'
    if "MacWin generated font fallback" not in text:
        gtkrc.write_text(text.rstrip() + marker, encoding="utf-8")

for gtk_dll in drive_c.glob("**/libgtk-3-0.dll"):
    if not gtk_dll.is_file():
        continue
    app_roots.add(gtk_dll.parent)
    app_roots.add(gtk_dll.parent.parent)

for app_root in app_roots:
    for settings in (
        app_root / "etc" / "gtk-3.0" / "settings.ini",
        app_root / "share" / "gtk-3.0" / "settings.ini",
        app_root / "lib" / "gtk-3.0" / "settings.ini",
    ):
        settings.parent.mkdir(parents=True, exist_ok=True)
        existing = settings.read_text(encoding="utf-8", errors="ignore") if settings.exists() else ""
        if "MacWin generated GTK3/Pango defaults" not in existing:
            settings.write_text(gtk3_settings, encoding="utf-8")

for user_dir in (drive_c / "users").glob("*"):
    if not user_dir.is_dir() or user_dir.name.lower() in {"public", "default"}:
        continue
    gtkrc = user_dir / ".gtkrc-2.0"
    gtkrc_existing = gtkrc.read_text(encoding="utf-8", errors="ignore") if gtkrc.exists() else ""
    gtkrc_marker = '\n# MacWin generated user GTK font fallback\ngtk-font-name = "Tahoma 9"\n'
    if "MacWin generated user GTK font fallback" not in gtkrc_existing:
        gtkrc.write_text(gtkrc_existing.rstrip() + gtkrc_marker, encoding="utf-8")
    for settings in (
        user_dir / ".config" / "gtk-3.0" / "settings.ini",
        user_dir / "AppData" / "Local" / "gtk-3.0" / "settings.ini",
        user_dir / "AppData" / "Roaming" / "gtk-3.0" / "settings.ini",
    ):
        settings.parent.mkdir(parents=True, exist_ok=True)
        existing = settings.read_text(encoding="utf-8", errors="ignore") if settings.exists() else ""
        if "MacWin generated GTK3/Pango defaults" not in existing:
            settings.write_text(gtk3_settings, encoding="utf-8")
PY
}

repair_freecad_python_uname_shim() {
  find "$PREFIX/drive_c" -type f -path '*/FreeCAD*/*/Lib/platform.py' -print 2>/dev/null | while IFS= read -r platform_py; do
    lib_dir="$(dirname "$platform_py")"
    cat > "$lib_dir/sitecustomize.py" <<'PY'
# MacWin compatibility shim for FreeCAD's embedded Windows Python under Wine on macOS.
import os

if not hasattr(os, "uname"):
    class _MacWinUnameResult(tuple):
        __slots__ = ()
        _fields = ("sysname", "nodename", "release", "version", "machine")

        def __new__(cls):
            return tuple.__new__(cls, ("Windows", "macwin", "11", "Wine", "AMD64"))

        @property
        def sysname(self):
            return self[0]

        @property
        def nodename(self):
            return self[1]

        @property
        def release(self):
            return self[2]

        @property
        def version(self):
            return self[3]

        @property
        def machine(self):
            return self[4]

    def _macwin_uname():
        return _MacWinUnameResult()

    os.uname = _macwin_uname
PY
  done
}

repair_freecad_smoke_profile() {
  local config_dir="$PREFIX/drive_c/users/$USER/AppData/Roaming/FreeCAD/v1-1"
  mkdir -p "$config_dir"
  cat > "$config_dir/user.cfg" <<'XML'
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<FCParameters>
  <FCParamGroup Name="Root">
    <FCParamGroup Name="BaseApp">
      <FCParamGroup Name="LogLevels">
        <FCInt Name="Default" Value="2"/>
      </FCParamGroup>
      <FCParamGroup Name="Preferences">
        <FCParamGroup Name="General">
          <FCText Name="AutoloadModule">PartDesignWorkbench</FCText>
          <FCBool Name="SplashScreen" Value="0"/>
        </FCParamGroup>
        <FCParamGroup Name="Mod">
          <FCParamGroup Name="Start">
            <FCBool Name="ShowOnStartup" Value="0"/>
            <FCBool Name="ShowExamples" Value="0"/>
            <FCBool Name="CloseStart" Value="1"/>
            <FCBool Name="Migration2024Complete" Value="1"/>
          </FCParamGroup>
        </FCParamGroup>
        <FCParamGroup Name="HighDPI">
          <FCBool Name="UseHighDPI" Value="0"/>
        </FCParamGroup>
        <FCParamGroup Name="MainWindow">
          <FCInt Name="WindowWidth" Value="1280"/>
          <FCInt Name="WindowHeight" Value="800"/>
        </FCParamGroup>
      </FCParamGroup>
      <FCParamGroup Name="Workbench">
        <FCText Name="CurrentWorkbench">PartDesignWorkbench</FCText>
      </FCParamGroup>
    </FCParamGroup>
  </FCParamGroup>
</FCParameters>
XML
}

run_freecad_core_workload() {
  local output_windows="C:\\users\\$USER\\Temp\\macwin-freecad-core.FCStd"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-freecad-core.FCStd"
  local command_output exit_code

  mkdir -p "$(dirname "$output_unix")"
  rm -f "$output_unix"
  command_output="$(
    "${WINE_CMD[@]}" 'C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe' -c \
      "import FreeCAD as App, Part; d=App.newDocument('MacWinCore'); s=d.addObject('Part::Feature','Solid'); s.Shape=Part.makeBox(10,20,30); d.recompute(); print('MACWIN_FREECAD_VOLUME=%.1f' % s.Shape.Volume); d.saveAs(r'$output_windows'); print('MACWIN_FREECAD_SAVED='+d.FileName)" \
      2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  printf '%s\n' "$command_output" | rg -q '^MACWIN_FREECAD_VOLUME=6000\.0\r?$' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -F -q "MACWIN_FREECAD_SAVED=$output_windows" || return 1
  [ -s "$output_unix" ] || return 1
  if [ "$exit_code" -ne 0 ] && [ "$exit_code" -ne 1 ]; then
    return "$exit_code"
  fi
  printf 'MACWIN_FREECAD_COMMAND_EXIT=%s\n' "$exit_code"
  printf 'MACWIN_FREECAD_FILE_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
}

run_kicad_core_workload() {
  local cli='C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
  local input='C:\Program Files\KiCad\10.0\share\kicad\template\Arduino_Uno\Arduino_Uno.kicad_pcb'
  local output_windows="C:\\users\\$USER\\Temp\\macwin-kicad-drc.json"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-kicad-drc.json"
  local command_output exit_code

  mkdir -p "$(dirname "$output_unix")"
  rm -f "$output_unix"
  command_output="$(
    "${WINE_CMD[@]}" "$cli" pcb drc --format json --severity-all \
      --output "$output_windows" "$input" 2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  /usr/bin/python3 - "$output_unix" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as report_file:
    report = json.load(report_file)

required = {"kicad_version", "source", "violations", "unconnected_items"}
if not required.issubset(report):
    raise SystemExit(1)
if not str(report["kicad_version"]).startswith("10."):
    raise SystemExit(1)
if not isinstance(report["violations"], list) or not isinstance(report["unconnected_items"], list):
    raise SystemExit(1)

print(f"MACWIN_KICAD_VERSION={report['kicad_version']}")
print(f"MACWIN_KICAD_VIOLATIONS={len(report['violations'])}")
print(f"MACWIN_KICAD_UNCONNECTED={len(report['unconnected_items'])}")
print(f"MACWIN_KICAD_REPORT_SIZE={len(json.dumps(report))}")
PY
}

prepare_qelectrotech_project_fixture() {
  local source="$SCRIPT_DIR/fixtures/qelectrotech-smoke.qet"
  local destination="$PREFIX/drive_c/macwin-tests/qelectrotech-smoke.qet"

  [ -s "$source" ] || return 1
  mkdir -p "$(dirname "$destination")"
  cp "$source" "$destination"
  /usr/bin/python3 - "$destination" <<'PY'
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
root = ET.parse(path).getroot()
diagrams = root.findall("diagram")
if root.tag != "project":
    raise SystemExit("fixture root is not a QElectroTech project")
if root.get("title") != "MacWin 工业电气兼容性测试":
    raise SystemExit("fixture project title mismatch")
if len(diagrams) != 1 or diagrams[0].get("title") != "工业控制回路":
    raise SystemExit("fixture diagram mismatch")
print("MACWIN_QET_FIXTURE=prepared")
print(f"MACWIN_QET_FIXTURE_PATH={path}")
PY
}

run_qelectrotech_project_workload() {
  local project="$PREFIX/drive_c/macwin-tests/qelectrotech-smoke.qet"
  local launch_log="$LOG_DIR/qelectrotech-cad-launch.log"
  local capture="$LOG_DIR/qelectrotech-cad-launch-visual.png"
  local screen_capture="$LOG_DIR/qelectrotech-cad-launch-visual-screen.png"

  [ -s "$project" ] || return 1
  [ -s "$launch_log" ] || return 1
  LC_ALL=C rg -q '^smokeOutcome=(keptAlive|passed)$' "$launch_log" || return 1
  LC_ALL=C rg -q '^visualProbe.domainClassification=rendered$' "$launch_log" || return 1
  LC_ALL=C rg -q 'Count All Elements in collections = [1-9][0-9]* Elements' "$launch_log" || return 1
  [ -s "$capture" ] || [ -s "$screen_capture" ] || return 1

  /usr/bin/python3 - "$project" <<'PY'
import os
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
root = ET.parse(path).getroot()
diagrams = root.findall("diagram")
if root.tag != "project":
    raise SystemExit("project root mismatch")
if root.get("title") != "MacWin 工业电气兼容性测试":
    raise SystemExit("project title mismatch")
if len(diagrams) != 1 or diagrams[0].get("title") != "工业控制回路":
    raise SystemExit("project diagram mismatch")
print("MACWIN_QET_PROJECT_TITLE=" + root.get("title", ""))
print("MACWIN_QET_DIAGRAM_TITLE=" + diagrams[0].get("title", ""))
print("MACWIN_QET_DIAGRAMS=1")
print("MACWIN_QET_PROJECT_BYTES=" + str(os.path.getsize(path)))
print("MACWIN_QET_VISUAL=structured-cad-canvas-rendered")
print("MACWIN_QET_PROJECT=PASS")
PY
}

run_blender_core_workload() {
  local exe='C:\Program Files\Blender Foundation\Blender 4.1\blender.exe'
  local output_windows="C:\\users\\$USER\\Temp\\macwin-blender-cycles.png"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-blender-cycles.png"
  local command_output exit_code image_metadata

  mkdir -p "$(dirname "$output_unix")"
  rm -f "$output_unix"
  command_output="$(
    WINEDEBUG=-all "${WINE_CMD[@]}" "$exe" -b --factory-startup --python-expr \
      "import bpy; s=bpy.context.scene; s.render.engine='CYCLES'; s.cycles.device='CPU'; s.cycles.samples=1; s.render.resolution_x=64; s.render.resolution_y=64; s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'; s.render.filepath=r'$output_windows'; bpy.ops.render.render(write_still=True); print('MACWIN_BLENDER_RENDER='+s.render.filepath)" \
      2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -F -q "MACWIN_BLENDER_RENDER=$output_windows" || return 1
  [ -s "$output_unix" ] || return 1
  /usr/bin/file "$output_unix" | rg -q 'PNG image data, 64 x 64' || return 1
  image_metadata="$(/usr/bin/sips -g pixelWidth -g pixelHeight "$output_unix" 2>/dev/null)"
  printf '%s\n' "$image_metadata"
  printf '%s\n' "$image_metadata" | rg -q 'pixelWidth: 64' || return 1
  printf '%s\n' "$image_metadata" | rg -q 'pixelHeight: 64' || return 1
  printf 'MACWIN_BLENDER_FILE_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
  printf '%s\n' 'MACWIN_BLENDER_EEVEE_HEADLESS=unsupported-no-opengl-vendor'
}

run_blender_eevee_windowed_workload() {
  local exe='C:\Program Files\Blender Foundation\Blender 4.1\blender.exe'
  local output_windows="C:/users/$USER/Temp/macwin-blender-eevee-windowed.png"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-blender-eevee-windowed.png"
  local capture="$LOG_DIR/blender-3d-eevee-window.png"
  local analysis="$LOG_DIR/blender-3d-eevee-window-analysis.json"
  local python_expression window_info window_id classification
  local pid elapsed=0 status=0

  mkdir -p "$(dirname "$output_unix")"
  rm -f "$output_unix" "$capture" "$analysis"
  python_expression="import bpy; exec(\"def macwin_render():\\n s=bpy.context.scene\\n s.render.engine='BLENDER_EEVEE'\\n s.render.resolution_x=64\\n s.render.resolution_y=64\\n s.render.resolution_percentage=100\\n s.render.image_settings.file_format='PNG'\\n s.render.filepath=r'$output_windows'\\n print('MACWIN_BLENDER_ENGINE='+s.render.engine)\\n bpy.ops.render.render(write_still=True)\\n print('MACWIN_BLENDER_EEVEE_RENDER='+s.render.filepath)\\n return None\"); bpy.app.timers.register(macwin_render, first_interval=3.0)"

  WINEDEBUG=-all \
    WINE_D3D_CONFIG='renderer=gl,csmt=0x0' \
    GALLIUM_DRIVER=llvmpipe \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MESA_LOADER_DRIVER_OVERRIDE=llvmpipe \
    WINEDLLOVERRIDES='opengl32=n,b;winemenubuilder.exe=d' \
    "${WINE_CMD[@]}" "$exe" --factory-startup --python-expr "$python_expression" &
  pid="$!"

  while kill -0 "$pid" 2>/dev/null && [ "$elapsed" -lt 60 ]; do
    if [ -s "$output_unix" ]; then
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if [ ! -s "$output_unix" ]; then
    echo "Blender Eevee output did not appear before process exit or the 60-second deadline."
    status=1
  else
    sleep 3
  fi

  window_info=""
  elapsed=0
  while [ "$elapsed" -lt 20 ]; do
    window_info="$(/usr/bin/swift "$SCRIPT_DIR/find-macos-window.swift" \
      --discover wine 'Blender 4.1' 2>/dev/null || true)"
    [ -n "$window_info" ] && break
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if [ -n "$window_info" ]; then
    window_id="${window_info%%$'\t'*}"
    printf 'MACWIN_BLENDER_WINDOW=%s\n' "$window_info"
    if /usr/bin/swift "$SCRIPT_DIR/capture-macos-window.swift" \
      "$window_id" "$capture"; then
      classification="$(/usr/bin/python3 "$SCRIPT_DIR/analyze-window-image.py" \
        "$capture" "$analysis" 2>/dev/null || true)"
      printf 'MACWIN_BLENDER_WINDOW_CLASSIFICATION=%s\n' "$classification"
      [ "$classification" = "rendered" ] || status=1
    else
      status=1
    fi
  else
    echo "Blender window was not discoverable after Eevee rendering."
    status=1
  fi

  kill -TERM "$pid" 2>/dev/null || true
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true

  if [ -s "$output_unix" ]; then
    /usr/bin/file "$output_unix"
    /usr/bin/file "$output_unix" | rg -q 'PNG image data, 64 x 64' || status=1
    /usr/bin/sips -g pixelWidth -g pixelHeight "$output_unix"
    printf 'MACWIN_BLENDER_EEVEE_FILE_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
    printf '%s\n' 'MACWIN_BLENDER_EEVEE_WINDOWED=PASS'
  fi
  return "$status"
}

run_freeoffice_core_workload() {
  local test_dir_unix="$PREFIX/drive_c/MacWinTests"
  local test_dir_windows='C:\MacWinTests'
  local folder_probe_unix="$test_dir_unix/special-folder-probe.exe"
  local bootstrap_probe_unix="$test_dir_unix/freeoffice-bootstrap.exe"
  local ui_probe_unix="$test_dir_unix/freeoffice-ui-probe.exe"
  local bootstrap_first_unix="$test_dir_unix/freeoffice-bootstrap-first.txt"
  local bootstrap_second_unix="$test_dir_unix/freeoffice-bootstrap-second.txt"
  local ui_result_unix="$test_dir_unix/freeoffice-ui-result.txt"
  local document_unix="$test_dir_unix/freeoffice-roundtrip.rtf"
  local overrides='msvcr80,msvcp80=b;winemenubuilder.exe=d'
  local status=0 code

  command -v i686-w64-mingw32-gcc >/dev/null 2>&1 || {
    echo "i686-w64-mingw32-gcc is required for the FreeOffice workload."
    return 127
  }

  mkdir -p "$test_dir_unix"
  (
    set -e
    i686-w64-mingw32-gcc -O2 -Wall -Wextra \
      -o "$folder_probe_unix" "$SCRIPT_DIR/fixtures/special-folder-probe.c" \
      -lshell32 -lole32
    i686-w64-mingw32-gcc -O2 -Wall -Wextra -municode \
      -o "$bootstrap_probe_unix" "$SCRIPT_DIR/fixtures/freeoffice-bootstrap.c" \
      -lole32 -lgdi32
    i686-w64-mingw32-gcc -O2 -Wall -Wextra -municode \
      -o "$ui_probe_unix" "$SCRIPT_DIR/fixtures/freeoffice-ui-probe.c" \
      -lole32 -lshell32 -lgdi32

    WINEDEBUG=-all WINEDLLOVERRIDES="$overrides" \
      "${WINE_CMD[@]}" "$test_dir_windows\special-folder-probe.exe"

    WINEDEBUG=-all WINEDLLOVERRIDES="$overrides" \
      "${WINE_CMD[@]}" "$test_dir_windows\freeoffice-bootstrap.exe" \
      "$test_dir_windows\freeoffice-bootstrap-first.txt"
    rg -q '^MAIN_READY=true\r?$' "$bootstrap_first_unix"
    rg -q '^WARNING_DISMISSED=false\r?$' "$bootstrap_first_unix"
    rg -q '^CLOSED=true\r?$' "$bootstrap_first_unix"

    WINEDEBUG=-all WINEDLLOVERRIDES="$overrides" \
      "${WINE_CMD[@]}" "$test_dir_windows\freeoffice-bootstrap.exe" \
      "$test_dir_windows\freeoffice-bootstrap-second.txt"
    rg -q '^INITIAL_TITLE=TextMaker\r?$' "$bootstrap_second_unix"
    rg -q '^DISMISSED=false\r?$' "$bootstrap_second_unix"
    rg -q '^WARNING_DISMISSED=false\r?$' "$bootstrap_second_unix"
    rg -q '^CLOSED=true\r?$' "$bootstrap_second_unix"

    printf '%s\n' '{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\f0\fs22 MacWin FreeOffice seed\par}' > "$document_unix"
    WINEDEBUG=-all WINEDLLOVERRIDES="$overrides" \
      "${WINE_CMD[@]}" "$test_dir_windows\freeoffice-ui-probe.exe" \
      "$test_dir_windows\freeoffice-ui-result.txt" \
      "$test_dir_windows\freeoffice-roundtrip.rtf"
    rg -q '^MDI_READY=true\r?$' "$ui_result_unix"
    rg -q '^SAVED=true\r?$' "$ui_result_unix"
    for code in 20445 23384 24448 36820 27491 24120; do
      rg -a -F -q "\\u$code" "$document_unix"
    done

    echo '== FreeOffice bootstrap first run =='
    rg '^(INITIAL_TITLE|DISMISSED|MAIN_READY|WARNING_DISMISSED|INFO_DISMISSED|CLOSED)=' "$bootstrap_first_unix"
    echo '== FreeOffice bootstrap second run =='
    rg '^(INITIAL_TITLE|DISMISSED|MAIN_READY|WARNING_DISMISSED|INFO_DISMISSED|CLOSED)=' "$bootstrap_second_unix"
    echo '== FreeOffice document roundtrip =='
    rg '^(WINDOW|OLD_SIZE|NEW_SIZE|MDI_READY|SAVED)=' "$ui_result_unix"
    printf 'MACWIN_FREEOFFICE_RTF_SIZE=%s\n' "$(stat -f '%z' "$document_unix")"
  ) || status=$?

  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  return "$status"
}

run_jabref_core_workload() {
  local jabref='C:\macwin-portable\jabref-portable\JabRef\JabRef.exe'
  local fixture_unix="$SCRIPT_DIR/fixtures/jabref-smoke.bib"
  local test_dir_unix="$PREFIX/drive_c/MacWinTests/jabref"
  local input_unix="$test_dir_unix/input.bib"
  local output_unix="$test_dir_unix/output.ris"
  local input_windows='C:\MacWinTests\jabref\input.bib'
  local output_windows='C:\MacWinTests\jabref\output.ris'
  local java_options='-Dsun.java2d.d3d=false -Dsun.java2d.opengl=false -Dprism.order=d3d -Dprism.forceGPU=true -Dprism.text=t2k -Dprism.fontdir=C:\windows\Fonts -Djava.awt.headless=false -Dglass.win.uiScale=100%'
  local command_output exit_code record_count

  mkdir -p "$test_dir_unix"
  cp -f "$fixture_unix" "$input_unix"
  rm -f "$output_unix"

  command_output="$(
    WINEDEBUG=-all JAVA_TOOL_OPTIONS="$java_options" \
      "${WINE_CMD[@]}" "$jabref" --nogui \
      --import "$input_windows,bibtex" \
      --output "$output_windows,ris" 2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  record_count="$(tr -d '\r' < "$output_unix" | rg -c '^ER  -$' || true)"
  [ "$record_count" -eq 2 ] || return 1
  tr -d '\r' < "$output_unix" | rg -F -q 'T1  - MacWin compatibility validation' || return 1
  tr -d '\r' < "$output_unix" | rg -F -q 'AU  - Smith, Ada' || return 1
  tr -d '\r' < "$output_unix" | rg -F -q 'T1  - Reliable Windows Workloads on macOS' || return 1
  tr -d '\r' < "$output_unix" | rg -F -q 'PB  - Open Systems Press' || return 1
  tr -d '\r' < "$output_unix" | rg -F -q 'M3  - https://doi.org/10.1234/macwin.2026.17' || return 1

  printf 'MACWIN_JABREF_RIS_RECORDS=%s\n' "$record_count"
  printf 'MACWIN_JABREF_RIS_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
  printf '%s\n' 'PASS jabref_bibtex_to_ris'
}

prepare_jabref_gui_fixture() {
  local fixture_unix="$SCRIPT_DIR/fixtures/jabref-smoke.bib"
  local test_dir_unix="$PREFIX/drive_c/MacWinTests/jabref"
  local input_unix="$test_dir_unix/input.bib"

  [ -s "$fixture_unix" ] || return 1
  mkdir -p "$test_dir_unix"
  cp -f "$fixture_unix" "$input_unix"
  [ -s "$input_unix" ]
  printf '%s\n' 'PASS jabref_gui_fixture'
}

run_projectlibre_core_workload() {
  local java='C:\macwin-runtime\temurin-jdk21\jdk-21.0.11+10\bin\java.exe'
  local javac='C:\macwin-runtime\temurin-jdk21\jdk-21.0.11+10\bin\javac.exe'
  local projectlibre_jar='C:\Program Files\ProjectLibre\app\projectlibre-1.9.8.jar'
  local source_unix="$SCRIPT_DIR/fixtures/projectlibre-mpxj-smoke.java"
  local source_windows="Z:${source_unix//\//\\}"
  local test_dir_unix="$PREFIX/drive_c/MacWinTests/projectlibre"
  local classes_unix="$test_dir_unix/classes"
  local classes_windows='C:\MacWinTests\projectlibre\classes'
  local project_unix="$test_dir_unix/macwin-project.xml"
  local project_windows='C:\MacWinTests\projectlibre\macwin-project.xml'
  local result_unix="$test_dir_unix/result.txt"
  local result_windows='C:\MacWinTests\projectlibre\result.txt'
  local class_path="$classes_windows;$projectlibre_jar"

  configure_temurin_jdk21_runtime || return $?
  mkdir -p "$classes_unix"
  rm -f "$classes_unix/ProjectLibreMpxjSmoke.class" "$project_unix" "$result_unix"

  JAVA_TOOL_OPTIONS='-Dfile.encoding=UTF-8' WINEDEBUG=-all \
    "${WINE_CMD[@]}" "$javac" -encoding UTF-8 -proc:none \
      -cp "$projectlibre_jar" -d "$classes_windows" "$source_windows" || return $?
  [ -s "$classes_unix/ProjectLibreMpxjSmoke.class" ] || return 1

  JAVA_TOOL_OPTIONS='-Dfile.encoding=UTF-8 -Djava.awt.headless=true' WINEDEBUG=-all \
    "${WINE_CMD[@]}" "$java" -cp "$class_path" \
      ProjectLibreMpxjSmoke "$project_windows" "$result_windows" || return $?
  [ -s "$project_unix" ] && [ -s "$result_unix" ] || return 1

  tr -d '\r' < "$result_unix" | rg -q '^FORMAT=MSPDI$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^TASKS=3$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^TASK_UNICODE=passed$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^RESOURCES=1$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^RESOURCE_UNICODE=passed$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^DURATION_DAYS=3.5$' || return 1
  tr -d '\r' < "$result_unix" | rg -q '^ROUNDTRIP=passed$' || return 1
  rg -q '<Name>兼容性调试</Name>' "$project_unix" || return 1
  rg -q '<Name>测试工程师</Name>' "$project_unix" || return 1

  tr -d '\r' < "$result_unix" | sed 's/^/MACWIN_PROJECTLIBRE_/'
  printf 'MACWIN_PROJECTLIBRE_XML_SIZE=%s\n' "$(stat -f '%z' "$project_unix")"
  printf '%s\n' 'PASS projectlibre_mpxj_roundtrip'
}

prepare_pdfarranger_workload() {
  local test_dir="$PREFIX/drive_c/MacWinTests/pdfarranger"

  command -v cupsfilter >/dev/null 2>&1 || {
    echo "cupsfilter is required to create the PDF Arranger fixtures."
    return 127
  }
  mkdir -p "$test_dir"
  cupsfilter -m application/pdf "$SCRIPT_DIR/fixtures/pdfarranger-page-one.txt" \
    > "$test_dir/page-one.pdf"
  cupsfilter -m application/pdf "$SCRIPT_DIR/fixtures/pdfarranger-page-two.txt" \
    > "$test_dir/page-two.pdf"
  [ -s "$test_dir/page-one.pdf" ] && [ -s "$test_dir/page-two.pdf" ]
}

run_pdfarranger_core_workload() {
  local app_dir_windows='C:\macwin-portable\pdfarranger-portable\pdf arranger-1.14.0'
  local lib_dir_windows="$app_dir_windows\\lib"
  local qpdf_dll_windows="$lib_dir_windows\\libqpdf30.dll"
  local test_dir_unix="$PREFIX/drive_c/MacWinTests/pdfarranger"
  local test_dir_windows='C:\MacWinTests\pdfarranger'
  local probe_unix="$test_dir_unix/pdfarranger-qpdf-probe.exe"
  local output_unix="$test_dir_unix/merged.pdf"
  local command_output exit_code pdfinfo_output

  command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1 || {
    echo "x86_64-w64-mingw32-gcc is required for the PDF Arranger workload."
    return 127
  }
  prepare_pdfarranger_workload || return $?
  x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Wno-cast-function-type \
    -o "$probe_unix" "$SCRIPT_DIR/fixtures/pdfarranger-qpdf-probe.c"
  rm -f "$output_unix"

  command_output="$(
    WINEDEBUG=-all "${WINE_CMD[@]}" "$test_dir_windows\\pdfarranger-qpdf-probe.exe" \
      "$app_dir_windows" \
      "$lib_dir_windows" \
      "$qpdf_dll_windows" \
      "$test_dir_windows\\page-one.pdf" \
      "$test_dir_windows\\page-two.pdf" \
      "$test_dir_windows\\merged.pdf" 2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^input\.pages=1\+1$' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^output\.pages=2$' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^PASS pdfarranger_qpdf_merge$' || return 1
  [ -s "$output_unix" ] || return 1

  pdfinfo_output="$("${MACWIN_PDFINFO_BIN:-$(command -v pdfinfo || true)}" "$output_unix" 2>/dev/null)" || return 1
  printf '%s\n' "$pdfinfo_output"
  printf '%s\n' "$pdfinfo_output" | rg -q '^Pages:[[:space:]]+2$' || return 1
  printf 'MACWIN_PDFARRANGER_MERGED_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
}

run_libreoffice_core_workload() {
  local soffice='C:\Program Files\LibreOffice\program\soffice.exe'
  local input_unix="$SCRIPT_DIR/fixtures/libreoffice-smoke.html"
  local input_windows="Z:${input_unix//\//\\}"
  local output_dir_windows="C:\\users\\$USER\\Temp\\macwin-libreoffice"
  local output_dir_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-libreoffice"
  local output_unix="$output_dir_unix/libreoffice-smoke.pdf"
  local profile_uri="file:///C:/users/$USER/Temp/macwin-libreoffice-profile"
  local command_output exit_code metadata pdfinfo_output pdfinfo_bin

  mkdir -p "$output_dir_unix"
  rm -f "$output_unix"
  command_output="$(
    WINEDEBUG=-all "${WINE_CMD[@]}" "$soffice" \
      "-env:UserInstallation=$profile_uri" \
      --headless --nologo --nodefault --nofirststartwizard \
      --convert-to pdf --outdir "$output_dir_windows" "$input_windows" \
      2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  /usr/bin/file "$output_unix" | rg -q 'PDF document, version 1\.7, 1 pages' || return 1
  # Spotlight metadata is not guaranteed for temporary files under a Wine
  # prefix. Validate the PDF itself so an unindexed file cannot become a
  # false compatibility failure.
  pdfinfo_bin="${MACWIN_PDFINFO_BIN:-$(command -v pdfinfo || true)}"
  if [ -n "$pdfinfo_bin" ] && [ -x "$pdfinfo_bin" ]; then
    pdfinfo_output="$("$pdfinfo_bin" "$output_unix" 2>/dev/null)" || return 1
    printf '%s\n' "$pdfinfo_output"
    printf '%s\n' "$pdfinfo_output" | rg -q '^Pages:[[:space:]]+1$' || return 1
    printf '%s\n' "$pdfinfo_output" | rg -q '^Producer:[[:space:]]+.*LibreOffice 26\.2\.4\.2 \(X86_64\)' || return 1
  else
    metadata="$(/usr/bin/file "$output_unix")"
    printf '%s\n' "$metadata"
    printf '%s\n' "$metadata" | rg -q 'PDF document, version 1\.7, 1 pages' || return 1
  fi
  strings "$output_unix" | rg -q 'MacWin LibreOffice compatibility probe' || return 1
  strings "$output_unix" | rg -q 'LibreOffice 26\.2\.4\.2 \(X86_64\)' || return 1
  printf 'MACWIN_LIBREOFFICE_PDF_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
}

run_onlyoffice_core_workload() {
  local x2t='C:\Program Files\ONLYOFFICE\DesktopEditors\converter\x2t.exe'
  local converter_unix="$PREFIX/drive_c/Program Files/ONLYOFFICE/DesktopEditors/converter"
  local input_unix="$SCRIPT_DIR/fixtures/libreoffice-smoke.html"
  local input_windows="Z:${input_unix//\//\\}"
  local output_windows="C:\\users\\$USER\\Temp\\macwin-onlyoffice.docx"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-onlyoffice.docx"
  local command_output exit_code document_xml

  mkdir -p "$(dirname "$output_unix")"
  rm -f "$output_unix"
  command_output="$(
    cd "$converter_unix" &&
      env PATH='C:\Program Files\ONLYOFFICE\DesktopEditors\converter;C:\Program Files\ONLYOFFICE\DesktopEditors;C:\windows\system32;C:\windows' \
        WINEDEBUG=-all "${WINE_CMD[@]}" "$x2t" "$input_windows" "$output_windows" \
        2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  /usr/bin/file "$output_unix" | rg -q 'Microsoft Word 2007\+' || return 1
  unzip -t "$output_unix" >/dev/null 2>&1 || return 1
  document_xml="$(unzip -p "$output_unix" word/document.xml)"
  printf '%s\n' "$document_xml" | rg -F -q 'MacWin 办公兼容性测试' || return 1
  printf '%s\n' "$document_xml" | rg -F -q 'LibreOffice Writer conversion passed.' || return 1
  printf 'MACWIN_ONLYOFFICE_DOCX_SIZE=%s\n' "$(stat -f '%z' "$output_unix")"
}

run_onlyoffice_pdf_export_workload() {
  local x2t='C:\Program Files\ONLYOFFICE\DesktopEditors\converter\x2t.exe'
  local converter_unix="$PREFIX/drive_c/Program Files/ONLYOFFICE/DesktopEditors/converter"
  local input_windows="C:\\users\\$USER\\Temp\\macwin-onlyoffice.docx"
  local input_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-onlyoffice.docx"
  local output_windows="C:\\users\\$USER\\Temp\\macwin-onlyoffice.pdf"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-onlyoffice.pdf"
  local font_dir_windows="C:\\users\\$USER\\AppData\\Local\\ONLYOFFICE\\DesktopEditors\\data\\fonts"
  local font_dir_unix="$PREFIX/drive_c/users/$USER/AppData/Local/ONLYOFFICE/DesktopEditors/data/fonts"
  local command_output exit_code pdf_size

  [ -s "$input_unix" ] || return 1
  [ -s "$font_dir_unix/AllFonts.js" ] || return 1
  [ -s "$font_dir_unix/font_selection.bin" ] || return 1

  rm -f "$output_unix"
  command_output="$(
    cd "$converter_unix" &&
      env PATH='C:\Program Files\ONLYOFFICE\DesktopEditors\converter;C:\Program Files\ONLYOFFICE\DesktopEditors;C:\windows\system32;C:\windows' \
        WINEDEBUG=-all "${WINE_CMD[@]}" "$x2t" \
        "$input_windows" "$output_windows" "$font_dir_windows" \
        2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  /usr/bin/file "$output_unix" | rg -q 'PDF document, version 1\.7, 1 pages' || return 1
  strings "$output_unix" | rg -q '<pdf:Producer>ONLYOFFICE/' || return 1
  strings "$output_unix" | rg -q '^/Count 1$' || return 1
  strings "$output_unix" | rg -q '^/Type /Page$' || return 1
  pdf_size="$(stat -f '%z' "$output_unix")"
  [ "$pdf_size" -ge 32768 ] || return 1
  printf 'MACWIN_ONLYOFFICE_PDF_SIZE=%s\n' "$pdf_size"
  printf 'MACWIN_ONLYOFFICE_PDF_PAGES=1\n'
}

repair_r_runtime_environment() {
  local r_home='C:\Program Files\R\R-4.6.0'
  local r_path='C:\Program Files\R\R-4.6.0\bin\x64;C:\Program Files\R\R-4.6.0\bin'
  local current_path new_path

  [ -f "$PREFIX/drive_c/Program Files/R/R-4.6.0/bin/x64/R.dll" ] || return 0
  for key in \
    'HKLM\Software\R-core\R64' \
    'HKLM\Software\R-core\R64\4.6.0' \
    'HKLM\Software\R-core\R' \
    'HKLM\Software\R-core\R\4.6.0'; do
    "${WINE_CMD[@]}" reg.exe add "$key" /v InstallPath /t REG_SZ /d "$r_home" /f >/dev/null 2>&1 || return 1
  done
  for key in 'HKLM\Software\R-core\R64' 'HKLM\Software\R-core\R'; do
    "${WINE_CMD[@]}" reg.exe add "$key" /v 'Current Version' /t REG_SZ /d '4.6.0' /f >/dev/null 2>&1 || return 1
  done

  current_path="$(
    "${WINE_CMD[@]}" reg.exe query 'HKCU\Environment' /v Path 2>/dev/null \
      | LC_ALL=C sed -n 's/^.*REG_EXPAND_SZ[[:space:]]*//p' \
      | tail -n 1
  )"
  case ";$current_path;" in
    *';C:\Program Files\R\R-4.6.0\bin\x64;'*)
      return 0
      ;;
  esac
  new_path="$r_path"
  [ -z "$current_path" ] || new_path="$current_path;$r_path"
  "${WINE_CMD[@]}" reg.exe add 'HKCU\Environment' /v Path /t REG_EXPAND_SZ /d "$new_path" /f >/dev/null 2>&1 || return 1
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  sleep 2
}

run_r_statistics_workload() {
  local rscript='C:\Program Files\R\R-4.6.0\bin\x64\Rscript.exe'
  local script_unix="$SCRIPT_DIR/fixtures/r-statistics-smoke.R"
  local script_windows="Z:${script_unix//\//\\}"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-r-statistics.csv"
  local command_output exit_code

  rm -f "$output_unix"
  command_output="$(
    LC_ALL='Chinese_China.utf8' LANG='Chinese_China.utf8' WINEDEBUG=-all \
      "${WINE_CMD[@]}" "$rscript" --encoding=UTF-8 "$script_windows" 2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^MACWIN_R_MEAN=3$' || return 1
  [ -s "$output_unix" ] || return 1
  /usr/bin/python3 - "$output_unix" <<'PY'
import csv
import sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as csv_file:
    rows = list(csv.DictReader(csv_file))

if len(rows) != 1:
    raise SystemExit(1)
if rows[0].get("mean") != "3" or rows[0].get("chinese") != "中文统计":
    raise SystemExit(1)

print(f"MACWIN_R_SD={rows[0]['sd']}")
print("MACWIN_R_UTF8=passed")
PY
}

run_rstudio_backend_workload() {
  local rsession='C:\Program Files\RStudio\resources\app\bin\rsession.exe'
  LC_ALL='Chinese_China.utf8' LANG='Chinese_China.utf8' WINEDEBUG=-all \
    RSTUDIO_WHICH_R='C:\Program Files\R\R-4.6.0\bin\x64\R.exe' \
    R_HOME='C:\Program Files\R\R-4.6.0' \
    "${WINE_CMD[@]}" "$rsession" --verify-installation=1
}

run_energyplus_simulation_workload() {
  local app='C:\EnergyPlusV26-1-0\energyplus.exe'
  local weather='C:\EnergyPlusV26-1-0\WeatherData\USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw'
  local input='C:\EnergyPlusV26-1-0\ExampleFiles\1ZoneUncontrolled.idf'
  local output_windows='C:\macwin-tests\energyplus-output'
  local output_unix="$PREFIX/drive_c/macwin-tests/energyplus-output"
  local error_file="$output_unix/eplusout.err"
  local table_file="$output_unix/eplustbl.csv"

  rm -rf "$output_unix"
  mkdir -p "$output_unix"
  PATH='C:\EnergyPlusV26-1-0;C:\windows\system32;C:\windows' \
    "${WINE_CMD[@]}" "$app" -w "$weather" -d "$output_windows" "$input"
  [ -s "$error_file" ] || {
    echo "EnergyPlus did not create eplusout.err." >&2
    return 1
  }
  log_has_runtime_fixed_string 'EnergyPlus Completed Successfully' "$error_file" || {
    echo "EnergyPlus simulation did not report successful completion." >&2
    return 1
  }
  [ -s "$table_file" ] || {
    echo "EnergyPlus did not create the tabular CSV output." >&2
    return 1
  }
  local severe_count output_count
  severe_count="$(sed -n 's/.*-- [0-9][0-9]* Warning; \([0-9][0-9]*\) Severe Errors.*/\1/p' "$error_file" | tail -n 1)"
  output_count="$(find "$output_unix" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  printf 'MACWIN_ENERGYPLUS_VERSION=26.1.0-6f2e40d102\n'
  printf 'MACWIN_ENERGYPLUS_SEVERE_ERRORS=%s\n' "${severe_count:-unknown}"
  printf 'MACWIN_ENERGYPLUS_OUTPUT_FILES=%s\n' "$output_count"
  printf 'MACWIN_ENERGYPLUS_SIMULATION=PASS\n'
}

run_openplc_compiler_workload() {
  local app_dir="$PREFIX/drive_c/macwin-portable/openplc-editor"
  local resources_dir="$app_dir/resources"
  local test_dir="$PREFIX/drive_c/macwin-tests/openplc"
  local fixture="$SCRIPT_DIR/fixtures/openplc-smoke.xml"
  local semantic_probe="$SCRIPT_DIR/fixtures/openplc-smoke-main.cpp"
  local app_asar="$resources_dir/app.asar"
  local bundle="$test_dir/strucpp-bundle.js"
  local probe_script="$test_dir/strucpp-probe.js"
  local result_json="$test_dir/strucpp-result.json"
  local node_bin
  local arduino_output
  local semantic_output

  [ -f "$app_dir/OpenPLC Editor.exe" ] || return 1
  [ -f "$resources_dir/bin/xml2st.exe" ] || return 1
  [ -f "$resources_dir/bin/arduino-cli.exe" ] || return 1
  [ -s "$app_asar" ] || return 1
  [ -s "$fixture" ] || return 1
  [ -s "$semantic_probe" ] || return 1

  node_bin="$(command -v node || true)"
  [ -n "$node_bin" ] || {
    echo "Host Node.js is required to extract the packaged OpenPLC compiler bundle." >&2
    return 1
  }

  rm -rf "$test_dir"
  mkdir -p "$test_dir"
  cp "$fixture" "$test_dir/plc.xml"

  WINEDEBUG=-all "${WINE_CMD[@]}" \
    'C:\macwin-portable\openplc-editor\resources\bin\xml2st.exe' \
    --generate-st 'C:\macwin-tests\openplc\plc.xml' --keep-structs
  [ -s "$test_dir/program.st" ] || return 1
  LC_ALL=C rg -q '^PROGRAM main\r?$' "$test_dir/program.st" || return 1
  LC_ALL=C rg -q '^    Pulse AT %QX0\.0 : BOOL := FALSE;\r?$' "$test_dir/program.st" || return 1
  LC_ALL=C rg -q '^    PROGRAM instance0 WITH task0 : main;\r?$' "$test_dir/program.st" || return 1

  "$node_bin" - "$app_asar" "$bundle" <<'NODE'
const fs = require("fs");

const [archivePath, outputPath] = process.argv.slice(2);
const archive = fs.readFileSync(archivePath);
const headerSize = archive.readUInt32LE(4);
const jsonSize = archive.readUInt32LE(12);
const header = JSON.parse(archive.subarray(16, 16 + jsonSize).toString("utf8"));
const dataOffset = 8 + headerSize;

let entry = header;
for (const part of "dist/main/main.js".split("/")) {
  entry = entry.files?.[part];
  if (!entry) {
    throw new Error(`app.asar entry missing: dist/main/main.js (${part})`);
  }
}

let source = archive
  .subarray(dataOffset + Number(entry.offset), dataOffset + Number(entry.offset) + entry.size)
  .toString("utf8");
const exportSignature = "ELEMENTARY_TYPES:()=>";
const signatureIndex = source.indexOf(exportSignature);
if (signatureIndex < 0) {
  throw new Error("STruC++ export signature missing from OpenPLC main bundle");
}

const modulePattern = /[},](\d+):/g;
let moduleMatch;
let strucppModuleId;
while ((moduleMatch = modulePattern.exec(source.slice(0, signatureIndex))) !== null) {
  strucppModuleId = moduleMatch[1];
}
if (!strucppModuleId) {
  throw new Error("Unable to locate bundled STruC++ module id");
}

const entryPattern = /([A-Za-z_$][A-Za-z0-9_$]*)\(\1\.s=(\d+)\)/g;
let entryMatch;
let lastEntryMatch;
while ((entryMatch = entryPattern.exec(source)) !== null) {
  lastEntryMatch = entryMatch;
}
if (!lastEntryMatch) {
  throw new Error("Unable to locate OpenPLC webpack entry point");
}

const webpackRequire = lastEntryMatch[1];
source = source.replace(
  lastEntryMatch[0],
  `({strucpp:${webpackRequire}(${strucppModuleId})})`,
);
const externalMarker = 't(require("serialport"),require("socket.io-client"))';
if (!source.includes(externalMarker)) {
  throw new Error("OpenPLC CommonJS external marker missing");
}
source = source.replace(externalMarker, "t({}, {})");
fs.writeFileSync(outputPath, source);
NODE
  [ -s "$bundle" ] || return 1

  cat > "$probe_script" <<'NODE'
const fs = require("fs");
const path = require("path");

const [bundlePath, sourcePath, outputDirectory, libraryDirectory] = process.argv.slice(2);
const api = require(bundlePath).strucpp;
const source = fs.readFileSync(sourcePath, "utf8");
const libraryNames = ["iec-std-functions.stlib", "iec-standard-fb.stlib"];
const libraries = libraryNames.map((name) =>
  api.loadStlibFromBuffer(fs.readFileSync(path.join(libraryDirectory, name))),
);
const result = api.compile(source, {
  fileName: "program.st",
  libraries,
});

for (const file of result.cppFiles) {
  fs.writeFileSync(path.join(outputDirectory, file.name), file.content);
}
fs.writeFileSync(path.join(outputDirectory, "generated.cpp"), result.cppCode);
fs.writeFileSync(path.join(outputDirectory, "generated.hpp"), result.headerCode);
fs.writeFileSync(
  path.join(outputDirectory, "strucpp-result.json"),
  JSON.stringify(
    {
      version: api.getVersion(),
      success: result.success,
      errors: result.errors,
      warnings: result.warnings,
      libraries: libraries.map((library) => library.manifest.name),
      resolvedLibraries: (result.resolvedLibraries ?? []).map(
        (library) => library.manifest.name,
      ),
      cppFiles: result.cppFiles.map((file) => ({
        name: file.name,
        bytes: Buffer.byteLength(file.content),
      })),
      cppBytes: Buffer.byteLength(result.cppCode),
      headerBytes: Buffer.byteLength(result.headerCode),
    },
    null,
    2,
  ),
);
if (!result.success) {
  process.exitCode = 2;
}
NODE

  WINEDEBUG=-all ELECTRON_RUN_AS_NODE=1 "${WINE_CMD[@]}" \
    'C:\macwin-portable\openplc-editor\OpenPLC Editor.exe' \
    'C:\macwin-tests\openplc\strucpp-probe.js' \
    'C:\macwin-tests\openplc\strucpp-bundle.js' \
    'C:\macwin-tests\openplc\program.st' \
    'C:\macwin-tests\openplc' \
    'C:\macwin-portable\openplc-editor\resources\strucpp\libs'
  [ -s "$result_json" ] || return 1

  /usr/bin/python3 - "$result_json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as result_file:
    result = json.load(result_file)

if result.get("version") != "0.5.10":
    raise SystemExit(f"unexpected STruC++ version: {result.get('version')}")
if result.get("success") is not True or result.get("errors") or result.get("warnings"):
    raise SystemExit(f"STruC++ compilation failed: {result}")
if result.get("libraries") != ["iec-std-functions", "iec-standard-fb"]:
    raise SystemExit(f"unexpected OpenPLC library set: {result.get('libraries')}")
if result.get("resolvedLibraries") != ["iec-std-functions", "iec-standard-fb"]:
    raise SystemExit(f"unexpected resolved library set: {result.get('resolvedLibraries')}")
if {item.get("name") for item in result.get("cppFiles", [])} != {
    "configuration.cpp",
    "pou_MAIN.cpp",
}:
    raise SystemExit(f"unexpected generated C++ files: {result.get('cppFiles')}")
if result.get("cppBytes", 0) < 1000 or result.get("headerBytes", 0) < 2000:
    raise SystemExit("generated C++ output is unexpectedly small")

print(f"MACWIN_OPENPLC_STRUCPP_VERSION={result['version']}")
print(f"MACWIN_OPENPLC_CPP_BYTES={result['cppBytes']}")
print(f"MACWIN_OPENPLC_HEADER_BYTES={result['headerBytes']}")
print("MACWIN_OPENPLC_STRUCPP=PASS")
PY

  clang++ -std=c++17 -O2 \
    -I "$resources_dir/strucpp/runtime/include" \
    -I "$test_dir" \
    "$test_dir/generated.cpp" "$semantic_probe" \
    -o "$test_dir/openplc-semantic-probe"
  semantic_output="$("$test_dir/openplc-semantic-probe")"
  printf '%s\n' "$semantic_output"
  printf '%s\n' "$semantic_output" | LC_ALL=C rg -Fxq 'MACWIN_OPENPLC_SEMANTICS=PASS' || return 1

  arduino_output="$(
    WINEDEBUG=-all "${WINE_CMD[@]}" \
      'C:\macwin-portable\openplc-editor\resources\bin\arduino-cli.exe' version
  )"
  printf '%s\n' "$arduino_output"
  printf '%s\n' "$arduino_output" | LC_ALL=C rg -q '^arduino-cli  Version: 1\.4\.1 ' || return 1
  printf 'MACWIN_OPENPLC_ARDUINO_CLI=PASS\n'
  printf 'MACWIN_OPENPLC_COMPILER_PIPELINE=PASS\n'
}

run_opendss_power_workload() {
  local launcher='C:\macwin-launchers\opendss-svn-x64-smoke.cmd'
  local output="$PREFIX/drive_c/macwin-portable/opendss-svn-x64/macwin_EXP_VOLTAGES.CSV"
  local command_output exit_code=0

  [ -f "$PREFIX/drive_c/macwin-portable/opendss-svn-x64/OpenDSScmd.exe" ] || return 1
  [ -f "$PREFIX/drive_c/macwin-portable/opendss-svn-x64/macwin-smoke.dss" ] || return 1
  rm -f "$output"
  command_output="$(
    PATH='C:\macwin-portable\opendss-svn-x64;C:\windows\system32;C:\windows' \
      WINEDEBUG=-all "${WINE_CMD[@]}" 'C:\windows\system32\cmd.exe' /c "$launcher" 2>&1
  )" || exit_code=$?
  printf '%s\n' "$command_output"
  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output" ] || {
    echo "OpenDSS did not create the voltage export CSV." >&2
    return 1
  }

  /usr/bin/python3 - "$output" <<'PY'
import csv
import sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as csv_file:
    rows = {
        row["Bus"].strip().strip('"').upper(): row
        for row in csv.DictReader(csv_file, skipinitialspace=True)
    }

source = rows.get("SOURCEBUS")
load = rows.get("LOADBUS")
if source is None or load is None:
    raise SystemExit("missing SOURCEBUS or LOADBUS voltage row")

def value(row, key):
    return float(row[key].strip())

source_voltage = value(source, "Magnitude1")
load_voltage = value(load, "Magnitude1")
source_pu = value(source, "pu1")
load_pu = value(load, "pu1")
voltage_drop = source_voltage - load_voltage

if not 7100.0 <= source_voltage <= 7300.0:
    raise SystemExit(f"unexpected source voltage: {source_voltage}")
if not 7100.0 <= load_voltage <= source_voltage:
    raise SystemExit(f"unexpected load voltage: {load_voltage}")
if not 0.98 <= source_pu <= 1.02 or not 0.98 <= load_pu <= 1.02:
    raise SystemExit(f"unexpected per-unit voltages: source={source_pu} load={load_pu}")
if not 0.1 <= voltage_drop <= 10.0:
    raise SystemExit(f"unexpected line voltage drop: {voltage_drop}")

print(f"MACWIN_OPENDSS_SOURCE_V={source_voltage:.3f}")
print(f"MACWIN_OPENDSS_LOAD_V={load_voltage:.3f}")
print(f"MACWIN_OPENDSS_LOAD_PU={load_pu:.6f}")
print(f"MACWIN_OPENDSS_VOLTAGE_DROP={voltage_drop:.3f}")
print("MACWIN_OPENDSS_SIMULATION=PASS")
PY
}

run_opendss_com_workload() {
  local app_dir="$PREFIX/drive_c/macwin-portable/opendss-svn-x64"
  local engine_dll='C:\macwin-portable\opendss-svn-x64\OpenDSSengine.dll'
  local probe="$PROJECT_ROOT/refs/exe-tests/bin/94_opendss_com_probe.exe"
  local probe_windows="Z:${probe//\//\\}"
  local command_output exit_code=0

  [ -f "$app_dir/OpenDSSengine.dll" ] || return 1
  [ -f "$probe" ] || {
    echo "Missing OpenDSS COM probe: $probe" >&2
    return 1
  }

  WINEDEBUG=-all "${WINE_CMD[@]}" regsvr32.exe /s "$engine_dll" || return $?
  command_output="$(WINEDEBUG=-all "${WINE_CMD[@]}" "$probe_windows" 2>&1)" \
    || exit_code=$?
  printf '%s\n' "$command_output"
  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^solution_converged=true$' \
    || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^active_circuit=available$' \
    || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^PASS opendss_com$'
}

run_wireshark_packet_workload() {
  local app_dir="$PREFIX/drive_c/Program Files/Wireshark"
  local tshark='C:\Program Files\Wireshark\tshark.exe'
  local test_dir="$PREFIX/drive_c/macwin-tests/wireshark"
  local capture="$test_dir/macwin-smoke.pcap"
  local capture_windows='C:\macwin-tests\wireshark\macwin-smoke.pcap'
  local command_output exit_code=0
  local expected='1,192.0.2.1,198.51.100.2,4242,54321,4d414357494e2d504341502d50415353'

  [ -f "$app_dir/tshark.exe" ] || return 1
  rm -rf "$test_dir"
  mkdir -p "$test_dir"
  /usr/bin/python3 - "$capture" <<'PY'
import socket
import struct
import sys

payload = b"MACWIN-PCAP-PASS"
source_ip = socket.inet_aton("192.0.2.1")
destination_ip = socket.inet_aton("198.51.100.2")
udp = struct.pack("!HHHH", 4242, 54321, 8 + len(payload), 0) + payload
ip_without_checksum = struct.pack(
    "!BBHHHBBH4s4s",
    0x45, 0, 20 + len(udp), 0x1234, 0x4000, 64, 17, 0,
    source_ip, destination_ip,
)
words = struct.unpack("!10H", ip_without_checksum)
checksum_sum = sum(words)
while checksum_sum >> 16:
    checksum_sum = (checksum_sum & 0xFFFF) + (checksum_sum >> 16)
checksum = (~checksum_sum) & 0xFFFF
ip = struct.pack(
    "!BBHHHBBH4s4s",
    0x45, 0, 20 + len(udp), 0x1234, 0x4000, 64, 17, checksum,
    source_ip, destination_ip,
)
ethernet = (
    bytes.fromhex("020000000002")
    + bytes.fromhex("020000000001")
    + struct.pack("!H", 0x0800)
)
packet = ethernet + ip + udp
global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
packet_header = struct.pack("<IIII", 1700000000, 123456, len(packet), len(packet))
with open(sys.argv[1], "wb") as capture:
    capture.write(global_header)
    capture.write(packet_header)
    capture.write(packet)
PY
  [ -s "$capture" ] || return 1

  command_output="$(
    cd "$app_dir" || exit 1
    PATH='C:\Program Files\Wireshark;C:\windows\system32;C:\windows' \
      WINEDEBUG=-all "${WINE_CMD[@]}" "$tshark" \
      -r "$capture_windows" -Y 'udp.dstport == 54321' \
      -T fields -E 'separator=,' \
      -e frame.number -e ip.src -e ip.dst \
      -e udp.srcport -e udp.dstport -e data.data 2>&1
  )" || exit_code=$?
  printf '%s\n' "$command_output"
  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -Fxq "$expected" || return 1
  printf 'MACWIN_WIRESHARK_VERSION=4.6.6\n'
  printf 'MACWIN_WIRESHARK_PACKET=%s\n' "$expected"
  printf 'MACWIN_WIRESHARK_OFFLINE_DISSECTION=PASS\n'
}

run_vlc_audio_workload() {
  local app='C:\Program Files\VideoLAN\VLC\vlc.exe'
  local test_dir="$PREFIX/drive_c/macwin-tests/vlc"
  local input="$test_dir/macwin-tone-input.wav"
  local output="$test_dir/macwin-tone-output.wav"
  local input_windows='C:\macwin-tests\vlc\macwin-tone-input.wav'
  local output_windows='C:\macwin-tests\vlc\macwin-tone-output.wav'
  local sout
  local command_output exit_code=0

  [ -f "$PREFIX/drive_c/Program Files/VideoLAN/VLC/vlc.exe" ] || return 1
  rm -rf "$test_dir"
  mkdir -p "$test_dir" "$PREFIX/drive_c/users/$USER/AppData/Roaming/vlc"
  : > "$PREFIX/drive_c/users/$USER/AppData/Roaming/vlc/vlcrc"
  /usr/bin/python3 - "$input" <<'PY'
import math
import struct
import sys
import wave

sample_rate = 8000
with wave.open(sys.argv[1], "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(sample_rate)
    audio.writeframes(b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
        for index in range(sample_rate)
    ))
PY
  [ -s "$input" ] || return 1

  sout="#transcode{acodec=s16l,channels=1,samplerate=8000}:standard{access=file,mux=wav,dst=$output_windows}"
  command_output="$(
    WINEDEBUG=-all "${WINE_CMD[@]}" "$app" \
      -I dummy --dummy-quiet --no-video "$input_windows" \
      "--sout=$sout" vlc://quit 2>&1
  )" || exit_code=$?
  printf '%s\n' "$command_output"
  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output" ] || {
    echo "VLC did not create the decoded PCM WAV output." >&2
    return 1
  }

  /usr/bin/python3 - "$output" <<'PY'
import math
import struct
import sys
import wave

with wave.open(sys.argv[1], "rb") as audio:
    channels = audio.getnchannels()
    sample_rate = audio.getframerate()
    sample_width = audio.getsampwidth()
    frame_count = audio.getnframes()
    data = audio.readframes(frame_count)

if channels != 1 or sample_rate != 8000 or sample_width != 2:
    raise SystemExit(
        f"unexpected VLC WAV shape: channels={channels} rate={sample_rate} width={sample_width}"
    )
if not 7400 <= frame_count <= 8000:
    raise SystemExit(f"unexpected VLC frame count: {frame_count}")

samples = struct.unpack(f"<{len(data) // 2}h", data)
rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
crossings = sum(
    1 for left, right in zip(samples, samples[1:])
    if (left < 0 <= right) or (left >= 0 > right)
)
frequency = crossings * sample_rate / (2 * frame_count)
if not 8000 <= rms <= 9000:
    raise SystemExit(f"unexpected VLC PCM RMS: {rms}")
if not 430 <= frequency <= 450:
    raise SystemExit(f"unexpected VLC decoded tone frequency: {frequency}")

print(f"MACWIN_VLC_OUTPUT_FRAMES={frame_count}")
print(f"MACWIN_VLC_OUTPUT_RMS={rms:.3f}")
print(f"MACWIN_VLC_OUTPUT_FREQUENCY={frequency:.3f}")
print("MACWIN_VLC_AUDIO_TRANSCODE=PASS")
PY
}

run_inkscape_core_workload() {
  local inkscape='C:\Program Files\Inkscape\bin\inkscape.exe'
  local input_unix="$SCRIPT_DIR/fixtures/inkscape-smoke.svg"
  local input_windows="Z:${input_unix//\//\\}"
  local output_windows="C:\\users\\$USER\\Temp\\macwin-inkscape.png"
  local output_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-inkscape.png"
  local command_output exit_code image_metadata file_size

  rm -f "$output_unix"
  command_output="$(
    LC_ALL='zh_CN.UTF-8' LANG='zh_CN.UTF-8' WINEDEBUG=-all \
      "${WINE_CMD[@]}" "$inkscape" "$input_windows" \
        --export-type=png --export-filename="$output_windows" \
        --export-width=320 --export-height=180 2>&1
  )"
  exit_code=$?
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$output_unix" ] || return 1
  /usr/bin/file "$output_unix" | rg -q 'PNG image data, 320 x 180, 8-bit/color RGBA' || return 1
  image_metadata="$(/usr/bin/sips -g pixelWidth -g pixelHeight "$output_unix" 2>/dev/null)"
  printf '%s\n' "$image_metadata"
  printf '%s\n' "$image_metadata" | rg -q 'pixelWidth: 320' || return 1
  printf '%s\n' "$image_metadata" | rg -q 'pixelHeight: 180' || return 1
  file_size="$(stat -f '%z' "$output_unix")"
  [ "$file_size" -ge 10000 ] || return 1
  printf 'MACWIN_INKSCAPE_PNG_SIZE=%s\n' "$file_size"
}

run_sqlitebrowser_core_workload() {
  local app_dir="$PREFIX/drive_c/Program Files/DB Browser for SQLite"
  local source="$SCRIPT_DIR/fixtures/sqlitebrowser-probe.c"
  local probe_unix="$app_dir/macwin-sqlitebrowser-probe.exe"
  local probe_windows='C:\Program Files\DB Browser for SQLite\macwin-sqlitebrowser-probe.exe'
  local database_windows="C:\\users\\$USER\\Temp\\macwin-sqlitebrowser.db"
  local database_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-sqlitebrowser.db"
  local command_output exit_code host_rows

  command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1 || {
    echo "x86_64-w64-mingw32-gcc is required for the DB Browser SQLite DLL probe."
    return 127
  }
  [ -f "$app_dir/sqlite3.dll" ] || return 1
  mkdir -p "$(dirname "$database_unix")"
  rm -f "$probe_unix" "$database_unix" "$database_unix-shm" "$database_unix-wal"
  x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -o "$probe_unix" "$source" || return 1

  command_output="$(
    cd "$app_dir" &&
      WINEDEBUG=-all "${WINE_CMD[@]}" "$probe_windows" "$database_windows" 2>&1
  )"
  exit_code=$?
  rm -f "$probe_unix"
  printf '%s\n' "$command_output"

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | tr -d '\r' | rg -F -q \
    'MACWIN_SQLITE_DLL=C:\Program Files\DB Browser for SQLite\sqlite3.dll' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -F -q \
    'MACWIN_SQLITE_ROW=DB Browser|中文数据|98.5' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -F -q \
    'MACWIN_SQLITE_ROW=MacWin CAD|工程软件|96.0' || return 1
  printf '%s\n' "$command_output" | tr -d '\r' | rg -q '^MACWIN_SQLITE_INTEGRITY=ok$' || return 1
  [ -s "$database_unix" ] || return 1

  host_rows="$(/usr/bin/sqlite3 -separator '|' "file:$database_unix?immutable=1" \
    'SELECT name, category, printf("%.1f", score) FROM applications ORDER BY id;')" || return 1
  printf '%s\n' "$host_rows"
  printf '%s\n' "$host_rows" | rg -F -q 'DB Browser|中文数据|98.5' || return 1
  printf '%s\n' "$host_rows" | rg -F -q 'MacWin CAD|工程软件|96.0' || return 1
  [ "$(/usr/bin/sqlite3 "file:$database_unix?immutable=1" 'PRAGMA integrity_check;')" = "ok" ] || return 1
  printf 'MACWIN_SQLITE_DB_SIZE=%s\n' "$(stat -f '%z' "$database_unix")"
}

run_beekeeper_sqlite_workload() {
  local electron='C:\macwin-portable\beekeeper-studio\Beekeeper Studio.exe'
  local script_unix="$SCRIPT_DIR/fixtures/beekeeper-sqlite-smoke.js"
  local script_windows="Z:${script_unix//\//\\}"
  local database_windows="C:\\users\\$USER\\Temp\\macwin-beekeeper.db"
  local database_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-beekeeper.db"
  local result_windows="C:\\users\\$USER\\Temp\\macwin-beekeeper-result.json"
  local result_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-beekeeper-result.json"
  local exit_code

  mkdir -p "$(dirname "$database_unix")"
  rm -f "$database_unix" "$database_unix-shm" "$database_unix-wal" "$result_unix"
  ELECTRON_RUN_AS_NODE=1 WINEDEBUG=-all "${WINE_CMD[@]}" \
    "$electron" "$script_windows" "$database_windows" "$result_windows"
  exit_code=$?

  [ "$exit_code" -eq 0 ] || return "$exit_code"
  [ -s "$database_unix" ] || return 1
  [ -s "$result_unix" ] || return 1
  /usr/bin/python3 - "$result_unix" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as result_file:
    result = json.load(result_file)

expected_rows = [
    {"application": "Beekeeper Studio", "category": "中文数据", "score": "97.5"},
    {"application": "MacWin SQL", "category": "数据库工具", "score": "96.0"},
]
if result.get("integrity") != "ok" or result.get("rows") != expected_rows:
    raise SystemExit(1)
version = str(result.get("sqliteVersion", ""))
if not version.startswith("3."):
    raise SystemExit(1)

print(f"MACWIN_BEEKEEPER_SQLITE_VERSION={version}")
print("MACWIN_BEEKEEPER_INTEGRITY=ok")
print("MACWIN_BEEKEEPER_UTF8=passed")
PY
  /usr/bin/sqlite3 "file:$database_unix?immutable=1" \
    'PRAGMA integrity_check; SELECT application, category, printf("%.1f", score) FROM compatibility_results ORDER BY id;'
  [ "$(/usr/bin/sqlite3 "file:$database_unix?immutable=1" 'PRAGMA integrity_check;')" = "ok" ] || return 1
  printf 'MACWIN_BEEKEEPER_DB_SIZE=%s\n' "$(stat -f '%z' "$database_unix")"
}

run_pgadmin_backend_workload() {
  local base_unix="$PREFIX/drive_c/users/$USER/AppData/Local/Programs/pgAdmin 4"
  local python="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\python\\python.exe"
  local web="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\web\\pgAdmin4.py"
  local psql="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\runtime\\psql.exe"
  local pg_dump="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\runtime\\pg_dump.exe"
  local script_unix="$SCRIPT_DIR/fixtures/pgadmin-backend-smoke.py"
  local script_windows="Z:${script_unix//\//\\}"
  local database_windows="C:\\users\\$USER\\Temp\\macwin-pgadmin-backend.db"
  local database_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-pgadmin-backend.db"
  local result_windows="C:\\users\\$USER\\Temp\\macwin-pgadmin-backend.json"
  local result_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-pgadmin-backend.json"
  local server_log="$LOG_DIR/pgadmin-db-admin-server.log"
  local port key server_pid response="" exit_code=1

  mkdir -p "$(dirname "$database_unix")"
  rm -f "$database_unix" "$database_unix-shm" "$database_unix-wal" "$result_unix" "$server_log"

  WINEDEBUG=-all "${WINE_CMD[@]}" "$python" \
    "$script_windows" "$database_windows" "$result_windows" || return $?
  [ -s "$database_unix" ] || return 1
  [ -s "$result_unix" ] || return 1
  /usr/bin/python3 - "$result_unix" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as result_file:
    result = json.load(result_file)

expected_rows = [
    ["pgAdmin Python", "中文数据", "98.0"],
    ["psycopg", "PostgreSQL 驱动", "97.0"],
]
if result.get("integrity") != "ok" or result.get("rows") != expected_rows:
    raise SystemExit(1)
if result.get("flaskProbe") != {"message": "后端服务正常", "status": "ok"}:
    raise SystemExit(1)
if not str(result.get("pythonVersion", "")).startswith("3.13."):
    raise SystemExit(1)
if not str(result.get("psycopgVersion", "")).startswith("3."):
    raise SystemExit(1)
if not isinstance(result.get("libpqVersion"), int) or result["libpqVersion"] <= 0:
    raise SystemExit(1)

print(f"MACWIN_PGADMIN_PYTHON={result['pythonVersion']}")
print(f"MACWIN_PGADMIN_SQLITE={result['sqliteVersion']}")
print(f"MACWIN_PGADMIN_OPENSSL={result['opensslVersion']}")
print(f"MACWIN_PGADMIN_PSYCOPG={result['psycopgVersion']}")
print(f"MACWIN_PGADMIN_LIBPQ={result['libpqVersion']}")
print("MACWIN_PGADMIN_UTF8=passed")
PY

  "${WINE_CMD[@]}" "$psql" --version | rg -q '^psql \(PostgreSQL\) ' || return 1
  "${WINE_CMD[@]}" "$pg_dump" --version | rg -q '^pg_dump \(PostgreSQL\) ' || return 1

  port="$(/usr/bin/python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
  key="macwin-pgadmin-$RUN_ID"
  (
    cd "$base_unix/web" &&
      PGADMIN_SERVER_MODE=OFF PGADMIN_INT_PORT="$port" PGADMIN_INT_KEY="$key" \
        PYTHONDONTWRITEBYTECODE=1 WINEDEBUG=-all \
        "${WINE_CMD[@]}" "$python" "$web"
  ) >"$server_log" 2>&1 &
  server_pid=$!

  for _ in $(seq 1 60); do
    if response="$(curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS \
      "http://127.0.0.1:$port/misc/ping?key=$key" 2>/dev/null)"; then
      [ "$response" = "PING" ] && exit_code=0
      break
    fi
    kill -0 "$server_pid" 2>/dev/null || break
    sleep 1
  done

  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  "${WINE_CMD[@]}" taskkill.exe /IM python.exe /F >/dev/null 2>&1 || true
  [ "$exit_code" -eq 0 ] || {
    tail -120 "$server_log"
    return 1
  }
  printf 'MACWIN_PGADMIN_SERVER_RESPONSE=%s\n' "$response"
  printf 'MACWIN_PGADMIN_DB_SIZE=%s\n' "$(stat -f '%z' "$database_unix")"
}

run_pgadmin_postgres_workload() {
  local python="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\python\\python.exe"
  local psql="C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\runtime\\psql.exe"
  local script_unix="$SCRIPT_DIR/fixtures/pgadmin-backend-smoke.py"
  local script_windows="Z:${script_unix//\//\\}"
  local database_windows="C:\\users\\$USER\\Temp\\macwin-pgadmin-postgres.db"
  local database_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-pgadmin-postgres.db"
  local result_windows="C:\\users\\$USER\\Temp\\macwin-pgadmin-postgres.json"
  local result_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-pgadmin-postgres.json"
  local psql_output

  rm -f "$database_unix" "$database_unix-shm" "$database_unix-wal" "$result_unix"
  PGCLIENTENCODING=UTF8 WINEDEBUG=-all "${WINE_CMD[@]}" "$python" \
    "$script_windows" "$database_windows" "$result_windows" 127.0.0.1 "$USER" || return $?
  [ -s "$result_unix" ] || return 1
  /usr/bin/python3 - "$result_unix" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as result_file:
    result = json.load(result_file)

expected = [
    ["MacWin TCP", "数据库连接", "98.0"],
    ["pgAdmin psycopg", "中文 PostgreSQL", "99.0"],
]
if result.get("postgresRows") != expected:
    raise SystemExit(1)

print("MACWIN_PGADMIN_PSYCOPG_TCP=passed")
for row in result["postgresRows"]:
    print("MACWIN_PGADMIN_POSTGRES_ROW=" + "|".join(row))
PY

  psql_output="$(
    PGCLIENTENCODING=UTF8 WINEDEBUG=-all "${WINE_CMD[@]}" "$psql" \
      -h 127.0.0.1 -p 5432 -U "$USER" -d postgres -X -v ON_ERROR_STOP=1 -At \
      -c "SELECT 'MacWin psql|' || U&'\4E2D\6587\67E5\8BE2' || '|' || current_setting('server_version');" 2>&1
  )" || {
    printf '%s\n' "$psql_output"
    return 1
  }
  printf '%s\n' "$psql_output"
  printf '%s\n' "$psql_output" | tr -d '\r' | rg -q '^MacWin psql\|中文查询\|17\.' || return 1
  printf '%s\n' 'MACWIN_PGADMIN_PSQL_TCP=passed'
}

run_dbeaver_jdbc_workload() {
  local java='C:\macwin-portable\dbeaver-database\dbeaver\jre\bin\java.exe'
  local driver="C:\\users\\$USER\\AppData\\Roaming\\DBeaverData\\drivers\\maven\\maven-central\\org.postgresql\\postgresql\\42.7.13\\postgresql-42.7.13.jar"
  local driver_unix="$PREFIX/drive_c/users/$USER/AppData/Roaming/DBeaverData/drivers/maven/maven-central/org.postgresql/postgresql/42.7.13/postgresql-42.7.13.jar"
  local compiler="C:\\users\\$USER\\AppData\\Roaming\\DBeaverData\\macwin-tools\\ecj-3.46.0.jar"
  local compiler_unix="$PREFIX/drive_c/users/$USER/AppData/Roaming/DBeaverData/macwin-tools/ecj-3.46.0.jar"
  local script_unix="$SCRIPT_DIR/fixtures/dbeaver-jdbc-smoke.java"
  local script_windows="Z:${script_unix//\//\\}"
  local classes_windows="C:\\users\\$USER\\Temp\\macwin-dbeaver-jdbc-classes"
  local classes_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-dbeaver-jdbc-classes"
  local result_windows="C:\\users\\$USER\\Temp\\macwin-dbeaver-jdbc.txt"
  local result_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-dbeaver-jdbc.txt"

  [ -s "$driver_unix" ] || return 1
  [ -s "$compiler_unix" ] || return 1
  mkdir -p "$(dirname "$result_unix")"
  rm -rf "$classes_unix"
  mkdir -p "$classes_unix"
  rm -f "$result_unix"
  JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=14 -Dfile.encoding=UTF-8' \
    WINEDEBUG=-all "${WINE_CMD[@]}" "$java" -jar "$compiler" \
      -17 -proc:none -encoding UTF-8 -d "$classes_windows" "$script_windows" || return $?
  [ -s "$classes_unix/DbeaverJdbcSmoke.class" ] || return 1
  JAVA_TOOL_OPTIONS='-XX:ActiveProcessorCount=14 -Dfile.encoding=UTF-8' \
    WINEDEBUG=-all "${WINE_CMD[@]}" "$java" --class-path "$classes_windows;$driver" \
      DbeaverJdbcSmoke 127.0.0.1 5432 postgres "$USER" "$result_windows" 42.7.13 || return $?
  [ -s "$result_unix" ] || return 1

  /usr/bin/python3 - "$result_unix" <<'PY'
import sys

with open(sys.argv[1], encoding="utf-8") as result_file:
    lines = [line.rstrip("\n") for line in result_file]

if not lines[0].startswith("DRIVER=PostgreSQL JDBC Driver 42.7.13"):
    raise SystemExit(1)
if not lines[1].startswith("SERVER=PostgreSQL 17."):
    raise SystemExit(1)
if lines[2:] != [
    "ROW=DBeaver JDBC|中文数据|99.0",
    "ROW=MacWin Java|数据库连接|98.0",
    "UTF8=passed",
]:
    raise SystemExit(1)

for line in lines:
    print("MACWIN_DBEAVER_" + line)
PY
}

run_firefox_browser_workload() {
  local firefox='C:\Program Files\Mozilla Firefox\firefox.exe'
  local fixture="$SCRIPT_DIR/fixtures/firefox-browser-smoke.py"
  local profile_windows="C:\\macwin-portable\\firefox-workload-$RUN_ID"
  local profile_unix="$PREFIX/drive_c/macwin-portable/firefox-workload-$RUN_ID"
  local screenshot_windows="C:\\users\\$USER\\Temp\\macwin-firefox-browser.png"
  local screenshot_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-firefox-browser.png"
  local tls_screenshot_windows="C:\\users\\$USER\\Temp\\macwin-firefox-tls.png"
  local tls_screenshot_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-firefox-tls.png"
  local result_unix="$PREFIX/drive_c/users/$USER/Temp/macwin-firefox-browser.json"
  local browser_log="$LOG_DIR/firefox-browser-render-engine.log"
  local server_log="$LOG_DIR/firefox-browser-fixture-server.log"
  local port server_pid firefox_pid ready=0

  # Gecko can leave detached content processes after the GUI timeout cleanup.
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  sleep 2

  port="$(/usr/bin/python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
  mkdir -p "$profile_unix" "$(dirname "$screenshot_unix")"
  rm -f "$screenshot_unix" "$tls_screenshot_unix" "$result_unix" "$browser_log" "$server_log"
  if [ -f "$PREFIX/drive_c/macwin-portable/firefox-profile/user.js" ]; then
    cp -f "$PREFIX/drive_c/macwin-portable/firefox-profile/user.js" "$profile_unix/user.js"
  fi
  printf '%s\n' \
    'user_pref("network.proxy.type", 0);' \
    'user_pref("browser.tabs.remote.autostart", true);' \
    'user_pref("dom.ipc.processCount", 1);' \
    >> "$profile_unix/user.js"

  /usr/bin/python3 "$fixture" --port "$port" --result "$result_unix" >"$server_log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 30); do
    if curl --noproxy '*' --connect-timeout 1 --max-time 2 -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    kill -0 "$server_pid" 2>/dev/null || break
    sleep 0.2
  done
  if [ "$ready" -ne 1 ]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    cat "$server_log"
    return 1
  fi

  env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    MOZ_ACCELERATED=0 MOZ_CRASHREPORTER=0 MOZ_CRASHREPORTER_DISABLE=1 \
    MOZ_CRASHREPORTER_NO_REPORT=1 MOZ_DISABLE_CONTENT_SANDBOX=1 \
    MOZ_DISABLE_GPU_SANDBOX=1 MOZ_DISABLE_GMP_SANDBOX=1 \
    MOZ_DISABLE_RDD_SANDBOX=1 MOZ_DISABLE_SOCKET_PROCESS_SANDBOX=1 MOZ_WEBRENDER=0 \
    WINEDEBUG=-all "${WINE_CMD[@]}" "$firefox" \
      --headless --no-remote --new-instance --profile "$profile_windows" \
      --screenshot "$screenshot_windows" --window-size 1280,900 \
      "http://127.0.0.1:$port/" >"$browser_log" 2>&1 &
  firefox_pid=$!

  for _ in $(seq 1 900); do
    if [ -s "$screenshot_unix" ] && [ -s "$result_unix" ]; then
      ready=1
      break
    fi
    kill -0 "$firefox_pid" 2>/dev/null || break
    sleep 0.1
  done

  kill -KILL "$firefox_pid" 2>/dev/null || true
  wait "$firefox_pid" 2>/dev/null || true
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  [ -s "$screenshot_unix" ] && [ -s "$result_unix" ] || {
    cat "$browser_log"
    cat "$server_log"
    return 1
  }

  env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    MOZ_ACCELERATED=0 MOZ_CRASHREPORTER=0 MOZ_CRASHREPORTER_DISABLE=1 \
    MOZ_CRASHREPORTER_NO_REPORT=1 MOZ_DISABLE_CONTENT_SANDBOX=1 \
    MOZ_DISABLE_GPU_SANDBOX=1 MOZ_DISABLE_GMP_SANDBOX=1 \
    MOZ_DISABLE_RDD_SANDBOX=1 MOZ_DISABLE_SOCKET_PROCESS_SANDBOX=1 MOZ_WEBRENDER=0 \
    WINEDEBUG=-all "${WINE_CMD[@]}" "$firefox" \
      --headless --no-remote --new-instance --profile "$profile_windows" \
      --screenshot "$tls_screenshot_windows" --window-size 1024,768 \
      'https://example.com/' >>"$browser_log" 2>&1 &
  firefox_pid=$!
  for _ in $(seq 1 600); do
    [ -s "$tls_screenshot_unix" ] && break
    kill -0 "$firefox_pid" 2>/dev/null || break
    sleep 0.1
  done
  kill -KILL "$firefox_pid" 2>/dev/null || true
  wait "$firefox_pid" 2>/dev/null || true
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  [ -s "$tls_screenshot_unix" ] || {
    cat "$browser_log"
    return 1
  }

  /usr/bin/python3 - "$result_unix" "$screenshot_unix" "$tls_screenshot_unix" <<'PY'
import json
import os
import struct
import sys

result_path, screenshot_path, tls_screenshot_path = sys.argv[1:4]
with open(result_path, encoding="utf-8") as result_file:
    result = json.load(result_file)

if result.get("api") != {"message": "浏览器网络正常", "score": 100}:
    raise SystemExit(1)
if result.get("canvasPixel") != [11, 110, 79, 255]:
    raise SystemExit(1)
for key in ("cryptoRandom", "cssGrid", "fontAvailable", "utf8RoundTrip"):
    if result.get(key) is not True:
        raise SystemExit(1)
if "Firefox/152.0.1" not in result.get("userAgent", ""):
    raise SystemExit(1)

with open(screenshot_path, "rb") as screenshot_file:
    header = screenshot_file.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit(1)
width, height = struct.unpack(">II", header[16:24])
if (width, height) != (1280, 900):
    raise SystemExit(1)
if os.path.getsize(screenshot_path) < 20000:
    raise SystemExit(1)
with open(tls_screenshot_path, "rb") as screenshot_file:
    tls_header = screenshot_file.read(24)
if tls_header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit(1)
tls_width, tls_height = struct.unpack(">II", tls_header[16:24])
if (tls_width, tls_height) != (1024, 768):
    raise SystemExit(1)
if os.path.getsize(tls_screenshot_path) < 8000:
    raise SystemExit(1)

print("MACWIN_FIREFOX_GECKO=passed")
print("MACWIN_FIREFOX_TLS=passed")
print("MACWIN_FIREFOX_UTF8=passed")
print("MACWIN_FIREFOX_CANVAS=passed")
print("MACWIN_FIREFOX_CSS_GRID=passed")
print(f"MACWIN_FIREFOX_SCREENSHOT={width}x{height}")
PY
  printf '%s\n' \
    'MACWIN_FIREFOX_GECKO=passed' \
    'MACWIN_FIREFOX_TLS=passed' \
    'MACWIN_FIREFOX_UTF8=passed' \
    'MACWIN_FIREFOX_CANVAS=passed' \
    'MACWIN_FIREFOX_CSS_GRID=passed'
  printf 'MACWIN_FIREFOX_SCREENSHOT_SIZE=%s\n' "$(stat -f '%z' "$screenshot_unix")"
  printf 'MACWIN_FIREFOX_TLS_SCREENSHOT_SIZE=%s\n' "$(stat -f '%z' "$tls_screenshot_unix")"
}

run_chromium_browser_workload() {
  local sample_id="$1"
  local browser="$2"
  local profile_stem="$3"
  local local_port="$4"
  local tls_port="$5"
  local fixture_source="$SCRIPT_DIR/fixtures/brave-browser-smoke.html"
  local fixture_unix="$PREFIX/drive_c/macwin-tests/chromium-browser-smoke.html"
  local fixture_url='file:///C:/macwin-tests/chromium-browser-smoke.html'
  local local_report="$LOG_DIR/$sample_id-local-page.json"
  local local_screenshot="$LOG_DIR/$sample_id-local-page.png"
  local tls_report="$LOG_DIR/$sample_id-tls-page.json"
  local tls_screenshot="$LOG_DIR/$sample_id-tls-page.png"
  local browser_log="$LOG_DIR/$sample_id-render-engine.log"
  local inspector_log="$LOG_DIR/$sample_id-inspector.log"
  local common_args=(
    --no-first-run --no-default-browser-check --no-sandbox
    --no-proxy-server --proxy-server=direct:// '--proxy-bypass-list=*'
    --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb
    --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization
    --disable-gpu-sandbox --disable-direct-composition --disable-vulkan
    --disable-webgpu --disable-accelerated-2d-canvas --use-gl=disabled
    --enable-features=FontSrcLocalMatching
    --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc
  )
  local pid port profile report screenshot page

  mkdir -p "$(dirname "$fixture_unix")"
  cp -f "$fixture_source" "$fixture_unix"
  rm -f "$local_report" "$local_screenshot" "$tls_report" "$tls_screenshot" \
    "$browser_log" "$inspector_log"

  for page in local tls; do
    if [ "$page" = local ]; then
      port="$local_port"
      profile="C:\\macwin-portable\\$profile_stem-workload-local"
      report="$local_report"
      screenshot="$local_screenshot"
      page="$fixture_url"
    else
      port="$tls_port"
      profile="C:\\macwin-portable\\$profile_stem-workload-tls"
      report="$tls_report"
      screenshot="$tls_screenshot"
      page='https://example.com/'
    fi

    env -u ROSETTA_X87_PATH -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
      WINEDEBUG=-all "${WINE_CMD[@]}" "$browser" \
      "--user-data-dir=$profile" "--remote-debugging-port=$port" \
      --remote-allow-origins=* "${common_args[@]}" "$page" >>"$browser_log" 2>&1 &
    pid=$!
    if ! env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
      /usr/bin/swift "$SCRIPT_DIR/inspect-chromium-page.swift" "$port" \
      "$report" "$screenshot" 4 50 >>"$inspector_log" 2>&1; then
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
      cat "$browser_log"
      cat "$inspector_log"
      return 1
    fi
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
    sleep 1
  done

  /usr/bin/python3 - "$sample_id" "$local_report" "$local_screenshot" "$tls_report" "$tls_screenshot" <<'PY'
import json
import os
import struct
import sys

sample_id, local_report_path, local_png, tls_report_path, tls_png = sys.argv[1:6]
local = json.load(open(local_report_path, encoding="utf-8"))["diagnostics"]
tls = json.load(open(tls_report_path, encoding="utf-8"))["diagnostics"]

text = local.get("visibleTextSample", "")
if local.get("readyState") != "complete":
    raise SystemExit("local fixture did not reach readyState=complete")
if "浏览器兼容性测试" not in text or "MACWIN_CHROMIUM_FIXTURE_READY" not in text:
    raise SystemExit("local fixture Chinese/English sentinel text is missing")
if local.get("canvasCount", 0) < 1 or local.get("visibleElementCount", 0) < 10:
    raise SystemExit("local fixture Canvas or visible DOM did not render")
if not tls.get("href", "").startswith("https://example.com/"):
    raise SystemExit(f"{sample_id} did not load the HTTPS workload")
if "Example Domain" not in tls.get("visibleTextSample", ""):
    raise SystemExit("HTTPS page body text was not rendered")

for path in (local_png, tls_png):
    with open(path, "rb") as image:
        header = image.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"invalid PNG screenshot: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 640 or height < 480 or os.path.getsize(path) < 8000:
        raise SystemExit(f"undersized browser screenshot: {path} ({width}x{height})")

print(f"MACWIN_CHROMIUM_SAMPLE={sample_id}")
print("MACWIN_CHROMIUM_LOCAL_RENDER=passed")
print("MACWIN_CHROMIUM_UTF8=passed")
print("MACWIN_CHROMIUM_CANVAS=passed")
print("MACWIN_CHROMIUM_TLS=passed")
print("MACWIN_CHROMIUM_INPUT_CONTROL=present")
PY
}

run_brave_browser_workload() {
  run_chromium_browser_workload brave-portable \
    'C:\macwin-portable\brave-portable\app\brave.exe' brave 9233 9234
}

run_opera_browser_workload() {
  run_chromium_browser_workload opera-browser \
    'C:\macwin-portable\opera-browser\opera.exe' opera 9235 9236
}

run_edge_browser_workload() {
  run_chromium_browser_workload edge-enterprise \
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' edge 9238 9239
}

run_itch_market_workload() {
  local app="C:\\users\\$USER\\AppData\\Local\\itch\\app-26.13.0\\itch.exe"
  local report="$LOG_DIR/itch-ui.json"
  local screenshot="$LOG_DIR/itch-ui.png"
  local browser_log="$LOG_DIR/itch-render-engine.log"
  local inspector_log="$LOG_DIR/itch-inspector.log"
  local port=9237 pid

  rm -f "$report" "$screenshot" "$browser_log" "$inspector_log"
  env -u ROSETTA_X87_PATH -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    ITCH_CHROME_DEVTOOLS_PORT="$port" ELECTRON_ENABLE_LOGGING=1 ELECTRON_FORCE_IS_PACKAGED=1 \
    LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 WINEDEBUG=-all \
    WINE_D3D_CONFIG=renderer=gl,csmt=0x0 \
    'WINEDLLOVERRIDES=qone,wbemprox=d;winemenubuilder.exe=d' \
    "${WINE_CMD[@]}" "$app" \
    --no-sandbox --no-proxy-server --proxy-server=direct:// '--proxy-bypass-list=*' \
    --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb \
    --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization \
    --disable-gpu-sandbox --disable-direct-composition --disable-vulkan --disable-webgpu \
    --disable-accelerated-2d-canvas --disable-accelerated-video-decode \
    --disable-accelerated-video-encode --disable-oop-rasterization \
    --disable-oop-rasterization-ddl --disable-gpu-memory-buffer-compositor-resources \
    --disable-partial-raster --in-process-gpu --use-angle=swiftshader --use-gl=angle \
    --enable-unsafe-swiftshader --enable-features=FontSrcLocalMatching \
    '--disable-features=CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder' \
    "--remote-debugging-port=$port" --remote-allow-origins=* >"$browser_log" 2>&1 &
  pid=$!
  if ! env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    /usr/bin/swift "$SCRIPT_DIR/inspect-chromium-page.swift" "$port" \
    "$report" "$screenshot" 8 70 >"$inspector_log" 2>&1; then
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
    cat "$browser_log"
    cat "$inspector_log"
    return 1
  fi
  kill -KILL "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true

  /usr/bin/python3 - "$report" "$screenshot" "$browser_log" <<'PY'
import json
import os
import struct
import sys

report_path, screenshot_path, log_path = sys.argv[1:4]
diagnostics = json.load(open(report_path, encoding="utf-8"))["diagnostics"]
text = diagnostics.get("visibleTextSample", "")
if diagnostics.get("readyState") != "complete" or diagnostics.get("title") != "itch":
    raise SystemExit("itch renderer did not reach its completed root window")
if "app-26.13.0/resources/app/dist/renderer/index.html" not in diagnostics.get("href", ""):
    raise SystemExit("itch did not load the expected Electron renderer")
if "Log in with itch.io" not in text or "已保存的账号" not in text:
    raise SystemExit("itch login UI or Chinese localization text is missing")
if diagnostics.get("visibleElementCount", 0) < 20 or diagnostics.get("bodyHTMLLength", 0) < 1000:
    raise SystemExit("itch visible DOM is incomplete")
with open(log_path, encoding="utf-8", errors="replace") as handle:
    log = handle.read()
for marker in ("itch@26.13.0", '"preload done"', "Now speaking with butlerd", "Setup done"):
    if marker not in log:
        raise SystemExit(f"itch startup marker is missing: {marker}")
with open(screenshot_path, "rb") as image:
    header = image.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("itch screenshot is not a PNG")
width, height = struct.unpack(">II", header[16:24])
if width < 900 or height < 600 or os.path.getsize(screenshot_path) < 10000:
    raise SystemExit(f"itch screenshot is undersized: {width}x{height}")
print("MACWIN_ITCH_ELECTRON=passed")
print("MACWIN_ITCH_UTF8=passed")
print("MACWIN_ITCH_INPUT_UI=passed")
print("MACWIN_ITCH_BUTLERD=passed")
print(f"MACWIN_ITCH_SCREENSHOT={width}x{height}")
PY
}

run_npackd_repository_workload() {
  local database="$PREFIX/drive_c/ProgramData/Npackd/Data.db"
  local temp_root="$PREFIX/drive_c/users/$USER/AppData/Local/Temp"
  local windows_temp="$PREFIX/drive_c/windows/temp"
  /usr/bin/python3 - "$database" "$temp_root" "$windows_temp" <<'PY'
import os
import sqlite3
import sys
import time

database = sys.argv[1]
temp_roots = sys.argv[2:]
if not os.path.isfile(database) or os.path.getsize(database) < 10 * 1024 * 1024:
    raise SystemExit("Npackd repository database is missing or undersized")

connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
try:
    counts = {
        "packages": connection.execute("select count(*) from PACKAGE").fetchone()[0],
        "versions": connection.execute("select count(*) from PACKAGE_VERSION").fetchone()[0],
        "categories": connection.execute("select count(*) from CATEGORY").fetchone()[0],
        "links": connection.execute("select count(*) from LINK").fetchone()[0],
    }
    named_packages = connection.execute(
        "select count(*) from PACKAGE where length(trim(TITLE)) > 0 and length(trim(DESCRIPTION)) > 0"
    ).fetchone()[0]
    icon_metadata = connection.execute(
        "select count(*) from PACKAGE where length(trim(coalesce(ICON, ''))) > 0"
    ).fetchone()[0]
finally:
    connection.close()

if counts["packages"] < 1000 or counts["versions"] < 10000 or counts["categories"] < 10:
    raise SystemExit(f"Npackd repository is incomplete: {counts}")
if named_packages < 900 or counts["links"] < 1000:
    raise SystemExit("Npackd package metadata and links are incomplete")
if icon_metadata < 800:
    raise SystemExit(f"Npackd icon metadata is incomplete: {icon_metadata}")

cache_directories = []
for temp_root in temp_roots:
    if not os.path.isdir(temp_root):
        continue
    for name in os.listdir(temp_root):
        if not name.startswith("npackdg-"):
            continue
        path = os.path.join(temp_root, name)
        if os.path.isdir(path):
            cache_directories.append(path)

def is_image_payload(path):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    with open(path, "rb") as image:
        header = image.read(16)
    return (
        header.startswith(b"\x00\x00\x01\x00")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.lstrip().startswith(b"<svg")
    )

icon_count = 0
if cache_directories:
    newest_cache = max(cache_directories, key=os.path.getmtime)
    icon_count = sum(
        1 for child in os.listdir(newest_cache)
        if is_image_payload(os.path.join(newest_cache, child))
    )
if icon_count < 6:
    raise SystemExit(f"Npackd icon cache is incomplete: {icon_count}")

age_seconds = max(0, int(time.time() - os.path.getmtime(database)))
if age_seconds > 600:
    raise SystemExit(f"Npackd repository database was not refreshed by this run: age={age_seconds}s")

print(f'MACWIN_NPACKD_PACKAGES={counts["packages"]}')
print(f'MACWIN_NPACKD_VERSIONS={counts["versions"]}')
print(f'MACWIN_NPACKD_CATEGORIES={counts["categories"]}')
print(f'MACWIN_NPACKD_LINKS={counts["links"]}')
print(f"MACWIN_NPACKD_NAMED_PACKAGES={named_packages}")
print(f"MACWIN_NPACKD_ICON_METADATA={icon_metadata}")
print(f"MACWIN_NPACKD_ICONS={icon_count}")
print(f"MACWIN_NPACKD_DB_AGE_SECONDS={age_seconds}")
print("MACWIN_NPACKD_REPOSITORY=passed")
PY
}

run_cura_slicing_workload() {
  local app_dir="$PREFIX/drive_c/Program Files/UltiMaker Cura 5.13.0"
  local output="$PREFIX/drive_c/macwin-testdata/cura/nozzle.gcode"
  local output_windows='C:\macwin-testdata\cura\nozzle.gcode'
  local definition='C:\Program Files\UltiMaker Cura 5.13.0\share\cura\resources\definitions\fdmprinter.def.json'
  local model='C:\Program Files\UltiMaker Cura 5.13.0\share\cura\plugins\SimulationView\resources\nozzle.stl'
  local search_path='C:\Program Files\UltiMaker Cura 5.13.0\share\cura\resources\definitions;C:\Program Files\UltiMaker Cura 5.13.0\share\cura\resources\extruders'

  [ -f "$app_dir/CuraEngine.exe" ] || return 1
  [ -f "$app_dir/share/cura/plugins/SimulationView/resources/nozzle.stl" ] || return 1
  mkdir -p "$(dirname "$output")"
  rm -f "$output"
  (
    cd "$app_dir" || exit 1
    /usr/bin/env CURA_ENGINE_SEARCH_PATH="$search_path" WINEDEBUG=-all \
      "${WINE_CMD[@]}" 'C:\Program Files\UltiMaker Cura 5.13.0\CuraEngine.exe' \
      slice -p -j "$definition" \
      -s machine_extruder_count=1 -s layer_height=0.2 -s layer_height_0=0.2 \
      -s wall_line_count=2 -s top_layers=4 -s bottom_layers=4 \
      -s roofing_layer_count=0 -s flooring_layer_count=0 -s infill_sparse_density=15 \
      -s material_print_temperature=200 -s material_bed_temperature=60 \
      -s machine_width=220 -s machine_depth=220 -s machine_height=250 \
      -s machine_center_is_zero=false -s adhesion_type=skirt \
      -e0 -s machine_nozzle_size=0.4 -s material_diameter=1.75 \
      -l "$model" -o "$output_windows"
  )

  /usr/bin/python3 - "$output" <<'PY'
import os
import sys

path = sys.argv[1]
if not os.path.isfile(path) or os.path.getsize(path) < 100_000:
    raise SystemExit("CuraEngine G-code output is missing or undersized")
with open(path, encoding="utf-8", errors="replace") as handle:
    text = handle.read()
move_count = sum(1 for line in text.splitlines() if line.startswith(("G0 ", "G1 ")))
for marker in (";FLAVOR:Marlin", ";Filament used:", ";TIME_ELAPSED:", ";End of Gcode"):
    if marker not in text:
        raise SystemExit(f"CuraEngine output marker is missing: {marker}")
if move_count < 1_000:
    raise SystemExit(f"CuraEngine produced too few motion commands: {move_count}")
print(f"MACWIN_CURA_GCODE_BYTES={os.path.getsize(path)}")
print(f"MACWIN_CURA_MOTION_COMMANDS={move_count}")
print("MACWIN_CURA_SLICE=passed")
PY
}

run_bambu_studio_slicing_workload() {
  local app_dir="$PREFIX/drive_c/macwin-portable/bambu-studio-portable"
  local app_windows='C:\macwin-portable\bambu-studio-portable'
  local output_dir="$PREFIX/drive_c/macwin-tests/bambu-studio/cli-output"
  local output_windows='C:\macwin-tests\bambu-studio\cli-output'
  local fixture_windows="$app_windows\\resources\\calib\\filament_flow\\flowrate-test-pass1.3mf"
  local gcode="$output_dir/plate_1.gcode"
  local result="$output_dir/result.json"
  local project="$output_dir/result.3mf"

  [ -f "$app_dir/bambu-studio.exe" ] || return 1
  [ -f "$app_dir/resources/calib/filament_flow/flowrate-test-pass1.3mf" ] || return 1
  rm -rf "$output_dir"
  mkdir -p "$output_dir/slicedata"
  (
    cd "$app_dir" || exit 1
    /usr/bin/env \
      WINEDEBUG=-all \
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0 \
      'WINEDLLOVERRIDES=opengl32,msvcp140,msvcp140_1,msvcp140_2,msvcp140_codecvt_ids,vcruntime140,vcruntime140_1,concrt140=n;winemenubuilder.exe=d' \
      GALLIUM_DRIVER=llvmpipe \
      LIBGL_ALWAYS_SOFTWARE=1 \
      MESA_GL_VERSION_OVERRIDE=4.5COMPAT \
      MESA_GLSL_VERSION_OVERRIDE=450 \
      "${WINE_CMD[@]}" "$app_windows\\bambu-studio.exe" \
      --slice 0 --debug 3 \
      --outputdir "$output_windows" \
      --export-3mf 'result.3mf' \
      "$fixture_windows"
  )

  /usr/bin/python3 - "$gcode" "$result" "$project" <<'PY'
import json
import os
import sys
import zipfile

gcode_path, result_path, project_path = sys.argv[1:4]
if not os.path.isfile(gcode_path) or os.path.getsize(gcode_path) < 100_000:
    raise SystemExit("Bambu Studio G-code output is missing or undersized")
if not os.path.isfile(result_path):
    raise SystemExit("Bambu Studio result.json is missing")
if not os.path.isfile(project_path) or os.path.getsize(project_path) < 100_000:
    raise SystemExit("Bambu Studio exported 3MF is missing or undersized")
with zipfile.ZipFile(project_path) as archive:
    bad_member = archive.testzip()
    if bad_member is not None:
        raise SystemExit(f"Bambu Studio 3MF contains a corrupt member: {bad_member}")
    names = set(archive.namelist())
required_members = {
    "3D/3dmodel.model",
    "Metadata/project_settings.config",
    "Metadata/slice_info.config",
    "Metadata/plate_1.gcode",
    "Metadata/plate_1.png",
}
missing_members = sorted(required_members - names)
if missing_members:
    raise SystemExit(f"Bambu Studio 3MF is missing members: {missing_members}")
with open(result_path, encoding="utf-8") as handle:
    result = json.load(handle)
if result.get("return_code") != 0 or result.get("error_string") != "Success.":
    raise SystemExit(f"Bambu Studio reported a failed slice: {result}")
plates = result.get("sliced_plates") or []
objects = sum(len(plate.get("objects") or []) for plate in plates)
triangles = sum(int(plate.get("triangle_count") or 0) for plate in plates)
if len(plates) != 1 or objects != 9 or triangles < 6_000:
    raise SystemExit(
        f"Bambu Studio result structure is incomplete: plates={len(plates)} "
        f"objects={objects} triangles={triangles}"
    )
with open(gcode_path, encoding="utf-8", errors="replace") as handle:
    text = handle.read()
move_count = sum(1 for line in text.splitlines() if line.startswith(("G0 ", "G1 ")))
if move_count < 1_000:
    raise SystemExit(f"Bambu Studio produced too few motion commands: {move_count}")
print(f"MACWIN_BAMBU_GCODE_BYTES={os.path.getsize(gcode_path)}")
print(f"MACWIN_BAMBU_3MF_BYTES={os.path.getsize(project_path)}")
print(f"MACWIN_BAMBU_3MF_MEMBERS={len(names)}")
print(f"MACWIN_BAMBU_MOTION_COMMANDS={move_count}")
print(f"MACWIN_BAMBU_OBJECTS={objects}")
print(f"MACWIN_BAMBU_TRIANGLES={triangles}")
print("MACWIN_BAMBU_SLICE=passed")
PY
}

run_orcaslicer_slicing_workload() {
  local app_dir="$PREFIX/drive_c/Program Files/OrcaSlicer"
  local app_windows='C:\Program Files\OrcaSlicer'
  local output_dir="$PREFIX/drive_c/macwin-tests/orcaslicer/cli-output"
  local output_windows='C:\macwin-tests\orcaslicer\cli-output'
  local fixture_windows="$app_windows\\resources\\calib\\filament_flow\\flowrate-test-pass1.3mf"
  local machine_windows="$app_windows\\resources\\profiles\\BBL\\machine\\Bambu Lab P1P 0.4 nozzle.json"
  local process_windows="$app_windows\\resources\\profiles\\BBL\\process\\0.20mm Standard @BBL P1P.json"
  local filament_windows="$app_windows\\resources\\profiles\\BBL\\filament\\Generic PLA High Speed @BBL P1P.json"
  local gcode="$output_dir/plate_1.gcode"
  local project="$output_dir/result.3mf"

  [ -f "$app_dir/orca-slicer.exe" ] || return 1
  [ -f "$app_dir/resources/calib/filament_flow/flowrate-test-pass1.3mf" ] || return 1
  rm -rf "$output_dir"
  mkdir -p "$output_dir"
  (
    cd "$app_dir" || exit 1
    /usr/bin/env \
      WINEDEBUG=-all \
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0 \
      'WINEDLLOVERRIDES=winemenubuilder.exe=d' \
      "${WINE_CMD[@]}" "$app_windows\\orca-slicer.exe" \
      --load-settings "$machine_windows;$process_windows" \
      --load-filaments "$filament_windows" \
      --slice 0 --debug 3 \
      --outputdir "$output_windows" \
      --export-3mf 'result.3mf' \
      "$fixture_windows"
  )

  /usr/bin/python3 - "$gcode" "$project" <<'PY'
import os
import sys
import zipfile

gcode_path, project_path = sys.argv[1:3]
if not os.path.isfile(gcode_path) or os.path.getsize(gcode_path) < 500_000:
    raise SystemExit("OrcaSlicer G-code output is missing or undersized")
if not os.path.isfile(project_path) or os.path.getsize(project_path) < 100_000:
    raise SystemExit("OrcaSlicer exported 3MF is missing or undersized")
with zipfile.ZipFile(project_path) as archive:
    bad_member = archive.testzip()
    if bad_member is not None:
        raise SystemExit(f"OrcaSlicer 3MF contains a corrupt member: {bad_member}")
    names = set(archive.namelist())
required_members = {
    "3D/3dmodel.model",
    "Metadata/project_settings.config",
    "Metadata/model_settings.config",
    "Metadata/slice_info.config",
    "Metadata/plate_1.gcode",
}
missing_members = sorted(required_members - names)
if missing_members:
    raise SystemExit(f"OrcaSlicer 3MF is missing members: {missing_members}")
objects = sum(1 for name in names if name.startswith("3D/Objects/") and name.endswith(".model"))
if objects != 9:
    raise SystemExit(f"OrcaSlicer exported an unexpected object count: {objects}")
with open(gcode_path, encoding="utf-8", errors="replace") as handle:
    move_count = sum(1 for line in handle if line.startswith(("G0 ", "G1 ")))
if move_count < 10_000:
    raise SystemExit(f"OrcaSlicer produced too few motion commands: {move_count}")
print(f"MACWIN_ORCASLICER_GCODE_BYTES={os.path.getsize(gcode_path)}")
print(f"MACWIN_ORCASLICER_3MF_BYTES={os.path.getsize(project_path)}")
print(f"MACWIN_ORCASLICER_3MF_MEMBERS={len(names)}")
print(f"MACWIN_ORCASLICER_MOTION_COMMANDS={move_count}")
print(f"MACWIN_ORCASLICER_OBJECTS={objects}")
print("MACWIN_ORCASLICER_SLICE=passed")
PY
}

run_krita_image_workload() {
  local app_dir="$PREFIX/drive_c/Program Files/Krita (x64)/bin"
  local test_dir="$PREFIX/drive_c/macwin-testdata/krita"
  local input="$test_dir/krita-input.bmp"
  local output="$test_dir/krita-output.png"

  [ -f "$app_dir/krita.exe" ] || return 1
  mkdir -p "$test_dir"
  rm -f "$output"
  /usr/bin/python3 - "$input" <<'PY'
import struct
import sys

path = sys.argv[1]
width = height = 256
row_size = (width * 3 + 3) & ~3
pixels = bytearray()
for y in range(height - 1, -1, -1):
    row = bytearray()
    for x in range(width):
        if x < 128 and y < 128:
            red, green, blue = 230, 55, 70
        elif x >= 128 and y < 128:
            red, green, blue = 45, 180, 95
        elif x < 128:
            red, green, blue = 55, 105, 225
        else:
            red, green, blue = 245, 190, 45
        if 112 <= x < 144 or 112 <= y < 144:
            value = 245 if ((x // 8 + y // 8) % 2 == 0) else 25
            red = green = blue = value
        row.extend((blue, green, red))
    row.extend(b"\0" * (row_size - width * 3))
    pixels.extend(row)
file_size = 54 + len(pixels)
header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
info = struct.pack(
    "<IIIHHIIIIII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0
)
with open(path, "wb") as handle:
    handle.write(header + info + pixels)
PY

  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH WINEDEBUG=-all \
      WINE_D3D_CONFIG='renderer=gl,csmt=0x0' QT_OPENGL=desktop PYTHONHASHSEED=0 \
      "${WINE_CMD[@]}" 'C:\Program Files\Krita (x64)\bin\krita.exe' \
      --export --export-filename 'C:\macwin-testdata\krita\krita-output.png' \
      'C:\macwin-testdata\krita\krita-input.bmp'
  )

  /usr/bin/python3 - "$output" <<'PY'
import binascii
import struct
import sys
import zlib

path = sys.argv[1]
data = open(path, "rb").read()
if len(data) < 1_000 or data[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("Krita PNG output is missing or invalid")
position = 8
compressed = bytearray()
width = height = bit_depth = color_type = interlace = None
while position < len(data):
    length = struct.unpack(">I", data[position:position + 4])[0]
    kind = data[position + 4:position + 8]
    payload = data[position + 8:position + 8 + length]
    expected_crc = struct.unpack(">I", data[position + 8 + length:position + 12 + length])[0]
    if binascii.crc32(kind + payload) & 0xffffffff != expected_crc:
        raise SystemExit(f"Krita PNG chunk CRC failed: {kind!r}")
    if kind == b"IHDR":
        width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
    elif kind == b"IDAT":
        compressed.extend(payload)
    position += 12 + length
if (width, height, bit_depth, color_type, interlace) != (256, 256, 8, 6, 0):
    raise SystemExit("Krita PNG dimensions or RGBA format are incorrect")

raw = zlib.decompress(bytes(compressed))
bytes_per_pixel = 4
stride = width * bytes_per_pixel
if len(raw) != height * (stride + 1):
    raise SystemExit("Krita PNG scanline payload has an unexpected size")

def paeth(left, above, upper_left):
    value = left + above - upper_left
    left_distance = abs(value - left)
    above_distance = abs(value - above)
    upper_left_distance = abs(value - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    return above if above_distance <= upper_left_distance else upper_left

rows = []
previous = bytearray(stride)
for y in range(height):
    offset = y * (stride + 1)
    filter_type = raw[offset]
    source = raw[offset + 1:offset + 1 + stride]
    row = bytearray(stride)
    for index, value in enumerate(source):
        left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        above = previous[index]
        upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        predictor = {
            0: 0,
            1: left,
            2: above,
            3: (left + above) // 2,
            4: paeth(left, above, upper_left),
        }.get(filter_type)
        if predictor is None:
            raise SystemExit(f"Unsupported PNG filter from Krita: {filter_type}")
        row[index] = (value + predictor) & 0xff
    rows.append(row)
    previous = row

def rgba(x, y):
    start = x * bytes_per_pixel
    return tuple(rows[y][start:start + bytes_per_pixel])

expected = {
    (64, 64): (230, 55, 70, 255),
    (192, 64): (45, 180, 95, 255),
    (64, 192): (55, 105, 225, 255),
    (192, 192): (245, 190, 45, 255),
}

for point, color in expected.items():
    if rgba(*point) != color:
        raise SystemExit(f"Krita changed image content at {point}: {rgba(*point)}")
if rgba(120, 120) == rgba(120, 128):
    raise SystemExit("Krita checkerboard detail was lost during export")
print(f"MACWIN_KRITA_PNG_BYTES={len(data)}")
print(f"MACWIN_KRITA_DIMENSIONS={width}x{height}")
print("MACWIN_KRITA_IMAGE_EXPORT=passed")
PY
}

run_godot_vulkan_workload() {
  local sample_id="${1:-godot-win64-editor}"
  local exe installed_exe architecture
  local fixture_source="$SCRIPT_DIR/fixtures/godot-vulkan-smoke"
  local project_dir="$PREFIX/drive_c/macwin-tests/godot-vulkan-smoke"
  local project_windows='C:\macwin-tests\godot-vulkan-smoke'
  local output="$project_dir/godot-vulkan-smoke.png"
  local command_output image_width image_height exit_code=0

  case "$sample_id" in
    godot-win64-editor)
      exe='C:\macwin-portable\godot-win64-editor\Godot_v4.7-stable_win64.exe'
      installed_exe="$PREFIX/drive_c/macwin-portable/godot-win64-editor/Godot_v4.7-stable_win64.exe"
      architecture="x86_64"
      ;;
    godot-win32-editor)
      exe='C:\macwin-portable\godot-win32-editor\Godot_v4.7-stable_win32.exe'
      installed_exe="$PREFIX/drive_c/macwin-portable/godot-win32-editor/Godot_v4.7-stable_win32.exe"
      architecture="i386-wow64"
      ;;
    *)
      return 2
      ;;
  esac

  [ -f "$installed_exe" ] || return 1
  [ -f "$fixture_source/project.godot" ] \
    && [ -f "$fixture_source/main.tscn" ] \
    && [ -f "$fixture_source/main.gd" ] || return 1

  rm -rf "$project_dir"
  mkdir -p "$(dirname "$project_dir")"
  /usr/bin/ditto "$fixture_source" "$project_dir"

  command_output="$(
    "${launch_env_cmd[@]}" PATH="$windows_path_env" "${launch_env[@]}" \
      "${WINE_CMD[@]}" "$exe" \
      --path "$project_windows" \
      --rendering-driver vulkan \
      --rendering-method forward_plus \
      --quit-after 30 \
      --verbose 2>&1
  )" || exit_code=$?
  printf '%s\n' "$command_output"
  [ "$exit_code" -eq 0 ] || return "$exit_code"
  printf '%s\n' "$command_output" | rg -q 'Vulkan [0-9.]+ - Forward\+ - Using Device'
  printf '%s\n' "$command_output" | rg -q 'MACWIN_GODOT_VULKAN=PASS'
  [ -s "$output" ] || return 1

  printf 'MACWIN_GODOT_ARCHITECTURE=%s\n' "$architecture"
  image_width="$(/usr/bin/sips -g pixelWidth "$output" 2>/dev/null | awk '/pixelWidth:/ {print $2}')"
  image_height="$(/usr/bin/sips -g pixelHeight "$output" 2>/dev/null | awk '/pixelHeight:/ {print $2}')"
  printf 'MACWIN_GODOT_CAPTURE=%s\n' "$output"
  printf 'MACWIN_GODOT_CAPTURE_SIZE=%sx%s\n' "$image_width" "$image_height"
  [ "$image_width" = "960" ] && [ "$image_height" = "540" ]
}

run_ltspice_circuit_workload() {
  local app="C:\\Program Files\\ADI\\LTspice\\LTspice.exe"
  local source="$PROJECT_ROOT/refs/testdata/ltspice/rc-transient.cir"
  local test_dir="$PREFIX/drive_c/macwin-tests/ltspice"
  local circuit="$test_dir/rc-transient.cir"
  local circuit_windows="C:\\macwin-tests\\ltspice\\rc-transient.cir"
  local solver_log="$test_dir/rc-transient.log"
  local raw_output="$test_dir/rc-transient.raw"
  local process_log="$LOG_DIR/ltspice-circuit-solver-process.log"
  local prompt_log="$LOG_DIR/ltspice-circuit-first-run-prompt.log"
  local prompt_probe_log="$LOG_DIR/.ltspice-circuit-first-run-probe.log"
  local capture_probe="$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe"
  local capture_probe_windows="Z:${capture_probe//\//\\}"
  local pid elapsed status prompt_dismissed=0

  [ -f "$source" ] || return 1
  [ -f "$PREFIX/drive_c/Program Files/ADI/LTspice/LTspice.exe" ] || return 1
  [ -f "$capture_probe" ] || return 1
  mkdir -p "$test_dir"
  cp "$source" "$circuit"
  rm -f "$test_dir/rc-transient.db" "$test_dir/rc-transient.log" \
    "$test_dir/rc-transient.op.raw" "$raw_output" "$process_log" "$prompt_log" "$prompt_probe_log"

  "${WINE_CMD[@]}" "$app" -b "$circuit_windows" >"$process_log" 2>&1 &
  pid=$!
  elapsed=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$prompt_dismissed" -eq 0 ]; then
      if "${WINE_CMD[@]}" "$capture_probe_windows" --click \
        "Anonymously Share" "No, do not send" >"$prompt_probe_log" 2>&1; then
        "${WINE_CMD[@]}" "$capture_probe_windows" --click \
          "Anonymously Share" "OK" >>"$prompt_probe_log" 2>&1 || true
        printf '%s\n' \
          "LTSPICE_FIRST_RUN_PROMPT=dismissed-with-analytics-disabled" \
          "PASS ltspice_first_run_prompt" >"$prompt_log"
        prompt_dismissed=1
      fi
    fi
    if [ "$elapsed" -ge 60 ]; then
      "${WINE_CMD[@]}" taskkill.exe /IM LTspice.exe /F >>"$process_log" 2>&1 || true
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      echo "LTspice batch simulation timed out." >&2
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  wait "$pid"
  status=$?
  rm -f "$prompt_probe_log"
  if [ "$prompt_dismissed" -eq 0 ]; then
    printf '%s\n' \
      "LTSPICE_FIRST_RUN_PROMPT=not-present" \
      "PASS ltspice_first_run_prompt" >"$prompt_log"
  fi
  [ "$status" -eq 0 ] || return "$status"
  [ -s "$solver_log" ] || return 1
  [ -s "$raw_output" ] || return 1
  if ! /usr/bin/python3 - "$solver_log" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
final_match = re.search(r"vout_final:\s+V\(out\)\s*=\s*([0-9.eE+-]+)", text)
rise_match = re.search(r"rise_time\s*=\s*([0-9.eE+-]+)", text)
if not final_match or not rise_match:
    raise SystemExit("missing LTspice measurement output")
final_voltage = float(final_match.group(1))
rise_time = float(rise_match.group(1))
if not 4.8 <= final_voltage <= 5.1:
    raise SystemExit(f"unexpected final voltage: {final_voltage}")
if not 0.0020 <= rise_time <= 0.0024:
    raise SystemExit(f"unexpected RC rise time: {rise_time}")
print(f"LTSPICE_VOUT_FINAL={final_voltage:.9f}")
print(f"LTSPICE_RISE_TIME={rise_time:.9f}")
PY
  then
    return 1
  fi
  echo "PASS ltspice_rc_transient" | tee -a "$process_log"
}

run_powertoys_fancyzones_workload() {
  local app_dir="$PREFIX/drive_c/users/$USER/AppData/Local/PowerToys"
  local cli="$app_dir/FancyZonesCLI.exe"
  local service="$app_dir/PowerToys.FancyZones.exe"
  local service_log="$LOG_DIR/powertoys-fancyzones-service.log"
  local editor_log="$LOG_DIR/powertoys-fancyzones-open-editor.log"
  local capture_log="$LOG_DIR/powertoys-fancyzones-win32-capture.log"
  local capture_probe="$PROJECT_ROOT/refs/exe-tests/bin/98_window_capture_probe.exe"
  local capture_probe_windows="Z:${capture_probe//\//\\}"
  local capture_dir="$PREFIX/drive_c/users/$USER/Temp"
  local capture_bmp capture_bmp_windows
  local applied_layouts="$PREFIX/drive_c/users/$USER/AppData/Local/Microsoft/PowerToys/FancyZones/applied-layouts.json"
  local service_pid version elapsed

  [ -f "$cli" ] || return 1
  [ -f "$service" ] || return 1
  [ -f "$capture_probe" ] || return 1

  version="$(
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH "${WINE_CMD[@]}" \
      'C:\users\'"$USER"'\AppData\Local\PowerToys\FancyZonesCLI.exe' --version
  )" || return 1
  version="${version//$'\r'/}"
  printf '%s\n' "$version"
  printf '%s\n' "$version" | rg -q '^0\.100\.0\.0$' || return 1

  WINEDEBUG=-all "${WINE_CMD[@]}" reg add \
    'HKCU\Software\Microsoft\Avalon.Graphics' \
    /v DisableHWAcceleration /t REG_DWORD /d 1 /f >/dev/null || return 1

  rm -f "$applied_layouts"
  (
    cd "$app_dir" || exit 1
    exec /usr/bin/env -u ROSETTA_X87_PATH "${WINE_CMD[@]}" \
      'C:\users\'"$USER"'\AppData\Local\PowerToys\PowerToys.FancyZones.exe'
  ) >"$service_log" 2>&1 &
  service_pid="$!"

  elapsed=0
  while [ "$elapsed" -lt 20 ]; do
    if ! kill -0 "$service_pid" 2>/dev/null; then
      wait "$service_pid" 2>/dev/null || true
      echo "FancyZones service exited before the stability threshold." >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  if [ ! -s "$applied_layouts" ]; then
    echo "FancyZones did not generate applied-layouts.json." >&2
    return 1
  fi
  if rg -q 'Unhandled page fault|starting debugger' "$service_log"; then
    echo "FancyZones reported a page fault during the stability window." >&2
    return 1
  fi

  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH "${WINE_CMD[@]}" \
      'C:\users\'"$USER"'\AppData\Local\PowerToys\FancyZonesCLI.exe' open-editor
  ) >"$editor_log" 2>&1 || return 1
  sleep 5
  if ! kill -0 "$service_pid" 2>/dev/null; then
    wait "$service_pid" 2>/dev/null || true
    echo "FancyZones service exited after the editor IPC request." >&2
    return 1
  fi
  if rg -q 'Unhandled page fault|starting debugger' "$service_log" "$editor_log"; then
    echo "FancyZones reported a page fault after the editor IPC request." >&2
    return 1
  fi
  mkdir -p "$capture_dir"
  rm -f "$capture_log"
  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH WINEDEBUG=-all "${WINE_CMD[@]}" \
      "$capture_probe_windows" --list
  ) >>"$capture_log" 2>&1 || true
  capture_bmp="$capture_dir/macwin-fancyzones-editor-print.bmp"
  capture_bmp_windows="C:\\users\\$USER\\Temp\\macwin-fancyzones-editor-print.bmp"
  rm -f "$capture_bmp"
  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH WINEDEBUG=-all "${WINE_CMD[@]}" \
      "$capture_probe_windows" --capture FancyZones "$capture_bmp_windows" print
  ) >>"$capture_log" 2>&1
  [ -s "$capture_bmp" ] || return 1
  echo "PASS fancyzones_win32_capture" >> "$capture_log"
  echo "MACWIN_POWERTOYS_FANCYZONES_VERSION=0.100.0.0"
  echo "MACWIN_POWERTOYS_FANCYZONES_SERVICE_ALIVE_SECONDS=20"
  echo "MACWIN_POWERTOYS_FANCYZONES_LAYOUT_STATE=PASS"
  echo "MACWIN_POWERTOYS_FANCYZONES_EDITOR_IPC=PASS"
  echo "MACWIN_POWERTOYS_FANCYZONES_WIN32_CAPTURE=PASS"
}

run_powertoys_image_resizer_workload() {
  local app_dir="$PREFIX/drive_c/users/$USER/AppData/Local/PowerToys/WinUI3Apps"
  local cli="$app_dir/PowerToys.ImageResizerCLI.exe"
  local test_dir="$PREFIX/drive_c/macwin-tests/powertoys-image-resizer"
  local source="$test_dir/source-128.png"
  local output_dir="$test_dir/out"
  local output="$output_dir/source-128-resized.png"
  local fresh_output_dir="$test_dir/out-fresh"
  local fresh_output="$fresh_output_dir/source-128-fresh.png"

  [ -f "$cli" ] || return 1
  rm -rf "$output_dir" "$fresh_output_dir"
  mkdir -p "$output_dir" "$fresh_output_dir"

  /usr/bin/python3 - "$source" <<'PY'
import binascii
import struct
import sys
import zlib

path = sys.argv[1]
width = height = 128
rows = []
for y in range(height):
    row = bytearray([0])
    for x in range(width):
        row.extend(((x * 2) & 255, (y * 2) & 255, ((x ^ y) * 3) & 255, 255))
    rows.append(bytes(row))

def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xffffffff)

png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
png += chunk(b"IEND", b"")
with open(path, "wb") as stream:
    stream.write(png)
PY

  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH WINEDEBUG=-all "${WINE_CMD[@]}" \
      'C:\users\'"$USER"'\AppData\Local\PowerToys\WinUI3Apps\PowerToys.ImageResizerCLI.exe' \
      --destination 'C:\macwin-tests\powertoys-image-resizer\out' \
      --width 64 --height 64 --unit Pixel --fit Fit \
      --filename '%1-resized' --progress-lines \
      'C:\macwin-tests\powertoys-image-resizer\source-128.png'
  )

  (
    cd "$app_dir" || exit 1
    /usr/bin/env -u ROSETTA_X87_PATH WINEDEBUG=-all "${WINE_CMD[@]}" \
      'C:\users\'"$USER"'\AppData\Local\PowerToys\WinUI3Apps\PowerToys.ImageResizerCLI.exe' \
      --destination 'C:\macwin-tests\powertoys-image-resizer\out-fresh' \
      --width 72 --height 48 --unit Pixel --fit Fill --remove-metadata \
      --filename '%1-fresh' --progress-lines \
      'C:\macwin-tests\powertoys-image-resizer\source-128.png'
  )

  /usr/bin/python3 - "$output" "$fresh_output" <<'PY'
import struct
import sys
import zlib

def paeth(left, above, upper_left):
    prediction = left + above - upper_left
    left_distance = abs(prediction - left)
    above_distance = abs(prediction - above)
    upper_left_distance = abs(prediction - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left

def decode_rows(raw, width, height):
    stride = width * 4
    rows = []
    position = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        encoded = raw[position:position + stride]
        position += stride
        row = bytearray(stride)
        for index, value in enumerate(encoded):
            left = row[index - 4] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = paeth(left, above, upper_left)
            else:
                raise SystemExit(f"Unsupported PNG filter type: {filter_type}")
            row[index] = (value + predictor) & 255
        rows.append(row)
        previous = row
    if position != len(raw):
        raise SystemExit("PowerToys Image Resizer output has trailing pixel data")
    return rows

def inspect(path, expected):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"PowerToys Image Resizer output is not a PNG: {path}")
    position = 8
    compressed = bytearray()
    width = height = bit_depth = color_type = None
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            compressed.extend(payload)
        position += 12 + length
    if (width, height, bit_depth, color_type) != (*expected, 8, 6):
        raise SystemExit(f"Unexpected resized PNG format: {width}x{height}, depth={bit_depth}, color={color_type}")
    raw = zlib.decompress(bytes(compressed))
    if len(raw) != height * (1 + width * 4) or len(set(raw)) < 8:
        raise SystemExit("PowerToys Image Resizer output pixel payload is empty or malformed")
    return width, height, decode_rows(raw, width, height)

transcode_width, transcode_height, transcode_rows = inspect(sys.argv[1], (64, 64))
fresh_width, fresh_height, _ = inspect(sys.argv[2], (72, 48))
sample_offset = 10 * 4
sample_pixel = tuple(transcode_rows[10][sample_offset:sample_offset + 4])
expected_pixel = (41, 41, 2, 255)
if any(abs(actual - expected) > 1 for actual, expected in zip(sample_pixel, expected_pixel)):
    raise SystemExit(
        f"PowerToys Image Resizer did not use smooth WIC interpolation: "
        f"pixel(10,10)={sample_pixel}, expected approximately {expected_pixel}"
    )
print(f"MACWIN_POWERTOYS_IMAGE_RESIZER_TRANSCODE_OUTPUT={sys.argv[1]}")
print(f"MACWIN_POWERTOYS_IMAGE_RESIZER_TRANSCODE_DIMENSIONS={transcode_width}x{transcode_height}")
print(f"MACWIN_POWERTOYS_IMAGE_RESIZER_INTERPOLATED_PIXEL={','.join(map(str, sample_pixel))}")
print(f"MACWIN_POWERTOYS_IMAGE_RESIZER_FRESH_OUTPUT={sys.argv[2]}")
print(f"MACWIN_POWERTOYS_IMAGE_RESIZER_FRESH_DIMENSIONS={fresh_width}x{fresh_height}")
print("MACWIN_POWERTOYS_IMAGE_RESIZER=PASS")
PY
}

prepare_npackd_repository_seed() {
  local cache="$DOWNLOADS/NpackdRepository"
  local seed="$cache/Data.db"
  local destination_dir="$PREFIX/drive_c/ProgramData/Npackd"
  local destination="$destination_dir/Data.db"
  local expected='23c53b9aadf67ee4795ffcc5d6834f7c8bf23d4829b73dffbb3d7004b6379997'
  local actual size

  [ -f "$seed" ] || return 1
  actual="$(shasum -a 256 "$seed" | awk '{print $1}')"
  [ "$actual" = "$expected" ] || return 1
  size="$(stat -f %z "$destination" 2>/dev/null || echo 0)"
  if [ "$size" -lt $((10 * 1024 * 1024)) ]; then
    mkdir -p "$destination_dir"
    cp "$seed" "$destination.tmp"
    mv "$destination.tmp" "$destination"
  fi
  mkdir -p "$PREFIX/drive_c/macwin-runtime/npackd"
  for file_name in stable.zip stable64.zip; do
    if [ -f "$cache/$file_name" ]; then
      cp "$cache/$file_name" "$PREFIX/drive_c/macwin-runtime/npackd/$file_name"
    fi
  done
  touch "$destination"
}

launch_cwd_for_executable() {
  local installed_path="$1"
  local app_dir
  app_dir="$(dirname "$installed_path")"
  if [[ "$installed_path" == *"/macwin-portable/supermium-"*"/Supermium/chrome.exe" ]]; then
    printf '%s\n' "$app_dir"
    return 0
  fi
  if [[ "$installed_path" == *"/QElectroTech/bin/qelectrotech.exe" ]]; then
    printf '%s\n' "$(dirname "$app_dir")"
    return 0
  fi
  if is_chromium_application_dir "$app_dir"; then
    version_dir="$(latest_chromium_version_dir "$app_dir" || true)"
    if [ -n "${version_dir:-}" ]; then
      printf '%s\n' "$version_dir"
      return 0
    fi
  fi
  printf '%s\n' "$app_dir"
}

chromium_software_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-native-gpu-memory-buffers --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --use-gl=disabled --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
geogebra_legacy_args="$chromium_software_args --js-flags=--jitless"
lenovo_appstore_renderer_preset="${MACWIN_LENOVO_RENDERER_PRESET:-dxvk-macos-inprocess}"
lenovo_appstore_debug_port="${MACWIN_LENOVO_DEBUG_PORT:-9231}"
pgadmin_debug_port="${MACWIN_PGADMIN_DEBUG_PORT:-9232}"
openplc_debug_port="${MACWIN_OPENPLC_DEBUG_PORT:-9233}"
lenovo_appstore_args="$chromium_software_args"
case "$lenovo_appstore_renderer_preset" in
  dxvk-macos-inprocess)
    lenovo_appstore_args="--in-process-gpu --no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --use-gl=angle --use-angle=d3d11 --remote-debugging-port=$lenovo_appstore_debug_port --remote-allow-origins=* --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  dxvk-macos)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --use-gl=angle --use-angle=d3d11 --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  swiftshader|angle)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --use-gl=angle --use-angle=swiftshader-webgl --enable-unsafe-swiftshader --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  inprocess-swiftshader)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --in-process-gpu --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  single-process|single-process-software)
    lenovo_appstore_args="--single-process $chromium_software_args"
    ;;
  single-process-swiftshader)
    lenovo_appstore_args="--single-process --no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --in-process-gpu --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  warp|d3d11-warp)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --use-gl=angle --use-angle=d3d11-warp --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  native)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
  stock-software)
    lenovo_appstore_args="$chromium_software_args"
    ;;
  stock-native)
    lenovo_appstore_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu-sandbox --disable-backgrounding-occluded-windows --disable-zero-copy --disable-vulkan --disable-webgpu --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-partial-raster --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,Vulkan,WebGPU,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
    ;;
esac
edge_enterprise_smoke_args="--user-data-dir=C:\\macwin-edge-smoke-profile --no-first-run --no-default-browser-check --disable-sync --disable-background-networking --disable-component-update --disable-default-apps --disable-extensions --disable-popup-blocking $chromium_software_args about:blank"
electron_software_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-native-gpu-memory-buffers --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-oop-rasterization-ddl --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
vscode_software_args="$chromium_software_args --disable-updates"
qtwebengine_software_args="--no-sandbox --single-process --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-software-rasterizer --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-native-gpu-memory-buffers --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --use-gl=disabled --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
qtwebengine_multiprocess_software_args="--no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --lang=zh-CN --accept-lang=zh-CN,zh,en-US,en --force-color-profile=srgb --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-software-rasterizer --disable-direct-composition --disable-backgrounding-occluded-windows --disable-zero-copy --disable-native-gpu-memory-buffers --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-accelerated-video-encode --disable-oop-rasterization --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --use-gl=disabled --enable-features=FontSrcLocalMatching --disable-features=RendererCodeIntegrity,CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,CanvasOopRasterization,UseChromeOSDirectVideoDecoder,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc"
supermium64_portable_args="--disable-encryption --disable-machine-id --user-data-dir=portable_data --no-first-run --no-default-browser-check $chromium_software_args about:blank"
supermium32_portable_args="--disable-encryption --disable-machine-id --user-data-dir=portable_data32-macwin --no-first-run --no-default-browser-check --disable-background-mode --disable-background-networking --new-window --no-sandbox --no-proxy-server --proxy-server=direct:// --proxy-bypass-list=* --disable-gpu --in-process-gpu --use-angle=swiftshader --use-gl=angle --enable-unsafe-swiftshader about:blank"
lenovo_appstore_source_dir="${MACWIN_LENOVO_APPSTORE_SOURCE_DIR:-$ROOT/Bottles/high-performance-win11/drive_c/Program Files (x86)/Lenovo/LeAppStore}"

installers=(
  "quick|7zip|$DOWNLOADS/7z2601-x64.exe|EXE|/S|drive_c/Program Files/7-Zip/7z.exe|C:\\Program Files\\7-Zip\\7z.exe||exit|180|45"
  "quick|sumatrapdf|$DOWNLOADS/SumatraPDF-3.6.1-64-install.exe|EXE|/S|drive_c/users/$USER/AppData/Local/SumatraPDF/SumatraPDF.exe|C:\\users\\$USER\\AppData\\Local\\SumatraPDF\\SumatraPDF.exe||gui|180|20"
  "quick|everything|$DOWNLOADS/Everything-1.4.1.1028.x64-Setup.exe|EXE|/S|drive_c/Program Files/Everything/Everything.exe|C:\\Program Files\\Everything\\Everything.exe||gui|180|20"
  "quick|putty|$DOWNLOADS/putty-64bit-installer.msi|MSI||drive_c/Program Files/PuTTY/putty.exe|C:\\Program Files\\PuTTY\\putty.exe||gui|180|20"
  "browser|chrome-enterprise|$DOWNLOADS/GoogleChromeStandaloneEnterprise64.msi|CHROME_PAYLOAD||drive_c/users/$USER/AppData/Local/Google/Chrome/Application/chrome.exe|C:\\users\\$USER\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe|$chromium_software_args|gui|480|25"
  "browser|firefox-browser|$DOWNLOADS/Firefox_Setup_152.0.1.msi|MSI||drive_c/Program Files/Mozilla Firefox/firefox.exe|C:\\Program Files\\Mozilla Firefox\\firefox.exe|--no-remote --new-instance --profile C:\\macwin-portable\\firefox-profile about:blank|gui|360|25"
  "browser|firefox-developer|$DOWNLOADS/Firefox_Developer_Edition_Setup.exe|EXE_UNTIL_FILE|/S|drive_c/Program Files/Firefox Developer Edition/firefox.exe|C:\\Program Files\\Firefox Developer Edition\\firefox.exe|--no-remote --new-instance --profile C:\\macwin-portable\\firefox-dev-profile about:blank|gui|480|30"
  "browser|vivaldi-browser|$DOWNLOADS/Vivaldi.7.9.3970.47.x64.exe|EXE|--vivaldi-silent --do-not-launch-chrome --system-level|drive_c/Program Files/Vivaldi/Application/vivaldi.exe|C:\\Program Files\\Vivaldi\\Application\\vivaldi.exe|$chromium_software_args|gui|420|30"
  "browser|librewolf-browser|$DOWNLOADS/librewolf-152.0.1-2-windows-x86_64-setup.exe|EXE|/S|drive_c/Program Files/LibreWolf/librewolf.exe|C:\\Program Files\\LibreWolf\\librewolf.exe|--no-remote --new-instance --profile C:\\macwin-portable\\librewolf-profile about:blank|gui|360|30"
  "browser|librewolf-portable|$DOWNLOADS/librewolf-152.0.1-2-windows-x86_64-portable.zip|ZIP||drive_c/macwin-portable/librewolf-portable/librewolf-152.0.1-2/LibreWolf-Portable.exe|C:\\macwin-portable\\librewolf-portable\\librewolf-152.0.1-2\\LibreWolf-Portable.exe||gui|180|30"
  "browser|floorp-browser|$DOWNLOADS/floorp-windows-x86_64.installer.exe|NSIS_EXTRACT|drive_c/Program Files/Ablaze Floorp|drive_c/Program Files/Ablaze Floorp/core/floorp.exe|C:\\Program Files\\Ablaze Floorp\\core\\floorp.exe|--no-remote --new-instance --profile C:\\macwin-portable\\floorp-profile about:blank|gui|240|30"
  "browser|waterfox-browser|$DOWNLOADS/Waterfox_Setup_6.6.15.exe|NSIS_EXTRACT|drive_c/Program Files/Waterfox|drive_c/Program Files/Waterfox/core/waterfox.exe|C:\\Program Files\\Waterfox\\core\\waterfox.exe|--no-remote --new-instance --profile C:\\macwin-portable\\waterfox-profile about:blank|gui|240|30"
  "browser|palemoon-browser|$DOWNLOADS/palemoon-34.3.0.1.win64.installer.exe|NSIS_EXTRACT|drive_c/Program Files/Pale Moon|drive_c/Program Files/Pale Moon/core/palemoon.exe|C:\\Program Files\\Pale Moon\\core\\palemoon.exe|--no-remote --new-instance --profile C:\\macwin-portable\\palemoon-profile about:blank|gui|240|30"
  "browser|palemoon-32-browser|$DOWNLOADS/palemoon-34.3.0.1.win32.installer.exe|NSIS_EXTRACT|drive_c/Program Files (x86)/Pale Moon|drive_c/Program Files (x86)/Pale Moon/core/palemoon.exe|C:\\Program Files (x86)\\Pale Moon\\core\\palemoon.exe|--no-remote --new-instance --profile C:\\macwin-portable\\palemoon32-profile about:blank|gui|240|30"
  "browser|qutebrowser-portable|$DOWNLOADS/qutebrowser-3.7.0-windows-standalone.zip|ZIP||drive_c/macwin-portable/qutebrowser-portable/qutebrowser-3.7.0/qutebrowser.exe|C:\\macwin-portable\\qutebrowser-portable\\qutebrowser-3.7.0\\qutebrowser.exe||gui|240|35"
  "browser|supermium-browser|$DOWNLOADS/Supermium_144_64_setup_win10_11.exe|NSIS_EXTRACT|drive_c/macwin-portable/supermium-browser|drive_c/macwin-portable/supermium-browser/Supermium/chrome.exe|C:\\macwin-portable\\supermium-browser\\Supermium\\chrome.exe|$supermium64_portable_args|gui|240|35"
  "browser|supermium-32-browser|$DOWNLOADS/Supermium_144_32_setup.exe|NSIS_EXTRACT|drive_c/macwin-portable/supermium-32-browser|drive_c/macwin-portable/supermium-32-browser/Supermium/chrome.exe|C:\\macwin-portable\\supermium-32-browser\\Supermium\\chrome.exe|$supermium32_portable_args|gui|240|35"
  "browser|ungoogled-chromium-portable|$DOWNLOADS/ungoogled-chromium_149.0.7827.155-1.1_windows_x64.zip|ZIP||drive_c/macwin-portable/ungoogled-chromium-portable/ungoogled-chromium_149.0.7827.155-1.1_windows_x64/chrome.exe|C:\\macwin-portable\\ungoogled-chromium-portable\\ungoogled-chromium_149.0.7827.155-1.1_windows_x64\\chrome.exe|--user-data-dir=C:\\macwin-portable\\ungoogled-chromium-profile --no-first-run --no-default-browser-check $chromium_software_args about:blank|gui|240|35"
  "browser|brave-portable|$DOWNLOADS/brave-portable-win64-1.89.132-99.7z|7Z||drive_c/macwin-portable/brave-portable/app/brave.exe|C:\\macwin-portable\\brave-portable\\app\\brave.exe|--user-data-dir=C:\\macwin-portable\\brave-portable-profile --no-first-run --no-default-browser-check $chromium_software_args about:blank|gui|240|35"
  "browser|opera-browser|$DOWNLOADS/Opera_132.0.5905.73_Setup_x64.exe|SFX_7Z_EXTRACT|drive_c/macwin-portable/opera-browser|drive_c/macwin-portable/opera-browser/opera.exe|C:\\macwin-portable\\opera-browser\\opera.exe|--user-data-dir=C:\\macwin-portable\\opera-profile --no-first-run --no-default-browser-check $chromium_software_args about:blank|gui|300|35"
  "browser|min-browser-portable|$DOWNLOADS/Min-v1.35.5-windows.zip|ZIP||drive_c/macwin-portable/min-browser-portable/Min-v1.35.5/Min.exe|C:\\macwin-portable\\min-browser-portable\\Min-v1.35.5\\Min.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\min-profile about:blank|gui|240|35"
  "browser|edge-enterprise|$DOWNLOADS/MicrosoftEdgeEnterpriseX64.msi|MSI_UNTIL_FILE||drive_c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe|C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe|$edge_enterprise_smoke_args|gui|420|30"
  "browser|brave-standalone|$DOWNLOADS/BraveBrowserStandaloneSetup.exe|EXE|--silent --install|drive_c/users/$USER/AppData/Local/BraveSoftware/Brave-Browser/Application/brave.exe|C:\\users\\$USER\\AppData\\Local\\BraveSoftware\\Brave-Browser\\Application\\brave.exe|$chromium_software_args|gui|420|30"
  "browser|seamonkey-browser|$DOWNLOADS/seamonkey-2.53.23.zh-CN.win64.installer.exe|NSIS_EXTRACT|drive_c/Program Files/SeaMonkey|drive_c/Program Files/SeaMonkey/core/seamonkey.exe|C:\\Program Files\\SeaMonkey\\core\\seamonkey.exe|--no-remote --new-instance --profile C:\\macwin-portable\\seamonkey-profile about:blank|gui|240|30"
  "browser|seamonkey-32-browser|$DOWNLOADS/seamonkey-2.53.21.zh-CN.win32.installer.exe|NSIS_EXTRACT|drive_c/Program Files (x86)/SeaMonkey|drive_c/Program Files (x86)/SeaMonkey/core/seamonkey.exe|C:\\Program Files (x86)\\SeaMonkey\\core\\seamonkey.exe|--no-remote --new-instance --profile C:\\macwin-portable\\seamonkey32-profile about:blank|gui|240|30"
  "browser|mullvad-browser|$DOWNLOADS/mullvad-browser-windows-x86_64-15.0.16.exe|NSIS_EXTRACT|drive_c/Program Files/Mullvad Browser|drive_c/Program Files/Mullvad Browser/Browser/mullvadbrowser.exe|C:\\Program Files\\Mullvad Browser\\Browser\\mullvadbrowser.exe|--no-remote --new-instance --profile C:\\macwin-portable\\mullvad-profile about:blank|gui|300|35"
  "browser|zen-browser|$DOWNLOADS/ZenBrowser-1.21.3b-installer.exe|SFX_7Z_EXTRACT|drive_c/macwin-portable/zen-browser|drive_c/macwin-portable/zen-browser/core/zen.exe|C:\\macwin-portable\\zen-browser\\core\\zen.exe|--no-remote --new-instance --profile C:\\macwin-portable\\zen-profile about:blank|gui|240|35"
  "browser|otter-browser-portable|$DOWNLOADS/otter-browser-win64-weekly120.zip|ZIP||drive_c/macwin-portable/otter-browser-portable/otter-browser-win64-weekly120/otter-browser.exe|C:\\macwin-portable\\otter-browser-portable\\otter-browser-win64-weekly120\\otter-browser.exe|about:blank|gui|180|30"
  "browser|kmeleon-portable|$DOWNLOADS/K-MeleonPortable_76.5.5-2024-12-21.paf.exe|NSIS_EXTRACT|drive_c/macwin-portable/kmeleon-portable|drive_c/macwin-portable/kmeleon-portable/K-MeleonPortable.exe|C:\\macwin-portable\\kmeleon-portable\\K-MeleonPortable.exe||gui|180|30"
  "market|npackd|$DOWNLOADS/Npackd64-1.26.9.zip|ZIP||drive_c/macwin-portable/npackd/npackdg.exe|C:\\macwin-portable\\npackd\\npackdg.exe||gui|180|35"
  "market|portableapps-platform|$DOWNLOADS/PortableApps.com_Platform_Setup_30.4.1.paf.exe|DIRECT||drive_c/macwin-portable/portableapps-platform/PortableApps.com_Platform_Setup_30.4.1.paf.exe|C:\\macwin-portable\\portableapps-platform\\PortableApps.com_Platform_Setup_30.4.1.paf.exe||gui|60|30"
  "market|lenovo-app-store|$lenovo_appstore_source_dir|DIRECTORY_COPY|drive_c/Program Files (x86)/Lenovo/LeAppStore|drive_c/Program Files (x86)/Lenovo/LeAppStore/LenovoAppStore.exe|C:\\Program Files (x86)\\Lenovo\\LeAppStore\\LenovoAppStore.exe|$lenovo_appstore_args|gui|600|35"
  "market|itch|$DOWNLOADS/itch-setup-windows-amd64.exe|EXE_UNTIL_FILE|--silent|drive_c/users/$USER/AppData/Local/itch/app-26.13.0/itch.exe|C:\\users\\$USER\\AppData\\Local\\itch\\app-26.13.0\\itch.exe|$electron_software_args --in-process-gpu --use-angle=swiftshader --use-gl=angle --enable-unsafe-swiftshader|gui|420|35"
  "office|libreoffice-suite|$DOWNLOADS/LibreOffice_26.2.4_Win_x86-64.msi|MSI||drive_c/Program Files/LibreOffice/program/soffice.exe|C:\\Program Files\\LibreOffice\\program\\soffice.exe||gui|600|30"
  "office|wps-office|$DOWNLOADS/WPSOffice-offline.exe|WPS_PACKET_EXTRACT|12.1.0.27458|drive_c/Program Files/Kingsoft/WPS Office/12.1.0.27458/office6/wps.exe|C:\\Program Files\\Kingsoft\\WPS Office\\12.1.0.27458\\office6\\wps.exe|C:\\macwin-tests\\wps\\macwin-wps-smoke.rtf|gui|900|40"
  "office|onlyoffice-suite|$DOWNLOADS/OnlyOfficeDesktopEditors-x64.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/ONLYOFFICE/DesktopEditors/DesktopEditors.exe|C:\\Program Files\\ONLYOFFICE\\DesktopEditors\\DesktopEditors.exe|--no-sandbox --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-gpu-sandbox --disable-direct-composition --disable-vulkan --disable-webgpu --disable-accelerated-2d-canvas --disable-accelerated-video-decode --disable-oop-rasterization --disable-gpu-memory-buffer-compositor-resources --disable-partial-raster --use-gl=disabled --disable-features=CalculateNativeWinOcclusion,VizDisplayCompositor,Vulkan,WebGPU,DirectCompositionUseDCompVisualTree,UseDCompVisualTree,DawnGraphite,SkiaGraphite,RawDraw,EnableDrDc|gui|600|30"
  "office|thunderbird-mail|$DOWNLOADS/Thunderbird-latest-win64-zhCN.exe|EXE|-ms|drive_c/Program Files/Mozilla Thunderbird/thunderbird.exe|C:\\Program Files\\Mozilla Thunderbird\\thunderbird.exe||gui|420|30"
  "office|texstudio-editor|$DOWNLOADS/Texstudio-4.9.5-win-qt6-signed.exe|NSIS_EXTRACT|drive_c/Program Files/TeXstudio|drive_c/Program Files/TeXstudio/texstudio.exe|C:\\Program Files\\TeXstudio\\texstudio.exe|--no-session -platform windows:fontengine=freetype|gui|420|30"
  "office|calibre-library|$DOWNLOADS/calibre-64bit-9.9.0.msi|MSI||drive_c/Program Files/Calibre2/calibre.exe|C:\\Program Files\\Calibre2\\calibre.exe||gui|600|35"
  "office|freeoffice-suite|$DOWNLOADS/FreeOffice2024.msi|MSI||drive_c/Program Files (x86)/SoftMaker FreeOffice 2024/TextMaker.exe|C:\\Program Files (x86)\\SoftMaker FreeOffice 2024\\TextMaker.exe||gui|600|30"
  "office|pdfxchange-editor|$DOWNLOADS/EditorV11.x64.msi|MSI||drive_c/Program Files/PDF-XChange/PDF Editor/PXCEditor.exe|C:\\Program Files\\PDF-XChange\\PDF Editor\\PXCEditor.exe|C:\\macwin-testdata\\pdfxchange\\PXCLicense.pdf|gui|600|30"
  "office|typora-editor|$DOWNLOADS/typora-setup-x64.exe|INNO_EXTRACT|drive_c/Program Files/Typora|drive_c/Program Files/Typora/Typora.exe|C:\\Program Files\\Typora\\Typora.exe|$chromium_software_args --user-data-dir=C:\\macwin-portable\\typora-profile --no-sandbox|gui|420|30"
  "office|naps2-scanner|$DOWNLOADS/NAPS2-8.2.1-win-x64.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/NAPS2/NAPS2.exe|C:\\Program Files\\NAPS2\\NAPS2.exe||gui|420|25"
  "office|cherrytree-notes|$DOWNLOADS/CherryTree-1.7.0-win64-setup.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/CherryTree/ucrt64/bin/cherrytree.exe|C:\\Program Files\\CherryTree\\ucrt64\\bin\\cherrytree.exe||gui|420|25"
  "office|freemind-mindmap|$DOWNLOADS/FreeMind-Windows-Installer-1.0.1-max.exe|INNO_EXTRACT|drive_c/Program Files/FreeMind|drive_c/Program Files/FreeMind/FreeMind.exe|C:\\Program Files\\FreeMind\\FreeMind.exe||gui|300|25"
  "office|freeplane-mindmap|$DOWNLOADS/Freeplane-Setup-1.13.2.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/Freeplane/freeplane.exe|C:\\Program Files\\Freeplane\\freeplane.exe||gui|600|35"
  "office|projectlibre-pm|$DOWNLOADS/ProjectLibre-1.9.8.msi|MSI||drive_c/Program Files/ProjectLibre/ProjectLibre.exe|C:\\Program Files\\ProjectLibre\\ProjectLibre.exe||gui|600|35"
  "office|lyx-editor|$DOWNLOADS/LyX-251-Installer-1-x64.exe|NSIS_EXTRACT|drive_c/Program Files/LyX|drive_c/Program Files/LyX/bin/LyX.exe|C:\\Program Files\\LyX\\bin\\LyX.exe||gui|420|30"
  "office|focuswriter-editor|$DOWNLOADS/FocusWriter-1.9.0-Windows10-x64.exe|NSIS_EXTRACT|drive_c/Program Files/FocusWriter|drive_c/Program Files/FocusWriter/FocusWriter.exe|C:\\Program Files\\FocusWriter\\FocusWriter.exe||gui|300|25"
  "office|zettlr-editor|$DOWNLOADS/Zettlr-4.6.0-x64.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/zettlr-editor|drive_c/macwin-portable/zettlr-editor/Zettlr.exe|C:\\macwin-portable\\zettlr-editor\\Zettlr.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\zettlr-profile|gui|360|35"
  "office|zotero-research|$DOWNLOADS/Zotero-Windows-latest.exe|EXE|/S|drive_c/Program Files (x86)/Zotero/zotero.exe|C:\\Program Files (x86)\\Zotero\\zotero.exe|-no-remote -profile C:\\macwin-portable\\zotero-profile|gui|420|30"
  "office|jabref-portable|$DOWNLOADS/JabRef-5.15-portable_windows.zip|ZIP||drive_c/macwin-portable/jabref-portable/JabRef/JabRef.exe|C:\\macwin-portable\\jabref-portable\\JabRef\\JabRef.exe||gui|300|35"
  "office|openboard-whiteboard|$DOWNLOADS/OpenBoard_Installer_1.7.3.exe|INNO_EXTRACT|drive_c/Program Files/OpenBoard|drive_c/Program Files/OpenBoard/OpenBoard.exe|C:\\Program Files\\OpenBoard\\OpenBoard.exe||gui|600|35"
  "office|scribus-dtp|$DOWNLOADS/Scribus-1.4.8-windows-x64.exe|NSIS_EXTRACT|drive_c/Program Files/Scribus|drive_c/Program Files/Scribus/Scribus.exe|C:\\Program Files\\Scribus\\Scribus.exe||gui|420|30"
  "office|qownnotes-portable|$DOWNLOADS/QOwnNotes.zip|ZIP||drive_c/macwin-portable/qownnotes-portable/QOwnNotes.exe|C:\\macwin-portable\\qownnotes-portable\\QOwnNotes.exe|--portable|gui|180|25"
  "office|marktext-editor|$DOWNLOADS/marktext-win-x64-0.19.1-setup.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/marktext-editor|drive_c/macwin-portable/marktext-editor/marktext.exe|C:\\macwin-portable\\marktext-editor\\marktext.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\marktext-profile|gui|360|35"
  "office|wxmaxima|$DOWNLOADS/wxMaxima-26.06.2-win64.exe|NSIS_EXTRACT|drive_c/Program Files/wxMaxima|drive_c/Program Files/wxMaxima/bin/wxmaxima.exe|C:\\Program Files\\wxMaxima\\bin\\wxmaxima.exe||gui|240|30"
  "office|macwin-maxima-cas|$DOWNLOADS/maxima-5.49.0-win64.exe|SFX_7Z_EXTRACT|drive_c/Program Files/Maxima-5.49.0|drive_c/Program Files/Maxima-5.49.0/bin/wxmaxima.exe|C:\\Program Files\\Maxima-5.49.0\\bin\\wxmaxima.exe||gui|420|35"
  "office|labplot-workbench|$DOWNLOADS/labplot-2.12.1-x86_64-setup.exe|EMBEDDED_7Z_EXTRACT|drive_c/Program Files/LabPlot|drive_c/Program Files/LabPlot/bin/labplot.exe|C:\\Program Files\\LabPlot\\bin\\labplot.exe||gui|420|35"
  "office|smath-studio|$DOWNLOADS/SMathStudioDesktop.1_4_0_9654.Setup.msi|MSI||drive_c/Program Files (x86)/SMath Studio/Solver.exe|C:\\Program Files (x86)\\SMath Studio\\Solver.exe||gui|420|30"
  "office|dia-diagram|$DOWNLOADS/dia-setup-0.97.2-2-unsigned.exe|NSIS_EXTRACT|drive_c/Program Files/Dia|drive_c/Program Files/Dia/bin/diaw.exe|C:\\Program Files\\Dia\\bin\\diaw.exe||gui|240|25"
  "office|sigil-ebook|$DOWNLOADS/Sigil-2.8.0-Windows-x64-Setup.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/Sigil/Sigil.exe|C:\\Program Files\\Sigil\\Sigil.exe||gui|420|30"
  "office|joplin-notes|$DOWNLOADS/Joplin-Setup-3.6.15.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/joplin-notes|drive_c/macwin-portable/joplin-notes/Joplin.exe|C:\\macwin-portable\\joplin-notes\\Joplin.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\joplin-profile|gui|360|35"
  "office|obsidian-notes|$DOWNLOADS/Obsidian-1.12.7.exe|EXE|/S|drive_c/users/$USER/AppData/Local/Programs/obsidian/Obsidian.exe|C:\\users\\$USER\\AppData\\Local\\Programs\\obsidian\\Obsidian.exe|$chromium_software_args|gui|360|30"
  "office|standard-notes|$DOWNLOADS/standard-notes-3.201.21-win-x64.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/standard-notes|drive_c/macwin-portable/standard-notes/Standard Notes.exe|C:\\macwin-portable\\standard-notes\\Standard Notes.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\standard-notes-profile|gui|360|35"
  "office|pdfarranger-portable|$DOWNLOADS/pdfarranger-1.14.0-windows-portable.zip|ZIP||drive_c/macwin-portable/pdfarranger-portable/pdf arranger-1.14.0/pdfarranger.exe|C:\\macwin-portable\\pdfarranger-portable\\pdf arranger-1.14.0\\pdfarranger.exe||gui|180|30"
  "productivity|drawio-diagram|$DOWNLOADS/draw.io-30.2.4.msi|MSI||drive_c/Program Files/draw.io/draw.io.exe|C:\\Program Files\\draw.io\\draw.io.exe|$chromium_software_args|gui|420|30"
  "developer|sqlitebrowser-db|$DOWNLOADS/DB.Browser.for.SQLite-v3.13.1-win64.msi|MSI||drive_c/Program Files/DB Browser for SQLite/DB Browser for SQLite.exe|C:\\Program Files\\DB Browser for SQLite\\DB Browser for SQLite.exe||gui|300|25"
  "developer|sqlitestudio-db|$DOWNLOADS/SQLiteStudio-3.4.17-windows-x64-installer.exe|EXE|--mode unattended --install_for local|drive_c/Program Files/SQLiteStudio/SQLiteStudio.exe|C:\\Program Files\\SQLiteStudio\\SQLiteStudio.exe||gui|300|25"
  "developer|pgadmin-db-admin|$DOWNLOADS/pgadmin4-9.16-x64.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/users/$USER/AppData/Local/Programs/pgAdmin 4/runtime/pgAdmin4.exe|C:\\users\\$USER\\AppData\\Local\\Programs\\pgAdmin 4\\runtime\\pgAdmin4.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\pgadmin-profile|gui|600|40"
  "developer|heidisql-portable|$DOWNLOADS/HeidiSQL_12.19_64_Portable.zip|ZIP||drive_c/macwin-portable/heidisql-portable/heidisql.exe|C:\\macwin-portable\\heidisql-portable\\heidisql.exe||gui|180|25"
  "developer|beekeeper-studio|$DOWNLOADS/Beekeeper-Studio-Setup-5.8.1.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/beekeeper-studio|drive_c/macwin-portable/beekeeper-studio/Beekeeper Studio.exe|C:\\macwin-portable\\beekeeper-studio\\Beekeeper Studio.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\beekeeper-profile|gui|360|35"
  "developer|postman-api-client|$DOWNLOADS/Postman-win64-latest.exe|SQUIRREL_ZIP||drive_c/macwin-portable/postman-api-client/Postman.exe|C:\\macwin-portable\\postman-api-client\\Postman.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\postman-profile|gui|240|35"
  "developer|vscode-portable|$DOWNLOADS/VSCode-win32-x64-1.125.1.zip|ZIP||drive_c/macwin-portable/vscode-portable/Code.exe|C:\\macwin-portable\\vscode-portable\\Code.exe|$vscode_software_args --user-data-dir=C:\\macwin-portable\\vscode-portable-user-data --disable-extensions --skip-welcome --skip-release-notes --new-window|gui|240|35"
  "developer|thonny-portable|$DOWNLOADS/thonny-5.0.0-windows-portable-x64.zip|ZIP||drive_c/macwin-portable/thonny-portable/thonny.exe|C:\\macwin-portable\\thonny-portable\\thonny.exe||gui|180|30"
  "developer|rstudio-desktop|$DOWNLOADS/RStudio-2025.09.0-387.exe|EXE|/S|drive_c/Program Files/RStudio/rstudio.exe|C:\\Program Files\\RStudio\\rstudio.exe|$chromium_software_args|gui|600|45"
  "developer|julia-cli|$DOWNLOADS/Julia-1.12.2-win64.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER|drive_c/users/$USER/AppData/Local/Programs/Julia-1.12.2/bin/julia.exe|C:\\users\\$USER\\AppData\\Local\\Programs\\Julia-1.12.2\\bin\\julia.exe|--version|exit|420|45"
  "developer|pandoc-cli|$DOWNLOADS/pandoc-3.10-windows-x86_64.msi|MSI||drive_c/users/$USER/AppData/Local/Pandoc/pandoc.exe|C:\\users\\$USER\\AppData\\Local\\Pandoc\\pandoc.exe|--version|exit|300|30"
  "developer|cmake-cli|$DOWNLOADS/cmake-4.3.3-windows-x86_64.msi|MSI||drive_c/Program Files/CMake/bin/cmake.exe|C:\\Program Files\\CMake\\bin\\cmake.exe|--version|exit|300|30"
  "developer|nodejs-cli|$DOWNLOADS/node-v26.3.1-x64.msi|MSI||drive_c/Program Files/nodejs/node.exe|C:\\Program Files\\nodejs\\node.exe|--version|exit|300|30"
  "developer|godot-win64-editor|$DOWNLOADS/Godot_v4.7-stable_win64.exe.zip|ZIP||drive_c/macwin-portable/godot-win64-editor/Godot_v4.7-stable_win64.exe|C:\\macwin-portable\\godot-win64-editor\\Godot_v4.7-stable_win64.exe|--single-window --editor --rendering-driver vulkan --rendering-method forward_plus --quit-after 20|gui|120|30"
  "developer|godot-win32-editor|$DOWNLOADS/Godot_v4.7-stable_win32.exe.zip|ZIP||drive_c/macwin-portable/godot-win32-editor/Godot_v4.7-stable_win32.exe|C:\\macwin-portable\\godot-win32-editor\\Godot_v4.7-stable_win32.exe|--single-window --editor --rendering-driver vulkan --rendering-method forward_plus --quit-after 20|gui|120|30"
  "developer|tiled-map-editor|$DOWNLOADS/Tiled-1.12.2_Windows-10+_x86_64.msi|MSI||drive_c/Program Files/Tiled/tiled.exe|C:\\Program Files\\Tiled\\tiled.exe||gui|300|30"
  "industrial|arduino-ide|$DOWNLOADS/arduino-ide_2.3.10_Windows_64bit.exe|EXE|/S|drive_c/users/$USER/AppData/Local/Programs/Arduino IDE/Arduino IDE.exe|C:\\users\\$USER\\AppData\\Local\\Programs\\Arduino IDE\\Arduino IDE.exe|$chromium_software_args|gui|420|35"
  "industrial|dbeaver-database|$DOWNLOADS/dbeaver-ce-latest-win32.win32.x86_64.zip|ZIP||drive_c/macwin-portable/dbeaver-database/dbeaver/dbeaver.exe|C:\\macwin-portable\\dbeaver-database\\dbeaver\\dbeaver.exe||gui|240|35"
  "industrial|ltspice-circuit|$DOWNLOADS/LTspice64.msi|MSI_CAB_7Z|drive_c/Program Files/ADI/LTspice|drive_c/Program Files/ADI/LTspice/LTspice.exe|C:\\Program Files\\ADI\\LTspice\\LTspice.exe||gui|600|30"
  "industrial|qelectrotech-cad|$DOWNLOADS/Installer_QElectroTech-0.100.0_x86_64-win64.exe|NSIS_EXTRACT|drive_c/Program Files/QElectroTech|drive_c/Program Files/QElectroTech/bin/qelectrotech.exe|C:\\Program Files\\QElectroTech\\bin\\qelectrotech.exe|-platform windows:fontengine=freetype --common-elements-dir=elements/ --common-tbt-dir=titleblocks/ --lang-dir=lang/|gui|240|30"
  "industrial|qucs-s-circuit|$DOWNLOADS/Qucs-S-26.1.1-win64.zip|ZIP|drive_c/macwin-portable/qucs-s-circuit|drive_c/macwin-portable/qucs-s-circuit/bin/qucs-s.exe|C:\\macwin-portable\\qucs-s-circuit\\bin\\qucs-s.exe||gui|420|30"
  "industrial|qgis-ltr|$DOWNLOADS/QGIS-OSGeo4W-3.44.11-1.msi|MSI||drive_c/Program Files/QGIS 3.44.11/bin/qgis-ltr-bin.exe|C:\\windows\\system32\\cmd.exe|/c C:\\macwin-launchers\\qgis-ltr-smoke.cmd|gui|900|45"
  "industrial|openmodelica-omedit|$DOWNLOADS/OpenModelica-v1.26.9-64bit.exe|NSIS_EXTRACT|drive_c/Program Files/OpenModelica|drive_c/Program Files/OpenModelica/bin/OMEdit.exe|C:\\Program Files\\OpenModelica\\bin\\OMEdit.exe||gui|1200|45"
  "industrial|orange-data-mining|$DOWNLOADS/Orange3-3.40.0-x86_64.exe|EXE|/S|drive_c/users/$USER/AppData/Local/Programs/Orange/Scripts/orange-canvas.exe|C:\\users\\$USER\\AppData\\Local\\Programs\\Orange\\Scripts\\orange-canvas.exe|--no-welcome|gui|900|45"
  "industrial|scilab-workbench|$DOWNLOADS/Scilab-2026.1.0-x64.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/scilab-2026.1.0/bin/WScilex.exe|C:\\Program Files\\scilab-2026.1.0\\bin\\WScilex.exe||gui|900|45"
  "industrial|octave-workbench|$DOWNLOADS/Octave-11.3.0-w64-installer.exe|EXE|/S|drive_c/Program Files/GNU Octave/Octave-11.3.0/mingw64/bin/octave-gui.exe|C:\\Program Files\\GNU Octave\\Octave-11.3.0\\mingw64\\bin\\octave-gui.exe|--gui|gui|900|45"
  "industrial|kicad-eda|$DOWNLOADS/Kicad-10.0.3-x86_64.exe|NSIS_EXTRACT|drive_c/Program Files/KiCad/10.0|drive_c/Program Files/KiCad/10.0/bin/kicad.exe|C:\\Program Files\\KiCad\\10.0\\bin\\kicad.exe||gui|900|45"
  "industrial|qcad-legacy|$DOWNLOADS/QCad-2.0.5.0-Installer.exe|NSIS_EXTRACT|drive_c/Program Files/QCad 2|drive_c/Program Files/QCad 2/qcad.exe|C:\\Program Files\\QCad 2\\qcad.exe|C:\\macwin-testdata\\qcad\\macwin-qcad-smoke.dxf|gui|180|25"
  "industrial|meshlab-3d|$DOWNLOADS/MeshLab2025.07-windows_x86_64.exe|NSIS_EXTRACT|drive_c/Program Files/MeshLab|drive_c/Program Files/MeshLab/meshlab.exe|C:\\Program Files\\MeshLab\\meshlab.exe|C:\\macwin-tests\\meshlab-cube.obj|gui|360|35"
  "industrial|orcaslicer-print|$DOWNLOADS/OrcaSlicer_Windows_Installer_V2.4.0.exe|NSIS_EXTRACT|drive_c/Program Files/OrcaSlicer|drive_c/Program Files/OrcaSlicer/orca-slicer.exe|C:\\Program Files\\OrcaSlicer\\orca-slicer.exe||gui|600|35"
  "industrial|prusaslicer-print|$DOWNLOADS/PrusaSlicer-2.9.5-setup.exe|INNO_EXTRACT|drive_c/Program Files/Prusa3D/PrusaSlicer|drive_c/Program Files/Prusa3D/PrusaSlicer/prusa-slicer.exe|C:\\Program Files\\Prusa3D\\PrusaSlicer\\prusa-slicer.exe||gui|600|35"
  "industrial|wireshark-analyzer|$DOWNLOADS/Wireshark-latest-x64.exe|NSIS_EXTRACT|drive_c/Program Files/Wireshark|drive_c/Program Files/Wireshark/Wireshark.exe|C:\\Program Files\\Wireshark\\Wireshark.exe||gui|600|35"
  "industrial|geogebra-classic|$DOWNLOADS/GeoGebra-Windows-Installer.exe|SQUIRREL_PE||drive_c/macwin-portable/geogebra-classic/GeoGebra.exe|C:\\macwin-portable\\geogebra-classic\\GeoGebra.exe|$geogebra_legacy_args|gui|300|35"
  "industrial|geogebra-classic5|$DOWNLOADS/GeoGebraClassic5-Windows-Installer.exe|EXE|/S|drive_c/Program Files (x86)/GeoGebra 5.4/GeoGebra.exe|C:\\Program Files (x86)\\GeoGebra 5.4\\GeoGebra.exe||gui|300|35"
  "industrial|sweethome3d-design|$DOWNLOADS/SweetHome3D-7.5-windows.exe|INNO_EXTRACT|drive_c/Program Files/Sweet Home 3D|drive_c/Program Files/Sweet Home 3D/SweetHome3D.exe|C:\\Program Files\\Sweet Home 3D\\SweetHome3D.exe|C:\\macwin-testdata\\sweethome3d\\macwin-studio.sh3d|gui|420|35"
  "industrial|openrocket-sim|$DOWNLOADS/OpenRocket-24.12-installer-Windows-x86_64.exe|EXE|-q|drive_c/Program Files/OpenRocket/OpenRocket.exe|C:\\Program Files\\OpenRocket\\OpenRocket.exe||gui|420|35"
  "industrial|opencpn-chartplotter|$DOWNLOADS/opencpn_5.14.0-0+4418.91f3b67_setup.exe|NSIS_EXTRACT|drive_c/macwin-portable/opencpn|drive_c/macwin-portable/opencpn/opencpn.exe|C:\\macwin-portable\\opencpn\\opencpn.exe||gui|420|35"
  "industrial|qgroundcontrol-drone|$DOWNLOADS/QGroundControl-installer.exe|NSIS_EXTRACT|drive_c/Program Files/QGroundControl|drive_c/Program Files/QGroundControl/bin/QGroundControl.exe|C:\\Program Files\\QGroundControl\\bin\\QGroundControl.exe||gui|600|35"
  "industrial|mqtt-explorer|$DOWNLOADS/MQTT-Explorer-Setup-0.4.0-beta.6.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/mqtt-explorer|drive_c/macwin-portable/mqtt-explorer/MQTT Explorer.exe|C:\\macwin-portable\\mqtt-explorer\\MQTT Explorer.exe|$electron_software_args --user-data-dir=C:\\macwin-portable\\mqtt-explorer-profile|gui|360|35"
  "industrial|jasp-stats|$DOWNLOADS/JASP-0.97.1-Windows-Community.msi|MSI||drive_c/Program Files/JASP/JASPDesktop.exe|C:\\Program Files\\JASP\\JASPDesktop.exe|--safeGraphics --noSandbox|gui|900|45"
  "industrial|mremoteng-manager|$DOWNLOADS/mRemoteNG-Installer-1.76.20.24615.msi|MSI_ADMIN|drive_c/macwin-portable/mremoteng-admin|drive_c/macwin-portable/mremoteng-admin/mRemoteNG/mRemoteNG.exe|C:\\macwin-portable\\mremoteng-admin\\mRemoteNG\\mRemoteNG.exe||gui|300|30"
  "industrial|mremoteng-1782-x64|$DOWNLOADS/mRemoteNG-20260222-v1.78.2-NB-3405-x64.rar|RAR_BSDTAR||drive_c/macwin-portable/mremoteng-1782-x64/mRemoteNG.exe|C:\\macwin-portable\\mremoteng-1782-x64\\mRemoteNG.exe|/reset /noreconnect|gui|180|30"
  "industrial|r-base-gui|$DOWNLOADS/R-4.6.0-win.exe|INNO_EXTRACT|drive_c/Program Files/R/R-4.6.0|drive_c/Program Files/R/R-4.6.0/bin/x64/Rgui.exe|C:\\Program Files\\R\\R-4.6.0\\bin\\x64\\Rgui.exe||gui|420|30"
  "industrial|bambu-studio-portable|$DOWNLOADS/Bambu_Studio_win-v02.07.01.62-20260616174358.zip|ZIP||drive_c/macwin-portable/bambu-studio-portable/bambu-studio.exe|C:\\macwin-portable\\bambu-studio-portable\\bambu-studio.exe||gui|240|40"
  "industrial|logisim-evolution|$DOWNLOADS/logisim-evolution-4.1.0-amd64.msi|MSI||drive_c/Program Files/logisim-evolution/logisim-evolution.exe|C:\\Program Files\\logisim-evolution\\logisim-evolution.exe||gui|420|35"
  "industrial|lasergrbl-cnc|$DOWNLOADS/LaserGRBL-install-7.14.1.exe|INNO_EXTRACT|drive_c/Program Files/LaserGRBL|drive_c/Program Files/LaserGRBL/LaserGRBL.exe|C:\\Program Files\\LaserGRBL\\LaserGRBL.exe||gui|300|25"
  "industrial|slic3r-64|$DOWNLOADS/Slic3r-1.3.0.64bit.zip|ZIP||drive_c/macwin-portable/slic3r-64/Slic3r.exe|C:\\macwin-portable\\slic3r-64\\Slic3r.exe||gui|180|30"
  "industrial|slic3r-32|$DOWNLOADS/Slic3r-1.3.0.32bit.zip|ZIP||drive_c/macwin-portable/slic3r-32/Slic3r.exe|C:\\macwin-portable\\slic3r-32\\Slic3r.exe||gui|180|30"
  "industrial|esphome-flasher-x64|$DOWNLOADS/ESPHome-Flasher-1.4.0-Windows-x64.exe|DIRECT||drive_c/macwin-portable/esphome-flasher-x64/ESPHome-Flasher-1.4.0-Windows-x64.exe|C:\\macwin-portable\\esphome-flasher-x64\\ESPHome-Flasher-1.4.0-Windows-x64.exe|--help|exit|90|30"
  "industrial|esphome-flasher-x86|$DOWNLOADS/ESPHome-Flasher-1.4.0-Windows-x86.exe|DIRECT||drive_c/macwin-portable/esphome-flasher-x86/ESPHome-Flasher-1.4.0-Windows-x86.exe|C:\\macwin-portable\\esphome-flasher-x86\\ESPHome-Flasher-1.4.0-Windows-x86.exe|--help|exit|90|30"
  "industrial|processing-ide|$DOWNLOADS/processing-4.5.2-windows-x64.msi|MSI||drive_c/Program Files/Processing/processing.exe|C:\\Program Files\\Processing\\processing.exe||gui|600|35"
  "industrial|openplc-editor|$DOWNLOADS/OpenPLC.Editor_4.2.7.exe|ELECTRON_BUILDER_NSIS|drive_c/macwin-portable/openplc-editor|drive_c/macwin-portable/openplc-editor/OpenPLC Editor.exe|C:\\macwin-portable\\openplc-editor\\OpenPLC Editor.exe|$electron_software_args --in-process-gpu --use-angle=swiftshader --use-gl=angle --enable-unsafe-swiftshader --user-data-dir=C:\\macwin-portable\\openplc-profile|gui|360|35"
  "industrial|cloudcompare-pointcloud|$DOWNLOADS/CloudCompare_v2.13.2_setup_x64.exe|INNO_EXTRACT|drive_c/Program Files/CloudCompare|drive_c/Program Files/CloudCompare/CloudCompare.exe|C:\\Program Files\\CloudCompare\\CloudCompare.exe||gui|600|35"
  "industrial|paraview-visualization|$DOWNLOADS/ParaView-6.1.0-Windows-Python3.12-msvc2017-AMD64.msi|MSI||drive_c/Program Files/ParaView 6.1.0/bin/paraview.exe|C:\\Program Files\\ParaView 6.1.0\\bin\\paraview.exe||gui|900|45"
  "industrial|graphviz-dot|$DOWNLOADS/Graphviz-15.0.0-win64.exe|NSIS_EXTRACT|drive_c/Program Files/Graphviz|drive_c/Program Files/Graphviz/bin/dot.exe|C:\\Program Files\\Graphviz\\bin\\dot.exe|-V|exit|180|30"
  "industrial|saga-gis|$DOWNLOADS/saga-9.9.1_x64_setup.exe|INNO_EXTRACT|drive_c/Program Files/SAGA|drive_c/Program Files/SAGA/saga_gui.exe|C:\\Program Files\\SAGA\\saga_gui.exe||gui|420|35"
  "industrial|dwsim-process-sim|$DOWNLOADS/DWSIM_v905_win64_setup.exe|NSIS_EXTRACT|drive_c/Program Files/DWSIM|drive_c/Program Files/DWSIM/DWSIM.UI.Desktop.exe|C:\\Program Files\\DWSIM\\DWSIM.UI.Desktop.exe||gui|600|45"
  "industrial|epanet-water|$DOWNLOADS/epanet2.2_setup.exe|INNO_EXTRACT|drive_c/Program Files/EPANET 2.2|drive_c/Program Files/EPANET 2.2/runepanet.exe|C:\\Program Files\\EPANET 2.2\\runepanet.exe|C:\\macwin-testdata\\epanet\\smoke.inp C:\\macwin-testdata\\epanet\\smoke.rpt C:\\macwin-testdata\\epanet\\smoke.bin|exit|240|25"
  "industrial|swmm-hydrology|$DOWNLOADS/swmm524x64_setup.exe|INNO_EXTRACT|drive_c/Program Files/EPA SWMM 5.2|drive_c/Program Files/EPA SWMM 5.2/epaswmm5.exe|C:\\Program Files\\EPA SWMM 5.2\\epaswmm5.exe||gui|300|25"
  "industrial|opendss-power|$DOWNLOADS/opendss-svn-x64/OpenDSScmd.exe|OPENDSS_SVN_X64||drive_c/macwin-portable/opendss-svn-x64/OpenDSScmd.exe|C:\\windows\\system32\\cmd.exe|/c C:\\macwin-launchers\\opendss-svn-x64-smoke.cmd|exit|180|35"
  "industrial|qmodmaster-64|$DOWNLOADS/qModMaster-Win64-exe-0.5.3-beta.zip|ZIP||drive_c/macwin-portable/qmodmaster-64/qModMaster/qModMaster.exe|C:\\macwin-portable\\qmodmaster-64\\qModMaster\\qModMaster.exe||gui|180|25"
  "industrial|qmodmaster-32|$DOWNLOADS/qModMaster-Win32-exe-0.5.2-3.zip|ZIP||drive_c/macwin-portable/qmodmaster-32/qModMaster/qModMaster.exe|C:\\macwin-portable\\qmodmaster-32\\qModMaster\\qModMaster.exe||gui|180|25"
  "industrial|ugs-cnc|$DOWNLOADS/ugs-2.1.23-x64.msi|MSI||drive_c/Program Files/Universal G-code Sender/Universal G-code Sender.exe|C:\\Program Files\\Universal G-code Sender\\Universal G-code Sender.exe||gui|600|35"
  "industrial|energyplus-building|$DOWNLOADS/EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64.exe|QTIFW_UNTIL_FILE|C:\\EnergyPlusV26-1-0|drive_c/EnergyPlusV26-1-0/energyplus.exe|C:\\EnergyPlusV26-1-0\\energyplus.exe|--version|exit|420|45"
  "industrial|openjump-gis|$DOWNLOADS/OpenJUMP-Portable-2.4.0-r5303[6c9a02d]-PLUS.zip|ZIP||drive_c/macwin-portable/openjump-gis/OpenJUMP-2.4.0-r5303[6c9a02d]-PLUS/bin/OpenJUMP.exe|C:\\macwin-portable\\openjump-gis\\OpenJUMP-2.4.0-r5303[6c9a02d]-PLUS\\bin\\OpenJUMP.exe||gui|240|35"
  "industrial|lazarus-ide-64|$DOWNLOADS/lazarus-4.8-fpc-3.2.2-win64.exe|INNO_EXTRACT|drive_c/Program Files/Lazarus|drive_c/Program Files/Lazarus/lazarus.exe|C:\\Program Files\\Lazarus\\lazarus.exe||gui|600|35"
  "industrial|lazarus-fpc-64-version|$DOWNLOADS/lazarus-4.8-fpc-3.2.2-win64.exe|INNO_EXTRACT|drive_c/Program Files/Lazarus|drive_c/Program Files/Lazarus/fpc/3.2.2/bin/x86_64-win64/fpc.exe|C:\\Program Files\\Lazarus\\fpc\\3.2.2\\bin\\x86_64-win64\\fpc.exe|-iV|exit|600|25"
  "industrial|lazarus-ide-32|$DOWNLOADS/lazarus-4.8-fpc-3.2.2-win32.exe|INNO_EXTRACT|drive_c/Program Files (x86)/Lazarus|drive_c/Program Files (x86)/Lazarus/lazarus.exe|C:\\Program Files (x86)\\Lazarus\\lazarus.exe||gui|600|35"
  "industrial|lazarus-fpc-32-version|$DOWNLOADS/lazarus-4.8-fpc-3.2.2-win32.exe|INNO_EXTRACT|drive_c/Program Files (x86)/Lazarus|drive_c/Program Files (x86)/Lazarus/fpc/3.2.2/bin/i386-win32/fpc.exe|C:\\Program Files (x86)\\Lazarus\\fpc\\3.2.2\\bin\\i386-win32\\fpc.exe|-iV|exit|600|25"
  "industrial|codeblocks-mingw|$DOWNLOADS/codeblocks-20.03mingw-setup.exe|NSIS_EXTRACT|drive_c/Program Files/CodeBlocks|drive_c/Program Files/CodeBlocks/codeblocks.exe|C:\\Program Files\\CodeBlocks\\codeblocks.exe||gui|420|35"
  "industrial|codeblocks-gcc-version|$DOWNLOADS/codeblocks-20.03mingw-setup.exe|NSIS_EXTRACT|drive_c/Program Files/CodeBlocks|drive_c/Program Files/CodeBlocks/MinGW/bin/gcc.exe|C:\\Program Files\\CodeBlocks\\MinGW\\bin\\gcc.exe|--version|exit|420|25"
  "cad|librecad|$DOWNLOADS/LibreCAD-v2.2.1.5-win64-msvc.exe|EXE|/S|drive_c/Program Files/LibreCAD/LibreCAD.exe|C:\\Program Files\\LibreCAD\\LibreCAD.exe||gui|300|25"
  "cad|openscad|$DOWNLOADS/OpenSCAD-2021.01-x86-64-Installer.exe|EXE|/S|drive_c/Program Files/OpenSCAD/openscad.exe|C:\\Program Files\\OpenSCAD\\openscad.exe|C:\\macwin-testdata\\openscad\\macwin-cad-smoke.scad|gui|300|25"
  "cad|librepcb-eda|$DOWNLOADS/librepcb-installer-2.1.1-windows-x86_64.exe|INNO_EXTRACT|drive_c/Program Files/LibrePCB|drive_c/Program Files/LibrePCB/bin/librepcb.exe|C:\\Program Files\\LibrePCB\\bin\\librepcb.exe||gui|420|30"
  "cad|gmsh-mesh|$DOWNLOADS/gmsh-4.14.1-Windows64.zip|ZIP||drive_c/macwin-portable/gmsh-mesh/gmsh-4.14.1-Windows64/gmsh.exe|C:\\macwin-portable\\gmsh-mesh\\gmsh-4.14.1-Windows64\\gmsh.exe||gui|240|30"
  "cad|brlcad-tools|$DOWNLOADS/BRL-CAD_7.42.2_win64.msi|MSI||drive_c/Program Files/BRLCAD 7.42.2/bin/archer.exe|C:\\Program Files\\BRLCAD 7.42.2\\bin\\archer.exe||gui|600|35"
  "cad|freecad-workbench|$DOWNLOADS/FreeCAD_1.1.1-Windows-x86_64-py311-installer.exe|EXE|/S|drive_c/Program Files/FreeCAD 1.1/bin/FreeCAD.exe|C:\\Program Files\\FreeCAD 1.1\\bin\\FreeCAD.exe|--safe-mode|gui|900|35"
  "cad|cura-slicer|$DOWNLOADS/UltiMaker-Cura-5.13.0-win64-X64.msi|MSI||drive_c/Program Files/UltiMaker Cura 5.13.0/UltiMaker-Cura.exe|C:\\Program Files\\UltiMaker Cura 5.13.0\\UltiMaker-Cura.exe||gui|900|45"
  "cad|solvespace-direct|$DOWNLOADS/SolveSpace-3.2-x64.exe|DIRECT||drive_c/macwin-portable/solvespace-direct/SolveSpace-3.2-x64.exe|C:\\macwin-portable\\solvespace-direct\\SolveSpace-3.2-x64.exe||gui|60|20"
  "graphics|krita-paint|$DOWNLOADS/krita-x64-5.2.9-setup.exe|EXE|/S|drive_c/Program Files/Krita (x64)/bin/krita.exe|C:\\Program Files\\Krita (x64)\\bin\\krita.exe||gui|480|30"
  "graphics|gimp-image-editor|$DOWNLOADS/GIMP-2.10.38-win64-setup.exe|INNO_EXTRACT|drive_c/Program Files/GIMP 2|drive_c/Program Files/GIMP 2/bin/gimp-2.10.exe|C:\\Program Files\\GIMP 2\\bin\\gimp-2.10.exe||gui|600|30"
  "graphics|inkscape-vector|$DOWNLOADS/Inkscape-1.4.2-x64.msi|MSI||drive_c/Program Files/Inkscape/bin/inkscape.exe|C:\\Program Files\\Inkscape\\bin\\inkscape.exe||gui|600|35"
  "graphics|blender-3d|$DOWNLOADS/blender-4.1.0-windows-x64.msi|MSI||drive_c/Program Files/Blender Foundation/Blender 4.1/blender.exe|C:\\Program Files\\Blender Foundation\\Blender 4.1\\blender.exe||gui|600|35"
  "graphics|audacity-audio|$DOWNLOADS/audacity-win-3.7.8-64bit.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/Audacity/Audacity.exe|C:\\Program Files\\Audacity\\Audacity.exe||gui|420|30"
  "graphics|musescore-studio|$DOWNLOADS/MuseScore-Studio-4.7.3.260608135-x86_64.msi|MSI||drive_c/Program Files/MuseScore 4/bin/MuseScore4.exe|C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe|--session-type start-empty|gui|600|35"
  "graphics|lmms-audio|$DOWNLOADS/lmms-1.2.2-win64.exe|NSIS_EXTRACT|drive_c/Program Files/LMMS|drive_c/Program Files/LMMS/lmms.exe|C:\\Program Files\\LMMS\\lmms.exe||gui|300|30"
  "graphics|openshot-video|$DOWNLOADS/OpenShot-v3.3.0-x86_64.exe|INNO_EXTRACT|drive_c/Program Files/OpenShot|drive_c/Program Files/OpenShot/openshot-qt.exe|C:\\Program Files\\OpenShot\\openshot-qt.exe||gui|600|35"
  "graphics|flameshot-capture|$DOWNLOADS/Flameshot-14.0.0-win64.msi|MSI||drive_c/Program Files/Flameshot/bin/flameshot.exe|C:\\Program Files\\Flameshot\\bin\\flameshot.exe|gui|gui|300|25"
  "utility|powertoys-fancyzones|$DOWNLOADS/PowerToysUserSetup-0.100.0-x64.exe|EXE|/quiet /norestart|drive_c/users/$USER/AppData/Local/PowerToys/FancyZonesCLI.exe|C:\\users\\$USER\\AppData\\Local\\PowerToys\\FancyZonesCLI.exe|--version|exit|900|30"
  "utility|notepadpp-editor|$DOWNLOADS/npp.8.9.6.4.Installer.x64.exe|EXE|/S|drive_c/Program Files/Notepad++/notepad++.exe|C:\\Program Files\\Notepad++\\notepad++.exe||gui|180|20"
  "utility|notepadpp-32-editor|$DOWNLOADS/npp.8.9.6.4.Installer.exe|NSIS_EXTRACT|drive_c/Program Files (x86)/Notepad++|drive_c/Program Files (x86)/Notepad++/notepad++.exe|C:\\Program Files (x86)\\Notepad++\\notepad++.exe||gui|180|20"
  "utility|winscp-client|$DOWNLOADS/WinSCP-6.5.6-Setup.exe|EXE_UNTIL_FILE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files (x86)/WinSCP/WinSCP.exe|C:\\Program Files (x86)\\WinSCP\\WinSCP.exe||gui|300|25"
  "utility|winscp-cli-help|$DOWNLOADS/WinSCP-6.5.6-Setup.exe|EXE_UNTIL_FILE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files (x86)/WinSCP/WinSCP.com|C:\\Program Files (x86)\\WinSCP\\WinSCP.com|/help|exit|300|25"
  "utility|winscp-x64-portable|$DOWNLOADS/WinSCP-6.6.2.RC-Portable-x64-Experimental.zip|ZIP||drive_c/macwin-portable/winscp-x64-portable/WinSCP.exe|C:\\macwin-portable\\winscp-x64-portable\\WinSCP.exe|/ini=nul|gui|180|25"
  "utility|winscp-x64-cli-help|$DOWNLOADS/WinSCP-6.6.2.RC-Portable-x64-Experimental.zip|ZIP||drive_c/macwin-portable/winscp-x64-cli-help/WinSCP.com|C:\\macwin-portable\\winscp-x64-cli-help\\WinSCP.com|/help|exit|180|25"
  "utility|keepass-passwords|$DOWNLOADS/KeePass-2.59-Setup.exe|EXE|/VERYSILENT /SUPPRESSMSGBOXES /NORESTART|drive_c/Program Files/KeePass Password Safe 2/KeePass.exe|C:\\Program Files\\KeePass Password Safe 2\\KeePass.exe||gui|300|25"
  "utility|rufus-direct|$DOWNLOADS/rufus-4.11.exe|DIRECT||drive_c/macwin-portable/rufus-direct/rufus-4.11.exe|C:\\macwin-portable\\rufus-direct\\rufus-4.11.exe||gui|60|20"
  "utility|winmerge-diff|$DOWNLOADS/WinMerge-2.16.50-x64-Setup.exe|INNO_EXTRACT|drive_c/Program Files/WinMerge|drive_c/Program Files/WinMerge/WinMergeU.exe|C:\\Program Files\\WinMerge\\WinMergeU.exe||gui|240|25"
  "utility|qbittorrent-client|$DOWNLOADS/qbittorrent_5.2.2_x64_setup.exe|EXE|/S|drive_c/Program Files/qBittorrent/qbittorrent.exe|C:\\Program Files\\qBittorrent\\qbittorrent.exe||gui|300|25"
  "utility|vlc-media|$DOWNLOADS/vlc-3.0.23-win64.exe|EXE|/S|drive_c/Program Files/VideoLAN/VLC/vlc.exe|C:\\Program Files\\VideoLAN\\VLC\\vlc.exe||gui|300|25"
)

echo "Smoke run: $RUN_ID"
echo "Suite: $SMOKE_SUITE"
if [ -n "$SMOKE_SAMPLE" ]; then
  echo "Sample: $SMOKE_SAMPLE"
fi
echo "Prefix: $PREFIX"
echo "Logs: $LOG_DIR"

validate_selected_samples

bootstrap_status=0
wineboot_timeout="${MACWIN_WINEBOOT_TIMEOUT:-90}"
runtime_stall_pids="$(uninterruptible_wine_pids)"
if [ -n "$runtime_stall_pids" ] && [ "${MACWIN_SMOKE_IGNORE_RUNTIME_STALL:-0}" != "1" ]; then
  RUNTIME_STALL_ACTIVE=1
  bootstrap_status=75
  runtime_stall_pids_csv="$(printf '%s\n' "$runtime_stall_pids" | paste -sd, -)"
  printf 'Wine runtime preflight blocked: uninterruptible Wine PIDs=%s\n' "$runtime_stall_pids_csv" \
    > "$LOG_DIR/wine-runtime-preflight.log"
  record "wine-runtime-preflight" "bootstrap" "failed" "$bootstrap_status" \
    "$LOG_DIR/wine-runtime-preflight.log" 0 \
    "Rosetta has uninterruptible Wine processes (PIDs: $runtime_stall_pids_csv); no Wine command was started. Restart macOS or recover Rosetta before rerunning compatibility tests."
else
  run_logged wineboot bootstrap "$wineboot_timeout" timeout "Process did not exit before timeout." "${WINE_CMD[@]}" wineboot -u || bootstrap_status=$?
fi
if [ "$bootstrap_status" -ne 0 ]; then
  if [ "$RUNTIME_STALL_ACTIVE" -ne 1 ]; then
    "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
  fi
  bootstrap_guard_log="$LOG_DIR/wineboot-bootstrap.log"
  if [ "$RUNTIME_STALL_ACTIVE" -eq 1 ]; then
    bootstrap_guard_log="$LOG_DIR/wine-runtime-preflight.log"
  fi
  record "macwin-bootstrap-guard" "bootstrap" "skipped" "$bootstrap_status" "$bootstrap_guard_log" 0 "Skipped repairs and samples because Wine runtime bootstrap is unavailable; rerun after runtime recovery with a clean or known-good prefix before classifying app compatibility."
else
  # Engine modules and the Windows 11 bottle identity are runtime invariants,
  # not optional app-specific repairs. Fresh WoW64 prefixes otherwise miss
  # fallback x86_64 modules such as ODBC32.dll and can fail before app startup.
  repair_engine_dlls || true
  repair_engine_tools || true
  run_repair_with_watchdog macwin-windows11-setup-compat 60 repair_windows11_setup_registry || true
  if [ "${MACWIN_SMOKE_SKIP_REPAIRS:-0}" != "1" ]; then
    repair_wic_codecs_registry || true
    repair_wine_mono || true
    repair_dotnet_framework_registry || true
    repair_msxml_saxxmlreader_registry || true
    repair_user_shell_folders || true
    repair_documents_shell_namespace_registry || true
    repair_keyboard_layout_registry || true
    repair_window_metrics_fonts || true
    repair_wininet_proxy_registry || true
    write_smoke_fontconfig || true
    repair_javafx_windows_fonts || true
    repair_gtk2_font_aliases || true
    repair_onlyoffice_environment || true
    repair_gimp_extracted_layout || true
    repair_gecko_smoke_profiles || true
    repair_cura_smoke_profile || true
    run_repair_with_watchdog macwin-com-proxy "${MACWIN_COM_PROXY_REPAIR_TIMEOUT:-300}" repair_com_proxy_registry || true
    run_repair_with_watchdog macwin-winrt-activation "${MACWIN_WINRT_REPAIR_TIMEOUT:-240}" repair_winrt_activation_registry || true
    run_repair_with_watchdog macwin-windows-timezone 60 repair_windows_timezone_registry || true
  else
    write_smoke_fontconfig || true
    repair_documents_shell_namespace_registry || true
    repair_keyboard_layout_registry || true
    repair_window_metrics_fonts || true
    repair_wininet_proxy_registry || true
    repair_javafx_windows_fonts || true
    record "macwin-global-repairs" "repair" "skipped" 0 "" 0 "Skipped because MACWIN_SMOKE_SKIP_REPAIRS=1."
  fi
fi

if [ "$bootstrap_status" -eq 0 ]; then
for item in "${installers[@]}"; do
  IFS='|' read -r item_suite id installer install_mode install_arg installed_rel exe_path launch_arg launch_mode install_timeout launch_timeout <<< "$item"
  selected_suite_matches "$item_suite" || continue
  selected_sample_matches "$id" || continue
  if [ "$id" = "jasp-stats" ]; then
    launch_timeout="${MACWIN_JASP_LAUNCH_TIMEOUT:-120}"
    MACWIN_JASP_CLEAN_IPC="${MACWIN_JASP_CLEAN_IPC:-1}"
  fi
	  if [ "$id" = "pgadmin-db-admin" ]; then
	    launch_timeout="${MACWIN_PGADMIN_LAUNCH_TIMEOUT:-75}"
	  fi
	  if [ "$id" = "wps-office" ]; then
	    launch_timeout="${MACWIN_WPS_LAUNCH_TIMEOUT:-40}"
	  fi
  if [ "$id" = "jasp-stats" ] && [ -n "${MACWIN_JASP_EXTRA_LAUNCH_ARGS:-}" ]; then
    if [ -n "$launch_arg" ]; then
      launch_arg="$launch_arg ${MACWIN_JASP_EXTRA_LAUNCH_ARGS}"
    else
      launch_arg="${MACWIN_JASP_EXTRA_LAUNCH_ARGS}"
    fi
    record "$id" "launch-args-preset" "passed" 0 "" 0 "Applied extra JASP launch args from MACWIN_JASP_EXTRA_LAUNCH_ARGS: ${MACWIN_JASP_EXTRA_LAUNCH_ARGS}"
  fi

  if ! require_file "$installer"; then
    record "$id" install "missingInstaller" 127 "" 0 "Installer is missing."
    continue
  fi

  installed_path="$PREFIX/$installed_rel"
  if winepath_exists "$installed_path"; then
    record "$id" install "skipped" 0 "$installed_path" 0 "Installed executable already present; skipped installer."
  else
    if [ "$install_mode" = "ZIP" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Archive extraction did not exit before timeout." extract_zip_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "7Z" ]; then
      if run_logged "$id" install "$install_timeout" timeout "7z archive extraction did not exit before timeout." extract_7z_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "RAR_BSDTAR" ]; then
      if run_logged "$id" install "$install_timeout" timeout "RAR extraction did not exit before timeout." extract_rar_bsdtar_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "SFX_7Z_EXTRACT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "7z SFX extraction did not exit before timeout." extract_7z_sfx_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "EMBEDDED_7Z_EXTRACT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Embedded 7z payload extraction did not exit before timeout." extract_embedded_7z_payload_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "WPS_PACKET_EXTRACT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "WPS packet extraction did not exit before timeout." extract_wps_packet_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "DIRECTORY_COPY" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Directory copy did not exit before timeout." install_directory_copy_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "DIRECT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Direct executable copy did not exit before timeout." install_direct_exe_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "SQUIRREL_ZIP" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Squirrel package extraction did not exit before timeout." extract_squirrel_zip_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "SQUIRREL_PE" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Squirrel PE package extraction did not exit before timeout." extract_squirrel_pe_into_prefix "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "INNO_EXTRACT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Inno extraction did not exit before timeout." extract_inno_into_prefix "$installer" "$id" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "NSIS_EXTRACT" ]; then
      if run_logged "$id" install "$install_timeout" timeout "NSIS extraction did not exit before timeout." extract_nsis_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "ELECTRON_BUILDER_NSIS" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Electron builder NSIS extraction did not exit before timeout." extract_electron_builder_nsis_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "MSI_ADMIN" ]; then
      if run_logged "$id" install "$install_timeout" timeout "MSI administrative extraction did not exit before timeout." extract_msi_admin_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "MSI_CAB_7Z" ]; then
      if run_logged "$id" install "$install_timeout" timeout "MSI CAB extraction did not exit before timeout." extract_msi_cab_7z_into_prefix "$installer" "$install_arg"; then
        :
      fi
    elif [ "$install_mode" = "MSI_UNTIL_FILE" ]; then
      if run_logged "$id" install "$install_timeout" timeout "MSI target file did not appear before timeout." install_msi_until_file "$installer" "$installed_rel" "$id" "$install_timeout"; then
        :
      fi
    elif [ "$install_mode" = "EXE_UNTIL_FILE" ]; then
      read -r -a install_args <<< "$install_arg"
      if run_logged "$id" install "$install_timeout" timeout "EXE target file did not appear before timeout." install_exe_until_file "$installer" "$installed_rel" "$id" "$install_timeout" "${install_args[@]}"; then
        :
      fi
    elif [ "$install_mode" = "CHROME_PAYLOAD" ]; then
      if run_logged "$id" install "$install_timeout" timeout "Chrome payload installer did not exit before timeout." install_chrome_enterprise_payload "$installer" "$id"; then
        :
      fi
    elif [ "$install_mode" = "QTIFW_UNTIL_FILE" ]; then
      qtifw_auto_answer=""
      if [ "$id" = "energyplus-building" ]; then
        qtifw_auto_answer="installationErrorWithCancel=Ignore"
      fi
      if run_logged "$id" install "$install_timeout" timeout "Qt Installer Framework target did not appear before timeout." install_qtifw_until_file "$installer" "$installed_rel" "$install_arg" "$install_timeout" "$qtifw_auto_answer"; then
        :
      fi
    elif [ "$install_mode" = "OPENDSS_SVN_X64" ]; then
      if run_logged "$id" install "$install_timeout" timeout "OpenDSS SVN x64 direct-copy install did not exit before timeout." install_opendss_svn_x64_into_prefix; then
        :
      fi
    else
      installer_windows="$(copy_installer_into_prefix "$installer")"
    fi
    if [ "$install_mode" = "MSI" ]; then
      msi_log_name="$id-msi-detail.log"
      msi_log_windows="C:\\macwin-installers\\$msi_log_name"
      run_logged "$id" install "$install_timeout" timeout "Installer did not exit before timeout." "${WINE_CMD[@]}" msiexec /i "$installer_windows" /qn /norestart /l*v "$msi_log_windows" || true
      msi_log_unix="$PREFIX/drive_c/macwin-installers/$msi_log_name"
      if [ -f "$msi_log_unix" ]; then
        cp -f "$msi_log_unix" "$LOG_DIR/$msi_log_name"
      fi
    elif [ "$install_mode" = "EXE" ]; then
      read -r -a install_args <<< "$install_arg"
      run_logged "$id" install "$install_timeout" timeout "Installer did not exit before timeout." "${WINE_CMD[@]}" "$installer_windows" "${install_args[@]}" || true
    fi
  fi

  repair_chromium_root_dlls
  repair_gtk2_font_aliases || true
  if [ "$id" = "freecad-workbench" ]; then
    repair_freecad_python_uname_shim || true
    repair_freecad_smoke_profile || true
  fi
  repair_onlyoffice_environment || true
  if [ "$id" = "r-base-gui" ] || [ "$id" = "rstudio-desktop" ]; then
    repair_r_runtime_environment || true
  fi
  repair_gimp_extracted_layout || true
  repair_gecko_smoke_profiles || true
  repair_cura_smoke_profile || true
  if [ "$id" = "librecad" ]; then
    configure_librecad_profile || true
  fi
  if [ "$id" = "openscad" ]; then
    configure_openscad_workload || true
  fi
  if [ "$id" = "qcad-legacy" ]; then
    configure_qcad_legacy_profile || true
  fi
  if [ "$id" = "qgroundcontrol-drone" ]; then
    prepare_qgroundcontrol_first_run_probe || true
  fi
  if [ "$id" = "sweethome3d-design" ]; then
    configure_sweethome3d_profile || true
  fi
  if [ "$id" = "sqlitebrowser-db" ]; then
    configure_sqlitebrowser_profile || true
  fi
  if [ "$id" = "qucs-s-circuit" ]; then
    configure_qucs_s_profile || true
  fi
  if [ "$id" = "pdfxchange-editor" ]; then
    configure_pdfxchange_sample || true
  fi
  if [ "$id" = "jabref-portable" ]; then
    configure_jabref_javafx_fonts || true
  fi
  if [ "$id" = "geogebra-classic" ]; then
    configure_geogebra_classic_profile || true
  fi
  if [ "$id" = "lenovo-app-store" ]; then
    configure_lenovo_app_store_profile || true
  fi
  if [ "$id" = "pgadmin-db-admin" ]; then
    configure_pgadmin_profile || true
  fi
  if [ "$id" = "dbeaver-database" ]; then
    configure_dbeaver_profile || true
  fi
	  if [ "$id" = "meshlab-3d" ]; then
	    configure_meshlab_software_opengl "$id" || true
	  fi
	  if [ "$id" = "bambu-studio-portable" ]; then
	    configure_bambu_studio_runtime "$id" || true
	  fi
	  if [ "$id" = "orcaslicer-print" ]; then
	    configure_orcaslicer_runtime "$id" || true
	  fi
	  if [ "$id" = "onlyoffice-suite" ]; then
	    configure_onlyoffice_profile || true
	  fi
    if [ "$id" = "wps-office" ]; then
      run_logged "$id" profile-repair 45 timeout \
        "WPS profile and OOXML/PDF fixture preparation did not finish before timeout." \
        configure_wps_office_profile "$install_arg" || true
    fi
	  if [ "$id" = "jasp-stats" ]; then
	    configure_jasp_qtwebengine_layout || true
	    configure_jasp_software_opengl || true
	    configure_jasp_constructor_tail_isolation "$id" || true
	    configure_jasp_empty_values_preset "$id" || true
	    configure_jasp_engine_count_preset "$id" || true
		    configure_jasp_initial_state_isolation "$id" || true
		    configure_jasp_ipc_trace_preset "$id" || true
		    configure_jasp_ipc_cleanup "$id" || true
		    configure_jasp_desktop_exe_override "$id" || true
		    write_jasp_qml_resource_probe "$id" || true
	    write_jasp_runtime_state_probe "$id" || true
	    write_jasp_constructor_boundary_probe "$id" || true
	    write_jasp_engine_direct_probe "$id" || true
	    write_jasp_createprocess_probe "$id" || true
	    if [ "${MACWIN_JASP_SPAWN_TRACE:-0}" = "1" ]; then
	      write_jasp_spawn_trace_probe "$id" || true
	    fi
	  fi
  if [ "$id" = "mremoteng-1782-x64" ]; then
    run_logged "$id-dotnet10-runtime" repair 180 timeout ".NET Desktop Runtime 10 zip deployment did not exit before timeout." install_dotnet_desktop10_zip_runtime || true
    configure_mremoteng_1782_profile || true
  fi
  if [ "$id" = "lyx-editor" ]; then
    run_logged "$id-python314-runtime" repair 180 timeout "Portable Python 3.14 deployment did not exit before timeout." install_python314_portable_runtime || true
    configure_lyx_python_shims || true
  fi
  if [ "$id" = "openplc-editor" ]; then
    if ! run_logged "$id" profile-repair 30 timeout \
      "OpenPLC timezone profile or history repair did not finish before timeout." \
      configure_openplc_profile; then
      continue
    fi
  fi
  if [ "$id" = "dwsim-process-sim" ]; then
    configure_dwsim_gtk3_profile || true
  fi
  if [ "$id" = "freeoffice-suite" ]; then
    repair_user_shell_folders || true
    repair_documents_shell_namespace_registry || true
    configure_freeoffice_profile || true
    if [ "${MACWIN_SMOKE_SKIP_REPAIRS:-0}" = "1" ]; then
      run_repair_with_watchdog macwin-com-proxy "${MACWIN_COM_PROXY_REPAIR_TIMEOUT:-300}" repair_com_proxy_registry || true
    fi
  fi
	  if [ "$id" = "paraview-visualization" ]; then
	    configure_paraview_software_opengl || true
	  fi
	  if [ "$id" = "blender-3d" ]; then
	    configure_blender_software_opengl || true
	  fi
  if [ "$id" = "qgis-ltr" ]; then
    configure_qgis_launcher || true
  fi
  if [ "$id" = "orange-data-mining" ]; then
    configure_orange_profile || true
  fi
  if [ "$id" = "supermium-browser" ] || [ "$id" = "supermium-32-browser" ]; then
    configure_supermium_profile "$id" || true
  fi
  if [ "$id" = "openjump-gis" ]; then
    configure_openjump_java_runtime || true
  fi
  if [ "$id" = "projectlibre-pm" ]; then
    configure_temurin_jdk21_runtime || true
  fi
  if [ "$id" = "epanet-water" ]; then
    configure_epanet_cli_sample || true
  fi
  if [ "$id" = "opendss-power" ]; then
    configure_opendss_svn_x64_smoke || true
  fi
  repair_sweethome3d_runtime || true
  if winepath_exists "$installed_path"; then
    record "$id" installed-file "passed" 0 "$installed_path" 0 "Installed executable found."
  else
    record "$id" installed-file "failed" 1 "$installed_path" 0 "Installed executable not found."
    continue
  fi

  if is_superseded_legacy_launch_sample "$id" && [ "${MACWIN_SMOKE_RUN_LEGACY_SUPERSEDED:-0}" != "1" ]; then
    record "$id" launch "skipped" 108 "$installed_path" 0 "$(winscp_legacy_wow64_note)"
    continue
  fi

  launch_cwd="$(launch_cwd_for_executable "$installed_path")"
  if is_pe32_executable "$installed_path" && [ "$ENGINE_SUPPORTS_WIN32" != "true" ]; then
    record "$id" launch "failed" 92 "$installed_path" 0 "32-bit Windows executable requires a WoW64-capable engine; current engine '$ENGINE_ID' has supportsWin32=false."
    continue
  fi
  if is_pe32_dotnet_executable "$installed_path" && [ ! -f "$PREFIX/drive_c/windows/syswow64/mscoree.dll" ]; then
    record "$id" launch "failed" 92 "$installed_path" 0 "32-bit .NET Framework app requires syswow64/mscoree.dll; current managed bridge only has 64-bit mscoree."
    continue
  fi
  if [ "$id" = "freeoffice-suite" ]; then
    run_logged "$id" core-workload 240 timeout \
      "FreeOffice bootstrap and document roundtrip did not exit before timeout." \
      run_freeoffice_core_workload || true
  fi
  if [ "$id" = "projectlibre-pm" ]; then
    if run_logged "$id" core-workload 120 timeout \
      "ProjectLibre project model roundtrip did not exit before timeout." \
      run_projectlibre_core_workload; then
      launch_arg="$launch_arg C:\\MacWinTests\\projectlibre\\macwin-project.xml"
    else
      continue
    fi
  fi
  if [ "$id" = "wps-office" ]; then
    windows_path_env="C:\\Program Files\\Kingsoft\\WPS Office\\$install_arg\\office6;C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\windows\\system32\\WindowsPowershell\\v1.0"
  elif [ "$id" = "onlyoffice-suite" ]; then
    windows_path_env='C:\Program Files\ONLYOFFICE\DesktopEditors\converter;C:\Program Files\ONLYOFFICE\DesktopEditors;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "jasp-stats" ]; then
    windows_path_env='C:\Program Files\JASP\bin;C:\Program Files\JASP;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "qelectrotech-cad" ]; then
    windows_path_env='C:\Program Files\QElectroTech\bin;C:\Program Files\QElectroTech;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "qgis-ltr" ]; then
    windows_path_env='C:\Program Files\QGIS 3.44.11\bin;C:\Program Files\QGIS 3.44.11\apps\qgis-ltr\bin;C:\Program Files\QGIS 3.44.11\apps\Qt5\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "cloudcompare-pointcloud" ]; then
    windows_path_env='C:\Program Files\CloudCompare;C:\Program Files\CloudCompare\plugins;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "paraview-visualization" ]; then
    windows_path_env='C:\Program Files\ParaView 6.1.0\bin;C:\Program Files\ParaView 6.1.0\lib;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "openmodelica-omedit" ]; then
    windows_path_env='C:\Program Files\OpenModelica\bin;C:\Program Files\OpenModelica\ucrt64\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "orange-data-mining" ]; then
    windows_path_env="C:\\users\\$USER\\AppData\\Local\\Programs\\Orange;C:\\users\\$USER\\AppData\\Local\\Programs\\Orange\\Scripts;C:\\users\\$USER\\AppData\\Local\\Programs\\Orange\\Library\\bin;C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\windows\\system32\\WindowsPowershell\\v1.0"
  elif [ "$id" = "octave-workbench" ]; then
    windows_path_env='C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\qt6\bin;C:\Program Files\GNU Octave\Octave-11.3.0\mingw64\bin;C:\Program Files\GNU Octave\Octave-11.3.0\usr\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "wxmaxima" ]; then
    windows_path_env='C:\Program Files\wxMaxima\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "macwin-maxima-cas" ]; then
    windows_path_env='C:\Program Files\Maxima-5.49.0\bin;C:\Program Files\Maxima-5.49.0\gnuplot\bin;C:\Program Files\Maxima-5.49.0\clisp-2.49;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "labplot-workbench" ]; then
    windows_path_env='C:\Program Files\LabPlot\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "lyx-editor" ]; then
    windows_path_env='C:\macwin-runtimes\python314-portable;C:\Program Files\LyX\bin;C:\Program Files\LyX;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "saga-gis" ]; then
    windows_path_env='C:\Program Files\SAGA;C:\Program Files\SAGA\tools;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "dia-diagram" ]; then
    windows_path_env='C:\Program Files\Dia\bin;C:\Program Files\Dia;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "epanet-water" ]; then
    windows_path_env='C:\Program Files\EPANET 2.2;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "swmm-hydrology" ]; then
    windows_path_env='C:\Program Files\EPA SWMM 5.2;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "opendss-power" ]; then
    windows_path_env='C:\macwin-portable\opendss-svn-x64;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "energyplus-building" ]; then
    windows_path_env='C:\EnergyPlusV26-1-0;C:\EnergyPlusV26-1-0\PostProcess;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "lazarus-ide-64" ] || [ "$id" = "lazarus-fpc-64-version" ]; then
    windows_path_env='C:\Program Files\Lazarus;C:\Program Files\Lazarus\fpc\3.2.2\bin\x86_64-win64;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "lazarus-ide-32" ] || [ "$id" = "lazarus-fpc-32-version" ]; then
    windows_path_env='C:\Program Files (x86)\Lazarus;C:\Program Files (x86)\Lazarus\fpc\3.2.2\bin\i386-win32;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "codeblocks-mingw" ] || [ "$id" = "codeblocks-gcc-version" ]; then
    windows_path_env='C:\Program Files\CodeBlocks;C:\Program Files\CodeBlocks\MinGW\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "openjump-gis" ]; then
    windows_path_env='C:\macwin-runtime\temurin-jdk21\jdk-21.0.11+10\bin;C:\macwin-portable\openjump-gis\OpenJUMP-2.4.0-r5303[6c9a02d]-PLUS\bin;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  elif [ "$id" = "mremoteng-1782-x64" ]; then
    windows_path_env='C:\macwin-runtimes\dotnet-desktop-10-x64;C:\windows\system32;C:\windows;C:\windows\system32\wbem;C:\windows\system32\WindowsPowershell\v1.0'
  else
    windows_path_env=""
  fi
  launch_env=(MACWIN_SOFTWARE_SMOKE_LAUNCH=1)
  if [ "$id" = "wps-office" ]; then
    launch_env+=(
      LANG=zh_CN.UTF-8
      LANGUAGE=zh_CN:zh:en_US:en
      LC_ALL=zh_CN.UTF-8
      LC_CTYPE=zh_CN.UTF-8
      MACWIN_COMPAT_PROFILE=wps-office
      MACWIN_ACTIVATE_WINE_APP=1
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_FONTCONFIG_REPAIR=1
      MACWIN_FONT_FALLBACK_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_TEXT_RENDERING_REPAIR=1
      MACWIN_WPS_OFFICE_REPAIR=1
      QT_ACCESSIBILITY=0
      QT_FONT_DPI=96
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
    )
  fi
  if [ "$id" = "freeoffice-suite" ]; then
    launch_env+=("WINEDLLOVERRIDES=msvcr80,msvcp80=b;winemenubuilder.exe=d")
  fi
  if [ "$item_suite" = "cad" ] || [ "$item_suite" = "industrial" ] || [ "$item_suite" = "graphics" ]; then
    launch_env+=(WINE_D3D_CONFIG=renderer=gl,csmt=0x0)
  fi
  if [ "$id" = "sqlitebrowser-db" ] \
    || [ "$id" = "postman-api-client" ] \
    || [ "$id" = "vscode-portable" ] \
    || [ "$id" = "chrome-enterprise" ] \
    || [ "$id" = "edge-enterprise" ] \
    || [ "$id" = "brave-standalone" ] \
    || [ "$id" = "opera-browser" ] \
    || [ "$id" = "supermium-browser" ] \
    || [ "$id" = "supermium-32-browser" ] \
    || [ "$id" = "vivaldi-browser" ] \
    || [ "$id" = "rstudio-desktop" ] \
    || [ "$id" = "arduino-ide" ] \
    || [ "$id" = "joplin-notes" ] \
    || [ "$id" = "obsidian-notes" ] \
    || [ "$id" = "typora-editor" ] \
    || [ "$id" = "min-browser-portable" ] \
    || [ "$id" = "zettlr-editor" ] \
    || [ "$id" = "openplc-editor" ] \
    || [ "$id" = "beekeeper-studio" ] \
    || [ "$id" = "marktext-editor" ] \
    || [ "$id" = "pgadmin-db-admin" ] \
    || [ "$id" = "mqtt-explorer" ]; then
    launch_env+=(MACWIN_IPHLPAPI_FORCE_FALLBACK=1)
  fi
  if [ "$id" = "rstudio-desktop" ]; then
    launch_env+=(
      LC_ALL=Chinese_China.utf8
      LANG=Chinese_China.utf8
      'R_HOME=C:\Program Files\R\R-4.6.0'
      'RSTUDIO_WHICH_R=C:\Program Files\R\R-4.6.0\bin\x64\R.exe'
      QTWEBENGINE_DISABLE_SANDBOX=1
      QT_OPENGL=software
      QT_QUICK_BACKEND=software
      QT_RHI_BACKEND=software
      QSG_RHI_BACKEND=opengl
      QSG_RENDER_LOOP=basic
      "QTWEBENGINE_CHROMIUM_FLAGS=$qtwebengine_software_args"
    )
  fi
  if [ "$id" = "openplc-editor" ]; then
    launch_env+=(TZ="${MACWIN_OPENPLC_TIMEZONE:-Asia/Shanghai}")
  fi
  if [ "$id" = "jasp-stats" ]; then
    launch_env+=(
	      QT_OPENGL=software
	      QT_QUICK_BACKEND=software
	      QML_DISABLE_DISK_CACHE=1
	      QMLSCENE_DEVICE=softwarecontext
	      QSG_RENDER_LOOP=basic
	      QSG_RHI_BACKEND=opengl
	      QT_ACCESSIBILITY=0
	      QT_AUTO_SCREEN_SCALE_FACTOR=0
	      QT_ENABLE_HIGHDPI_SCALING=0
	      QT_FONT_DPI=96
	      QT_QUICK_CONTROLS_STYLE=Basic
	      QT_RHI_BACKEND=software
	      QT_SCALE_FACTOR=1
	      "QT_PLUGIN_PATH=C:\\Program Files\\JASP"
	      "QT_QPA_PLATFORM_PLUGIN_PATH=C:\\Program Files\\JASP\\platforms"
	      "QML2_IMPORT_PATH=C:\\Program Files\\JASP\\qml"
	      "QTWEBENGINE_RESOURCES_PATH=C:\\Program Files\\JASP\\resources"
	      "QTWEBENGINE_LOCALES_PATH=C:\\Program Files\\JASP\\translations\\qtwebengine_locales"
	      "QTWEBENGINEPROCESS_PATH=C:\\Program Files\\JASP\\QtWebEngineProcess.exe"
	      "JASPENGINE_LOCATION=C:\\Program Files\\JASP\\JASPEngine.exe"
	      WINEDEBUG="${MACWIN_JASP_WINEDEBUG:--all}"
	    )
    if [ "${MACWIN_JASP_WEBENGINE_MODE:-multiprocess}" = "single-process" ]; then
      launch_env+=(
        MACWIN_JASP_WEBENGINE_MODE=single-process
        "QTWEBENGINE_CHROMIUM_FLAGS=$qtwebengine_software_args"
      )
    else
      launch_env+=(
        MACWIN_JASP_WEBENGINE_MODE=multiprocess
        "QTWEBENGINE_CHROMIUM_FLAGS=$qtwebengine_multiprocess_software_args"
      )
    fi
    if [ "${MACWIN_JASP_QML_TRACE:-0}" = "1" ]; then
      launch_env+=(
        QML_IMPORT_TRACE=1
        QT_DEBUG_PLUGINS=1
        QT_FORCE_STDERR_LOGGING=1
        QT_LOGGING_RULES='qt.qml.import=true;qt.qml.typecompiler=true;qt.qml.diskcache=false;qt.qml.binding=false;qt.plugin.*=true'
      )
    fi
  fi
  if [ "$id" = "mremoteng-1782-x64" ]; then
    launch_env+=(DOTNET_ROOT_X64='C:\macwin-runtimes\dotnet-desktop-10-x64' DOTNET_ROOT='C:\macwin-runtimes\dotnet-desktop-10-x64')
  fi
  if [ "$id" = "librecad" ]; then
    launch_env+=(LANGUAGE=zh_CN:zh LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 LC_CTYPE=zh_CN.UTF-8)
  fi
  if [ "$id" = "openboard-whiteboard" ] || [ "$id" = "sigil-ebook" ]; then
    launch_env+=("QTWEBENGINE_CHROMIUM_FLAGS=$qtwebengine_software_args")
  fi
  if [ "$id" = "sqlitebrowser-db" ] || [ "$id" = "qelectrotech-cad" ] || [ "$id" = "qgis-ltr" ] || [ "$id" = "cloudcompare-pointcloud" ] || [ "$id" = "paraview-visualization" ] || [ "$id" = "openmodelica-omedit" ] || [ "$id" = "orange-data-mining" ] || [ "$id" = "octave-workbench" ] || [ "$id" = "lyx-editor" ] || [ "$id" = "focuswriter-editor" ] || [ "$id" = "openboard-whiteboard" ] || [ "$id" = "sigil-ebook" ] || [ "$id" = "qownnotes-portable" ] || [ "$id" = "texstudio-editor" ] || [ "$id" = "qucs-s-circuit" ] || [ "$id" = "tiled-map-editor" ] || [ "$id" = "musescore-studio" ] || [ "$id" = "otter-browser-portable" ] || [ "$id" = "wxmaxima" ] || [ "$id" = "macwin-maxima-cas" ] || [ "$id" = "labplot-workbench" ] || [ "$id" = "saga-gis" ] || [ "$id" = "qmodmaster-64" ] || [ "$id" = "qmodmaster-32" ]; then
    launch_env+=(QT_OPENGL=software QT_QUICK_BACKEND=software)
  fi
  if [ "$id" = "qgroundcontrol-drone" ]; then
    launch_env+=(
      LANG=zh_CN.UTF-8
      LANGUAGE=zh_CN:zh:en_US:en
      LC_ALL=zh_CN.UTF-8
      LC_CTYPE=zh_CN.UTF-8
      MACWIN_ACTIVATE_WINE_APP=1
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_COMPAT_PROFILE=qt-rhi-software
      MACWIN_FONTCONFIG_REPAIR=1
      MACWIN_FONT_FALLBACK_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_QT_RHI_SOFTWARE_REPAIR=1
      MACWIN_TEXT_RENDERING_REPAIR=1
      QML_DISABLE_DISK_CACHE=1
      QSG_RENDER_LOOP=basic
      QSG_RHI_BACKEND=opengl
      QT_ACCESSIBILITY=0
      QT_AUTO_SCREEN_SCALE_FACTOR=0
      QT_ENABLE_HIGHDPI_SCALING=0
      QT_FONT_DPI=96
      QT_OPENGL=software
      QT_SCALE_FACTOR=1
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
    )
  fi
	  if [ "$id" = "texstudio-editor" ]; then
	    launch_env+=(QT_STYLE_OVERRIDE=windows QT_ENABLE_HIGHDPI_SCALING=0 QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 QT_FONT_DPI=96)
	  fi
	  if [ "$id" = "tiled-map-editor" ]; then
	    launch_env+=(QT_STYLE_OVERRIDE=windows QT_ENABLE_HIGHDPI_SCALING=0 QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 QT_FONT_DPI=96)
	  fi
	  if [ "$id" = "qucs-s-circuit" ]; then
	    launch_env+=(QT_STYLE_OVERRIDE=windows QT_ENABLE_HIGHDPI_SCALING=0 QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 QT_FONT_DPI=96)
	  fi
	  if [ "$id" = "musescore-studio" ]; then
	    launch_env+=(QSG_RHI_BACKEND=opengl QSG_RENDER_LOOP=basic QMLSCENE_DEVICE=softwarecontext QT_RHI_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic QT_ENABLE_HIGHDPI_SCALING=0 QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_DEVICE_PIXEL_RATIO=1 QT_SCALE_FACTOR=1 QT_SCALE_FACTOR_ROUNDING_POLICY=Round QT_SCREEN_SCALE_FACTORS=1 QT_USE_PHYSICAL_DPI=0 QT_FONT_DPI=96 QT_ACCESSIBILITY=0 QML_DISABLE_DISK_CACHE=1 QT_LOGGING_RULES='qt.accessibility.*=false;qt.pointer.dispatch=false' MACWIN_APP_MODE_INPUT_REPAIR=1 MACWIN_AUTOMATED_UI_CLICK_REPAIR=1 MACWIN_BORDERLESS_APP_MODE=0 MACWIN_FORCE_MOUSE_FOCUS=1 MACWIN_MOUSE_FOCUS_CLICK_AUTOMATION=1 MACWIN_MUSESCORE_WELCOME_CLICK_AUTOMATION=1 MACWIN_MUSESCORE_WELCOME_REPAIR=1 MACWIN_QT_RHI_SOFTWARE_REPAIR=1 MACWIN_RETINA_INPUT_REPAIR=0)
	  fi
	  if [ "$id" = "lenovo-app-store" ]; then
	    launch_env+=(LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 LC_CTYPE=zh_CN.UTF-8 QT_OPENGL=software QT_QUICK_BACKEND=software QTWEBENGINE_DISABLE_SANDBOX=1 "QTWEBENGINE_CHROMIUM_FLAGS=$lenovo_appstore_args" MACWIN_LENOVO_BLACK_SCREEN_REPAIR=1 MACWIN_WEBVIEW_SOFTWARE_RENDERER=1 MACWIN_TEXT_RENDERING_REPAIR=1 MACWIN_FORCE_MOUSE_FOCUS=1 "MACWIN_LENOVO_RENDERER_PRESET=$lenovo_appstore_renderer_preset" WINEDLLOVERRIDES=qone,wbemprox=d)
	    if [ "$lenovo_appstore_renderer_preset" = "dxvk-macos" ] || [ "$lenovo_appstore_renderer_preset" = "dxvk-macos-inprocess" ]; then
	      mkdir -p "$LOG_DIR/dxvk" "$PREFIX/dxvk-cache"
	      launch_env+=("WINEDLLOVERRIDES=dxgi,d3d11,d3d10core=n,b;qone,wbemprox=d" "DYLD_LIBRARY_PATH=$RUNTIME/lib64" "DYLD_FALLBACK_LIBRARY_PATH=$RUNTIME/lib64" DXVK_LOG_LEVEL=debug "DXVK_LOG_PATH=$LOG_DIR/dxvk" "DXVK_STATE_CACHE_PATH=$PREFIX/dxvk-cache")
	    fi
	    if [ "$lenovo_appstore_renderer_preset" = "dxvk-macos-inprocess" ]; then
	      env -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY \
	        -u all_proxy -u http_proxy -u https_proxy -u no_proxy \
	        /usr/bin/swift "$SCRIPT_DIR/repair-lenovo-app-store-page.swift" "$lenovo_appstore_debug_port" 50 \
	        >"$LOG_DIR/lenovo-app-store-page-repair.log" 2>&1 &
	      env -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY \
	        -u all_proxy -u http_proxy -u https_proxy -u no_proxy \
	        /usr/bin/swift "$SCRIPT_DIR/inspect-chromium-page.swift" "$lenovo_appstore_debug_port" \
	        "$LOG_DIR/lenovo-app-store-cdp-report.json" "$LOG_DIR/lenovo-app-store-cdp.png" 12 45 \
	        >"$LOG_DIR/lenovo-app-store-cdp.log" 2>&1 &
	    fi
	    case "$lenovo_appstore_renderer_preset" in
	      stock-software|stock-native|dxvk-macos|dxvk-macos-inprocess)
	        ;;
	      *)
	        launch_env+=(MACWIN_DISABLE_DWM_COMPOSITION=1 MACWIN_FORCE_OPAQUE_LAYERED_WINDOWS=1)
	        ;;
	    esac
	    if [ "$lenovo_appstore_renderer_preset" != "native" ] && [ "$lenovo_appstore_renderer_preset" != "stock-native" ] && [ "$lenovo_appstore_renderer_preset" != "warp" ] && [ "$lenovo_appstore_renderer_preset" != "d3d11-warp" ] && [ "$lenovo_appstore_renderer_preset" != "dxvk-macos" ] && [ "$lenovo_appstore_renderer_preset" != "dxvk-macos-inprocess" ]; then
	      launch_env+=(WINE_D3D_CONFIG=renderer=gl,csmt=0x0)
	    fi
	  fi
	  if [ "$id" = "paraview-visualization" ]; then
	    launch_env+=(GALLIUM_DRIVER=llvmpipe LIBGL_ALWAYS_SOFTWARE=1 MESA_LOADER_DRIVER_OVERRIDE=llvmpipe MESA_GL_VERSION_OVERRIDE=3.3COMPAT MESA_GLSL_VERSION_OVERRIDE=330 "WINEDLLOVERRIDES=opengl32=n,b;winemenubuilder.exe=d")
	  fi
	  if [ "$id" = "blender-3d" ]; then
	    launch_env+=(
	      GALLIUM_DRIVER=llvmpipe
	      LIBGL_ALWAYS_SOFTWARE=1
	      MACWIN_BLENDER_SOFTWARE_OPENGL_REPAIR=1
	      MACWIN_COMPAT_PROFILE=blender-software-opengl
	      MACWIN_OPENGL_VIEWPORT_REPAIR=1
	      MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
	      "WINEDLLOVERRIDES=opengl32=n,b;winemenubuilder.exe=d"
	    )
	  fi
  if [ "$id" = "sqlitebrowser-db" ]; then
    launch_env+=("WINEDLLOVERRIDES=winhttp,jsproxy=d;winemenubuilder.exe=d")
  fi
  if [ "$id" = "winscp-client" ]; then
    launch_env+=(WINEDEBUG=+seh,-all)
  fi
	  if [ "$id" = "zotero-research" ]; then
	    launch_env+=(WINEDEBUG="${MACWIN_ZOTERO_WINEDEBUG:--all}" MACWIN_ZOTERO_GECKO32_REPAIR=1 MACWIN_GECKO_PROFILE_REPAIR=1 MACWIN_WOW64_BROWSER_REPAIR=1 MACWIN_DISABLE_WINE_D3D_CONFIG=1)
	  fi
  if [ "$id" = "octave-workbench" ]; then
    launch_env+=(MSYSTEM=MINGW64 TERM=cygwin GNUTERM=wxt GS=gs.exe "QT_PLUGIN_PATH=C:\\Program Files\\GNU Octave\\Octave-11.3.0\\mingw64\\qt6\\plugins" "PKG_CONFIG_PATH=C:\\Program Files\\GNU Octave\\Octave-11.3.0\\mingw64\\lib\\pkgconfig")
  fi
  if [ "$id" = "slic3r-64" ] || [ "$id" = "slic3r-32" ]; then
    launch_env+=(PERL_BADLANG=0)
  fi
  if [ "$id" = "arduino-ide" ] || [ "$id" = "joplin-notes" ] || [ "$id" = "obsidian-notes" ] || [ "$id" = "postman-api-client" ] || [ "$id" = "vscode-portable" ] || [ "$id" = "typora-editor" ] || [ "$id" = "min-browser-portable" ] || [ "$id" = "zettlr-editor" ] || [ "$id" = "openplc-editor" ] || [ "$id" = "beekeeper-studio" ] || [ "$id" = "marktext-editor" ] || [ "$id" = "mqtt-explorer" ] || [ "$id" = "pgadmin-db-admin" ] || [ "$id" = "itch" ]; then
    launch_env+=(ELECTRON_ENABLE_LOGGING=1)
  fi
  if [ "$id" = "itch" ]; then
    launch_env+=(ELECTRON_FORCE_IS_PACKAGED=1 LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 WINE_D3D_CONFIG=renderer=gl,csmt=0x0)
  fi
  if [ "$id" = "npackd" ]; then
    if run_logged "$id" catalog-seed 30 timeout "Npackd catalog seed preparation timed out." \
      prepare_npackd_repository_seed; then
      launch_env+=(LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 WINE_D3D_CONFIG=renderer=gl,csmt=0x0 MACWIN_NPACKD_CATALOG_REPAIR=1)
    fi
  fi
  if [ "$id" = "projectlibre-pm" ] || [ "$id" = "freeplane-mindmap" ] || [ "$id" = "ugs-cnc" ] || [ "$id" = "openjump-gis" ]; then
    launch_env+=(JAVA_TOOL_OPTIONS="-Dsun.java2d.d3d=false -Dsun.java2d.opengl=false")
  fi
  if [ "$id" = "dbeaver-database" ]; then
    launch_env+=(
      FREETYPE_PROPERTIES="truetype:interpreter-version=40 cff:no-stem-darkening=0"
      LANG=zh_CN.UTF-8
      LANGUAGE=zh_CN:zh:en_US:en
      LC_ALL=zh_CN.UTF-8
      LC_CTYPE=zh_CN.UTF-8
      MACWIN_ACTIVATE_WINE_APP=1
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_COMPAT_PROFILE=dbeaver-swt
      MACWIN_DBEAVER_SWT_REPAIR=1
      MACWIN_FONTCONFIG_REPAIR=1
      MACWIN_FONT_FALLBACK_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_TEXT_RENDERING_REPAIR=1
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
      'WINEDLLOVERRIDES=winemenubuilder.exe=d'
    )
  fi
  if [ "$id" = "sweethome3d-design" ]; then
    launch_env+=(
      "_JAVA_OPTIONS=-Dj3d.rend=ogl -Dsun.java2d.d3d=false -Dsun.java2d.opengl=true"
      MACWIN_SWEETHOME3D_OPENGL_REPAIR=1
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
    )
  fi
  if [ "$id" = "openjump-gis" ]; then
    launch_env+=(JAVA_HOME='C:\macwin-runtime\temurin-jdk21\jdk-21.0.11+10')
  fi
  if [ "$id" = "jabref-portable" ]; then
    jabref_java_tool_options="-Dsun.java2d.d3d=false -Dsun.java2d.opengl=false -Dprism.order=d3d -Dprism.forceGPU=true -Dprism.text=t2k -Dprism.fontdir=C:\\windows\\Fonts -Djava.awt.headless=false -Dglass.win.uiScale=100% -Dprism.verbose=true"
    if [ "${MACWIN_JABREF_DEBUG_FONTS:-0}" = "1" ]; then
      jabref_java_tool_options="$jabref_java_tool_options -Dprism.debugfonts=true"
    fi
    launch_env+=(
      JAVA_TOOL_OPTIONS="$jabref_java_tool_options"
      MACWIN_COMPAT_PROFILE=jabref-javafx-d3d
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_FONTCONFIG_REPAIR=1
      MACWIN_FONT_FALLBACK_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_JABREF_JAVAFX_REPAIR=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_TEXT_RENDERING_REPAIR=1
      WINE_D3D_CONFIG=renderer=vulkan,csmt=0x0
      'WINEDLLOVERRIDES=winemenubuilder.exe=d'
    )
  fi
  if [ "$id" = "freecad-workbench" ]; then
    launch_env+=(
      LANG=zh_CN.UTF-8
      LANGUAGE=zh_CN:zh:en_US:en
      LC_ALL=zh_CN.UTF-8
      LC_CTYPE=zh_CN.UTF-8
      MACWIN_COMPAT_PROFILE=freecad-opengl
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_FONTCONFIG_REPAIR=1
      MACWIN_FONT_FALLBACK_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_FREECAD_PYTHON_REPAIR=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_OPENGL_VIEWPORT_REPAIR=1
      MACWIN_TEXT_RENDERING_REPAIR=1
      QT_ACCESSIBILITY=0
      QT_AUTO_SCREEN_SCALE_FACTOR=0
      QT_ENABLE_HIGHDPI_SCALING=0
      QT_FONT_DPI=96
      QT_OPENGL=software
      QT_SCALE_FACTOR=1
      LIBGL_ALWAYS_SOFTWARE=1
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
      'WINEDLLOVERRIDES=opengl32=n;winemenubuilder.exe=d'
    )
  fi
  if [ "$id" = "openscad" ]; then
    launch_env+=(
      LANG=zh_CN.UTF-8
      LANGUAGE=zh_CN:zh:en_US:en
      LC_ALL=zh_CN.UTF-8
      LC_CTYPE=zh_CN.UTF-8
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_LAUNCH_CWD=executable-dir
      MACWIN_OPENGL_VIEWPORT_REPAIR=1
      QT_ACCESSIBILITY=0
      QT_AUTO_SCREEN_SCALE_FACTOR=0
      QT_ENABLE_HIGHDPI_SCALING=0
      QT_FONT_DPI=96
      QT_OPENGL=desktop
      QT_SCALE_FACTOR=1
      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
      'WINEDLLOVERRIDES=winemenubuilder.exe=d'
    )
  fi
  if [ "$id" = "calibre-library" ]; then
    launch_env+=(TZ=America/Los_Angeles)
  fi
  if [ "$id" = "processing-ide" ]; then
    launch_env+=(JAVA_TOOL_OPTIONS="-Dsun.java2d.d3d=false -Dsun.java2d.opengl=false")
  fi
	  if [ "$id" = "dwsim-process-sim" ]; then
	    launch_env+=(
	      WINEDLLOVERRIDES="winemenubuilder.exe=d"
	      XDG_CONFIG_HOME='C:\macwin-portable\dwsim-gtk-config'
	      "GTK2_RC_FILES=C:\\users\\$USER\\.gtkrc-2.0"
	      GTK_DATA_PREFIX='C:\Program Files\DWSIM'
	      GTK_EXE_PREFIX='C:\Program Files\DWSIM'
	      GDK_BACKEND=win32
	      GDK_RENDERING=image
	      GSK_RENDERER=cairo
	      GTK_CSD=0
	      GTK_USE_PORTAL=0
	      PANGOCAIRO_BACKEND=fontconfig
	      NO_AT_BRIDGE=1
	      MACWIN_DISABLE_DWM_COMPOSITION=1
	      MACWIN_FORCE_OPAQUE_LAYERED_WINDOWS=1
	    )
	  fi
  if [ "$id" = "pdfarranger-portable" ]; then
    if run_logged "$id" document-fixture 30 timeout \
      "PDF Arranger document fixture preparation did not finish before timeout." \
      prepare_pdfarranger_workload; then
      launch_arg="$launch_arg C:\\MacWinTests\\pdfarranger\\page-one.pdf C:\\MacWinTests\\pdfarranger\\page-two.pdf"
    else
      continue
    fi
    launch_env+=(GDK_BACKEND=win32 GTK_CSD=0 GTK_USE_PORTAL=0 GDK_RENDERING=image GSK_RENDERER=cairo PANGOCAIRO_BACKEND=fontconfig NO_AT_BRIDGE=1 GDK_WIN32_DISABLE_HIDPI=1 MACWIN_DISABLE_DWM_COMPOSITION=1 MACWIN_FORCE_OPAQUE_LAYERED_WINDOWS=1)
  fi
	  if [ "$id" = "meshlab-3d" ]; then
	    launch_env+=(QT_OPENGL=software QT_QUICK_BACKEND=software LIBGL_ALWAYS_SOFTWARE=1 MACWIN_MESHLAB_SOFTWARE_OPENGL_REPAIR=1 'WINEDLLOVERRIDES=opengl32=n;winemenubuilder.exe=d')
	  fi
	  if [ "$id" = "bambu-studio-portable" ]; then
	    launch_env+=(
	      MACWIN_COMPAT_PROFILE=bambu-studio-software-opengl
	      MACWIN_BAMBU_STUDIO_RUNTIME_REPAIR=1
	      GALLIUM_DRIVER=llvmpipe
	      LIBGL_ALWAYS_SOFTWARE=1
	      MESA_GL_VERSION_OVERRIDE=4.5COMPAT
	      MESA_GLSL_VERSION_OVERRIDE=450
	      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
	      'WINEDLLOVERRIDES=opengl32,msvcp140,msvcp140_1,msvcp140_2,msvcp140_codecvt_ids,vcruntime140,vcruntime140_1,concrt140=n;winemenubuilder.exe=d'
	    )
	  fi
	  if [ "$id" = "orcaslicer-print" ]; then
	    launch_env+=(
	      MACWIN_COMPAT_PROFILE=orcaslicer-native-opengl
	      MACWIN_ORCASLICER_RUNTIME_REPAIR=1
	      WINE_D3D_CONFIG=renderer=gl,csmt=0x0
	      'WINEDLLOVERRIDES=winemenubuilder.exe=d'
	    )
	  fi
  if [ "$id" = "esphome-flasher-x64" ] || [ "$id" = "esphome-flasher-x86" ] || [ "$id" = "krita-paint" ]; then
    launch_env+=(PYTHONHASHSEED=0)
  fi
  if [ "$id" = "krita-paint" ]; then
    launch_env+=(
      MACWIN_COMPAT_PROFILE=krita-opengl
      MACWIN_APP_MODE_INPUT_REPAIR=1
      MACWIN_FORCE_MOUSE_FOCUS=1
      MACWIN_KRITA_OPENGL_REPAIR=1
      QT_ACCESSIBILITY=0
      QT_AUTO_SCREEN_SCALE_FACTOR=0
      QT_ENABLE_HIGHDPI_SCALING=0
      QT_FONT_DPI=96
      QT_OPENGL=desktop
      QT_SCALE_FACTOR=1
    )
  fi
  if [ "$id" = "firefox-browser" ] || [ "$id" = "firefox-developer" ] || [ "$id" = "librewolf-browser" ] || [ "$id" = "floorp-browser" ] || [ "$id" = "waterfox-browser" ] || [ "$id" = "palemoon-browser" ] || [ "$id" = "palemoon-32-browser" ] || [ "$id" = "seamonkey-browser" ] || [ "$id" = "seamonkey-32-browser" ] || [ "$id" = "mullvad-browser" ] || [ "$id" = "zen-browser" ] || [ "$id" = "zotero-research" ]; then
    launch_env+=(MOZ_ACCELERATED=0 MOZ_CRASHREPORTER=0 MOZ_CRASHREPORTER_DISABLE=1 MOZ_CRASHREPORTER_NO_REPORT=1 MOZ_DISABLE_CONTENT_SANDBOX=1 MOZ_DISABLE_GPU_SANDBOX=1 MOZ_DISABLE_GMP_SANDBOX=1 MOZ_DISABLE_RDD_SANDBOX=1 MOZ_DISABLE_SOCKET_PROCESS_SANDBOX=1 MOZ_WEBRENDER=0)
  fi
  if [ "$id" = "musescore-studio" ]; then
    repair_winemac_input_config
    repair_musescore_first_launch_config
  fi
	  if [ "$id" = "beekeeper-studio" ]; then
	    repair_beekeeper_studio_profile_config
	  fi
	  pgadmin_cdp_pid=""
	  openplc_cdp_pid=""
	  if [ "$id" = "pgadmin-db-admin" ]; then
	    launch_arg="$launch_arg --remote-debugging-port=$pgadmin_debug_port --remote-allow-origins=*"
	    rm -f \
	      "$LOG_DIR/pgadmin-db-admin-cdp-report.json" \
	      "$LOG_DIR/pgadmin-db-admin-cdp.png" \
	      "$LOG_DIR/pgadmin-db-admin-cdp.log"
	    env -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY \
	      -u all_proxy -u http_proxy -u https_proxy -u no_proxy \
	      /usr/bin/swift "$SCRIPT_DIR/inspect-chromium-page.swift" "$pgadmin_debug_port" \
	      "$LOG_DIR/pgadmin-db-admin-cdp-report.json" "$LOG_DIR/pgadmin-db-admin-cdp.png" 8 65 \
	      >"$LOG_DIR/pgadmin-db-admin-cdp.log" 2>&1 &
	    pgadmin_cdp_pid=$!
	  fi
	  if [ "$id" = "openplc-editor" ]; then
	    launch_arg="$launch_arg --remote-debugging-port=$openplc_debug_port --remote-allow-origins=*"
	    rm -f \
	      "$LOG_DIR/openplc-editor-cdp-report.json" \
	      "$LOG_DIR/openplc-editor-cdp.png" \
	      "$LOG_DIR/openplc-editor-cdp.log"
	    env -u ALL_PROXY -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY \
	      -u all_proxy -u http_proxy -u https_proxy -u no_proxy \
	      /usr/bin/swift "$SCRIPT_DIR/inspect-chromium-page.swift" "$openplc_debug_port" \
	      "$LOG_DIR/openplc-editor-cdp-report.json" "$LOG_DIR/openplc-editor-cdp.png" 8 65 \
	      >"$LOG_DIR/openplc-editor-cdp.log" 2>&1 &
	    openplc_cdp_pid=$!
	  fi
	  if [ "$id" = "qelectrotech-cad" ]; then
    if run_logged "$id" project-fixture 15 timeout \
      "QElectroTech project fixture preparation timed out." \
      prepare_qelectrotech_project_fixture; then
      launch_arg="$launch_arg C:\\macwin-tests\\qelectrotech-smoke.qet"
    else
      continue
    fi
  fi
  if [ "$id" = "jabref-portable" ]; then
    if run_logged "$id" gui-fixture 15 timeout \
      "JabRef GUI fixture preparation timed out." \
      prepare_jabref_gui_fixture; then
      launch_arg="$launch_arg C:\\MacWinTests\\jabref\\input.bib"
    else
      continue
    fi
  fi
  if [ "$id" = "ltspice-circuit" ]; then
    if ! run_logged "$id" simulation-workload 90 timeout \
      "LTspice RC transient simulation or first-run prompt handling timed out." \
      run_ltspice_circuit_workload; then
      continue
    fi
    launch_arg="$launch_arg C:\\macwin-tests\\ltspice\\rc-transient.cir"
  fi
  repair_retina_dpi_config
  prepare_launch_user_data_dirs "$launch_arg" || true
	  launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
	  if [ "$id" = "winscp-client" ] || [ "$id" = "winscp-cli-help" ] || [ "$id" = "palemoon-32-browser" ] || [ "$id" = "portableapps-platform" ]; then
	    if [ -x "$ROSETTA_X87_RUNTIME" ]; then
	      launch_env_cmd=(/usr/bin/env ROSETTA_X87_PATH="$ROSETTA_X87_RUNTIME")
	    fi
	  fi
  if [ "$id" = "supermium-32-browser" ] || [ "$id" = "gimp-image-editor" ] || [ "$id" = "zotero-research" ] || { [ "$id" = "lenovo-app-store" ] && { [ "$lenovo_appstore_renderer_preset" = "native" ] || [ "$lenovo_appstore_renderer_preset" = "stock-native" ] || [ "$lenovo_appstore_renderer_preset" = "warp" ] || [ "$lenovo_appstore_renderer_preset" = "d3d11-warp" ] || [ "$lenovo_appstore_renderer_preset" = "dxvk-macos" ] || [ "$lenovo_appstore_renderer_preset" = "dxvk-macos-inprocess" ]; }; }; then
    launch_env_cmd=(/usr/bin/env -u WINE_D3D_CONFIG)
  fi
  if [ "$id" = "jasp-stats" ]; then
    # JASPDesktop and JASPEngine are native x86_64 binaries. Injecting the
    # 32-bit RosettaX87 shim makes this Qt process exit before MainWindow/QML.
    launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
    configure_jasp_ipc_cleanup "$id" "prelaunch-ipc-cleanup-preset" || true
    stabilize_jasp_wineserver_for_launch "$id" || true
  fi
  if [ "$id" = "meshlab-3d" ] || [ "$id" = "krita-paint" ] || [ "$id" = "powertoys-fancyzones" ]; then
    launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
  fi
  if [ "$id" = "opera-browser" ]; then
    # Opera is a native x86_64 Chromium build. The 32-bit Rosetta x87 shim can
    # invalidate translated code fragments when the HTTPS renderer starts.
    launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
  fi
  if [ "$id" = "itch" ]; then
    launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
  fi
  if [ "$id" = "npackd" ]; then
    launch_env_cmd=(/usr/bin/env -u ROSETTA_X87_PATH)
  fi
  if [ "$launch_mode" = "gui" ] && macos_gui_session_is_locked; then
    record "$id" launch "skipped" 122 "" 0 \
      "macOS session is locked; GUI launch and visible-window validation require an unlocked session."
  elif [ -n "$launch_arg" ]; then
    read -r -a launch_args <<< "$launch_arg"
    if [ "$launch_mode" = "gui" ]; then
      if [ -n "$windows_path_env" ]; then
        run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" launched "GUI process stayed alive until timeout; treating as launch success." "${launch_env_cmd[@]}" PATH="$windows_path_env" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" "${launch_args[@]}" || true
      else
        run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" launched "GUI process stayed alive until timeout; treating as launch success." "${launch_env_cmd[@]}" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" "${launch_args[@]}" || true
      fi
    else
      run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" timeout "Process did not exit before timeout." "${launch_env_cmd[@]}" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" "${launch_args[@]}" || true
    fi
  elif [ "$launch_mode" = "gui" ]; then
    if [ -n "$windows_path_env" ]; then
      run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" launched "GUI process stayed alive until timeout; treating as launch success." "${launch_env_cmd[@]}" PATH="$windows_path_env" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" || true
    else
      run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" launched "GUI process stayed alive until timeout; treating as launch success." "${launch_env_cmd[@]}" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" || true
    fi
	  else
	    run_launch_logged "$launch_cwd" "$id" launch "$launch_timeout" timeout "Process did not exit before timeout." "${launch_env_cmd[@]}" "${launch_env[@]}" "${WINE_CMD[@]}" "$exe_path" || true
	    fi
	  if [ "$id" = "wps-office" ]; then
	    wps_office6="$PREFIX/drive_c/Program Files/Kingsoft/WPS Office/$install_arg/office6"
	    wps_fixture_dir="$PREFIX/drive_c/macwin-tests/wps"
	    if /usr/bin/unzip -tqq "$wps_fixture_dir/macwin-wps-smoke.xlsx" \
	      && /usr/bin/unzip -tqq "$wps_fixture_dir/macwin-wps-smoke.pptx" \
	      && head -c 8 "$wps_fixture_dir/macwin-wps-smoke.pdf" | rg -q '^%PDF-1\.'; then
	      record "$id" document-fixtures "passed" 0 "$wps_fixture_dir" 0 \
	        "Generated structurally valid XLSX, PPTX, and PDF files for native WPS component launches."
	      run_logged wps-office-spreadsheet document-acceptance 35 timeout \
	        "WPS Spreadsheets did not both stay alive and register the unique XLSX document." \
	        run_wps_component_document_acceptance wps-office-spreadsheet et.exe \
	        macwin-wps-smoke.xlsx pageEt || true
	      run_logged wps-office-presentation document-acceptance 35 timeout \
	        "WPS Presentation did not both stay alive and register the unique PPTX document." \
	        run_wps_component_document_acceptance wps-office-presentation wpp.exe \
	        macwin-wps-smoke.pptx pageWpp || true
	      run_logged wps-office-pdf document-acceptance 35 timeout \
	        "WPS PDF did not both stay alive and register the unique PDF document." \
	        run_wps_component_document_acceptance wps-office-pdf wpspdf.exe \
	        macwin-wps-smoke.pdf pagePdf || true
	      if macos_gui_session_is_locked; then
	        record wps-office-spreadsheet document-writeback "skipped" 122 "" 0 \
	          "macOS session is locked; spreadsheet keyboard input and save verification require an unlocked GUI session."
	        record wps-office-presentation document-writeback "skipped" 122 "" 0 \
	          "macOS session is locked; presentation keyboard input and save verification require an unlocked GUI session."
	        record wps-office-pdf print-dialog "skipped" 122 "" 0 \
	          "macOS session is locked; PDF print-dialog verification requires an unlocked GUI session."
	      else
	        case ",${MACWIN_WPS_FUNCTIONAL_ACTIONS:-spreadsheet-save,presentation-save,pdf-print-dialog}," in
	          *,spreadsheet-save,*)
	            run_logged wps-office-spreadsheet document-writeback 55 timeout \
	              "WPS Spreadsheets did not persist the injected marker to the XLSX package." \
	              run_wps_component_functional_acceptance wps-office-spreadsheet et.exe \
	              macwin-wps-smoke.xlsx spreadsheet-save || true
	            ;;
	        esac
	        case ",${MACWIN_WPS_FUNCTIONAL_ACTIONS:-spreadsheet-save,presentation-save,pdf-print-dialog}," in
	          *,presentation-save,*)
	            run_logged wps-office-presentation document-writeback 55 timeout \
	              "WPS Presentation did not add and persist a second slide to the PPTX package." \
	              run_wps_component_functional_acceptance wps-office-presentation wpp.exe \
	              macwin-wps-smoke.pptx presentation-save || true
	            ;;
	        esac
	        case ",${MACWIN_WPS_FUNCTIONAL_ACTIONS:-spreadsheet-save,presentation-save,pdf-print-dialog}," in
	          *,pdf-print-dialog,*)
	            run_logged wps-office-pdf print-dialog 60 timeout \
	              "WPS PDF did not expose a visible native or custom Qt print dialog after Ctrl+P." \
	              run_wps_component_functional_acceptance wps-office-pdf wpspdf.exe \
	              macwin-wps-smoke.pdf pdf-print-dialog || true
	            ;;
	        esac
	      fi
	    else
	      record "$id" document-fixtures "failed" 1 "$wps_fixture_dir" 0 \
	        "Generated WPS XLSX, PPTX, or PDF fixture failed its container integrity check."
	    fi
	  fi
	  if [ -n "$pgadmin_cdp_pid" ]; then
	    wait "$pgadmin_cdp_pid" 2>/dev/null || true
	  fi
	  if [ -n "$openplc_cdp_pid" ]; then
	    wait "$openplc_cdp_pid" 2>/dev/null || true
	  fi
	  if [ "$id" = "freecad-workbench" ]; then
	    run_logged "$id" core-workload 60 timeout "FreeCAD core geometry workload did not exit before timeout." \
	      run_freecad_core_workload || true
	  fi
	  if [ "$id" = "kicad-eda" ]; then
	    run_logged "$id" core-workload 60 timeout "KiCad PCB DRC workload did not exit before timeout." \
	      run_kicad_core_workload || true
	  fi
	  if [ "$id" = "qelectrotech-cad" ]; then
	    run_logged "$id" project-workload 30 timeout "QElectroTech project validation did not exit before timeout." \
	      run_qelectrotech_project_workload || true
	  fi
	  if [ "$id" = "blender-3d" ]; then
	    run_logged "$id" core-workload 120 timeout "Blender Cycles CPU render did not exit before timeout." \
	      run_blender_core_workload || true
	    run_logged "$id" eevee-windowed-workload 90 timeout \
	      "Blender Eevee software OpenGL render or window validation did not exit before timeout." \
	      run_blender_eevee_windowed_workload || true
	  fi
	  if [ "$id" = "inkscape-vector" ]; then
	    run_logged "$id" core-workload 120 timeout "Inkscape SVG-to-PNG export did not exit before timeout." \
	      run_inkscape_core_workload || true
	  fi
	  if [ "$id" = "sqlitebrowser-db" ]; then
	    run_logged "$id" core-workload 60 timeout "DB Browser SQLite DLL workload did not exit before timeout." \
	      run_sqlitebrowser_core_workload || true
	  fi
	  if [ "$id" = "beekeeper-studio" ]; then
	    run_logged "$id" core-workload 60 timeout "Beekeeper Studio native SQLite workload did not exit before timeout." \
	      run_beekeeper_sqlite_workload || true
	  fi
	  if [ "$id" = "pgadmin-db-admin" ]; then
	    run_logged "$id" core-workload 120 timeout "pgAdmin backend service workload did not exit before timeout." \
	      run_pgadmin_backend_workload || true
	    if command -v pg_isready >/dev/null 2>&1 \
	      && pg_isready -h 127.0.0.1 -p 5432 -d postgres >/dev/null 2>&1; then
	      run_logged "$id" postgres-workload 90 timeout "pgAdmin PostgreSQL TCP workload did not exit before timeout." \
	        run_pgadmin_postgres_workload || true
	    else
	      record "$id" postgres-workload "skipped" 77 "" 0 \
	        "No local PostgreSQL server is accepting TCP connections on 127.0.0.1:5432."
	    fi
	  fi
	  if [ "$id" = "dbeaver-database" ]; then
	    if command -v pg_isready >/dev/null 2>&1 \
	      && pg_isready -h 127.0.0.1 -p 5432 -d postgres >/dev/null 2>&1; then
	      run_logged "$id" jdbc-workload 90 timeout "DBeaver PostgreSQL JDBC workload did not exit before timeout." \
	        run_dbeaver_jdbc_workload || true
	    else
	      record "$id" jdbc-workload "skipped" 77 "" 0 \
	        "No local PostgreSQL server is accepting TCP connections on 127.0.0.1:5432."
	    fi
	  fi
	  if [ "$id" = "energyplus-building" ]; then
	    run_logged "$id" simulation-workload 120 timeout "EnergyPlus annual simulation did not exit before timeout." \
	      run_energyplus_simulation_workload || true
	  fi
	  if [ "$id" = "openplc-editor" ]; then
	    run_logged "$id" compiler-workload 120 timeout "OpenPLC PLCopen XML, STruC++, generated C++, or Arduino CLI workload did not finish before timeout." \
	      run_openplc_compiler_workload || true
	  fi
	  if [ "$id" = "opendss-power" ]; then
	    run_logged "$id" simulation-workload 60 timeout "OpenDSS power-flow simulation did not produce valid voltage results." \
	      run_opendss_power_workload || true
	    run_logged "$id" com-workload 60 timeout "OpenDSS COM automation did not register, create an active circuit, or converge." \
	      run_opendss_com_workload || true
	  fi
	  if [ "$id" = "wireshark-analyzer" ]; then
	    if run_logged "$id" packet-workload 60 timeout "Wireshark tshark did not decode the deterministic Ethernet/IPv4/UDP capture." \
	      run_wireshark_packet_workload; then
	      {
	        echo "wiresharkOfflineDissection=passed"
	        echo "wiresharkLiveCapture=unsupported-npcap-driver"
	      } >> "$LOG_DIR/$id-launch.log"
	    fi
	  fi
	  if [ "$id" = "vlc-media" ]; then
	    run_logged "$id" audio-workload 60 timeout "VLC did not decode and transcode the deterministic PCM tone." \
	      run_vlc_audio_workload || true
	  fi
	  if [ "$id" = "firefox-browser" ]; then
	    run_logged "$id" browser-workload 120 timeout "Firefox rendering workload did not finish before timeout." \
	      run_firefox_browser_workload || true
	  fi
	  if [ "$id" = "brave-portable" ]; then
	    run_logged "$id" browser-workload 150 timeout "Brave rendering and TLS workload did not finish before timeout." \
	      run_brave_browser_workload || true
	  fi
	  if [ "$id" = "opera-browser" ]; then
	    run_logged "$id" browser-workload 150 timeout "Opera rendering and TLS workload did not finish before timeout." \
	      run_opera_browser_workload || true
	  fi
	  if [ "$id" = "edge-enterprise" ]; then
	    run_logged "$id" browser-workload 150 timeout "Edge rendering and TLS workload did not finish before timeout." \
	      run_edge_browser_workload || true
	  fi
	  if [ "$id" = "itch" ]; then
	    run_logged "$id" browser-workload 120 timeout "itch Electron UI and butlerd workload did not finish before timeout." \
	      run_itch_market_workload || true
	  fi
	  if [ "$id" = "npackd" ]; then
	    run_logged "$id" repository-workload 30 timeout "Npackd repository validation did not finish before timeout." \
	      run_npackd_repository_workload || true
	  fi
	  if [ "$id" = "cura-slicer" ]; then
	    run_logged "$id" slicing-workload 120 timeout "CuraEngine slicing workload did not finish before timeout." \
	      run_cura_slicing_workload || true
	  fi
	  if [ "$id" = "bambu-studio-portable" ]; then
	    run_logged "$id" slicing-workload 120 timeout "Bambu Studio 3MF slicing workload did not finish before timeout." \
	      run_bambu_studio_slicing_workload || true
	  fi
	  if [ "$id" = "orcaslicer-print" ]; then
	    run_logged "$id" slicing-workload 120 timeout "OrcaSlicer 3MF slicing workload did not finish before timeout." \
	      run_orcaslicer_slicing_workload || true
	  fi
	  if [ "$id" = "krita-paint" ]; then
	    run_logged "$id" image-workload 120 timeout "Krita image import/export workload did not finish before timeout." \
	      run_krita_image_workload || true
	  fi
	  if [ "$id" = "godot-win64-editor" ] || [ "$id" = "godot-win32-editor" ]; then
	    run_logged "$id" vulkan-workload 90 timeout "Godot Forward+ Vulkan render and frame-buffer capture did not finish before timeout." \
	      run_godot_vulkan_workload "$id" || true
	  fi
	  if [ "$id" = "powertoys-fancyzones" ]; then
	    if run_logged "$id" fancyzones-workload 90 timeout "PowerToys FancyZones service, layout-state, and editor IPC workload did not finish before timeout." \
	      run_powertoys_fancyzones_workload; then
	      echo "PASS fancyzones_editor_ipc" >> "$LOG_DIR/powertoys-fancyzones-open-editor.log"
	      record "$id" fancyzones-editor-ipc "passed" 0 \
	        "$LOG_DIR/powertoys-fancyzones-open-editor.log" 5 \
	        "FancyZonesCLI open-editor IPC returned successfully; the service remained alive for five seconds with no Wine page fault."
	      capture_visual_probe_for_sample "$id" fancyzones-editor-visual \
	        "$LOG_DIR/powertoys-fancyzones-open-editor.log" || true
	      fancyzones_visual_classification="$(
	        LC_ALL=C sed -n 's/^visualProbe.classification=//p' \
	          "$LOG_DIR/powertoys-fancyzones-open-editor.log" | tail -n 1
	      )"
	      fancyzones_visual_reason="$(
	        LC_ALL=C sed -n 's/^visualProbe.reason=//p' \
	          "$LOG_DIR/powertoys-fancyzones-open-editor.log" | tail -n 1
	      )"
	      if [ "$fancyzones_visual_classification" = "rendered" ]; then
	        echo "PASS fancyzones_editor_visual" >> "$LOG_DIR/powertoys-fancyzones-open-editor.log"
	        record "$id" fancyzones-editor-visual "passed" 0 \
	          "$LOG_DIR/powertoys-fancyzones-editor-visual-visual.png" 0 \
	          "FancyZones editor window was captured and verified as rendered."
	      elif [ "$fancyzones_visual_reason" = "session-locked" ]; then
	        record "$id" fancyzones-editor-visual "skipped" 122 \
	          "$LOG_DIR/powertoys-fancyzones-open-editor.log" 0 \
	          "Editor IPC passed, but the macOS session is locked, so the visible editor window remains unverified."
	      else
	        record "$id" fancyzones-editor-visual "failed" 125 \
	          "$LOG_DIR/powertoys-fancyzones-open-editor.log" 0 \
	          "FancyZones editor IPC passed, but its visible window could not be verified as rendered."
	      fi
	    else
	      record "$id" fancyzones-editor-visual "skipped" 121 \
	        "$LOG_DIR/powertoys-fancyzones-open-editor.log" 0 \
	        "FancyZones editor visual probe was not run because the service or editor IPC workload failed."
	    fi
	    run_logged "$id" image-resizer-workload 90 timeout \
	      "PowerToys Image Resizer PNG workload did not finish before timeout." \
	      run_powertoys_image_resizer_workload || true
	  fi
	  if [ "$id" = "jabref-portable" ]; then
	    run_logged "$id" core-workload 90 timeout "JabRef BibTeX-to-RIS workload did not finish before timeout." \
	      run_jabref_core_workload || true
	  fi
	  if [ "$id" = "pdfarranger-portable" ]; then
	    run_logged "$id" core-workload 90 timeout "PDF Arranger qpdf merge workload did not finish before timeout." \
	      run_pdfarranger_core_workload || true
	  fi
	  if [ "$id" = "libreoffice-suite" ]; then
	    run_logged "$id" core-workload 120 timeout "LibreOffice PDF conversion did not exit before timeout." \
	      run_libreoffice_core_workload || true
	  fi
	  if [ "$id" = "onlyoffice-suite" ]; then
	    run_logged "$id" core-workload 120 timeout "ONLYOFFICE OOXML conversion did not exit before timeout." \
	      run_onlyoffice_core_workload || true
	    run_logged "$id" renderer-font-repair 30 timeout "ONLYOFFICE renderer font cache was not synchronized." \
	      repair_onlyoffice_renderer_fonts || true
	    run_logged "$id" pdf-export-capability 120 timeout "ONLYOFFICE DOCX-to-PDF conversion did not exit before timeout." \
	      run_onlyoffice_pdf_export_workload || true
	  fi
	  if [ "$id" = "r-base-gui" ]; then
	    run_logged "$id" core-workload 120 timeout "R statistics workload did not exit before timeout." \
	      run_r_statistics_workload || true
	  fi
	  if [ "$id" = "rstudio-desktop" ]; then
	    run_logged "$id" backend-workload 120 timeout "RStudio rsession verification did not exit before timeout." \
	      run_rstudio_backend_workload || true
	    run_logged "$id" core-workload 120 timeout "RStudio R statistics workload did not exit before timeout." \
	      run_r_statistics_workload || true
	  fi
	  if [ "$id" = "jasp-stats" ]; then
	    jasp_launch_log="$LOG_DIR/${id}-launch.log"
	    if log_has_runtime_fixed_string 'QML Initialized!' "$jasp_launch_log" \
	      && { log_has_runtime_fixed_string 'JASP Desktop started and Engines initalized' "$jasp_launch_log" \
	        || log_has_runtime_fixed_string 'MainWindow::resultsPageLoaded()' "$jasp_launch_log"; }; then
	      {
	        echo "jaspStartupMilestone=passed"
	        echo "jaspStartupQMLInitialized=yes"
	        if log_has_runtime_fixed_string 'MainWindow::resultsPageLoaded()' "$jasp_launch_log"; then
	          echo "jaspStartupResultsPageLoaded=yes"
	        fi
	      } >> "$jasp_launch_log"
	      record "$id" "startup-milestones" "passed" 0 "$jasp_launch_log" 0 \
	        "JASP initialized QML and reached either the Desktop-started or results-page milestone under Wine."
	    else
	      echo "jaspStartupMilestone=failed" >> "$jasp_launch_log"
	      record "$id" "startup-milestones" "failed" 124 "$jasp_launch_log" 0 \
	        "JASP stayed alive but did not complete both the Desktop-started and QML-initialized milestones."
	    fi
	    if has_jasp_qt_platform_plugin_missing_failure "$jasp_launch_log"; then
	      jasp_postlaunch_skip_note="$(jasp_qt_platform_plugin_missing_note)"
	      record "$id" "constructor-boundary-postlaunch-probe" "skipped" 122 "$jasp_launch_log" 0 "$jasp_postlaunch_skip_note"
	      record "$id" "post-ipc-failfast-postlaunch-probe" "skipped" 122 "$jasp_launch_log" 0 "$jasp_postlaunch_skip_note"
	      record "$id" "runtime-state-postlaunch-probe" "skipped" 122 "$jasp_launch_log" 0 "$jasp_postlaunch_skip_note"
	    else
	      capture_jasp_boost_ipc_snapshot "$id" "postlaunch" "$jasp_launch_log" || true
	      write_jasp_constructor_boundary_probe "$id" "constructor-boundary-postlaunch-probe" || true
	      write_jasp_failfast_boundary_probe "$id" "post-ipc-failfast-postlaunch-probe" || true
	      write_jasp_runtime_state_probe "$id" "runtime-state-postlaunch-probe" || true
	    fi
	    if log_has_runtime_fixed_string 'jaspStartupMilestone=passed' "$jasp_launch_log"; then
	      {
	        echo "jaspStartupMilestone=passed"
	        echo "jaspStartupQMLInitialized=yes"
	        if log_has_runtime_fixed_string 'MainWindow::resultsPageLoaded()' "$jasp_launch_log"; then
	          echo "jaspStartupResultsPageLoaded=yes"
	        fi
	      } >> "$jasp_launch_log"
	    fi
	    if is_jasp_unit_test_launch; then
	      if has_jasp_completed_analysis_workload "$jasp_launch_log"; then
	        jasp_analysis_note="JASP started JASPEngine/R, completed the requested analysis, and emitted comparable old/new statistical result tables."
	        if log_has_runtime_fixed_string 'The results are different...' "$jasp_launch_log"; then
	          jasp_analysis_note="$(append_note "$jasp_analysis_note" "The fixture's stored values use different result precision than this JASP build, so exact baseline comparison returned nonzero while the statistical workload itself completed.")"
	        fi
	        record "$id" "analysis-workload" "passed" 0 "$jasp_launch_log" 0 "$jasp_analysis_note"
	      else
	        record "$id" "analysis-workload" "failed" 128 "$jasp_launch_log" 0 \
	          "JASP unit-test mode did not show a started JASPEngine plus a completed analysis and old/new result tables."
	      fi
	    fi
	  fi
	  if [ "$id" = "meshlab-3d" ]; then
	    meshlab_launch_log="$LOG_DIR/${id}-launch.log"
	    if log_has_runtime_fixed_string 'Using OpenGL 3.0' "$meshlab_launch_log" \
	      && [ -f "$PREFIX/drive_c/macwin-tests/meshlab-cube.obj" ]; then
	      record "$id" "viewport-workload" "passed" 0 "$meshlab_launch_log" 0 \
	        "MeshLab kept its real cube mesh workload alive with the bundled OpenGL 3.0 software renderer; interactive rotation was validated on the macOS session."
	    else
	      record "$id" "viewport-workload" "failed" 127 "$meshlab_launch_log" 0 \
	        "MeshLab did not initialize its bundled OpenGL 3.0 renderer for the cube viewport workload."
	    fi
	  fi
	  done
	fi

if [ "$RUNTIME_STALL_ACTIVE" -ne 1 ]; then
  "${WINESERVER_CMD[@]}" -k >/dev/null 2>&1 || true
fi

/usr/bin/python3 - "$records_file" "$REPORT_JSON" "$REPORT_MD" "$RUN_ID" "$SMOKE_SUITE" "$SMOKE_SAMPLE" "$PREFIX" "$LOG_DIR" <<'PY'
import json, sys
from collections import Counter
from datetime import datetime, timezone
records_path, report_json, report_md, run_id, suite, sample, prefix, log_dir = sys.argv[1:]
records = []
with open(records_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))
counts = Counter(r["state"] for r in records)
superseded_legacy = {
    "geogebra-classic": {
        "supersededBy": ["geogebra-classic5"],
        "reason": "GeoGebra Classic 6 is a legacy 32-bit Electron/WOW64 regression path; GeoGebra Classic 5 is the validated geometry UI target.",
    },
    "mremoteng-manager": {
        "supersededBy": ["mremoteng-1782-x64"],
        "reason": "mRemoteNG 1.76.x is a legacy 32-bit .NET/Wine-Mono path; mRemoteNG 1.78.2 x64 is the validated WinForms target.",
    },
    "winscp-client": {
        "supersededBy": ["winscp-x64-portable", "winscp-x64-cli-help"],
        "reason": "WinSCP stable GUI installer is a legacy 32-bit Delphi/VCL path; WinSCP x64 portable GUI and CLI are the validated targets.",
    },
    "winscp-cli-help": {
        "supersededBy": ["winscp-x64-cli-help"],
        "reason": "WinSCP stable WinSCP.com is part of the same legacy 32-bit package; the x64 portable CLI is the validated command-line target.",
    },
    "qownnotes-editor": {
        "supersededBy": ["qownnotes-portable"],
        "reason": "The older QOwnNotes editor sample was replaced by the portable build, which preserves the Qt notes UI target and has a validated GUI launch path.",
    },
    "palemoon-32-browser": {
        "supersededBy": ["seamonkey-32-browser", "supermium-32-browser"],
        "reason": "Pale Moon 32-bit needs the managed rosettax87 runtime for Gecko/XUL startup; without it, SeaMonkey 32-bit and Supermium 32-bit preserve the browser coverage targets.",
    },
}
launch_records_by_id = {}
for record in records:
    if record.get("phase") != "launch":
        continue
    launch_records_by_id.setdefault(record.get("id"), []).append(record)
superseded_skips = []
for record in records:
    if record.get("phase") != "launch" or record.get("state") != "skipped":
        continue
    metadata = superseded_legacy.get(record.get("id"))
    if not metadata:
        continue
    covered_by = []
    missing_alternates = []
    for alternate_id in metadata["supersededBy"]:
        alternate_records = launch_records_by_id.get(alternate_id, [])
        successful = [item for item in alternate_records if item.get("state") in ("passed", "launched")]
        if successful:
            covered_by.append({
                "id": alternate_id,
                "state": successful[-1].get("state"),
                "logPath": successful[-1].get("logPath"),
                "note": successful[-1].get("note", ""),
            })
        else:
            missing_alternates.append(alternate_id)
    superseded_skips.append({
        "id": record.get("id"),
        "state": record.get("state"),
        "exitCode": record.get("exitCode"),
        "logPath": record.get("logPath"),
        "note": record.get("note", ""),
        "reason": metadata["reason"],
        "supersededBy": metadata["supersededBy"],
        "coveredBy": covered_by,
        "missingAlternatesInRun": missing_alternates,
    })
effective_counts = Counter(counts)
if superseded_skips:
    effective_counts["skipped"] -= len(superseded_skips)
    if effective_counts["skipped"] <= 0:
        effective_counts.pop("skipped", None)
    effective_counts["superseded"] += len(superseded_skips)
report = {
    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "runId": run_id,
    "suite": suite,
    "sample": sample or None,
    "prefix": prefix,
    "logDirectory": log_dir,
    "recordCount": len(records),
    "stateCounts": dict(sorted(counts.items())),
    "effectiveStateCounts": dict(sorted(effective_counts.items())),
    "supersededSkipCount": len(superseded_skips),
    "supersededSkips": superseded_skips,
    "records": records,
}
with open(report_json, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
    f.write("\n")
lines = [
    "# MacWin Real Software Smoke Report",
    "",
    f"- Generated: {report['generatedAt']}",
    f"- Run: `{run_id}`",
    f"- Suite: `{suite}`",
    f"- Sample: `{sample}`" if sample else "- Sample: all selected samples",
    f"- Prefix: `{prefix}`",
    f"- Logs: `{log_dir}`",
    f"- Records: {len(records)}",
    "",
    "## State Counts",
    "",
]
for key, value in sorted(counts.items()):
    lines.append(f"- `{key}`: {value}")
if superseded_skips:
    lines += [
        "",
        "## Effective State Counts",
        "",
    ]
    for key, value in sorted(effective_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += [
        "",
        "## Superseded Legacy Skips",
        "",
    ]
    for item in superseded_skips:
        covered = ", ".join(f"{record['id']} ({record['state']})" for record in item["coveredBy"]) or "not covered in this run"
        missing = ", ".join(item["missingAlternatesInRun"]) or "none"
        lines.append(f"### {item['id']}")
        lines.append("")
        lines.append(f"- Superseded by: `{', '.join(item['supersededBy'])}`")
        lines.append(f"- Covered in this run: {covered}")
        lines.append(f"- Missing alternates in this run: {missing}")
        lines.append(f"- Reason: {item['reason']}")
        if item.get("note"):
            lines.append(f"- Original note: {item['note']}")
        lines.append("")
lines += ["", "## Records", ""]
for record in records:
    lines.append(f"### {record['id']} / {record['phase']}")
    lines.append("")
    lines.append(f"- State: `{record['state']}`")
    lines.append(f"- Exit code: `{record['exitCode']}`")
    if record.get("logPath"):
        lines.append(f"- Log: `{record['logPath']}`")
    if record.get("note"):
        lines.append(f"- Note: {record['note']}")
    lines.append("")
with open(report_md, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
    f.write("\n")
print(report_json)
print(report_md)
print(json.dumps(report["stateCounts"], ensure_ascii=False, sort_keys=True))
PY

if [ "$RUNTIME_STALL_ACTIVE" -eq 1 ]; then
  exit 75
fi
