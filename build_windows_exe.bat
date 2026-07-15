@echo off
setlocal
cd /d "%~dp0" || exit /b 1

if "%APP_VERSION%"=="" set APP_VERSION=0.3.35-dev

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required to build the Windows application.
  if "%CI%"=="" pause
  exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
  python -m venv .venv-build
)

call ".venv-build\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
python -m pip install pyinstaller
if errorlevel 1 (
  echo Failed to install build dependencies.
  if "%CI%"=="" pause
  exit /b 1
)

if exist ".playwright-browsers" rmdir /s /q ".playwright-browsers"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\.playwright-browsers"
python -m playwright install chromium --no-shell
if errorlevel 1 (
  echo Failed to download the bundled Chromium runtime.
  if "%CI%"=="" pause
  exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller ^
  --noconfirm ^
  --onedir ^
  --windowed ^
  --name GEO-SOP ^
  --paths "%CD%\web_app" ^
  --add-data "web_app;web_app" ^
  --add-data "platforms;platforms" ^
  --add-data "reference_sentiment;reference_sentiment" ^
  --add-data "tools;tools" ^
  --add-data "version.py;." ^
  --hidden-import flask ^
  --hidden-import flask_login ^
  --hidden-import flask_sqlalchemy ^
  --hidden-import flask_cors ^
  --hidden-import app ^
  --hidden-import config_web ^
  --hidden-import models ^
  --hidden-import local_paths ^
  --hidden-import profile_utils ^
  --hidden-import cloud_sync ^
  --hidden-import login_checker ^
  --hidden-import login_helper ^
  --hidden-import scheduler ^
  --hidden-import remote_worker ^
  --hidden-import playwright ^
  --hidden-import requests ^
  --hidden-import openpyxl ^
  --hidden-import webview ^
  --collect-submodules playwright ^
  --collect-submodules apscheduler ^
  desktop_app.py

if errorlevel 1 (
  echo Windows application build failed.
  if "%CI%"=="" pause
  exit /b 1
)

echo.
echo Build complete: dist\GEO-SOP\GEO-SOP.exe
echo Release version: %APP_VERSION%
echo Chromium runtime: .playwright-browsers
if "%CI%"=="" pause
