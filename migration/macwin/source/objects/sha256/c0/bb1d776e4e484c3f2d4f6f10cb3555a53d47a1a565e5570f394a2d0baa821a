#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="${MACWIN_JASP_PATCHED_SOURCE_DIR:-$PROJECT_ROOT/tmp/jasp-compat-source}"
BUILD_DIR="${MACWIN_JASP_PATCHED_BUILD_DIR:-$PROJECT_ROOT/tmp/jasp-compat-build-host}"
LOG_FILE="${MACWIN_JASP_PATCHED_CONFIGURE_LOG:-$PROJECT_ROOT/tmp/jasp-compat-configure.log}"
LOCAL_CONAN_BIN="${MACWIN_JASP_CONAN_BIN:-$PROJECT_ROOT/tmp/jasp-conan-venv/bin}"
LOCAL_CONAN_HOME="${MACWIN_JASP_CONAN_HOME:-$PROJECT_ROOT/tmp/jasp-conan-home}"
LOCAL_CODESIGN_IDENTITY="${LOCAL_CODESIGN_IDENTITY:--}"
CMAKE_BUILD_TYPE="${MACWIN_JASP_CMAKE_BUILD_TYPE:-Release}"
INSTALL_R_MODULES="${MACWIN_JASP_INSTALL_R_MODULES:-OFF}"
RENV_PACKAGE_URL="${MACWIN_JASP_RENV_PACKAGE_URL:-https://packagemanager.posit.co/cran/latest/bin/macosx/big-sur-arm64/contrib/4.5/renv_1.2.3.tgz}"
RENV_PACKAGE_CACHE="${MACWIN_JASP_RENV_PACKAGE:-$PROJECT_ROOT/tmp/jasp-r-package-cache/renv_1.2.3.tgz}"
LOCAL_LIBARCHIVE_PREFIX="${MACWIN_JASP_LIBARCHIVE_PREFIX:-}"
CMAKE_SIGNING_ARGS=(
  -DSIGN_AT_BUILD_TIME=OFF
  -DTIMESTAMP_AT_BUILD_TIME=OFF
)

if [ -x "$LOCAL_CONAN_BIN/conan" ]; then
  export PATH="$LOCAL_CONAN_BIN:$PATH"
  export CONAN_HOME="$LOCAL_CONAN_HOME"
fi

if [ -z "$LOCAL_LIBARCHIVE_PREFIX" ] && [ -d "$LOCAL_CONAN_HOME/p/b" ]; then
  libarchive_header="$(find "$LOCAL_CONAN_HOME/p/b" -path '*/p/include/archive.h' -print -quit 2>/dev/null || true)"
  if [ -n "$libarchive_header" ]; then
    LOCAL_LIBARCHIVE_PREFIX="$(cd "$(dirname "$libarchive_header")/.." && pwd)"
  fi
fi

"$SCRIPT_DIR/prepare-jasp-compat-source.sh" "$SOURCE_DIR" >/tmp/macwin-jasp-prepare-for-configure.log

rm -rf "$BUILD_DIR"
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$RENV_PACKAGE_CACHE")"

if [ ! -s "$RENV_PACKAGE_CACHE" ]; then
  curl -fL --retry 5 --retry-all-errors --connect-timeout 30 --max-time 300 \
    "$RENV_PACKAGE_URL" -o "$RENV_PACKAGE_CACHE" || rm -f "$RENV_PACKAGE_CACHE"
fi

set +e
env -u GITHUB_PAT -u GITHUB_PAT_DEF \
  LOCAL_CODESIGN_IDENTITY="$LOCAL_CODESIGN_IDENTITY" \
  MACWIN_JASP_RENV_PACKAGE="$RENV_PACKAGE_CACHE" \
  MACWIN_JASP_LIBARCHIVE_PREFIX="$LOCAL_LIBARCHIVE_PREFIX" \
  cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" -G Ninja -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" \
  -DINSTALL_R_MODULES="$INSTALL_R_MODULES" \
  "${CMAKE_SIGNING_ARGS[@]}" \
  >"$LOG_FILE" 2>&1
cmake_rc=$?
set -e

printf 'configure.source=%s\n' "$SOURCE_DIR"
printf 'configure.buildDir=%s\n' "$BUILD_DIR"
printf 'configure.log=%s\n' "$LOG_FILE"
printf 'configure.buildType=%s\n' "$CMAKE_BUILD_TYPE"
printf 'configure.installRModules=%s\n' "$INSTALL_R_MODULES"
printf 'configure.codesignIdentity=%s\n' "$LOCAL_CODESIGN_IDENTITY"
if [ -n "$LOCAL_LIBARCHIVE_PREFIX" ]; then
  printf 'configure.libarchivePrefix=%s\n' "$LOCAL_LIBARCHIVE_PREFIX"
else
  printf 'configure.libarchivePrefix=missing\n'
fi
if [ -s "$RENV_PACKAGE_CACHE" ]; then
  printf 'configure.renvPackageCache=%s\n' "$RENV_PACKAGE_CACHE"
else
  printf 'configure.renvPackageCache=missing\n'
fi
printf 'configure.exitCode=%s\n' "$cmake_rc"

if rg -q 'minizip/1\.2\.13:.*Error 415 downloading file https://zlib\.net/fossils/zlib-1\.2\.13\.tar\.gz|ERROR: minizip/1\.2\.13: Error in source\(\) method' "$LOG_FILE"; then
  printf 'configure.failure=minizip-source-download\n'
elif rg -q 'default build profile .*doesn.t exist|conan profile detect' "$LOG_FILE"; then
  printf 'configure.failure=missing-conan-profile\n'
elif rg -q 'command not found: conan|Conan configuration failed' "$LOG_FILE"; then
  printf 'configure.failure=missing-conan\n'
elif rg -q 'Modules/install-(renv|tools|modules)\.R\.in does not exist' "$LOG_FILE"; then
  printf 'configure.failure=incomplete-jasp-sparse-checkout\n'
elif rg -q 'Timeout of [0-9]+ seconds was reached|download of package .renv. failed|there is no package called .renv.' "$LOG_FILE"; then
  printf 'configure.failure=r-package-download-timeout\n'
elif rg -q 'archive.h.*file not found|failed to install .archive.|install-tools\.R failed' "$LOG_FILE"; then
  printf 'configure.failure=r-package-libarchive\n'
elif rg -q 'Could NOT find R\b|Could NOT find Rscript\b|No R installation|R executable.*not found' "$LOG_FILE"; then
  printf 'configure.failure=missing-r\n'
elif rg -q 'IMPORTED_LOCATION not set for imported target .*RELWITHDEBINFO|configuration "RelWithDebInfo"' "$LOG_FILE"; then
  printf 'configure.failure=conan-build-type-mismatch\n'
elif rg -q 'Could NOT find (Qt|Qt6)\b|Qt6.*Config\.cmake.*not found|package .*Qt.*not found' "$LOG_FILE"; then
  printf 'configure.failure=missing-qt\n'
elif rg -q 'no identity found|Signing .* was NOT successful|Signing .*unsuccessful' "$LOG_FILE"; then
  printf 'configure.failure=missing-codesign-identity\n'
elif [ "$cmake_rc" -ne 0 ]; then
  printf 'configure.failure=unknown\n'
else
  printf 'configure.failure=none\n'
fi

printf 'configure.tail.begin\n'
tail -80 "$LOG_FILE"
printf 'configure.tail.end\n'

exit "$cmake_rc"
