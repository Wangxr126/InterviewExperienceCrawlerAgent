#!/usr/bin/env python3
"""
验证 Stage1 与 Worker 一致的 max_tokens 能否通过 MINER_STAGE1_REMOTE / MINER_REMOTE OpenAI 兼容网关（避免 400 InvalidParameter）。

用法（项目根）:
  conda run -n NewCoderAgent python backend/scripts/smoke_miner_stage1_max_tokens.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env", override=True)


def main() -> int:
    from backend.config.config import settings

    mt = settings.miner_stage1_max_tokens
    api_cap = settings.miner_stage1_api_max_tokens
    print(f"miner_stage1_max_tokens={mt} (api_cap={api_cap}, remote_cap={settings.miner_remote_max_tokens_cap})")
    if not (1 <= mt <= api_cap):
        print(f"FAIL: max_tokens 应在 [1, {api_cap}] 内，当前 {mt}")
        return 1

    base = (settings.miner_stage1_remote_base_url or settings.miner_remote_base_url or "").strip().rstrip("/")
    key = (settings.miner_stage1_remote_api_key or settings.miner_remote_api_key or "").strip()
    model = (settings.miner_stage1_remote_model or settings.miner_remote_model or "").strip()
    if not (base and key and model):
        print("SKIP: 未完整配置 MINER_STAGE1_REMOTE_* 或 MINER_REMOTE_*")
        return 0

    try:
        from openai import OpenAI
    except ImportError:
        print("SKIP: 未安装 openai")
        return 0

    client = OpenAI(
        api_key=key,
        base_url=base,
        timeout=float(settings.miner_stage1_remote_timeout or settings.miner_remote_timeout or 90),
    )
    extra = dict(settings.miner_remote_stage1_extra_body)
    req: dict = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复一个字：好"}],
        "max_tokens": mt,
    }
    if extra:
        req["extra_body"] = extra

    resp = client.chat.completions.create(**req)
    text = (resp.choices[0].message.content or "").strip()
    print("OK:", text[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
