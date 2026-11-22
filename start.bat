@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python server.py --lan
) else (
  py -3 server.py --lan
)
pause
