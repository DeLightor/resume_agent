# Resume-Agent One-Click Install Script (Windows PowerShell)
# US-19/US-20: Environment check + dependency install + LLM config + Docker check
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

# === Helper Functions ===
function Write-InfoMsg  { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Blue }
function Write-OkMsg    { param([string]$msg) Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-WarnMsg   { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-FailMsg   { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }

# Script directory (project root)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    Resume-Agent Install Script" -ForegroundColor Cyan
Write-Host "    Windows PowerShell" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================
# Step 1: Environment Check
# ============================================
Write-InfoMsg "Step 1/5: Environment Check..."
Write-Host ""

$Missing = @()

# --- Node.js ---
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    $nodeVersion = (node -v) -replace 'v', ''
    $nodeMajor = ($nodeVersion -split '\.')[0]
    if ([int]$nodeMajor -ge 20) {
        Write-OkMsg "Node.js v$nodeVersion"
    } else {
        Write-WarnMsg "Node.js v$nodeVersion (need >= 20)"
        $Missing += "node"
    }
} else {
    Write-FailMsg "Node.js not installed"
    $Missing += "node"
}

# --- pnpm ---
$pnpmCmd = Get-Command pnpm -ErrorAction SilentlyContinue
if ($pnpmCmd) {
    $pnpmVersion = (pnpm -v)
    $pnpmMajor = ($pnpmVersion -split '\.')[0]
    if ([int]$pnpmMajor -ge 9) {
        Write-OkMsg "pnpm v$pnpmVersion"
    } else {
        Write-WarnMsg "pnpm v$pnpmVersion (need >= 9)"
        $Missing += "pnpm"
    }
} else {
    Write-FailMsg "pnpm not installed"
    $Missing += "pnpm"
}

# --- Python ---
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    $pyCmd = Get-Command python3 -ErrorAction SilentlyContinue
}
if ($pyCmd) {
    $pyVersion = (python --version 2>$null) -replace 'Python ', ''
    if (-not $pyVersion) {
        $pyVersion = (python3 --version 2>$null) -replace 'Python ', ''
    }
    $pyParts = $pyVersion -split '\.'
    $pyMajor = [int]$pyParts[0]
    $pyMinor = [int]$pyParts[1]
    if ($pyMajor -eq 3 -and $pyMinor -ge 10) {
        Write-OkMsg "Python $pyVersion"
    } else {
        Write-WarnMsg "Python $pyVersion (need >= 3.10)"
        $Missing += "python"
    }
} else {
    Write-FailMsg "Python 3 not installed"
    $Missing += "python"
}

# --- uv ---
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvVersion = (uv --version 2>$null) -replace 'uv ', ''
    Write-OkMsg "uv v$uvVersion"
} else {
    Write-FailMsg "uv not installed"
    $Missing += "uv"
}

# --- Docker (optional) ---
$DockerAvailable = $false
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCmd) {
    try {
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerVersion = (docker --version) -replace 'Docker version ', '' -replace ',.*', ''
            Write-OkMsg "Docker v$dockerVersion (available)"
            $DockerAvailable = $true
        } else {
            Write-WarnMsg "Docker installed but not running"
        }
    } catch {
        Write-WarnMsg "Docker installed but not running"
    }
} else {
    Write-InfoMsg "Docker not installed (optional)"
}

Write-Host ""

if ($Missing.Count -gt 0) {
    Write-WarnMsg "Missing dependencies, please install first:"
    Write-Host ""
    foreach ($dep in $Missing) {
        switch ($dep) {
            "node" {
                Write-Host "  Node.js >= 20" -ForegroundColor Yellow
                Write-Host "    Download: https://nodejs.org/en/download/" -ForegroundColor Cyan
                Write-Host "    Or:       winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
            }
            "pnpm" {
                Write-Host "  pnpm >= 9" -ForegroundColor Yellow
                Write-Host "    npm install -g pnpm@9" -ForegroundColor Cyan
                Write-Host "    Or:       corepack enable" -ForegroundColor Cyan
            }
            "python" {
                Write-Host "  Python >= 3.10" -ForegroundColor Yellow
                Write-Host "    Download: https://www.python.org/downloads/" -ForegroundColor Cyan
                Write-Host "    Or:       winget install Python.Python.3.12" -ForegroundColor Cyan
            }
            "uv" {
                Write-Host "  uv" -ForegroundColor Yellow
                Write-Host "    powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Cyan
            }
        }
    }
    Write-Host ""
    Write-FailMsg "Please install above dependencies and re-run: .\install.ps1"
    exit 1
}

Write-OkMsg "All required dependencies are ready"
Write-Host ""

# ============================================
# Step 2: Install Dependencies
# ============================================
Write-InfoMsg "Step 2/5: Installing project dependencies..."
Write-Host ""

