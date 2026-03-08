"""
为所有Agent添加完整的配置项（provider和timeout）
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 为 Architect Agent 添加 provider 和 timeout
architect_old = """    # ── 3. Architect Agent ────────────────────────────────────────
    @property
    def architect_model(self) -> str:
        return _get("ARCHITECT_MODEL") or self.llm_model_id"""

architect_new = """    # ── 3. Architect Agent ────────────────────────────────────────
    @property
    def architect_provider(self) -> str:
        return _get("ARCHITECT_PROVIDER") or self.llm_provider

    @property
    def architect_model(self) -> str:
        return _get("ARCHITECT_MODEL") or self.llm_model_id"""

content = content.replace(architect_old, architect_new)

# 在 architect_temperature 后添加 timeout
architect_temp = """    @property
    def architect_temperature(self) -> float:
        return _get_float("ARCHITECT_TEMPERATURE", 0.0)

    # ── 4. Interviewer Agent"""

architect_temp_new = """    @property
    def architect_temperature(self) -> float:
        return _get_float("ARCHITECT_TEMPERATURE", 0.0)

    @property
    def architect_timeout(self) -> int:
        return _get_int("ARCHITECT_TIMEOUT") or self.llm_timeout

    # ── 4. Interviewer Agent"""

content = content.replace(architect_temp, architect_temp_new)

# 2. 为 Interviewer Agent 添加 provider 和 timeout
interviewer_old = """    # ── 4. Interviewer Agent ──────────────────────────────────────
    @property
    def interviewer_model(self) -> str:
        return _get("INTERVIEWER_MODEL") or self.llm_model_id"""

interviewer_new = """    # ── 4. Interviewer Agent ──────────────────────────────────────
    @property
    def interviewer_provider(self) -> str:
        return _get("INTERVIEWER_PROVIDER") or self.llm_provider

    @property
    def interviewer_model(self) -> str:
        return _get("INTERVIEWER_MODEL") or self.llm_model_id"""

content = content.replace(interviewer_old, interviewer_new)

# 在 interviewer_temperature 后添加 timeout
interviewer_temp = """    @property
    def interviewer_temperature(self) -> float:
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)

    # ── 4.5 微调辅助大模型"""

interviewer_temp_new = """    @property
    def interviewer_temperature(self) -> float:
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)

    @property
    def interviewer_timeout(self) -> int:
        return _get_int("INTERVIEWER_TIMEOUT") or self.llm_timeout

    # ── 4.5 微调辅助大模型"""

content = content.replace(interviewer_temp, interviewer_temp_new)

# 3. 为 Finetune LLM 添加 provider 和 timeout
finetune_old = """    # ── 4.5 微调辅助大模型 ────────────────────────────────────────
    @property
    def finetune_llm_model(self) -> str:
        return _get("FINETUNE_LLM_MODEL") or self.llm_model_id"""

finetune_new = """    # ── 4.5 微调辅助大模型 ────────────────────────────────────────
    @property
    def finetune_llm_provider(self) -> str:
        return _get("FINETUNE_LLM_PROVIDER") or self.llm_provider

    @property
    def finetune_llm_model(self) -> str:
        return _get("FINETUNE_LLM_MODEL") or self.llm_model_id"""

content = content.replace(finetune_old, finetune_new)

# 在 finetune_llm_temperature 后添加 timeout
finetune_temp = """    @property
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)

    # ── 4.6 爬虫/题目提取"""

finetune_temp_new = """    @property
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)

    @property
    def finetune_llm_timeout(self) -> int:
        return _get_int("FINETUNE_LLM_TIMEOUT") or self.llm_timeout

    # ── 4.6 爬虫/题目提取"""

content = content.replace(finetune_temp, finetune_temp_new)

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已为所有Agent添加完整配置项')
print('')
print('添加的配置项：')
print('  1. architect_provider')
print('  2. architect_timeout')
print('  3. interviewer_provider')
print('  4. interviewer_timeout')
print('  5. finetune_llm_provider')
print('  6. finetune_llm_timeout')
