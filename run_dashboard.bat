@echo off
title EVA Dashboard - Chitchat Bot
cd /d "%~dp0"

echo.
echo ============================================================
echo    EVA Dashboard - session setup + bot control
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   X  Python NOT FOUND - install Python 3.10+ first
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

echo   [ok] starting dashboard at http://127.0.0.1:8800
echo   [..] browser will open automatically. Keep this window open!
echo.
python -m eva.dashboard.server

echo.
pause
