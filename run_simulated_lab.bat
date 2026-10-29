@echo off
title LabWatch Lab Computer Simulator
color 0E
echo =========================================================
echo       Simulating 10 Additional Lab Computers
echo =========================================================
cd /d "%~dp0"
python scripts\simulate_lab.py 10 http://127.0.0.1:8000
pause
