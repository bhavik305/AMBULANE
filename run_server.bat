
@echo off
title Lane-Aware EVAS Server
color 0A

:: -----------------------------------------------------------------------
:: Lane-Aware Intelligent Emergency Vehicle Alert System (EVAS / AMBULANE)
:: run_server.bat  —  single-file startup for local + LAN access
::
:: Port note: WinError 10013 is caused by --reload on Windows (child
:: subprocess tries to rebind the same port while the parent holds it).
:: Solution: run WITHOUT --reload. Use a fresh terminal to restart.
:: -----------------------------------------------------------------------

set PORT=8000

echo ======================================================================
echo    Lane-Aware Intelligent Emergency Vehicle Alert System (EVAS)
echo ======================================================================
echo  Port : %PORT%
echo  Docs : http://localhost:%PORT%/docs

:: Detect Wi-Fi IP for LAN access display
for /f "tokens=3 delims=: " %%a in ('netsh interface ip show address "Wi-Fi" ^| findstr /C:"IP Address"') do (
    set WIFI_IP=%%a
)
if defined WIFI_IP (
    echo  LAN  : http://%WIFI_IP%:%PORT%/
) else (
    echo  LAN  : Run 'ipconfig' to find your Wi-Fi IPv4 address, then use http://<ip>:%PORT%/
)
echo ======================================================================

:: Check if the port is already in use and warn the user
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo [WARN] Port %PORT% is already in use. Stop the existing server first.
    echo        To kill it, find the PID with:  netstat -ano ^| findstr ":%PORT%"
    echo        Then run:                        taskkill /PID ^<pid^> /F
    echo.
    echo  Press any key to try starting anyway (may fail if port is taken)...
    pause >nul
)

:: Add Windows Firewall inbound rule for this port if not already present
:: (silently skips if it already exists or if not running as admin)
netsh advfirewall firewall show rule name="EVAS Port %PORT%" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Adding Windows Firewall inbound rule for port %PORT% ...
    netsh advfirewall firewall add rule name="EVAS Port %PORT%" protocol=TCP dir=in localport=%PORT% action=allow >nul 2>&1
    if %errorlevel% == 0 (
        echo [INFO] Firewall rule added. Run as Administrator if this fails.
    ) else (
        echo [WARN] Could not add firewall rule. Run this BAT as Administrator
        echo        or add the rule manually for LAN access to work.
    )
)

echo.
echo  Starting server — press Ctrl+C to stop.
echo  NOTE: --reload is intentionally disabled (causes WinError 10013 on Windows).
echo  Restart this BAT to pick up backend code changes.
echo ======================================================================
echo.

cd /d "%~dp0backend"
C:\Python310\python.exe -m uvicorn main:app --host 0.0.0.0 --port %PORT%

pause
