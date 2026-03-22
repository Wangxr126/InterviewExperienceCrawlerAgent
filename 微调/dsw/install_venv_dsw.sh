#!/usr/bin/env bash
# PAI-DSW 推荐：新建虚拟环境，与系统自带的 TensorFlow/lmdeploy 隔离，避免 protobuf / peft 冲突。
# 用法：cd 到含 train_lora.py 的目录后执行
#   bash dsw/install_venv_dsw.sh
set -euo pipefail

FINETUNE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FINETUNE_ROOT"

VENV_DIR="${VENV_DIR:-$FINETUNE_ROOT/.venv_finetune}"
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# 与仓库 requirements.txt「GPU 微调」一致：Windows 本地为 2.5.1+cu124；Linux DSW 用官方 cu121 轮子（勿用镜像自带 2.3.x）
TORCH_CUDA="${TORCH_CUDA:-cu121}"
TORCH_VER="${TORCH_VER:-2.5.1}"
TV_VER="${TV_VER:-0.20.1}"
TA_VER="${TA_VER:-2.5.1}"

echo "==> 工作目录: $FINETUNE_ROOT"
echo "==> 将创建 venv: $VENV_DIR"
echo "==> PyTorch 版本与本地说明对齐: ${TORCH_VER}+${TORCH_CUDA}（见 微调/dsw/对齐本地微调环境.txt）"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "==> venv python: $(which python)"
pip install -U pip setuptools wheel -i "$PIP_INDEX" --default-timeout 300

echo "==> 安装 PyTorch 三件套 + xformers（与 requirements.txt 第 65–67 行语义一致；Linux 用 ${TORCH_CUDA} 索引）"
pip install \
  "torch==${TORCH_VER}" "torchvision==${TV_VER}" "torchaudio==${TA_VER}" \
  --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}"
pip install xformers --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}"

python - <<'PY'
import torch
print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
PY

echo "==> 安装其余依赖（PyPI: $PIP_INDEX；transformers 等与根目录 requirements.txt 对齐）"
pip install -r "dsw/requirements-dsw.txt" -i "$PIP_INDEX" --default-timeout 300

echo "==> 验证 unsloth / xformers"
python - <<'PY'
import xformers
import unsloth
from unsloth import FastLanguageModel
print("xformers OK, unsloth OK")
PY

echo "==> 完成。之后每次训练前先执行:"
echo "    source $VENV_DIR/bin/activate"
echo "    cd $FINETUNE_ROOT && python train_lora.py"
