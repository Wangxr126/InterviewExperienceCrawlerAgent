# 临时测试：解析 trace 中的 JSON
import json

# 从 trace 中复制的 LLM 输出（第一个对象）
s = '''[
  {
    "question_text": "有实习经历吗？",
    "answer_text": "无",
    "company": "字节跳动",
    "job": "后端开发",
    "difficulty": "低",
    "type": "基础",
    "tags": ["实习"]
  }
]'''

try:
    j = json.loads(s)
    print("OK, parsed", len(j), "items")
except json.JSONDecodeError as e:
    print("Error:", e)
    print("At position:", e.pos, "line", e.lineno, "col", e.colno)
    if e.pos and e.pos < len(s):
        start = max(0, e.pos - 20)
        end = min(len(s), e.pos + 20)
        print("Context:", repr(s[start:end]))
