@echo off
title Lane-Aware EVAS Server
color 0A
echo ======================================================================
echo    Lane-Aware Intelligent Emergency Vehicle Alert System (EVAS)
echo ======================================================================
echo  Starting FastAPI + WebSocket Server on http://localhost:8000 ...
echo  Driver HUD:      http://localhost:8000/
echo  Ambulance GPS:   http://localhost:8000/ambulance
echo  System Status:   http://localhost:8000/status
echo ======================================================================
cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
