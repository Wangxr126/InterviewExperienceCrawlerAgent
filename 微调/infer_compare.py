# -*- coding: utf-8 -*-
# LoRA adapter 推理对比脚本
# 用法：python infer_compare.py
# 可通过环境变量指定单个 adapter：ADAPTER_PATH=... python infer_compare.py

import os
import sys
from pathlib import Path

os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("UNSLOTH_DISABLE_STATISTICS", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# ========== 配置 ==========
BASE_MODEL = "unsloth/Qwen3-4B"          # 与训练时相同
LOAD_IN_4BIT = True

_SCRIPT_DIR = Path(__file__).resolve().parent

# 三组 adapter 路径
ADAPTERS = {
    "seq2048": str(_SCRIPT_DIR / "adapter/lora_seq2048/qwen3-4b-miner_r16_seq2048_bs1x16_ep3_lr2e-4"),
    "seq4096": str(_SCRIPT_DIR / "adapter/lora_seq4096/qwen3-4b-miner_r16_seq4096_bs1x16_ep3_lr2e-4"),
    "seq8192": str(_SCRIPT_DIR / "adapter/lora_seq8192/qwen3-4b-miner_r16_seq8192_bs1x32_ep3_lr2e-4"),
}

# 若通过环境变量指定单个 adapter
_single = os.environ.get("ADAPTER_PATH", "").strip()
if _single:
    ADAPTERS = {"custom": _single}

# 测试问题（可自行修改）
TEST_QUESTIONS = [
    "请介绍一下 Java 中的 HashMap 和 HashTable 的区别？",
    "解释一下 TCP 三次握手的过程。",
    "什么是 Spring Boot 的自动配置原理？",
]

MAX_NEW_TOKENS = 512


def load_base_model():
    print(f"[加载基础模型] {BASE_MODEL} (4bit={LOAD_IN_4BIT})")
    from transformers import BitsAndBytesConfig
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=LOAD_IN_4BIT,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    ) if LOAD_IN_4BIT else None

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    return model, tokenizer


def infer(model, tokenizer, question: str) -> str:
    prompt = f"<|im_start|>user\n{question}<|im_end|>\n<|im_start|>assistant\n"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    # 只返回新生成的部分
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def main():
    if not torch.cuda.is_available():
        print("[警告] 未检测到 CUDA，将使用 CPU（速度很慢）")

    base_model, tokenizer = load_base_model()

    sep = "=" * 60

    for adapter_name, adapter_path in ADAPTERS.items():
        if not Path(adapter_path).exists():
            print(f"[跳过] {adapter_name}: 路径不存在 {adapter_path}")
            continue

        print(f"\n{sep}")
        print(f"[加载 adapter] {adapter_name}: {adapter_path}")
        print(sep)

        # 加载 LoRA adapter
        model = PeftModel.from_pretrained(base_model, adapter_path)
        model.eval()

        for i, q in enumerate(TEST_QUESTIONS, 1):
            print(f"\n[Q{i}] {q}")
            print("-" * 40)
            answer = infer(model, tokenizer, q)
            print(answer)

        # 卸载 adapter，准备加载下一个
        base_model = model.unload()  # 还原为基础模型
        print(f"\n[完成] {adapter_name}")

    print(f"\n{sep}")
    print("全部对比完成")


if __name__ == "__main__":
    main()
