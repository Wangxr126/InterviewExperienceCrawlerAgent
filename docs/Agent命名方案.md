# Agent命名方案

## 问题：Extractor应该叫什么？

### 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Extractor Agent** | 准确（有LLM） | 不好听 | ⭐⭐ |
| **Parser Agent** | 简洁 | 不够准确（Parser偏向解析） | ⭐⭐⭐ |
| **Analyzer Agent** | 专业 | 偏向分析而非提取 | ⭐⭐ |
| **Hunter Agent** | 形象（猎取信息） | 可能与爬虫混淆 | ⭐⭐ |
| **Miner Agent** | 形象（挖掘信息） | 很好听！ | ⭐⭐⭐⭐⭐ |
| **Digger Agent** | 形象（挖掘） | 不如Miner | ⭐⭐⭐ |

### 推荐方案：Miner Agent（信息挖掘师）

**理由：**
1. ✅ 形象：从原文中"挖掘"结构化信息
2. ✅ 好听：Miner比Extractor更有画面感
3. ✅ 准确：有LLM，是Agent
4. ✅ 专业：数据挖掘（Data Mining）是专业术语

**新架构命名：**
```
Hunter（爬虫）→ 抓取原文
   ↓
Miner Agent（挖掘师）→ 挖掘结构化信息（使用LLM）
   ↓
Knowledge Manager（管理器）→ 管理数据（无LLM）
   ↓
Interviewer Agent（面试官）→ 面试对话（使用LLM）
```

---

## 新的三层架构

```
┌─────────────────────────────────────────┐
│         爬虫层（Hunter Service）         │
│  职责：抓取原始面经                      │
│  LLM：❌                                 │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│         挖掘层（Miner Agent）            │
│  职责：从原文挖掘结构化信息              │
│    - 挖掘元信息（公司、岗位、难度）      │
│    - 挖掘题目列表                        │
│  LLM：✅ 使用LLM挖掘                     │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│       管理层（Knowledge Manager）        │
│  职责：数据管理                          │
│    - 构建知识图谱                        │
│    - 双写入库                            │
│  LLM：❌                                 │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│       应用层（Interviewer Agent）        │
│  职责：面试对话                          │
│  LLM：✅                                 │
└─────────────────────────────────────────┘
```

---

## 文件命名

```
backend/agents/
├── miner_agent.py           # 信息挖掘师（原extractor）
├── interviewer_agent.py     # 面试官
└── orchestrator.py          # 编排器

backend/services/
├── knowledge_manager.py     # 知识管理器（原architect）
├── crawler/                 # 爬虫
└── ...

backend/prompts/
├── miner_prompt.py          # Miner的Prompt
├── interviewer_prompt.py    # Interviewer的Prompt
└── ...
```

---

## 你觉得Miner Agent这个名字如何？

如果不喜欢，我们可以再讨论其他方案！
