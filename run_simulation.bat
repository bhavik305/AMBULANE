@echo off
title EVAS Simulation Runner
color 0B
echo ======================================================================
echo    Starting Multi-Vehicle Real-Time Simulation
echo ======================================================================
cd /d "%~dp0backend"
python simulate.py
pause
