@echo off
title EVA Dashboard - EXE Builder
cd /d "%~dp0"

echo.
echo ============================================================
echo    EVA Dashboard - EXE Builder (one-time, needs internet)
echo    NOTE: zip-er vitore ready-made EXE thake na!
echo    ei script tomar PC-te notun EXE banabe.
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   X  Python NOT FOUND - install Python 3.10+ first
    pause
    exit /b 1
)

echo   [1/4] Checking packages...
python -c "import PyQt6" >nul 2>&1 || pip install PyQt6
python -c "import aiohttp" >nul 2>&1 || pip install aiohttp
python -c "import psutil" >nul 2>&1 || pip install psutil
python -c "import PyInstaller" >nul 2>&1 || pip install pyinstaller

echo   [2/4] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo   [3/4] Building exe (2-5 minutes)...
python -m PyInstaller --noconfirm EVA_Dashboard.spec
if errorlevel 1 (
    echo.
    echo   X  BUILD FAILED - error upar dekho. Screenshot niye amake pathao.
    pause
    exit /b 1
)

echo   [4/4] Copying configs next to exe...
if not exist "dist\EVA Dashboard\configs" mkdir "dist\EVA Dashboard\configs"
copy /y "configs\fixed_script.txt" "dist\EVA Dashboard\configs\" >nul
copy /y "configs\fixed_script.example.txt" "dist\EVA Dashboard\configs\" >nul
copy /y "configs\snap.txt.example" "dist\EVA Dashboard\configs\" >nul
copy /y "configs\chitchat_bot.example.json" "dist\EVA Dashboard\configs\" >nul
copy /y "configs\session.example.json" "dist\EVA Dashboard\configs\" >nul

echo.
echo ============================================================
echo    EXE READY:
echo    dist\EVA Dashboard\EVA Dashboard.exe
echo.
echo    - exe chalate "EVA Dashboard" FOLDER ta puro copy koro
echo      (exe + _internal folder + configs -- sob lagbe!)
echo    - exe double-click = dashboard (console window chhara)
echo    - desktop shortcut banate chaile:
echo        powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\EVA Bot.lnk');$s.TargetPath=(Resolve-Path 'dist\EVA Dashboard\EVA Dashboard.exe').Path;$s.WorkingDirectory=(Resolve-Path 'dist\EVA Dashboard').Path;$s.Save()"
echo ============================================================
echo.
explorer "dist\EVA Dashboard"
pause
