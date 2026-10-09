@echo off
title Multi-Site Bot - Installer
setlocal enabledelayedexpansion

cd /d "%~dp0.."

set OK_PKG=0
set MISSING=0
set MISSING_LIST=
set CHROMIUM_OK=0
set MOD_OK=0
set MOD_FAIL=0
set PIP_FAIL=0
set NODE_FOUND=0

echo.
echo ============================================================
echo    Multi-Site Bot - Installer / Updater
echo ============================================================
echo.
echo [CHECK] System...
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   X  Python NOT FOUND
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   OK  Python %%v

where pip >nul 2>&1
if errorlevel 1 (
    echo   X  pip NOT FOUND
    pause
    exit /b 1
)
echo   OK  pip

where node >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2" %%v in ('node --version 2^>^&1') do (
        echo   OK  Node %%v
        set NODE_FOUND=1
    )
)
if !NODE_FOUND!==0 echo   -- Node.js not found ^(Playwright may need it^)

echo.
echo ============================================================
echo [1/3] Python packages
echo ============================================================
echo.

for /f "usebackq delims=" %%l in ("src\requirements.txt") do (
    set INPUT_LINE=%%l
    for /f "tokens=1 delims=;=<>~ " %%p in ("!INPUT_LINE!") do (
        set CURRENT_PKG=%%p
        set SKIP=0
        if "!CURRENT_PKG!"=="" set SKIP=1
        if "!CURRENT_PKG:~0,1!"=="#" set SKIP=1
        if !SKIP!==0 (
            pip show !CURRENT_PKG! >nul 2>&1
            if errorlevel 1 (
                echo   MISSING   !CURRENT_PKG!
                set /a MISSING+=1
                set MISSING_LIST=!MISSING_LIST! !CURRENT_PKG!
            ) else (
                for /f "tokens=2" %%v in ('pip show !CURRENT_PKG! 2^>nul ^| findstr /c:"Version:"') do echo   OK        !CURRENT_PKG!  v%%v
                set /a OK_PKG+=1
            )
        )
    )
)

echo.
if !MISSING! gtr 0 (
    echo   Installing !MISSING! missing package^(s^)...
    echo.
    pip install !MISSING_LIST!
    if errorlevel 1 (
        set PIP_FAIL=1
    ) else (
        set /a OK_PKG=!OK_PKG! + !MISSING!
        set MISSING=0
        echo   OK  Installed
    )
) else (
    echo   All packages already installed.
)

echo.
echo ============================================================
echo [2/3] Playwright Chromium
echo ============================================================
echo.

python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo   MISSING   Chromium browser
    echo   Downloading ^(~150MB, one-time^)...
    echo.
    python -m playwright install chromium
    if errorlevel 1 (
        echo   FAILED    Chromium install
        set CHROMIUM_OK=0
    ) else (
        echo   OK        Chromium installed
        set CHROMIUM_OK=1
    )
) else (
    echo   OK        Chromium browser ready
    set CHROMIUM_OK=1
)

echo.
echo ============================================================
echo [3/3] Module verification
echo ============================================================
echo.

python -c "import sys; sys.path.insert(0,'src'); from db import Database" 2>nul
if errorlevel 1 (echo   FAIL  db.py& set /a MOD_FAIL+=1) else (echo   OK    db.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from reply_engine import ReplyEngine" 2>nul
if errorlevel 1 (echo   FAIL  reply_engine.py& set /a MOD_FAIL+=1) else (echo   OK    reply_engine.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from proxy_manager import ProxyManager" 2>nul
if errorlevel 1 (echo   FAIL  proxy_manager.py& set /a MOD_FAIL+=1) else (echo   OK    proxy_manager.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from fixed_sms_engine import FixedSmsEngine" 2>nul
if errorlevel 1 (echo   FAIL  fixed_sms_engine.py& set /a MOD_FAIL+=1) else (echo   OK    fixed_sms_engine.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from debug_utils import DebugLogger" 2>nul
if errorlevel 1 (echo   FAIL  debug_utils.py& set /a MOD_FAIL+=1) else (echo   OK    debug_utils.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from sites.joingy import JoingyBot" 2>nul
if errorlevel 1 (echo   FAIL  sites/joingy.py& set /a MOD_FAIL+=1) else (echo   OK    sites/joingy.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from sites.isexychat import IsexychatBot" 2>nul
if errorlevel 1 (echo   FAIL  sites/isexychat.py& set /a MOD_FAIL+=1) else (echo   OK    sites/isexychat.py& set /a MOD_OK+=1)

python -c "import sys; sys.path.insert(0,'src'); from dashboard.cli import BotDashboard" 2>nul
if errorlevel 1 (echo   FAIL  dashboard/cli.py& set /a MOD_FAIL+=1) else (echo   OK    dashboard/cli.py& set /a MOD_OK+=1)

echo.
echo ============================================================
echo    FINAL REPORT
echo ============================================================
echo.
echo    Packages  :  !OK_PKG! installed / !MISSING! missing
echo    Chromium   :  !CHROMIUM_OK! ready
echo    Modules   :  !MOD_OK! loaded / !MOD_FAIL! failed
echo.

if !PIP_FAIL!==1 echo    X  pip install failed for some packages
if !MISSING! gtr 0 echo    X  Run install.bat again to retry missing packages
if !CHROMIUM_OK!==0 echo    X  iSexyChat bot won^'t work without Chromium
if !MOD_FAIL! gtr 0 echo    X  Some source files have errors

if !MISSING! equ 0 if !MOD_FAIL! equ 0 if !CHROMIUM_OK!==1 (
    echo    ALL GOOD - Ready to run
    echo.
    echo    Run:  tools\run.bat
    echo.
)

pause
exit /b 0
