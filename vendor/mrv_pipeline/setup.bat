@echo off
rem First-time setup on a new PC: create .venv (if missing) and install the packages the pipeline needs
chcp 65001 > nul
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Creating .venv ...
  python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-pipeline.txt
echo.
echo Setup done. Next: run_version_crawl.bat
pause
