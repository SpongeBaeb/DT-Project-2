@echo off
rem Sea Marksman AIS collector: collects aisstream positions into data\ais\state.json (default 6 hours). Usage: run_ais_collector.bat [hours]
cd /d "%~dp0"
set SEA_CONFIG=config/mrv_pipeline.yaml
set PYTHONIOENCODING=utf-8
if not exist data\ais mkdir data\ais
set H=%1
if "%H%"=="" set H=6
"%USERPROFILE%\miniconda3\envs\sm313\python.exe" -m api.ais_daemon --hours %H% >> data\ais\collector.log 2>&1
