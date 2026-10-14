@echo off
rem MRV version update + VesselFinder crawl for ships without specs (max 200 per run)
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d %~dp0
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% -m pipeline.run --mode version --crawl %*
set CODE=%ERRORLEVEL%
echo.
echo exit code %CODE%  (0 = OK, 1 = error, 2 = needs review)  report: reports\pipeline\latest_summary.md
pause
exit /b %CODE%
