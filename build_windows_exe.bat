@echo off
setlocal
cd /d "%~dp0"
set APP_VERSION=0.3.8-dev

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required to build the Windows EXE.
  pause
  exit /b 1
)

if not exist ".venv-build\\Scripts\\python.exe" (
  python -m venv .venv-build
)

call ".venv-build\\Scripts\\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
python -m pip install pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller ^
  --noconfirm ^
  --onedir ^
  --windowed ^
  --name GEO-SOP ^
  --add-data "web_app;web_app" ^
  --add-data "platforms;platforms" ^
  --add-data "reference_sentiment;reference_sentiment" ^
  --add-data "tools;tools" ^
  --add-data "version.py;." ^
  --add-data "requirements-desktop.txt;." ^
  --hidden-import flask ^
  --hidden-import flask_login ^
  --hidden-import flask_sqlalchemy ^
  --hidden-import flask_cors ^
  --hidden-import playwright ^
  --hidden-import requests ^
  --hidden-import openpyxl ^
  desktop_app.py

echo.
echo Build complete: dist\\GEO-SOP\\GEO-SOP.exe
echo Release version: %APP_VERSION%
echo Copy the whole dist\\GEO-SOP folder when distributing the Windows build.
pause
