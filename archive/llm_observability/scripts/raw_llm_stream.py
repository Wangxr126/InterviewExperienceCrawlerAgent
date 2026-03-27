"""
直连 OpenAI 兼容 Chat Completions 的流式接口，原样打印 SSE 行（不做适配、不走 Agent）。

用于观察 DeepSeek（或其它兼容端）在 stream=true 时返回的原始 data: JSON 片段，
包括 reasoning_content、delta.tool_calls 等。

运行（项目根目录）：
  conda activate NewCoderAgent
  python llm_observability/scripts/raw_llm_stream.py "用一句话介绍你自己"

兼容：python -m backend.scripts.raw_llm_stream （转发至本文件）

默认读取 .env 里当前 Interviewer 的 base_url / api_key / model；
也可用参数覆盖。

  python llm_observability/scripts/raw_llm_stream.py "hello" --model deepseek-chat \\
      --base-url https://api.deepseek.com/v1 --api-key sk-...

非流式对照：python llm_observability/scripts/raw_llm_complete.py "同上"
拼接推理/正文（stderr）：加 --merged-footer
参数矩阵：python llm_observability/scripts/raw_llm_matrix.py --quick

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
    p = argparse.ArgumentParser(description="原始 SSE 流式打印（无适配层、无 Agent）")
    p.add_argument("message", nargs="?", default="用一句话介绍你自己", help="user 消息内容")
    p.add_argument("--model", default="", help="覆盖 model，默认 .env Interviewer/LLM")
    p.add_argument("--base-url", default="", help="覆盖 base URL，须含 /v1，如 https://api.deepseek.com/v1")
    p.add_argument("--api-key", default="", help="覆盖 API Key")
    p.add_argument(
        "--timeout",
        type=int,
        default=max(settings.interviewer_timeout, settings.llm_remote_timeout, 120),
        help="秒",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="对 data: 后的 JSON 做缩进打印（仍是一条流一块一块的）",
    )
    p.add_argument(
        "--merged-footer",
        action="store_true",
        help="流结束后在 stderr 打印拼接后的 reasoning_content 与 content（对照「要不要过程」）",
    )
    args = p.parse_args()

    d_base, d_key, d_model = _default_endpoint()
    base = (args.base_url or d_base).strip().rstrip("/")
    api_key = (args.api_key or d_key).strip()
    model = (args.model or d_model).strip()

    if not base or not api_key or not model:
        print(
            "缺少 base-url / api-key / model。请配置 .env（INTERVIEWER_* 或 LLM_REMOTE_*）或使用命令行参数。",
            file=sys.stderr,
        )
        return 1

    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": args.message}],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"# POST {url}", file=sys.stderr)
    print(f"# model={model!r} stream=true（原始 SSE，非框架 step）\n", file=sys.stderr)

    reasoning_acc: list[str] = []
    content_acc: list[str] = []

    def _accumulate_from_line(line: str) -> None:
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            return
        raw = line[6:].strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return
        choices = obj.get("choices") or []
        if not choices:
            return
        delta = (choices[0] or {}).get("delta") or {}
        r = delta.get("reasoning_content")
        c = delta.get("content")
        if isinstance(r, str) and r:
            reasoning_acc.append(r)
        if isinstance(c, str) and c:
            content_acc.append(c)

    try:
        with httpx.Client(timeout=args.timeout) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")
                    print(f"HTTP {resp.status_code}\n{body}", file=sys.stderr)
                    return 1

                for line in resp.iter_lines():
                    if line is None:
                        continue
                    line = line.strip("\r\n")
                    if not line:
                        continue
                    if args.merged_footer:
                        _accumulate_from_line(line)
                    if args.pretty and line.startswith("data: ") and line != "data: [DONE]":
                        raw = line[6:].strip()
                        try:
                            obj = json.loads(raw)
                            print("data: " + json.dumps(obj, ensure_ascii=False, indent=2))
                        except json.JSONDecodeError:
                            print(line)
                    else:
                        print(line)
    except httpx.HTTPError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1

    if args.merged_footer:
        print("\n# ----- merged reasoning_content (stderr) -----", file=sys.stderr)
        print("".join(reasoning_acc), file=sys.stderr)
        print("# ----- merged content (stderr) -----", file=sys.stderr)
        print("".join(content_acc), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
