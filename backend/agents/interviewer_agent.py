"""
金牌面试官 Agent v3.0

职责收窄（对比 v2.0 的变化）：
  ✅ 保留：自然对话、出题推荐策略、换个问法、筛选题目、笔记、掌握度查看
  ✅ 保留：简历分析（需要 NLU 理解）、知识推荐（用户主动请求时）
  ❌ 移除：update_progress —— 已由 Orchestrator.submit_answer() 确定性调用
  ❌ 移除：generate_evaluation —— 已由 Orchestrator.end_session() 触发
  ❌ 移除：内存写入职责 —— 全部由 Orchestrator 代码层保证

简单一句话：InterviewerAgent 只做"需要语言理解和推理"的事，
             确定性副作用由 Orchestrator 代码层保证执行。
"""
import logging
from hello_agents import ReActAgent as PlanAndSolveAgent  # PlanAndSolveAgent 无 tool_registry，改用 ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.tools.interviewer_tools import (
    SmartRecommendationEngine,
    SimilaritySearchTool,
    FilterTool,
    NoteTool,
    MasteryReporter,
    KnowledgeRecommender,
    ResumeAnalysisTool,
)
from backend.agents.prompts.interviewer_prompt import interviewer_prompt

logger = logging.getLogger(__name__)


def _try_get_memory_tool(user_id: str = "default"):
    """尝试加载 hello-agents MemoryTool（可选，失败不影响主流程）

    只启用三层记忆（工作/情节/语义），跳过感知层（perceptual）：
    - 感知层需要下载 CLIP/CLAP 大模型（图像/音频），面经场景不需要
    - 语义层使用 DashScope Embedding + Qdrant + Neo4j，已在 .env 中配置
    """
    try:
        from hello_agents.tools import MemoryTool
        from hello_agents.memory import MemoryConfig
        from backend.config.config import settings as _s
        mem_cfg = MemoryConfig(storage_path=_s.memory_data_dir)
        mt = MemoryTool(
            user_id=user_id,
            memory_config=mem_cfg,
            memory_types=["working", "episodic", "semantic"],
        )
        logger.info("✅ MemoryTool 初始化成功（工作/情节/语义三层记忆）")
        return mt
    except ImportError:
        logger.warning("⚠️ MemoryTool 未找到，需要 pip install 'hello-agents[all]'")
        return None
    except Exception as e:
        logger.warning(f"⚠️ MemoryTool 初始化失败（降级运行）: {e}")
        return None


class InterviewerAgent(PlanAndSolveAgent):
    """
    面试对话 Agent。
    专注：自然语言交互、题目推荐策略、概念解释、换个问法、笔记、资源推荐。
    不负责：答题记录写入、SM-2更新、记忆写入（这些全由 Orchestrator 确定性执行）。
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

        # 角色未单独配置时回退到全局模型（Ollama 需用本地模型名如 qwen3-vl:4b）
        _model = settings.interviewer_model or settings.llm_model_id
        llm = HelloAgentsLLM(
            provider=settings.llm_provider,
            model=_model,
            api_key=settings.interviewer_api_key or settings.llm_api_key,
            base_url=settings.interviewer_base_url or settings.llm_base_url,
            temperature=settings.interviewer_temperature,
            timeout=settings.llm_timeout
        )
        logger.info(f"Interviewer LLM: provider={settings.llm_provider}, model={_model}, base={settings.interviewer_base_url or settings.llm_base_url}")

        registry = ToolRegistry()

        # ── 可选：hello-agents 框架四层记忆（仅用于用户主动查询记忆时）──
        memory_tool = _try_get_memory_tool(user_id)
        if memory_tool:
            registry.register_tool(memory_tool)

        # ── 需要 LLM 推理的工具 ──
        registry.register_tool(SmartRecommendationEngine())   # 出题策略推理
        registry.register_tool(SimilaritySearchTool())        # 换个问法/举一反三
        registry.register_tool(FilterTool())                  # 按条件筛选题目
        registry.register_tool(NoteTool())                    # 笔记 CRUD
        registry.register_tool(MasteryReporter())             # 掌握度报告
        registry.register_tool(KnowledgeRecommender())        # 用户主动请求时的资源推荐
        registry.register_tool(ResumeAnalysisTool())          # 简历 NLU 分析

        # 注意：ProgressTracker / InterviewEvaluator 已移除
        # 这些操作现在由 Orchestrator.submit_answer() / end_session() 确定性执行

        super().__init__(
            name="Interviewer",
            llm=llm,
            tool_registry=registry,
            system_prompt=interviewer_prompt,
        )
