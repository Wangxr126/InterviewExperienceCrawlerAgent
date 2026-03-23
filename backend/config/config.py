"""
配置管理 —— 纯环境变量读取器
所有值均来自 .env 文件（项目根目录），不在此处硬编码。
修改配置请直接编辑 /.env 文件。
"""
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_path(p: str) -> str:
    """相对路径转为基于项目根的绝对路径"""
    if not p:
        return p
    path = Path(p)
    return str(path) if path.is_absolute() else str(_PROJECT_ROOT / path)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_nonempty(key: str) -> bool:
    """环境变量存在且非空白（# 注释行不会被 dotenv 加载，等价于「未设置」）。"""
    v = os.environ.get(key)
    return bool(v and str(v).strip())


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, ""))
    except (ValueError, TypeError):
        return default


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, ""))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


def _get_list(key: str, default: str = "") -> list:
    """逗号分隔的字符串 → list，去掉空项"""
    raw = os.environ.get(key, default).strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def _remote_chain_with_fallback(
    primary_model: str,
    primary_key: str,
    primary_base: str,
    primary_timeout: int,
    fallback_json_raw: str,
) -> List[Dict[str, Any]]:
    """主端点 + *._FALLBACK_MODELS（单行 JSON 数组）→ 统一端点列表，格式与 MINER_STAGE2_FALLBACK_MODELS 一致。"""
    pm = (primary_model or "").strip()
    pb = (primary_base or "").strip().rstrip("/")
    pk = (primary_key or "").strip()
    if not pm or not pb:
        return []
    to = int(primary_timeout or 0) or 120
    result: List[Dict[str, Any]] = [
        {"model": pm, "api_key": pk or "sk-dummy", "base_url": pb, "timeout": to}
    ]
    raw = (fallback_json_raw or "").strip()
    if not raw:
        return result
    try:
        fallbacks = json.loads(raw)
        if not isinstance(fallbacks, list):
            return result
        for item in fallbacks:
            if not isinstance(item, dict) or not item.get("model"):
                continue
            item_base = str(item.get("base_url") or pb).strip().rstrip("/")
            item_to = to
            if item.get("timeout") is not None:
                try:
                    item_to = int(item["timeout"])
                except (TypeError, ValueError):
                    pass
            result.append(
                {
                    "model": str(item["model"]),
                    "api_key": str(item.get("api_key") or pk or "sk-dummy"),
                    "base_url": item_base,
                    "timeout": item_to,
                }
            )
    except json.JSONDecodeError:
        pass
    return result


