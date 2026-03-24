# -*- coding: utf-8 -*-
"""
在 DSW 上对已启动的 infer_server（默认 8899）批量跑四模型，导出 JSON。

用法（DSW，infer_server 已就绪）:
  cd /mnt/workspace/TEMP-FILE-STATION
  pip install requests   # 若无
  python /path/to/export_infer_compare_results.py \\
    --bench lora_bench_pack/bench_cases.json \\
    --out lora_bench_pack/compare_results_10.json \\
    --base-url http://127.0.0.1:8899 \\
    --limit 10
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("请先安装: pip install requests", file=sys.stderr)
    sys.exit(1)


def run_one_stream(base_url: str, question: str, model: str, timeout: int) -> dict:
    url = f"{base_url.rstrip('/')}/infer/stream"
    payload = {"question": question, "model": model}
    text_parts: list[str] = []
    err = ""
    elapsed_ms = None

    with requests.post(url, json=payload, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = msg.get("type")
            if t == "token":
                text_parts.append(msg.get("text") or "")
            elif t == "error":
                err = msg.get("text") or "error"
            elif t == "done":
                elapsed_ms = msg.get("elapsed_ms")
                break

    return {
        "text": "".join(text_parts),
        "error": err,
        "elapsed_ms": elapsed_ms,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="lora_bench_pack/bench_cases.json")
    ap.add_argument("--out", default="lora_bench_pack/compare_results.json")
    ap.add_argument("--base-url", default="http://127.0.0.1:8899")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument(
        "--models",
        default="base,seq2048,seq4096,seq8192",
        help="逗号分隔",
    )
    ap.add_argument("--timeout", type=int, default=1800, help="单模型请求超时秒数")
    args = ap.parse_args()

    bench_path = Path(args.bench)
    out_path = Path(args.out)
    if not bench_path.is_file():
        print(f"找不到题库文件: {bench_path.resolve()}", file=sys.stderr)
        return 1

    data = json.loads(bench_path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])[: max(0, args.limit)]
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    out_path.parent.mkdir(parents=True, exist_ok=True)

    items = []
    for i, c in enumerate(cases, 1):
        q = (c.get("question_text") or "").strip()
        qid = c.get("q_id", "")
        print(f"[{i}/{len(cases)}] q_id={qid} len={len(q)}", flush=True)
        row = {
            "idx": i,
            "q_id": qid,
            "category": c.get("category"),
            "question_text": q,
            "doubao_answer": c.get("answer_text") or "",
            "post_raw_content": c.get("post_raw_content") or "",
            "models": {},
        }
        for m in models:
            print(f"  -> model={m} ...", flush=True)
            try:
                row["models"][m] = run_one_stream(args.base_url, q, m, args.timeout)
            except Exception as e:
                row["models"][m] = {"text": "", "error": f"{type(e).__name__}: {e}", "elapsed_ms": None}
        items.append(row)

        # 每题写完就落盘，避免最后一题崩了全丢
        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "service": args.base_url,
            "models": models,
            "count_done": len(items),
            "count_total": len(cases),
            "items": items,
        }
        out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  saved partial -> {out_path}", flush=True)

    final = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": args.base_url,
        "models": models,
        "count": len(items),
        "items": items,
    }
    out_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: {out_path.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
