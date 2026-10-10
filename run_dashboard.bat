@echo off
title EVA Bot - Mood Dashboard
cd /d "%~dp0"

echo.
echo ============================================================
echo    EVA BOT - MOOD DASHBOARD (browser mood + session mood)
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   X  Python NOT FOUND - python.org theke Python 3.10+ install koro
    pause
    exit /b 1
)

python -c "import aiohttp" >nul 2>&1
if errorlevel 1 (
    echo   [..] Installing aiohttp ^(one-time^)...
    pip install aiohttp
    if errorlevel 1 (
        echo   X  pip install failed - run: pip install aiohttp
        pause
        exit /b 1
    )
)

python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo   [..] Installing PyQt6 ^(one-time^)...
    pip install PyQt6
    if errorlevel 1 (
        echo   X  pip install PyQt6 failed - run: pip install PyQt6
        pause
        exit /b 1
    )
)

echo   [ok] Mood Dashboard khulche...
echo.
python -m eva.gui.dashboard

echo.
pause
