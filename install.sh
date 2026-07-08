#!/usr/bin/env bash
# Resume-Agent 一键安装脚本（macOS / Linux）
# US-19: 环境检测 + 依赖安装 + LLM 配置引导 + Docker 检测
set -euo pipefail

# === 颜色定义 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# === 辅助函数 ===
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()    { echo -e "${RED}[FAIL]${NC} $*"; }

# 脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}    Resume-Agent 一键安装脚本${NC}"
echo -e "${CYAN}    macOS / Linux${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ============================================
# Step 1: 环境检测
# ============================================
info "Step 1/5: 环境检测..."
echo ""

MISSING=()

# --- Node.js ---
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=${NODE_VERSION%%.*}
    if [ "$NODE_MAJOR" -ge 20 ]; then
        success "Node.js v$NODE_VERSION"
    else
        warn "Node.js v$NODE_VERSION (需要 >= 20)"
        MISSING+=("node")
    fi
else
    fail "Node.js 未安装"
    MISSING+=("node")
fi

# --- pnpm ---
if command -v pnpm &>/dev/null; then
    PNPM_VERSION=$(pnpm -v)
    PNPM_MAJOR=${PNPM_VERSION%%.*}
    if [ "$PNPM_MAJOR" -ge 9 ]; then
        success "pnpm v$PNPM_VERSION"
    else
        warn "pnpm v$PNPM_VERSION (需要 >= 9)"
        MISSING+=("pnpm")
    fi
else
    fail "pnpm 未安装"
    MISSING+=("pnpm")
fi

# --- Python ---
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 12 ]; then
        success "Python $PY_VERSION"
    else
        warn "Python $PY_VERSION (需要 >= 3.12)"
        MISSING+=("python")
    fi
else
    fail "Python 3 未安装"
    MISSING+=("python")
fi

# --- uv ---
if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | sed 's/uv //')
    success "uv v$UV_VERSION"
else
    fail "uv 未安装"
    MISSING+=("uv")
fi

# --- Docker (可选) ---
DOCKER_AVAILABLE=false
if command -v docker &>/dev/null; then
    if docker info &>/dev/null 2>&1; then
        DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
        success "Docker v$DOCKER_VERSION (可用)"
        DOCKER_AVAILABLE=true
    else
        warn "Docker 已安装但未运行"
    fi
else
    info "Docker 未安装 (可选)"
fi

echo ""
if [ ${#MISSING[@]} -gt 0 ]; then
    warn "以下依赖缺失，请先安装："
    echo ""
    for dep in "${MISSING[@]}"; do
        case "$dep" in
            node)
                echo -e "  ${YELLOW}Node.js >= 20${NC}"
                echo -e "    macOS:  ${CYAN}brew install node@20${NC}"
                echo -e "    Linux:  ${CYAN}curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs${NC}"
                echo -e "    或:     ${CYAN}nvm install 20 && nvm use 20${NC}"
                ;;
            pnpm)
                echo -e "  ${YELLOW}pnpm >= 9${NC}"
                echo -e "    ${CYAN}npm install -g pnpm@9${NC}"
                echo -e "    或:     ${CYAN}corepack enable && corepack prepare pnpm@latest --activate${NC}"
                ;;
            python)
                echo -e "  ${YELLOW}Python >= 3.12${NC}"
                echo -e "    macOS:  ${CYAN}brew install python@3.12${NC}"
                echo -e "    Linux:  参考 https://www.python.org/downloads/${NC}"
                ;;
            uv)
                echo -e "  ${YELLOW}uv${NC}"
                echo -e "    ${CYAN}curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
                ;;
        esac
    done
    echo ""
    fail "请安装上述依赖后重新运行此脚本: ./install.sh"
    exit 1
fi

success "所有必需依赖已就绪"
echo ""

# ============================================
# Step 2: 依赖安装
# ============================================
info "Step 2/5: 安装项目依赖..."
echo ""

# 前端依赖
info "安装前端依赖 (pnpm install)..."
cd frontend
# pnpm v11+ 可能因 ignored build scripts 返回非 0 退出码，检查 node_modules 是否存在即可
pnpm install 2>&1 || true
if [ -d "node_modules" ]; then
    success "前端依赖安装完成"
else
    fail "前端依赖安装失败"
    exit 1
fi
cd "$SCRIPT_DIR"

# 后端依赖
info "安装后端依赖 (uv sync)..."
cd backend
if uv sync --extra dev; then
    success "后端依赖安装完成"
else
    fail "后端依赖安装失败"
    exit 1
fi
cd "$SCRIPT_DIR"

