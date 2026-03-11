# Agent 架构重构说明

## 重构目标

将两个 Agent 统一为**框架自动注入工具描述**的标准模式，解决工具描述维护分散、容易不同步的问题。

---

## 重构前的问题

### 1. MinerAgent（手动 Function Calling）
- ❌ 完全手动实现 function calling 循环
- ❌ 工具 schema 硬编码在代码中
- ❌ Prompt 中只有决策流程，工具描述分散在代码里
- ❌ 代码复杂度高（200+ 行手动循环逻辑）

### 2. InterviewerAgent（框架托管但 Prompt 冗余）
- ✅ 使用 hello-agents 框架
- ❌ **工具清单表格硬编码在 Prompt 中**
- ❌ 工具信息双重维护（Prompt + 工具类）
- ❌ 添加/删除工具时容易不同步

---

## 重构后的架构

### 统一原则：**单一数据源 + 框架自动注入**

```
工具类 (Tool)
  ├─ name: 工具名称
  ├─ description: 详细描述（包含调用时机）
  └─ parameters: 参数定义
         ↓
   框架自动注入
         ↓
   LLM 收到完整工具信息
```

---

## 具体改动

### 1. MinerAgent 重构

#### 改动前（手动模式）
```python
class MinerAgent:
    def __init__(...):
        self._llm = HelloAgentsLLM(...)
        self._all_tools = self._build_tool_schemas()  # 手动构建
    
    def run(...):
        # 200+ 行手动循环
        resp = client.chat.completions.create(
            tools=all_tools,  # 手动传入
            tool_choice="auto",
        )
        # 手动处理工具调用...
```

#### 改动后（框架托管）
```python
class MinerAgent(SimpleAgent):  # 继承框架基类
    def __init__(...):
        llm = HelloAgentsLLM(...)
        registry = ToolRegistry()
        registry.register_tool(OcrImagesTool(...))      # 框架自动处理
        registry.register_tool(MarkUnrelatedTool())
        registry.register_tool(FinishTool())
        
        super().__init__(
            llm=llm,
            tool_registry=registry,  # 工具交给框架
            system_prompt=get_miner_prompt(),
            max_tool_iterations=5,
        )
    
    def run(...):
        # 只需调用父类方法，框架自动处理循环
        result = super().run(user_input)
        return self._parse_result(result)
```

**优势**：
- ✅ 代码从 257 行减少到 121 行
- ✅ 工具描述统一在工具类中维护
- ✅ 框架自动处理工具循环和错误
- ✅ 更易扩展和维护

---

### 2. 工具类重构

#### 新增两个信号工具类

```python
class MarkUnrelatedTool(Tool):
    """标记无关帖子工具"""
    def __init__(self):
        super().__init__(
            name="mark_unrelated",
            description=(
                "标记当前帖子与面经无关（如求内推、纯吐槽、广告等）。"
                "调用时机：① 正文无题且无图片；② 正文无题且 OCR 后图片也无题。"
            ),
        )

class FinishTool(Tool):
    """完成提取工具"""
    def __init__(self):
        super().__init__(
            name="Finish",
            description=(
                "提取到面试题后调用此工具返回结果。"
                "调用时机：正文或 OCR 中找到了有效面试题。"
            ),
        )
```

**关键点**：
- 工具描述包含**调用时机**，LLM 知道何时使用
- 描述足够详细，无需在 Prompt 中重复

---

### 3. Prompt 重构

#### MinerAgent Prompt（改动后）

```python
MINER_REACT_SYSTEM_PROMPT = """你是面经题目提取专家。

## 工作流程
1. **分析正文**：判断正文是否包含有效面试题
2. **按需 OCR**：若正文无题但有图片，调用 ocr_images
3. **提取或标记**：
   - 找到面试题 → 调用 Finish 返回 JSON
   - 正文+图片均无题 → 调用 mark_unrelated

## 提取规则
...（业务规则）

**具体工具列表和参数见下方 [TOOLS] 部分（由框架自动注入）**
"""
```

**改动**：
- ❌ 删除：工具的详细描述和参数定义
- ✅ 保留：工作流程、业务规则、输出格式
- ✅ 新增：提示框架会自动注入工具信息

---

#### InterviewerAgent Prompt（改动后）

