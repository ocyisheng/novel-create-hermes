#!/usr/bin/env bash
# ============================================================
# novel-create-hermes 环境初始化脚本 (macOS/Linux)
# 创建共用虚拟环境，多个小说项目共享
# 支持：系统 Python / conda 环境中的 Python
# ============================================================

set -e

echo "========================================"
echo "novel-create-hermes 环境初始化"
echo "========================================"
echo ""

# === 检测 Python 来源：系统 Python → conda Python ===
PYTHON_CMD=""

# 1. 先尝试系统 Python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo "[检测] 使用系统 Python"
    python3 --version
    echo ""
# 2. 尝试 conda 环境中的 Python
elif command -v conda &> /dev/null; then
    echo "[检测] 使用 conda base 环境中的 Python"
    conda run -n base python3 --version
    echo ""
    PYTHON_CMD="conda_run"
else
    echo "[错误] 未检测到 Python 或 conda"
    echo "  - 安装 Python 3.8+: https://www.python.org/downloads/"
    echo "  - 或安装 conda: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# 检查是否已有虚拟环境
if [ -d ".venv" ]; then
    echo "[提示] 虚拟环境已存在"
    echo ""
    read -p "是否重新创建？(y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "[1/3] 删除旧环境..."
        rm -rf .venv
    else
        echo "[2/3] 激活虚拟环境..."
        source .venv/bin/activate
        echo "[3/3] 安装/更新依赖..."
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        pip install -r "$SCRIPT_DIR/requirements.txt"
        echo ""
        echo "========================================"
        echo "环境已就绪！"
        echo "========================================"
        echo ""
        echo "使用方法:"
        echo "  1. 激活环境: source .venv/bin/activate"
        echo "  2. 验证环境: python .opencode/skills/novel-env-setup/scripts/setup.py"
        echo "  3. 进入小说项目目录运行技能脚本"
        echo ""
        echo "多个小说项目共用此环境，无需重复创建"
        exit 0
    fi
fi

echo "[1/3] 创建虚拟环境..."
if [ "$PYTHON_CMD" = "conda_run" ]; then
    conda run -n base python3 -m venv .venv
else
    python3 -m venv .venv
fi

echo "[2/3] 激活虚拟环境..."
source .venv/bin/activate

echo "[3/3] 安装依赖..."
# requirements.txt 与脚本在同一目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "========================================"
echo "环境初始化完成！"
echo "========================================"
echo ""
echo "使用方法:"
echo "  1. 激活环境: source .venv/bin/activate"
echo "  2. 验证环境: python .opencode/skills/novel-env-setup/scripts/setup.py"
echo "  3. 进入小说项目目录运行技能脚本"
echo ""
echo "多个小说项目共用此环境，无需重复创建"
