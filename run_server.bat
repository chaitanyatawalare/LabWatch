@echo off
title LabWatch Central Server
color 0B
echo =========================================================
echo            Starting LabWatch Central Server
echo =========================================================
cd /d "%~dp0"
python -m src.server
pause
