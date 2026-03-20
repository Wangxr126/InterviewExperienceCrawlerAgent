"""
火山引擎 Stage2 客户端：支持单条与批量推理

- 单条：POST /api/v3/chat/completions（默认，无额外费用）
- 批量：POST /api/v3/batch/chat/completions（批量推理有额外收费）

参考：https://www.volcengine.com/docs/82379/1528783
"""
import json
import logging
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


def _build_messages(system_prompt: str, user_content: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def call_single(
    *,
    model: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    user_content: str,
    temperature: float = 0.3,
    max_tokens: int = 65536,
    timeout: int = 300,
) -> str:
    """
    单条请求：POST /api/v3/chat/completions
    """
    url = base_url.rstrip("/")
    if "/chat/completions" not in url:
        url = f"{url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_content),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        # 400/422 时，火山通常会在响应体里返回更具体原因（参数/模型名/限额等）。
        # 目前 stage2_processor 只打印 str(e)，所以这里把 resp.text 拼进异常消息里方便定位。
        body = (resp.text or "").strip()
        raise RuntimeError(
            f"Volcengine chat/completions failed: status={resp.status_code}, body={body[:1200]}"
        )
    data = resp.json()
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


def call_batch(
    *,
    model: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    user_contents: List[str],
    temperature: float = 0.3,
    max_tokens: int = 65536,
    timeout: int = 600,
) -> List[str]:
    """
    批量请求：POST /api/v3/batch/chat/completions

    火山批量 API 格式（根据官方文档）：
    - 单条：与 chat/completions 相同
    - 批量：requests 数组，每项为 {model, messages, ...}
    """
    if not user_contents:
        return []
    url = base_url.rstrip("/")
    if "/batch/chat/completions" in url:
        pass
    elif "/chat/completions" in url:
        url = url.replace("/chat/completions", "/batch/chat/completions")
    else:
        url = f"{url}/batch/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    requests_list = [
        {
            "model": model,
            "messages": _build_messages(system_prompt, uc),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        for uc in user_contents
    ]
    payload = {"requests": requests_list}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        raise RuntimeError(
            f"Volcengine batch chat/completions failed: status={resp.status_code}, body={body[:1200]}"
        )
    data = resp.json()
    # 批量返回格式：data 或 data.responses 或 data.choices
    responses = data.get("responses") or data.get("data") or data.get("choices") or []
    results = []
    for r in responses:
        if isinstance(r, dict):
            content = (
                r.get("choices", [{}])[0].get("message", {}).get("content", "")
                or r.get("message", {}).get("content", "")
                or r.get("content", "")
            )
        else:
            content = ""
        results.append(content or "")
    return results
