@echo off
rem Sea Marksman v7: team model API (port 8000) + web_sm7 (port 5192, shared backend via /shared)
if not exist "%USERPROFILE%\miniconda3\envs\sm313\python.exe" (
  echo Python env sm313 not found. See sea_marksman_v5\web_sm7\README.md
  pause
  exit /b 1
)
cd /d "%~dp0sea_marksman_v5"
start "Sea Marksman API" cmd /c run_api.bat
cd web_sm7
if not exist node_modules call npm install
call npm run dev
pause
