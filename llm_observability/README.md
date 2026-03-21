# LLM 可观测性 / DeepSeek 流式（查阅入口）

本目录集中存放：**直连 API 的探针脚本** + **流式/推理/工具相关的说明文档**。与业务代码解耦，便于单独打开、检索与分享。

---

## 目录结构

```
llm_observability/
├── README.md                 ← 你正在读：总索引
├── docs/
│   └── deepseek-streaming-guide.md   ← 协议行为 + 框架问题 + 适配层 + 测试命令
└── scripts/
    ├── raw_llm_stream.py     ← SSE 原样打印（可选 --merged-footer）
    ├── raw_llm_complete.py   ← 非流式整包 JSON
    └── raw_llm_matrix.py     ← 推理×流式×tools 参数矩阵
```

**仍位于 `backend/` 的实现（非本目录）**：

| 位置 | 说明 |
|------|------|
| `backend/llm/deepseek_thinking_adapter.py` | DeepSeek 流式 + tools，`LLMStreamDelta` |
| `backend/llm/stream_delta.py` | `content` / `reasoning` 通道类型 |
| `backend/agents/react_stream_single_request.py` | 单请求 ReAct 流 |
| `backend/tests/test_react_stream_delta_events.py` | THINKING → LLM_CHUNK 顺序回归 |

**兼容入口**：`python -m backend.scripts.raw_llm_*` 会转发到本目录下同名脚本。

---

## 环境与前缀命令

```bash
conda activate NewCoderAgent
cd <项目根目录>    # 含 .env 的 wxr_agent 根目录
```

---

## 脚本速查

| 目的 | 命令 |
|------|------|
| 看原始 SSE | `python llm_observability/scripts/raw_llm_stream.py "你好" --pretty` |
| 流式结束拼推理+正文（stderr） | 同上加 `--merged-footer` |
| 非流式整包 JSON | `python llm_observability/scripts/raw_llm_complete.py "你好"` |
| 矩阵（先看计划） | `python llm_observability/scripts/raw_llm_matrix.py --dry-run` |
| 矩阵快速 4 组 | `python llm_observability/scripts/raw_llm_matrix.py --quick` |
| 矩阵全 8 组 | `python llm_observability/scripts/raw_llm_matrix.py --max-calls 8` |

配置默认来自 `.env` 的 `INTERVIEWER_*` / `LLM_REMOTE_*`（与线上面经对话一致）；可用 `--base-url`、`--api-key`、`--model` 覆盖。

---

## 文档速查

| 需求 | 打开 |
|------|------|
| 一次性读完：协议、矩阵结论、hello_agents 坑、wxr 适配、回归测试 | [docs/deepseek-streaming-guide.md](./docs/deepseek-streaming-guide.md) |

---

## 回归测试（事件顺序）

```bash
python -m unittest discover -s backend/tests -p "test_*.py" -v
```

---

*维护提示：新增「只探针、不跑业务」的 LLM 脚本时，优先放在 `llm_observability/scripts/`，并在此 README 表格补一行。*
