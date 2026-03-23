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
import os
import logging
from urllib.parse import urlparse
from typing import List, Optional

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/model-bench", tags=["model-bench"])
logger = logging.getLogger(__name__)

# 推理服务默认地址（由后端统一转发，前端无需直连）
_DEFAULT_SERVER = os.getenv("MODEL_BENCH_SERVER_URL", "http://localhost:8899")
_INFER_PATH = "/infer/stream"   # POST {question, model}
_FALLBACK_INFER_PATH = "/infer/compare-stream"  # GET ?question=...&models=...
_MODEL_TIMEOUT = float(os.getenv("MODEL_BENCH_TIMEOUT_SECONDS", "600"))
_QUEUE_IDLE_TIMEOUT = float(os.getenv("MODEL_BENCH_QUEUE_IDLE_TIMEOUT_SECONDS", str(_MODEL_TIMEOUT + 30)))
_HTTP_TIMEOUT = httpx.Timeout(connect=20.0, read=_MODEL_TIMEOUT, write=60.0, pool=60.0)
_ENABLE_DOCKER_HOST_FALLBACK = os.getenv("MODEL_BENCH_ENABLE_DOCKER_HOST_FALLBACK", "0").lower() in {"1", "true", "yes", "on"}


def _normalize_server_url(server_url: str) -> str:
    """规范化推理服务地址：补协议、去尾斜杠、剔除 infer 子路径。"""
    s = (server_url or "").strip()
    if not s:
        return _DEFAULT_SERVER
    if "://" not in s:
        s = f"http://{s}"
    s = s.rstrip("/")
    if s.endswith("/infer/stream"):
        s = s[: -len("/infer/stream")]
    elif s.endswith("/infer/compare-stream"):
        s = s[: -len("/infer/compare-stream")]
    return s


def _candidate_server_urls(server_url: str) -> List[str]:
    """
    生成候选地址，优先原地址。
    额外兼容后端跑在容器内、推理服务跑在宿主机的常见场景：
    localhost/127.0.0.1 -> host.docker.internal
    """
    base = _normalize_server_url(server_url)
    out = [base]
    # 仅在显式开启时，才做 localhost -> host.docker.internal 回退
    if _ENABLE_DOCKER_HOST_FALLBACK:
        try:
            parsed = urlparse(base)
            host = (parsed.hostname or "").lower()
            if host in {"localhost", "127.0.0.1"}:
                alt = base.replace(parsed.netloc, base.split("//", 1)[1].replace(host, "host.docker.internal", 1), 1)
                if alt not in out:
                    out.append(alt)
        except Exception:
            pass
    return out


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
    logger.info("[model-bench] model=%s 开始请求推理服务", model_id)
    async def _consume_stream(resp: httpx.Response) -> str:
        resp.raise_for_status()
        started = False
        token_count = 0
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
                if not started:
                    started = True
                    logger.info("[model-bench] model=%s 收到首个 token（%.2fs）", model_id, time.time() - start)
                    await queue.put({"type": "start", "model": model_id})
                await queue.put({"type": "token", "model": model_id, "text": msg.get("text", "")})
                token_count += 1
            elif t == "done":
                if not started:
                    started = True
                    await queue.put({"type": "start", "model": model_id})
                elapsed_ms = int((time.time() - start) * 1000)
                logger.info("[model-bench] model=%s 完成 elapsed=%dms tokens=%d", model_id, elapsed_ms, token_count)
                await queue.put({"type": "done", "model": model_id, "elapsed_ms": elapsed_ms})
                return "done"
            elif t == "error":
                logger.error("[model-bench] model=%s 推理服务返回错误: %s", model_id, msg.get("text", "unknown error"))
                await queue.put({"type": "error", "model": model_id, "text": msg.get("text", "unknown error")})
                return "error"
            else:
                # 其他类型透传
                await queue.put({**msg, "model": model_id})
        # 流自然结束（未显式给出 done/error）
        return "eof"
    try:
        last_error: Optional[Exception] = None
        end_state = "eof"
        for base_url in _candidate_server_urls(server_url):
            url = base_url + _INFER_PATH
            for attempt in (1, 2):
                try:
                    async with client.stream(
                        "POST",
                        url,
                        json={"question": question, "model": model_id},
                        timeout=_HTTP_TIMEOUT,
                    ) as resp:
                        end_state = await _consume_stream(resp)
                    last_error = None
                    break
                except httpx.HTTPStatusError as e:
                    # 兼容 infer_server.py 的 GET /infer/compare-stream
                    if e.response is not None and e.response.status_code in (404, 405):
                        fallback_url = base_url + _FALLBACK_INFER_PATH
                        params = {"question": question, "models": model_id}
                        async with client.stream("GET", fallback_url, params=params, timeout=_HTTP_TIMEOUT) as resp2:
                            end_state = await _consume_stream(resp2)
                        last_error = None
                        break
                    last_error = e
                except httpx.ConnectError as e:
                    last_error = e
                except httpx.ReadError as e:
                    # 推理服务偶发断流时重试一次
                    last_error = e
                    logger.warning("[model-bench] model=%s 读取流失败，重试 attempt=%d url=%s", model_id, attempt, url)
                    if attempt < 2:
                        continue
                except Exception as e:
                    last_error = e
                # 这里如果没 break，说明本次尝试失败
                if attempt >= 2:
                    break
            if last_error is None:
                break
        if last_error is not None:
            logger.error("[model-bench] model=%s 所有候选地址均失败: %s", model_id, repr(last_error))
            raise last_error
        # 仅在流自然结束且未显式发送 done/error 时补发 done
        if end_state == "eof":
            elapsed_ms = int((time.time() - start) * 1000)
            logger.warning("[model-bench] model=%s 流自然结束（无 done 事件）elapsed=%dms", model_id, elapsed_ms)
            await queue.put({"type": "done", "model": model_id, "elapsed_ms": elapsed_ms})
    except Exception as e:
        extra = ""
        if isinstance(e, httpx.ConnectError):
            extra = (
                "（后端无法连到推理服务；请确认该地址对后端进程可达，"
                "若后端在容器内且你填了 localhost，可改为宿主机 IP）"
            )
        elif isinstance(e, httpx.ReadTimeout):
            extra = "（推理流读取超时；可调大 MODEL_BENCH_TIMEOUT_SECONDS / 降低并发模型数）"
        logger.exception("[model-bench] model=%s 异常: %s", model_id, e)
        await queue.put({"type": "error", "model": model_id, "text": f"{type(e).__name__}: {e}{extra}"})


