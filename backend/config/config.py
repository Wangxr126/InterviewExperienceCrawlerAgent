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
        return _get_int("LLM_TIMEOUT", 60)

    @property
    def llm_temperature(self) -> float:
        return _get_float("LLM_TEMPERATURE", 0.3)

    # ── 2. Hunter Agent ───────────────────────────────────────────
    @property
    def hunter_model(self) -> str:
        return _get("HUNTER_MODEL") or self.llm_model_id

    @property
    def hunter_api_key(self) -> str:
        return _get("HUNTER_API_KEY") or self.llm_api_key

    @property
    def hunter_base_url(self) -> str:
        return _get("HUNTER_BASE_URL") or self.llm_base_url

    @property
    def hunter_temperature(self) -> float:
        return _get_float("HUNTER_TEMPERATURE", 0.1)

    # ── 3. Architect Agent ────────────────────────────────────────
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

    # ── 4. Interviewer Agent ──────────────────────────────────────
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

    # ── 8. 工具 API ───────────────────────────────────────────────
    @property
    def tavily_api_key(self) -> str:
        return _get("TAVILY_API_KEY")

    @property
    def serpapi_api_key(self) -> str:
        return _get("SERPAPI_API_KEY")

    @property
    def amap_api_key(self) -> str:
        return _get("AMAP_API_KEY")

    @property
    def unsplash_access_key(self) -> str:
        return _get("UNSPLASH_ACCESS_KEY")

    # ── 9. 本地存储（统一在 backend/data 下，可通过 DATA_DIR 覆盖）──
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
        """帖子图片存储目录"""
        return self.backend_data_dir / "post_images"

    # ── 10. 爬虫基础 ──────────────────────────────────────────────
    @property
    def nowcoder_cookie(self) -> str:
        return _get("NOWCODER_COOKIE")

    # ── 11. 调度器 ────────────────────────────────────────────────
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
    def xhs_login_wait_seconds(self) -> int:
        return _get_int("XHS_LOGIN_WAIT_SECONDS", 120)

    @property
    def crawler_process_batch_size(self) -> int:
        return _get_int("CRAWLER_PROCESS_BATCH_SIZE", 5)

    # ── 12. 对话与 Agent ───────────────────────────────────────────
    @property
    def default_user_id(self) -> str:
        """默认用户 ID，前端未指定时使用"""
        return _get("DEFAULT_USER_ID", "user_001")

    @property
    def interviewer_max_steps(self) -> int:
        """Interviewer Agent 最大思考步数"""
        return _get_int("INTERVIEWER_MAX_STEPS", 8)


# 全局单例（懒加载，main.py 中 load_dotenv 先于任何 import settings 执行）
settings = _Settings()
