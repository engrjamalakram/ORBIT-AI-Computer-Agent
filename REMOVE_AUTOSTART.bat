@echo off
setlocal
title Remove ORBIT auto-start

echo.
echo  Removing ORBIT's scheduled tasks...
echo.

schtasks /delete /tn "ORBIT" /f >nul 2>&1
if errorlevel 1 (echo    - "ORBIT" logon task: not found) else (echo    - "ORBIT" logon task removed)

schtasks /delete /tn "ORBIT Watchdog" /f >nul 2>&1
if errorlevel 1 (echo    - watchdog: not found) else (echo    - watchdog removed)

powershell -NoProfile -Command ^
  "$l = Join-Path ([Environment]::GetFolderPath('Startup')) 'ORBIT.lnk';" ^
  "if (Test-Path $l) { Remove-Item $l -Force; Write-Host '    - old Startup shortcut removed' }" 2>nul

echo.
echo  She will no longer start or restart by herself.
echo  (If she is running right now, use STOP_ORBIT.bat to stop her.)
echo.
pause
