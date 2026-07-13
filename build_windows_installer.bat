@echo off
setlocal
cd /d "%~dp0" || exit /b 1

if "%APP_VERSION%"=="" set APP_VERSION=0.3.17-dev

where ISCC.exe >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "PATH=%ProgramFiles(x86)%\Inno Setup 6;%PATH%"
  ) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "PATH=%ProgramFiles%\Inno Setup 6;%PATH%"
  ) else (
    echo Inno Setup was not found.
    echo Install Inno Setup 6, then run this script again:
    echo https://jrsoftware.org/isdl.php
    if "%CI%"=="" pause
    exit /b 1
  )
)

if not exist "release" mkdir release
ISCC.exe /DMyAppVersion=%APP_VERSION% installer\windows\GEO-SOP.iss
if errorlevel 1 (
  echo Windows installer build failed.
  if "%CI%"=="" pause
  exit /b 1
)

echo.
echo Build complete: release\GEO-SOP-Setup-v%APP_VERSION%.exe
if "%CI%"=="" pause
