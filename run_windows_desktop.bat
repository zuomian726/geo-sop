@echo off
setlocal
cd /d "%~dp0" || (
  echo Cannot enter the GEO-SOP folder. Please extract the ZIP package first.
  pause
  exit /b 1
)

echo ============================================
echo GEO-SOP Windows Desktop
echo ============================================
echo Current folder: %CD%
echo.

set "PYTHON_CMD="
if defined GEO_PYTHON_CMD (
  set "PYTHON_CMD=%GEO_PYTHON_CMD%"
  %PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if errorlevel 1 set "PYTHON_CMD="
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  echo Python 3.10 or later was not found.
  echo Please install Python 3.10 or later and enable "Add python.exe to PATH".
  echo Download: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist "desktop_app.py" (
  echo desktop_app.py was not found.
  echo Please run this script inside the fully extracted GEO-SOP folder.
  pause
  exit /b 1
)

if not exist "requirements-desktop.txt" (
  echo requirements-desktop.txt was not found.
  echo Please fully extract the ZIP first. Do not run from the ZIP preview window.
  pause
  exit /b 1
)

if not exist ".venv-desktop\Scripts\python.exe" (
  echo First launch: creating local runtime...
  %PYTHON_CMD% -m venv .venv-desktop
  if errorlevel 1 (
    echo Failed to create local runtime. Please check your Python installation.
    pause
    exit /b 1
  )
)

call ".venv-desktop\Scripts\activate.bat"
if errorlevel 1 (
  echo Failed to activate local runtime.
  echo You can delete the .venv-desktop folder and run this script again.
  pause
  exit /b 1
)

echo Checking dependencies. The first launch may take a few minutes...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
if errorlevel 1 (
  echo Dependency installation failed. Please check your network and try again.
  pause
  exit /b 1
)

echo Checking Playwright browser runtime...
python -m playwright install chromium
if errorlevel 1 (
  echo Playwright browser installation failed. Please check your network and try again.
  pause
  exit /b 1
)

set GEO_DESKTOP_MODE=1
set NODE_NO_WARNINGS=1
set FLASK_ENV=production
echo.
echo Starting GEO-SOP...
python desktop_app.py
pause
