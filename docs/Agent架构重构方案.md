# Agent架构重构方案

## 🎯 重构目标

**解决当前问题：**
1. ❌ 提取逻辑分散（QuestionExtractor + MetaExtractor）
2. ❌ Architect Agent职责混乱（既做提取又做管理）
3. ❌ 配置不统一（Extractor只有temperature）

**重构后目标：**
1. ✅ 提取逻辑统一（ExtractorService）
2. ✅ 每个Agent职责清晰
3. ✅ 配置统一（都有LOCAL和REMOTE配置）

---

## 📋 重构方案：三层架构

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    爬虫层（Hunter）                      │
│  - 牛客网爬虫（nowcoder_crawler.py）                    │
│  - 小红书爬虫（xhs_crawler.py）                         │
│  职责：抓取原始面经内容                                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              提取层（Extractor Service）                 │
│  - 统一的提取服务（extractor_service.py）               │
│  职责：从原文提取所有结构化信息                          │
│    1. 提取元信息（公司、岗位、业务线、难度）             │
│    2. 提取题目列表（题目、答案、分类、标签）             │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              管理层（Architect Agent）                   │
│  - 知识架构师（architect_agent.py）                     │
│  职责：知识管理（不做提取）                              │
│    1. 结构化解析                                         │
│    2. 语义查重                                           │
│    3. 构建知识图谱                                       │
│    4. 双写入库（Neo4j + SQLite）                        │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              应用层（Interviewer Agent）                 │
│  - 面试官（interviewer_agent.py）                       │
│  职责：面试对话                                          │
│    1. 出题推荐                                           │
│    2. 答案评估                                           │
│    3. 知识推荐                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 详细设计

### 1. Extractor Service（提取服务）

**文件：** `backend/services/extractor_service.py`

**性质：** 服务层（不是Agent）

**职责：** 从面经原文中提取所有结构化信息

**输入：**
```python
{
    "raw_text": "面经原文...",
    "source_platform": "nowcoder",
    "source_url": "https://..."
}
```

**输出：**
```python
{
    "meta": {
        "company": "字节跳动",
        "position": "后端研发",
        "business_line": "抖音",
        "difficulty": "medium",
        "source_platform": "nowcoder",
        "source_url": "https://..."
    },
    "questions": [
        {
            "question_text": "请介绍Redis的持久化机制",
            "answer_text": "RDB、AOF",
            "difficulty": "medium",
            "question_type": "缓存题",
            "topic_tags": ["Redis", "持久化"]
        }
    ]
}
```

**实现方式：**
- 合并 `question_extractor.py` 的题目提取逻辑
- 合并 `architect_tools.py` 的 `MetaExtractor` 逻辑
- 使用规则 + LLM 的混合策略

**配置：**
```bash
EXTRACTOR_MODE=local
EXTRACTOR_LOCAL_MODEL=qwen3:4b
EXTRACTOR_LOCAL_BASE_URL=http://localhost:11434/v1
EXTRACTOR_LOCAL_TIMEOUT=60
EXTRACTOR_REMOTE_MODEL=doubao-1-5-pro-32k-250115
EXTRACTOR_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EXTRACTOR_REMOTE_TIMEOUT=300
EXTRACTOR_TEMPERATURE=0.2
```

---

### 2. Architect Agent（知识架构师）

**文件：** `backend/agents/architect_agent.py`

**性质：** 独立Agent（使用hello-agents框架）

**职责：** 纯粹的知识管理（不做提取）

**输入：**
```python
{
    "meta": {...},           # 来自Extractor
    "questions": [...]       # 来自Extractor
}
```

**输出：**
```python
{
    "success": true,
    "processed_count": 10,
    "duplicates_found": 2,
    "graph_nodes_created": 15,
    "db_records_inserted": 8
}
```

**工具集：**
1. `KnowledgeStructurer` - 结构化解析
   - 解析题目的知识点
   - 构建知识点之间的关系

2. `DuplicateChecker` - 语义查重
   - 使用Embedding检测重复题目
   - 合并相似题目

3. `GraphBuilder` - 图谱构建
   - 构建知识图谱节点和关系
   - 题目 → 知识点 → 技术栈

4. `BaseManager` - 双写入库
   - 写入Neo4j（知识图谱）
   - 写入SQLite（结构化数据）

**移除的工具：**
- ❌ `MetaExtractor` - 移到Extractor Service

**配置：**
```bash
ARCHITECT_MODE=local
ARCHITECT_LOCAL_MODEL=qwen3:4b
ARCHITECT_LOCAL_BASE_URL=http://localhost:11434/v1
ARCHITECT_LOCAL_TIMEOUT=60
ARCHITECT_REMOTE_MODEL=doubao-1-5-pro-32k-250115
ARCHITECT_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARCHITECT_REMOTE_TIMEOUT=300
ARCHITECT_TEMPERATURE=0.2
```

