@echo off
title AI GitHub Radar

echo ============================================
echo   AI GitHub Radar - Start
echo ============================================

echo [1/2] Starting Backend (FastAPI)...
start "Backend" cmd /c "cd /d %~dp0backend && venv\Scripts\python.exe main.py"

echo [2/2] Starting Frontend (Vite)...
start "Frontend" cmd /c "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend : http://localhost:8000/docs
echo Frontend: http://localhost:5173
echo.
echo Starting browser...
timeout /t 5 /nobreak >nul
start http://localhost:5173
pause
