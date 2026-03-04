"""
LLM 服务模块 (LLM Factory)
负责根据 config.py 中的配置，为不同 Agent 创建专属的 LLM 实例。
"""

from typing import Dict, Optional
from hello_agents import HelloAgentsLLM
from ..config.config import settings

# 用于缓存不同角色的 LLM 实例，避免重复初始化
# Key: role_name (e.g., "default", "hunter", "architect")
# Value: HelloAgentsLLM instance
_llm_instances: Dict[str, HelloAgentsLLM] = {}

def get_llm(role: str = "default") -> HelloAgentsLLM:
    """
    获取指定角色的 LLM 实例 (支持单例缓存)。

    Args:
        role: 角色名称，支持 "default", "hunter", "architect", "interviewer"

    Returns:
        HelloAgentsLLM 实例
    """
    global _llm_instances

    # 1. 如果缓存里有，直接返回
    if role in _llm_instances and _llm_instances[role] is not None:
        return _llm_instances[role]

    # 2. 根据角色解析配置 (处理回退逻辑)
    llm_config = _resolve_config_for_role(role)

    print(f"🔄 初始化 LLM [{role}] -> Model: {llm_config['model']}")

    # 3. 创建实例
    instance = HelloAgentsLLM(
        provider=settings.llm_provider, # 统一使用同一个 Provider (如 volcengine)
        model=llm_config["model"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        temperature=llm_config["temperature"],
        timeout=settings.llm_timeout
    )

    # 4. 存入缓存
    _llm_instances[role] = instance
    return instance

def _resolve_config_for_role(role: str) -> Dict[str, any]:
    """
    内部辅助函数：解析配置。
    如果专用配置为空，则回退到全局默认配置。
    """
    # 默认值 (Global Default)
    config = {
        "model": settings.llm_model_id,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "temperature": settings.llm_temperature
    }

    # 差异化覆盖
    if role == "hunter":
        config["model"] = settings.hunter_model
        config["api_key"] = settings.hunter_api_key or settings.llm_api_key
        config["base_url"] = settings.hunter_base_url or settings.llm_base_url
        config["temperature"] = settings.hunter_temperature

    elif role == "architect":
        config["model"] = settings.architect_model
        config["api_key"] = settings.architect_api_key or settings.llm_api_key
        config["base_url"] = settings.architect_base_url or settings.llm_base_url
        config["temperature"] = settings.architect_temperature

    elif role == "interviewer":
        config["model"] = settings.interviewer_model
        config["api_key"] = settings.interviewer_api_key or settings.llm_api_key
        config["base_url"] = settings.interviewer_base_url or settings.llm_base_url
        config["temperature"] = settings.interviewer_temperature

    return config

def reset_llm():
    """重置所有 LLM 实例 (通常用于测试或热重载配置)"""
    global _llm_instances
    _llm_instances.clear()
    print("♻️ 已重置所有 LLM 实例缓存")