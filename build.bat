@echo off
setlocal enabledelayedexpansion
title FIFA Predictor -- Building .exe

echo ============================================================
echo  FIFA World Cup 2026 Predictor -- Desktop App Builder
echo ============================================================
echo.

:: Make sure we're in the right directory (where this .bat lives)
cd /d "%~dp0"

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Make sure Python is installed and
    echo        added to PATH, then re-run this script.
    pause
    exit /b 1
)

echo [1/4] Installing / updating Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [2/4] Installing PyInstaller, pystray, and Pillow...
pip install pyinstaller pystray pillow --quiet
if errorlevel 1 (
    echo ERROR: Could not install build tools.
    pause
    exit /b 1
)

echo [3/4] Building FIFA Predictor.exe with PyInstaller...
echo       (This takes 1-3 minutes -- please wait)
echo.
python -m PyInstaller predictor.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See the output above for details.
    pause
    exit /b 1
)

echo.
echo [4/4] Setting up data folder next to the exe...
if not exist "dist\data\raw"       mkdir "dist\data\raw"
if not exist "dist\data\processed" mkdir "dist\data\processed"
if not exist "dist\logs"           mkdir "dist\logs"

echo.
echo ============================================================
echo  BUILD SUCCESSFUL
echo ============================================================
echo.
echo  Your app is ready at:
echo    dist\FIFA Predictor.exe
echo.
echo  Double-click it to launch the dashboard.
echo  The first run will download the data (~5 MB) automatically.
echo.
echo  To share with someone: copy the entire dist\ folder.
echo  The .exe needs the data\ subfolder next to it to run.
echo.
pause
