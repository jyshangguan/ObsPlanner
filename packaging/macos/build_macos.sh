#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS bundle must be built on macOS." >&2
  exit 1
fi

python -c "import PyInstaller, webview, platformdirs" >/dev/null

# Refuse Pythons whose ssl module loads extra CA data from beside ssl.py
# (the codex runtime does this): PyInstaller does not bundle that file,
# and every TLS connection in the frozen app would then fail. Build with
# the observations environment instead.
ssl_dir="$(python -c 'import os, ssl; print(os.path.dirname(ssl.__file__))')"
if [[ -f "$ssl_dir/codex-rejected-cas.pem" ]]; then
  echo "This Python's ssl module loads codex-rejected-cas.pem next to ssl.py," >&2
  echo "which PyInstaller does not bundle, so the frozen app would have no TLS." >&2
  echo "Build with the 'observations' environment instead." >&2
  exit 1
fi

python -m PyInstaller \
  --clean \
  --noconfirm \
  --distpath "$project_root/dist" \
  --workpath "$project_root/build/pyinstaller" \
  "$project_root/packaging/macos/ObsPlanner.spec"

app_path="$project_root/dist/ObsPlanner.app"
test -d "$app_path"
echo "Built $app_path"

if [[ "${OBSPLANNER_ADHOC_SIGN:-0}" == "1" ]]; then
  codesign --force --deep --sign - "$app_path"
  codesign --verify --deep --strict --verbose=2 "$app_path"
  echo "Applied an ad-hoc signature to $app_path"
fi
