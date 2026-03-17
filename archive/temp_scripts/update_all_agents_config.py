"""
为所有Agent添加LOCAL和REMOTE配置
包括：Architect, Interviewer, Finetune
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改 Architect Agent 配置
architect_old = """    # ── 3. Architect Agent ────────────────────────────────────────
    @property
    def architect_provider(self) -> str:
        return _get("ARCHITECT_PROVIDER") or self.llm_provider

    @property
    def architect_model(self) -> str:
        return _get("ARCHITECT_MODEL") or self.llm_model_id

    @property
    def architect_api_key(self) -> str:
        return _get("ARCHITECT_API_KEY") or self.llm_api_key

    @property
    def architect_base_url(self) -> str:
        return _get("ARCHITECT_BASE_URL") or self.llm_base_url

    @property
    def architect_temperature(self) -> float:
        return _get_float("ARCHITECT_TEMPERATURE", 0.0)

    @property
    def architect_timeout(self) -> int:
        return _get_int("ARCHITECT_TIMEOUT", 0) or self.llm_timeout"""

architect_new = """    # ── 3. Architect Agent ────────────────────────────────────────
    @property
    def architect_mode(self) -> str:
        \"\"\"Architect使用模式：local/remote，留空则使用全局LLM_MODE\"\"\"
        return _get("ARCHITECT_MODE") or self.llm_mode

    # 本地配置
    @property
    def architect_local_provider(self) -> str:
        return _get("ARCHITECT_LOCAL_PROVIDER") or self.llm_local_provider

    @property
    def architect_local_model(self) -> str:
        return _get("ARCHITECT_LOCAL_MODEL") or self.llm_local_model

    @property
    def architect_local_base_url(self) -> str:
        return _get("ARCHITECT_LOCAL_BASE_URL") or self.llm_local_base_url

    @property
    def architect_local_timeout(self) -> int:
        return _get_int("ARCHITECT_LOCAL_TIMEOUT", 0) or self.llm_local_timeout

    # 远程配置
    @property
    def architect_remote_provider(self) -> str:
        return _get("ARCHITECT_REMOTE_PROVIDER") or self.llm_remote_provider

    @property
    def architect_remote_model(self) -> str:
        return _get("ARCHITECT_REMOTE_MODEL") or self.llm_remote_model

    @property
    def architect_remote_base_url(self) -> str:
        return _get("ARCHITECT_REMOTE_BASE_URL") or self.llm_remote_base_url

    @property
    def architect_remote_timeout(self) -> int:
        return _get_int("ARCHITECT_REMOTE_TIMEOUT", 0) or self.llm_remote_timeout

    # 当前使用的配置（根据mode选择）
    @property
    def architect_provider(self) -> str:
        return self.architect_local_provider if self.architect_mode == "local" else self.architect_remote_provider

    @property
    def architect_model(self) -> str:
        return self.architect_local_model if self.architect_mode == "local" else self.architect_remote_model

    @property
    def architect_api_key(self) -> str:
        local_key = _get("ARCHITECT_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = _get("ARCHITECT_REMOTE_API_KEY") or self.llm_remote_api_key
        return local_key if self.architect_mode == "local" else remote_key

    @property
    def architect_base_url(self) -> str:
        return self.architect_local_base_url if self.architect_mode == "local" else self.architect_remote_base_url

    @property
    def architect_timeout(self) -> int:
        return self.architect_local_timeout if self.architect_mode == "local" else self.architect_remote_timeout

    @property
    def architect_temperature(self) -> float:
        return _get_float("ARCHITECT_TEMPERATURE", 0.0)"""

content = content.replace(architect_old, architect_new)

# 2. 修改 Interviewer Agent 配置
interviewer_old = """    # ── 4. Interviewer Agent ──────────────────────────────────────
    @property
    def interviewer_provider(self) -> str:
        return _get("INTERVIEWER_PROVIDER") or self.llm_provider

    @property
    def interviewer_model(self) -> str:
        return _get("INTERVIEWER_MODEL") or self.llm_model_id

    @property
    def interviewer_api_key(self) -> str:
        return _get("INTERVIEWER_API_KEY") or self.llm_api_key

    @property
    def interviewer_base_url(self) -> str:
        return _get("INTERVIEWER_BASE_URL") or self.llm_base_url

    @property
    def interviewer_temperature(self) -> float:
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)

    @property
    def interviewer_timeout(self) -> int:
        return _get_int("INTERVIEWER_TIMEOUT", 0) or self.llm_timeout"""

interviewer_new = """    # ── 4. Interviewer Agent ──────────────────────────────────────
    @property
    def interviewer_mode(self) -> str:
        \"\"\"Interviewer使用模式：local/remote，留空则使用全局LLM_MODE\"\"\"
        return _get("INTERVIEWER_MODE") or self.llm_mode

    # 本地配置
    @property
    def interviewer_local_provider(self) -> str:
        return _get("INTERVIEWER_LOCAL_PROVIDER") or self.llm_local_provider

    @property
    def interviewer_local_model(self) -> str:
        return _get("INTERVIEWER_LOCAL_MODEL") or self.llm_local_model

    @property
    def interviewer_local_base_url(self) -> str:
        return _get("INTERVIEWER_LOCAL_BASE_URL") or self.llm_local_base_url

    @property
    def interviewer_local_timeout(self) -> int:
        return _get_int("INTERVIEWER_LOCAL_TIMEOUT", 0) or self.llm_local_timeout

    # 远程配置
    @property
    def interviewer_remote_provider(self) -> str:
        return _get("INTERVIEWER_REMOTE_PROVIDER") or self.llm_remote_provider

    @property
    def interviewer_remote_model(self) -> str:
        return _get("INTERVIEWER_REMOTE_MODEL") or self.llm_remote_model

    @property
    def interviewer_remote_base_url(self) -> str:
        return _get("INTERVIEWER_REMOTE_BASE_URL") or self.llm_remote_base_url

    @property
    def interviewer_remote_timeout(self) -> int:
        return _get_int("INTERVIEWER_REMOTE_TIMEOUT", 0) or self.llm_remote_timeout

    # 当前使用的配置（根据mode选择）
    @property
    def interviewer_provider(self) -> str:
        return self.interviewer_local_provider if self.interviewer_mode == "local" else self.interviewer_remote_provider

    @property
    def interviewer_model(self) -> str:
        return self.interviewer_local_model if self.interviewer_mode == "local" else self.interviewer_remote_model

    @property
    def interviewer_api_key(self) -> str:
        local_key = _get("INTERVIEWER_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = _get("INTERVIEWER_REMOTE_API_KEY") or self.llm_remote_api_key
        return local_key if self.interviewer_mode == "local" else remote_key

    @property
    def interviewer_base_url(self) -> str:
        return self.interviewer_local_base_url if self.interviewer_mode == "local" else self.interviewer_remote_base_url

    @property
    def interviewer_timeout(self) -> int:
        return self.interviewer_local_timeout if self.interviewer_mode == "local" else self.interviewer_remote_timeout

    @property
    def interviewer_temperature(self) -> float:
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)"""

content = content.replace(interviewer_old, interviewer_new)

# 3. 修改 Finetune LLM 配置
finetune_old = """    # ── 4.5 微调辅助大模型 ────────────────────────────────────────
    @property
    def finetune_llm_provider(self) -> str:
        return _get("FINETUNE_LLM_PROVIDER") or self.llm_provider

    @property
    def finetune_llm_model(self) -> str:
        return _get("FINETUNE_LLM_MODEL") or self.llm_model_id

    @property
    def finetune_llm_api_key(self) -> str:
        return _get("FINETUNE_LLM_API_KEY") or self.llm_api_key

    @property
    def finetune_llm_base_url(self) -> str:
        return _get("FINETUNE_LLM_BASE_URL") or self.llm_base_url

    @property
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)

    @property
    def finetune_llm_timeout(self) -> int:
        return _get_int("FINETUNE_LLM_TIMEOUT", 0) or self.llm_timeout"""

finetune_new = """    # ── 4.5 微调辅助大模型 ────────────────────────────────────────
    @property
    def finetune_mode(self) -> str:
        \"\"\"Finetune使用模式：local/remote，留空则使用全局LLM_MODE\"\"\"
        return _get("FINETUNE_MODE") or self.llm_mode

    # 本地配置
    @property
    def finetune_local_provider(self) -> str:
        return _get("FINETUNE_LOCAL_PROVIDER") or self.llm_local_provider

    @property
    def finetune_local_model(self) -> str:
        return _get("FINETUNE_LOCAL_MODEL") or self.llm_local_model

    @property
    def finetune_local_base_url(self) -> str:
        return _get("FINETUNE_LOCAL_BASE_URL") or self.llm_local_base_url

    @property
    def finetune_local_timeout(self) -> int:
        return _get_int("FINETUNE_LOCAL_TIMEOUT", 0) or self.llm_local_timeout

    # 远程配置
    @property
    def finetune_remote_provider(self) -> str:
        return _get("FINETUNE_REMOTE_PROVIDER") or self.llm_remote_provider

    @property
    def finetune_remote_model(self) -> str:
        return _get("FINETUNE_REMOTE_MODEL") or self.llm_remote_model

    @property
    def finetune_remote_base_url(self) -> str:
        return _get("FINETUNE_REMOTE_BASE_URL") or self.llm_remote_base_url

    @property
    def finetune_remote_timeout(self) -> int:
        return _get_int("FINETUNE_REMOTE_TIMEOUT", 0) or self.llm_remote_timeout

    # 当前使用的配置（根据mode选择）
    @property
    def finetune_llm_provider(self) -> str:
        return self.finetune_local_provider if self.finetune_mode == "local" else self.finetune_remote_provider

    @property
    def finetune_llm_model(self) -> str:
        return self.finetune_local_model if self.finetune_mode == "local" else self.finetune_remote_model

    @property
    def finetune_llm_api_key(self) -> str:
        local_key = _get("FINETUNE_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = _get("FINETUNE_REMOTE_API_KEY") or self.llm_remote_api_key
        return local_key if self.finetune_mode == "local" else remote_key

    @property
    def finetune_llm_base_url(self) -> str:
        return self.finetune_local_base_url if self.finetune_mode == "local" else self.finetune_remote_base_url

    @property
    def finetune_llm_timeout(self) -> int:
        return self.finetune_local_timeout if self.finetune_mode == "local" else self.finetune_remote_timeout

    @property
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)"""

content = content.replace(finetune_old, finetune_new)

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已为所有Agent添加LOCAL和REMOTE配置')
print('')
print('更新的Agent：')
print('  1. Architect Agent')
print('  2. Interviewer Agent')
print('  3. Finetune LLM')
print('')
print('每个Agent现在都有：')
print('  - XXX_MODE (使用模式，留空则用全局)')
print('  - XXX_LOCAL_* (本地配置)')
print('  - XXX_REMOTE_* (远程配置)')
print('  - 自动选择逻辑')
