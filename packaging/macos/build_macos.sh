#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS bundle must be built on macOS." >&2
  exit 1
fi

python -c "import PyInstaller, webview, platformdirs" >/dev/null
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
