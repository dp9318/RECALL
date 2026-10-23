@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] RECALL virtual environment not found in .venv.
    echo Please run setup.bat first to configure your environment.
    echo.
    pause
    exit /b 1
)

echo [RECALL] Starting RECALL HTTP REST API ^& Web Dashboard on http://localhost:8080...
echo [RECALL] Web Dashboard: http://localhost:8080/
echo [RECALL] Interactive API Docs: http://localhost:8080/docs
echo [RECALL] Press Ctrl+C to stop the server.
echo.

".venv\Scripts\python.exe" -m api.main
