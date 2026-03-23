# -*- coding: utf-8 -*-
"""
LoRA 对比推理服务 —— 在 DSW（GPU）上运行
用法：
  conda activate NewCoderAgent  # 或已安装 unsloth 的环境
  python infer_server.py

启动后在 DSW 控制台开启端口 8899 转发，把转发地址填入前端配置。
"""
import os
import sys
import json
import asyncio
import threading
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("UNSLOTH_DISABLE_STATISTICS", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

# 读取项目根目录 .env，便于在前端/后端之外直接运行此脚本时也能吃到配置。
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

import torch
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer, BitsAndBytesConfig
from peft import PeftModel

# ========== 配置 ==========
BASE_MODEL     = "unsloth/Qwen3-4B"
LOAD_IN_4BIT   = True
PORT           = int(os.environ.get("INFER_PORT", 8899))
MAX_NEW_TOKENS = int(os.environ.get("INFER_MAX_NEW_TOKENS", os.environ.get("MAX_NEW_TOKENS", 2048)))

# adapter 路径（None = 基础模型不加载 adapter）
ADAPTERS: dict[str, Optional[str]] = {
    "base":    None,
    "seq2048": str(_SCRIPT_DIR / "adapter/lora_seq2048/qwen3-4b-miner_r16_seq2048_bs1x16_ep3_lr2e-4"),
    "seq4096": str(_SCRIPT_DIR / "adapter/lora_seq4096/qwen3-4b-miner_r16_seq4096_bs1x16_ep3_lr2e-4"),
    "seq8192": str(_SCRIPT_DIR / "adapter/lora_seq8192/qwen3-4b-miner_r16_seq8192_bs1x32_ep3_lr2e-4"),
}

ADAPTER_LABELS = {
    "base":    "原始模型（无 LoRA）",
    "seq2048": "微调 seq=2048",
    "seq4096": "微调 seq=4096",
    "seq8192": "微调 seq=8192",
}

# ========== 全局模型 ==========
_base_model  = None
_tokenizer   = None
_model_lock  = threading.Lock()   # 同一时刻只能推理一个
_loaded_ok   = False
_load_error  = ""


def _load_models():
    global _base_model, _tokenizer, _loaded_ok, _load_error
    try:
        print(f"[startup] 加载基础模型 {BASE_MODEL} ...", flush=True)
        bnb_cfg = BitsAndBytesConfig(
            load_in_4bit=LOAD_IN_4BIT,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        ) if LOAD_IN_4BIT else None
        _tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
        _base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_cfg,
            device_map="auto",
            trust_remote_code=True,
        )
        _base_model.eval()
        print("[startup] 基础模型加载完成", flush=True)
        _loaded_ok = True
    except Exception as e:
        _load_error = str(e)
        print(f"[startup] 模型加载失败: {e}", flush=True)


# ========== FastAPI ==========
app = FastAPI(title="LoRA 对比推理服务")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    t = threading.Thread(target=_load_models, daemon=True)
    t.start()


@app.get("/health")
def health():
    return {"ok": _loaded_ok, "error": _load_error, "adapters": list(ADAPTERS.keys())}


@app.get("/models")
def list_models():
    result = []
    for k, path in ADAPTERS.items():
        result.append({
            "id":      k,
            "label":  ADAPTER_LABELS.get(k, k),
            "path":   path,
            "exists": path is None or Path(path).exists(),
        })
    return result


def _build_prompt(question: str) -> str:
    return (
        f"<|im_start|>system\n你是一名专业的技术面试助手，请给出清晰、完整的回答。<|im_end|>\n"
        f"<|im_start|>user\n{question}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def _infer_stream_sync(model, question: str, queue: asyncio.Queue, loop):
    """在普通线程里做 generate，把 token 塞到 asyncio Queue。"""
    try:
        prompt = _build_prompt(question)
        inputs = _tokenizer(prompt, return_tensors="pt").to(model.device)
        streamer = TextIteratorStreamer(
            _tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs = dict(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
            streamer=streamer,
        )
        gen_thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        gen_thread.start()
        for token in streamer:
            asyncio.run_coroutine_threadsafe(queue.put(("token", token)), loop)
        gen_thread.join()
    except Exception as e:
        asyncio.run_coroutine_threadsafe(queue.put(("error", str(e))), loop)
    finally:
        asyncio.run_coroutine_threadsafe(queue.put(("done", "")), loop)


@app.get("/infer/compare-stream")
async def compare_stream(
    question: str = Query(..., description="面试题目"),
    models: str = Query("base,seq2048,seq4096,seq8192", description="逗号分隔的模型 ID")
):
    """SSE 流式接口：依次对每个模型做推理，token 实时推送。"""
    if not _loaded_ok:
        async def err_gen():
            msg = json.dumps({"type": "error", "model": "all", "text": f"模型未就绪: {_load_error}"}, ensure_ascii=False)
            yield f"data: {msg}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    model_ids = [m.strip() for m in models.split(",") if m.strip() in ADAPTERS]
    if not model_ids:
        model_ids = list(ADAPTERS.keys())

    loop = asyncio.get_event_loop()

    async def generate():
        for model_id in model_ids:
            adapter_path = ADAPTERS[model_id]
            label = ADAPTER_LABELS.get(model_id, model_id)

            # 通知前端：该模型开始
            start_evt = json.dumps({"type": "start", "model": model_id, "label": label}, ensure_ascii=False)
            yield f"data: {start_evt}\n\n"

            # 检查 adapter 路径
            if adapter_path and not Path(adapter_path).exists():
                err_evt = json.dumps({"type": "error", "model": model_id, "text": f"adapter 路径不存在: {adapter_path}"}, ensure_ascii=False)
                yield f"data: {err_evt}\n\n"
                continue

            with _model_lock:
                try:
                    # 加载 adapter（若有）
                    if adapter_path:
                        model = PeftModel.from_pretrained(_base_model, adapter_path)
                        model.eval()
                    else:
                        model = _base_model

                    # 异步推理
                    queue: asyncio.Queue = asyncio.Queue()
                    t = threading.Thread(
                        target=_infer_stream_sync,
                        args=(model, question, queue, loop),
                        daemon=True,
                    )
                    t.start()

                    while True:
                        kind, text = await queue.get()
                        if kind == "done":
                            break
                        elif kind == "error":
                            evt = json.dumps({"type": "error", "model": model_id, "text": text}, ensure_ascii=False)
                            yield f"data: {evt}\n\n"
                            break
                        else:
                            evt = json.dumps({"type": "token", "model": model_id, "text": text}, ensure_ascii=False)
                            yield f"data: {evt}\n\n"

                except Exception as e:
                    evt = json.dumps({"type": "error", "model": model_id, "text": str(e)}, ensure_ascii=False)
                    yield f"data: {evt}\n\n"
                finally:
                    # 卸载 adapter，还原基础模型
                    if adapter_path and isinstance(model, PeftModel):
                        try:
                            model.unload()
                        except Exception:
                            pass

            done_evt = json.dumps({"type": "done", "model": model_id}, ensure_ascii=False)
            yield f"data: {done_evt}\n\n"

        # 所有模型跑完
        yield f"data: {json.dumps({'type': 'all_done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    print(f"[server] 启动推理服务，端口 {PORT}")
    print(f"[server] 健康检查: http://0.0.0.0:{PORT}/health")
    print(f"[server] 模型列表: http://0.0.0.0:{PORT}/models")
    print(f"[server] 推理接口: http://0.0.0.0:{PORT}/infer/compare-stream?question=你的问题")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
