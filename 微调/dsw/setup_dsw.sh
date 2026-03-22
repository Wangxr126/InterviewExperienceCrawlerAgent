#!/usr/bin/env bash
# 在 PAI-DSW「打开 Terminal」后，cd 到含 train_lora.py 的目录，执行：
#   bash dsw/setup_dsw.sh
#
# 默认走「独立 venv」（install_venv_dsw.sh），避免破坏系统 Python 里 TensorFlow/protobuf。
# 若坚持系统环境（不推荐）：export FINETUNE_USE_SYSTEM_PYTHON=1
set -euo pipefail

FINETUNE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FINETUNE_ROOT"

echo "==> 工作目录: $FINETUNE_ROOT"

if [[ -f "dsw/env_dsw.sh" ]]; then
  # shellcheck source=/dev/null
  source "dsw/env_dsw.sh"
  echo "==> 已加载 dsw/env_dsw.sh"
fi

if [[ "${FINETUNE_USE_SYSTEM_PYTHON:-}" != "1" ]]; then
  echo "==> 使用独立 venv 安装依赖（推荐）"
  bash "dsw/install_venv_dsw.sh"
  # shellcheck source=/dev/null
  source "${VENV_DIR:-$FINETUNE_ROOT/.venv_finetune}/bin/activate"
else
  echo "==> GPU / PyTorch 探测（系统 Python）"
  python3 - <<'PY'
import sys
try:
    import torch
    print("torch:", torch.__version__)
    print("cuda_available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("device:", torch.cuda.get_device_name(0))
except Exception as e:
    print("import torch 失败:", e)
    sys.exit(1)
PY
  PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
  echo "==> 安装依赖（PyPI 镜像: $PIP_INDEX）— 可能污染系统环境，不推荐"
  pip install -U pip -i "$PIP_INDEX" --default-timeout 300
  pip install -r "dsw/requirements-dsw.txt" -i "$PIP_INDEX" --default-timeout 300
  TORCH_CUDA="${TORCH_CUDA:-cu121}"
  pip install xformers --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}"
fi

echo "==> 检查数据文件"
if [[ ! -f "training_data_alpaca.jsonl" ]]; then
  echo "错误: 缺少 training_data_alpaca.jsonl，请与 train_lora.py 同目录放置后再运行。"
  exit 1
fi

echo "==> 可选：快速试跑（取消注释下一行）"
# export FINETUNE_MAX_STEPS=20

echo "==> 开始训练"
python train_lora.py
