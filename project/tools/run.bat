@echo off
title Multi-Site Bot - Dashboard

cd /d "%~dp0.."

echo.
echo ============================================================
echo    Multi-Site Bot - Dashboard
echo ============================================================
echo.

python -c "import sys; sys.path.insert(0,'src'); from db import Database; print('ok')" >nul 2>&1
if errorlevel 1 (
    echo   FAIL - Core modules not found or broken.
    echo   Run tools\install.bat first.
    echo.
    pause
    exit /b 1
)

cd src
python main.py %*

if errorlevel 1 (
    echo.
    echo   FAIL - Dashboard crashed.
    echo.
    echo   Check:  cd src ^&^& python main.py --debug
    pause
    exit /b 1
)

exit /b 0
