# 1.5b 模型面经题目提取：问题分析与改进建议

## 一、从交互日志发现的主要问题

### 1. 输出格式错误（最严重）

| 现象 | 示例 |
|------|------|
| 输出对象而非数组 | `{"1. Transformer...": {...}}` 而非 `[{...}]` |
| JSON 残缺/截断 | `{"1. Transformer...": [{\":\"\"  \t}"` 首行即断 |
| 非法 JSON | 缺少引号、多余逗号、key 错误 |

**原因**：1.5b 小模型对严格 JSON 数组格式的遵循能力弱，易受上下文干扰。

---

### 2. 答案幻觉 / 照抄 few-shot 示例（高频）

| 现象 | 示例 |
|------|------|
| 照抄 OOM 答案 | 原文问「MCP是什么」，输出 `"1. 堆内存溢出：用 -Xmx 调大、mat 分析 dump\n2. 栈溢出..."` |
| 照抄 LRU 答案 | 原文问「介绍一下你的项目」，输出 `"1. 数据结构：HashMap + 双向链表\n2. get：若存在则移到链表头..."` |
| 照抄 Redis/MySQL 答案 | 与原文完全无关的题目也塞入 RDB/AOF、B+树等 |

**原因**：few-shot 示例中的 OOM、LRU、Redis 等答案被模型「记忆」并错误复用。

---

### 3. 题目拆分/合并错误

| 现象 | 示例 |
|------|------|
| 一道题拆成多道 | 「MCP与Skills分别是什么，讲一下二者区别」→ 拆成「MCP是什么?」「Skills分别是什么?」 |
| 多道题合并 | 若干独立题目被合并为一个 |
| 改写题目 | 原文「1.你对agent了解多少呢」→ 输出「Agent 的理解」 |

---

### 4. 幻觉无关题目

| 现象 | 示例 |
|------|------|
| 输出原文没有的题 | 「3. 堆内存溢出用 -Xmx 调大」「7. why离职？」「8. 期望薪资？」 |
| 把示例当题目 | 输出「字节跳动」「1面」「2面」等作为 key |
| 噪声当题目 | 「框架八股:fas_牛客网_牛客在手,offer不愁」「6._牛客网_牛客在手,offer不愁」 |

---

### 5. 漏题

| 现象 | 示例 |
|------|------|
| 原文 12 道题只输出 1 道 | Transformer、RAG、PPO/DPO 等全部漏掉 |
| 只输出部分 | 原文 5 道题只输出 2–3 道 |

---

### 6. topic_tags / question_type 错误

- topic_tags 经常填「Java」「JVM」「OOM」等与题目无关的标签
- question_type 混淆（如把技术题标成 HR 问题）

---

## 二、改进方向（按优先级）

### 方案 A：Prompt 工程（无需微调）

1. **彻底移除 few-shot**：当前示例已证实会诱发照抄，建议只保留极简格式说明。
2. **强制数组格式**：在 system prompt 中强调「必须且仅输出一个 JSON 数组，以 [ 开头、以 ] 结尾」。
3. **答案约束**：明确「answer_text 仅从原文提取，原文无答案则填空；严禁编造或照抄示例」。
4. **分步提取**：若单次输出不稳定，可先让模型只输出题目列表，再单独请求补充 answer/tags。

### 方案 B：换用更大模型（推荐优先尝试）

- 使用 qwen2.5:3b、7b 或 llama3.2:3b 做提取，格式遵循和抗干扰能力会明显提升。
- 若必须用 1.5b，再考虑微调。

### 方案 C：微调 1.5b（需构造数据）

- 构造 200–500 条「面经原文 → 标准 JSON 数组」样本。
- 格式统一、答案仅来自原文、无幻觉。
- 使用 LoRA/QLoRA 微调，重点学习：输出格式、不照抄、不幻觉。

---

## 三、微调数据构造说明

### 3.1 文件位置（均在 `微调/` 文件夹下）

- **脚本**：`微调/finetune_data_builder.py`
- **手动样本**：`微调/manual_samples.jsonl`（每行一个 `{"input":"面经原文","output":[{...}]}`）
- **输出**：`微调/finetune_samples.jsonl`（SFT 格式，兼容 LLaMA-Factory）
- **日志源**：`backend/data/logs/llm_prompt_log.jsonl`（--from-log 时读取）

### 3.2 用法（在项目根目录执行）

```bash
# 输出空模板，供复制后手动填写
python 微调/finetune_data_builder.py --template

# 从 manual_samples.jsonl 读取并生成 SFT 数据（推荐）
python 微调/finetune_data_builder.py --from-manual

# 从 llm_prompt_log.jsonl 筛选可用样本（输出为合法数组且无 OOM/LRU 幻觉）
python 微调/finetune_data_builder.py --from-log

# 指定输出路径
python 微调/finetune_data_builder.py --from-manual -o 微调/finetune_samples.jsonl
```

### 3.3 数据格式

**manual_samples.jsonl**（每行一条）：

```json
{"input": "面经原文内容...", "output": [{"question_text":"题目1","answer_text":"","difficulty":"","question_type":"技术题","topic_tags":["Java"],"company":"","position":""}, ...]}
```

**finetune_samples.jsonl**（SFT 格式）：

```json
{
  "conversations": [
    {"from": "human", "value": "你是面经题目提取专家。仅从面经原文中提取所有面试题，输出一个 JSON 数组。...\n\n【面经原文】\n{面经原文}"},
    {"from": "gpt", "value": "[{\"question_text\":\"...\",\"answer_text\":\"\",...}]"}
  ]
}
```

### 3.4 样本要求

- **input**：纯面经原文，不含模板、示例
- **output**：标准 JSON 数组，题目与原文一一对应
- **answer_text**：仅来自原文或填空，严禁照抄 OOM/LRU/Redis 等示例
- **建议数量**：200–500 条高质量样本用于微调 1.5b