async def _generate(
    server_url: str,
    model_ids: List[str],
    question: str,
):
    """SSE 生成器：串行启动模型请求（一个完成后再跑下一个）"""
    keepalive_sec = 10.0

    async with httpx.AsyncClient() as client:
        for mid in model_ids:
            queue: asyncio.Queue = asyncio.Queue()
            task = asyncio.create_task(_stream_one_model(client, server_url, mid, question, queue))
            model_finished = False
            while not model_finished:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=keepalive_sec)
                except asyncio.TimeoutError:
                    # 心跳：避免前端/代理因长时间无数据而断开 SSE 连接
                    yield _sse({"type": "keepalive", "ts": int(time.time()), "model": mid})
                    continue

                yield _sse(msg)
                if msg.get("model") == mid and msg.get("type") in ("done", "error"):
                    model_finished = True

            # 等该模型任务真正结束，再进入下一个模型
            await asyncio.gather(task, return_exceptions=True)

    yield _sse({"type": "all_done"})


@router.get("/stream")
async def model_bench_stream(
    question: str = Query(..., description="题目文本"),
    models: str = Query("base,seq2048,seq4096,seq8192", description="逗号分隔模型ID"),
    server_url: str = Query(_DEFAULT_SERVER, description="DSW 推理服务根地址"),
    question_id: Optional[str] = Query(None, description="题目ID（仅用于展示）"),
):
    logger.info(
        "[model-bench] 收到请求 question_len=%d models=%s server_url=%s question_id=%s",
        len((question or "").strip()),
        models,
        server_url,
        question_id or "",
    )
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


async def _self_test() -> None:
    """
    轻量自测：验证 URL 规范化和候选地址逻辑。
    运行：python backend/api/model_bench_api.py --self-test
    """
    assert _normalize_server_url("localhost:8899") == "http://localhost:8899"
    assert _normalize_server_url("http://localhost:8899/infer/stream") == "http://localhost:8899"
    assert _normalize_server_url("https://x.x.x.x:8899/infer/compare-stream") == "https://x.x.x.x:8899"
    cands = _candidate_server_urls("localhost:8899")
    assert cands[0] == "http://localhost:8899"
    assert any("host.docker.internal" in x for x in cands), cands
    print("model_bench_api self-test passed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Model bench api helper")
    parser.add_argument("--self-test", action="store_true", help="run lightweight self test")
    args = parser.parse_args()
    if args.self_test:
        asyncio.run(_self_test())
