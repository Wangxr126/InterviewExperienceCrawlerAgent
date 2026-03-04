from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.tools.architect_tools import (
    MetaExtractor,
    KnowledgeStructurer,
    DuplicateChecker,
    BaseManager
)
from backend.agents.prompts.architect_prompt import architect_prompt


class KnowledgeArchitectAgent(ReActAgent):
    """
    知识架构师：元信息提取 → 结构化解析 → 语义查重 → 双写入库
    工具：MetaExtractor / KnowledgeStructurer / DuplicateChecker / BaseManager
    """
    def __init__(self):
        llm = HelloAgentsLLM(
            provider=settings.llm_provider,
            model=settings.architect_model,
            api_key=settings.architect_api_key or settings.llm_api_key,
            base_url=settings.architect_base_url or settings.llm_base_url,
            temperature=settings.architect_temperature,
            timeout=settings.llm_timeout
        )

        registry = ToolRegistry()
        registry.register_tool(MetaExtractor())
        registry.register_tool(KnowledgeStructurer())
        registry.register_tool(DuplicateChecker())
        registry.register_tool(BaseManager())

        super().__init__(
            name="KnowledgeArchitect",
            llm=llm,
            tool_registry=registry,
            system_prompt=architect_prompt,
        )
