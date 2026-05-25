#!/bin/bash
# DocCheck · 一键部署脚本
#
# 适用环境：Linux (Ubuntu 20.04+/Debian 11+)
# 最低配置：2核2G
#
# 用法：
#     sudo bash deploy.sh
#
# 该脚本会：
#     1. 安装系统依赖（python3, pip 等）
#     2. 创建虚拟环境并安装 Python 包
#     3. 初始化数据库和种子数据
#     4. 创建 systemd 服务（自动开机启动）
#     5. 启动服务

set -euo pipefail

# ── 配置 ──
APP_NAME="doccheck"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-$(whoami)}"
APP_PORT=8000
PYTHON="python3"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"

# 清华镜像源（内网无外网时注释掉）
PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"

echo "=========================================="
echo "  DocCheck · 一键部署"
echo "=========================================="
echo "应用目录: $APP_DIR"
echo "服务端口: $APP_PORT"
echo "运行用户: $APP_USER"
echo "------------------------------------------"

# Step 1: 检查系统依赖
echo ""
echo "[1/5] 检查系统依赖..."

if ! command -v $PYTHON &>/dev/null; then
    echo "  安装 python3..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv
fi

# 检查中文字体（用于 PDF 导出）
if fc-list :lang=zh 2>/dev/null | grep -q .; then
    echo "  ✅ 中文字体已安装"
else
    echo "  ⚠️  未检测到中文字体，PDF 导出可能中文乱码"
    echo "     若要支持 PDF 中文: sudo apt install fonts-noto-cjk"
fi

echo "  ✅ 系统依赖检查完成"

# Step 2: 创建虚拟环境
echo ""
echo "[2/5] 创建 Python 虚拟环境..."

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    echo "  ✅ 虚拟环境已创建"
else
    echo "  ✅ 虚拟环境已存在，跳过"
fi

source "$VENV_DIR/bin/activate"

# Step 3: 安装 Python 依赖
echo ""
echo "[3/5] 安装 Python 包..."

pip install --upgrade pip -q $PIP_MIRROR
pip install -r "$APP_DIR/requirements.txt" $PIP_MIRROR

# 安装 reportlab（PDF 导出需要）
pip install reportlab $PIP_MIRROR 2>/dev/null || echo "  ⚠️  reportlab 安装失败，PDF 导出不可用"

echo "  ✅ Python 包安装完成"

# Step 4: 初始化数据库
echo ""
echo "[4/5] 初始化数据库..."

cd "$APP_DIR"
$PYTHON scripts/seed.py

echo "  ✅ 数据库初始化完成"

# Step 5: 创建 systemd 服务
echo ""
echo "[5/5] 创建 systemd 服务..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=DocCheck - AI Document Compliance Checker
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 0.0.0.0 --port $APP_PORT
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$APP_NAME"
systemctl restart "$APP_NAME"

echo "  ✅ systemd 服务已创建并启动"

# ── 完成 ──
echo ""
echo "=========================================="
echo "  🎉 DocCheck 部署完成！"
echo "=========================================="
echo ""
echo "  访问地址: http://$(hostname -I | awk '{print $1}'):$APP_PORT"
echo "  管理员:   admin / admin123"
echo "  审核员:   reviewer / review123"
echo ""
echo "  管理命令:"
echo "    sudo systemctl status $APP_NAME    # 查看状态"
echo "    sudo systemctl restart $APP_NAME   # 重启"
echo "    sudo journalctl -u $APP_NAME -f    # 查看日志"
echo ""
echo "=========================================="