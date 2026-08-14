#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/refs/jasp-desktop-v0.97.1"
PATCH_FILE="$PROJECT_ROOT/patches/jasp-0.97.1-initialize-enginesync-before-reset.patch"
PROXY_RESET_PATCH_FILE="$PROJECT_ROOT/patches/jasp-0.97.1-fix-proxy-model-reset.patch"
WORKSPACE_RESET_PATCH_FILE="$PROJECT_ROOT/patches/jasp-0.97.1-avoid-nested-workspace-reset.patch"
BUILD_PATCH_FILE="$PROJECT_ROOT/patches/jasp-0.97.1-local-macos-build-configure.patch"
DEST_DIR="${1:-$PROJECT_ROOT/tmp/jasp-compat-source}"
MARKER=".macwin-generated-jasp-patched-source"
LOCAL_CONAN_BIN="${MACWIN_JASP_CONAN_BIN:-$PROJECT_ROOT/tmp/jasp-conan-venv/bin}"
LOCAL_CONAN_HOME="${MACWIN_JASP_CONAN_HOME:-$PROJECT_ROOT/tmp/jasp-conan-home}"

if [ -x "$LOCAL_CONAN_BIN/conan" ]; then
  export PATH="$LOCAL_CONAN_BIN:$PATH"
  export CONAN_HOME="$LOCAL_CONAN_HOME"
fi

die() {
  printf 'error=%s\n' "$*" >&2
  exit 1
}

require_file() {
  [ -f "$1" ] || die "missing file: $1"
}

require_dir() {
  [ -d "$1" ] || die "missing directory: $1"
}

tool_path() {
  local tool="$1"
  command -v "$tool" 2>/dev/null || true
}

has_tool() {
  local tool="$1"
  command -v "$tool" >/dev/null 2>&1
}

require_dir "$SOURCE_DIR/.git"
require_file "$PATCH_FILE"
require_file "$PROXY_RESET_PATCH_FILE"
require_file "$WORKSPACE_RESET_PATCH_FILE"
require_file "$BUILD_PATCH_FILE"

if [ -e "$DEST_DIR" ]; then
  if [ -f "$DEST_DIR/$MARKER" ]; then
    git -C "$SOURCE_DIR" worktree remove --force "$DEST_DIR" >/dev/null 2>&1 || rm -rf "$DEST_DIR"
  else
    die "destination exists and is not marked as generated: $DEST_DIR"
  fi
fi

mkdir -p "$(dirname "$DEST_DIR")"
git -C "$SOURCE_DIR" worktree prune
git -C "$SOURCE_DIR" worktree add --detach "$DEST_DIR" HEAD >/dev/null
if git -C "$DEST_DIR" sparse-checkout list >/dev/null 2>&1; then
  git -C "$DEST_DIR" sparse-checkout add --skip-checks \
    Common \
    CommonData \
    Desktop \
    Engine \
    Modules \
    QMLComponents \
    R-Interface \
    Resources \
    SyntaxInterface \
    Tools \
    conanfile.py >/dev/null
fi
git -C "$DEST_DIR" submodule update --init --recursive \
  Engine/jaspBase \
  Engine/jaspModuleBundleManager \
  Tools/jaspTools >/dev/null
git -C "$DEST_DIR" apply "$PATCH_FILE"
git -C "$DEST_DIR" apply "$PROXY_RESET_PATCH_FILE"
git -C "$DEST_DIR" apply "$WORKSPACE_RESET_PATCH_FILE"
git -C "$DEST_DIR" apply "$BUILD_PATCH_FILE"

