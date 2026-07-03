@echo off
setlocal enabledelayedexpansion

echo ============================================
echo Force reinstall project dependencies
echo ============================================

:: Check and remove existing virtual environment in web_app
if exist "web_app\venv" (
    echo [1/4] Found existing venv in web_app, removing...
    rmdir /s /q "web_app\venv"
    if !errorlevel! equ 0 (
        echo       Successfully removed old venv
    ) else (
        echo       Remove failed, continue...
    )
)

:: Also remove .venv in root if exists (cleanup)
if exist ".venv" (
    echo       Cleaning up old .venv in root...
    rmdir /s /q ".venv"
)

:: Create new virtual environment in web_app
echo [2/4] Creating new virtual environment in web_app...
python -m venv web_app\venv
if !errorlevel! equ 0 (
    echo       Virtual environment created successfully
) else (
    echo       Failed to create virtual environment, check Python installation
    pause
    exit /b 1
)

:: Activate and install dependencies
echo [3/4] Activating venv and installing dependencies...
call web_app\venv\Scripts\activate.bat

:: Upgrade pip
echo       Upgrading pip...
python -m pip install --upgrade pip

:: Install requirements
echo       Installing project dependencies...
pip install -r requirements.txt
if !errorlevel! equ 0 (
    echo       Dependencies installed successfully
) else (
    echo       Failed to install dependencies
    pause
    exit /b 1
)

:: Install playwright browsers
echo [4/4] Installing Playwright browsers...
playwright install
if !errorlevel! equ 0 (
    echo       Playwright browsers installed successfully
) else (
    echo       Playwright browsers installation failed (optional)
)

echo.
echo ============================================
echo Installation complete!
echo To start the project, run:
echo   cd web_app
echo   venv\Scripts\activate.bat
echo   python app.py
echo ============================================
pause