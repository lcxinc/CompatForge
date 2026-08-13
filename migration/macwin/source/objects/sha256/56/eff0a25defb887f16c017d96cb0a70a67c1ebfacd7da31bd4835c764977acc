#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output_dir=${1:-"$script_dir/../../tmp/native-ui-probe"}

mkdir -p "$output_dir"

x86_64-w64-mingw32-windres \
    -I "$script_dir/../Sources/MacWinManagerApp/Resources/Icons" \
    "$script_dir/native-ui-probe.rc" \
    --output-format=coff \
    -o "$output_dir/native-ui-probe-x86_64.o"

x86_64-w64-mingw32-gcc \
    -std=c11 -Wall -Wextra -Werror -municode \
    "$script_dir/native-ui-probe.c" "$output_dir/native-ui-probe-x86_64.o" \
    -lcomdlg32 -lcomctl32 -lshell32 -lole32 -luuid \
    -o "$output_dir/native-ui-probe-x86_64.exe"

i686-w64-mingw32-windres \
    -I "$script_dir/../Sources/MacWinManagerApp/Resources/Icons" \
    "$script_dir/native-ui-probe.rc" \
    --output-format=coff \
    -o "$output_dir/native-ui-probe-i686.o"

i686-w64-mingw32-gcc \
    -std=c11 -Wall -Wextra -Werror -municode \
    "$script_dir/native-ui-probe.c" "$output_dir/native-ui-probe-i686.o" \
    -lcomdlg32 -lcomctl32 -lshell32 -lole32 -luuid \
    -o "$output_dir/native-ui-probe-i686.exe"

printf '%s\n' "$output_dir/native-ui-probe-x86_64.exe"
printf '%s\n' "$output_dir/native-ui-probe-i686.exe"
