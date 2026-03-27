"""
直连 OpenAI 兼容 Chat Completions，stream=false，一次性返回完整 JSON（无适配层、无 Agent）。

与 raw_llm_stream.py 对照使用：看非流式里 message 是否带 reasoning_content、usage 等。

运行（项目根目录）：
  conda activate NewCoderAgent
  python llm_observability/scripts/raw_llm_complete.py "用一句话介绍你自己"

兼容：python -m backend.scripts.raw_llm_complete

说明文档：llm_observability/docs/deepseek-streaming-guide.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from backend.config.config import settings


def _default_endpoint() -> tuple[str, str, str]:
    api_key = (settings.interviewer_api_key or settings.llm_api_key or "").strip()
    base = (settings.interviewer_base_url or settings.llm_base_url or "").strip().rstrip("/")
    model = (settings.interviewer_model or settings.llm_model_id or "").strip()
    return base, api_key, model


def main() -> int:
    p = argparse.ArgumentParser(description="非流式完整响应 JSON（无适配层）")
    p.add_argument("message", nargs="?", default="用一句话介绍你自己", help="user 消息内容")
    p.add_argument("--model", default="", help="覆盖 model")
    p.add_argument("--base-url", default="", help="须含 /v1")
    p.add_argument("--api-key", default="", help="覆盖 API Key")
    p.add_argument(
        "--timeout",
        type=int,
        default=max(settings.interviewer_timeout, settings.llm_remote_timeout, 120),
        help="秒",
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help="单行 JSON（默认缩进打印）",
    )
    args = p.parse_args()

    d_base, d_key, d_model = _default_endpoint()
    base = (args.base_url or d_base).strip().rstrip("/")
    api_key = (args.api_key or d_key).strip()
    model = (args.model or d_model).strip()

    if not base or not api_key or not model:
        print(
            "缺少 base-url / api-key / model。请配置 .env 或使用命令行参数。",
            file=sys.stderr,
        )
        return 1

    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": args.message}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"# POST {url} stream=false", file=sys.stderr)
    print(f"# model={model!r}\n", file=sys.stderr)

    try:
        with httpx.Client(timeout=args.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                print(f"HTTP {resp.status_code}\n{resp.text}", file=sys.stderr)
                return 1
            data = resp.json()
    except httpx.HTTPError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1

    if args.compact:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
