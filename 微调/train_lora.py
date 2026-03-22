# -*- coding: utf-8 -*-
# 一键微调脚本（Unsloth LoRA/QLoRA）
# 由后端 generate_training_script 生成；亦可手动编辑后在本目录执行 python train_lora.py

import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# 须在 import unsloth 之前：降低 Windows 上 inductor/triton 相关问题
os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 国内网络：拉取 HuggingFace 模型（可设 HF_ENDPOINT 覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

import json
import time
from datetime import datetime

from unsloth import FastLanguageModel
from datasets import load_dataset
import torch


def tlog(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# 路径相对本脚本目录，避免 Windows 下反斜杠转义导致路径错误
_SCRIPT_DIR = Path(__file__).resolve().parent
_OUTPUT_SUBDIR = "qwen3-4b-miner-lora"
OUTPUT_DIR = str(_SCRIPT_DIR / "lora_output" / _OUTPUT_SUBDIR)
DATA_PATH = str(_SCRIPT_DIR / "training_data_alpaca.jsonl")

# ========== 配置（来自微调界面） ==========
BASE_MODEL = "unsloth/Qwen3-4B"
# 8GB 显存建议 True（QLoRA）；有足够显存可改 False
LOAD_IN_4BIT = True
# 长 JSON 面经数据：2048 会大量截断；8GB 本机建议先 4096，仍截断可试 8192 且 BATCH_SIZE=1
MAX_SEQ_LENGTH = 4096
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LEARNING_RATE = 0.0002
NUM_EPOCHS = 3
# 每卡 batch；显存不足可改为 1。有效 batch = BATCH_SIZE × GRAD_ACCUM × GPU 数（与显存、速度强相关）
BATCH_SIZE = 2
GRAD_ACCUM = 8
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01
USE_RSLORA = True
BF16 = True
FP16 = False
_DATASET_NUM_PROC = 0 if sys.platform == "win32" else 2
_fin_ms = os.environ.get("FINETUNE_MAX_STEPS", "").strip()
TRAIN_MAX_STEPS = int(_fin_ms) if _fin_ms.isdigit() else -1
_ls = os.environ.get("FINETUNE_LOGGING_STEPS", "").strip()
# 总步数很少时若 logging_steps=10 则全程无 loss 输出，像卡住；默认每步打日志，长训可设 FINETUNE_LOGGING_STEPS=50
LOGGING_STEPS = max(1, int(_ls)) if _ls.isdigit() else 1
# 可视化：FINETUNE_REPORT_TO=tensorboard（或 tb）→ 用 tensorboard --logdir 查看 loss 曲线；wandb 需已登录
_rep = os.environ.get("FINETUNE_REPORT_TO", "").strip().lower()
if _rep in ("tensorboard", "tb"):
    REPORT_TO = "tensorboard"
elif _rep == "wandb":
    REPORT_TO = "wandb"
else:
    REPORT_TO = "none"

def main():
    if not Path(DATA_PATH).is_file():
        raise SystemExit(f"数据文件不存在: {DATA_PATH}")
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA：请安装 GPU 版 PyTorch（如 2.5.1+cu124）后再训练。")
    tlog("加载模型...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=LOAD_IN_4BIT,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
        use_rslora=USE_RSLORA,
    )
    tlog("加载数据...")
    dataset = load_dataset("json", data_files=DATA_PATH, split="train")
    def format_instruction(example):
        text = f"""<|im_start|>user
{example["instruction"]}

{example["input"]}<|im_end|>
<|im_start|>assistant
{example["output"]}<|im_end|>"""
        return {"text": text}
    dataset = dataset.map(
        format_instruction,
        remove_columns=dataset.column_names,
        num_proc=_DATASET_NUM_PROC,
    )
    from trl import SFTTrainer
    from transformers import TrainingArguments, TrainerCallback

    class _StepHeartbeatCallback(TrainerCallback):
        """仅提示首个 micro-batch：梯度累积下 on_step_begin 每个 micro-batch 都会触发，不宜每条都打。"""
        def __init__(self):
            self._seen = False

        def on_step_begin(self, args, state, control, **kwargs):
            if not self._seen:
                self._seen = True
                tlog("已进入训练迭代：第 1 个 micro-batch 开始（长序列/首次 GPU 计算可能较慢，请等待 loss 日志）")

        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs:
                return
            parts = []
            for k, v in logs.items():
                if isinstance(v, float):
                    parts.append(f"{k}={v:.6f}")
                else:
                    parts.append(f"{k}={v}")
            tlog(f"step {state.global_step} | " + " | ".join(parts))

    class _EpochTimingCallback(TrainerCallback):
        """每轮 epoch 结束写入 epoch_times.json，并在控制台打印本 epoch 用时。"""

        def __init__(self, out_path: Path):
            self.out_path = out_path
            self._train_t0 = None
            self._epoch_t0 = None
            self._epoch_num = None
            self.per_epoch = []

        def on_train_begin(self, args, state, control, **kwargs):
            self._train_t0 = time.perf_counter()

        def on_epoch_begin(self, args, state, control, **kwargs):
            self._epoch_t0 = time.perf_counter()
            # 进入第几轮（1-based）；首轮开始时 state.epoch 一般为 0
            try:
                self._epoch_num = int(state.epoch) + 1
            except (TypeError, ValueError):
                self._epoch_num = 1

        def on_epoch_end(self, args, state, control, **kwargs):
            if self._epoch_t0 is None:
                return
            dur = time.perf_counter() - self._epoch_t0
            en = self._epoch_num or 1
            rec = {
                "epoch": en,
                "duration_sec": round(dur, 3),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.per_epoch.append(rec)
            tlog(f"Epoch {en} 完成，本 epoch 用时 {dur:.1f}s（约 {dur / 60:.2f} min）")
            self._write_json(total_sec=None)

        def on_train_end(self, args, state, control, **kwargs):
            total = None
            if self._train_t0 is not None:
                total = round(time.perf_counter() - self._train_t0, 3)
            self._write_json(total_sec=total)
            if total is not None:
                tlog(
                    f"训练总用时 {total}s（约 {total / 60:.2f} min），各 epoch 耗时已写入 {self.out_path}"
                )

        def _write_json(self, total_sec):
            payload = {
                "output_dir": str(self.out_path.parent.resolve()),
                "per_epoch": self.per_epoch,
                "total_training_sec": total_sec,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            self.out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    epoch_json = Path(OUTPUT_DIR) / "epoch_times.json"
    n_gpu = max(1, torch.cuda.device_count())
    eff_batch = BATCH_SIZE * GRAD_ACCUM * n_gpu
    tlog(
        f"有效 batch size = 每卡{BATCH_SIZE} × 梯度累积{GRAD_ACCUM} × GPU{n_gpu} = {eff_batch}；"
        "慢多为序列长与反传开销，非单纯「batch 大」。OOM 时优先减 BATCH_SIZE 或 MAX_SEQ_LENGTH。"
    )
    tlog(f"开始训练… logging_steps={LOGGING_STEPS}，max_steps={TRAIN_MAX_STEPS}，样本数={len(dataset)}，report_to={REPORT_TO}")
    if REPORT_TO == "tensorboard":
        _tb = Path(OUTPUT_DIR) / "tensorboard"
        tlog(f"TensorBoard 目录: {_tb.resolve()}  执行: tensorboard --logdir \"{_tb}\"")
    elif REPORT_TO == "wandb":
        tlog("已启用 W&B，需本机已 wandb login；浏览器可查看曲线。")
    tlog("首个 optimizer step 前向+反传可能需数分钟，请等待下方 loss 行出现。")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=_DATASET_NUM_PROC,
        packing=False,
        callbacks=[
            _StepHeartbeatCallback(),
            _EpochTimingCallback(epoch_json),
        ],
        args=TrainingArguments(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            learning_rate=LEARNING_RATE,
            num_train_epochs=NUM_EPOCHS,
            warmup_ratio=WARMUP_RATIO,
            weight_decay=WEIGHT_DECAY,
            bf16=BF16,
            fp16=FP16,
            logging_steps=LOGGING_STEPS,
            save_strategy="epoch",
            report_to=REPORT_TO,
            logging_dir=str(Path(OUTPUT_DIR) / "tensorboard")
            if REPORT_TO == "tensorboard"
            else None,
            dataloader_pin_memory=False,
            max_steps=TRAIN_MAX_STEPS,
            disable_tqdm=False,
        ),
    )
    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    tlog(f"训练完成，模型已保存到 {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
