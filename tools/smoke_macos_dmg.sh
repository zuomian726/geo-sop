#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 DMG_PATH EXPECTED_ARCH [EXPECTED_VERSION]" >&2
  exit 2
fi

DMG_PATH=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
EXPECTED_ARCH="$2"
EXPECTED_VERSION="${3:-}"
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

(
  work_dir=$(mktemp -d "/tmp/geo-sop-dmg-smoke.XXXXXX")
  mount_dir="$work_dir/mount"
  install_dir="$work_dir/Applications"
  data_dir="$work_dir/data"
  app_log="$work_dir/app.log"
  cookie_jar="$work_dir/cookies"
  app_pid=""

  cleanup() {
    if [ -n "$app_pid" ]; then
      kill "$app_pid" >/dev/null 2>&1 || true
      wait "$app_pid" >/dev/null 2>&1 || true
    fi
    hdiutil detach "$mount_dir" -force >/dev/null 2>&1 || true
    rm -rf "$work_dir"
  }
  trap cleanup EXIT

  mkdir -p "$mount_dir" "$install_dir" "$data_dir"
  hdiutil attach -readonly -nobrowse -mountpoint "$mount_dir" "$DMG_PATH" >/dev/null
  test -L "$mount_dir/Applications"
  test -f "$mount_dir/安装说明.txt"
  ditto "$mount_dir/GEO-SOP.app" "$install_dir/GEO-SOP.app"

  app="$install_dir/GEO-SOP.app"
  actual_arch=$(lipo -archs "$app/Contents/MacOS/GEO-SOP")
  if [ "$actual_arch" != "$EXPECTED_ARCH" ]; then
    echo "Expected $EXPECTED_ARCH, found $actual_arch" >&2
    exit 1
  fi
  codesign --verify --deep --strict "$app"
  python3 "$ROOT_DIR/tools/verify_macos_bundle.py" "$app" "$EXPECTED_ARCH" 12.0

  env \
    GEO_DATA_DIR="$data_dir" \
    GEO_FORCE_BROWSER=1 \
    BROWSER=/usr/bin/true \
    GEO_DEBUG_BOOT=1 \
    GEO_BOOT_LOG_PATH="$work_dir/boot.log" \
    "$app/Contents/MacOS/GEO-SOP" >"$app_log" 2>&1 &
  app_pid=$!

  app_url=""
  for _ in $(seq 1 120); do
    app_url=$(sed -n 's/.*desktop server: \(http[^ ]*\).*/\1/p' "$app_log" | tail -1)
    if [ -n "$app_url" ]; then
      break
    fi
    if ! kill -0 "$app_pid" >/dev/null 2>&1; then
      cat "$app_log" >&2
      exit 1
    fi
    sleep 0.25
  done
  if [ -z "$app_url" ]; then
    echo "Packaged application did not expose its local URL" >&2
    cat "$app_log" >&2
    exit 1
  fi

  base_url=${app_url%/}
  base_url=${base_url%/dashboard}
  curl -fsS --max-time 10 -c "$cookie_jar" \
    -H 'Content-Type: application/json' \
    -d '{"username":"package-smoke","email":"package-smoke@example.invalid","password":"smoke-test-only"}' \
    "$base_url/register" >"$work_dir/register.json"
  curl -fsS --max-time 10 -b "$cookie_jar" \
    "$base_url/api/app-info" >"$work_dir/app-info.json"
  curl -fsS --max-time 10 -b "$cookie_jar" \
    -H 'Content-Type: application/json' \
    -d '{"browser_path":"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}' \
    "$base_url/api/browser/config" >"$work_dir/browser-config.json"

  python3 - "$work_dir/app-info.json" "$work_dir/browser-config.json" "$EXPECTED_VERSION" <<'PY'
import json
import sys

app_info = json.load(open(sys.argv[1], encoding="utf-8"))
browser_config = json.load(open(sys.argv[2], encoding="utf-8"))
expected_version = sys.argv[3]
assert app_info.get("success") is True, app_info
assert app_info.get("desktop_mode") is True, app_info
assert browser_config.get("success") is True, browser_config
if expected_version:
    assert app_info["app"]["version"] == expected_version, app_info
PY

  test -f "$data_dir/browser_config.json"
  grep -q 'Google Chrome.app' "$data_dir/browser_config.json"
  test ! -e "$app/Contents/Resources/browser_config.json"
  codesign --verify --deep --strict "$app"
  echo "DMG smoke test passed: arch=$actual_arch url=$app_url"
)
