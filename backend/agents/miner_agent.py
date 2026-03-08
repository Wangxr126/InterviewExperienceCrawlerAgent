"""
Miner Agent - 信息挖掘师
职责：从面经原文中智能挖掘结构化信息（使用 LLM）
"""
import logging
from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.prompts.miner_prompt import get_miner_prompt

logger = logging.getLogger(__name__)


class MinerAgent(ReActAgent):
    """
    信息挖掘师 Agent
    
    职责：从面经原文中智能挖掘结构化信息
    - 使用 LLM 进行语义理解
    - 提取元信息（公司、岗位、难度）
    - 提取题目列表（题目、答案、标签）
    """
    
    def __init__(self):
        llm = HelloAgentsLLM(
            provider=settings.llm_provider,
            model=settings.llm_model_id,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.miner_temperature,
            timeout=settings.llm_timeout
        )

        registry = ToolRegistry()
        # TODO: 注册 Miner 需要的工具

        super().__init__(
            name="Miner Agent",
            llm=llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
        )
        
        logger.info("✅ Miner Agent 初始化完成")
        logger.info(f"   - Model: {settings.llm_model_id}")
        logger.info(f"   - Provider: {settings.llm_provider}")
        logger.info(f"   - Base URL: {settings.llm_base_url}")
        logger.info(f"   - Temperature: {settings.miner_temperature}")
        logger.info(f"   - Max Tokens: {settings.miner_max_tokens or settings.llm_max_tokens}")
        logger.info(f"   - Timeout: {settings.llm_timeout}s")


# 全局实例
miner_agent = MinerAgent()
