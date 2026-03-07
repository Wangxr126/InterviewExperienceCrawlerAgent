#!/usr/bin/env python3
"""调试：检查牛客 feed 页面 HTML 中完整内容的存储位置"""
import requests
import re
import json

url = "https://www.nowcoder.com/feed/main/detail/78d6c8c30f1741e6b0a1a02d7b4bbfab"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0"})
html = r.text

# 提取 __INITIAL_STATE__ = {...}
for pattern in [r'__INITIAL_STATE__\s*=\s*(\{)', r'window\.__PRELOADED_STATE__\s*=\s*(\{)']:
    m = re.search(pattern, html)
    if m:
        start = m.start(1)
        depth, i, in_str, escape = 0, start, None, False
        while i < len(html):
            c = html[i]
            if in_str:
                escape = (c == "\\" and not escape)
                if not escape and c == in_str:
                    in_str = None
                i += 1
                continue
            if c in ('"', "'"):
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        d = json.loads(html[start:i + 1])
                        print("Parsed JSON, keys:", list(d.keys())[:10])
                        def find_content(obj, path=""):
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if "content" in k.lower() and isinstance(v, str) and len(v) > 200:
                                        print(f"\n=== Found at {path}.{k}: len={len(v)} ===")
                                        print(v[:1200])
                                    find_content(v, f"{path}.{k}")
                            elif isinstance(obj, list):
                                for i, v in enumerate(obj[:8]):
                                    find_content(v, f"{path}[{i}]")
                        find_content(d)
                    except Exception as e:
                        print("JSON error:", e)
                    break
            i += 1
        break
else:
    print("No __INITIAL_STATE__ or __PRELOADED_STATE__ found")
