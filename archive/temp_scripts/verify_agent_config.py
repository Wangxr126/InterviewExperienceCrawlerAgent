"""
Agent 配置验证和说明脚本
显示当前所有Agent的配置情况
"""

import sys
sys.path.insert(0, 'backend')

from backend.config.config import settings

print("=" * 80)
print("Agent 配置验证")
print("=" * 80)

# 1. 全局LLM配置
print("\n[1] 全局 LLM 配置（所有Agent的默认配置）")
print("-" * 80)
print(f"  Provider:    {settings.llm_provider}")
print(f"  Model:       {settings.llm_model_id}")
print(f"  Base URL:    {settings.llm_base_url}")
print(f"  Temperature: {settings.llm_temperature}")
print(f"  Timeout:     {settings.llm_timeout}s")

# 2. Interviewer Agent
print("\n[2] Interviewer Agent（面试官）")
print("-" * 80)
print(f"  职责: 自然对话、出题推荐、换个问法、笔记、掌握度查看")
print(f"  Model:       {settings.interviewer_model or '(使用全局)'}")
print(f"  Base URL:    {settings.interviewer_base_url or '(使用全局)'}")
print(f"  Temperature: {settings.interviewer_temperature}")
print(f"  Max Steps:   {getattr(settings, 'interviewer_max_steps', 8)}")
print(f"  实际使用:")
print(f"    - Model:   {settings.interviewer_model or settings.llm_model_id}")
print(f"    - URL:     {settings.interviewer_base_url or settings.llm_base_url}")

# 3. Architect Agent
print("\n[3] Architect Agent（知识架构师）")
print("-" * 80)
print(f"  职责: 元信息提取、结构化解析、语义查重、双写入库")
print(f"  Model:       {settings.architect_model or '(使用全局)'}")
print(f"  Base URL:    {settings.architect_base_url or '(使用全局)'}")
print(f"  Temperature: {settings.architect_temperature}")
print(f"  实际使用:")
print(f"    - Model:   {settings.architect_model or settings.llm_model_id}")
print(f"    - URL:     {settings.architect_base_url or settings.llm_base_url}")

# 4. Extractor（题目提取器）
print("\n[4] Question Extractor（题目提取器）")
print("-" * 80)
print(f"  职责: 从面经原文中提取结构化题目")
print(f"  Temperature: {settings.extractor_temperature}")
print(f"  Max Retries: {settings.extractor_max_retries}")
print(f"  实际使用:")
print(f"    - Model:   {settings.llm_model_id} (使用全局)")
print(f"    - URL:     {settings.llm_base_url} (使用全局)")

# 5. Finetune LLM
print("\n[5] Finetune LLM（微调辅助大模型）")
print("-" * 80)
print(f"  职责: 微调页面调用远程大模型辅助生成标注数据")
print(f"  Model:       {settings.finetune_llm_model or '(使用全局)'}")
print(f"  Base URL:    {settings.finetune_llm_base_url or '(使用全局)'}")
print(f"  Temperature: {settings.finetune_llm_temperature}")
print(f"  实际使用:")
print(f"    - Model:   {settings.finetune_llm_model or settings.llm_model_id}")
print(f"    - URL:     {settings.finetune_llm_base_url or settings.llm_base_url}")

# 6. OCR配置
print("\n[6] OCR 配置")
print("-" * 80)
print(f"  Method:      {settings.ocr_method}")
if settings.ocr_method == 'claude_vision':
    api_key = settings.anthropic_api_key
    if api_key and api_key != 'your_anthropic_api_key_here':
        print(f"  API Key:     {api_key[:20]}... (已配置)")
    else:
        print(f"  API Key:     (未配置)")
elif settings.ocr_method == 'mcp':
    print(f"  MCP Server:  {settings.mcp_ocr_server}")

# 7. 配置建议
print("\n" + "=" * 80)
print("配置建议")
print("=" * 80)

issues = []

# 检查全局配置
if not settings.llm_model_id:
    issues.append("全局 LLM_MODEL_ID 未配置")
if not settings.llm_base_url:
    issues.append("全局 LLM_BASE_URL 未配置")

# 检查OCR
if settings.ocr_method == 'claude_vision':
    if not settings.anthropic_api_key or settings.anthropic_api_key == 'your_anthropic_api_key_here':
        issues.append("OCR 使用 Claude Vision 但 ANTHROPIC_API_KEY 未配置")

# 检查温度设置
if settings.interviewer_temperature < 0.3:
    issues.append(f"Interviewer temperature ({settings.interviewer_temperature}) 过低，建议 0.5-0.7")
if settings.architect_temperature > 0.3:
    issues.append(f"Architect temperature ({settings.architect_temperature}) 过高，建议 0.0-0.2")

if issues:
    print("\n需要注意的问题:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
else:
    print("\n所有配置正常！")

print("\n" + "=" * 80)
print("配置优先级: Agent专属配置 > 全局配置")
print("=" * 80)
