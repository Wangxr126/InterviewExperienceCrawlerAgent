"""
为所有LLM调用添加max_tokens配置
避免输出截断导致JSON解析错误
"""

# 1. 添加配置到 config.py
config_additions = """
# 在全局LLM配置中添加
@property
def llm_max_tokens(self) -> int:
    return _get_int("LLM_MAX_TOKENS", 4096)

# 在Architect配置中添加
@property
def architect_max_tokens(self) -> int:
    return _get_int("ARCHITECT_MAX_TOKENS", 0) or self.llm_max_tokens

# 在Interviewer配置中添加
@property
def interviewer_max_tokens(self) -> int:
    return _get_int("INTERVIEWER_MAX_TOKENS", 0) or self.llm_max_tokens

# 在Extractor配置中添加
@property
def extractor_max_tokens(self) -> int:
    return _get_int("EXTRACTOR_MAX_TOKENS", 0) or self.llm_max_tokens

# 在Finetune配置中添加
@property
def finetune_max_tokens(self) -> int:
    return _get_int("FINETUNE_MAX_TOKENS", 0) or self.llm_max_tokens
"""

# 2. 添加配置到 .env
env_additions = """
# 在全局LLM配置中添加
LLM_MAX_TOKENS=4096              # 最大输出token数（避免截断）

# 在Architect配置中添加
ARCHITECT_MAX_TOKENS=            # 留空使用 LLM_MAX_TOKENS

# 在Interviewer配置中添加
INTERVIEWER_MAX_TOKENS=          # 留空使用 LLM_MAX_TOKENS

# 在Extractor配置中添加
EXTRACTOR_MAX_TOKENS=8192        # 题目提取可能需要更多token

# 在Finetune配置中添加
FINETUNE_MAX_TOKENS=             # 留空使用 LLM_MAX_TOKENS
"""

# 3. 修改 question_extractor.py
question_extractor_fix = """
# 在 _call_llm 函数中添加 max_tokens
temp = settings.extractor_temperature
max_tokens = settings.extractor_max_tokens  # 添加这行

try:
    resp = client.chat.completions.create(
        model=settings.llm_model_id,
        messages=messages,
        temperature=temp,
        timeout=timeout,
        max_tokens=max_tokens,  # 添加这行
        response_format={"type": "json_object"},
    )
except Exception:
    resp = client.chat.completions.create(
        model=settings.llm_model_id,
        messages=messages,
        temperature=temp,
        timeout=timeout,
        max_tokens=max_tokens,  # 添加这行
    )
"""

# 4. 修改 architect_tools.py
architect_tools_fix = """
# 在 _call_llm_json 函数中添加 max_tokens
payload = {
    "model": settings.architect_model,
    "messages": messages,
    "temperature": settings.architect_temperature,
    "max_tokens": settings.architect_max_tokens,  # 添加这行
    "response_format": {"type": "json_object"}
}
"""

print("=" * 80)
print("Max Tokens 配置方案")
print("=" * 80)
print("\n需要修改的文件：")
print("1. backend/config/config.py - 添加max_tokens配置属性")
print("2. .env - 添加max_tokens配置值")
print("3. backend/services/crawler/question_extractor.py - 使用max_tokens")
print("4. backend/tools/architect_tools.py - 使用max_tokens")
print("\n推荐配置：")
print("- LLM_MAX_TOKENS=4096 (全局默认)")
print("- EXTRACTOR_MAX_TOKENS=8192 (题目提取需要更多)")
print("- ARCHITECT_MAX_TOKENS= (留空使用全局)")
print("- INTERVIEWER_MAX_TOKENS= (留空使用全局)")
print("\n开始执行修改...")
