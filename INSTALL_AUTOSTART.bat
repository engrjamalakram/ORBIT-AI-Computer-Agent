@echo off
cd /d "%~dp0"
title ORBIT auto-start

REM --- need admin to create scheduled tasks: re-launch elevated if we are not ---
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ORBIT's auto-start needs Administrator rights once.
  echo  Windows will now ask for permission - click YES.
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo.
echo  ==================================================
echo    Making ORBIT start and stay running by herself
echo  ==================================================
echo.
echo  This replaces the plain Startup-folder shortcut, which only ran
echo  after you logged in manually and was delayed by Windows - that is
echo  why she did not come back on her own after the power cut.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_autostart.ps1"

echo.
echo  ==================================================
echo    Done.
echo  ==================================================
echo.
echo  From now on:
echo    - She starts as soon as you log in.
echo    - A watchdog checks every 3 minutes and restarts her if she is
echo      not running (crash, outage, reboot).
echo    - While the internet is down she keeps retrying and connects the
echo      moment it returns, then messages you "back online" on Discord.
echo    - Works on battery too (normally Windows blocks tasks on battery).
echo.
echo  IMPORTANT for the power-cut case: read AUTOSTART-NOTES.txt
echo  Windows must log in by itself, or nothing can run at all.
echo.
pause
