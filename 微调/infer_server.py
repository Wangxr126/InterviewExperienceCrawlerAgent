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
import time
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
from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer, BitsAndBytesConfig
from peft import PeftModel

# ========== 配置 ==========
BASE_MODEL     = "unsloth/Qwen3-4B"
LOAD_IN_4BIT   = True
PORT           = int(os.environ.get("INFER_PORT", 8899))
MAX_NEW_TOKENS = int(os.environ.get("INFER_MAX_NEW_TOKENS", os.environ.get("MAX_NEW_TOKENS", 2048)))
MAX_INPUT_TOKENS = int(os.environ.get("INFER_MAX_INPUT_TOKENS", "2048"))

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


def _gpu_snapshot() -> dict:
    """返回当前 GPU 快照，便于排查是否真的走到 CUDA。"""
    snap = {
        "cuda_available": bool(torch.cuda.is_available()),
        "device_count": 0,
        "current_device": None,
        "device_name": "",
        "memory_allocated_mb": 0.0,
        "memory_reserved_mb": 0.0,
    }
    if not torch.cuda.is_available():
        return snap
    try:
        idx = torch.cuda.current_device()
        snap["device_count"] = torch.cuda.device_count()
        snap["current_device"] = idx
        snap["device_name"] = torch.cuda.get_device_name(idx)
        snap["memory_allocated_mb"] = round(torch.cuda.memory_allocated(idx) / (1024 * 1024), 2)
        snap["memory_reserved_mb"] = round(torch.cuda.memory_reserved(idx) / (1024 * 1024), 2)
    except Exception:
        pass
    return snap


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
        gpu_info = _gpu_snapshot()
        print(
            f"[startup] CUDA={gpu_info['cuda_available']} "
            f"device={gpu_info['device_name']} "
            f"allocated={gpu_info['memory_allocated_mb']}MB "
            f"reserved={gpu_info['memory_reserved_mb']}MB",
            flush=True,
        )
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
    return {
        "ok": _loaded_ok,
        "error": _load_error,
        "adapters": list(ADAPTERS.keys()),
        "gpu": _gpu_snapshot(),
    }


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
    # 模型对比与 Miner 提取保持一致：拼接 Miner 的 system/user prompt 后再送模型。
    try:
        from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt

        miner_system = get_miner_prompt()
        miner_user = format_miner_user_prompt(
            content=question,
            has_image=False,
            company="",
            position="",
        )
        return (
            f"<|im_start|>system\n{miner_system}<|im_end|>\n"
            f"<|im_start|>user\n{miner_user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
    except Exception:
        # 回退：避免 prompt 模块异常导致服务不可用
        return (
            f"<|im_start|>system\n你是一名专业的面经分析助手，请提取结构化面试题并输出 JSON。<|im_end|>\n"
            f"<|im_start|>user\n{question}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )


def _compose_chat_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def _build_prompt_from_payload(payload: dict) -> str:
    """
    统一构造 prompt：
    1) 有 prompt + system_prompt：直接拼接成 chat；
    2) 有 prompt（已是完整文本）：直接使用；
    3) 有 question：按 Miner Prompt 规则构造。
    """
    prompt = (payload.get("prompt") or "").strip()
    system_prompt = (payload.get("system_prompt") or "").strip()
    question = (payload.get("question") or "").strip()

    if prompt and system_prompt:
        return _compose_chat_prompt(system_prompt, prompt)
    if prompt:
        return prompt
    if question:
        return _build_prompt(question)
    return _build_prompt("请输出空结果：[]")


def _infer_stream_sync(model, final_prompt: str, infer_params: dict, queue: asyncio.Queue, loop):
    """在普通线程里做 generate，把 token 塞到 asyncio Queue。"""
    try:
        t0 = time.time()
        # 关键：在 8GB 显卡上，Miner 超长 prompt 容易触发 OOM，需强制截断输入长度
        input_ids = _tokenizer.encode(final_prompt, add_special_tokens=False)
        raw_len = len(input_ids)
        if raw_len > MAX_INPUT_TOKENS:
            print(
                f"[infer] 输入过长，已截断: raw_tokens={raw_len} -> {MAX_INPUT_TOKENS}",
                flush=True,
            )
        inputs = _tokenizer(
            final_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_INPUT_TOKENS,
        ).to(model.device)
        streamer = TextIteratorStreamer(
            _tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        first_token_sent = False
        gen_kwargs = dict(
            **inputs,
            max_new_tokens=int(infer_params.get("max_new_tokens") or min(MAX_NEW_TOKENS, 512)),
            temperature=float(infer_params.get("temperature") or 0.7),
            top_p=float(infer_params.get("top_p") or 0.9),
            do_sample=bool(infer_params.get("do_sample", True)),
            pad_token_id=_tokenizer.eos_token_id,
            streamer=streamer,
        )
        gen_thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        gen_thread.start()
        for token in streamer:
            if not first_token_sent:
                first_token_sent = True
                first_token_ms = int((time.time() - t0) * 1000)
                asyncio.run_coroutine_threadsafe(queue.put(("meta", {"first_token_ms": first_token_ms})), loop)
            asyncio.run_coroutine_threadsafe(queue.put(("token", token)), loop)
        gen_thread.join()
        total_ms = int((time.time() - t0) * 1000)
        asyncio.run_coroutine_threadsafe(queue.put(("meta", {"total_ms": total_ms})), loop)
    except Exception as e:
        err_text = str(e)
        # 对 OOM 给出明确、可操作的错误提示，避免前端“无输出卡住”
        if isinstance(e, torch.OutOfMemoryError) or ("out of memory" in err_text.lower()):
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            err_text = (
                "CUDA 显存不足（OOM）。建议："
                "1) 降低 max_new_tokens（如 256）；"
                "2) 缩短输入（减少帖子正文长度）；"
                "3) 减少并发请求，仅保留单模型。"
            )
            print(f"[infer][OOM] {err_text}", flush=True)
        asyncio.run_coroutine_threadsafe(queue.put(("error", err_text)), loop)
    finally:
        asyncio.run_coroutine_threadsafe(queue.put(("done", "")), loop)


def _resolve_model(model_id: str):
    adapter_path = ADAPTERS.get(model_id)
    if model_id not in ADAPTERS:
        raise ValueError(f"未知模型ID: {model_id}")
    if adapter_path and not Path(adapter_path).exists():
        raise FileNotFoundError(f"adapter 路径不存在: {adapter_path}")
    if adapter_path:
        model = PeftModel.from_pretrained(_base_model, adapter_path)
        model.eval()
        return model, adapter_path
    return _base_model, None


@app.post("/infer/stream")
async def infer_stream(payload: dict = Body(...)):
    """
    单模型统一流式接口（与 backend/api/model_bench_api.py 对齐）:
      入参支持:
        - question + model
        - question + model_id
        - prompt + system_prompt + model_id
      流式输出:
        data: {"type":"token","text":"..."}
        data: {"type":"done","elapsed_ms":1234,...}
        data: {"type":"error","text":"..."}
    """
    if not _loaded_ok:
        async def err_gen():
            msg = json.dumps({"type": "error", "text": f"模型未就绪: {_load_error}"}, ensure_ascii=False)
            yield f"data: {msg}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    model_id = (payload.get("model") or payload.get("model_id") or "base").strip()
    final_prompt = _build_prompt_from_payload(payload)
    loop = asyncio.get_event_loop()

    async def generate():
        t0 = time.time()
        queue: asyncio.Queue = asyncio.Queue()
        with _model_lock:
            model = None
            adapter_path = None
            token_count = 0
            first_token_ms = None
            model_total_ms = None
            try:
                model, adapter_path = _resolve_model(model_id)
                t = threading.Thread(
                    target=_infer_stream_sync,
                    args=(model, final_prompt, payload, queue, loop),
                    daemon=True,
                )
                t.start()

                while True:
                    kind, value = await queue.get()
                    if kind == "done":
                        break
                    if kind == "error":
                        evt = json.dumps({"type": "error", "text": value}, ensure_ascii=False)
                        yield f"data: {evt}\n\n"
                        break
                    if kind == "meta":
                        if isinstance(value, dict):
                            if "first_token_ms" in value:
                                first_token_ms = value["first_token_ms"]
                            if "total_ms" in value:
                                model_total_ms = value["total_ms"]
                        continue
                    token_count += 1
                    evt = json.dumps({"type": "token", "text": value}, ensure_ascii=False)
                    yield f"data: {evt}\n\n"

            except Exception as e:
                evt = json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False)
                yield f"data: {evt}\n\n"
            finally:
                if adapter_path and isinstance(model, PeftModel):
                    try:
                        model.unload()
                    except Exception:
                        pass

                elapsed_ms = int((time.time() - t0) * 1000)
                done_evt = json.dumps({
                    "type": "done",
                    "model": model_id,
                    "elapsed_ms": elapsed_ms,
                    "first_token_ms": first_token_ms,
                    "model_total_ms": model_total_ms,
                    "token_count": token_count,
                    "gpu": _gpu_snapshot(),
                }, ensure_ascii=False)
                yield f"data: {done_evt}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
                    final_prompt = _build_prompt(question)
                    queue: asyncio.Queue = asyncio.Queue()
                    t = threading.Thread(
                        target=_infer_stream_sync,
                        args=(model, final_prompt, {"max_new_tokens": MAX_NEW_TOKENS}, queue, loop),
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