# Frontend dependencies
Write-InfoMsg "Installing frontend dependencies (pnpm install)..."
Set-Location "$ScriptDir\frontend"
pnpm install
if ($LASTEXITCODE -eq 0 -or (Test-Path "node_modules")) {
    Write-OkMsg "Frontend dependencies installed"
} else {
    Write-FailMsg "Frontend dependency install failed (see output above)"
    Set-Location $ScriptDir
    exit 1
}
Set-Location $ScriptDir

# Backend dependencies
Write-InfoMsg "Installing backend dependencies (uv sync)..."
Set-Location "$ScriptDir\backend"
uv sync --extra dev
if ($LASTEXITCODE -eq 0) {
    Write-OkMsg "Backend dependencies installed"
} else {
    Write-FailMsg "Backend dependency install failed"
    exit 1
}
Set-Location $ScriptDir

Write-Host ""
Write-OkMsg "Project dependencies installed"
Write-Host ""

# ============================================
# Step 3: LLM Config
# ============================================
Write-InfoMsg "Step 3/5: LLM Configuration..."
Write-Host ""

$EnvFile = "$ScriptDir\.env"
$EnvExample = "$ScriptDir\.env.example"
$SkipConfig = $false

if (Test-Path $EnvFile) {
    Write-OkMsg ".env file already exists"
    Write-Host ""
    $reconfigure = Read-Host "Reconfigure LLM? (y/N)"
    if ($reconfigure -ne "y" -and $reconfigure -ne "Y") {
        Write-InfoMsg "Skipping config, using existing .env"
        Write-Host ""
        $SkipConfig = $true
    }
}

if (-not $SkipConfig) {
    # Copy .env.example
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $EnvExample $EnvFile
        Write-OkMsg "Created .env from .env.example"
    }

    Write-Host ""
    Write-Host "Configure LLM (press Enter for defaults):" -ForegroundColor Cyan
    Write-Host ""

    # LLM Provider
    $provider = Read-Host "LLM Provider [openai/claude/deepseek/custom] (default: openai)"
    if ([string]::IsNullOrWhiteSpace($provider)) { $provider = "openai" }

    # API Key
    $apiKey = Read-Host "LLM API Key (required)"
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-WarnMsg "API Key is empty, AI features will not work. Edit .env later."
    }

    # Base URL & Model defaults
    $defaultUrl = ""
    $defaultModel = "gpt-4o"
    if ($provider -eq "deepseek") {
        $defaultUrl = "https://api.deepseek.com/v1"
        $defaultModel = "deepseek-chat"
    } elseif ($provider -eq "claude") {
        $defaultUrl = "https://api.anthropic.com"
        $defaultModel = "claude-sonnet-4-20250514"
    }

    $baseUrl = Read-Host "LLM Base URL (default: $defaultUrl)"
    if ([string]::IsNullOrWhiteSpace($baseUrl)) { $baseUrl = $defaultUrl }

    $model = Read-Host "LLM Model (default: $defaultModel)"
    if ([string]::IsNullOrWhiteSpace($model)) { $model = $defaultModel }

    # Read and replace .env content
    $envContent = Get-Content $EnvFile -Raw
    $envContent = $envContent -replace '^LLM_PROVIDER=.*', "LLM_PROVIDER=$provider"
    $envContent = $envContent -replace '^LLM_API_KEY=.*', "LLM_API_KEY=$apiKey"
    $envContent = $envContent -replace '^LLM_BASE_URL=.*', "LLM_BASE_URL=$baseUrl"
    $envContent = $envContent -replace '^LLM_MODEL=.*', "LLM_MODEL=$model"
    $envContent | Set-Content $EnvFile -NoNewline

    Write-OkMsg "LLM config saved to .env"
    Write-Host ""
}

# ============================================
# Step 4: Docker Check
# ============================================
Write-InfoMsg "Step 4/5: Docker Check..."
Write-Host ""

if ($DockerAvailable) {
    Write-OkMsg "Docker is available! You can start with:"
    Write-Host ""
    Write-Host "  docker compose up" -ForegroundColor Cyan
    Write-Host ""
    Write-InfoMsg "Docker mode does not require Node.js / Python"
} else {
    Write-InfoMsg "Docker not available, will use local dev mode"
}

Write-Host ""

# ============================================
# Step 5: Done
# ============================================
Write-InfoMsg "Step 5/5: Installation complete!"
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "    Resume-Agent installed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Start:"
Write-Host ""
if ($DockerAvailable) {
    Write-Host "  Docker:    docker compose up" -ForegroundColor Cyan
    Write-Host "  URL:       http://localhost:5173" -ForegroundColor Cyan
    Write-Host ""
}
Write-Host "  Dev mode:  powershell -ExecutionPolicy Bypass -File Makefile.ps1 dev" -ForegroundColor Cyan
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Test:      .\Makefile.ps1 test" -ForegroundColor Cyan
Write-Host "  Config:    .env (edit to change LLM config)" -ForegroundColor Cyan
Write-Host ""
