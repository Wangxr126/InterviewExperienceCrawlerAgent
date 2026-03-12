"""
配置管理 —— 纯环境变量读取器
所有值均来自 .env 文件（项目根目录），不在此处硬编码。
修改配置请直接编辑 /.env 文件。
"""
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_path(p: str) -> str:
    """相对路径转为基于项目根的绝对路径"""
    if not p:
        return p
    path = Path(p)
    return str(path) if path.is_absolute() else str(_PROJECT_ROOT / path)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


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
        return _get_float("LLM_TEMPERATURE", 0.3)

    @property
    def llm_max_tokens(self) -> int:
        """最大输出token数，避免截断导致JSON解析错误"""
        return _get_int("LLM_MAX_TOKENS", 4096)

    @property
    def llm_warmup_enabled(self) -> bool:
        """启动时是否预热 LLM（解决 Ollama/云端 冷启动首请求慢或无响应）"""
        return _get_bool("LLM_WARMUP_ENABLED", True)

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
        return _get_float("INTERVIEWER_TEMPERATURE", 0.6)

    @property
    def interviewer_max_tokens(self) -> int:
        return _get_int("INTERVIEWER_MAX_TOKENS", 0) or self.llm_max_tokens

    @property
    def enable_smart_compression(self) -> bool:
        """是否启用智能摘要（需额外 LLM 调用），默认 False"""
        return _get_bool("ENABLE_SMART_COMPRESSION", False)

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
    def finetune_llm_temperature(self) -> float:
        return _get_float("FINETUNE_LLM_TEMPERATURE", 0.1)

    @property
    def finetune_llm_max_tokens(self) -> int:
        return _get_int("FINETUNE_LLM_MAX_TOKENS", 0) or self.llm_max_tokens

    # ── 4.6 Miner Agent（题目提取器）──────────────────────────────────
    @property
    def miner_mode(self) -> str:
        """Miner使用模式：local/remote，留空则使用全局LLM_MODE"""
        return _get("MINER_MODE") or self.llm_mode

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
        return _get("MINER_REMOTE_BASE_URL") or self.llm_remote_base_url

    @property
    def miner_remote_timeout(self) -> int:
        return _get_int("MINER_REMOTE_TIMEOUT", 0) or self.llm_remote_timeout

    # 当前使用的配置（根据mode选择）
    @property
    def miner_provider(self) -> str:
        return self.miner_local_provider if self.miner_mode == "local" else self.miner_remote_provider

    @property
    def miner_model(self) -> str:
        return self.miner_local_model if self.miner_mode == "local" else self.miner_remote_model

    @property
    def miner_api_key(self) -> str:
        local_key = _get("MINER_LOCAL_API_KEY") or self.llm_local_api_key
        remote_key = _get("MINER_REMOTE_API_KEY") or self.llm_remote_api_key
        return local_key if self.miner_mode == "local" else remote_key

    @property
    def miner_base_url(self) -> str:
        return self.miner_local_base_url if self.miner_mode == "local" else self.miner_remote_base_url

    @property
    def miner_timeout(self) -> int:
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
    def miner_max_retries(self) -> int:
        """题目提取失败时的最大重试次数（返回空或格式错误时重试）"""
        return _get_int("MINER_MAX_RETRIES", 3)

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
    def post_images_dir(self) -> Path:
        """帖子图片存储目录：backend/data/post_images/{task_id}/"""
        return self.backend_data_dir / "post_images"

    # ── OCR 配置 ──────────────────────────────────────────────
    @property
    def ocr_method(self) -> str:
        """OCR 方法：qwen_vl（阿里云百炼，推荐）/ claude_vision / mcp"""
        return _get("OCR_METHOD", "qwen_vl")

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

    # ── 9. 爬虫 ──────────────────────────────────────────────────
    @property
    def nowcoder_cookie(self) -> str:
        return _get("NOWCODER_COOKIE")

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
    def crawler_recursive_retry_max(self) -> int:
        """爬取+提取失败任务的最大递归重试次数"""
        return _get_int("CRAWLER_RECURSIVE_RETRY_MAX", 10)

    # ── 11. 对话与 Agent ──────────────────────────────────────────
    @property
    def default_user_id(self) -> str:
        """默认用户 ID，前端未指定时使用"""
        return _get("DEFAULT_USER_ID", "Wangxr")

    @property
    def interviewer_max_steps(self) -> int:
        """Interviewer Agent 最大思考步数"""
        return _get_int("INTERVIEWER_MAX_STEPS", 8)


# 全局单例（懒加载，main.py 中 load_dotenv 先于任何 import settings 执行）
settings = _Settings()
