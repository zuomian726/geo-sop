@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo GEO-SOP requires Python 3. Please install Python 3.10+ from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist ".venv-desktop\\Scripts\\python.exe" (
  python -m venv .venv-desktop
)

call ".venv-desktop\\Scripts\\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
set GEO_DESKTOP_MODE=1
set NODE_NO_WARNINGS=1
set FLASK_ENV=production
python desktop_app.py
pause
