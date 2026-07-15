#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VERSION=$(python3 - <<'PY'
from version import APP_VERSION
print(APP_VERSION)
PY
)
TARGET_ARCH="${GEO_MACOS_ARCH:-$(uname -m)}"
APP_NAME="GEO-SOP"
BUILD_DIR="build"
DIST_DIR="dist"
PACKAGE_DIR="release"
ICON_PNG="web_app/static/img/geo-sop-icon.png"
ICON_ICNS="${BUILD_DIR}/geo-sop-icon.icns"
PYTHON_VERSION="3.12.10"
PYTHON_SERIES="3.12"
PYTHON_PACKAGE="python-${PYTHON_VERSION}-macos11.pkg"
PYTHON_PACKAGE_SHA256="8373e58da4ea146b3eb1c1f9834f19a319440b6b679b06050b1f9ee3237aa8e4"
RUNTIME_CACHE="${PWD}/.build-runtime"
PYTHON_PACKAGE_PATH="${RUNTIME_CACHE}/${PYTHON_PACKAGE}"
FRAMEWORK_ROOT="${RUNTIME_CACHE}/python-${PYTHON_VERSION}"
PYTHON_BASE="${FRAMEWORK_ROOT}/Python.framework/Versions/${PYTHON_SERIES}/bin/python${PYTHON_SERIES}"
RUNTIME_LIBRARY_DIR="${FRAMEWORK_ROOT}/Python.framework/Versions/${PYTHON_SERIES}/lib"

mkdir -p "${RUNTIME_CACHE}"
if [ ! -f "${PYTHON_PACKAGE_PATH}" ]; then
  curl -fL --retry 3 \
    "https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_PACKAGE}" \
    -o "${PYTHON_PACKAGE_PATH}"
fi
echo "${PYTHON_PACKAGE_SHA256}  ${PYTHON_PACKAGE_PATH}" | shasum -a 256 -c -

if [ ! -x "${PYTHON_BASE}" ]; then
  EXPANDED_PACKAGE="${RUNTIME_CACHE}/python-${PYTHON_VERSION}-expanded"
  rm -rf "${EXPANDED_PACKAGE}" "${FRAMEWORK_ROOT}"
  pkgutil --expand-full "${PYTHON_PACKAGE_PATH}" "${EXPANDED_PACKAGE}"
  mkdir -p "${FRAMEWORK_ROOT}/Python.framework/Versions"
  cp -R \
    "${EXPANDED_PACKAGE}/Python_Framework.pkg/Payload/Versions/${PYTHON_SERIES}" \
    "${FRAMEWORK_ROOT}/Python.framework/Versions/${PYTHON_SERIES}"
  ln -s "${PYTHON_SERIES}" "${FRAMEWORK_ROOT}/Python.framework/Versions/Current"
  ln -s "Versions/Current/Python" "${FRAMEWORK_ROOT}/Python.framework/Python"
  rm -rf "${EXPANDED_PACKAGE}"
fi
python3 tools/relocate_macos_python.py "${FRAMEWORK_ROOT}" "${PYTHON_SERIES}"

case "${TARGET_ARCH}" in
  arm64)
    BUILD_VENV=".venv-macos-arm64-py312"
    PACKAGE_SUFFIX="macOS-Apple-Silicon"
    VOLUME_ARCH="Apple Silicon"
    if [ ! -d "${BUILD_VENV}" ]; then
      env DYLD_FRAMEWORK_PATH="${FRAMEWORK_ROOT}" DYLD_LIBRARY_PATH="${RUNTIME_LIBRARY_DIR}" SSL_CERT_FILE="/etc/ssl/cert.pem" "${PYTHON_BASE}" -m venv "${BUILD_VENV}"
    fi
    PYTHON_CMD=(env DYLD_FRAMEWORK_PATH="${FRAMEWORK_ROOT}" DYLD_LIBRARY_PATH="${RUNTIME_LIBRARY_DIR}" SSL_CERT_FILE="/etc/ssl/cert.pem" "${BUILD_VENV}/bin/python")
    ;;
  x86_64)
    BUILD_VENV=".venv-macos-x86_64-py312"
    PACKAGE_SUFFIX="macOS-Intel"
    VOLUME_ARCH="Intel"
    if ! arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
      echo "Rosetta 2 is required to build the Intel macOS package." >&2
      exit 1
    fi
    if [ ! -d "${BUILD_VENV}" ]; then
      arch -x86_64 env DYLD_FRAMEWORK_PATH="${FRAMEWORK_ROOT}" DYLD_LIBRARY_PATH="${RUNTIME_LIBRARY_DIR}" SSL_CERT_FILE="/etc/ssl/cert.pem" "${PYTHON_BASE}" -m venv "${BUILD_VENV}"
    fi
    PYTHON_CMD=(arch -x86_64 env DYLD_FRAMEWORK_PATH="${FRAMEWORK_ROOT}" DYLD_LIBRARY_PATH="${RUNTIME_LIBRARY_DIR}" SSL_CERT_FILE="/etc/ssl/cert.pem" "${BUILD_VENV}/bin/python")
    ;;
  *)
    echo "Unsupported macOS build architecture: ${TARGET_ARCH}" >&2
    exit 1
    ;;
esac

"${PYTHON_CMD[@]}" -m pip install --upgrade pip
"${PYTHON_CMD[@]}" -m pip install -r requirements-desktop.txt
"${PYTHON_CMD[@]}" -m pip install pyinstaller

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

MACOSX_DEPLOYMENT_TARGET=11.0 "${PYTHON_CMD[@]}" -m PyInstaller "${PYINSTALLER_ARGS[@]}" desktop_app.py

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

BUILT_ARCH=$(lipo -archs "${DIST_DIR}/${APP_NAME}.app/Contents/MacOS/${APP_NAME}")
if [ "${BUILT_ARCH}" != "${TARGET_ARCH}" ]; then
  echo "Built application architecture ${BUILT_ARCH} does not match requested ${TARGET_ARCH}." >&2
  exit 1
fi
python3 tools/verify_macos_bundle.py "${DIST_DIR}/${APP_NAME}.app" "${TARGET_ARCH}" "12.0"

DMG_PATH="${PACKAGE_DIR}/${APP_NAME}-v${VERSION}-${PACKAGE_SUFFIX}.dmg"
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
  -volname "${APP_NAME} ${VOLUME_ARCH} v${VERSION}" \
  -srcfolder "${DMG_STAGE}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

shasum -a 256 "${DMG_PATH}" > "${DMG_PATH}.sha256"
echo "Built ${DMG_PATH} (${TARGET_ARCH})"
