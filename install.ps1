# Resume-Agent 一键安装脚本（Windows PowerShell）
# US-19: 环境检测 + 依赖安装 + LLM 配置引导 + Docker 检测
# 使用方式: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

# === 辅助函数 ===
function Write-Info    { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Blue }
function Write-Ok      { param([string]$msg) Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-WarnMsg { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail    { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }

# 脚本所在目录（项目根目录）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    Resume-Agent 一键安装脚本" -ForegroundColor Cyan
Write-Host "    Windows PowerShell" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================
# Step 1: 环境检测
# ============================================
Write-Info "Step 1/5: 环境检测..."
Write-Host ""

$Missing = @()

# --- Node.js ---
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    $nodeVersion = (node -v) -replace 'v', ''
    $nodeMajor = ($nodeVersion -split '\.')[0]
    if ([int]$nodeMajor -ge 20) {
        Write-Ok "Node.js v$nodeVersion"
    } else {
        Write-WarnMsg "Node.js v$nodeVersion (需要 >= 20)"
        $Missing += "node"
    }
} else {
    Write-Fail "Node.js 未安装"
    $Missing += "node"
}

# --- pnpm ---
$pnpmCmd = Get-Command pnpm -ErrorAction SilentlyContinue
if ($pnpmCmd) {
    $pnpmVersion = (pnpm -v)
    $pnpmMajor = ($pnpmVersion -split '\.')[0]
    if ([int]$pnpmMajor -ge 9) {
        Write-Ok "pnpm v$pnpmVersion"
    } else {
        Write-WarnMsg "pnpm v$pnpmVersion (需要 >= 9)"
        $Missing += "pnpm"
    }
} else {
    Write-Fail "pnpm 未安装"
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
    if ($pyMajor -eq 3 -and $pyMinor -ge 12) {
        Write-Ok "Python $pyVersion"
    } else {
        Write-WarnMsg "Python $pyVersion (需要 >= 3.12)"
        $Missing += "python"
    }
} else {
    Write-Fail "Python 3 未安装"
    $Missing += "python"
}

# --- uv ---
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvVersion = (uv --version 2>$null) -replace 'uv ', ''
    Write-Ok "uv v$uvVersion"
} else {
    Write-Fail "uv 未安装"
    $Missing += "uv"
}

# --- Docker (可选) ---
$DockerAvailable = $false
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCmd) {
    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerVersion = (docker --version) -replace 'Docker version ', '' -replace ',.*', ''
        Write-Ok "Docker v$dockerVersion (可用)"
        $DockerAvailable = $true
    } else {
        Write-WarnMsg "Docker 已安装但未运行"
    }
} else {
    Write-Info "Docker 未安装 (可选)"
}

Write-Host ""

if ($Missing.Count -gt 0) {
    Write-WarnMsg "以下依赖缺失，请先安装："
    Write-Host ""
    foreach ($dep in $Missing) {
        switch ($dep) {
            "node" {
                Write-Host "  Node.js >= 20" -ForegroundColor Yellow
                Write-Host "    下载: https://nodejs.org/en/download/" -ForegroundColor Cyan
                Write-Host "    或:   winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
            }
            "pnpm" {
                Write-Host "  pnpm >= 9" -ForegroundColor Yellow
                Write-Host "    npm install -g pnpm@9" -ForegroundColor Cyan
                Write-Host "    或:   corepack enable" -ForegroundColor Cyan
            }
            "python" {
                Write-Host "  Python >= 3.12" -ForegroundColor Yellow
                Write-Host "    下载: https://www.python.org/downloads/" -ForegroundColor Cyan
                Write-Host "    或:   winget install Python.Python.3.12" -ForegroundColor Cyan
            }
            "uv" {
                Write-Host "  uv" -ForegroundColor Yellow
                Write-Host "    powershell -ExecutionPolicy Bypass -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Cyan
            }
        }
    }
    Write-Host ""
    Write-Fail "请安装上述依赖后重新运行此脚本: .\install.ps1"
    exit 1
}

Write-Ok "所有必需依赖已就绪"
Write-Host ""

# ============================================
# Step 2: 依赖安装
# ============================================
Write-Info "Step 2/5: 安装项目依赖..."
Write-Host ""

# 前端依赖
Write-Info "安装前端依赖 (pnpm install)..."
Set-Location "$ScriptDir\frontend"
# pnpm v11+ 可能因 ignored build scripts 返回非 0 退出码，检查 node_modules 是否存在即可
try { pnpm install 2>&1 | Out-Null } catch {}
if (Test-Path "node_modules") {
    Write-Ok "前端依赖安装完成"
} else {
    Write-Fail "前端依赖安装失败"
    exit 1
}
Set-Location $ScriptDir

# 后端依赖
Write-Info "安装后端依赖 (uv sync)..."
Set-Location "$ScriptDir\backend"
uv sync --extra dev
if ($LASTEXITCODE -eq 0) {
    Write-Ok "后端依赖安装完成"
} else {
    Write-Fail "后端依赖安装失败"
    exit 1
}
Set-Location $ScriptDir

