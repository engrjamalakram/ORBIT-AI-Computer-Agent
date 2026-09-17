@echo off
setlocal
title Disable ORBIT auto-start

echo.
echo  Removing ORBIT from Windows startup...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'ORBIT.lnk';" ^
  "if (Test-Path $link) { Remove-Item $link -Force; Write-Host '  Removed - she will no longer start automatically.' } else { Write-Host '  Auto-start was not enabled.' }"

echo.
echo  (She may still be running right now - use STOP_ORBIT.bat to stop this session.)
echo.
pause
