@echo off
setlocal
cd /d "%~dp0" || (
  echo Cannot open the GEO-SOP folder. Please extract the ZIP package first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install GEO-SOP.ps1"
if errorlevel 1 (
  echo.
  echo GEO-SOP installation did not complete.
  pause
  exit /b 1
)
