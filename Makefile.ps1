# Resume-Agent PowerShell Makefile (Windows Native Support)
# US-20: PowerShell equivalent of Makefile
# Usage: .\Makefile.ps1 <target>
#   .\Makefile.ps1 install
#   .\Makefile.ps1 dev
#   .\Makefile.ps1 build
#   .\Makefile.ps1 test
#   .\Makefile.ps1 lint
#   .\Makefile.ps1 docker-up
#   .\Makefile.ps1 clean

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "dev", "build", "test", "lint", "docker-build", "docker-up", "clean", "help")]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Clear env vars that may interfere with Python
$env:PYTHONHOME = $null
$env:PYTHONPATH = $null

function Invoke-Install {
    Write-Host ">>> Installing frontend dependencies..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\frontend"
    pnpm install
    Set-Location $ScriptDir

    Write-Host ">>> Installing backend dependencies..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\backend"
    uv sync --extra dev
    Set-Location $ScriptDir

    Write-Host "Install complete!" -ForegroundColor Green
}

function Invoke-Dev {
    Write-Host ">>> Starting dev servers (frontend + backend)..." -ForegroundColor Cyan

    # Start backend
    $backendJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location "$dir\backend"
        $env:PYTHONHOME = $null
        $env:PYTHONPATH = $null
        uv run uvicorn resume_agent.main:app --reload --port 8000
    } -ArgumentList $ScriptDir

    # Start frontend
    $frontendJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location "$dir\frontend"
        & ".\node_modules\.bin\vite"
    } -ArgumentList $ScriptDir

    Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
    Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop..." -ForegroundColor Yellow

    try {
        Wait-Job -Any $backendJob, $frontendJob
    } finally {
        Stop-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
        Remove-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
    }
}

function Invoke-Build {
    Write-Host ">>> Building frontend..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\frontend"
    & ".\node_modules\.bin\tsc" -b
    & ".\node_modules\.bin\vite" build
    Set-Location $ScriptDir
    Write-Host "Build complete!" -ForegroundColor Green
}

function Invoke-Test {
    Write-Host ">>> Running backend tests..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\backend"
    uv run pytest
    Set-Location $ScriptDir

    Write-Host ">>> Running frontend typecheck..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\frontend"
    & ".\node_modules\.bin\tsc" --noEmit
    Set-Location $ScriptDir

    Write-Host "Tests passed!" -ForegroundColor Green
}

function Invoke-Lint {
    Write-Host ">>> Backend lint..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\backend"
    uv run ruff check .
    Set-Location $ScriptDir

    Write-Host ">>> Frontend typecheck..." -ForegroundColor Cyan
    Set-Location "$ScriptDir\frontend"
    & ".\node_modules\.bin\tsc" --noEmit
    Set-Location $ScriptDir

    Write-Host "Lint passed!" -ForegroundColor Green
}

function Invoke-DockerBuild {
    Write-Host ">>> Building Docker image..." -ForegroundColor Cyan
    docker compose build
}

function Invoke-DockerUp {
    Write-Host ">>> Starting Docker containers..." -ForegroundColor Cyan
    docker compose up
}

function Invoke-Clean {
    Write-Host ">>> Cleaning build artifacts..." -ForegroundColor Cyan
    if (Test-Path "$ScriptDir\frontend\dist") {
        Remove-Item -Recurse -Force "$ScriptDir\frontend\dist"
    }
    Get-ChildItem -Path $ScriptDir -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Clean complete!" -ForegroundColor Green
}

function Show-Help {
    Write-Host "Resume-Agent PowerShell Makefile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\Makefile.ps1 <target>"
    Write-Host ""
    Write-Host "Available targets:"
    Write-Host "  install       Install frontend and backend dependencies"
    Write-Host "  dev           Start dev servers (frontend + backend)"
    Write-Host "  build         Build frontend"
    Write-Host "  test          Run tests"
    Write-Host "  lint          Code check"
    Write-Host "  docker-build  Build Docker image"
    Write-Host "  docker-up     Start Docker containers"
    Write-Host "  clean         Clean build artifacts"
    Write-Host "  help          Show this help"
}

# === Route ===
switch ($Target) {
    "install"      { Invoke-Install }
    "dev"          { Invoke-Dev }
    "build"        { Invoke-Build }
    "test"         { Invoke-Test }
    "lint"         { Invoke-Lint }
    "docker-build" { Invoke-DockerBuild }
    "docker-up"    { Invoke-DockerUp }
    "clean"        { Invoke-Clean }
    "help"         { Show-Help }
}
