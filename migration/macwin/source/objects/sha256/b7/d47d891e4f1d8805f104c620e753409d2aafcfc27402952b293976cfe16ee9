#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${MACWIN_JASP_CONAN_VENV:-$PROJECT_ROOT/tmp/jasp-conan-venv}"
CONAN_HOME_DIR="${MACWIN_JASP_CONAN_HOME:-$PROJECT_ROOT/tmp/jasp-conan-home}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

die() {
  printf 'error=%s\n' "$*" >&2
  exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "missing python: $PYTHON_BIN"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools
"$VENV_DIR/bin/python" -m pip install 'conan>=2,<3'
mkdir -p "$CONAN_HOME_DIR"
CONAN_HOME="$CONAN_HOME_DIR" "$VENV_DIR/bin/conan" profile detect --force

printf 'conan.venv=%s\n' "$VENV_DIR"
printf 'conan.home=%s\n' "$CONAN_HOME_DIR"
printf 'conan.path=%s\n' "$VENV_DIR/bin/conan"
CONAN_HOME="$CONAN_HOME_DIR" "$VENV_DIR/bin/conan" --version | sed 's/^/conan.version=/'
CONAN_HOME="$CONAN_HOME_DIR" "$VENV_DIR/bin/conan" profile path default | sed 's/^/conan.defaultProfile=/'
