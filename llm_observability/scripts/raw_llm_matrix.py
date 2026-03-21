"""
DeepSeek（OpenAI 兼容）参数矩阵：推理模型 vs 普通模型 × 流式 vs 非流式 × 是否携带 tools。

不做 hello_agents / 适配层；直接 httpx 调 /chat/completions，汇总每档行为差异（推理片段、正文、tool_calls、usage）。

运行（项目根目录）：
  conda activate NewCoderAgent
  python llm_observability/scripts/raw_llm_matrix.py --dry-run
  python llm_observability/scripts/raw_llm_matrix.py --max-calls 8
  python llm_observability/scripts/raw_llm_matrix.py --quick

兼容：python -m backend.scripts.raw_llm_matrix

工具说明：内置 2 个 function 定义（get_weather / list_supported_cities），用户话术强引导调用 get_weather；
无 tools 组合使用另一句短提示，避免模型空转找工具。

说明文档：llm_observability/docs/deepseek-streaming-guide.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from backend.config.config import settings

# OpenAI 兼容 tools（与线上面经 Agent 一致 type=function + function.name/parameters）
DEMO_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市当前天气概况（气温、阴晴、风力）",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市中文名，如 北京、上海",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_supported_cities",
            "description": "列出天气查询支持的城市 ID 列表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

USER_TOOLS = (
    "【必须】先调用工具 get_weather，参数 city 填「深圳」。"
    "不要编造天气数据；工具返回后，用一句话中文总结给用户。"
)
USER_NO_TOOLS = "用不超过20个汉字自我介绍，不要调用任何函数或工具。"


def _default_endpoint() -> tuple[str, str, str]:
    api_key = (settings.interviewer_api_key or settings.llm_api_key or "").strip()
    base = (settings.interviewer_base_url or settings.llm_base_url or "").strip().rstrip("/")
    model = (settings.interviewer_model or settings.llm_model_id or "").strip()
    return base, api_key, model


def _merge_stream_tool_deltas(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把流式 delta.tool_calls 按 index 合并成类似非流式 message.tool_calls 的结构。"""
    by_idx: dict[int, dict[str, Any]] = {}
    for obj in chunks:
        for ch in obj.get("choices") or []:
            delta = (ch or {}).get("delta") or {}
            for tc in delta.get("tool_calls") or []:
                idx = int(tc.get("index", 0))
                slot = by_idx.setdefault(
                    idx,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
    return [by_idx[i] for i in sorted(by_idx.keys())]


@dataclass
class RunResult:
    name: str
    model: str
    stream: bool
    use_tools: bool
    ok: bool
    http_status: int = 0
    elapsed_ms: float = 0
    error: str = ""
    reasoning_chars: int = 0
    content_chars: int = 0
    tool_names: list[str] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, Any] | None = None
    preview: str = ""


def _run_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> tuple[bool, int, str, list[dict], int, int, list[str], str, dict | None, str]:
    chunks: list[dict[str, Any]] = []
    reasoning_acc: list[str] = []
    content_acc: list[str] = []
    err = ""
    status = 0
    finish = ""
    usage = None
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                status = resp.status_code
                if status != 200:
                    return False, status, resp.read().decode("utf-8", errors="replace"), [], 0, 0, [], "", None, ""
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break
                    raw = line[6:].strip()
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    chunks.append(obj)
                    for ch in obj.get("choices") or []:
                        delta = (ch or {}).get("delta") or {}
                        r = delta.get("reasoning_content")
                        c = delta.get("content")
                        if isinstance(r, str) and r:
                            reasoning_acc.append(r)
                        if isinstance(c, str) and c:
                            content_acc.append(c)
                        fr = ch.get("finish_reason")
                        if fr:
                            finish = fr
                    if obj.get("usage"):
                        usage = obj["usage"]
    except Exception as e:
        err = str(e)
        return False, status or 0, err, chunks, len("".join(reasoning_acc)), len("".join(content_acc)), [], finish, usage, ""

    merged = _merge_stream_tool_deltas(chunks)
    names = [m.get("function", {}).get("name") or "?" for m in merged]
    text = "".join(content_acc)
    preview = (text[:120] + "…") if len(text) > 120 else text
    return True, status, err, chunks, len("".join(reasoning_acc)), len(text), names, finish, usage, preview