```python
interviewer_prompt = """你是「刷题伴侣」AI 助手。

## 你的职责
根据用户需求，直接回复或调用合适的工具完成任务。

**具体工具列表和参数见下方 [TOOLS] 部分（由框架自动注入）**

## 工具使用原则
- 用户要练习题目 → 调用推荐工具
- 用户要换个问法 → 调用相似题目工具
- 用户要筛选题目 → 调用筛选工具
...

## 行为准则
- 简洁、鼓励、中文
"""
```

**改动**：
- ❌ 删除：工具清单表格（7 个工具 × 详细描述）
- ✅ 保留：通用使用原则和行为准则
- ✅ 新增：提示框架会自动注入工具信息

---

### 4. 工具描述优化

确保所有工具的 `description` 包含：
1. **功能说明**：这个工具做什么
2. **调用时机**：什么情况下使用
3. **参数说明**：关键参数的含义

#### 示例：SmartRecommendationEngine

```python
class SmartRecommendationEngine(Tool):
    def __init__(self):
        super().__init__(
            name="get_recommended_question",
            description=(
                "获取下一道推荐面试题。"
                "mode 可选：auto（自动）、review（复习到期题）、"
                "weakness（薄弱点）、new（新题）、company（按公司）。"
            )
        )
```

---

## 重构收益

### 1. 代码质量
- ✅ MinerAgent 代码量减少 53%（257 → 121 行）
- ✅ 消除重复代码（工具描述只维护一处）
- ✅ 符合 DRY 原则

### 2. 可维护性
- ✅ 添加新工具：只需注册，无需修改 Prompt
- ✅ 修改工具描述：只改工具类，自动同步
- ✅ 删除工具：取消注册即可，无需清理 Prompt

### 3. 一致性
- ✅ 两个 Agent 使用相同的架构模式
- ✅ 工具描述和实际功能保证一致
- ✅ 降低维护出错概率

### 4. 扩展性
- ✅ 框架提供统一的工具调用接口
- ✅ 易于添加新的 Agent
- ✅ 支持工具复用（如 MemoryTool）

---

## 迁移指南

### 如果要添加新工具

**旧方式（不推荐）**：
1. 在工具类中定义工具
2. 在 Agent 代码中手动构建 schema
3. 在 Prompt 中添加工具说明
4. 三处都要改，容易遗漏

**新方式（推荐）**：
1. 创建工具类，写好 `description`（包含调用时机）
2. 在 Agent 的 `__init__` 中注册：`registry.register_tool(YourTool())`
3. 完成！框架自动注入工具信息

### 如果要修改工具描述

**旧方式**：
- 改工具类 → 改 Prompt → 容易不同步

**新方式**：
- 只改工具类的 `description` → 自动生效

---

## 注意事项

### 1. 工具描述要详细
框架会把 `description` 直接发给 LLM，所以要包含：
- 功能说明
- 调用时机
- 关键参数含义

### 2. Prompt 保持简洁
Prompt 只需要：
- 角色定位
- 工作流程
- 业务规则
- 行为准则

**不要在 Prompt 中重复工具信息！**

### 3. 兼容性
- 旧的调用方式已更新（`question_extractor.py`）
- 接口保持兼容：`run()` 方法签名不变
- 返回值格式不变

---

## 测试建议

### 1. 功能测试
- ✅ MinerAgent 能正确提取题目
- ✅ MinerAgent 能正确调用 OCR
- ✅ MinerAgent 能正确标记无关帖子
- ✅ InterviewerAgent 能正确推荐题目
- ✅ InterviewerAgent 能正确调用各种工具

### 2. 回归测试
- ✅ 运行现有的爬虫任务
- ✅ 检查题目提取准确率
- ✅ 检查 OCR 调用是否正常
- ✅ 检查日志输出是否正常

### 3. 性能测试
- ⚠️ 框架托管可能略慢于手动实现
- ⚠️ 但差异应该在可接受范围内（< 10%）

---

## 总结

这次重构实现了：
1. **架构统一**：两个 Agent 都使用框架托管模式
2. **单一数据源**：工具描述只在工具类中维护
3. **自动注入**：框架自动把工具信息发给 LLM
4. **代码简化**：减少重复代码，提高可维护性

**核心理念**：工具描述应该维护在工具类本身，而不是 Prompt 里！
