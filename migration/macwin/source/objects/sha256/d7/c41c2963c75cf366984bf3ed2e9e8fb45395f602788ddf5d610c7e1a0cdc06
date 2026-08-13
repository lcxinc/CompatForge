#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONAN_HOME_DIR="${MACWIN_JASP_CONAN_HOME:-$PROJECT_ROOT/tmp/jasp-conan-home}"
OLD_URL="https://zlib.net/fossils/zlib-1.2.13.tar.gz"
NEW_URL="https://github.com/madler/zlib/releases/download/v1.2.13/zlib-1.2.13.tar.gz"

patched=0
while IFS= read -r conandata; do
  if grep -q "$OLD_URL" "$conandata"; then
    perl -0pi -e "s#\Q$OLD_URL\E#$NEW_URL#g" "$conandata"
    patched=$((patched + 1))
    printf 'patched.minizipConanData=%s\n' "$conandata"
  fi
done < <(find "$CONAN_HOME_DIR/p" -path '*/miniz*/e/conandata.yml' -type f 2>/dev/null)

if [ "$patched" -eq 0 ]; then
  printf 'patched.minizipConanData=none\n'
else
  printf 'patched.minizipSourceUrl=%s\n' "$NEW_URL"
fi
