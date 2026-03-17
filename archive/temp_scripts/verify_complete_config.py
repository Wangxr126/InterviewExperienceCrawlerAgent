"""
验证所有Agent配置的完整性
"""

import sys
sys.path.insert(0, 'backend')

from backend.config.config import settings

print("=" * 80)
print("Agent 配置完整性验证")
print("=" * 80)

# 定义每个Agent必须有的配置项
REQUIRED_CONFIG = ['provider', 'model', 'api_key', 'base_url', 'timeout', 'temperature']

agents = {
    'Global LLM': {
        'provider': settings.llm_provider,
        'model': settings.llm_model_id,
        'api_key': settings.llm_api_key,
        'base_url': settings.llm_base_url,
        'timeout': settings.llm_timeout,
        'temperature': settings.llm_temperature,
    },
    'Architect': {
        'provider': settings.architect_provider,
        'model': settings.architect_model or settings.llm_model_id,
        'api_key': settings.architect_api_key or settings.llm_api_key,
        'base_url': settings.architect_base_url or settings.llm_base_url,
        'timeout': settings.architect_timeout,
        'temperature': settings.architect_temperature,
    },
    'Interviewer': {
        'provider': settings.interviewer_provider,
        'model': settings.interviewer_model or settings.llm_model_id,
        'api_key': settings.interviewer_api_key or settings.llm_api_key,
        'base_url': settings.interviewer_base_url or settings.llm_base_url,
        'timeout': settings.interviewer_timeout,
        'temperature': settings.interviewer_temperature,
    },
    'Finetune': {
        'provider': settings.finetune_llm_provider,
        'model': settings.finetune_llm_model or settings.llm_model_id,
        'api_key': settings.finetune_llm_api_key or settings.llm_api_key,
        'base_url': settings.finetune_llm_base_url or settings.llm_base_url,
        'timeout': settings.finetune_llm_timeout,
        'temperature': settings.finetune_llm_temperature,
    },
}

all_complete = True

for agent_name, config in agents.items():
    print(f"\n[{agent_name}]")
    print("-" * 80)
    
    missing = []
    for key in REQUIRED_CONFIG:
        value = config.get(key)
        status = "OK" if value else "MISSING"
        
        if not value:
            missing.append(key)
            all_complete = False
        
        # 显示值（隐藏API Key）
        if key == 'api_key' and value:
            display_value = f"{value[:10]}..." if len(value) > 10 else value
        else:
            display_value = value
        
        print(f"  {key:12s}: {display_value} [{status}]")
    
    if missing:
        print(f"  WARNING: Missing {', '.join(missing)}")

print("\n" + "=" * 80)
if all_complete:
    print("SUCCESS: All agents have complete configuration!")
else:
    print("WARNING: Some agents have missing configuration!")
print("=" * 80)

# 配置建议
print("\nConfiguration Recommendations:")
print("-" * 80)

recommendations = []

# 检查全局配置
if not settings.llm_model_id:
    recommendations.append("Set LLM_MODEL_ID in .env")
if not settings.llm_base_url:
    recommendations.append("Set LLM_BASE_URL in .env")

# 检查温度设置
if settings.interviewer_temperature < 0.3:
    recommendations.append(f"Interviewer temperature ({settings.interviewer_temperature}) is too low, recommend 0.5-0.7")
if settings.architect_temperature > 0.3:
    recommendations.append(f"Architect temperature ({settings.architect_temperature}) is too high, recommend 0.0-0.2")

# 检查超时设置
if settings.llm_timeout < 60:
    recommendations.append(f"Global timeout ({settings.llm_timeout}s) might be too short")

if recommendations:
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec}")
else:
    print("  All configurations look good!")

print("\n" + "=" * 80)
print("Configuration Priority: Agent-specific > Global > Default")
print("=" * 80)