def _run_complete(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> tuple[bool, int, str, int, int, list[str], str, dict | None, str]:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                return False, resp.status_code, resp.text, 0, 0, [], "", None, ""
            data = resp.json()
    except Exception as e:
        return False, 0, str(e), 0, 0, [], "", None, ""

    ch0 = (data.get("choices") or [{}])[0]
    msg = ch0.get("message") or {}
    rc = msg.get("reasoning_content") or ""
    if not isinstance(rc, str):
        rc = str(rc) if rc is not None else ""
    content = msg.get("content") or ""
    if not isinstance(content, str):
        content = str(content) if content is not None else ""
    tcs = msg.get("tool_calls") or []
    names = []
    for tc in tcs:
        fn = (tc or {}).get("function") or {}
        names.append(fn.get("name") or "?")
    finish = ch0.get("finish_reason") or ""
    usage = data.get("usage")
    preview = (content[:120] + "…") if len(content) > 120 else content
    return True, resp.status_code, "", len(rc), len(content), names, finish, usage, preview


def _build_matrix(
    reasoner_model: str,
    chat_model: str,
    quick: bool,
) -> list[tuple[str, str, bool, bool]]:
    """
    返回 (name, model, stream, use_tools)
    """
    rows: list[tuple[str, str, bool, bool]] = []

    def add(tag: str, m: str, stream: bool, tools: bool) -> None:
        rows.append((tag, m, stream, tools))

    if quick:
        add("R+stream+tools", reasoner_model, True, True)
        add("R+nostream+tools", reasoner_model, False, True)
        add("C+stream+notools", chat_model, True, False)
        add("C+nostream+notools", chat_model, False, False)
        return rows

    for m, prefix in ((reasoner_model, "R"), (chat_model, "C")):
        for stream in (True, False):
            for tools in (True, False):
                add(f"{prefix}+{'stream' if stream else 'nostream'}+{'tools' if tools else 'notools'}", m, stream, tools)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="DeepSeek 参数矩阵（推理/流式/tools）")
    p.add_argument("--base-url", default="", help="覆盖 base，须含 /v1")
    p.add_argument("--api-key", default="", help="覆盖 API Key")
    p.add_argument("--reasoner-model", default="deepseek-reasoner", help="推理模型名")
    p.add_argument("--chat-model", default="deepseek-chat", help="非推理模型名")
    p.add_argument(
        "--timeout",
        type=int,
        default=max(settings.interviewer_timeout, settings.llm_remote_timeout, 180),
    )
    p.add_argument("--dry-run", action="store_true", help="只列出组合，不请求")
    p.add_argument("--quick", action="store_true", help="只跑 4 组抽样")
    p.add_argument("--max-calls", type=int, default=8, help="最多执行请求数（截断矩阵）")
    p.add_argument("--verbose", action="store_true", help="打印每档 JSON 摘要到 stderr")
    args = p.parse_args()

    d_base, d_key, _ = _default_endpoint()
    base = (args.base_url or d_base).strip().rstrip("/")
    api_key = (args.api_key or d_key).strip()

    if not base or not api_key:
        print("缺少 base-url 或 api-key（.env INTERVIEWER_* / LLM_REMOTE_*）", file=sys.stderr)
        return 1

    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    matrix = _build_matrix(args.reasoner_model, args.chat_model, args.quick)
    matrix = matrix[: max(0, args.max_calls)]

    print("# 计划执行的参数组合（模型 / stream / tools）", file=sys.stderr)
    for name, m, st, ut in matrix:
        print(f"  - {name}: model={m!r} stream={st} tools={ut}", file=sys.stderr)
    if args.dry_run:
        return 0

    results: list[RunResult] = []
    for name, model, stream, use_tools in matrix:
        user_msg = USER_TOOLS if use_tools else USER_NO_TOOLS
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": user_msg}],
            "stream": stream,
        }
        if use_tools:
            payload["tools"] = DEMO_TOOLS
            payload["tool_choice"] = "auto"

        t0 = time.perf_counter()
        if stream:
            ok, status, err, _, rlen, clen, tools, finish, usage, preview = _run_stream(
                url, headers, payload, args.timeout
            )
            error = "" if ok else (err or f"HTTP {status}")
        else:
            ok, status, err, rlen, clen, tools, finish, usage, preview = _run_complete(
                url, headers, payload, args.timeout
            )
            error = "" if ok else err
        elapsed = (time.perf_counter() - t0) * 1000

        rr = RunResult(
            name=name,
            model=model,
            stream=stream,
            use_tools=use_tools,
            ok=ok,
            http_status=status,
            elapsed_ms=elapsed,
            error=error[:500] if error else "",
            reasoning_chars=rlen,
            content_chars=clen,
            tool_names=tools,
            finish_reason=finish or "",
            usage=usage,
            preview=preview.replace("\n", "\\n"),
        )
        results.append(rr)
        if args.verbose:
            print(json.dumps(rr.__dict__, ensure_ascii=False, indent=2), file=sys.stderr)

    # 终端表格（Markdown）
    print("\n## 结果汇总\n")
    print("| 组合 | OK | http | ms | 推理字数 | 正文字数 | tool_calls | finish | usage.reasoning_tokens |")
    print("|------|-----|------|-----|---------|---------|------------|--------|------------------------|")
    for r in results:
        rtok = ""
        if r.usage and isinstance(r.usage, dict):
            det = r.usage.get("completion_tokens_details") or {}
            if isinstance(det, dict) and det.get("reasoning_tokens") is not None:
                rtok = str(det.get("reasoning_tokens"))
        tc = ",".join(r.tool_names) if r.tool_names else "—"
        print(
            f"| {r.name} | {r.ok} | {r.http_status} | {r.elapsed_ms:.0f} | "
            f"{r.reasoning_chars} | {r.content_chars} | {tc} | {r.finish_reason or '—'} | {rtok or '—'} |"
        )
        if not r.ok and r.error:
            print(f"| ↳ error: {r.error[:200]} | | | | | | | | |")

    print("\n## 结论提示（结合本表与 DeepSeek 文档自行核对）\n")
    print(
        "- **是否要推理**：`deepseek-reasoner` 行里「推理字数」或 `usage.completion_tokens_details.reasoning_tokens` "
        "非空/大于 0 即发生了思维链；`deepseek-chat` 通常无独立 reasoning 通道。\n"
        "- **流式 vs 非流式**：流式在 delta 里分段吐 `reasoning_content` 再吐 `content`；非流式在 `message` 里一次性给齐。\n"
        "- **带 tools**：流式下 `delta.tool_calls` 按 index 拼接；非流式在 `message.tool_calls`。若 finish=tool_calls 或 "
        "tool_names 非空，说明模型选择了函数调用。\n"
        "- **首轮 tool_calls**：`content` 常为空；本地执行工具后把 `role=tool` 写回 `messages` 再请求，模型才会继续出最终自然语言。\n"
    )

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
