@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title ORBIT - realistic voice

echo.
echo  ==================================================
echo    ORBIT ki awaaz ko realistic banayein
echo  ==================================================
echo.
echo  Ye ElevenLabs v3 use karta hai - ye akela model hai jo Urdu bhi
echo  bolta hai aur emotions bhi samajhta hai (hmm, laughs, sighs).
echo.
echo  Key yahan se lein:  https://elevenlabs.io  -^>  Profile  -^>  API Keys
echo  Free plan: har mahine ~10 minute. Starter: $6/mah.
echo.
set "KEY="
set /p KEY=Apni ElevenLabs key paste karein (khali chorne se cancel):

if "%KEY%"=="" (
  echo.
  echo  Kuch nahi likha - koi tabdeeli nahi ki gayi.
  echo.
  pause
  exit /b 1
)

echo.
echo  Save kar raha hoon...
".venv\Scripts\python.exe" set_env_value.py ELEVENLABS_API_KEY "%KEY%"
if errorlevel 1 goto :fail

echo  Check kar raha hoon...
".venv\Scripts\python.exe" -c "import sys; from agent.config import CONFIG; k=CONFIG.elevenlabs_key; print('   key loaded:', bool(k)); sys.exit(0 if k else 1)"
if errorlevel 1 goto :fail

echo.
echo  Awaaz ka test kar raha hoon...
".venv\Scripts\python.exe" -c "import asyncio; from agent import voice; p=asyncio.run(voice.synthesize('[warmly] Assalam o alaikum! Hmm... theek hai, main tayyar hoon.','ur')); print('   test file:', p if p else 'FAILED')"

echo.
echo  ORBIT ko restart kar raha hoon...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'agent' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul
wscript.exe "%~dp0lappilot-hidden.vbs"

echo.
echo  Ho gaya. ORBIT ko voice note bhej kar sunein.
echo.
echo  Aawaz badalni ho to:  .venv\Scripts\python.exe list_voices.py
echo.
pause
exit /b 0

:fail
echo.
echo  [X] Key save ya load nahi hui. .env kholein aur check karein.
echo.
pause
exit /b 1
