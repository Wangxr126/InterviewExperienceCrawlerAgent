"""
Model Bench API
从 DSW 推理服务并行拉取多个模型的流式回答，通过 SSE 推给前端。

GET/POST /api/model-bench/stream
  question      : 题目文本
  question_id   : （可选）题目 ID，用于展示
  models        : 逗号分隔的模型 ID，如 base,seq2048,seq4096,seq8192
  server_url    : DSW 推理服务根 URL，如 http://localhost:8899

SSE 消息格式（JSON）：
  {"type":"start",   "model":"base"}
  {"type":"token",   "model":"base", "text":"..."}
  {"type":"done",    "model":"base", "elapsed_ms":1234}
  {"type":"error",   "model":"base", "text":"error msg"}
  {"type":"all_done"}
"""
import asyncio
import json
import time
from typing import List, Optional

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/model-bench", tags=["model-bench"])

_DEFAULT_SERVER = "http://localhost:8899"
_INFER_PATH = "/infer/stream"   # POST {question, model}
_FALLBACK_INFER_PATH = "/infer/compare-stream"  # GET ?question=...&models=...
_MODEL_TIMEOUT = 120.0


def _sse(data: dict) -> str:
    """编码单条 SSE 消息"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_one_model(
    client: httpx.AsyncClient,
    server_url: str,
    model_id: str,
    question: str,
    queue: asyncio.Queue,
):
    """向 DSW 服务发送单个模型请求，token 逐个放入 queue"""
    start = time.time()
    await queue.put({"type": "start", "model": model_id})
    async def _consume_stream(resp: httpx.Response):
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            # SSE 格式：data: {...}
            if line.startswith("data:"):
                raw = line[5:].strip()
            else:
                raw = line
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                # 纯文本 token（兼容非 JSON 流）
                await queue.put({"type": "token", "model": model_id, "text": raw})
                continue

            t = msg.get("type", "token")
            if t == "token":
                await queue.put({"type": "token", "model": model_id, "text": msg.get("text", "")})
            elif t == "done":
                elapsed_ms = int((time.time() - start) * 1000)
                await queue.put({"type": "done", "model": model_id, "elapsed_ms": elapsed_ms})
                return
            elif t == "error":
                await queue.put({"type": "error", "model": model_id, "text": msg.get("text", "unknown error")})
                return
            else:
                # 其他类型透传
                await queue.put({**msg, "model": model_id})
    try:
        url = server_url.rstrip("/") + _INFER_PATH
        try:
            async with client.stream(
                "POST",
                url,
                json={"question": question, "model": model_id},
                timeout=_MODEL_TIMEOUT,
            ) as resp:
                await _consume_stream(resp)
        except httpx.HTTPStatusError as e:
            # 兼容 infer_server.py 的 GET /infer/compare-stream
            if e.response is not None and e.response.status_code in (404, 405):
                fallback_url = server_url.rstrip("/") + _FALLBACK_INFER_PATH
                params = {"question": question, "models": model_id}
                async with client.stream("GET", fallback_url, params=params, timeout=_MODEL_TIMEOUT) as resp2:
                    await _consume_stream(resp2)
            else:
                raise
        # 如果流结束但没有 done 消息
        elapsed_ms = int((time.time() - start) * 1000)
        await queue.put({"type": "done", "model": model_id, "elapsed_ms": elapsed_ms})
    except Exception as e:
        await queue.put({"type": "error", "model": model_id, "text": f"{type(e).__name__}: {e}"})


async def _generate(
    server_url: str,
    model_ids: List[str],
    question: str,
):
    """SSE 生成器：并行启动所有模型请求，按到达顺序推送事件"""
    queue: asyncio.Queue = asyncio.Queue()
    done_count = 0
    total = len(model_ids)

    async with httpx.AsyncClient() as client:
        # 并行启动所有模型任务
        tasks = [
            asyncio.create_task(
                _stream_one_model(client, server_url, mid, question, queue)
            )
            for mid in model_ids
        ]

        while done_count < total:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=_MODEL_TIMEOUT + 5)
            except asyncio.TimeoutError:
                break

            yield _sse(msg)

            if msg.get("type") in ("done", "error"):
                done_count += 1

        # 等所有任务真正结束
        await asyncio.gather(*tasks, return_exceptions=True)

    yield _sse({"type": "all_done"})


@router.get("/stream")
async def model_bench_stream(
    question: str = Query(..., description="题目文本"),
    models: str = Query("base,seq2048,seq4096,seq8192", description="逗号分隔模型ID"),
    server_url: str = Query(_DEFAULT_SERVER, description="DSW 推理服务根地址"),
    question_id: Optional[str] = Query(None, description="题目ID（仅用于展示）"),
):
    model_ids = [m.strip() for m in models.split(",") if m.strip()]
    if not model_ids:
        model_ids = ["base"]
    if not question.strip():
        return StreamingResponse(
            iter([_sse({"type": "error", "model": "all", "text": "题目不能为空"})]),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        _generate(server_url, model_ids, question.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
