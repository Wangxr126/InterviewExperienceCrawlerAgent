"""
金牌面试官 Agent v4.2 — 基于 hello_agents 记忆与上下文机制

设计原则：
  • ReAct 范式：Thought → Action（工具）→ Observation → 循环，直到 Finish
  • 使用 hello_agents HistoryManager：_build_messages() 注入对话历史，LLM 获得多轮上下文
  • 使用 hello_agents ContextBuilder（GSSC）：Orchestrator 构建记忆上下文
  • session 由项目 SQLite 管理，每次 chat 前从 SQLite 加载历史到 history_manager

工具职责：
  recall_memory               ← 首次对话/话题切换时主动查用户背景
  get_session_context         ← 本次会话统计
  get_recommended_question    ← 出题
  find_similar_questions      ← 举一反三/换个问法
  filter_questions            ← 按条件筛题
  manage_note                 ← 笔记 CRUD
  get_mastery_report          ← 查掌握度报告
  get_knowledge_recommendation← 学习资源推荐
  analyze_resume              ← 分析简历
"""
import logging
from typing import List, Dict

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.core.message import Message
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.tools.interviewer_tools import get_interviewer_tools
from backend.agents.prompts.interviewer_prompt import interviewer_prompt

logger = logging.getLogger(__name__)

# 历史消息最大条数（约 10 轮对话），避免 token 超限
HISTORY_MAX_MESSAGES = 20


class InterviewerAgent(ReActAgent):
    """
    面试对话 ReAct Agent v4.1。

    hello_agents ReActAgent 能力：
    - 内置 Thought 工具：LLM 显式记录推理过程（可观测）
    - 内置 Finish  工具：明确标记任务完成，返回最终答案
    - 并行工具执行：arun() 中多工具并发（asyncio.gather）
    - arun_stream()：真正 token 级流式输出，可直接接 stream_to_sse()

    职责边界：
    - 只做「需要语言理解和推理」的对话/出题/解释/笔记/掌握度查询
    - 确定性副作用（SM-2 更新、记忆写入、session 入库）全部由 Orchestrator 代码层保证
    - 记忆读取通过 recall_memory 工具主动触发，而非 Orchestrator 注入
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

        # ── LLM 配置 ──────────────────────────────────────────────
        _model = settings.interviewer_model or settings.llm_model_id
        llm = HelloAgentsLLM(
            model=_model,
            api_key=settings.interviewer_api_key or settings.llm_api_key,
            base_url=settings.interviewer_base_url or settings.llm_base_url,
            temperature=settings.interviewer_temperature,
            timeout=settings.interviewer_timeout or settings.llm_timeout,
        )

        # ── 工具注册 ──────────────────────────────────────────────
        registry = ToolRegistry()
        for tool in get_interviewer_tools():
            registry.register_tool(tool)

        # ── hello-agents Config（16 项能力全开）──────────────────────
        _data_dir = str(settings.backend_data_dir / "memory")
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        _agent_config = HelloAgentsConfig(
            # 可观测性
            trace_enabled=True,
            trace_dir=f"{_data_dir}/traces",
            trace_sanitize=True,
            # 会话持久化
            session_enabled=True,
            session_dir="sqlite",
            auto_save_enabled=True,
            auto_save_interval=2,
            # 上下文工程（HistoryManager + TokenCounter）
            context_window=128000,
            compression_threshold=0.8,
            min_retain_rounds=10,
            enable_smart_compression=settings.enable_smart_compression,
            # TodoWrite + DevLog
            todowrite_enabled=True,
            todowrite_persistence_dir=f"{_data_dir}/todos",
            devlog_enabled=True,
            devlog_persistence_dir=f"{_data_dir}/devlogs",
            # Skills 知识外化（面试官场景禁用：出题/讲解/评价用专用工具，Skill 易误触发 frontend-design 等无关技能）
            skills_enabled=False,
            skills_dir=_skills_dir,
            skills_auto_register=False,
            # 熔断器
            circuit_enabled=True,
            circuit_failure_threshold=3,
            # 工具输出截断（ObservationTruncator）
            tool_output_max_lines=500,
            tool_output_max_bytes=20480,
            tool_output_dir=f"{_data_dir}/tool-output",
            # 子代理（TaskTool）
            subagent_enabled=True,
            # 异步
            async_enabled=True,
            max_concurrent_tools=3,
            # 流式输出
            stream_enabled=True,
            stream_buffer_size=100,
            stream_include_thinking=True,
            stream_include_tool_calls=True,
        )

        max_steps = getattr(settings, "interviewer_max_steps", 3)  # 从 .env 读取，默认 3

        # ── 初始化父类 ReActAgent ──────────────────────────────────
        super().__init__(
            name="InterviewerAgent",
            llm=llm,
            tool_registry=registry,
            system_prompt=interviewer_prompt,
            max_steps=max_steps,
            config=_agent_config,
        )

        # 替换为 SqliteSessionStore，使 hello_agents 会话持久化与项目 SQLite 对齐
        if _agent_config.session_enabled:
            from backend.services.storage.sqlite_session_store import SqliteSessionStore
            self.session_store = SqliteSessionStore(session_dir="sqlite")

        logger.info(
            f"[InterviewerAgent] 初始化完成 model={_model} "
            f"base_url={settings.interviewer_base_url or settings.llm_base_url} "
            f"max_steps={max_steps}"
        )

    def _build_messages(self, input_text: str) -> List[Dict[str, str]]:
        """
        覆盖 ReActAgent：使用 hello_agents HistoryManager 注入对话历史。

        原版 ReActAgent 只返回 [system, user]，无法利用多轮上下文。
        本实现：system + 历史消息（user/assistant 交替）+ 当前 user 消息。
        """
        messages = []

        # 系统提示词（由父类 system_prompt 提供）
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 从 HistoryManager 获取历史，转为 OpenAI API 格式
        history = self.history_manager.get_history()
        recent = history[-HISTORY_MAX_MESSAGES:] if len(history) > HISTORY_MAX_MESSAGES else history
        for msg in recent:
            if msg.role in ("user", "assistant") and (msg.content or "").strip():
                messages.append({"role": msg.role, "content": msg.content})

        # 当前用户消息
        messages.append({"role": "user", "content": input_text})

        return messages
