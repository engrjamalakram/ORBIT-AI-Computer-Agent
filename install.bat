@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ==========================================
echo   LapPilot - installing
echo  ==========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo  [X] Python is not installed or not on PATH.
  echo      Get it from https://python.org/downloads  ^(tick "Add Python to PATH"^)
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :fail
)

echo  Installing dependencies ^(this takes a minute^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo  Created .env  -  opening it now.
  echo  Fill in DISCORD_BOT_TOKEN, DISCORD_ALLOWED_USER_IDS and ANTHROPIC_API_KEY,
  echo  save the file, then run  run.bat
  echo.
  notepad ".env"
) else (
  echo.
  echo  .env already exists, leaving it alone.
)

echo.
echo  Done. Start the agent with:  run.bat
echo.
pause
exit /b 0

:fail
echo.
echo  [X] Install failed - see the error above.
echo.
pause
exit /b 1