patch_sha="$(shasum -a 256 "$PATCH_FILE" "$PROXY_RESET_PATCH_FILE" "$WORKSPACE_RESET_PATCH_FILE" "$BUILD_PATCH_FILE" | awk '{print $1}' | paste -sd, -)"
{
  printf 'generatedBy=%s\n' "$0"
  printf 'sourceDir=%s\n' "$SOURCE_DIR"
  printf 'patchFile=%s\n' "$PATCH_FILE"
  printf 'proxyResetPatchFile=%s\n' "$PROXY_RESET_PATCH_FILE"
  printf 'workspaceResetPatchFile=%s\n' "$WORKSPACE_RESET_PATCH_FILE"
  printf 'buildPatchFile=%s\n' "$BUILD_PATCH_FILE"
  printf 'patchSha256=%s\n' "$patch_sha"
  printf 'generatedAt=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$DEST_DIR/$MARKER"

/usr/bin/python3 - "$DEST_DIR" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
dataset = (root / "Desktop/data/datasetpackage.cpp").read_text(errors="replace").splitlines()
engine = (root / "Desktop/engine/enginesync.cpp").read_text(errors="replace").splitlines()

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

print(f"preparedSource.path={root}")
print(f"preparedSource.dataset.qtimerInclude={dataset_qtimer_include}")
print(f"preparedSource.dataset.directResetInSetEngineSync={dataset_direct_reset}")
print(f"preparedSource.dataset.deferredResetInSetEngineSync={dataset_deferred_reset}")
print(f"preparedSource.engine.constructorSetDataPackageEngineSync={engine_ctor_set_pkg}")
print(f"preparedSource.engine.memoryNameAssignment={engine_memory_name}")
print(f"preparedDerived.initialResetSynchronous={'yes' if dataset_direct_reset and not dataset_deferred_reset else 'no'}")
print(f"preparedDerived.memoryNameAssignedBeforeSetEngineSync={'yes' if engine_ctor and engine_memory_name and engine_ctor_set_pkg and engine_ctor < engine_memory_name < engine_ctor_set_pkg else 'no'}")
print(f"preparedDerived.constructorReentryStateInitialized={'yes' if dataset_direct_reset and not dataset_deferred_reset and engine_memory_name and engine_ctor_set_pkg and engine_memory_name < engine_ctor_set_pkg else 'no'}")
print(f"preparedDerived.nestedWorkspaceResetAvoided={'yes' if dataset_constructor_defaults and dataset_create_defaults else 'no'}")
PY

printf 'buildTool.cmake=%s\n' "$(tool_path cmake)"
printf 'buildTool.ninja=%s\n' "$(tool_path ninja)"
printf 'buildTool.qtCmake=%s\n' "$(tool_path qt-cmake)"
printf 'buildTool.qmake6=%s\n' "$(tool_path qmake6)"
printf 'buildTool.R=%s\n' "$(tool_path R)"
printf 'buildTool.Rscript=%s\n' "$(tool_path Rscript)"
printf 'buildTool.conan=%s\n' "$(tool_path conan)"
printf 'buildTool.conanHome=%s\n' "${CONAN_HOME:-}"
if has_tool conan; then
  printf 'buildTool.conanDefaultProfile=%s\n' "$(conan profile path default 2>/dev/null || true)"
fi
printf 'buildTool.mingwGcc=%s\n' "$(tool_path x86_64-w64-mingw32-gcc)"
printf 'buildTool.mingwGxx=%s\n' "$(tool_path x86_64-w64-mingw32-g++)"
printf 'buildTool.mingwWindres=%s\n' "$(tool_path x86_64-w64-mingw32-windres)"
printf 'buildTool.msbuild=%s\n' "$(tool_path msbuild)"
printf 'buildTool.dotnet=%s\n' "$(tool_path dotnet)"
printf 'buildTool.pwsh=%s\n' "$(tool_path pwsh)"
printf 'buildEnv.MACWIN_JASP_WINDOWS_QT_PREFIX=%s\n' "${MACWIN_JASP_WINDOWS_QT_PREFIX:-}"
printf 'buildEnv.MACWIN_JASP_WINDOWS_R_HOME=%s\n' "${MACWIN_JASP_WINDOWS_R_HOME:-}"
printf 'buildEnv.CMAKE_TOOLCHAIN_FILE=%s\n' "${CMAKE_TOOLCHAIN_FILE:-}"

host_missing=()
for tool in cmake ninja qt-cmake R Rscript conan; do
  if ! has_tool "$tool"; then
    host_missing+=("$tool")
  fi
done

windows_missing=()
for tool in cmake ninja conan; do
  if ! has_tool "$tool"; then
    windows_missing+=("$tool")
  fi
done
if ! has_tool x86_64-w64-mingw32-gcc || ! has_tool x86_64-w64-mingw32-g++ || ! has_tool x86_64-w64-mingw32-windres; then
  windows_missing+=("mingw-w64")
fi
if [ -z "${MACWIN_JASP_WINDOWS_QT_PREFIX:-}" ] || [ ! -d "${MACWIN_JASP_WINDOWS_QT_PREFIX:-/nonexistent}" ]; then
  windows_missing+=("MACWIN_JASP_WINDOWS_QT_PREFIX")
fi
if [ -z "${MACWIN_JASP_WINDOWS_R_HOME:-}" ] || [ ! -d "${MACWIN_JASP_WINDOWS_R_HOME:-/nonexistent}" ]; then
  windows_missing+=("MACWIN_JASP_WINDOWS_R_HOME")
fi

if [ "${#host_missing[@]}" -eq 0 ]; then
  printf 'hostBuildReadiness=ready\n'
else
  printf 'hostBuildReadiness=missing-required-tools\n'
  printf 'missing.hostBuildInputs=%s\n' "$(IFS=,; echo "${host_missing[*]}")"
fi

if [ "${#windows_missing[@]}" -eq 0 ]; then
  printf 'windowsExeBuildReadiness=ready\n'
else
  printf 'windowsExeBuildReadiness=missing-required-inputs\n'
  printf 'missing.windowsExeBuildInputs=%s\n' "$(IFS=,; echo "${windows_missing[*]}")"
fi
