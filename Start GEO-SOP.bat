@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || (
  echo Cannot open the GEO-SOP folder. Please extract the ZIP package first.
  pause
  exit /b 1
)

call "%~dp0run_windows_desktop.bat"
