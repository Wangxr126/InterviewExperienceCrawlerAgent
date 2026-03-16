#!/bin/bash
# 面经Agent启动脚本（Linux/Mac）
# 自动激活conda环境并启动后端，需在项目根目录执行：bash backend/scripts/start.sh

echo "========================================"
echo "面经Agent启动脚本"
echo "========================================"
echo ""

echo "[1/2] 激活Conda环境: NewCoderAgent"
source $(conda info --base)/etc/profile.d/conda.sh
conda activate NewCoderAgent

if [ $? -ne 0 ]; then
    echo "错误: 无法激活环境 NewCoderAgent"
    echo "请确保已创建此环境: conda create -n NewCoderAgent python=3.10"
    exit 1
fi

echo "[2/2] 启动后端服务..."
echo ""
python run.py
