#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接测试 Miner 推理耗时和输出
用你那条帖子 + Miner Prompt 调推理服务
"""
import time
import requests
import json
from backend.agents.prompts.miner_prompt import MINER_REACT_SYSTEM_PROMPT, MINER_USER_PROMPT_TEMPLATE, format_miner_user_prompt

# 你提供的 nowcoder 案例（按前端传参格式拼接）
POST_CONTENT = """【帖子标题】 推荐一个AI Agent项目⭐ 【帖子URL】 https://www.nowcoder.com/feed/main/detail/9cfe74515ec04692b1e83abe0313d6f1 【帖子正文】 非常适合准备入门Agent开发或者是毕业生拿来做毕设的同学！！！ 链接为： https://github.com/Shy2593666979/AgentChat 包含的技术栈：LangChain + LangGraph + RAG + Agent + MCP + Memory + Python + FastAPI + Agent Skills Agent下又有ReAct-Agent、CodeAct-Agent、Plan-and-Execute-Agent 的三种范式的示例 目前项目的Star数量已有400+⭐ 并且现在支持本地部署和docker 部署，如果碰到部署的问题欢迎来找作者问，欢迎提交PR作为贡献者来优化项目，或者提Issue来让作者在后续的版本进行优化，欢迎大家积极反馈，遇到解决不了的部署问题作者也能免费进行远程操控来解决BUG！ 如果你认为项目可以的话，给项目点个Star⭐来激励一下作者 我们相信开源的价值！】"""

# 构造 Miner Prompt
system_prompt = MINER_REACT_SYSTEM_PROMPT
user_prompt = format_miner_user_prompt(POST_CONTENT, has_image=False)

print("=" * 80)
print("【测试配置】")
print(f"System Prompt 长度: {len(system_prompt)} chars")
print(f"User Prompt 长度: {len(user_prompt)} chars")
print(f"User Prompt 前200字: {user_prompt[:200].replace(chr(10), ' ')}")
print("=" * 80)
print()

# 调推理服务
infer_url = "http://127.0.0.1:8899/infer/stream"
payload = {
    "prompt": user_prompt,
    "system_prompt": system_prompt,
    "model_id": "base",
    "max_new_tokens": 2048,
    "temperature": 0.7,
    "top_p": 0.9,
}

print(f"【开始推理】 {time.strftime('%H:%M:%S')}")
print(f"URL: {infer_url}")
print(f"Model: {payload['model_id']}")
print(f"Max tokens: {payload['max_new_tokens']}")
print()

start_time = time.time()
full_output = ""
token_count = 0

try:
    with requests.post(infer_url, json=payload, stream=True, timeout=900) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                if line_str.startswith("data: "):
                    try:
                        data = json.loads(line_str[6:])
                        if data.get("type") == "token":
                            # 兼容两种字段：text（当前后端）/token（历史版本）
                            token = data.get("text", data.get("token", ""))
                            full_output += token
                            token_count += 1
                            if token_count % 50 == 0:
                                print(f"  [{token_count} tokens] {time.time() - start_time:.1f}s")
                        elif data.get("type") == "done":
                            print(f"  [完成] elapsed_ms={data.get('elapsed_ms')} first_token_ms={data.get('first_token_ms')} token_count={data.get('token_count')}")
                            gpu = data.get("gpu") or {}
                            if gpu:
                                print(f"  [GPU] cuda={gpu.get('cuda_available')} device={gpu.get('device_name')} alloc={gpu.get('memory_allocated_mb')}MB reserved={gpu.get('memory_reserved_mb')}MB")
                    except json.JSONDecodeError:
                        pass

except Exception as e:
    print(f"【错误】{type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

elapsed = time.time() - start_time

print()
print("=" * 80)
print(f"【结果统计】")
print(f"总耗时: {elapsed:.2f}s")
print(f"Token 数: {token_count}")
if elapsed > 0:
    print(f"吞吐: {token_count / elapsed:.2f} tokens/s")
print(f"输出长度: {len(full_output)} chars")
print("=" * 80)
print()
print("【完整输出】")
print(full_output[:500] if len(full_output) > 500 else full_output)
if len(full_output) > 500:
    print(f"... (还有 {len(full_output) - 500} 字符)")
