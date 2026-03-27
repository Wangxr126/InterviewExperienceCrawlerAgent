# DeepSeek 流式与参数矩阵 · 完整查阅手册

> **位置**：`llm_observability/docs/deepseek-streaming-guide.md`  
> **总入口**：[../README.md](../README.md)

---

## 目录（按需跳转）

1. [探针脚本与命令](#一探针脚本与命令)
2. [全矩阵实测结果（8 档）](#二全矩阵实测结果8-档)
3. [DeepSeek 输出特点](#三deepseek-输出特点)
4. [参数选择建议](#四参数选择建议)
5. [与项目适配层的关系](#五与项目适配层的关系)
6. [hello_agents ReAct 与 wxr 适配层](#六hello_agents-react-与-wxr-适配层)
7. [回归测试](#七回归测试)

---

## 一、探针脚本与命令

脚本位于 **`llm_observability/scripts/`**（也可用 `python -m backend.scripts.xxx` 兼容转发）。

| 脚本 | 作用 |
|------|------|
| `raw_llm_stream.py` | 流式 `stream=true`，逐行打印 SSE `data:`，可选 `--merged-footer` 在 stderr 拼接推理/正文 |
| `raw_llm_complete.py` | 非流式 `stream=false`，一次性打印完整 JSON |
| `raw_llm_matrix.py` | 参数矩阵：2 模型 × 2 stream × 2 tools，汇总表格 |

```bash
conda activate NewCoderAgent
cd <项目根目录>

python llm_observability/scripts/raw_llm_stream.py "1+1等于几" --merged-footer
python llm_observability/scripts/raw_llm_complete.py "1+1等于几"
python llm_observability/scripts/raw_llm_matrix.py --quick
python llm_observability/scripts/raw_llm_matrix.py --max-calls 8
```

---

## 二、全矩阵实测结果（8 档）

| 组合 | OK | ms | 推理字数 | 正文字数 | tool_calls | finish | reasoning_tokens |
|------|----|----|---------|---------|------------|--------|------------------|
| R+stream+tools | ✓ | ~4s | 110 | 0 | get_weather | tool_calls | 55 |
| R+stream+notools | ✓ | ~30s | 2009 | 14 | — | stop | 1163 |
| R+nostream+tools | ✓ | ~4s | 118 | 0 | get_weather | tool_calls | 56 |
| R+nostream+notools | ✓ | ~26s | 1836 | 18 | — | stop | 1096 |
| C+stream+tools | ✓ | ~2s | 0 | 14 | get_weather | tool_calls | — |
| C+stream+notools | ✓ | ~1s | 0 | 16 | — | stop | — |
| C+nostream+tools | ✓ | ~2s | 0 | 14 | get_weather | tool_calls | — |
| C+nostream+notools | ✓ | ~1s | 0 | 12 | — | stop | — |

- **R** = deepseek-reasoner，**C** = deepseek-chat  
- **tools** = 内置 `get_weather`、`list_supported_cities`（强引导话术）

---

## 三、DeepSeek 输出特点

### 3.1 推理模型 vs 普通模型

| 特性 | deepseek-reasoner | deepseek-chat |
|------|-------------------|---------------|
| 推理通道 | 有 `reasoning_content`（流式在 `delta`，非流式在 `message`） | 无 |
| `usage.completion_tokens_details.reasoning_tokens` | 有 | 无该字段 |
| 简单问题耗时 | 易「过度推理」 | 约 1–2s |

### 3.2 流式 vs 非流式

| 形态 | 流式 `stream=true` | 非流式 `stream=false` |
|------|--------------------|------------------------|
| 响应 | 多行 `data: {JSON}`，最后 `data: [DONE]` | 单次 JSON |
| 推理/正文 | `delta.reasoning_content` / `delta.content` | `message.reasoning_content` / `message.content` |
| tool_calls | `delta.tool_calls` 按 index 合并 | `message.tool_calls` 完整数组 |

### 3.3 流式 reasoner 两阶段

1. **推理阶段**：`delta.reasoning_content` 有字，`delta.content` 多为 `null`  
2. **正文阶段**：`delta.content` 有字，`reasoning_content` 为 `null`  
3. **结束**：末包常含 `finish_reason`、`usage`

### 3.4 带 tools

- 首轮可能 `finish_reason=tool_calls`，`content` 为空；需第二轮带 `role=tool` 结果再继续对话。  
- reasoner：常先推理再 `tool_calls`；chat：多直接 `tool_calls`。

### 3.5 非流式 reasoner 示例（结构）

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "…",
      "reasoning_content": "…"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "completion_tokens_details": { "reasoning_tokens": 154 }
  }
}
```

---

## 四、参数选择建议

| 场景 | 建议 |
|------|------|
| 面试官（展示推理 + 工具） | reasoner + stream + tools |
| 只要答案、低延迟 | chat + stream / nostream + notools |
| 调试完整结构 | nostream |
| 打字感 + 边推理边展示 | stream |

---

## 五、与项目适配层的关系

- 探针脚本**直连** API，不经过 `DeepSeekThinkingOpenAIAdapter`、`hello_agents`、Interviewer。  
- 用于对照：线上是否正确消费 `reasoning_content`、`tool_calls`、`finish_reason`。  
- reasoner 历史里 `assistant`+`tool_calls` 需带 `reasoning_content`（可为 `""`），避免 400。

---

## 六、hello_agents ReAct 与 wxr 适配层

### 6.1 框架默认 `ReActAgent.arun_stream` 的问题

1. **双请求**：先无 `tools` 流式，再 `invoke_with_tools`，与「单次 stream+tools」不一致。  
2. **推理丢失**：若只 `yield content`，`reasoning_content` 进不了 SSE。  
3. **STEP 与时间线**：仅靠 STEP_FINISH 整包补 THINKING，无法与正文流对齐。

### 6.2 wxr 已做（协议字段驱动，非正文正则拆流）

| 机制 | 说明 |
|------|------|
| `react_arun_stream_single_tool_stream` | 每步一次 `astream_invoke_with_tools` |
| `LLMStreamDelta` + `DeepSeekThinkingOpenAIAdapter` | `content` / `reasoning` 分通道 |
| `THINKING` 增量 + STEP_FINISH canonical | 已流式则不再整包重复 THINKING |
| `ChatView.vue` | `thinking` 直接拼接 chunk，避免一字一行 |

DSML 等内容清洗（`_strip_dsml_from_text`）与协议解析正交。

---

## 七、回归测试

```bash
python -m unittest discover -s backend/tests -p "test_*.py" -v
```

---

*基于 2026-03 实测整理；API 行为以官方文档为准。*
