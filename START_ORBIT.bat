@echo off
setlocal
cd /d "%~dp0"
title Start ORBIT

echo.
echo  ============================================
echo    Starting ORBIT + enabling auto-start
echo  ============================================
echo.

REM --- 1. Make sure the virtual environment exists ---
if not exist ".venv\Scripts\python.exe" (
    echo  First time here - installing. This takes a couple of minutes...
    echo.
    call install.bat
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [X] Install did not complete. Run install.bat and watch for errors.
    echo.
    pause
    exit /b 1
)

REM --- 2. Check .env configuration ---
echo  Checking your settings...
".venv\Scripts\python.exe" -c "from agent.config import validate; print(validate())"

if errorlevel 1 (
    echo.
    echo  [X] Could not validate your .env configuration.
    echo.
    pause
    exit /b 1
)

echo  Settings look good.
echo.

REM --- 3. Enable auto-start at Windows login ---
echo  Enabling auto-start at login...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'ORBIT.lnk'; $w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut($link); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%~dp0lappilot-hidden.vbs\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'ORBIT laptop agent'; $s.Save()" >nul 2>&1

echo  Done - ORBIT will start automatically at login.
echo.

REM --- 4. Start ORBIT now, hidden ---
echo  Starting ORBIT now...
wscript.exe "%~dp0lappilot-hidden.vbs"

REM --- 5. Confirm ORBIT started ---
timeout /t 8 /nobreak >nul

tasklist /fi "imagename eq python.exe" 2>nul | find /i "python.exe" >nul

if errorlevel 1 (
    echo.
    echo  [!] Could not confirm ORBIT is running.
    echo      Run run.bat manually to see any error message.
) else (
    echo.
    echo  ============================================
    echo    ORBIT is RUNNING in the background.
    echo  ============================================
    echo.
    echo  - Open Discord on your phone and DM the bot: /help
    echo  - ORBIT will auto-start every time you log in.
    echo  - To stop ORBIT: double-click STOP_ORBIT.bat
    echo  - To disable auto-start: double-click DISABLE_AUTOSTART.bat
)

echo.
echo  You can close this window now.
echo.
pause