@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Determine if interactive pause is enabled (suppressed by CI, NONINTERACTIVE, --no-pause, -y)
set "DO_PAUSE=1"
if not "%CI%"=="" set "DO_PAUSE=0"
if not "%NONINTERACTIVE%"=="" set "DO_PAUSE=0"
:parse_args
if "%~1"=="" goto done_args
if /i "%~1"=="--no-pause" set "DO_PAUSE=0"
if /i "%~1"=="-y" set "DO_PAUSE=0"
if /i "%~1"=="/y" set "DO_PAUSE=0"
if /i "%~1"=="--non-interactive" set "DO_PAUSE=0"
shift
goto parse_args
:done_args

echo =====================================================================
echo  RECALL v2.1.0 - Windows Installation ^& Environment Setup
echo =====================================================================
echo.

:: 1. Verify Python availability
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.11 or 3.12 from https://www.python.org/downloads/
    echo Ensure "Add Python to PATH" is checked during installation.
    echo.
    if "!DO_PAUSE!"=="1" pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYTHON_VERSION=%%v
echo [INFO] Detected Python: !PYTHON_VERSION!

:: 2. Create isolated virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating isolated virtual environment in .venv...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        if "!DO_PAUSE!"=="1" pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created successfully.
) else (
    echo [INFO] Existing virtual environment found in .venv.
)

:: 3. Upgrade pip and install RECALL dependencies
echo [INFO] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [INFO] Installing RECALL dependencies (FastAPI, MCP, ChromaDB, SentenceTransformers)...
".venv\Scripts\python.exe" -m pip install -e ".[mcp,semantic]"
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Editable install with extras failed; installing via requirements.txt...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Dependency installation failed. Check network access.
        if "!DO_PAUSE!"=="1" pause
        exit /b 1
    )
    echo [INFO] Linking RECALL local packages into virtual environment...
    ".venv\Scripts\python.exe" -m pip install --no-build-isolation --no-deps -e . >nul 2>&1
    ".venv\Scripts\python.exe" -c "import recall_mcp, api" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [INFO] Writing verified .pth link to ensure package importability...
        ".venv\Scripts\python.exe" -c "import site, pathlib; p = pathlib.Path(site.getsitepackages()[-1]) / 'recall_local.pth'; p.write_text(str(pathlib.Path.cwd().resolve()) + '\n', encoding='utf-8')"
    )
)

:: Verify package importability from arbitrary external working directory
set "CURR_DIR=%cd%"
cd /d "%TEMP%"
"%CURR_DIR%\.venv\Scripts\python.exe" -c "import recall_mcp, api; print('[SUCCESS] Core packages verified: recall_mcp from', recall_mcp.__file__)"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to verify package importability from external directory.
    cd /d "%CURR_DIR%"
    if "!DO_PAUSE!"=="1" pause
    exit /b 1
)
cd /d "%CURR_DIR%"
echo [SUCCESS] Dependencies and packages installed successfully.

:: 4. Verify canonical SQLite and MCP initialization (isolated smoke test)
echo [INFO] Running initial isolated smoke test to verify system integrity...
set "RECALL_MCP_WARMUP=false"
".venv\Scripts\python.exe" scripts\smoke_test_mcp.py --isolated
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Smoke test completed with warnings.
) else (
    echo [SUCCESS] RECALL verified and operational!
)

:: 5. Generate client-specific MCP configuration
echo [INFO] Generating local MCP configuration for your AI coding agents...
".venv\Scripts\python.exe" scripts\generate_mcp_config.py

echo.
echo =====================================================================
echo  Installation Complete!
echo =====================================================================
echo.
echo  Quick Start:
echo   1. Start HTTP API ^& Web Dashboard:
echo      start_api.bat
echo      (Full Web Dashboard and REST API available at http://localhost:8080)
echo.
echo   2. Configure AI Coding Agent (OpenCode, Cursor, Antigravity, Claude):
echo      A ready-to-copy configuration was generated in mcp_config.local.json!
echo      (See mcp_config.example.json for syntax and client paths)
echo.
if "!DO_PAUSE!"=="1" pause


