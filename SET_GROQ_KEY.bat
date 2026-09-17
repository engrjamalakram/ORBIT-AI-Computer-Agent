@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Set Groq key

echo.
echo  ==========================================
echo    Add your Groq key (fast voice)
echo  ==========================================
echo.
echo  Get one free at:  https://console.groq.com  -^>  API Keys  -^>  Create API Key
echo  It starts with:   gsk_
echo.
set "KEY="
set /p KEY=Paste your Groq key here and press Enter:

if "%KEY%"=="" (
  echo.
  echo  Nothing entered - no changes made.
  echo.
  pause
  exit /b 1
)

echo.
echo  Saving...

".venv\Scripts\python.exe" set_groq_key.py "%KEY%"

if errorlevel 1 (
  echo.
  echo  [X] Could not write .env
  echo.
  pause
  exit /b 1
)

echo  Verifying...
".venv\Scripts\python.exe" -c "from agent.config import CONFIG; k=CONFIG.groq_api_key; print('   GROQ key loaded:', bool(k)); print('   looks valid:', k.startswith('gsk_') if k else False); raise SystemExit(0 if k else 1)"
if errorlevel 1 (
  echo.
  echo  [X] Key still not loading - open .env and check the line reads  GROQ_API_KEY=gsk_...
  echo.
  pause
  exit /b 1
)

echo.
echo  Restarting ORBIT so it takes effect...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'agent' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul
wscript.exe "%~dp0lappilot-hidden.vbs"

echo.
echo  ==========================================
echo    Done. Voice notes are now ~1-2 seconds.
echo  ==========================================
echo.
echo  Send ORBIT a voice note to test.
echo.
pause
