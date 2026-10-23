# RECALL v2.1.1 - Windows PowerShell Setup & Verification Script
$ErrorActionPreference = "Stop"
if ($PSScriptRoot) { Set-Location $PSScriptRoot }

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host " RECALL v2.1.1 - Windows Installation & Environment Setup" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify Python availability
try {
    $pythonVer = & python --version 2>&1
    Write-Host "[INFO] Detected Python: $pythonVer" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python was not found in your system PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.11 or 3.12 from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Ensure 'Add Python to PATH' is checked during installation." -ForegroundColor Yellow
    exit 1
}

# 2. Create isolated virtual environment
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[INFO] Creating isolated virtual environment in .venv..." -ForegroundColor Cyan
    & python -m venv .venv
    Write-Host "[SUCCESS] Virtual environment created successfully." -ForegroundColor Green
} else {
    Write-Host "[INFO] Existing virtual environment found in .venv." -ForegroundColor Yellow
}

# 3. Upgrade pip and install dependencies
Write-Host "[INFO] Upgrading pip..." -ForegroundColor Cyan
& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet

Write-Host "[INFO] Installing RECALL dependencies (FastAPI, MCP, ChromaDB, SentenceTransformers)..." -ForegroundColor Cyan
$installSuccess = $false
try {
    & .venv\Scripts\python.exe -m pip install -e ".[mcp,semantic]"
    if ($LASTEXITCODE -eq 0) { $installSuccess = $true }
} catch {
    $installSuccess = $false
}

if (-not $installSuccess) {
    Write-Host "[WARNING] Editable install with extras failed; installing via requirements.txt..." -ForegroundColor Yellow
    & .venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Dependency installation failed. Check network access." -ForegroundColor Red
        exit 1
    }
    Write-Host "[INFO] Linking RECALL local packages into virtual environment..." -ForegroundColor Cyan
    & .venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e . 2>$null
    & .venv\Scripts\python.exe -c "import recall_mcp, api" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[INFO] Writing verified .pth link to ensure package importability..." -ForegroundColor Cyan
        & .venv\Scripts\python.exe -c "import site, pathlib; p = pathlib.Path(site.getsitepackages()[-1]) / 'recall_local.pth'; p.write_text(str(pathlib.Path.cwd().resolve()) + '\n', encoding='utf-8')"
    }
}

# Verify package importability from arbitrary external working directory
$repoDir = (Get-Location).Path
$tempDir = [System.IO.Path]::GetTempPath()
Push-Location $tempDir
try {
    & "$repoDir\.venv\Scripts\python.exe" -c "import recall_mcp, api; print('[SUCCESS] Core packages verified: recall_mcp from', recall_mcp.__file__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to verify package importability from external directory."
    }
} finally {
    Pop-Location
}
Write-Host "[SUCCESS] Dependencies and packages installed successfully." -ForegroundColor Green

# 4. Run Isolated Smoke Test
Write-Host "[INFO] Running initial isolated smoke test to verify system integrity..." -ForegroundColor Cyan
$env:RECALL_MCP_WARMUP = "false"
& .venv\Scripts\python.exe scripts\smoke_test_mcp.py --isolated

# 5. Generate client-specific MCP configuration
Write-Host "[INFO] Generating local MCP configuration for your AI coding agents..." -ForegroundColor Cyan
& .venv\Scripts\python.exe scripts\generate_mcp_config.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to generate local MCP configuration." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host " Installation Complete!" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host " Quick Start:"
Write-Host "  1. Start HTTP API & Web Dashboard:   .\start_api.bat (http://localhost:8080)"
Write-Host "  2. MCP Agent Configuration:          Generated in mcp_config.local.json"
Write-Host "                                       (See mcp_config.example.json for syntax)"
Write-Host ""

