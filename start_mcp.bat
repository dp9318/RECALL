@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] RECALL virtual environment not found in .venv.
    echo Please run setup.bat first to configure your environment.
    exit /b 1
)

".venv\Scripts\python.exe" -m recall_mcp.server