Write-Host ""
Write-Ok "项目依赖安装完成"
Write-Host ""

# ============================================
# Step 3: 配置引导
# ============================================
Write-Info "Step 3/5: LLM 配置引导..."
Write-Host ""

$EnvFile = "$ScriptDir\.env"
$EnvExample = "$ScriptDir\.env.example"
$SkipConfig = $false

if (Test-Path $EnvFile) {
    Write-Ok ".env 文件已存在"
    Write-Host ""
    $reconfigure = Read-Host "是否重新配置 LLM? (y/N)"
    if ($reconfigure -ne "y" -and $reconfigure -ne "Y") {
        Write-Info "跳过配置，使用现有 .env"
        Write-Host ""
        $SkipConfig = $true
    }
}

if (-not $SkipConfig) {
    # 复制 .env.example
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $EnvExample $EnvFile
        Write-Ok "已从 .env.example 创建 .env"
    }

    Write-Host ""
    Write-Host "请配置 LLM 信息（直接回车使用默认值）:" -ForegroundColor Cyan
    Write-Host ""

    # LLM Provider
    $provider = Read-Host "LLM Provider [openai/claude/deepseek/custom] (默认 openai)"
    if ([string]::IsNullOrWhiteSpace($provider)) { $provider = "openai" }

    # API Key
    $apiKey = Read-Host "LLM API Key (必填)"
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-WarnMsg "API Key 为空，AI 功能将无法使用。稍后可编辑 .env 填入"
    }

    # Base URL & Model 默认值
    switch ($provider) {
        "deepseek" {
            $defaultUrl = "https://api.deepseek.com/v1"
            $defaultModel = "deepseek-chat"
        }
        "claude" {
            $defaultUrl = "https://api.anthropic.com"
            $defaultModel = "claude-sonnet-4-20250514"
        }
        default {
            $defaultUrl = ""
            $defaultModel = "gpt-4o"
        }
    }

    $baseUrl = Read-Host "LLM Base URL (默认 $defaultUrl)"
    if ([string]::IsNullOrWhiteSpace($baseUrl)) { $baseUrl = $defaultUrl }

    $model = Read-Host "LLM Model (默认 $defaultModel)"
    if ([string]::IsNullOrWhiteSpace($model)) { $model = $defaultModel }

    # 读取 .env 内容并替换
    $envContent = Get-Content $EnvFile -Raw
    $envContent = $envContent -replace '^LLM_PROVIDER=.*', "LLM_PROVIDER=$provider"
    $envContent = $envContent -replace '^LLM_API_KEY=.*', "LLM_API_KEY=$apiKey"
    $envContent = $envContent -replace '^LLM_BASE_URL=.*', "LLM_BASE_URL=$baseUrl"
    $envContent = $envContent -replace '^LLM_MODEL=.*', "LLM_MODEL=$model"
    $envContent | Set-Content $EnvFile -NoNewline

    Write-Ok "LLM 配置已写入 .env"
    Write-Host ""
}

# ============================================
# Step 4: Docker 检测
# ============================================
Write-Info "Step 4/5: Docker 检测..."
Write-Host ""

if ($DockerAvailable) {
    Write-Ok "Docker 可用！你可以使用 Docker 一键启动："
    Write-Host ""
    Write-Host "  docker compose up" -ForegroundColor Cyan
    Write-Host ""
    Write-Info "Docker 方式无需 Node.js / Python 环境，适合快速体验"
} else {
    Write-Info "Docker 不可用，将使用本地开发模式启动"
}

Write-Host ""

# ============================================
# Step 5: 完成
# ============================================
Write-Info "Step 5/5: 安装完成！"
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "    Resume-Agent 安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "启动方式："
Write-Host ""
if ($DockerAvailable) {
    Write-Host "  Docker 一键启动:  docker compose up" -ForegroundColor Cyan
    Write-Host "  访问地址:        http://localhost:5173" -ForegroundColor Cyan
    Write-Host ""
}
Write-Host "  本地开发启动:    make dev  (需要 Make)" -ForegroundColor Cyan
Write-Host "  或分别启动:" -ForegroundColor White
Write-Host "    后端:  cd backend; uv run uvicorn resume_agent.main:app --reload --port 8000" -ForegroundColor Cyan
Write-Host "    前端:  cd frontend; npx vite" -ForegroundColor Cyan
Write-Host ""
Write-Host "  前端地址:        http://localhost:5173" -ForegroundColor Cyan
Write-Host "  后端地址:        http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  运行测试:        make test  (需要 Make)" -ForegroundColor Cyan
Write-Host "  或分别测试:" -ForegroundColor White
Write-Host "    后端:  cd backend; uv run pytest" -ForegroundColor Cyan
Write-Host "    前端:  cd frontend; npx tsc --noEmit" -ForegroundColor Cyan
Write-Host ""
Write-Host "  配置文件:        .env (如需修改 LLM 配置，编辑此文件)" -ForegroundColor Cyan
Write-Host ""