---

### 3. Interviewer Agent（面试官）

**文件：** `backend/agents/interviewer_agent.py`

**性质：** 独立Agent（使用hello-agents框架）

**职责：** 面试对话

**输入：**
```python
{
    "user_message": "我想练习Redis相关的题目",
    "context": {...}
}
```

**输出：**
```python
{
    "response": "好的，我为你推荐了3道Redis题目...",
    "questions": [...],
    "suggestions": [...]
}
```

**工具集：**
1. `QuestionRecommender` - 题目推荐
2. `AnswerEvaluator` - 答案评估
3. `KnowledgeNavigator` - 知识导航
4. `NoteTaker` - 笔记管理
5. `MasteryTracker` - 掌握度追踪

**配置：**
```bash
INTERVIEWER_MODE=local
INTERVIEWER_LOCAL_MODEL=qwen3:4b
INTERVIEWER_LOCAL_BASE_URL=http://localhost:11434/v1
INTERVIEWER_LOCAL_TIMEOUT=60
INTERVIEWER_REMOTE_MODEL=doubao-1-5-pro-32k-250115
INTERVIEWER_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
INTERVIEWER_REMOTE_TIMEOUT=300
INTERVIEWER_TEMPERATURE=0.6
INTERVIEWER_MAX_STEPS=8
```

---

## 📊 职责对比表

| 组件 | 性质 | 职责 | 输入 | 输出 | 使用LLM |
|------|------|------|------|------|---------|
| **Hunter** | 爬虫服务 | 抓取原文 | URL | 原文 | ❌ |
| **Extractor** | 提取服务 | 提取信息 | 原文 | 结构化数据 | ✅ |
| **Architect** | Agent | 知识管理 | 结构化数据 | 图谱+数据库 | ✅ |
| **Interviewer** | Agent | 面试对话 | 用户问题 | 面试回答 | ✅ |

---

## 🔄 数据流

### 完整流程

```
1. Hunter（爬虫）
   输入：URL
   输出：原文
   ↓
2. Extractor Service（提取）
   输入：原文
   输出：{meta, questions}
   ↓
3. Architect Agent（管理）
   输入：{meta, questions}
   输出：图谱 + 数据库
   ↓
4. Interviewer Agent（对话）
   输入：用户问题
   输出：面试回答
```

### 示例

**步骤1：Hunter抓取**
```python
# nowcoder_crawler.py
raw_text = "一面问了Redis的持久化，我说了RDB和AOF..."
```

**步骤2：Extractor提取**
```python
# extractor_service.py
result = extractor.extract_all(raw_text)
# {
#   "meta": {"company": "字节跳动", "position": "后端研发"},
#   "questions": [{"question_text": "请介绍Redis的持久化机制", ...}]
# }
```

**步骤3：Architect管理**
```python
# architect_agent.py
architect.run(result)
# - 语义查重
# - 构建图谱：Redis → 持久化 → RDB/AOF
# - 写入数据库
```

**步骤4：Interviewer对话**
```python
# interviewer_agent.py
interviewer.run("我想练习Redis")
# - 推荐Redis相关题目
# - 评估答案
# - 追踪掌握度
```

---

## 📝 重构步骤

### 阶段1：创建Extractor Service（不影响现有功能）

**文件：** `backend/services/extractor_service.py`

**任务：**
1. 创建 `ExtractorService` 类
2. 实现 `extract_meta()` 方法（从MetaExtractor迁移）
3. 实现 `extract_questions()` 方法（从question_extractor迁移）
4. 实现 `extract_all()` 方法（统一接口）
5. 添加配置支持（LOCAL/REMOTE）

**测试：**
- 单元测试：测试元信息提取
- 单元测试：测试题目提取
- 集成测试：测试完整提取流程

---

### 阶段2：简化Architect Agent（不影响现有功能）

**文件：** `backend/tools/architect_tools.py`

**任务：**
1. 删除 `MetaExtractor` 类
2. 保留 `KnowledgeStructurer`
3. 保留 `DuplicateChecker`
4. 保留 `BaseManager`
5. 可选：添加 `GraphBuilder`（如果需要）

**文件：** `backend/agents/architect_agent.py`

**任务：**
1. 移除 `MetaExtractor` 工具注册
2. 更新输入格式（接收完整的结构化数据）
3. 更新Prompt（不再提取，只管理）

**测试：**
- 单元测试：测试每个工具
- 集成测试：测试完整管理流程

---

### 阶段3：更新调用流程（切换到新架构）

**文件：** `backend/services/scheduler.py`

