@echo off
title EVA - Chitchat.gg WS Bot
cd /d "%~dp0"

echo.
echo ============================================================
echo    EVA - Chitchat.gg Live Chat Bot (WebSocket)
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

if not exist "configs\session.json" (
    echo   X  configs\session.json not found.
    echo.
    echo   Build it first with your logged-in chitchat.gg session:
    echo       python -m ops.tools.extract_session
    echo.
    pause
    exit /b 1
)

echo   [ok] starting bot with debug logging...
echo.
python -m eva.transport.ws_bot --debug

echo.
pause
