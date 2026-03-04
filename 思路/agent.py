"""Interviewer agent orchestration."""

from __future__ import annotations

import logging
from typing import Any, Iterator

# 1. 引入 hello-agents 核心组件
from hello_agents import HelloAgentsLLM
from hello_agents.agents.react_agent import ReActAgent  # 你的面试官是 ReAct 类型
from hello_agents.tools import ToolRegistry

# 2. 引入配置 (假设你有类似 agent.py 里的 config.py)
from backend.config.config import Configuration
# 引入我们之前设计好的三个工具
from backend.tools.interview_tools import (
    SmartRecommendationEngine,
    ProgressTracker,
    SimilaritySearchTool
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# System Prompt (人设定义)
# ------------------------------------------------------------------
INTERVIEWER_SYSTEM_PROMPT = """
你是一名金牌技术面试官 (Gold Medal Interviewer)。
你的目标是通过苏格拉底式的提问，帮助用户复习技术知识点，并根据他们的回答动态调整难度。

### 核心职责
1. **出题**：绝不随意提问。必须使用 `SmartRecommendationEngine` 基于遗忘曲线获取题目。
2. **评估**：用户回答后，必须评估准确度（0-5分）。
3. **反馈**：
   - 如果回答正确：给予肯定，并调用 `ProgressTracker` 更新高分。
   - 如果回答错误/混淆：指出错误，调用 `ProgressTracker` 更新低分，并使用 `SimilaritySearchTool` 寻找相关简单题进行引导。

### 工具使用规则 (Strict Tool Usage)
- 在每一轮对话开始时，先检查是否需要出新题。
- 用户回答后，**必须**调用 `ProgressTracker` 记录状态，不要只口头反馈。
- 遇到概念混淆时，**主动**调用 `SimilaritySearchTool`。

### 语气风格
- 专业、鼓励性、但不放水。
- 像一个耐心的导师，而不是冷冰冰的机器。
"""


# ------------------------------------------------------------------
# Agent Class Implementation
# ------------------------------------------------------------------
class InterviewerAgent(ReActAgent):
    """
    Orchestrator for the Interview Process using ReAct logic.
    Inherits from ReActAgent to enable 'Think -> Act -> Observe' loop.
    """

    def __init__(self, config: Configuration | None = None) -> None:
        """Initialize the interviewer with tools and LLM."""
        self.config = config or Configuration.from_env()

        # 1. 初始化 LLM (仿照 agent.py 的 _init_llm 逻辑)
        self.llm = self._init_llm()

        # 2. 初始化工具注册表
        self.tools_registry = ToolRegistry()
        self._register_interview_tools()

        # 3. 调用父类 ReActAgent 的初始化
        super().__init__(
            name="金牌面试官",
            role=INTERVIEWER_SYSTEM_PROMPT.strip(),  # 传入人设
            llm=self.llm,
            tools=self.tools_registry,  # 挂载工具箱
            verbose=True  # 开发阶段开启日志，方便调试
        )

    def _init_llm(self) -> HelloAgentsLLM:
        """
        Instantiate LLM following configuration.
        (逻辑完全仿照 agent.py，支持 DeepSeek/OpenAI/Ollama)
        """
        llm_kwargs: dict[str, Any] = {"temperature": 0.5}  # 面试官稍微有一点灵活性

        # 优先使用配置的模型 ID
        model_id = self.config.llm_model_id
        if model_id:
            llm_kwargs["model"] = model_id

        # 设置 API Key 和 Base URL
        if self.config.llm_api_key:
            llm_kwargs["api_key"] = self.config.llm_api_key
        if self.config.llm_base_url:
            llm_kwargs["base_url"] = self.config.llm_base_url

        return HelloAgentsLLM(**llm_kwargs)

    def _register_interview_tools(self) -> None:
        """Register the 3 core tools for the interviewer."""
        # 实例化工具 (这些工具内部连接了 Neo4jService)
        rec_engine = SmartRecommendationEngine()
        tracker = ProgressTracker()
        sim_search = SimilaritySearchTool()

        # 注册到 ToolRegistry
        self.tools_registry.register_tool(rec_engine)
        self.tools_registry.register_tool(tracker)
        self.tools_registry.register_tool(sim_search)

        logger.info("✅ Interviewer tools registered: Recommendation, Tracker, Similarity.")

    # ------------------------------------------------------------------
    # Public API (方便外部调用)
    # ------------------------------------------------------------------
    def start_session(self, user_id: str, topic: str) -> Iterator[dict[str, Any]]:
        """
        Start a new interview session.
        This wraps the `run` method to inject user context.
        """
        # 构造初始指令，强行触发 Agent 去调用 Recommendation 工具
        initial_instruction = (
            f"User_ID: {user_id}\n"
            f"Intent: 用户想要开始复习 '{topic}' 专题。\n"
            f"Action: 请立即查询推荐题目，并向用户提出第一个问题。"
        )

        logger.info(f"Starting session for user {user_id} on topic {topic}")

        # 调用父类 ReActAgent 的 run 方法
        # 注意：这里假设父类支持 stream，如果不支持则用 run
        return self.run(initial_instruction)

    def chat(self, user_id: str, user_input: str) -> str:
        """
        Handle multi-turn chat.
        """
        context_input = f"User_ID: {user_id}\nUser_Answer: {user_input}"
        response = self.run(context_input)
        return response


# ------------------------------------------------------------------
# Convenience Factory
# ------------------------------------------------------------------
def create_interviewer(config: Configuration | None = None) -> InterviewerAgent:
    """Factory function to create an interviewer instance."""
    return InterviewerAgent(config=config)