#!/bin/bash
# Host test of the remote parser. Run from anywhere: bash arduino/host_test/run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
sketch="$here/../hai_zeitreise/hai_zeitreise.ino"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
sed -n '/---- remote parser (pure)/,/---- end remote parser/p' "$sketch" > "$work/remote_block.inc"
if [ ! -s "$work/remote_block.inc" ]; then
  echo "FAIL: remote parser block not found in $sketch"
  exit 1
fi
c++ -std=c++17 -Wall -Wextra -Werror -I"$work" -o "$work/remote_test" "$here/remote_test.cpp"
"$work/remote_test"
