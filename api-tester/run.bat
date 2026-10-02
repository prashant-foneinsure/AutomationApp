@echo off
cd /d %~dp0
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --reload-exclude frontend --reload-exclude static
pause