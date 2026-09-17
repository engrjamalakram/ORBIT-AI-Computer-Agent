@echo off
setlocal
cd /d "%~dp0"
title ORBIT

if not exist ".venv\Scripts\python.exe" (
  echo  Not installed yet - run install.bat first.
  pause
  exit /b 1
)

:loop
".venv\Scripts\python.exe" -m agent.main
if %errorlevel%==3 goto :end
echo.
echo  ORBIT stopped. Restarting in 10 seconds - close this window to stop for good.
timeout /t 10 /nobreak >nul
goto :loop

:end
