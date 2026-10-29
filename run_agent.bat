@echo off
title LabWatch Windows Agent
color 0A
echo =========================================================
echo            Starting LabWatch Monitoring Agent
echo =========================================================
cd /d "%~dp0"
python -m src.agent http://127.0.0.1:8000 1
pause
