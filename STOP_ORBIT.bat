@echo off
setlocal
cd /d "%~dp0"
title Stop ORBIT

echo.
echo  Stopping ORBIT...
echo.

REM Kill the hidden launcher, the restart loop, and the agent process itself.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$killed = 0;" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'agent\.main' -or $_.CommandLine -match 'lappilot-hidden' -or $_.CommandLine -match 'run\.bat') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $killed++ } catch {} };" ^
  "Write-Host ('  Stopped ' + $killed + ' process(es).')"

echo.
echo  ORBIT is stopped. She will start again on your next login unless you also
echo  run DISABLE_AUTOSTART.bat. To start her now, double-click START_ORBIT.bat.
echo.
pause