**任务：**
1. 导入 `ExtractorService`
2. 更新 `process_post()` 方法
   ```python
   # 旧代码
   questions = extract_questions_from_content(raw_text)
   architect.run({"raw_text": raw_text})
   
   # 新代码
   extractor = ExtractorService()
   data = extractor.extract_all(raw_text)
   architect.run(data)
   ```

**文件：** `backend/services/crawler/nowcoder_crawler.py`

**任务：**
1. 更新爬虫调用流程
2. 使用新的 `ExtractorService`

**文件：** `backend/services/crawler/xhs_crawler.py`

**任务：**
1. 更新爬虫调用流程
2. 使用新的 `ExtractorService`

**测试：**
- 端到端测试：爬虫 → 提取 → 管理
- 回归测试：确保所有功能正常

---

### 阶段4：更新配置（统一配置）

**文件：** `backend/config/config.py`

**任务：**
1. 为Extractor添加完整配置
   - `extractor_mode`
   - `extractor_local_*`
   - `extractor_remote_*`

**文件：** `.env`

**任务：**
1. 添加Extractor配置
   ```bash
   EXTRACTOR_MODE=local
   EXTRACTOR_LOCAL_MODEL=qwen3:4b
   EXTRACTOR_LOCAL_BASE_URL=http://localhost:11434/v1
   EXTRACTOR_LOCAL_TIMEOUT=60
   EXTRACTOR_REMOTE_MODEL=doubao-1-5-pro-32k-250115
   EXTRACTOR_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
   EXTRACTOR_REMOTE_TIMEOUT=300
   EXTRACTOR_TEMPERATURE=0.2
   ```

**测试：**
- 配置测试：验证配置加载
- 切换测试：测试LOCAL/REMOTE切换

---

### 阶段5：清理旧代码（删除冗余）

**文件：** `backend/services/crawler/question_extractor.py`

**任务：**
1. 标记为废弃（添加注释）
2. 或者删除（如果确认不再使用）

**文件：** `backend/tools/architect_tools.py`

**任务：**
1. 确认 `MetaExtractor` 已删除
2. 清理相关导入

**测试：**
- 回归测试：确保所有功能正常
- 性能测试：对比重构前后性能

---

## ✅ 重构检查清单

### 阶段1：Extractor Service
- [ ] 创建 `extractor_service.py`
- [ ] 实现 `extract_meta()`
- [ ] 实现 `extract_questions()`
- [ ] 实现 `extract_all()`
- [ ] 添加配置支持
- [ ] 单元测试
- [ ] 集成测试

### 阶段2：Architect Agent
- [ ] 删除 `MetaExtractor`
- [ ] 更新工具注册
- [ ] 更新输入格式
- [ ] 更新Prompt
- [ ] 单元测试
- [ ] 集成测试

### 阶段3：调用流程
- [ ] 更新 `scheduler.py`
- [ ] 更新 `nowcoder_crawler.py`
- [ ] 更新 `xhs_crawler.py`
- [ ] 端到端测试
- [ ] 回归测试

### 阶段4：配置
- [ ] 更新 `config.py`
- [ ] 更新 `.env`
- [ ] 配置测试
- [ ] 切换测试

### 阶段5：清理
- [ ] 标记/删除旧代码
- [ ] 清理导入
- [ ] 回归测试
- [ ] 性能测试

---

## 🎯 重构后的优势

### 1. 职责清晰
- ✅ Extractor：只做提取
- ✅ Architect：只做管理
- ✅ Interviewer：只做对话

### 2. 配置统一
- ✅ 所有服务都有LOCAL和REMOTE配置
- ✅ 可以灵活切换本地/远程

### 3. 易于维护
- ✅ 代码结构清晰
- ✅ 职责单一
- ✅ 易于测试

### 4. 易于扩展
- ✅ 添加新的提取逻辑：修改Extractor
- ✅ 添加新的管理逻辑：修改Architect
- ✅ 添加新的对话逻辑：修改Interviewer

---

## 📊 风险评估

### 低风险
- ✅ 阶段1：创建新服务（不影响现有功能）
- ✅ 阶段2：简化Agent（不影响现有功能）

### 中风险
- ⚠️ 阶段3：更新调用流程（需要充分测试）

### 高风险
- ❌ 阶段5：删除旧代码（需要确认不再使用）

### 风险缓解
1. 分阶段重构（每个阶段独立测试）
2. 保留旧代码（标记为废弃，不立即删除）
3. 充分测试（单元测试 + 集成测试 + 端到端测试）
4. 回滚计划（如果出现问题，可以快速回滚）

---

## 🚀 开始重构？

**我建议：**
1. 先审查这个方案
2. 确认职责划分是否合理
3. 确认重构步骤是否完整
4. 然后我开始实施

**你觉得这个方案如何？需要调整吗？** 🤔
