"""
为所有Agent添加LOCAL和REMOTE配置
方案B：简化方案，手动切换
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改全局LLM配置，添加LOCAL和REMOTE
global_old = """    # ── 1. 全局 LLM ──────────────────────────────────────────────
    @property
    def llm_provider(self) -> str:
        return _get("LLM_PROVIDER", "volcengine")

    @property
    def llm_model_id(self) -> str:
        return _get("LLM_MODEL_ID")

    @property
    def llm_api_key(self) -> str:
        return _get("LLM_API_KEY")

    @property
    def llm_base_url(self) -> str:
        return _get("LLM_BASE_URL")

    @property
    def llm_timeout(self) -> int:
        return _get_int("LLM_TIMEOUT", 180)

    @property
    def llm_temperature(self) -> float:
        return _get_float("LLM_TEMPERATURE", 0.3)"""

global_new = """    # ── 1. 全局 LLM ──────────────────────────────────────────────
    # 使用模式：LOCAL（本地Ollama）或 REMOTE（云端API）
    @property
    def llm_mode(self) -> str:
        \"\"\"LLM使用模式：local（本地）或 remote（远程），默认local\"\"\"
        return _get("LLM_MODE", "local").lower()

    # ── 1.1 本地配置（Ollama）──
    @property
    def llm_local_provider(self) -> str:
        return _get("LLM_LOCAL_PROVIDER", "ollama")

    @property
    def llm_local_model(self) -> str:
        return _get("LLM_LOCAL_MODEL", "qwen3:4b")

    @property
    def llm_local_api_key(self) -> str:
        return _get("LLM_LOCAL_API_KEY", "ollama")

    @property
    def llm_local_base_url(self) -> str:
        return _get("LLM_LOCAL_BASE_URL", "http://localhost:11434/v1")

    @property
    def llm_local_timeout(self) -> int:
        return _get_int("LLM_LOCAL_TIMEOUT", 60)

    # ── 1.2 远程配置（云端API）──
    @property
    def llm_remote_provider(self) -> str:
        return _get("LLM_REMOTE_PROVIDER", "volcengine")

    @property
    def llm_remote_model(self) -> str:
        return _get("LLM_REMOTE_MODEL")

    @property
    def llm_remote_api_key(self) -> str:
        return _get("LLM_REMOTE_API_KEY")

    @property
    def llm_remote_base_url(self) -> str:
        return _get("LLM_REMOTE_BASE_URL")

    @property
    def llm_remote_timeout(self) -> int:
        return _get_int("LLM_REMOTE_TIMEOUT", 300)

    # ── 1.3 当前使用的配置（根据mode自动选择）──
    @property
    def llm_provider(self) -> str:
        return self.llm_local_provider if self.llm_mode == "local" else self.llm_remote_provider

    @property
    def llm_model_id(self) -> str:
        return self.llm_local_model if self.llm_mode == "local" else self.llm_remote_model

    @property
    def llm_api_key(self) -> str:
        return self.llm_local_api_key if self.llm_mode == "local" else self.llm_remote_api_key

    @property
    def llm_base_url(self) -> str:
        return self.llm_local_base_url if self.llm_mode == "local" else self.llm_remote_base_url

    @property
    def llm_timeout(self) -> int:
        return self.llm_local_timeout if self.llm_mode == "local" else self.llm_remote_timeout

    @property
    def llm_temperature(self) -> float:
        return _get_float("LLM_TEMPERATURE", 0.3)"""

content = content.replace(global_old, global_new)

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已修改 config.py')
print('')
print('添加的配置：')
print('  1. LLM_MODE - 使用模式（local/remote）')
print('  2. LLM_LOCAL_* - 本地配置（6项）')
print('  3. LLM_REMOTE_* - 远程配置（6项）')
print('  4. 自动选择逻辑 - 根据mode选择配置')
print('')
print('使用方式：')
print('  - 修改 LLM_MODE=local  使用本地Ollama')
print('  - 修改 LLM_MODE=remote 使用远程API')
