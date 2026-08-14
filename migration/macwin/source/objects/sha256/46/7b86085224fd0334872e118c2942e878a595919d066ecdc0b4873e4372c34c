#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${MACWIN_ROSETTA_X87_SOURCE:-$ROOT/refs/rosettax87}"
BUILD="${MACWIN_ROSETTA_X87_BUILD:-$SOURCE/build}"
WINE_LOADER="${MACWIN_WINE_LOADER:-$ROOT/refs/Whisky-wow64-game-build/loader/wine}"

if [[ ! -f "$SOURCE/CMakeLists.txt" ]]; then
  echo "Missing rosettax87 source: $SOURCE" >&2
  exit 1
fi
if [[ ! -x "$WINE_LOADER" ]]; then
  echo "Missing Wine loader: $WINE_LOADER" >&2
  exit 1
fi

cmake -S "$SOURCE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --parallel "${MACWIN_BUILD_JOBS:-8}"

codesign --force --sign - --entitlements "$SOURCE/entitlements.plist" "$WINE_LOADER"
codesign --verify --strict "$BUILD/rosettax87"
codesign --verify --strict "$WINE_LOADER"

printf 'rosettax87=%s\n' "$BUILD/rosettax87"
printf 'wine_loader=%s\n' "$WINE_LOADER"
