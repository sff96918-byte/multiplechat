@echo off
title ChitChat Direct Capture
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python নেই। https://python.org থেকে install করুন।
    pause
    exit /b 1
)

if not exist ".deps_ok" (
    echo [SETUP] Playwright install হচ্ছে...
    python -m pip install -q -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install ব্যর্থ।
        pause
        exit /b 1
    )
    python -m playwright install chromium
    echo ok> .deps_ok
)

echo.
echo  Chrome খুলবে। Login করে নিজে chat করুন।
echo  Terminal-এ লিখতে পারবেন:  note ^<text^>   /  shot   /   quit
echo.
python capture_direct.py --minutes 0
echo.
pause
