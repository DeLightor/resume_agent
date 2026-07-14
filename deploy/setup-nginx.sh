#!/bin/bash
# Nginx 部署脚本 - 在服务器上执行
# 用法: bash deploy/setup-nginx.sh

set -e

echo "===== Nginx 部署脚本 ====="

# 1. 安装 Nginx
if ! command -v nginx &> /dev/null; then
    echo "[1/5] 安装 Nginx..."
    sudo apt update && sudo apt install -y nginx
else
    echo "[1/5] Nginx 已安装，跳过"
fi

# 2. 部署配置文件
echo "[2/5] 部署 Nginx 配置文件..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$SCRIPT_DIR/nginx-xmutlhj.conf" /etc/nginx/sites-available/xmutlhj.eu.cc

# 3. 启用站点
echo "[3/5] 启用站点..."
sudo ln -sf /etc/nginx/sites-available/xmutlhj.eu.cc /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 4. 测试并重启
echo "[4/5] 测试配置并重启 Nginx..."
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# 5. 开放防火墙
echo "[5/5] 开放防火墙端口..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8080/tcp
    sudo ufw reload
    echo "防火墙已配置"
else
    echo "ufw 未安装，请手动确认 8080 端口已开放"
fi

echo ""
echo "===== 部署完成 ====="
echo "访问 http://xmutlhj.eu.cc:8080 验证"
echo ""
echo "注意: 国内服务器未备案域名无法使用 80/443 端口"
echo "当前使用 8080 端口，如需 HTTPS 需先完成 ICP 备案"
