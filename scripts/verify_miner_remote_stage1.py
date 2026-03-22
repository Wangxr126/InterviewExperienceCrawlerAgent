#!/usr/bin/env python3
"""
验证 two_stage 的 Stage1 远程（MINER_STAGE1_REMOTE_* 或 MINER_REMOTE / 通义 DashScope）参数可成功调用：
- max_tokens 不超过 MINER_REMOTE_MAX_TOKENS（默认钳制 16384）
- extra_body.enable_thinking=false（非流式）

失败时每隔 2 秒重试，最多 30 次（约 1 分钟），成功则退出 0。
用法（在项目根目录、已激活 NewCoderAgent）:
  python scripts/verify_miner_remote_stage1.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=True)

from openai import OpenAI

from backend.config.config import settings


def _call_once(client: OpenAI, *, with_tools: bool) -> None:
    model = (settings.miner_stage1_remote_model or settings.miner_remote_model or "").strip()
    base_extra = dict(settings.miner_remote_stage1_extra_body)
    mt = min(256, settings.miner_stage1_max_tokens)

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复一个字：好"}],
        "max_tokens": mt,
        "temperature": 0.2,
        "extra_body": base_extra,
    }
    if with_tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "测试工具",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        kwargs["tool_choice"] = "none"

    client.chat.completions.create(**kwargs)


def main() -> int:
    key = (settings.miner_stage1_remote_api_key or settings.miner_remote_api_key or "").strip()
    base = (settings.miner_stage1_remote_base_url or settings.miner_remote_base_url or "").strip()
    model = (settings.miner_stage1_remote_model or settings.miner_remote_model or "").strip()
    if not key or not base or not model:
        print("缺少配置：MINER_STAGE1_REMOTE_* 或 MINER_REMOTE_*（API_KEY / BASE_URL / MODEL）")
        return 1

    print(
        f"model={model!r} base={base!r} "
        f"stage1_max_tokens={settings.miner_stage1_max_tokens} "
        f"(MINER_MAX_TOKENS={settings.miner_max_tokens}, cap={settings.miner_remote_max_tokens_cap})"
    )

    client = OpenAI(
        api_key=key,
        base_url=base,
        timeout=float(settings.miner_stage1_remote_timeout or settings.miner_remote_timeout or 90),
    )

    max_attempts = 30
    delay_s = 2.0
    last_err: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            _call_once(client, with_tools=False)
            print(f"[{attempt}/{max_attempts}] 无工具调用：成功")
            _call_once(client, with_tools=True)
            print(f"[{attempt}/{max_attempts}] Function Calling（tool_choice=none）：成功")
            print("全部通过。")
            return 0
        except Exception as e:
            last_err = e
            print(f"[{attempt}/{max_attempts}] 失败: {e}")
            if attempt < max_attempts:
                time.sleep(delay_s)

    print("已达最大重试次数，最后一次错误:", last_err)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
