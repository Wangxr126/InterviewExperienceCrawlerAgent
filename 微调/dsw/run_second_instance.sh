#!/usr/bin/env bash
# 第二路训练：独立输出 + 后台日志。默认复用第一路已装好的 venv，不执行 pip 安装。
#
# 目录布局（与并行 zip 一致）：
#   .../finetune/       第一路，且已 bash dsw/install_venv_dsw.sh → .venv_finetune
#   .../finetune_run2/  本脚本
#
#   cd .../finetune_run2 && bash dsw/run_second_instance.sh
#
# 指定其它 venv：export VENV_DIR=/path/to/.venv_finetune
# 必须在 run2 下新建环境（慢）：FINETUNE_BOOTSTRAP_VENV=1 bash dsw/run_second_instance.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PARENT="$(cd "$ROOT/.." && pwd)"

if [[ -n "${VENV_DIR:-}" ]]; then
  :
elif [[ -x "$PARENT/finetune/.venv_finetune/bin/python" ]]; then
  VENV_DIR="$PARENT/finetune/.venv_finetune"
elif [[ -x "$ROOT/.venv_finetune/bin/python" ]]; then
  VENV_DIR="$ROOT/.venv_finetune"
elif [[ -x "$ROOT/.venv_finetune_run2/bin/python" ]]; then
  VENV_DIR="$ROOT/.venv_finetune_run2"
else
  VENV_DIR="$PARENT/finetune/.venv_finetune"
fi
export VENV_DIR

export FINETUNE_OUTPUT_SUBDIR="${FINETUNE_OUTPUT_SUBDIR:-qwen3-4b-miner-lora-run2}"
export FINETUNE_MAX_SEQ_LENGTH="${FINETUNE_MAX_SEQ_LENGTH:-8192}"
export FINETUNE_BATCH_SIZE="${FINETUNE_BATCH_SIZE:-1}"
export FINETUNE_GRAD_ACCUM="${FINETUNE_GRAD_ACCUM:-16}"

LOG="${ROOT}/train_run2_$(date +%Y%m%d_%H%M%S).log"
PY="$VENV_DIR/bin/python"

if [[ ! -x "$PY" ]]; then
  if [[ "${FINETUNE_BOOTSTRAP_VENV:-0}" == "1" ]]; then
    export VENV_DIR="$ROOT/.venv_finetune_run2"
    PY="$VENV_DIR/bin/python"
    echo "==> FINETUNE_BOOTSTRAP_VENV=1：创建 $VENV_DIR 并安装依赖（较慢）"
    bash "$ROOT/dsw/install_venv_dsw.sh"
  else
    echo "错误：未找到虚拟环境: $PY"
    echo "请先在第一套目录安装：cd $PARENT/finetune && bash dsw/install_venv_dsw.sh"
    echo "或: export VENV_DIR=/已有/.venv 后再执行本脚本。"
    exit 1
  fi
fi

echo "==> 使用已有 venv: $VENV_DIR"
echo "==> 单卡两路同时训练易 OOM，请自行确认显存。"
echo "==> 输出: lora_output/$FINETUNE_OUTPUT_SUBDIR"
echo "==> 日志: $LOG"

nohup env \
  FINETUNE_OUTPUT_SUBDIR="$FINETUNE_OUTPUT_SUBDIR" \
  FINETUNE_MAX_SEQ_LENGTH="$FINETUNE_MAX_SEQ_LENGTH" \
  FINETUNE_BATCH_SIZE="$FINETUNE_BATCH_SIZE" \
  FINETUNE_GRAD_ACCUM="$FINETUNE_GRAD_ACCUM" \
  "$PY" "$ROOT/train_lora.py" >>"$LOG" 2>&1 &

echo "已启动 pid=$!"
