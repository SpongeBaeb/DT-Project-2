@echo off
rem Sea Marksman team diagnosis API (port 8000). Started by run_sea_marksman_v5.bat
cd /d "%~dp0"
set SEA_CONFIG=config/mrv_pipeline.yaml
set PYTHONIOENCODING=utf-8
"%USERPROFILE%\miniconda3\envs\sm313\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8000
pause
