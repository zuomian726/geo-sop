@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || (
  echo 无法进入 GEO-SOP 程序目录，请确认压缩包已经完整解压。
  pause
  exit /b 1
)

echo ============================================
echo GEO-SOP Windows 桌面版
echo ============================================
echo 当前目录: %CD%
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Python。
  echo 请先安装 Python 3.10 或以上版本，并勾选 Add python.exe to PATH。
  echo 下载地址: https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

if not exist "desktop_app.py" (
  echo 未找到 desktop_app.py。
  echo 请确认你是在完整解压后的 GEO-SOP 文件夹内运行本脚本。
  pause
  exit /b 1
)

if not exist "requirements-desktop.txt" (
  echo 未找到 requirements-desktop.txt。
  echo 请确认压缩包已经完整解压，不要在压缩包预览窗口里直接运行。
  pause
  exit /b 1
)

if not exist ".venv-desktop\Scripts\python.exe" (
  echo 首次运行：正在创建本地运行环境...
  python -m venv .venv-desktop
  if errorlevel 1 (
    echo 创建运行环境失败，请检查 Python 是否可用。
    pause
    exit /b 1
  )
)

call ".venv-desktop\Scripts\activate.bat"
if errorlevel 1 (
  echo 启动本地运行环境失败。
  echo 可以删除 .venv-desktop 文件夹后重新运行本脚本。
  pause
  exit /b 1
)

echo 正在检查依赖，首次运行可能需要几分钟...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
if errorlevel 1 (
  echo 依赖安装失败，请检查网络连接后重试。
  pause
  exit /b 1
)

set GEO_DESKTOP_MODE=1
set NODE_NO_WARNINGS=1
set FLASK_ENV=production
echo.
echo 正在启动 GEO-SOP...
python desktop_app.py
pause