class _Settings:
    """运行时只读配置对象（属性懒加载，确保 load_dotenv 先执行）"""

    # ── 1. 全局 LLM ──────────────────────────────────────────────
    # 使用模式：LOCAL（本地Ollama）或 REMOTE（云端API）
    @property
    def llm_mode(self) -> str:
        """LLM使用模式：local（本地）或 remote（远程），默认local"""
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
        return _get_int("LLM_LOCAL_TIMEOUT", 120)  # 默认 120s，Function Calling 等场景需更长时间

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

    @property
    def llm_remote_models(self) -> List[Dict[str, Any]]:
        """全局 LLM_MODE=remote 时：主端点 + LLM_REMOTE_FALLBACK_MODELS（练习对话等）。"""
        if self.llm_mode != "remote":
            return []
        return _remote_chain_with_fallback(
            self.llm_remote_model,
            self.llm_remote_api_key,
            self.llm_remote_base_url,
            self.llm_remote_timeout,
            _get("LLM_REMOTE_FALLBACK_MODELS", ""),
        )

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
        return _get_float("LLM_TEMPERATURE", 0.3)

    @property
    def llm_max_tokens(self) -> int:
        """最大输出token数，避免截断导致JSON解析错误"""
        return _get_int("LLM_MAX_TOKENS", 4096)

    @property
    def llm_warmup_enabled(self) -> bool:
        """启动时是否预热 LLM（解决 Ollama/云端 冷启动首请求慢或无响应）"""
        return _get_bool("LLM_WARMUP_ENABLED", True)

    @property
    def warmup_embedding_rerank_ocr_enabled(self) -> bool:
        """是否预热 Embedding/Reranker/OCR（仅题目提取可设为 false 加快启动）"""
        return _get_bool("WARMUP_EMBEDDING_RERANK_OCR", True)

    # ── 3. Architect Agent ────────────────────────────────────────
    @property
    def architect_mode(self) -> str:
        """Architect使用模式：local/remote，留空则使用全局LLM_MODE"""
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
    def knowledge_manager_model(self) -> str:
        return self.architect_local_model if self.architect_mode == "local" else self.architect_remote_model

    @property
    def knowledge_manager_api_key(self) -> str:
        local_key = _get("ARCHITECT_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = _get("ARCHITECT_REMOTE_API_KEY") or self.llm_remote_api_key
        return local_key if self.architect_mode == "local" else remote_key

    @property
    def knowledge_manager_base_url(self) -> str:
        return self.architect_local_base_url if self.architect_mode == "local" else self.architect_remote_base_url

    @property
    def architect_timeout(self) -> int:
        return self.architect_local_timeout if self.architect_mode == "local" else self.architect_remote_timeout

    @property
    def knowledge_manager_temperature(self) -> float:
        return _get_float("KNOWLEDGE_MANAGER_TEMPERATURE", 0.0)

    @property
    def knowledge_manager_max_tokens(self) -> int:
        return _get_int("KNOWLEDGE_MANAGER_MAX_TOKENS", 0) or self.llm_max_tokens

    @property
    def architect_model(self) -> str:
        """与 knowledge_manager_model 相同（兼容 knowledge_tools 等旧引用）。"""
        return self.knowledge_manager_model

    @property
    def architect_temperature(self) -> float:
        return self.knowledge_manager_temperature

    @property
    def architect_max_tokens(self) -> int:
        return self.knowledge_manager_max_tokens

    @property
    def architect_remote_models(self) -> List[Dict[str, Any]]:
        """Architect / 知识管理 JSON 调用：主端点 + ARCHITECT_REMOTE_FALLBACK_MODELS。"""
        if self.architect_mode == "local":
            m = (self.architect_local_model or "").strip()
            b = (self.architect_local_base_url or "").strip().rstrip("/")
            if not m or not b:
                return []
            lk = _get("ARCHITECT_LOCAL_API_KEY") or self.llm_local_api_key or "ollama"
            return [
                {
                    "model": m,
                    "api_key": lk,
                    "base_url": b,
                    "timeout": self.architect_local_timeout,
                }
            ]
        return _remote_chain_with_fallback(
            self.architect_remote_model,
            (_get("ARCHITECT_REMOTE_API_KEY") or self.llm_remote_api_key),
            self.architect_remote_base_url,
            self.architect_remote_timeout,
            _get("ARCHITECT_REMOTE_FALLBACK_MODELS", ""),
        )

    # ── 4. Interviewer Agent ──────────────────────────────────────
    @property
    def interviewer_mode(self) -> str:
        """Interviewer使用模式：local/remote，留空则使用全局LLM_MODE"""
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
        return _get_int("INTERVIEWER_LOCAL_TIMEOUT", 0) or max(120, self.llm_local_timeout)  # 至少 120s，避免 Function Calling 超时

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
        return _get_int("INTERVIEWER_REMOTE_TIMEOUT", 0) or max(180, self.llm_remote_timeout)  # 至少 180s，云端 API 可能较慢

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
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)

    @property
    def interviewer_max_tokens(self) -> int:
        return _get_int("INTERVIEWER_MAX_TOKENS", 0) or self.llm_max_tokens

    @property
    def interviewer_remote_models(self) -> List[Dict[str, Any]]:
        """面试官：local 单端点；remote 时主端点 + INTERVIEWER_REMOTE_FALLBACK_MODELS。"""
        if self.interviewer_mode == "local":
            m = (self.interviewer_local_model or "").strip()
            b = (self.interviewer_local_base_url or "").strip().rstrip("/")
            if not m or not b:
                return []
            return [
                {
                    "model": m,
                    "api_key": (_get("INTERVIEWER_LOCAL_API_KEY") or self.llm_local_api_key or "ollama"),
                    "base_url": b,
                    "timeout": self.interviewer_local_timeout,
                }
            ]
        return _remote_chain_with_fallback(
            self.interviewer_remote_model,
            self.interviewer_api_key,
            self.interviewer_remote_base_url,
            self.interviewer_remote_timeout,
            _get("INTERVIEWER_REMOTE_FALLBACK_MODELS", ""),
        )

    @property
    def interviewer_history_max_messages(self) -> int:
        """注入 LLM 的对话历史最大条数，默认 20"""
        return _get_int("INTERVIEWER_HISTORY_MAX_MESSAGES", 20)

    @property
    def interviewer_streamable(self) -> bool:
        """是否对 /api/chat/stream 做 token 级 SSE 推送。
        为 false 时仍完整执行 arun_stream（推理链、工具、最终正文与 agent_finish 内 thinking 均不删减），
        仅在整轮结束后按原事件顺序一次性下发 SSE。
        支持环境变量：INTERVIEWER_STREAMABLE（推荐）或 INTERVIEWER_STREAMBLE（兼容拼写 streamble）。
        """
        raw = (_get("INTERVIEWER_STREAMABLE") or _get("INTERVIEWER_STREAMBLE")).lower()
        if raw in ("0", "false", "no"):
            return False
        if raw in ("1", "true", "yes"):
            return True
        return True

    @property
    def interviewer_session_enabled(self) -> bool:
        """Interviewer 会话持久化开关。"""
        return _get_bool("INTERVIEWER_SESSION_ENABLED", True)

    @property
    def interviewer_session_auto_save_enabled(self) -> bool:
        """Interviewer 自动保存开关。"""
        return _get_bool("INTERVIEWER_SESSION_AUTO_SAVE_ENABLED", True)

    @property
    def interviewer_session_auto_save_interval(self) -> int:
        """Interviewer 自动保存间隔（每 N 条消息）。"""
        return max(1, _get_int("INTERVIEWER_SESSION_AUTO_SAVE_INTERVAL", 2))

    @property
    def interviewer_circuit_enabled(self) -> bool:
        """Interviewer 工具熔断开关。"""
        return _get_bool("INTERVIEWER_CIRCUIT_ENABLED", True)

    @property
    def interviewer_circuit_failure_threshold(self) -> int:
        """Interviewer 工具连续失败多少次后熔断。"""
        return max(1, _get_int("INTERVIEWER_CIRCUIT_FAILURE_THRESHOLD", 3))

    @property
    def interviewer_circuit_recovery_timeout(self) -> int:
        """Interviewer 工具熔断后恢复时间（秒）。"""
        return max(1, _get_int("INTERVIEWER_CIRCUIT_RECOVERY_TIMEOUT", 300))

    @property
    def enable_smart_compression(self) -> bool:
        """是否启用智能摘要（需额外 LLM 调用），默认 False"""
        return _get_bool("ENABLE_SMART_COMPRESSION", False)

    @property
    def context_window(self) -> int:
        """上下文窗口大小（HelloAgents Config）。"""
        return _get_int("CONTEXT_WINDOW", 128000)

    @property
    def compression_threshold(self) -> float:
        """历史压缩阈值（0~1）。"""
        return _get_float("COMPRESSION_THRESHOLD", 0.8)

    @property
    def min_retain_rounds(self) -> int:
        """压缩后保留最近完整对话轮次。"""
        return _get_int("MIN_RETAIN_ROUNDS", 10)

    @property
    def summary_llm_provider(self) -> str:
        """历史摘要模型 provider（固定远程，默认复用全局远程 provider）。"""
        return _get("SUMMARY_LLM_PROVIDER") or self.llm_remote_provider

    @property
    def summary_llm_model(self) -> str:
        """历史摘要模型（固定远程）。"""
        return _get("SUMMARY_LLM_MODEL")

    @property
    def summary_llm_api_key(self) -> str:
        """历史摘要模型 API Key（固定远程）。"""
        return _get("SUMMARY_LLM_API_KEY") or self.llm_remote_api_key

    @property
    def summary_llm_base_url(self) -> str:
        """历史摘要模型 Base URL（固定远程）。"""
        return _get("SUMMARY_LLM_BASE_URL") or self.llm_remote_base_url

    @property
    def summary_llm_timeout(self) -> int:
        """历史摘要模型超时（秒）。"""
        return _get_int("SUMMARY_LLM_TIMEOUT", 0) or self.llm_remote_timeout

    @property
    def summary_max_tokens(self) -> int:
        """历史摘要最大输出 token。"""
        return _get_int("SUMMARY_MAX_TOKENS", 800)

    @property
    def summary_temperature(self) -> float:
        """历史摘要温度。"""
        return _get_float("SUMMARY_TEMPERATURE", 0.3)

    @property
    def agent_trace_enabled(self) -> bool:
        """是否启用 Agent trace。"""
        return _get_bool("AGENT_TRACE_ENABLED", True)

    @property
    def agent_trace_sanitize(self) -> bool:
        """是否对 trace 做脱敏。"""
        return _get_bool("AGENT_TRACE_SANITIZE", True)

    @property
    def agent_tool_output_max_lines(self) -> int:
        """工具输出最大行数（超限截断）。"""
        return _get_int("AGENT_TOOL_OUTPUT_MAX_LINES", 500)

    @property
    def agent_tool_output_max_bytes(self) -> int:
        """工具输出最大字节（超限截断）。"""
        return _get_int("AGENT_TOOL_OUTPUT_MAX_BYTES", 20480)

    @property
    def agent_tool_output_truncate_direction(self) -> str:
        """工具输出截断方向：head / tail / head_tail。"""
        direction = _get("AGENT_TOOL_OUTPUT_TRUNCATE_DIRECTION", "head").lower().strip()
        return direction if direction in ("head", "tail", "head_tail") else "head"

    # ── 4.5 微调辅助大模型 ────────────────────────────────────────
    @property
    def finetune_mode(self) -> str:
        """Finetune使用模式：local/remote，留空则使用全局LLM_MODE"""
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
    def finetune_remote_models(self) -> List[Dict[str, Any]]:
        """微调「AI 辅助标注」等：主端点 + FINETUNE_REMOTE_FALLBACK_MODELS。"""
        if self.finetune_mode == "local":
            m = (self.finetune_local_model or "").strip()
            b = (self.finetune_local_base_url or "").strip().rstrip("/")
            if not m or not b:
                return []
            return [
                {
                    "model": m,
                    "api_key": (_get("FINETUNE_LOCAL_API_KEY") or self.llm_local_api_key or "ollama"),
                    "base_url": b,
                    "timeout": self.finetune_local_timeout,
                }
            ]
        return _remote_chain_with_fallback(
            self.finetune_remote_model,
            self.finetune_llm_api_key,
            self.finetune_llm_base_url,
            self.finetune_remote_timeout,
            _get("FINETUNE_REMOTE_FALLBACK_MODELS", ""),
        )

    @property
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)

    @property
    def finetune_llm_max_tokens(self) -> int:
        return _get_int("FINETUNE_LLM_MAX_TOKENS", 0) or self.llm_max_tokens

    @property
    def compare_finetuned_ollama_model(self) -> str:
        """模型对比页「本地微调」槽位：Ollama 中已导入的模型名（如合并 LoRA 后的 GGUF），留空则该预设未就绪"""
        return (_get("COMPARE_FINETUNED_OLLAMA_MODEL") or "").strip()

    # ── 4.6 Miner Agent（题目提取器）──────────────────────────────────
    @property
    def miner_mode(self) -> str:
        """Miner 使用模式：local | remote | two_stage（两阶段同步：Stage1 粗提 + Stage2 精加工），留空则 LLM_MODE。"""
        raw = (_get("MINER_MODE") or self.llm_mode or "local").strip().lower()
        if raw == "two_stage":
            return "two_stage"
        if raw in ("remote", "local"):
            return raw
        return "local"

    # 本地配置
    @property
    def miner_local_provider(self) -> str:
        return _get("MINER_LOCAL_PROVIDER") or self.llm_local_provider

    @property
    def miner_local_model(self) -> str:
        return _get("MINER_LOCAL_MODEL") or self.llm_local_model

    @property
    def miner_local_base_url(self) -> str:
        return _get("MINER_LOCAL_BASE_URL") or self.llm_local_base_url

    @property
    def miner_local_timeout(self) -> int:
        return _get_int("MINER_LOCAL_TIMEOUT", 0) or self.llm_local_timeout

    # 远程配置
    @property
    def miner_remote_provider(self) -> str:
        return _get("MINER_REMOTE_PROVIDER") or self.llm_remote_provider

    @property
    def miner_remote_model(self) -> str:
        return _get("MINER_REMOTE_MODEL") or self.llm_remote_model

    @property
    def miner_remote_base_url(self) -> str:
        # two_stage Stage1 可与 Stage2 共用火山 Ark：未单独配 MINER_REMOTE_BASE_URL 时回退 Stage2
        return (
            _get("MINER_REMOTE_BASE_URL")
            or self.llm_remote_base_url
            or _get("MINER_STAGE2_BASE_URL")
        )

    @property
    def miner_remote_timeout(self) -> int:
        return _get_int("MINER_REMOTE_TIMEOUT", 0) or self.llm_remote_timeout

    @property
    def miner_remote_api_key(self) -> str:
        # 未单独配 MINER_REMOTE_API_KEY 时可用 Stage2 / 全局远程 Key（同一 Ark 账号时常共用）
        return _get("MINER_REMOTE_API_KEY") or self.llm_remote_api_key or _get("MINER_STAGE2_API_KEY")

    @property
    def miner_remote_models(self) -> List[Dict[str, Any]]:
        """
        单阶段 remote / 直连降级 LLM：主端点 MINER_REMOTE_* + MINER_REMOTE_FALLBACK_MODELS（JSON 数组）。
        格式同 MINER_STAGE2_FALLBACK_MODELS：[{"model":"...","api_key":"..." , "base_url":"..." 可选, "timeout": 可选}]
        local / 未配置 base 时返回空列表。
        """
        if self.miner_mode == "local":
            m = (self.miner_local_model or "").strip()
            b = (self.miner_local_base_url or "").strip().rstrip("/")
            if not m or not b:
                return []
            to = self.miner_local_timeout
            _lk = (_get("MINER_LOCAL_API_KEY") or self.llm_local_api_key or "ollama").strip() or "ollama"
            return [
                {
                    "model": m,
                    "api_key": _lk,
                    "base_url": b,
                    "timeout": to,
                }
            ]
        return _remote_chain_with_fallback(
            self.miner_remote_model,
            self.miner_remote_api_key,
            self.miner_remote_base_url,
            self.miner_remote_timeout,
            _get("MINER_REMOTE_FALLBACK_MODELS", ""),
        )

    @property
    def miner_remote_enable_thinking(self) -> bool:
        """
        通义 DashScope 等：非流式 chat.completions + tools 时若默认开启思考链会报
        enable_thinking must be set to false for non-streaming calls。
        默认 false：在 Stage1 请求 extra_body 中传 enable_thinking=false。
        设为 true 则不传该字段（对接严格 OpenAI 官方、未知参数即报错时可试）。
        """
        return _get_bool("MINER_REMOTE_ENABLE_THINKING", False)

    @property
    def miner_remote_extra_body_json(self) -> Dict[str, Any]:
        """可选 JSON，合并进 Stage1 的 chat.completions extra_body（后者覆盖同名键）"""
        raw = _get("MINER_REMOTE_EXTRA_BODY_JSON")
        if not raw:
            return {}
        try:
            o = json.loads(raw)
            return o if isinstance(o, dict) else {}
        except json.JSONDecodeError:
            return {}

    @property
    def miner_remote_stage1_extra_body(self) -> Dict[str, Any]:
        """two_stage Stage1（Miner ReAct 非流式工具调用）附加给 OpenAI SDK 的 extra_body"""
        body: Dict[str, Any] = {}
        if not self.miner_remote_enable_thinking:
            body["enable_thinking"] = False
        body.update(self.miner_remote_extra_body_json)
        return body

    # ── two_stage：Stage1 与 Stage2 解耦（粗提取单独选本地或远程 + 远程多 Key）────────
    @property
    def miner_stage1_mode(self) -> str:
        """仅 MINER_MODE=two_stage 时生效：Stage1 走 local 还是 remote。
        未设置时默认 remote（与旧版「Stage1 用 MINER_REMOTE_*」一致）。"""
        raw = (_get("MINER_STAGE1_MODE") or "").strip().lower()
        if raw in ("local", "remote"):
            return raw
        return "remote"

    @property
    def miner_stage1_local_model(self) -> str:
        return (_get("MINER_STAGE1_LOCAL_MODEL") or self.miner_local_model or "").strip()

    @property
    def miner_stage1_local_base_url(self) -> str:
        return (_get("MINER_STAGE1_LOCAL_BASE_URL") or self.miner_local_base_url or "").strip().rstrip("/")

    @property
    def miner_stage1_local_api_key(self) -> str:
        return (_get("MINER_STAGE1_LOCAL_API_KEY") or _get("MINER_LOCAL_API_KEY") or self.llm_local_api_key or "").strip()

    @property
    def miner_stage1_local_timeout(self) -> int:
        v = _get_int("MINER_STAGE1_LOCAL_TIMEOUT", 0)
        return v if v > 0 else self.miner_local_timeout

    @property
    def miner_stage1_remote_model(self) -> str:
        """Stage1 远程主端点模型；未单独配置时回退 MINER_REMOTE_MODEL。"""
        return (_get("MINER_STAGE1_REMOTE_MODEL") or self.miner_remote_model or "").strip()

    @property
    def miner_stage1_remote_base_url(self) -> str:
        """Stage1 远程主端点 base；未单独配置时回退 MINER_REMOTE_BASE_URL（含 Stage2 回退链）。"""
        explicit = (_get("MINER_STAGE1_REMOTE_BASE_URL") or "").strip().rstrip("/")
        return explicit or self.miner_remote_base_url

    @property
    def miner_stage1_remote_api_key(self) -> str:
        """Stage1 远程主端点 Key；未单独配置时回退 MINER_REMOTE_API_KEY。"""
        return (_get("MINER_STAGE1_REMOTE_API_KEY") or self.miner_remote_api_key or "").strip()

    @property
    def miner_stage1_remote_timeout(self) -> int:
        v = _get_int("MINER_STAGE1_REMOTE_TIMEOUT", 0)
        return v if v > 0 else self.miner_remote_timeout

    @property
    def miner_stage1_remote_explicit_in_env(self) -> bool:
        """是否有 MINER_STAGE1_REMOTE_MODEL/API_KEY/BASE_URL 任一在环境中显式设置（非注释）。"""
        return any(
            _env_nonempty(k)
            for k in (
                "MINER_STAGE1_REMOTE_MODEL",
                "MINER_STAGE1_REMOTE_API_KEY",
                "MINER_STAGE1_REMOTE_BASE_URL",
            )
        )

    @property
    def miner_stage1_fallback_models_in_env(self) -> bool:
        return _env_nonempty("MINER_STAGE1_FALLBACK_MODELS")

    @property
    def miner_stage1_models(self) -> List[Dict[str, Any]]:
        """two_stage 时 Stage1 端点链：local 仅 1 个；remote 为主 + MINER_STAGE1_FALLBACK_MODELS。
        每项含 model, api_key, base_url, kind(local|remote), timeout。"""
        if (self.miner_mode or "").lower() != "two_stage":
            return []
        if self.miner_stage1_mode == "local":
            m, b = self.miner_stage1_local_model, self.miner_stage1_local_base_url
            if not m or not b:
                return []
            return [
                {
                    "model": m,
                    "api_key": self.miner_stage1_local_api_key or "ollama",
                    "base_url": b,
                    "kind": "local",
                    "timeout": self.miner_stage1_local_timeout,
                }
            ]
        pm = self.miner_stage1_remote_model
        pb = self.miner_stage1_remote_base_url
        pk = self.miner_stage1_remote_api_key
        if not pm or not pb:
            return []
        to = self.miner_stage1_remote_timeout
        chain = _remote_chain_with_fallback(pm, pk, pb, to, _get("MINER_STAGE1_FALLBACK_MODELS", ""))
        return [{**d, "kind": "remote", "base_url": (d.get("base_url") or "").rstrip("/")} for d in chain]

    # 当前使用的配置（根据mode选择）
    @property
    def miner_provider(self) -> str:
        if self.miner_mode == "two_stage":
            return f"two_stage/{self.miner_stage1_mode}"
        return self.miner_local_provider if self.miner_mode == "local" else self.miner_remote_provider

    @property
    def miner_model(self) -> str:
        if self.miner_mode == "two_stage":
            s1 = self.miner_stage1_models
            if s1:
                return str(s1[0].get("model") or "").strip() or "two_stage"
            return "two_stage"
        return self.miner_local_model if self.miner_mode == "local" else self.miner_remote_model

    @property
    def miner_api_key(self) -> str:
        local_key = _get("MINER_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = self.miner_remote_api_key
        if self.miner_mode == "two_stage":
            if self.miner_stage1_mode == "local":
                return self.miner_stage1_local_api_key or local_key
            return self.miner_stage1_remote_api_key or remote_key
        return local_key if self.miner_mode == "local" else remote_key

    @property
    def miner_base_url(self) -> str:
        if self.miner_mode == "two_stage":
            if self.miner_stage1_mode == "local":
                return self.miner_stage1_local_base_url or self.miner_local_base_url
            return self.miner_stage1_remote_base_url or self.miner_remote_base_url
        return self.miner_local_base_url if self.miner_mode == "local" else self.miner_remote_base_url

    @property
    def miner_timeout(self) -> int:
        if self.miner_mode == "two_stage":
            if self.miner_stage1_mode == "local":
                return self.miner_stage1_local_timeout
            return self.miner_stage1_remote_timeout
        return self.miner_local_timeout if self.miner_mode == "local" else self.miner_remote_timeout

    @property
    def miner_temperature(self) -> float:
        """面经题目提取 LLM 温度。结构化 JSON 输出建议 0.0~0.2，小模型可略高至 0.2 减少刻板错误。"""
        return _get_float("MINER_TEMPERATURE", 0.2)

    @property
    def miner_max_tokens(self) -> int:
        """题目提取最大输出token数，避免截断导致JSON解析错误"""
        return _get_int("MINER_MAX_TOKENS", 0) or self.llm_max_tokens

    @property
    def miner_remote_max_tokens_cap(self) -> int:
        """
        two_stage Stage1 远程「期望」的 max_tokens 上限（省配额时可调小）。
        设为 0 或未设置时使用 16384。实际请求还会与 miner_stage1_api_max_tokens 取 min，
        避免通义等网关报 max_tokens 超范围。
        """
        v = _get_int("MINER_REMOTE_MAX_TOKENS", 0)
        return v if v > 0 else 16384

    @property
    def miner_stage1_api_max_tokens(self) -> int:
        """
        Stage1 所用 OpenAI 兼容网关对 completion 的 max_tokens 硬上限。
        部分通义模型报 [1, 8192]，部分为 [1, 16384]；默认取 8192 以兼容较严的模型。
        若你确认当前模型允许更大输出，可在 .env 设置 MINER_STAGE1_API_MAX_TOKENS=16384。
        """
        v = _get_int("MINER_STAGE1_API_MAX_TOKENS", 0)
        return v if v > 0 else 8192

    @property
    def miner_stage1_max_tokens(self) -> int:
        """Stage1 实际 max_tokens：min(MINER_MAX_TOKENS, 配置上限, 网关硬上限)，至少 1。"""
        remote = self.miner_remote_max_tokens_cap
        api_cap = self.miner_stage1_api_max_tokens
        cap = min(remote, api_cap)
        return max(1, min(self.miner_max_tokens, cap))

    @property
    def miner_max_retries(self) -> int:
        """题目提取单轮循环次数：1=只请求 1 次 LLM，2=失败后再试 1 次，以此类推"""
        return max(1, _get_int("MINER_MAX_RETRIES", 1))

    @property
    def miner_refusal_retries(self) -> int:
        """Miner 模型拒绝时，重试 Miner 的次数，用尽后再降级为直接 LLM 调用"""
        return max(0, _get_int("MINER_REFUSAL_RETRIES", 1))

    @property
    def worker_subprocess_log_body_max_chars(self) -> int:
        """子进程（WXR_WORKER_SUBPROCESS=1）日志中帖子正文最大字符数；0=不截断"""
        return _get_int("WORKER_SUBPROCESS_LOG_BODY_MAX_CHARS", 100_000)

    @property
    def miner_enforce_chinese_output(self) -> bool:
        """原帖含中文时，若题干/答案/标签英文主导则触发 ReAct 重试；设为 false 可关闭。"""
        return _get("MINER_ENFORCE_CHINESE_OUTPUT", "true").lower() in ("1", "true", "yes")

    @property
    def miner_circuit_enabled(self) -> bool:
        """Miner/TwoStage Stage1 工具熔断开关。"""
        return _get_bool("MINER_CIRCUIT_ENABLED", True)

    @property
    def miner_circuit_failure_threshold(self) -> int:
        """Miner/TwoStage Stage1 工具连续失败多少次后熔断。"""
        return max(1, _get_int("MINER_CIRCUIT_FAILURE_THRESHOLD", 3))

    @property
    def miner_circuit_recovery_timeout(self) -> int:
        """Miner/TwoStage Stage1 工具熔断后恢复时间（秒）。"""
        return max(1, _get_int("MINER_CIRCUIT_RECOVERY_TIMEOUT", 300))

    @property
    def miner_max_steps(self) -> int:
        """Miner Agent 最大步数（含 OCR、TodoWrite、Finish 等工具调用）"""
        return _get_int("MINER_MAX_STEPS", 100)

    @property
    def miner_session_enabled(self) -> bool:
        """Miner 会话持久化开关（断电续跑）。默认关闭以保持历史行为。"""
        return _get_bool("MINER_SESSION_ENABLED", False)

    @property
    def miner_session_auto_save_enabled(self) -> bool:
        """Miner 自动保存开关（每 N 条消息）。"""
        return _get_bool("MINER_SESSION_AUTO_SAVE_ENABLED", True)

    @property
    def miner_session_auto_save_interval(self) -> int:
        """Miner 自动保存间隔。"""
        return max(1, _get_int("MINER_SESSION_AUTO_SAVE_INTERVAL", 1))

    @property
    def miner_log_input_preview_chars(self) -> int:
        """Miner ReAct INFO 日志中用户输入截断长度。0=不截断（完整写入，长文日志会很大）；>0 则截断并加省略号。"""
        return _get_int("MINER_LOG_INPUT_PREVIEW_CHARS", 0)

    # ── 两阶段 Miner：Stage 2 豆包配置（精加工阶段）────────────────────────
    @property
    def miner_stage2_env_explicit(self) -> bool:
        """是否在 .env 中单独声明了 Stage2（任一即可触发独立端点，不再仅依赖回退）。"""
        return (
            _env_nonempty("MINER_STAGE2_MODEL")
            or _env_nonempty("MINER_STAGE2_BASE_URL")
            or _env_nonempty("MINER_STAGE2_API_KEY")
        )

    @property
    def miner_stage2_model(self) -> str:
        """Stage 2 精加工模型（建议豆包/Ark 等与 Stage1 不同的端点）；留空则用 MINER_REMOTE_MODEL"""
        return _get("MINER_STAGE2_MODEL") or self.miner_remote_model

    @property
    def miner_stage2_api_key(self) -> str:
        return _get("MINER_STAGE2_API_KEY") or self.miner_remote_api_key or _get("FINETUNE_LLM_API_KEY")

    @property
    def miner_stage2_base_url(self) -> str:
        return _get("MINER_STAGE2_BASE_URL") or self.miner_remote_base_url or _get("FINETUNE_LLM_BASE_URL")

    @property
    def miner_stage2_timeout(self) -> int:
        """Stage 2 精加工 API 超时（秒），默认 180（3 分钟）"""
        return _get_int("MINER_STAGE2_TIMEOUT", 0) or 180

    @property
    def miner_stage2_temperature(self) -> float:
        return _get_float("MINER_STAGE2_TEMPERATURE", 0.3)

    @property
    def miner_stage2_max_tokens_cap(self) -> int:
        """Stage2 输出 token 硬上限；<=0 表示不限制。默认 12288（火山 Ark 多数 lite 端点上限）。"""
        return _get_int("MINER_STAGE2_MAX_TOKENS_CAP", 12288)

    @property
    def miner_stage2_max_tokens(self) -> int:
        """Stage 2 精加工最大输出 token。

        火山 Ark 上部分模型（如 doubao-*-lite）要求 max_tokens <= 12288，超出会 400。
        实际生效：min(配置值, miner_stage2_max_tokens_cap)；cap<=0 时不做上限。
        """
        raw = _get_int("MINER_STAGE2_MAX_TOKENS", 0) or 8192
        cap = self.miner_stage2_max_tokens_cap
        if cap <= 0:
            return raw
        return min(raw, cap)

    @property
    def miner_stage2_use_batch(self) -> bool:
        """Stage 2 是否使用火山批量 API（批量推理有额外收费，默认单条）"""
        return _get("MINER_STAGE2_USE_BATCH", "").lower() in ("1", "true", "yes")

    @property
    def miner_stage2_batch_size(self) -> int:
        """Stage 2 队列触发批量处理的条数，达到即触发（默认 10）"""
        return _get_int("MINER_STAGE2_BATCH_SIZE", 10)

    @property
    def miner_stage2_recovery_stale_seconds(self) -> int:
        """
        Stage2 恢复：当 stage2_pending.status='in_progress' 且 locked_at 距离现在超过该值时，
        认为消费者崩溃/卡死，自动把它们置回 pending 供重试。
        """
        # 默认 10 分钟：Stage2 单条超时 180s/批量也可能更久，10min 足够覆盖重启后快速补跑
        return _get_int("MINER_STAGE2_RECOVERY_STALE_SECONDS", 600)

    @property
    def miner_stage2_async_enabled(self) -> bool:
        """已废弃：Stage2 仅支持同步执行（同一请求内跑完），始终为 False。"""
        return False

    @property
    def miner_stage2_run_mode(self) -> str:
        """Stage2 异步执行模式：thread(线程) / process(子进程)"""
        mode = _get("MINER_STAGE2_RUN_MODE", "process").lower()
        return mode if mode in ("thread", "process") else "process"

    @property
    def miner_stage2_models(self) -> List[Dict[str, Any]]:
        """Stage 2 模型列表（含主模型 + 备用），额度超限时按序切换。
        主模型来自 MINER_STAGE2_MODEL/API_KEY/BASE_URL；
        备用来自 MINER_STAGE2_FALLBACK_MODELS（JSON 数组），如：
        [{"model":"doubao-pro-32k","api_key":"xxx"},{"model":"xxx","api_key":"yyy","base_url":"https://..."}]
        base_url 可省略，默认用主配置的 BASE_URL。
        """
        primary_model = self.miner_stage2_model
        primary_key = self.miner_stage2_api_key
        primary_base = self.miner_stage2_base_url
        if not primary_model or not primary_base:
            return []
        return _remote_chain_with_fallback(
            primary_model,
            primary_key,
            primary_base,
            self.miner_stage2_timeout,
            _get("MINER_STAGE2_FALLBACK_MODELS", ""),
        )

    @property
    def extract_retries_on_failure(self) -> int:
        """有图片时，整段 extract 失败后的额外重试次数：0=只跑 1 轮 extract；1=失败再跑 1 轮"""
        return max(0, _get_int("EXTRACT_RETRIES_ON_FAILURE", 0))

    @property
    def crawler_fetch_max_retries(self) -> int:
        """爬取详情页失败时的最大重试次数"""
        return _get_int("CRAWLER_FETCH_MAX_RETRIES", 3)
    
    @property
    def crawler_retry_delay(self) -> int:
        """爬取重试间隔（秒）"""
        return _get_int("CRAWLER_RETRY_DELAY", 5)

    # ── 5. Embedding ──────────────────────────────────────────────
    @property
    def embed_model_type(self) -> str:
        return _get("EMBED_MODEL_TYPE", "dashscope")

    @property
    def embed_model_name(self) -> str:
        return _get("EMBED_MODEL_NAME", "text-embedding-v4")

    @property
    def embed_api_key(self) -> str:
        return _get("EMBED_API_KEY")

    @property
    def embed_base_url(self) -> str:
        return _get("EMBED_BASE_URL")

    @property
    def embed_ollama_url(self) -> str:
        """Ollama 本地服务地址（EMBED_MODEL_TYPE=ollama 时使用）"""
        return _get("EMBED_OLLAMA_URL", "http://localhost:11434")

    # ── 5.5 检索与重排 ─────────────────────────────────────────────
    @property
    def rerank_enabled(self) -> bool:
        """是否启用检索后重排"""
        return _get_bool("RERANK_ENABLED", True)

    @property
    def rerank_mode(self) -> str:
        """
        重排后端：ollama（本地 POST /api/rerank）或 remote / dashscope / bailian
        （阿里云百炼 compatible-api/v1/reranks，文档见 text-rerank-api）。
        """
        return _get("RERANK_MODE", "ollama").lower().strip()

    @property
    def rerank_model(self) -> str:
        """重排模型：ollama 如 dengcao/Qwen3-Reranker-8B:Q4_K_M；remote 如 qwen3-rerank"""
        raw = _get("RERANK_MODEL", "dengcao/Qwen3-Reranker-8B:Q4_K_M")
        # 常见笔误：Qwen3--Reranker（双连字符）会导致 Ollama 找不到模型
        return raw.replace("Qwen3--Reranker", "Qwen3-Reranker")

    @property
    def rerank_ollama_url(self) -> str:
        """重排服务 Ollama 地址（RERANK_MODE=ollama 时）"""
        return _get("RERANK_OLLAMA_URL", "http://localhost:11434")

    @property
    def rerank_remote_api_key(self) -> str:
        """远程重排 API Key；未设置时复用 EMBED_API_KEY（百炼同账号）"""
        return _get("RERANK_API_KEY") or _get("EMBED_API_KEY")

    @property
    def rerank_remote_base_url(self) -> str:
        """百炼文本重排 compatible 根 URL（不含 /reranks）"""
        return _get(
            "RERANK_REMOTE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-api/v1",
        ).rstrip("/")

    @property
    def rerank_instruct(self) -> str:
        """qwen3-rerank 可选任务说明（英文）；空则使用服务端默认策略"""
        return _get("RERANK_INSTRUCT", "")

    @property
    def rerank_top_n(self) -> int:
        """重排后返回条数"""
        return _get_int("RERANK_TOP_N", 5)

    @property
    def rerank_max_doc_length(self) -> int:
        """单文档最大长度（字符），超长截断"""
        return _get_int("RERANK_MAX_DOC_LENGTH", 1024)

    @property
    def rerank_timeout(self) -> int:
        """重排请求超时（秒）"""
        return _get_int("RERANK_TIMEOUT", 60)

    @property
    def rerank_trace_enabled(self) -> bool:
        """是否将向量候选与重排结果写入单独目录（见 rerank_trace_dir）"""
        return _get_bool("RERANK_TRACE_ENABLED", True)

    @property
    def rerank_trace_dir(self) -> str:
        """重排追踪 JSON 目录，默认 backend/logs/similar_rerank"""
        d = _get("RERANK_TRACE_DIR", "").strip()
        if d:
            return _resolve_data_path(d)
        return str(_PROJECT_ROOT / "backend" / "logs" / "similar_rerank")

    @property
    def rerank_trace_text_max_len(self) -> int:
        """追踪文件中单段题目正文最大字符数，避免单文件过大"""
        return _get_int("RERANK_TRACE_TEXT_MAX_LEN", 4000)

    @property
    def retrieval_search_top_k(self) -> int:
        """向量检索初筛条数（重排前多取一些）"""
        return _get_int("RETRIEVAL_SEARCH_TOP_K", 15)

    @property
    def retrieval_score_threshold(self) -> float:
        """向量检索相似度阈值（0~1）"""
        return _get_float("RETRIEVAL_SCORE_THRESHOLD", 0.5)

    @property
    def retrieval_similar_limit(self) -> int:
        """find_similar_questions 最终返回条数"""
        return _get_int("RETRIEVAL_SIMILAR_LIMIT", 5)

    @property
    def retrieval_check_duplicate_threshold(self) -> float:
        """查重阈值（入库时，高于此视为重复）"""
        return _get_float("RETRIEVAL_CHECK_DUPLICATE_THRESHOLD", 0.92)

    # ── 5.6 智能练习（知识点不足 + 随机，含遗忘曲线与 Reranker）────
    @property
    def smart_practice_knowledge_gap_count(self) -> int:
        """智能练习：按知识点不足（薄弱点+到期复习）给出的题目数，默认 10"""
        return _get_int("SMART_PRACTICE_KNOWLEDGE_GAP_COUNT", 10)

    @property
    def smart_practice_random_count(self) -> int:
        """智能练习：随机补充题目数，默认 10"""
        return _get_int("SMART_PRACTICE_RANDOM_COUNT", 10)

    @property
    def smart_practice_recall_ratio(self) -> float:
        """智能练习：召回倍数，每路召回条数 = 最终条数 * 此值（如 3 表示要 10 条则先召回 30 条再 rerank）"""
        return _get_float("SMART_PRACTICE_RECALL_RATIO", 3.0)

    @property
    def smart_practice_rerank_enabled(self) -> bool:
        """智能练习：是否对知识点不足一路使用 Reranker 重排，默认 true"""
        return _get_bool("SMART_PRACTICE_RERANK_ENABLED", True)

    @property
    def smart_practice_vector_weight(self) -> float:
        """智能练习：薄弱点向量相似题权重（与 review 一起融合排序）"""
        return _get_float("SMART_PRACTICE_VECTOR_WEIGHT", 0.35)

    @property
    def smart_practice_review_weight(self) -> float:
        """智能练习：到期复习（遗忘曲线）权重"""
        return _get_float("SMART_PRACTICE_REVIEW_WEIGHT", 0.45)

    @property
    def smart_practice_popular_weight(self) -> float:
        """智能练习：热门/标签补充权重（可选，用于多路召回）"""
        return _get_float("SMART_PRACTICE_POPULAR_WEIGHT", 0.2)

    @property
    def smart_practice_weak_tags_limit(self) -> int:
        """智能练习：参与召回的薄弱标签数量上限，默认 5"""
        return _get_int("SMART_PRACTICE_WEAK_TAGS_LIMIT", 5)

    # ── 6. Neo4j ──────────────────────────────────────────────────
    @property
    def neo4j_uri(self) -> str:
        return _get("NEO4J_URI", "bolt://localhost:7687")

    @property
    def neo4j_username(self) -> str:
        return _get("NEO4J_USERNAME", "neo4j")

    @property
    def neo4j_password(self) -> str:
        return _get("NEO4J_PASSWORD")

    @property
    def neo4j_database(self) -> str:
        return _get("NEO4J_DATABASE", "neo4j")

    # ── 7. Qdrant ─────────────────────────────────────────────────
    @property
    def qdrant_url(self) -> str:
        return _get("QDRANT_URL")

    @property
    def qdrant_api_key(self) -> str:
        return _get("QDRANT_API_KEY")

    @property
    def qdrant_collection(self) -> str:
        return _get("QDRANT_COLLECTION", "hello_agents_vectors")

    # ── 8. 本地存储 ───────────────────────────────────────────────
    @property
    def backend_data_dir(self) -> Path:
        """后端数据根目录，默认 backend/data"""
        p = _get("DATA_DIR", "").strip()
        if p:
            return Path(p) if Path(p).is_absolute() else _PROJECT_ROOT / p
        return _PROJECT_ROOT / "backend" / "data"

    @property
    def sqlite_db_path(self) -> str:
        p = _get("SQLITE_DB_PATH", "").strip()
        return str(self.backend_data_dir / "local_data.db") if not p else _resolve_data_path(p)

    @property
    def memory_data_dir(self) -> str:
        p = _get("MEMORY_DATA_DIR", "").strip()
        return str(self.backend_data_dir / "memory") if not p else _resolve_data_path(p)

    @property
    def log_dir(self) -> str:
        p = _get("LOG_DIR", "").strip()
        return str(_PROJECT_ROOT / "backend" / "logs") if not p else _resolve_data_path(p)

    @property
    def subprocess_log_dir(self) -> str:
        """后台子进程专用日志根目录；默认 LOG_DIR/subprocess。相对路径基于项目根。"""
        p = _get("SUBPROCESS_LOG_DIR", "").strip()
        if not p:
            return str(Path(self.log_dir) / "subprocess")
        return _resolve_data_path(p)

    @property
    def agent_trace_dir(self) -> str:
        """HelloAgents trace 目录。"""
        p = _get("AGENT_TRACE_DIR", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(Path(self.memory_data_dir) / "traces")

    @property
    def agent_run_log_dir(self) -> str:
        """HelloAgents AgentLogger 目录（每个 agent 单独文件）。"""
        p = _get("AGENT_RUN_LOG_DIR", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(Path(self.log_dir) / "agents")

    @property
    def agent_devlog_enabled(self) -> bool:
        """全局 DevLog 开关（各 Agent 可再单独覆盖）。"""
        return _get_bool("AGENT_DEVLOG_ENABLED", True)

    @property
    def interviewer_devlog_enabled(self) -> bool:
        """Interviewer DevLog 开关。"""
        return _get_bool("INTERVIEWER_DEVLOG_ENABLED", self.agent_devlog_enabled)

    @property
    def miner_devlog_enabled(self) -> bool:
        """Miner（含 two_stage Stage1）DevLog 开关。"""
        return _get_bool("MINER_DEVLOG_ENABLED", self.agent_devlog_enabled)

    @property
    def agent_devlog_dir(self) -> str:
        """DevLog 落盘目录。"""
        p = _get("AGENT_DEVLOG_DIR", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(Path(self.memory_data_dir) / "devlogs")

    @property
    def agent_tool_output_dir(self) -> str:
        """HelloAgents 工具输出完整落盘目录。"""
        p = _get("AGENT_TOOL_OUTPUT_DIR", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(Path(self.memory_data_dir) / "tool-output")

    @property
    def chat_history_migration_on_startup(self) -> bool:
        """启动时是否自动执行历史迁移（合并到默认 user/session）。"""
        return _get_bool("CHAT_HISTORY_MIGRATION_ON_STARTUP", False)

    @property
    def chat_history_migration_mode(self) -> str:
        """迁移模式：off | dry_run | apply。"""
        mode = _get("CHAT_HISTORY_MIGRATION_MODE", "off").lower().strip()
        return mode if mode in ("off", "dry_run", "apply") else "off"

    @property
    def chat_history_migration_run_once(self) -> bool:
        """迁移是否只运行一次（通过 marker 文件判定）。"""
        return _get_bool("CHAT_HISTORY_MIGRATION_RUN_ONCE", True)

    @property
    def chat_history_migration_marker(self) -> str:
        """历史迁移一次性标记文件路径。"""
        p = _get("CHAT_HISTORY_MIGRATION_MARKER", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(Path(self.memory_data_dir) / "chat_history_migration.done")

    @property
    def post_images_dir(self) -> Path:
        """帖子图片存储目录：backend/data/post_images/{task_id}/"""
        return self.backend_data_dir / "post_images"

    # ── OCR 配置 ──────────────────────────────────────────────
    @property
    def ocr_method(self) -> str:
        """OCR 方法：remote（云端视觉，OCR_REMOTE_* 独立配置）/ ollama_vl / qwen_vl / claude_vision / mcp"""
        m = _get("OCR_METHOD", "ollama_vl").lower()
        # 旧名 volcengine_vl 已合并为 remote
        return "remote" if m == "volcengine_vl" else m

    @property
    def mcp_ocr_server(self) -> str:
        """MCP OCR 服务器名称"""
        return _get("MCP_OCR_SERVER", "ocr-server")

    @property
    def mcp_image_extractor_path(self) -> str:
        """mcp-image-extractor dist/index.js 的绝对路径"""
        default = str(_PROJECT_ROOT / "mcp" / "mcp-image-extractor" / "dist" / "index.js")
        return _get("MCP_IMAGE_EXTRACTOR_PATH", default)

    @property
    def anthropic_api_key(self) -> str:
        """Anthropic API Key（用于 Claude Vision OCR）"""
        return _get("ANTHROPIC_API_KEY", "")

    @property
    def ocr_api_key(self) -> str:
        """OCR 用 API Key：优先 OCR_API_KEY，其次复用 EMBED_API_KEY（dashscope）"""
        return _get("OCR_API_KEY") or self.embed_api_key

    @property
    def ocr_model(self) -> str:
        """OCR 模型名，留空则按 ocr_method 自动选择"""
        return _get("OCR_MODEL", "")

    @property
    def ocr_timeout(self) -> int:
        """OCR 单张图片超时秒数，图片多或模型慢时可调大"""
        return _get_int("OCR_TIMEOUT", 120)

    @property
    def ocr_retries(self) -> int:
        """单张图片 OCR 失败或乱码时的重试次数"""
        return _get_int("OCR_RETRIES", 3)

    @property
    def ocr_remote_api_key(self) -> str:
        """远程 OCR API Key（仅 OCR_REMOTE_API_KEY，不复用 MINER/LLM）"""
        return _get("OCR_REMOTE_API_KEY")

    @property
    def ocr_remote_base_url(self) -> str:
        """远程 OCR OpenAI 兼容 Base（仅 OCR_REMOTE_BASE_URL）"""
        return _get("OCR_REMOTE_BASE_URL")

    @property
    def ocr_remote_max_tokens(self) -> int:
        """远程视觉 OCR max_tokens，默认 8192"""
        return _get_int("OCR_REMOTE_MAX_TOKENS", 0) or 8192

    @property
    def ocr_remote_models(self) -> List[Dict[str, Any]]:
        """
        远程 OCR 模型链（按顺序尝试）。OCR_REMOTE_MODELS 为 JSON 数组，格式同 MINER_STAGE2_FALLBACK_MODELS：
        [{"model":"doubao-xxx"},{"model":"yyy","api_key":"可选","base_url":"可选"}]
        省略的 api_key、base_url 使用 OCR_REMOTE_API_KEY / OCR_REMOTE_BASE_URL。
        若 JSON 为空但 OCR_REMOTE_MODEL 与密钥、BASE_URL 均已配置，则退化为单模型。
        """
        default_key = (self.ocr_remote_api_key or "").strip()
        default_base = (self.ocr_remote_base_url or "").strip()
        result: List[Dict[str, Any]] = []
        raw = _get("OCR_REMOTE_MODELS", "").strip()
        if raw:
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict) or not item.get("model"):
                            continue
                        result.append({
                            "model": str(item["model"]).strip(),
                            "api_key": str(item.get("api_key") or default_key).strip(),
                            "base_url": str(item.get("base_url") or default_base).strip(),
                        })
            except json.JSONDecodeError:
                pass
        if not result:
            single = _get("OCR_REMOTE_MODEL", "").strip()
            if single and default_key and default_base:
                result.append({
                    "model": single,
                    "api_key": default_key,
                    "base_url": default_base,
                })
        return result

    @property
    def nowcoder_output_dir(self) -> Path:
        """牛客测试/调试输出目录（正文 txt + 图片，不含 HTML）"""
        return self.backend_data_dir / "nowcoder_output"

    @property
    def logs_dir(self) -> Path:
        """日志相关 data 统一目录：LLM CSV、llm_failures、xhs_link_cache 等"""
        return self.backend_data_dir / "logs"

    @property
    def llm_prompt_log_csv(self) -> str:
        """LLM 交互日志路径（JSONL 格式，精简原始+输出），留空则不记录"""
        p = _get("LLM_PROMPT_LOG_CSV", "").strip()
        return "" if not p else _resolve_data_path(p)

    @property
    def miner_two_stage_log_path(self) -> str:
        """两阶段提取日志路径（Stage1 MINER_REMOTE + Stage2 豆包 对比，用于微调）"""
        p = _get("MINER_TWO_STAGE_LOG", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(_PROJECT_ROOT / "微调" / "llm_logs" / "miner_two_stage_log.jsonl")

    @property
    def finetune_logs_dir(self) -> str:
        """微调日志目录（导入日志页扫描目录）"""
        p = _get("FINETUNE_LOGS_DIR", "").strip()
        if p:
            return _resolve_data_path(p)
        return str(_PROJECT_ROOT / "微调" / "llm_logs")

    # ── 9. 爬虫 ──────────────────────────────────────────────────
    @property
    def nowcoder_cookie(self) -> str:
        return _get("NOWCODER_COOKIE")

    @property
    def crawler_source(self) -> str:
        """爬虫来源：local=本地后端爬虫 | mcp=远程 MCP Content Fetcher"""
        return _get("CRAWLER_SOURCE", "local").lower()

    @property
    def mcp_content_fetcher_url(self) -> str:
        """MCP Content Fetcher 根 URL（CRAWLER_SOURCE=mcp 时生效）"""
        return _get("MCP_CONTENT_FETCHER_URL", "https://mcp-content-fetcher.onrender.com").rstrip("/")

    @property
    def mcp_content_fetcher_timeout(self) -> int:
        """MCP Content Fetcher 请求超时秒数"""
        return _get_int("MCP_CONTENT_FETCHER_TIMEOUT", 30)

    @property
    def smithery_api_key(self) -> str:
        """Smithery API Key（通过 Smithery 网关时用于鉴权）"""
        return _get("SMITHERY_API_KEY", "")

    # ── 10. 调度器 ────────────────────────────────────────────────
    @property
    def scheduler_enable_nowcoder(self) -> bool:
        return _get_bool("SCHEDULER_ENABLE_NOWCODER", True)

    @property
    def scheduler_enable_xhs(self) -> bool:
        return _get_bool("SCHEDULER_ENABLE_XHS", False)

    @property
    def scheduler_nowcoder_hours(self) -> str:
        """cron 小时表达式，如 "2,14" 表示 02:00 和 14:00"""
        return _get("SCHEDULER_NOWCODER_HOURS", "2,14")

    @property
    def scheduler_process_minute(self) -> str:
        """任务处理器 cron 分钟，"0" 表示每小时整点"""
        return _get("SCHEDULER_PROCESS_MINUTE", "0")

    @property
    def nowcoder_keywords(self) -> list:
        return _get_list(
            "NOWCODER_KEYWORDS",
            "后端面经,Java面经,Go面经,算法面经,前端面经,测试面经"
        )

    @property
    def nowcoder_max_pages(self) -> int:
        return _get_int("NOWCODER_MAX_PAGES", 2)

    @property
    def xhs_keywords(self) -> list:
        return _get_list("XHS_KEYWORDS", "后端面经,算法面经,Java面经")

    @property
    def xhs_max_notes_per_keyword(self) -> int:
        return _get_int("XHS_MAX_NOTES_PER_KEYWORD", 5)

    @property
    def xhs_user_data_dir(self) -> str:
        p = _get("XHS_USER_DATA_DIR", "").strip()
        return str(self.backend_data_dir / "xhs_user_data") if not p else _resolve_data_path(p)

    @property
    def xhs_link_cache_path(self) -> str:
        """小红书已获取链接缓存文件（存于 logs 目录）"""
        p = _get("XHS_LINK_CACHE", "").strip()
        return str(self.logs_dir / "xhs_link_cache.txt") if not p else _resolve_data_path(p)

    @property
    def xhs_login_wait_seconds(self) -> int:
        return _get_int("XHS_LOGIN_WAIT_SECONDS", 120)

    @property
    def crawler_process_batch_size(self) -> int:
        """任务队列每批处理条数（定时任务、API 默认值均由此读取）"""
        return _get_int("CRAWLER_PROCESS_BATCH_SIZE", 100)

    @property
    def crawler_process_batch_max(self) -> int:
        """API 可传入的 batch_size 上限"""
        return _get_int("CRAWLER_PROCESS_BATCH_MAX", 200)

    @property
    def crawler_background_run_mode(self) -> str:
        """后台任务执行模式：process(子进程) / thread(线程)。process 时凡经 task_executor 触发的 process_tasks（定时、API 等）均走子进程，避免主进程阻塞与刷屏。"""
        mode = _get("CRAWLER_BACKGROUND_RUN_MODE", "process").lower()
        return mode if mode in ("process", "thread") else "process"

    @property
    def crawler_auto_resume_fetched_on_startup(self) -> bool:
        """后端重启时是否自动恢复 fetched 遗留任务（子进程续跑）"""
        return _get_bool("CRAWLER_AUTO_RESUME_FETCHED_ON_STARTUP", True)

    @property
    def crawler_auto_resume_batch_extract_on_startup(self) -> bool:
        """后端重启时若存在 shutdown 保存的未完成批量提取，是否自动拉起 batch_extract 子进程续跑"""
        return _get_bool("CRAWLER_AUTO_RESUME_BATCH_EXTRACT_ON_STARTUP", True)

    @property
    def crawler_recursive_retry_max(self) -> int:
        """爬取+提取失败任务的最大递归重试次数"""
        return _get_int("CRAWLER_RECURSIVE_RETRY_MAX", 10)

    # ── 11. 对话与 Agent ──────────────────────────────────────────
    @property
    def default_user_id(self) -> str:
        """默认用户 ID，前端未指定时使用"""
        return _get("DEFAULT_USER_ID", "Wangxr")

    @property
    def default_session_id(self) -> str:
        """默认会话 ID，前端未指定时使用（固定单会话时在 .env 配置）"""
        return _get("DEFAULT_SESSION_ID", "sess_fixed")

    @property
    def interviewer_max_steps(self) -> int:
        """Interviewer Agent 最大思考步数"""
        return _get_int("INTERVIEWER_MAX_STEPS", 8)

    # ── 12. 题目推荐配置（GetRecommendedQuestionTool）──────────────
    @property
    def recommend_questions_count(self) -> int:
        """一次推荐的题目数量，默认 5"""
        return _get_int("RECOMMEND_QUESTIONS_COUNT", 5)

    @property
    def recommend_questions_json_format(self) -> bool:
        """是否启用 JSON 格式化输出，默认 true"""
        return _get_bool("RECOMMEND_QUESTIONS_JSON_FORMAT", True)

    @property
    def recommend_questions_show_detail(self) -> bool:
        """是否显示题目详情（题目文本、难度、标签），默认 true"""
        return _get_bool("RECOMMEND_QUESTIONS_SHOW_DETAIL", True)

    @property
    def recommend_questions_show_reason(self) -> bool:
        """是否显示推荐理由，默认 true"""
        return _get_bool("RECOMMEND_QUESTIONS_SHOW_REASON", True)


# 全局单例（懒加载，main.py 中 load_dotenv 先于任何 import settings 执行）
settings = _Settings()

_stage2_remote_fallback_warned = False


def warn_if_stage2_shares_remote_fallback() -> None:
    """
    若未在 .env 中单独声明 MINER_STAGE2_*，Stage2 与单阶段 Miner 共用 MINER_REMOTE_*。
    进程内只告警一次，便于发现「精答与粗提取抢同一模型额度」。
    """
    global _stage2_remote_fallback_warned
    if _stage2_remote_fallback_warned or settings.miner_stage2_env_explicit:
        return
    _stage2_remote_fallback_warned = True
    logging.getLogger("backend.config").warning(
        "[Stage2] 未单独配置 MINER_STAGE2_MODEL / MINER_STAGE2_BASE_URL / MINER_STAGE2_API_KEY，"
        "精加工与单阶段 Miner 共用 MINER_REMOTE_*（当前 model=%s）。若需独立额度或火山豆包等，请在 .env 填写 MINER_STAGE2_*。",
        (settings.miner_stage2_model or "")[:120] or "(空)",
    )
