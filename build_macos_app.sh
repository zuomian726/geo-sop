#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VERSION=$(python3 - <<'PY'
from version import APP_VERSION
print(APP_VERSION)
PY
)
APP_NAME="GEO-SOP"
BUILD_DIR="build"
DIST_DIR="dist"
PACKAGE_DIR="release"
ICON_PNG="web_app/static/img/geo-sop-icon.png"
ICON_ICNS="${BUILD_DIR}/geo-sop-icon.icns"

if [ ! -d ".venv-build" ]; then
  python3 -m venv .venv-build
fi

source .venv-build/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
python -m pip install pyinstaller

rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${BUILD_DIR}" "${PACKAGE_DIR}"

if [ -f "${ICON_PNG}" ]; then
  ICONSET="${BUILD_DIR}/geo-sop.iconset"
  mkdir -p "${ICONSET}"
  for size in 16 32 64 128 256 512; do
    sips -z "${size}" "${size}" "${ICON_PNG}" --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null
  done
  sips -z 32 32 "${ICON_PNG}" --out "${ICONSET}/icon_16x16@2x.png" >/dev/null
  sips -z 64 64 "${ICON_PNG}" --out "${ICONSET}/icon_32x32@2x.png" >/dev/null
  sips -z 256 256 "${ICON_PNG}" --out "${ICONSET}/icon_128x128@2x.png" >/dev/null
  sips -z 512 512 "${ICON_PNG}" --out "${ICONSET}/icon_256x256@2x.png" >/dev/null
  sips -z 1024 1024 "${ICON_PNG}" --out "${ICONSET}/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "${ICONSET}" -o "${ICON_ICNS}"
fi

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --argv-emulation
  --name "${APP_NAME}"
  --add-data "web_app:web_app"
  --add-data "platforms:platforms"
  --add-data "reference_sentiment:reference_sentiment"
  --add-data "tools:tools"
  --add-data "version.py:."
  --hidden-import flask
  --hidden-import flask_login
  --hidden-import flask_sqlalchemy
  --hidden-import flask_cors
  --hidden-import playwright
  --hidden-import requests
  --hidden-import openpyxl
  --hidden-import PIL
  --hidden-import local_paths
  --hidden-import profile_utils
  --hidden-import browser_config
  --hidden-import browser_utils
  --hidden-import config
  --hidden-import utils
  --collect-submodules playwright
  --collect-submodules apscheduler
)

if [ -f "${ICON_ICNS}" ]; then
  PYINSTALLER_ARGS+=(--icon "${ICON_ICNS}")
fi

pyinstaller "${PYINSTALLER_ARGS[@]}" desktop_app.py

PLIST_PATH="${DIST_DIR}/${APP_NAME}.app/Contents/Info.plist"
APP_RESOURCES="${DIST_DIR}/${APP_NAME}.app/Contents/Resources"
if [ -d "${APP_RESOURCES}/web_app" ]; then
  rm -rf \
    "${APP_RESOURCES}/web_app/answers" \
    "${APP_RESOURCES}/web_app/instance" \
    "${APP_RESOURCES}/web_app/browser_profiles" \
    "${APP_RESOURCES}/web_app/uploads" \
    "${APP_RESOURCES}/web_app/exports" \
    "${APP_RESOURCES}/web_app/__pycache__"
fi
if [ -f "${PLIST_PATH}" ]; then
  plutil -replace CFBundleShortVersionString -string "${VERSION}" "${PLIST_PATH}"
  plutil -replace CFBundleVersion -string "$(python3 - <<'PY'
from version import BUILD_NUMBER
print(BUILD_NUMBER)
PY
)" "${PLIST_PATH}"
  plutil -replace CFBundleIdentifier -string "com.tukemarketing.geosop" "${PLIST_PATH}"
  python3 - "${PLIST_PATH}" <<'PY'
import plistlib
import sys

path = sys.argv[1]
with open(path, "rb") as f:
    plist = plistlib.load(f)
plist["CFBundleURLTypes"] = [
    {
        "CFBundleURLName": "GEO-SOP URL",
        "CFBundleURLSchemes": ["geo-sop"],
    }
]
with open(path, "wb") as f:
    plistlib.dump(plist, f)
PY
  codesign --force --deep --sign - "${DIST_DIR}/${APP_NAME}.app"
fi

DMG_PATH="${PACKAGE_DIR}/${APP_NAME}-v${VERSION}-macOS.dmg"
DMG_STAGE="${BUILD_DIR}/dmg-stage"
rm -f "${DMG_PATH}"
rm -rf "${DMG_STAGE}"
mkdir -p "${DMG_STAGE}"
cp -R "${DIST_DIR}/${APP_NAME}.app" "${DMG_STAGE}/${APP_NAME}.app"
ln -s /Applications "${DMG_STAGE}/Applications"
cat > "${DMG_STAGE}/安装说明.txt" <<TXT
GEO-SOP macOS 安装说明

1. 将 GEO-SOP.app 拖到右侧 Applications 文件夹。
2. 打开“应用程序”文件夹里的 GEO-SOP。
3. 如果 macOS 提示“Apple 无法验证”，请进入：
   系统设置 -> 隐私与安全性 -> 仍要打开。

开发版临时处理方式：
xattr -dr com.apple.quarantine "/Applications/GEO-SOP.app"

提示：
- 请不要直接在 DMG 窗口中长期运行 App。
- 平台登录、浏览器采集和截图会在本机完成。
- 云端账号用于同步任务和分析结果。
TXT
hdiutil create \
  -volname "${APP_NAME} v${VERSION}" \
  -srcfolder "${DMG_STAGE}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

shasum -a 256 "${DMG_PATH}" > "${DMG_PATH}.sha256"
echo "Built ${DMG_PATH}"
