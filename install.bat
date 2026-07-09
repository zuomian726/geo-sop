@echo off
setlocal
cd /d "%~dp0" || (
  echo Cannot open the GEO-SOP folder. Please extract the ZIP package first.
  pause
  exit /b 1
)

call "%~dp0Install GEO-SOP.bat"
