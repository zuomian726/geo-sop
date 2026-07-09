@echo off
setlocal
cd /d "%~dp0" || (
  echo Cannot open the GEO-SOP folder. Please extract the ZIP package first.
  pause
  exit /b 1
)

echo This installer uses the same desktop launcher.
echo Please keep this window open during the first launch.
echo.
call "%~dp0Start GEO-SOP.bat"
