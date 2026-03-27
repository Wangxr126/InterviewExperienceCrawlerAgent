#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
串行验证 4 个模型推理，并打印 GPU 使用证据。

用法：
  conda activate NewCoderAgent
  python test_infer_seq4_gpu.py
"""

import json
import time
from typing import Dict, Any

import requests
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt


INFER_SERVER = "http://127.0.0.1:8899"
INFER_URL = f"{INFER_SERVER}/infer/stream"
HEALTH_URL = f"{INFER_SERVER}/health"
MODELS = ["base", "seq2048", "seq4096", "seq8192"]

CASE_TEXT = """【帖子标题】 推荐一个AI Agent项目⭐ 【帖子URL】 https://www.nowcoder.com/feed/main/detail/9cfe74515ec04692b1e83abe0313d6f1 【帖子正文】 非常适合准备入门Agent开发或者是毕业生拿来做毕设的同学！！！ 链接为： https://github.com/Shy2593666979/AgentChat 包含的技术栈：LangChain + LangGraph + RAG + Agent + MCP + Memory + Python + FastAPI + Agent Skills Agent下又有ReAct-Agent、CodeAct-Agent、Plan-and-Execute-Agent 的三种范式的示例 目前项目的Star数量已有400+⭐ 并且现在支持本地部署和docker 部署，如果碰到部署的问题欢迎来找作者问，欢迎提交PR作为贡献者来优化项目，或者提Issue来让作者在后续的版本进行优化，欢迎大家积极反馈，遇到解决不了的部署问题作者也能免费进行远程操控来解决BUG！ 如果你认为项目可以的话，给项目点个Star⭐来激励一下作者 我们相信开源的价值！】"""
MINER_SYSTEM_PROMPT = get_miner_prompt()
MINER_USER_PROMPT = format_miner_user_prompt(content=CASE_TEXT, has_image=False, company="", position="")


def get_health() -> Dict[str, Any]:
    try:
        resp = requests.get(HEALTH_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": f"health 请求失败: {type(e).__name__}: {e}"}


def run_one_model(model_id: str) -> Dict[str, Any]:
    payload = {
        # 关键：按前端/后端完整链路，显式传 system_prompt + prompt
        "system_prompt": MINER_SYSTEM_PROMPT,
        "prompt": MINER_USER_PROMPT,
        "model_id": model_id,
        "max_new_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.9,
    }
    t0 = time.time()
    first_token_s = None
    token_count = 0
    output = ""
    done_msg: Dict[str, Any] = {}
    error_msg = ""

    try:
        with requests.post(INFER_URL, json=payload, stream=True, timeout=900) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                msg = json.loads(line[6:])
                tp = msg.get("type")
                if tp == "token":
                    if first_token_s is None:
                        first_token_s = time.time() - t0
                    tok = msg.get("text", "")
                    output += tok
                    token_count += 1
                elif tp == "error":
                    error_msg = msg.get("text", "unknown error")
                    break
                elif tp == "done":
                    done_msg = msg
                    break
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"

    elapsed_s = time.time() - t0
    return {
        "model": model_id,
        "elapsed_s": elapsed_s,
        "first_token_s": first_token_s,
        "token_count": token_count,
        "done": done_msg,
        "error": error_msg,
        "output": output,
    }


def print_gpu(gpu: Dict[str, Any], prefix: str = "") -> None:
    if not gpu:
        print(f"{prefix}GPU 信息: <空>")
        return
    print(
        f"{prefix}GPU: cuda={gpu.get('cuda_available')} "
        f"device={gpu.get('device_name')} "
        f"alloc={gpu.get('memory_allocated_mb')}MB "
        f"reserved={gpu.get('memory_reserved_mb')}MB"
    )


def main() -> None:
    print("=" * 90)
    print("串行推理验证开始（4模型）")
    print(f"Infer URL: {INFER_URL}")
    print("=" * 90)

    h = get_health()
    print("\n[启动前 health]")
    print(json.dumps(h, ensure_ascii=False, indent=2)[:1200])

    all_results = []
    for idx, model_id in enumerate(MODELS, start=1):
        print("\n" + "-" * 90)
        print(f"[{idx}/{len(MODELS)}] 模型 {model_id} 开始")
        r = run_one_model(model_id)
        all_results.append(r)

        if r["error"]:
            print(f"状态: ERROR -> {r['error']}")
        else:
            print("状态: DONE")

        print(f"耗时: {r['elapsed_s']:.2f}s")
        print(f"首 token: {r['first_token_s']:.2f}s" if r["first_token_s"] is not None else "首 token: <无>")
        print(f"token 数: {r['token_count']}")

        done = r.get("done") or {}
        if done:
            print(
                "done字段: "
                f"elapsed_ms={done.get('elapsed_ms')} "
                f"first_token_ms={done.get('first_token_ms')} "
                f"token_count={done.get('token_count')}"
            )
            print_gpu(done.get("gpu") or {}, prefix="done返回 ")

        preview = (r.get("output") or "").replace("\n", " ")
        print(f"答案预览: {preview[:220]}")

    h2 = get_health()
    print("\n[结束后 health]")
    print(json.dumps(h2, ensure_ascii=False, indent=2)[:1200])

    print("\n" + "=" * 90)
    print("汇总")
    for r in all_results:
        print(
            f"- {r['model']}: elapsed={r['elapsed_s']:.2f}s, "
            f"first_token={('%.2fs' % r['first_token_s']) if r['first_token_s'] is not None else 'N/A'}, "
            f"tokens={r['token_count']}, error={r['error'] or 'None'}"
        )
    print("=" * 90)


if __name__ == "__main__":
    main()