echo ""
success "项目依赖安装完成"
echo ""

# ============================================
# Step 3: 配置引导
# ============================================
info "Step 3/5: LLM 配置引导..."
echo ""

ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

if [ -f "$ENV_FILE" ]; then
    success ".env 文件已存在"
    echo ""
    read -rp "是否重新配置 LLM? (y/N): " RECONFIGURE
    if [[ ! "$RECONFIGURE" =~ ^[Yy]$ ]]; then
        info "跳过配置，使用现有 .env"
        echo ""
        # 跳到 Step 4
        SKIP_CONFIG=true
    fi
fi

if [ "${SKIP_CONFIG:-false}" != "true" ]; then
    # 复制 .env.example
    if [ ! -f "$ENV_FILE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        success "已从 .env.example 创建 .env"
    fi

    echo ""
    echo -e "${CYAN}请配置 LLM 信息（直接回车使用默认值）:${NC}"
    echo ""

    # LLM Provider
    read -rp "LLM Provider [openai/claude/deepseek/custom] (默认 openai): " INPUT_PROVIDER
    PROVIDER="${INPUT_PROVIDER:-openai}"

    # API Key
    read -rp "LLM API Key (必填): " INPUT_KEY
    if [ -z "$INPUT_KEY" ]; then
        warn "API Key 为空，AI 功能将无法使用。稍后可编辑 .env 填入"
    fi

    # Base URL
    case "$PROVIDER" in
        deepseek)
            DEFAULT_URL="https://api.deepseek.com/v1"
            DEFAULT_MODEL="deepseek-chat"
            ;;
        claude)
            DEFAULT_URL="https://api.anthropic.com"
            DEFAULT_MODEL="claude-sonnet-4-20250514"
            ;;
        *)
            DEFAULT_URL=""
            DEFAULT_MODEL="gpt-4o"
            ;;
    esac
    read -rp "LLM Base URL (默认 ${DEFAULT_URL:-空}): " INPUT_URL
    BASE_URL="${INPUT_URL:-$DEFAULT_URL}"

    read -rp "LLM Model (默认 $DEFAULT_MODEL): " INPUT_MODEL
    MODEL="${INPUT_MODEL:-$DEFAULT_MODEL}"

    # 写入 .env
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS sed
        sed -i '' "s|^LLM_PROVIDER=.*|LLM_PROVIDER=$PROVIDER|" "$ENV_FILE"
        sed -i '' "s|^LLM_API_KEY=.*|LLM_API_KEY=$INPUT_KEY|" "$ENV_FILE"
        sed -i '' "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$BASE_URL|" "$ENV_FILE"
        sed -i '' "s|^LLM_MODEL=.*|LLM_MODEL=$MODEL|" "$ENV_FILE"
    else
        # GNU sed
        sed -i "s|^LLM_PROVIDER=.*|LLM_PROVIDER=$PROVIDER|" "$ENV_FILE"
        sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$INPUT_KEY|" "$ENV_FILE"
        sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$BASE_URL|" "$ENV_FILE"
        sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$MODEL|" "$ENV_FILE"
    fi

    success "LLM 配置已写入 .env"
    echo ""
fi

# ============================================
# Step 4: Docker 检测
# ============================================
info "Step 4/5: Docker 检测..."
echo ""

if [ "$DOCKER_AVAILABLE" = true ]; then
    success "Docker 可用！你可以使用 Docker 一键启动："
    echo ""
    echo -e "  ${CYAN}docker compose up${NC}"
    echo ""
    info "Docker 方式无需 Node.js / Python 环境，适合快速体验"
else
    info "Docker 不可用，将使用本地开发模式启动"
fi

echo ""

# ============================================
# Step 5: 完成
# ============================================
info "Step 5/5: 安装完成！"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}    Resume-Agent 安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "启动方式："
echo ""
if [ "$DOCKER_AVAILABLE" = true ]; then
    echo -e "  Docker 一键启动:  ${CYAN}docker compose up${NC}"
    echo -e "  访问地址:        ${CYAN}http://localhost:5173${NC}"
    echo ""
fi
echo -e "  本地开发启动:    ${CYAN}make dev${NC}"
echo -e "  前端地址:        ${CYAN}http://localhost:5173${NC}"
echo -e "  后端地址:        ${CYAN}http://localhost:8000${NC}"
echo ""
echo -e "  运行测试:        ${CYAN}make test${NC}"
echo ""
echo -e "  配置文件:        ${CYAN}.env${NC} (如需修改 LLM 配置，编辑此文件)"
echo ""
