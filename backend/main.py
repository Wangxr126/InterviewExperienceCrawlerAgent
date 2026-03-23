"""

面经 Agent 后端 FastAPI 主入口

启动：python run.py  或  uvicorn backend.main:app --reload

API 文档：http://localhost:8000/docs

"""
import os
import sys
import warnings

# 修复 Windows GBK 终端下 emoji/中文字符编码问题
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# 禁用 requests/urllib3 版本兼容性警告（使用 filterwarnings，避免 PYTHONWARNINGS 的 invalid module name 报错）
try:
    import requests.exceptions
    warnings.filterwarnings('ignore', category=requests.exceptions.RequestsDependencyWarning)
except Exception:
    pass
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*urllib3.*')
warnings.filterwarnings('ignore', message='.*chardet.*')


# ── 必须最先执行：加载项目 .env，确保 hello_agents 能读到正确的数据库/embedding 配置 ──

from backend.utils.time_utils import now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing

import logging

import sys

from pathlib import Path

from dotenv import load_dotenv



_env_file = Path(__file__).parent.parent / ".env"

if _env_file.exists():

    load_dotenv(dotenv_path=str(_env_file), override=True)



# ── 确保运行时目录存在（统一从 config 读取）──

from backend.config.config import settings as _cfg

_PROJECT_ROOT = Path(__file__).parent.parent

_BACKEND_DATA = _cfg.backend_data_dir

_BACKEND_LOGS = Path(_cfg.log_dir)

_BATCH_EXTRACT_STATE_FILE = _BACKEND_LOGS / "batch_extract_state.json"
_BATCH_EXTRACT_ABORT_FILE = _BACKEND_LOGS / "batch_extract.abort"

# 父进程持有的批量提取子进程句柄，shutdown 时用于优雅终止
_batch_extract_proc: "subprocess.Popen | None" = None

_MEMORY_DIR = Path(_cfg.memory_data_dir)

_XHS_DATA_DIR = Path(_cfg.xhs_user_data_dir)

_POST_IMAGES_DIR = _cfg.post_images_dir

_NOWCODER_OUTPUT_DIR = _cfg.nowcoder_output_dir



for _d in [
    _BACKEND_DATA,
    _BACKEND_LOGS,
    Path(_cfg.subprocess_log_dir),
    _MEMORY_DIR,
    _XHS_DATA_DIR,
    _POST_IMAGES_DIR,
    _NOWCODER_OUTPUT_DIR,
]:

    _d.mkdir(parents=True, exist_ok=True)



# ── 使用 loguru：终端彩色（INFO 绿 / WARNING 黄 / ERROR 红），文件滚动 ──

try:

    from loguru import logger as _loguru_logger

    _loguru_logger.remove()

    # 统一的日志格式：完整日期时间 | 级别（7字符宽） | 文件:行号 | 消息
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"

    # 多进程模式：只在主进程输出到终端，避免重复打印
    # uvicorn多进程模式下，worker进程会设置 UVICORN_WORKER_ID 环境变量
    is_main_process = os.environ.get('UVICORN_WORKER_ID') is None
    
    if is_main_process:
        _loguru_logger.add(

            sys.stderr,

            colorize=True,

            format=_log_format,

            level="INFO",

        )

    # 所有进程都写入文件（enqueue=True 确保多进程安全）
    _loguru_logger.add(

        _BACKEND_LOGS / "backend.log",

        rotation="10 MB",

        retention=5,

        encoding="utf-8",

        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",

        level="INFO",

        enqueue=True,

    )

    # 拦截标准库 logging，统一到 loguru

    class _InterceptHandler(logging.Handler):

        def emit(self, record):

            try:

                level = _loguru_logger.level(record.levelname).name

            except ValueError:

                level = record.levelno

            
            # 格式化消息
            msg = record.getMessage()
            
            # 过滤极度冗长的日志（neo4j 约束通知、httpx 请求详情、xhs_crawl 内部日志）
            if record.name == "neo4j.notifications":
                return
            if record.name == "httpx":
                return
            if record.name.startswith("xhs_crawl"):
                level = "DEBUG"
            
            # 简化 uvicorn 访问日志格式（降为 DEBUG，避免刷屏）
            if record.name == "uvicorn.access":
                import re
                match = re.search(r'"([A-Z]+)\s+([^\s]+)[^"]*"\s+(\d+)', msg)
                if match:
                    method, path, status = match.groups()
                    # 200 用 DEBUG，4xx/5xx 用 WARNING/ERROR
                    status_int = int(status)
                    if status_int >= 500:
                        level = "ERROR"
                    elif status_int >= 400:
                        level = "WARNING"
                    else:
                        level = "DEBUG"
                    msg = f"[HTTP] {method} {path} → {status}"
                else:
                    level = "DEBUG"

            _loguru_logger.opt(depth=6, exception=record.exc_info).log(level, msg)

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    _loguru_logger.info("✅ 日志系统已启动（统一格式）")

    # 修复 hello_agents 工具参数 JSON 解析（Unterminated string）问题
    try:
        from backend.patches.tool_args_json_patch import apply_patch
        apply_patch()
    except Exception as _e:
        _loguru_logger.warning("工具参数 JSON 解析补丁未应用: %s", _e)
    
    # 禁用 hello-agents 框架的工具注册日志（print 直接输出到 stdout，需 monkey-patch 静默）
    logging.getLogger("hello_agents").setLevel(logging.WARNING)
    logging.getLogger("hello_agents.tools").setLevel(logging.WARNING)
    try:
        from hello_agents.tools.registry import ToolRegistry as _TR
        import io as _io
        _orig_register_tool = _TR.register_tool
        _orig_register_function = _TR.register_function
        def _silent_register_tool(self, tool, **kw):
            import sys as _sys
            _old, _sys.stdout = _sys.stdout, _io.StringIO()
            try:
                return _orig_register_tool(self, tool, **kw)
            finally:
                _sys.stdout = _old
        def _silent_register_function(self, func, **kw):
            import sys as _sys
            _old, _sys.stdout = _sys.stdout, _io.StringIO()
            try:
                return _orig_register_function(self, func, **kw)
            finally:
                _sys.stdout = _old
        _TR.register_tool = _silent_register_tool
        _TR.register_function = _silent_register_function
    except Exception:
        pass

except ImportError:

    _loguru_logger = None

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",

                       datefmt="%Y-%m-%d %H:%M:%S")
    # loguru 未安装时仍应用工具参数 JSON 解析补丁
    try:
        from backend.patches.tool_args_json_patch import apply_patch
        apply_patch()
    except Exception:
        pass





class _StatsAccessFilter(logging.Filter):

    """过滤 uvicorn 对 /api/crawler/stats 的 access log，避免轮询刷屏"""



    def filter(self, record: logging.LogRecord) -> bool:

        if record.name != "uvicorn.access":

            return True

        try:

            return "crawler/stats" not in (record.getMessage() or "")

        except Exception:

            return True





logging.getLogger("uvicorn.access").addFilter(_StatsAccessFilter())

# 降低 openai 重试日志级别，避免 "Retrying request to /chat/completions" 刷屏

logging.getLogger("openai").setLevel(logging.WARNING)

logging.getLogger("openai._base_client").setLevel(logging.WARNING)

logger = _loguru_logger if _loguru_logger else logging.getLogger(__name__)



# ── 安装线程感知 stdout 拦截器（用于捕获 hello_agents 思考步骤）──

from backend.agents.thinking_capture import install as _install_thinking_capture

_install_thinking_capture()



import random

import time

from typing import Optional, List, Dict, Any



import asyncio

import json
from datetime import datetime

import requests

from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import StreamingResponse

from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel



from backend.agents.interviewer_agent import get_orchestrator

from backend.services.storage.sqlite_service import sqlite_service
from backend.services.multi_recall_recommender import multi_recall_recommender

from backend.services.scheduling.scheduler import crawl_scheduler
from backend.services.scheduling.subprocess_log_paths import new_subprocess_log_file
from backend.services.crawler.task_executor import (
    execute as task_execute,
    get_source_info as task_get_source_info,
)



# 后台提取运行状态（供前端刷新后恢复进度显示）

_extraction_running = False

_extraction_initial_by_platform = {}  # 开始时的 fetched 数量按平台，如 {"nowcoder": 5, "xiaohongshu": 17}



app = FastAPI(

    title="面经 Agent API",

    description="面试复习助手后端接口",

    version="3.0"

)

# ══════════════════════════════════════════════════════
# 请求模型定义
# ══════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    """自由对话请求"""
    user_id: str
    message: str
    resume: Optional[str] = None
    session_id: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    """答题提交请求"""
    user_id: str
    session_id: Optional[str] = None
    question_id: Optional[str] = None
    question_text: Optional[str] = None
    user_answer: str
    question_tags: Optional[List[str]] = None






class EndSessionRequest(BaseModel):
    """结束会话请求"""
    user_id: str
    session_id: str


class IngestRequest(BaseModel):
    """内容采集请求"""
    url: str
    user_id: Optional[str] = None
    source_platform: Optional[str] = None


# 允许前端跨域（开发阶段全放开）

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



# 挂载构建后的前端静态文件（生产模式）

_DIST_DIR = _PROJECT_ROOT / "backend" / "static" / "dist"

if _DIST_DIR.exists():

    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="assets")



# 帖子图片静态服务（相对路径 post_images/TASK_XXX/0.jpg → /post-images/TASK_XXX/0.jpg）

if _POST_IMAGES_DIR.exists():

    app.mount("/post-images", StaticFiles(directory=str(_POST_IMAGES_DIR)), name="post_images")





# 添加调度器管理 API 路由

from backend.api.scheduler_api import router as scheduler_router
from backend.api.reasoning_api import router as reasoning_router
from backend.api.model_bench_api import router as model_bench_router

app.include_router(scheduler_router)
app.include_router(reasoning_router)
app.include_router(model_bench_router)



orchestrator = get_orchestrator()





def _warmup_llm_sync():
    """同步预热 LLM，供启动时及 run_xhs_worker 子进程调用"""
    from backend.services.warmup.llm_warmup import warmup_llm

    warmup_llm(timeout=120)  # Ollama 冷启动可能较久


def _warmup_embedding_rerank_sync():
    """同步预热 Embedding + Reranker（LLM 预热之后调用）"""
    from backend.services.warmup.model_warmup import warmup_embedding_rerank

    warmup_embedding_rerank(timeout=120)





def _print_agent_llm_config():

    """启动时打印各 Agent 使用的 LLM 和参数（从 settings 读取，不直接读 env）"""

    from backend.config.config import settings as s

    base = (s.llm_base_url or "")[:60] + ("..." if len(s.llm_base_url or "") > 60 else "")

    logger.info("─" * 60)

    logger.info("各 Agent LLM 配置（运行时实际值）")

    logger.info("─" * 60)

    logger.info(f"  [全局] provider={s.llm_provider}, model={s.llm_model_id or '(未设置)'}")

    logger.info(f"          base_url={base or '(未设置)'}, timeout={s.llm_timeout}, temperature={s.llm_temperature}")

    logger.info("  " + "─" * 56)

    mm = s.miner_model or s.llm_model_id or "(未设置)"
    logger.info(
        f"  [Miner Agent] mode={s.miner_mode}, model={mm}, temperature={s.miner_temperature}, "
        f"max_tokens={s.miner_max_tokens}, base={s.miner_base_url or s.llm_base_url or '(同全局)'}"
    )

    # Interviewer Agent

    im = s.interviewer_model or s.llm_model_id

    logger.info(f"  [Interviewer Agent] model={im}, temperature={s.interviewer_temperature}, base={s.interviewer_base_url or s.llm_base_url or '(同全局)'}")

    logger.info("=" * 60)







@app.on_event("startup")
async def startup_event():
    """FastAPI 启动时启动后台调度器，并可选预热 LLM"""
    from backend.config.config import settings as _s
    from backend.services.crawler.question_extractor import _print_miner_config_once
    from backend.services.storage import sqlite_service

    _print_miner_config_once()
    _print_agent_llm_config()
    crawl_scheduler.start()
    _src = getattr(_s, "crawler_source", "local")
    logger.info(f"爬虫调度器已启动 | 牛客抓取来源={_src}")

    # 批量提取恢复：检测上次 shutdown 时保存的未完成进度
    try:
        if _BATCH_EXTRACT_STATE_FILE.exists():
            with open(_BATCH_EXTRACT_STATE_FILE, "r", encoding="utf-8") as f:
                import json
                state = json.load(f)
            if state.get("interrupted_at"):
                completed = set(state.get("completed", []))
                task_ids = state.get("task_ids", [])
                remaining = [t for t in task_ids if t not in completed]
                if remaining:
                    # 主 logger 为 loguru 时，% 占位符+额外参数不会格式化，须用 f-string
                    logger.info(
                        f"[Startup] 检测到未完成批量提取：已完成 {len(completed)}/{state.get('total', 0)}，"
                        f"剩余 {len(remaining)} 条。"
                    )
                    if getattr(_s, "crawler_auto_resume_batch_extract_on_startup", True):
                        log_path = new_subprocess_log_file("batch_extract")
                        cmd = (
                            [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker"]
                            + remaining
                        )
                        _spawn_batch_extract_subprocess(cmd, log_path, len(remaining))
                        logger.info(
                            f"[Startup] 已自动恢复批量提取子进程，剩余 {len(remaining)} 条，日志: {log_path}"
                        )
                    else:
                        logger.info(
                            "[Startup] 已关闭自动恢复（CRAWLER_AUTO_RESUME_BATCH_EXTRACT_ON_STARTUP=false），"
                            "请调用 POST /api/crawler/tasks/resume-batch"
                        )
    except (OSError, ValueError, KeyError):
        pass

    # fetched 恢复补跑：后端重启后，自动继续上次未完成的正文提取任务
    # 依赖 crawl_tasks.status 持久化，无需额外状态文件
    try:
        if _s.crawler_auto_resume_fetched_on_startup:
            with sqlite_service._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM crawl_tasks WHERE status='fetched'"
                ).fetchone()
                fetched_count = int(row["c"] or 0) if row else 0
            if fetched_count > 0:
                resume_batch_size = max(
                    int(getattr(_s, "crawler_process_batch_size", 30) or 30),
                    fetched_count,
                )
                logger.info(
                    f"[Startup] 检测到 fetched 遗留任务 {fetched_count} 条，"
                    f"启动子进程自动恢复（batch_size={resume_batch_size}）"
                )
                _spawn_process_tasks_worker(
                    batch_size=resume_batch_size,
                    reason="startup-resume-fetched",
                )
    except Exception:
        logger.warning("[Startup] fetched 自动恢复失败（不影响主服务启动）", exc_info=True)

    # 历史迁移：将旧会话清洗并合并到默认 user/session，供 HelloAgents SessionStore 直接加载
    try:
        mode = _s.chat_history_migration_mode
        if _s.chat_history_migration_on_startup and mode != "off":
            marker_path = Path(_s.chat_history_migration_marker)
            if _s.chat_history_migration_run_once and marker_path.exists():
                logger.info("[Startup] 历史迁移已执行过（marker 存在），跳过。")
            else:
                from backend.scripts.migrate_chat_history_to_default_session import migrate as _migrate_chat_history

                do_apply = mode == "apply"
                logger.info(f"[Startup] 执行历史迁移 mode={mode} ...")
                rc = await asyncio.to_thread(_migrate_chat_history, do_apply)
                if rc == 0 and _s.chat_history_migration_run_once:
                    marker_path.parent.mkdir(parents=True, exist_ok=True)
                    marker_payload = {
                        "mode": mode,
                        "applied": do_apply,
                        "executed_at": datetime.now().isoformat(),
                    }
                    marker_path.write_text(json.dumps(marker_payload, ensure_ascii=False), encoding="utf-8")
                logger.info(f"[Startup] 历史迁移完成 mode={mode} rc={rc}")
    except Exception:
        logger.warning("[Startup] 历史迁移执行失败（不影响主服务启动）", exc_info=True)

    # 同步预热 LLM，确保首次请求不因冷启动超时
    if _s.llm_warmup_enabled and _s.llm_base_url:
        await asyncio.to_thread(_warmup_llm_sync)
    # Embedding/Reranker/OCR 预热（仅题目提取可关闭以加快启动）
    if _s.warmup_embedding_rerank_ocr_enabled:
        await asyncio.to_thread(_warmup_embedding_rerank_sync)


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI 停止时关闭调度器，并优雅终止批量提取子进程、持久化进度"""
    global _batch_extract_proc
    if _batch_extract_proc is not None and _batch_extract_proc.poll() is None:
        try:
            _BATCH_EXTRACT_ABORT_FILE.write_text("1", encoding="utf-8")
        except OSError:
            pass
        await asyncio.sleep(2)
        try:
            _batch_extract_proc.terminate()
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _batch_extract_proc.wait),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, OSError):
            try:
                _batch_extract_proc.kill()
            except OSError:
                pass
        try:
            with open(_BATCH_EXTRACT_STATE_FILE, "r", encoding="utf-8") as f:
                import json
                state = json.load(f)
            start_offset = state.get("log_start_offset", 0)
            _lp = state.get("log_path")
            log_path = Path(_lp) if _lp else _BACKEND_LOGS / "batch_extract.log"
            completed = _parse_completed_from_log(log_path, start_offset)
            _save_batch_extract_state(
                state.get("task_ids", []),
                state.get("total", 0),
                start_offset,
                completed=completed,
                interrupted_at=__import__("datetime").datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                log_path=_lp or str(log_path.resolve()),
            )
            logger.info(
                f"[Shutdown] 批量提取已保存进度：已完成 {len(completed)}/{state.get('total', 0)}，重启后可恢复"
            )
        except (OSError, ValueError) as e:
            logger.warning("[Shutdown] 保存批量提取进度失败: %s", e)
        _batch_extract_proc = None
    crawl_scheduler.stop()


@app.get("/", include_in_schema=False)

@app.get("/app", include_in_schema=False)

async def serve_frontend():

    """生产模式：返回 Vite 构建产物 index.html"""

    from fastapi.responses import FileResponse

    dist_index = _PROJECT_ROOT / "backend" / "static" / "dist" / "index.html"

    if dist_index.exists():

        return FileResponse(str(dist_index))

    return {"message": "前端未构建，请在 web/ 目录执行 npm run build，或用 npm run dev 开发模式访问 http://localhost:5173"}





@app.get("/api/config")
def get_config():
    """前端配置：默认用户 ID、Agent 最大步数、爬虫/OCR 来源等（来自 .env）"""
    from backend.config.config import settings as _s
    from backend.services.crawler.task_executor import get_source_info
    return {
        "default_user_id": _s.default_user_id,
        "default_session_id": _s.default_session_id,
        "interviewer_max_steps": _s.interviewer_max_steps,
        "crawler_process_batch_size": _s.crawler_process_batch_size,
        "crawler_source": _s.crawler_source,
        "ocr_method": _s.ocr_method,
        "source_info": get_source_info(),
    }





def _extract_user_display_content(content: str) -> str:
    """从后端存储的完整输入中提取用户实际内容，供前端展示"""
    if not content or "[用户消息]" not in content:
        return content or ""
    # 格式: ... [用户消息]\n用户实际内容
    idx = content.find("[用户消息]")
    after = content[idx + len("[用户消息]"):].lstrip("\n\r")
    return after if after else content


def _strip_internal_markers_for_display(content: str) -> str:
    """移除用户消息中的内部标记（如【q_id:xxx】），不展示给用户"""
    if not content:
        return content
    import re
    # 移除 【q_id:uuid】 格式
    return re.sub(r'【q_id:[^\】]+】', '', content).replace('  ', ' ').strip()



def _normalize_thinking_for_frontend(thinking_raw) -> list:
    """
    将 DB 存储的 thinking 数据规范化为前端期望的格式：
      [{__step, thought, tools:[{name,args,result,observation,observationIsJson}]}]
    兼容旧格式（带 🔧 前缀、用 observation 字段、缺少 result 等）
    """
    import json as _json

    def _is_json(s):
        if not s or not isinstance(s, str):
            return False
        s = s.strip()
        if not (s.startswith("{") or s.startswith("[")):
            return False
        try:
            _json.loads(s)
            return True
        except Exception:
            return False

    if not isinstance(thinking_raw, list):
        return []
    result = []
    for idx, step in enumerate(thinking_raw):
        if not isinstance(step, dict):
            continue
        raw_tools = step.get("tools") or []
        tools = []
        for t in raw_tools:
            if not isinstance(t, dict):
                continue
            name = t.get("name", "") or ""
            # 去除 🔧 及各种 emoji 前缀
            name = name.strip()
            for prefix in ["🔧 ", "🔧", "\U0001f527 ", "\U0001f527"]:
                if name.startswith(prefix):
                    name = name[len(prefix):].strip()
            obs = t.get("result") or t.get("observation") or ""
            obs_str = str(obs) if obs else ""
            tools.append({
                "name": name,
                "args": t.get("args") or {},
                "result": obs_str,
                "observation": obs_str,
                "observationIsJson": _is_json(obs_str),
            })
        # 兼容旧格式：step.action + step.toolArgs + step.observation
        if not tools and step.get("action"):
            obs = step.get("observation") or step.get("result") or ""
            obs_str = str(obs) if obs else ""
            action_name = str(step.get("action", "")).replace("🔧", "").strip()
            tools.append({
                "name": action_name,
                "args": step.get("toolArgs") or {},
                "result": obs_str,
                "observation": obs_str,
                "observationIsJson": _is_json(obs_str),
            })
        # 兼容更旧/不完整格式：只有 step.thought + step.observation/result，但没有 tools/action
        # 这种情况下前端只能展示推理，不会展示“工具调用”块；这里补一个占位工具让 UI 可展开显示。
        if not tools:
            obs = step.get("observation") or step.get("result") or ""
            obs_str = str(obs) if obs else ""
            if obs_str.strip():
                tools.append({
                    "name": "（占位）工具",
                    "args": {},
                    "result": obs_str,
                    "observation": obs_str,
                    "observationIsJson": _is_json(obs_str),
                })
        result.append({
            "__step": step.get("__step", idx + 1),
            "thought": step.get("thought", ""),
            "tools": tools,
        })
    return result


def _parse_iso_dt(v):
    from datetime import datetime as _dt
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    try:
        d = _dt.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is not None:
            d = d.astimezone().replace(tzinfo=None)
        return d
    except Exception:
        return None


def _load_tool_logs_for_user_session(user_id: str, session_id: str):
    import json as _json
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parent / "interviewer_logs"
    if not root.exists():
        return []
    items = []
    for p in root.rglob("tools_*.jsonl"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = _json.loads(line)
                    except Exception:
                        continue
                    if rec.get("user_id") != user_id or rec.get("session_id") != session_id:
                        continue
                    ts = _parse_iso_dt(rec.get("timestamp"))
                    if ts is None:
                        continue
                    items.append({
                        "ts": ts,
                        "name": str(rec.get("tool_name") or "").strip() or "（占位）工具",
                        "args": rec.get("tool_input") if isinstance(rec.get("tool_input"), dict) else {},
                        "result": str(rec.get("tool_output") or ""),
                    })
        except Exception:
            continue
    items.sort(key=lambda x: x["ts"])
    return items


def _attach_placeholder_tools_from_logs(messages: list, user_id: str, session_id: str):
    """
    当 assistant 缺失 thinking 时，按时间窗口将 tools_*.jsonl 工具调用补成占位步骤。
    仅用于历史展示，不回写数据库。
    """
    if not messages:
        return
    tool_logs = _load_tool_logs_for_user_session(user_id, session_id)
    if not tool_logs:
        return

    used = set()
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        if m.get("thinking"):
            continue
        asst_ts = _parse_iso_dt(m.get("timestamp"))
        if asst_ts is None:
            continue

        prev_user_ts = None
        for j in range(i - 1, -1, -1):
            if messages[j].get("role") == "user":
                prev_user_ts = _parse_iso_dt(messages[j].get("timestamp"))
                break
        next_user_ts = None
        for j in range(i + 1, len(messages)):
            if messages[j].get("role") == "user":
                next_user_ts = _parse_iso_dt(messages[j].get("timestamp"))
                break

        picked_idx = []
        for ti, t in enumerate(tool_logs):
            if ti in used:
                continue
            tts = t["ts"]
            if prev_user_ts and tts < prev_user_ts:
                continue
            if next_user_ts and tts >= next_user_ts:
                continue
            # 允许 assistant 时间后 90 秒内到达，覆盖异步刷库延迟
            if tts > asst_ts:
                delta = (tts - asst_ts).total_seconds()
                if delta > 90:
                    continue
            picked_idx.append(ti)

        if not picked_idx:
            continue

        tools = []
        for ti in picked_idx:
            t = tool_logs[ti]
            obs = t["result"] or ""
            obs_is_json = False
            s = obs.strip()
            if s.startswith("{") or s.startswith("["):
                import json as _json
                try:
                    _json.loads(s)
                    obs_is_json = True
                except Exception:
                    pass
            tools.append({
                "name": t["name"] or "（占位）工具",
                "args": t["args"] or {},
                "result": obs,
                "observation": obs,
                "observationIsJson": obs_is_json,
            })
            used.add(ti)

        if tools:
            m["thinking"] = [{"__step": 1, "thought": "", "tools": tools}]


def _load_history_from_session_store(user_id: str, session_id: str) -> list:
    """
    从 InterviewerAgent 的 session_store 读取会话历史（与 chat load/save 同源）。
    读取失败时返回空列表。
    """
    try:
        _store = getattr(orchestrator, "session_store", None)
        if _store is None:
            return []
        payload = _store.load(f"{user_id}:{session_id}")
        history = payload.get("history") if isinstance(payload, dict) else []
        return history if isinstance(history, list) else []
    except Exception:
        return []

@app.get("/")

def root():

    return {"status": "ok", "message": "面经 Agent API 运行中", "docs": "/docs"}





@app.get("/api/health")

def health():

    return {"status": "ok"}


def _normalize_circuit_status(status_obj: Any) -> Dict[str, Any]:
    if isinstance(status_obj, dict):
        return {
            "state": status_obj.get("state"),
            "failure_count": status_obj.get("failure_count"),
            "open_since": status_obj.get("open_since"),
            "recover_in_seconds": status_obj.get("recover_in_seconds"),
        }
    return {"raw": str(status_obj)}


def _collect_registry_circuit_status(registry: Any) -> Dict[str, Any]:
    cb = getattr(registry, "circuit_breaker", None) if registry is not None else None
    if cb is None:
        return {"available": False, "reason": "circuit_breaker_not_found"}
    get_all = getattr(cb, "get_all_status", None)
    if not callable(get_all):
        return {"available": False, "reason": "get_all_status_not_supported"}
    try:
        raw = get_all() or {}
        if not isinstance(raw, dict):
            return {"available": True, "tools": {}, "raw": str(raw)}
        tools = {name: _normalize_circuit_status(st) for name, st in raw.items()}
        return {"available": True, "tools": tools}
    except Exception as e:
        return {"available": False, "reason": f"read_failed: {e}"}


@app.get("/api/agents/circuit-breaker/status")
def get_agents_circuit_breaker_status():
    """查看各 Agent 工具熔断状态（open/closed、失败次数、恢复倒计时）。"""
    from backend.services.crawler.question_extractor import get_latest_miner_runtime_handles

    interviewer_registry = getattr(orchestrator, "tool_registry", None)
    miner_handles = get_latest_miner_runtime_handles()
    miner_agent = miner_handles.get("miner_agent")
    two_stage_extractor = miner_handles.get("two_stage_extractor")

    miner_registry = getattr(miner_agent, "tool_registry", None) if miner_agent else None
    two_stage_registry = getattr(two_stage_extractor, "_registry", None) if two_stage_extractor else None

    return {
        "status": "ok",
        "generated_at": now_beijing_str(),
        "agents": {
            "interviewer": _collect_registry_circuit_status(interviewer_registry),
            "miner": _collect_registry_circuit_status(miner_registry) if miner_registry else {
                "available": False,
                "reason": "miner_not_initialized_yet",
            },
            "two_stage_stage1": _collect_registry_circuit_status(two_stage_registry) if two_stage_registry else {
                "available": False,
                "reason": "two_stage_not_initialized_yet",
            },
        },
    }





# ══════════════════════════════════════════════════════

# 题库浏览 API

# ══════════════════════════════════════════════════════



@app.get("/api/questions")
def get_questions(
    company: Optional[str] = Query(None, description="公司名，模糊匹配"),
    position: Optional[str] = Query(None, description="岗位，模糊匹配"),
    difficulty: Optional[str] = Query(None, description="难度：easy/medium/hard"),
    question_type: Optional[str] = Query(None, description="题目类型小类：算法-/工程-/基础-/软技能-/AI-*（见 /api/questions/meta 下拉）"),
    tag: Optional[str] = Query(None, description="技术标签，如 Redis"),
    keyword: Optional[str] = Query(None, description="关键词，搜索题目文本"),
    source_platform: Optional[str] = Query(None, description="来源平台：nowcoder/xiaohongshu"),
    rand: bool = Query(False, description="true 时随机返回"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页题目数量"),
    sort_by: Optional[str] = Query(
        None,
        description="排序字段：created_at/difficulty/company/question_type/question_text/next_review_at（待复习时间，需 user_id）",
    ),
    sort_order: Optional[str] = Query(None, description="排序方向：asc/desc"),
    user_id: Optional[str] = Query(None, description="用户ID，传入时在题目中附加该用户最近作答得分"),
):
    """
    题库浏览接口（纯 SQL 过滤，不调用 LLM）。
    支持：按公司/岗位/难度/标签/关键词过滤，支持随机返回，支持分页。
    """
    import json as _json
    import math as _math
    tags = [tag] if tag else None

    if rand:
        results = sqlite_service.filter_questions(
            company=company, position=position, difficulty=difficulty,
            question_type=question_type, tags=tags, keyword=keyword,
            source_platform=source_platform, limit=200, offset=0
        )
        random.shuffle(results)
        results = results[:1]
        total = len(results)
        total_pages = 1
        cur_page = 1
        cur_page_size = 1
    else:
        offset = (page - 1) * page_size
        total = sqlite_service.count_questions(
            company=company, position=position, difficulty=difficulty,
            question_type=question_type, tags=tags, keyword=keyword,
            source_platform=source_platform
        )
        results = sqlite_service.filter_questions(
            company=company, position=position, difficulty=difficulty,
            question_type=question_type, tags=tags, keyword=keyword,
            source_platform=source_platform, limit=page_size, offset=offset,
            sort_by=sort_by or "created_at", sort_order=sort_order or "desc",
            user_id=user_id,
        )
        total_pages = _math.ceil(total / page_size) if page_size > 0 else 1
        cur_page = page
        cur_page_size = page_size

    # 解析 topic_tags JSON 字符串
    for r in results:
        try:
            r["topic_tags"] = _json.loads(r.get("topic_tags") or "[]")
        except Exception:
            r["topic_tags"] = []

    # 附加用户作答评分记录（最近一次得分）
    if user_id and results:
        q_ids = [r.get("q_id") for r in results if r.get("q_id")]
        scores_map = sqlite_service.get_latest_scores_for_questions(user_id, q_ids)
        for r in results:
            qid = r.get("q_id")
            if qid and qid in scores_map:
                r["last_score"] = scores_map[qid]["score"]
                r["last_studied_at"] = scores_map[qid]["studied_at"]
                nra = scores_map[qid].get("next_review_at")
                if nra is not None and nra != "":
                    r["next_review_at"] = nra

    return {
        "total": total,
        "page": cur_page,
        "page_size": cur_page_size,
        "total_pages": total_pages,
        "questions": results,
    }





@app.get("/api/questions/random")

def get_random_question(

    tag: Optional[str] = Query(None),

    difficulty: Optional[str] = Query(None),

    company: Optional[str] = Query(None),

    question_type: Optional[str] = Query(None),

):

    """随机返回一道题（用于练习开始时出题）"""

    import json

    tags = [tag] if tag else None

    results = sqlite_service.filter_questions(

        tags=tags, difficulty=difficulty, company=company,

        question_type=question_type, limit=50

    )

    if not results:

        raise HTTPException(status_code=404, detail="没有符合条件的题目")

    q = random.choice(results)

    try:

        q["topic_tags"] = json.loads(q.get("topic_tags") or "[]")

    except Exception:

        q["topic_tags"] = []

    return q


@app.get("/api/questions/smart-practice")
def get_smart_practice_questions(
    user_id: Optional[str] = Query(None, description="用户ID，必填时启用薄弱点+复习召回"),
    limit: int = Query(20, ge=1, le=50, description="每批题目数量上限（实际条数由 .env 知识点不足+随机数决定）"),
    company: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    source_platform: Optional[str] = Query(None),
):
    """
    智能练习：知识点不足 N 条（薄弱点+遗忘曲线多路召回+ Reranker）+ 随机 M 条。
    召回条数 = N * SMART_PRACTICE_RECALL_RATIO，所有参数见 .env 中 SMART_PRACTICE_*。
    """
    import json as _json
    tags = [tag] if tag else None
    uid = user_id or "user_001"
    questions, is_review_mode = multi_recall_recommender.recommend_smart_practice(
        user_id=uid,
        company=company,
        difficulty=difficulty,
        question_type=question_type,
        tags=tags,
        source_platform=source_platform,
    )
    if limit < len(questions):
        questions = questions[:limit]
    for q in questions:
        try:
            q["topic_tags"] = _json.loads(q.get("topic_tags") or "[]")
        except Exception:
            q["topic_tags"] = []
    stats = sqlite_service.get_practice_stats(uid)
    if uid and questions:
        q_ids = [q.get("q_id") for q in questions if q.get("q_id")]
        scores_map = sqlite_service.get_latest_scores_for_questions(uid, q_ids)
        for q in questions:
            qid = q.get("q_id")
            if qid and qid in scores_map:
                q["last_score"] = scores_map[qid]["score"]
                q["last_studied_at"] = scores_map[qid]["studied_at"]
    return {
        "questions": questions,
        "total_in_batch": len(questions),
        "is_review_mode": is_review_mode,
        "practiced_count": stats["practiced_count"],
        "total_count": stats["total_count"],
        "all_learned": stats["all_learned"],
    }


@app.get("/api/questions/meta")

def get_questions_meta():

    """

    返回题库中存在的公司列表、标签列表、难度列表。

    用于前端筛选下拉框。

    """

    import json

    import sqlite3

    db_path = sqlite_service.db_path



    with sqlite3.connect(db_path) as conn:

        companies = [row[0] for row in

                     conn.execute("SELECT DISTINCT company FROM questions WHERE company IS NOT NULL AND company != '' ORDER BY company").fetchall()]

        positions = [row[0] for row in

                     conn.execute("SELECT DISTINCT position FROM questions WHERE position IS NOT NULL AND position != '' ORDER BY position").fetchall()]

        platforms = [row[0] for row in

                     conn.execute("SELECT DISTINCT source_platform FROM questions WHERE source_platform IS NOT NULL AND source_platform != '' ORDER BY source_platform").fetchall()]

        difficulties = ["easy", "medium", "hard"]

        question_types = [row[0] for row in

                         conn.execute("SELECT DISTINCT question_type FROM questions WHERE question_type IS NOT NULL AND question_type != '' ORDER BY question_type").fetchall()]

        if not question_types:
            from backend.agents.schemas.miner_schema import ALLOWED_QUESTION_TYPES

            question_types = sorted(ALLOWED_QUESTION_TYPES)



        # 从所有题目的 topic_tags JSON 数组里聚合

        raw_tags = conn.execute("SELECT topic_tags FROM questions WHERE topic_tags IS NOT NULL AND topic_tags != '[]'").fetchall()

        all_tags = set()

        for (t,) in raw_tags:

            try:

                for tag in json.loads(t):

                    all_tags.add(tag)

            except Exception:

                pass



        # 统计总题数

        total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]



    return {

        "total": total,

        "companies": companies,

        "positions": positions,

        "platforms": platforms,

        "difficulties": difficulties,

        "question_types": question_types,

        "tags": sorted(all_tags),

    }





@app.get("/api/questions/{q_id}")

def get_question_detail(q_id: str):

    """获取单题详情"""

    import json

    results = sqlite_service.filter_questions(limit=1)  # fallback

    # 直接查 sqlite

    import sqlite3

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute("SELECT * FROM questions WHERE q_id = ?", (q_id,)).fetchone()

    if not row:

        raise HTTPException(status_code=404, detail="题目不存在")

    q = dict(row)

    try:

        q["topic_tags"] = json.loads(q.get("topic_tags") or "[]")

    except Exception:

        q["topic_tags"] = []

    return q


@app.get("/api/posts/{crawl_task_id}")
def get_post_by_crawl_task_id(crawl_task_id: int):
    """根据 crawl_task_id（crawl_tasks.id）获取原帖子信息，用于「查看原帖」"""
    import sqlite3
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, task_id, source_url, source_platform, post_title, company, position FROM crawl_tasks WHERE id = ?",
            (crawl_task_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return dict(row)


# ══════════════════════════════════════════════════════

# 面试对话 API

# ══════════════════════════════════════════════════════



def _is_retryable_error(e: Exception) -> bool:

    """连接/超时类错误可重试（冷启动时 LLM 可能尚未就绪）"""

    err = str(e).lower()

    return any(x in err for x in ["timeout", "connection", "refused", "reset", "econnrefused"])





@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """
    自由对话接口：出题、解释、换个问法、查看掌握度等。
    答题评估请使用 /api/submit_answer。
    超时 90 秒；连接/超时错误会自动重试 2 次。
    """
    import logging as _logging
    from backend.config.config import settings as _settings
    _user_id = (req.user_id or "").strip() or _settings.default_user_id
    _session_id = (req.session_id or "").strip() or None
    if _session_id is None:
        _session_id = _settings.default_session_id
    _chat_logger = _logging.getLogger("chat")
    _chat_logger.info(f"[Chat ←] user={_user_id} | {req.message[:120]}")

    last_err = None
    for attempt in range(3):
        try:
            reply, thinking_steps = await asyncio.wait_for(
                orchestrator.chat(
                    user_id=_user_id,
                    message=req.message,
                    resume=req.resume,
                    session_id=_session_id
                ),
                timeout=float(_settings.interviewer_timeout),
            )

            _chat_logger.info(

                f"[Chat →] user={_user_id} | reply({len(reply)}chars): "

                f"{reply}"

            )

            return {"reply": reply, "thinking": thinking_steps}

        except asyncio.TimeoutError as e:

            last_err = e

            if attempt < 2:

                _chat_logger.warning(f"[Chat] 超时，重试 {attempt + 2}/3...")

                await asyncio.sleep(2)

            else:

                _chat_logger.error(f"[Chat ✗] user={_user_id} TIMEOUT {_settings.interviewer_timeout}s")

                return {"reply": f"⚠️ 响应超时（{_settings.interviewer_timeout}s），LLM 服务可能繁忙，请稍后重试。", "error": "timeout"}

        except Exception as e:

            last_err = e

            err_msg = str(e)

            if attempt < 2 and _is_retryable_error(e):

                _chat_logger.warning(f"[Chat] 连接错误，重试 {attempt + 2}/3: {err_msg[:80]}")

                await asyncio.sleep(2)

                continue

            _chat_logger.error(f"[Chat ✗] user={_user_id} error: {err_msg[:300]}")

            if "429" in err_msg or "SetLimitExceeded" in err_msg or "TooManyRequests" in err_msg:

                return {"reply": "⚠️ LLM 接口调用超出限额（429）。请前往火山引擎控制台 → 模型推理 → 安全体验模式，关闭或调整限制后重试。", "error": "rate_limit"}

            if "LLM调用失败" in err_msg or "api" in err_msg.lower() or "connection" in err_msg.lower():

                return {"reply": f"⚠️ LLM 接口调用失败，请检查 API Key 和网络连接：{err_msg[:200]}", "error": "llm_error"}

            return {"reply": f"⚠️ 内部错误：{err_msg[:200]}", "error": "server_error"}





@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    """
    流式对话接口（SSE）：使用 hello_agents arun_stream() 实现真实 token 级流式。
    连接/超时错误会自动重试 2 次。
    """
    import logging as _logging
    from backend.config.config import settings as _settings
    # 未传或空 user_id 时使用配置的默认用户（与 /api/config 的 default_user_id 一致，如 Wangxr）
    _user_id = (req.user_id or "").strip() or _settings.default_user_id
    _session_id = (req.session_id or "").strip() or None
    if _session_id is None:
        _session_id = _settings.default_session_id
    _chat_logger = _logging.getLogger("chat")
    _chat_logger.info(f"[Stream ←] user={_user_id} | {req.message[:]}")

    async def generate():
        # 用后台生产者 + 队列解耦 HTTP 连接生命周期。
        # 即使前端刷新/断开，生产者仍可继续完成本轮对话并落库，避免“被打断”。
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def _producer():
            for attempt in range(3):
                try:
                    _chat_logger.info(f"[Stream] 使用 arun_stream，attempt={attempt+1}")
                    async for sse_line in orchestrator.chat_stream(
                        user_id=_user_id,
                        message=req.message,
                        resume=req.resume,
                        session_id=_session_id,
                    ):
                        if isinstance(sse_line, str):
                            if not sse_line.endswith('\n\n'):
                                sse_line += '\n\n'
                            await queue.put(sse_line.encode('utf-8'))
                        else:
                            await queue.put(sse_line)
                    _chat_logger.info("[Stream →] 完成")
                    break
                except asyncio.TimeoutError:
                    if attempt < 2:
                        _chat_logger.warning(f"[Stream] 超时，重试 {attempt + 2}/3...")
                        await asyncio.sleep(2)
                    else:
                        await queue.put(
                            f"data: {json.dumps({'error': f'⚠️ 响应超时（{_settings.interviewer_timeout}s），LLM 服务可能繁忙，请稍后重试'}, ensure_ascii=False)}\n\n".encode("utf-8")
                        )
                except Exception as e:
                    err_str = str(e)
                    if attempt < 2 and _is_retryable_error(e):
                        _chat_logger.warning(f"[Stream] 连接错误，重试 {attempt + 2}/3: {err_str[:80]}")
                        await asyncio.sleep(2)
                        continue
                    if "429" in err_str or "SetLimitExceeded" in err_str or "TooManyRequests" in err_str:
                        msg = (
                            "⚠️ **API 限额已到**（429 SetLimitExceeded）\n\n"
                            "原因：火山引擎「安全体验模式」限制了每日调用次数。\n\n"
                            "**解决方法**（两步）：\n"
                            "1. 打开 https://console.volcengine.com/\n"
                            "2. 进入「模型推理」→「安全体验模式」→ 关闭或调高限制\n\n"
                            "关闭后刷新页面即可恢复正常使用。"
                        )
                        await queue.put(f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n".encode("utf-8"))
                    else:
                        await queue.put(
                            f"data: {json.dumps({'error': f'⚠️ 错误：{err_str[:300]}'}, ensure_ascii=False)}\n\n".encode("utf-8")
                        )
                    break
            await queue.put(sentinel)

        producer_task = asyncio.create_task(_producer())
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield item
        except asyncio.CancelledError:
            _chat_logger.warning("[Stream] 客户端连接断开：后台继续生成并保存本轮结果")
            raise
        finally:
            # 关键：不要在这里取消 producer_task，允许其在客户端断开后继续跑完。
            if producer_task.done():
                try:
                    producer_task.result()
                except Exception as e:
                    _chat_logger.error(f"[Stream] 后台生产者异常: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )





# 全局存储：评分任务状态 {task_id: {status, result, error}}
_submit_answer_tasks: Dict[str, Dict[str, Any]] = {}



@app.post("/api/submit_answer/stream")
async def api_submit_answer_stream(req: SubmitAnswerRequest):
    """
    答题提交接口（SSE 流式，确定性评分）：
    直接调用 InterviewerAgent.submit_answer() 确定性方法完成评估、入库、SM-2。
    不走 ReAct LLM 循环，避免评分不一致和 DSML 泄漏问题。
    返回两个 SSE 事件：evaluating（进行中）+ eval_result（最终结果）。
    """
    from backend.config.config import settings as _settings
    _uid = (req.user_id or "").strip() or _settings.default_user_id
    _session_id = (req.session_id or "").strip() or _settings.default_session_id
    _question_id = (req.question_id or "").strip()
    _question_text = (req.question_text or "").strip()
    _user_answer = (req.user_answer or "").strip()
    _question_tags = req.question_tags or []

    if not _question_id or not _user_answer:
        async def _err_gen():
            yield json.dumps({"error": "question_id 和 user_answer 不能为空"}, ensure_ascii=False).encode()
        return StreamingResponse(_err_gen(), media_type="text/event-stream")

    async def generate():
        # 1. 推送「评分中」状态，让前端立即显示 loading
        yield ("data: " + json.dumps({"type": "evaluating", "message": "正在评分中..."}, ensure_ascii=False) + "\n\n").encode("utf-8")
        try:
            # 2. 走确定性评分路径（不走 ReAct 循环）
            result = await orchestrator.submit_answer(
                user_id=_uid,
                session_id=_session_id,
                question_id=_question_id,
                question_text=_question_text,
                user_answer=_user_answer,
                question_tags=_question_tags,
            )
            # 3. 推送最终评分结果
            payload = {
                "type": "eval_result",
                "score": result.get("score", 0),
                "feedback": result.get("feedback", ""),
                "strong_points": result.get("strong_points", []),
                "missed_points": result.get("missed_points", []),
                "error_points": result.get("error_points", []),
                "shortcomings": result.get("shortcomings", []),
                "standard_answer": result.get("standard_answer", ""),
                "explanation": result.get("explanation", ""),
                "tags": result.get("tags", []),
            }
            yield ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
            logger.info(f"[submit_answer/stream] 确定性评分完成 q={_question_id} score={result.get('score')}")
        except Exception as e:
            err_str = str(e)
            logger.error(f"[submit_answer/stream] 评分失败: {err_str[:200]}")
            yield ("data: " + json.dumps({"error": f"⚠️ 评分失败：{err_str[:200]}"}, ensure_ascii=False) + "\n\n").encode("utf-8")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/submit_answer")
async def api_submit_answer(req: SubmitAnswerRequest):
    """
    答题提交接口：直接记录作答，不调用 LLM 评估。
    评估由 Agent（/api/submit_answer/stream 或 /api/chat/stream）负责。
    """
    from backend.config.config import settings as _settings
    from backend.services.storage.sqlite_service import sqlite_service as _sqlite
    _uid = (req.user_id or "").strip() or _settings.default_user_id
    _session_id = (req.session_id or "").strip() or _settings.default_session_id
    _question_id = (req.question_id or "").strip()
    _user_answer = (req.user_answer or "").strip()

    if not _question_id or not _user_answer:
        raise HTTPException(status_code=400, detail="question_id 和 user_answer 不能为空")

    task_id = f"eval_{_question_id}_{int(time.time() * 1000)}"

    try:
        sm2 = _sqlite.add_study_record(
            user_id=_uid,
            question_id=_question_id,
            score=0.0,
            user_answer=_user_answer,
            ai_feedback="已记录作答，待 Agent 评估。",
            session_id=_session_id,
            message_id=task_id,
            eval_details={},
        )
        tags = req.question_tags or []
        if tags:
            try:
                _sqlite.update_tag_mastery(_uid, tags, 0)
            except Exception:
                pass
        result = {
            "task_id": task_id,
            "status": "completed",
            "score": 0.0,
            "feedback": "已记录作答，请在对话中让 AI 为你评估。",
            "sm2": sm2,
            "message": "作答已记录。",
        }
        logger.info(f"[submit_answer] 任务 {task_id} 记录完成（无评估）")
        return result
    except Exception as e:
        err_msg = str(e)
        logger.error(f"[submit_answer] 任务 {task_id} 失败: {err_msg[:200]}")
        raise HTTPException(status_code=500, detail=err_msg[:300])


@app.get("/api/submit_answer/status/{task_id}")
async def api_submit_answer_status(task_id: str):
    """
    查询答题评分任务状态。
    前端轮询此接口，直到 status 为 completed 或 failed。
    """
    if task_id not in _submit_answer_tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    task = _submit_answer_tasks[task_id]
    
    if task["status"] == "evaluating":
        return {
            "task_id": task_id,
            "status": "evaluating",
            "message": "正在评分中..."
        }
    elif task["status"] == "completed":
        return {
            "task_id": task_id,
            "status": "completed",
            "result": task["result"]
        }
    else:  # failed
        return {
            "task_id": task_id,
            "status": "failed",
            "error": task["error"]
        }





@app.post("/api/session/end")

async def api_end_session(req: EndSessionRequest):

    """结束 session，触发记忆整合"""

    await orchestrator.end_session(

        user_id=req.user_id,

        session_id=req.session_id,

        session_summary=req.session_summary

    )

    return {"status": "ok", "message": "Session 已结束，记忆已整合"}





# ══════════════════════════════════════════════════════

# 用户数据 API

# ══════════════════════════════════════════════════════



@app.get("/api/user/{user_id}/mastery")

def get_user_mastery(user_id: str):

    """获取用户标签掌握度报告"""

    summary = sqlite_service.get_mastery_summary(user_id)

    weak_tags = sqlite_service.get_weak_tags(user_id)

    history = sqlite_service.get_study_history(user_id, limit=10)

    weakness_notes = sqlite_service.get_user_weakness_notes(user_id, limit=20)

    profile = sqlite_service.get_user_profile(user_id)

    # 兼容前端 ReportView 期望的字段（total_answered, mastered_count, mastery_by_level）
    total = (summary or {}).get("total_questions_practiced", 0)
    rate = (summary or {}).get("correct_rate", 0) or 0
    correct = int(total * rate / 100) if total else 0
    return {
        "user_id": user_id,
        "profile": profile,
        "mastery_summary": summary,
        "mastery_by_level": (summary or {}).get("by_level", {}),
        "weak_tags": weak_tags,
        "recent_history": history,
        "weakness_notes": weakness_notes,
        "total_answered": total,
        "mastered_count": correct,
    }





@app.get("/api/user/{user_id}/reviews")

def get_due_reviews(user_id: str, limit: int = 10):

    """获取 SM-2 到期需要复习的题目"""

    due = sqlite_service.get_due_reviews(user_id, limit=limit)

    return {"user_id": user_id, "due_count": len(due), "questions": due}


@app.get("/api/user/{user_id}/practice-stats")
def get_practice_stats(user_id: str):
    """获取练习统计：已练题目数（去重）、题库总数、是否全学完"""
    return sqlite_service.get_practice_stats(user_id)


@app.get("/api/user/{user_id}/tool-usage")
def get_user_tool_usage(user_id: str, days: int = Query(365, ge=1, le=3650, description="统计最近 N 天的工具调用")):
    """统计 Agent 工具调用（运行时实时统计，按 agent 聚合）"""
    from backend.services.logging.interviewer_tool_usage import get_interviewer_tool_usage as _get_interviewer_tool_usage

    return _get_interviewer_tool_usage(user_id=user_id, days=days)


@app.get("/api/user/{user_id}/graph-rag")
def get_user_graph_rag(
    user_id: str,
    max_bank_tags: int = Query(80, ge=20, le=200, description="题库图最多展示的标签节点数"),
    max_record_questions: int = Query(80, ge=10, le=200, description="做题图最多展示的题目节点数"),
):
    """GraphRAG 可视化数据：题库知识图 + 用户做题记录图。"""
    return sqlite_service.get_graph_rag_data(
        user_id=user_id,
        max_bank_tags=max_bank_tags,
        max_record_questions=max_record_questions,
    )


@app.get("/api/user/{user_id}/questions/{question_id}/study-records")
def get_question_study_records(
    user_id: str,
    question_id: str,
    limit: int = Query(20, ge=1, le=50, description="最多返回条数"),
):
    """获取某用户对某题的历史作答记录（得分、回答、要点等）"""
    return sqlite_service.get_study_records_by_question(user_id, question_id, limit=limit)

@app.get("/api/user/{user_id}/chat/history")
def get_chat_history(
    user_id: str,
    session_id: str | None = Query(None, description="可选。指定会话 ID；不传则取默认/最近会话"),
):
    """获取用户对话历史：优先读取 .env 默认会话，不存在再回退到用户最近一次会话。"""
    import re as _re
    from datetime import datetime as _dt, timedelta as _td
    from backend.config.config import settings as _settings
    fixed_session_id = _settings.default_session_id
    preferred_session_id = (session_id or "").strip()
    if preferred_session_id:
        session = sqlite_service.get_session(preferred_session_id)
        if session and session.get("user_id") != user_id:
            session = None
    else:
        session = sqlite_service.get_session(fixed_session_id)
        if not session or session.get("user_id") != user_id:
            session = sqlite_service.get_latest_session_for_user(user_id)
    if not session:
        return {"messages": [], "session_id": None}

    raw_history = session.get("conversation_history") or []
    session_id = session.get("session_id")
    ss_history = _load_history_from_session_store(user_id, session_id or fixed_session_id)
    if len(ss_history) > len(raw_history):
        raw_history = ss_history

    messages = []
    base_time = _dt.now()
    for msg in raw_history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "") or ""
        content = msg.get("content", "") or ""
        if role == "user":
            # 去掉【q_id:xxx】等内部标记
            content = _re.sub(r"【q_id:[^】]*】", "", content).strip()
            # 如果有 [用户消息] 格式，只保留用户部分
            if "\n[用户消息]\n" in content:
                content = content.split("\n[用户消息]\n", 1)[-1].strip()
            elif content.startswith("[系统]"):
                lines = content.split("\n")
                content = "\n".join(
                    l for l in lines
                    if not l.startswith("[系统]") and not l.startswith("[Task]") and not l.startswith("[Output]")
                ).strip()
        if not content and role != "assistant":
            continue
        out = {
            "role": role,
            "content": content,
            "timestamp": msg.get("timestamp") or msg.get("ts") or "",
        }
        if not out["timestamp"]:
            out["timestamp"] = (base_time - _td(minutes=max(0, len(raw_history) - len(messages)))).isoformat()
        if msg.get("thinking"):
            # 🔧 规范化 thinking 数据，确保格式一致
            out["thinking"] = _normalize_thinking_for_frontend(msg["thinking"])
        if msg.get("duration_ms") is not None:
            out["duration_ms"] = msg["duration_ms"]
        messages.append(out)
    # 历史兜底：若 assistant 没有 thinking，则按同时间段 tools 日志补占位工具调用
    _attach_placeholder_tools_from_logs(messages, user_id=user_id, session_id=session_id or fixed_session_id)
    return {"messages": messages, "session_id": session_id}


@app.get("/api/user/{user_id}/chat/history/all")
def get_all_chat_history(user_id: str):
    """获取用户所有对话历史（所有会话）"""
    import re as _re
    from datetime import datetime as _dt, timedelta as _td
    
    # 获取该用户的所有会话
    all_sessions = sqlite_service.get_all_sessions_for_user(user_id)
    if not all_sessions:
        return {"messages": [], "total_sessions": 0}
    
    all_messages = []
    base_time = _dt.now()
    
    # 遍历所有会话，合并消息
    for session in all_sessions:
        raw_history = session.get("conversation_history") or []
        session_id = session.get("session_id")
        ss_history = _load_history_from_session_store(user_id, session_id or "")
        if len(ss_history) > len(raw_history):
            raw_history = ss_history
        
        for msg in raw_history:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "") or ""
            content = msg.get("content", "") or ""
            if role == "user":
                # 去掉【q_id:xxx】等内部标记
                content = _re.sub(r"【q_id:[^】]*】", "", content).strip()
                # 如果有 [用户消息] 格式，只保留用户部分
                if "\n[用户消息]\n" in content:
                    content = content.split("\n[用户消息]\n", 1)[-1].strip()
                elif content.startswith("[系统]"):
                    lines = content.split("\n")
                    content = "\n".join(
                        l for l in lines
                        if not l.startswith("[系统]") and not l.startswith("[Task]") and not l.startswith("[Output]")
                    ).strip()
            if not content and role != "assistant":
                continue
            out = {
                "role": role,
                "content": content,
                "timestamp": msg.get("timestamp") or msg.get("ts") or "",
                "session_id": session_id,
            }
            if not out["timestamp"]:
                out["timestamp"] = (base_time - _td(minutes=max(0, len(raw_history) - len(all_messages)))).isoformat()
            if msg.get("thinking"):
                # 🔧 规范化 thinking 数据，确保格式一致
                out["thinking"] = _normalize_thinking_for_frontend(msg["thinking"])
            if msg.get("duration_ms") is not None:
                out["duration_ms"] = msg["duration_ms"]
            all_messages.append(out)
    
    # 按时间戳排序
    all_messages.sort(key=lambda m: m.get("timestamp", ""), reverse=False)
    
    # 🔧 补充推理过程：若 assistant 没有 thinking，则按同时间段 tools 日志补占位工具调用
    _attach_placeholder_tools_from_logs(all_messages, user_id=user_id, session_id=all_sessions[0].get("session_id") if all_sessions else "")
    
    return {"messages": all_messages, "total_sessions": len(all_sessions)}


@app.post("/api/user/{user_id}/chat/clear")
def clear_chat_session(user_id: str):
    """清空 .env 默认会话的 conversation_history"""
    from backend.config.config import settings as _settings
    fixed_session_id = _settings.default_session_id
    sqlite_service.clear_conversation_history(fixed_session_id, user_id)
    return {"ok": True, "session_id": fixed_session_id}



# ══════════════════════════════════════════════════════

# 面经收录 API

# ══════════════════════════════════════════════════════



@app.post("/api/ingest")

async def api_ingest(req: IngestRequest):

    """立即收录一条面经 URL"""

    return await orchestrator.ingest_instant(

        url=req.url,

        user_id=req.user_id,

        source_platform=req.source_platform

    )





# ══════════════════════════════════════════════════════

# 知识资源 API

# ══════════════════════════════════════════════════════



@app.get("/api/resources")

def get_resources(tag: Optional[str] = Query(None), limit: int = 10):

    """获取学习资源推荐"""

    tags = [tag] if tag else []

    resources = sqlite_service.get_resources_by_tags(tags, limit=limit)

    return {"resources": resources}





# ══════════════════════════════════════════════════════

# 记忆系统 API（调试用）

# ══════════════════════════════════════════════════════



@app.get("/api/user/{user_id}/memory")

def get_memory_summary(user_id: str):

    """获取用户记忆摘要（调试用）"""

    summary = orchestrator.get_memory_summary(user_id)

    return {"user_id": user_id, "memory_summary": summary}





# ══════════════════════════════════════════════════════

# 爬虫管理 API

# ══════════════════════════════════════════════════════




class CrawlTriggerRequest(BaseModel):

    platform: str = "nowcoder"           # nowcoder / xiaohongshu

    keywords: Optional[List[str]] = None

    max_pages: int = 2                   # 牛客最多抓几页

    max_notes: int = 10                  # 小红书最多抓几条

    headless: bool = True                # XHS 是否无头模式（True 不弹窗）

    process: bool = True                 # 发现后立即处理任务队列





@app.get("/api/crawler/stats")
def get_crawler_stats():
    """获取爬虫调度器状态及统计信息，含 source_info 便于区分本地/MCP"""
    return {**crawl_scheduler.get_stats(), "source_info": task_get_source_info()}





@app.get("/api/crawler/extraction-status")
def get_extraction_status():
    """获取后台提取是否正在运行（前端刷新后可据此恢复进度显示），含 source_info 便于区分本地/MCP"""
    return {
        "running": _extraction_running,
        "initial_by_platform": _extraction_initial_by_platform,
        "source_info": task_get_source_info(),
    }


def _candidate_trace_dirs() -> list[Path]:
    """返回可用的 trace 目录候选（兼容历史目录迁移）。"""
    dirs: list[Path] = []
    try:
        dirs.append(Path(_cfg.agent_trace_dir))
    except Exception:
        pass
    try:
        dirs.append(Path(_cfg.backend_data_dir) / "memory" / "traces")
    except Exception:
        pass
    # 兼容历史运行目录：<project_root>/memory/traces
    try:
        dirs.append(Path(__file__).resolve().parents[1] / "memory" / "traces")
    except Exception:
        pass

    out: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        k = str(d.resolve()) if d.exists() else str(d)
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out


def _read_extraction_trace_steps():
    """读取最新 trace 文件的推理步骤，供轮询和 SSE 复用"""
    import json
    from pathlib import Path
    files = []
    for trace_dir in _candidate_trace_dirs():
        if not trace_dir.exists():
            continue
        files.extend(trace_dir.glob("trace-s-*.jsonl"))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return [], None
    latest = files[0]
    steps = []
    try:
        with open(latest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    payload = ev.get("payload") or {}
                    event = ev.get("event")
                    step_num = ev.get("step")
                    if event == "tool_call":
                        tool_name = payload.get("tool_name", "")
                        args = payload.get("args", {})
                        if tool_name == "Thought":
                            steps.append({"step": step_num, "type": "thought", "text": args.get("reasoning", "")[:200]})
                        elif tool_name == "Finish":
                            ans = args.get("answer", "")
                            cnt = ans.count('"question_text"') if ans else 0
                            steps.append({"step": step_num, "type": "finish", "text": f"✅ 提取完成，共 {cnt} 道题目" if cnt else "✅ 提取完成"})
                        elif tool_name == "ocr_images":
                            steps.append({"step": step_num, "type": "tool", "text": "🔍 调用 OCR 识别图片..."})
                        elif tool_name == "mark_unrelated":
                            steps.append({"step": step_num, "type": "tool", "text": "⚠️ 标记为无关帖"})
                        else:
                            steps.append({"step": step_num, "type": "tool", "text": f"调用 {tool_name}"})
                    elif event == "tool_result" and steps:
                        last = steps[-1]
                        if last.get("type") == "tool" and "OCR" in last.get("text", ""):
                            last["text"] = "✅ OCR 识别完成"
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception as e:
        logger.debug(f"读取 trace 失败: {e}")
    session_id = latest.stem.replace("trace-", "", 1) if latest else None
    return steps, session_id


@app.get("/api/crawler/extraction-trace")
def get_extraction_trace():
    """
    获取当前提取任务的最新推理过程（Miner Agent 的 Thought/工具调用/Finish）。
    提取进行中时前端轮询此接口，动态展示推理步骤。
    """
    steps, session_id = _read_extraction_trace_steps()
    return {"steps": steps, "session_id": session_id}


@app.get("/api/crawler/extraction-trace-stream")
async def get_extraction_trace_stream():
    """
    SSE 流式推送当前提取的推理过程，提取进行中时前端连接此接口实时展示。
    """
    import asyncio
    from fastapi.responses import StreamingResponse

    async def _stream():
        last_steps_json = ""
        for _ in range(1800):  # 最多 30 分钟
            steps, session_id = _read_extraction_trace_steps()
            data = json.dumps({"steps": steps, "session_id": session_id}, ensure_ascii=False)
            if data != last_steps_json:
                last_steps_json = data
                yield f"event: trace\ndata: {data}\n\n"
            if not _extraction_running:
                yield f"event: done\ndata: {{\"done\": true}}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/crawler/trace/{session_id}")
def get_trace_html(session_id: str):
    """
    返回指定 session 的 trace HTML 文件内容，用于帖子记录表中「查看推理过程」链接。
    session_id 格式如 s-20260314-142242-0644
    """
    import re as _re
    from fastapi.responses import FileResponse
    # 安全校验：session_id 只允许字母数字和连字符
    if not _re.match(r"^s-[a-zA-Z0-9\-]+$", session_id):
        raise HTTPException(status_code=400, detail="无效的 session_id")
    for trace_dir in _candidate_trace_dirs():
        html_path = trace_dir / f"trace-{session_id}.html"
        if html_path.exists():
            return FileResponse(html_path, media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=404, detail="Trace 文件不存在或已清理")





@app.get("/api/crawler/keywords")

def get_crawl_keywords():

    """获取帖子记录中已有关键词列表（用于筛选下拉）"""

    import sqlite3

    with sqlite3.connect(sqlite_service.db_path) as conn:

        rows = conn.execute(

            "SELECT DISTINCT discover_keyword FROM crawl_tasks "

            "WHERE discover_keyword IS NOT NULL AND trim(discover_keyword) != '' "

            "ORDER BY discover_keyword"

        ).fetchall()

    return {"keywords": [r[0] for r in rows]}





@app.post("/api/crawler/trigger")

async def trigger_crawler(req: CrawlTriggerRequest):

    """

    手动触发爬虫任务。

    - platform=nowcoder：同步执行，立即返回发现数量

    - platform=xiaohongshu：在后台线程运行（会弹出浏览器等待扫码），立即返回 "已启动"

    - process=true：发现后自动提取题目入库（牛客同步，XHS 异步）

    """

    import asyncio, threading

    loop = asyncio.get_event_loop()



    if req.platform == "nowcoder":
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: task_execute("nowcoder_discovery", "button", keywords=req.keywords, max_pages=req.max_pages),
                ),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.warning("牛客帖子发现超时（120s）")
            raise HTTPException(status_code=504, detail="牛客帖子发现超时，请减少爬取页数后重试。")
        added = result["discovered"]
        discovered_links = result.get("discovered_links", [])
        if req.process and added > 0:
            def _bg_process():
                try:
                    task_execute("process_tasks", "button", batch_size=added + 5)
                    logger.info(f"牛客后台提取完成")
                except Exception as e:
                    logger.error(f"牛客后台提取失败: {e}", exc_info=True)
            threading.Thread(target=_bg_process, daemon=True).start()
        tip = f"发现 {added} 条新帖子" + ("，LLM 提取已在后台进行，完成后可刷新任务列表" if req.process and added > 0 else "")
        return {
            "status": "ok",
            "platform": "nowcoder",
            "discovered": added,
            "discovered_links": discovered_links or [],
            "questions_added": -1,
            "message": tip,
            "source_info": result.get("source_info", task_get_source_info()),
        }



    elif req.platform == "xiaohongshu":

        # XHS 需要弹出浏览器扫码，不能阻塞 HTTP 请求。

        # 必须用 subprocess.Popen（不能用 threading.Thread）：

        # 在 Windows 上，从 FastAPI 服务线程启动 headless=False 的 Chromium 会因为

        # 线程没有独立的 Windows 桌面 window station 而立即崩溃（exit code=21）。

        # subprocess.Popen 创建独立进程，可以正常弹出浏览器窗口。

        import subprocess, sys as _sys



        worker = str(

            _PROJECT_ROOT / "backend" / "services" / "crawler" / "run_xhs_worker.py"

        )

        cmd = [

            _sys.executable, worker,

            "--keywords", ",".join(req.keywords) if req.keywords else "",

            "--max-notes", str(req.max_notes),

            "--headless",  "false",

            "--process",   "true" if req.process else "false",

        ]

        logger.info(f"启动 XHS worker 子进程: {' '.join(cmd)}")

        # 设置 UTF-8 编码环境变量
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        subprocess.Popen(

            cmd,

            cwd=str(_PROJECT_ROOT),

            creationflags=0,        # 在当前控制台窗口组中运行，可见输出

            env=env,

        )

        return {
            "status": "ok",
            "platform": "xiaohongshu",
            "discovered": -1,
            "questions_added": -1,
            "message": "🌸 小红书爬取已以独立子进程启动，请在弹出的浏览器中完成扫码登录。完成后可在「任务队列」查看进度。",
            "background": True,
            "source_info": task_get_source_info(),
        }

    else:

        raise HTTPException(status_code=400, detail=f"不支持的平台: {req.platform}")





@app.post("/api/crawler/process")
async def process_crawler_queue(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """手动触发任务处理队列。process 模式：提交子进程后立即返回；thread 模式：线程池内同步跑完整批。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 同步处理队列 被调用 batch_size={batch_size}")
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: task_execute("process_tasks", "button", batch_size=batch_size),
    )
    logger.info(f"[API] 同步处理队列 完成 questions_added={result.get('questions_added', 0)}")
    return result





@app.post("/api/crawler/clean-data")
async def clean_unrelated_data(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """清洗无关帖：1) 直接删除 unrelated 状态；2) 对 done 帖子用 LLM 二次判断，无关则删除。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 清洗数据 被调用 batch_size={batch_size}")
    result = await asyncio.to_thread(task_execute, "clean_data", "button", batch_size=batch_size)
    logger.info(f"[API] 清洗数据 完成: {result.get('message', '')}")
    return result





@app.post("/api/crawler/clear-all")

async def clear_all_crawl_data():

    """

    清除所有爬虫相关数据：crawl_tasks、crawl_logs、questions、ingestion_logs、post_images、

    LLM 日志（llm_prompt_log）、llm_failures、xhs_link_cache。不可恢复，请谨慎操作。

    """

    import sqlite3

    import shutil

    from pathlib import Path

    from backend.config.config import settings



    logger.info("[API] 清除所有爬虫数据 被调用")

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT task_id, source_url FROM crawl_tasks"

        ).fetchall()

    urls = [r["source_url"] for r in rows]

    deleted_questions = 0

    for url in urls:

        deleted_questions += sqlite_service.delete_by_source_url(url)

    # 清理可能残留的 crawl_tasks / crawl_logs / ingestion_logs（delete_by_source_url 已删，此处兜底）

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.execute("DELETE FROM crawl_tasks")

        conn.execute("DELETE FROM crawl_logs")

        # 兜底：删除 ingestion_logs 中牛客/小红书题目的关联（避免孤儿记录）

        conn.execute("""

            DELETE FROM ingestion_logs WHERE question_id IN (

                SELECT q_id FROM questions WHERE source_platform IN ('nowcoder', 'xiaohongshu')

            )

        """)

        # 兜底：删除所有来源为牛客/小红书的题目（crawl_tasks 为空时上面循环不会删题）

        try:

            from backend.services.storage.neo4j_service import neo4j_service

            neo4j_service.delete_questions_by_source_platform(["nowcoder", "xiaohongshu"])

        except Exception as e:

            logger.warning("Neo4j 按平台删除题目失败: %s", e)

        cur = conn.execute(

            "DELETE FROM questions WHERE source_platform IN ('nowcoder', 'xiaohongshu')"

        )

        deleted_questions += cur.rowcount

        conn.commit()



    # 清除 post_images 目录下所有子目录（兜底清理孤儿目录）

    post_images = settings.post_images_dir

    if post_images.exists():

        for d in post_images.iterdir():

            if d.is_dir():

                try:

                    shutil.rmtree(d)

                except Exception as e:

                    logger.warning(f"删除图片目录失败 {d}: {e}")



    # 清除小红书链接缓存（保留 LLM 交互日志，用户可能需要用于微调）

    log_cleared = []

    xhs_path = Path(settings.xhs_link_cache_path)

    if xhs_path.exists():

        xhs_path.write_text("", encoding="utf-8")

        log_cleared.append("小红书链接缓存")



    log_msg = f"，以及 {', '.join(log_cleared)}" if log_cleared else ""

    logger.info(f"[API] 清除所有爬虫数据 完成: {len(urls)} 条帖子, {deleted_questions} 道题目{log_msg}")

    return {

        "status": "ok",

        "message": f"已清除 {len(urls)} 条帖子记录、{deleted_questions} 道题目{log_msg}",

        "posts_deleted": len(urls),

        "questions_deleted": deleted_questions,

    }





@app.get("/api/crawler/xhs/login-status")

async def xhs_login_status():

    """检查小红书登录状态（是否有有效 session）"""

    import asyncio

    loop = asyncio.get_event_loop()

    try:

        from backend.services.crawler.xhs_crawler import XHSCrawler

        crawler = XHSCrawler(headless=True)

        logged_in = await loop.run_in_executor(None, crawler.is_logged_in)

        return {

            "logged_in": logged_in,

            "session_dir": "./backend/data/xhs_user_data",

            "tip": "已登录，定时任务可正常运行" if logged_in

                   else "未登录，请调用 POST /api/crawler/xhs/login 完成扫码",

        }

    except Exception as e:

        return {"logged_in": False, "error": str(e)}





@app.post("/api/crawler/xhs/login")

async def xhs_login(wait_seconds: int = Query(120, ge=30, le=300, description="等待扫码秒数")):

    """

    触发小红书扫码登录（弹出浏览器窗口，无需回车，自动倒计时）。

    登录状态保存后，后续定时任务可无头运行。

    wait_seconds：最多等待多少秒，默认 120 秒。

    """

    import asyncio

    loop = asyncio.get_event_loop()

    try:

        from backend.services.crawler.xhs_crawler import xhs_do_login

        success = await loop.run_in_executor(None, lambda: xhs_do_login(wait_seconds=wait_seconds))

        return {

            "success": success,

            "message": "登录成功，后续任务将使用已保存的 session" if success

                       else f"等待 {wait_seconds} 秒内未检测到登录，请重试",

        }

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))





def _validate_batch_task_ids(task_ids: list) -> list:
    """同步校验 task_ids，供 run_in_executor 调用"""
    import sqlite3
    ids = [tid for tid in (task_ids or [])[:50] if tid and isinstance(tid, str)]
    if not ids:
        return []
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        valid_ids = []
        for tid in ids:
            row = conn.execute(
                "SELECT task_id, length(raw_content) as clen FROM crawl_tasks WHERE task_id=?",
                (tid,),
            ).fetchone()
            if row and (row["clen"] or 0) >= 50:
                valid_ids.append(tid)
    return valid_ids


def _spawn_process_tasks_worker(batch_size: int, reason: str):
    """启动 process_tasks 子进程，避免父进程退出导致后台线程中断。"""
    from backend.services.scheduling.process_tasks_spawn import spawn_process_tasks_worker

    return spawn_process_tasks_worker(batch_size=batch_size, reason=reason)


def _save_batch_extract_state(
    task_ids: list,
    total: int,
    log_start_offset: int,
    completed: list | None = None,
    interrupted_at: str | None = None,
    log_path: str | None = None,
) -> None:
    """持久化批量提取状态，供 shutdown 时保存进度、startup 时恢复"""
    import json
    from datetime import datetime
    state = {
        "task_ids": task_ids,
        "total": total,
        "log_start_offset": log_start_offset,
        "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if completed is not None:
        state["completed"] = completed
    if interrupted_at:
        state["interrupted_at"] = interrupted_at
    if log_path:
        state["log_path"] = log_path
    try:
        with open(_BATCH_EXTRACT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("保存批量提取状态失败: %s", e)


def _parse_completed_from_log(log_path: Path, start_offset: int) -> list:
    """从 log 中解析「完成 task_id=」行，提取已完成的 task_id 列表"""
    import re
    completed = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(max(0, start_offset))
            for line in f:
                m = re.search(r"完成 task_id=([A-Za-z0-9\-]+)", line)
                if m:
                    completed.append(m.group(1))
    except OSError:
        pass
    return completed


def _spawn_batch_extract_subprocess(
    cmd: list,
    log_path: Path,
    total_count: int,
    *,
    persist_batch_state: bool = True,
    progress_label: str = "[批量提取]",
) -> None:
    """启动批量提取子进程，日志写入 SUBPROCESS_LOG_DIR 下按任务类型与时间戳命名的文件。

    子进程 stdout/stderr 直接追加写入日志文件（不用 PIPE），避免父进程退出或终端中断时
    管道断裂导致子进程写入失败、进度条与实际不符或任务假死。
    父进程 shutdown 时会写 abort 文件通知子进程优雅退出，并持久化已完成进度与 log_path 供下次解析。

    persist_batch_state=False 时：不写批量提取断点状态、不占用 _batch_extract_proc。
    """
    import re
    import subprocess
    import threading
    global _batch_extract_proc

    log_path.parent.mkdir(parents=True, exist_ok=True)
    task_ids = cmd[3:] if len(cmd) > 3 else []
    completed = 0
    last_print_time = [0]  # 用 list 以便闭包内修改
    lock = threading.Lock()
    color_enabled = bool(getattr(sys.stdout, "isatty", lambda: False)()) and os.environ.get("NO_COLOR", "").strip() == ""
    C_RESET = "\033[0m"
    C_INFO = "\033[36m"      # cyan
    C_PROGRESS = "\033[96m"  # bright cyan
    C_DONE = "\033[92m"      # bright green
    C_WARN = "\033[93m"      # bright yellow
    C_ERROR = "\033[91m"     # bright red

    def _with_color(text: str, color: str) -> str:
        if not color_enabled:
            return text
        return f"{color}{text}{C_RESET}"

    def _colorize_log_line(text: str) -> str:
        s = text.rstrip("\n")
        if " ERROR " in s or "❌" in s or "失败" in s:
            return _with_color(s, C_ERROR) + "\n"
        if " WARNING " in s or "⚠️" in s or "警告" in s:
            return _with_color(s, C_WARN) + "\n"
        if "✅" in s or "完成" in s:
            return _with_color(s, C_DONE) + "\n"
        return _with_color(s, C_INFO) + "\n"

    def _print_progress():
        with lock:
            pct = int(100 * completed / total_count) if total_count else 0
            bar_len = 20
            filled = int(bar_len * completed / total_count) if total_count else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            ts = now_beijing_str("%Y-%m-%d %H:%M:%S")
            msg = f"\r{ts} | INFO    | {progress_label} {bar} {completed}/{total_count} ({pct}%)\n"
            sys.stdout.write(_with_color(msg, C_PROGRESS))
            sys.stdout.flush()

    _re_batch_done = re.compile(r"\[BatchExtractWorker\]\s+完成\s+task_id=|\[Stage2EnrichWorker\]\s+完成\s+task_id=")

    def _handle_log_line(text: str) -> None:
        nonlocal completed
        # 解析进度：完成 task_id=xxx（BatchExtract 或 Stage2Enrich）
        if _re_batch_done.search(text):
            with lock:
                completed += 1
            _print_progress()
            last_print_time[0] = time.time()
        if "[BatchExtractWorker] 全部完成" in text or "[Stage2EnrichWorker] 全部完成" in text:
            with lock:
                completed = total_count
            _print_progress()
            last_print_time[0] = time.time()
        # 主终端透传关键日志（开始/处理中/完成/异常）
        if "[BatchExtractWorker]" in text or "[Stage2EnrichWorker]" in text:
            if (
                "开始批量" in text
                or "处理 " in text
                or "完成 task_id=" in text
                or "批量提取异常" in text or "异常 task_id=" in text
                or "全部完成" in text
            ):
                sys.stdout.write(_colorize_log_line(text if text.endswith("\n") else text + "\n"))
                sys.stdout.flush()

    start_offset = log_path.stat().st_size if log_path.exists() else 0
    try:
        _BATCH_EXTRACT_ABORT_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    if persist_batch_state:
        _save_batch_extract_state(
            task_ids,
            total_count,
            start_offset,
            log_path=str(log_path.resolve()),
        )
    env = os.environ.copy()
    env["BATCH_EXTRACT_ABORT_FILE"] = str(_BATCH_EXTRACT_ABORT_FILE)
    logf = open(log_path, "a", encoding="utf-8", buffering=1)
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": logf,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kw["start_new_session"] = True
    proc = subprocess.Popen(cmd, **popen_kw)
    if persist_batch_state:
        _batch_extract_proc = proc  # noqa: PLW0603 (global set in function)
    try:
        logf.close()
    except Exception:
        pass

    def follow_log_tail():
        nonlocal completed
        pos = start_offset
        line_buf = ""
        try:
            while True:
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as rf:
                        rf.seek(pos)
                        chunk = rf.read()
                        pos = rf.tell()
                except OSError:
                    chunk = ""
                if chunk:
                    line_buf += chunk
                    parts = line_buf.split("\n")
                    line_buf = parts.pop() if parts else ""
                    for p in parts:
                        _handle_log_line(p + "\n")
                elif proc.poll() is not None:
                    if line_buf:
                        _handle_log_line(line_buf if line_buf.endswith("\n") else line_buf + "\n")
                    break
                time.sleep(0.35)
        finally:
            # 不可在持锁时调用 _print_progress（其内部再次 acquire 同一把 Lock 会死锁）
            _print_progress()

    threading.Thread(target=follow_log_tail, daemon=True).start()


@app.post("/api/crawler/tasks/re-extract-batch")
async def re_extract_batch_tasks(body: dict):
    """
    对选中的多个任务批量重新执行 OCR + MinerAgent 提取，子进程后台执行，不阻塞其他 API。
    请求体: { "task_ids": ["uuid1", "uuid2", ...] }
    """
    task_ids = body.get("task_ids") or []
    if not isinstance(task_ids, list) or not task_ids:
        raise HTTPException(status_code=400, detail="请提供 task_ids 数组")

    loop = asyncio.get_event_loop()
    valid_ids = await loop.run_in_executor(None, _validate_batch_task_ids, task_ids)

    if not valid_ids:
        raise HTTPException(status_code=400, detail="没有符合条件的任务（正文需≥50字）")

    # 子进程执行，与主进程完全隔离，不阻塞 loadTasks/loadStats/提交作答等
    # 子进程日志写入 SUBPROCESS_LOG_DIR/batch_extract/，控制台按进度条线程刷新
    cmd = [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker"] + valid_ids
    log_path = new_subprocess_log_file("batch_extract")
    _spawn_batch_extract_subprocess(cmd, log_path, len(valid_ids))
    logger.info(f"[API] 批量重新提取已启动（子进程），共 {len(valid_ids)} 条，日志: {log_path}")
    return {"status": "ok", "message": f"已提交 {len(valid_ids)} 条，后台执行中", "count": len(valid_ids)}


@app.post("/api/crawler/tasks/stage2-enrich-batch")
async def stage2_enrich_batch(body: dict):
    """
    对已入库题目的帖子批量跑 Stage2（MINER_STAGE2_* 豆包等），合并后更新 questions.answer_text / raw_answer，并同步 Neo4j。
    子进程后台执行，不阻塞其他 API。
    请求体: { "task_ids": ["TASK-xxx", ...] }
    """
    task_ids = body.get("task_ids") or []
    if not isinstance(task_ids, list) or not task_ids:
        raise HTTPException(status_code=400, detail="请提供 task_ids 数组")
    cleaned = [str(t).strip() for t in task_ids if t and str(t).strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail="task_ids 为空")

    cmd = [sys.executable, "-m", "backend.services.scheduling.stage2_enrich_worker"] + cleaned
    log_path = new_subprocess_log_file("stage2_enrich")
    _spawn_batch_extract_subprocess(
        cmd, log_path, len(cleaned),
        persist_batch_state=False,
        progress_label="[Stage2精答]",
    )
    logger.info(f"[API] Stage2 批量精答已启动（子进程），共 {len(cleaned)} 条，日志: {log_path}")
    return {
        "status": "ok",
        "message": f"已提交 {len(cleaned)} 条，后台 Stage2 精答执行中",
        "count": len(cleaned),
    }


@app.post("/api/crawler/tasks/resume-batch")
async def resume_batch_extract():
    """恢复上次父进程 shutdown 时中断的批量提取，从剩余任务继续执行。"""
    import json
    global _batch_extract_proc
    if _batch_extract_proc is not None and _batch_extract_proc.poll() is None:
        return {"status": "busy", "message": "已有批量提取进行中，请稍后再试", "count": 0}
    if not _BATCH_EXTRACT_STATE_FILE.exists():
        return {"status": "ok", "message": "无待恢复的批量提取", "count": 0}
    try:
        with open(_BATCH_EXTRACT_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"读取状态失败: {e}")
    if not state.get("interrupted_at"):
        return {"status": "ok", "message": "上次批量提取已完成，无需恢复", "count": 0}
    completed = set(state.get("completed", []))
    task_ids = state.get("task_ids", [])
    remaining = [t for t in task_ids if t not in completed]
    if not remaining:
        return {"status": "ok", "message": "剩余任务为空，已完成", "count": 0}
    cmd = [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker"] + remaining
    log_path = new_subprocess_log_file("batch_extract")
    _spawn_batch_extract_subprocess(cmd, log_path, len(remaining))
    logger.info(f"[API] 批量提取恢复已启动，剩余 {len(remaining)} 条")
    return {"status": "ok", "message": f"已恢复，剩余 {len(remaining)} 条后台执行中", "count": len(remaining)}


def _validate_single_task_id(task_id: str) -> tuple:
    """同步校验单任务，供 run_in_executor 调用，返回 (row_dict, error_msg)"""
    import sqlite3
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT task_id, status, post_title, length(raw_content) as clen FROM crawl_tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
    if not row:
        return None, "task_id 不存在"
    row = dict(row)
    if (row.get("clen") or 0) < 50:
        return row, f"任务正文为空或过短（{row.get('clen', 0)}字），请先抓取正文"
    return row, None


@app.post("/api/crawler/tasks/{task_id}/re-extract")
async def re_extract_single_task(task_id: str):
    """
    对单个任务重新执行完整的 OCR + MinerAgent 提取流程（子进程后台执行）。

    适用场景：
    - 任务状态为 error/fetched/done，需重新提取
    - 帖子包含图片，想验证 OCR 效果
    - 调试单条任务的提取结果

    立即返回，提取在子进程中执行，不阻塞其他 API（如提交作答、题库浏览）。
    """
    loop = asyncio.get_event_loop()
    row, err = await loop.run_in_executor(None, _validate_single_task_id, task_id)
    if err:
        if "不存在" in err:
            raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")
        raise HTTPException(status_code=400, detail=err)

    post_title = (row.get("post_title") or "(无标题)")[:40]
    logger.info(f"[API] 单任务重新提取 task_id={task_id} title={post_title}...")

    cmd = [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker", task_id]
    log_path = new_subprocess_log_file("batch_extract")
    _spawn_batch_extract_subprocess(cmd, log_path, 1)
    return {
        "status": "ok",
        "task_id": task_id,
        "message": "已提交后台执行，请稍后刷新任务列表查看结果",
    }


@app.post("/api/crawler/refetch-xhs-body")

async def refetch_xhs_body(task_id: str = Query(..., description="任务 ID")):

    """

    对已入库但正文为空或标题为「页面不见了」的小红书帖子，用 Playwright 重新抓取正文并更新。

    成功后任务重置为 fetched，可参与「从正文提取」。

    """

    import sqlite3

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(

            "SELECT task_id, source_url, source_platform, post_title FROM crawl_tasks WHERE task_id = ?",

            (task_id,),

        ).fetchone()

    if not row:

        raise HTTPException(status_code=404, detail="任务不存在")

    if row["source_platform"] != "xiaohongshu":

        raise HTTPException(status_code=400, detail="仅支持小红书帖子")

    url = row["source_url"]

    try:

        from backend.services.crawler.xhs_crawler import _fetch_xhs_with_playwright

        pw_data = await _fetch_xhs_with_playwright(url)

    except Exception as e:

        logger.exception(f"Playwright 重抓失败 task_id={task_id}")

        raise HTTPException(status_code=500, detail=str(e))

    if not pw_data or not (pw_data.get("content") or "").strip():

        return {"status": "fail", "message": "Playwright 未能获取到正文，请确认已登录小红书"}

    title = (pw_data.get("title") or row["post_title"] or "").strip()

    for suffix in (" - 小红书", "- 小红书"):

        if title.endswith(suffix):

            title = title[:-len(suffix)].strip()

            break

    content = (pw_data.get("content") or "").strip()

    image_urls = pw_data.get("image_urls") or []

    image_paths = []

    if image_urls:

        from backend.services.crawler.image_utils import download_images

        image_paths = download_images(image_urls, task_id)

    post_time = pw_data.get("post_time") or ""
    sqlite_service.update_task_content(task_id, post_title=title, raw_content=content, image_paths=image_paths, post_time=post_time)

    logger.info(f"[API] 重抓正文成功 task_id={task_id} title={title[:40]}... ({len(content)} 字)")

    return {"status": "ok", "message": f"已更新正文 {len(content)} 字，可参与「从正文提取」"}





@app.get("/api/crawler/tasks")

def get_crawl_tasks(

    status: Optional[str] = Query(
        None,
        description="pending/fetched/done/error/unrelated/skipped；虚拟：stage2_incomplete（已完成且在有答案题目中精答完成率<=50%）、stage2_complete（已完成且在有答案题目中精答完成率>50%）",
    ),

    platform: Optional[str] = Query(None),

    keyword: Optional[str] = Query(None, description="发现关键词筛选"),

    title: Optional[str] = Query(None, description="帖子标题模糊搜索"),

    limit: int = Query(20, ge=1, le=100),

    offset: int = Query(0, ge=0),

    sort_by: Optional[str] = Query(None, description="排序字段：id/status/questions_count/processed_at/extract_duration_min/content_len等"),

    sort_order: Optional[str] = Query(None, description="排序方向：asc/desc"),

):

    """查看爬虫任务队列详情（分页）"""

    import sqlite3

    where_parts = []

    params = []

    # stage2 虚拟状态标记，用于后续生成特殊的 id IN (...) 子查询分页（绕过 SQLite EXISTS+OFFSET bug）
    _stage2_status = None

    if status:
        if status == "stage2_incomplete":
            _stage2_status = "incomplete"
        elif status == "stage2_complete":
            _stage2_status = "complete"
        else:
            where_parts.append("status = ?")
            params.append(status)

    if platform:

        where_parts.append("source_platform = ?")

        params.append(platform)

    if keyword:

        where_parts.append("discover_keyword = ?")

        params.append(keyword)

    if title:

        where_parts.append("post_title LIKE ?")

        params.append(f"%{title}%")

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # 排序字段白名单
    _SORT_FIELDS = {"id", "source_platform", "discover_keyword", "post_title",
                    "company", "status", "questions_count", "extraction_source",
                    "agent_used_tool", "extract_duration_min", "processed_at", "discovered_at", "post_time"}
    order_dir = "ASC" if sort_order and sort_order.lower() == "asc" else "DESC"
    if sort_by == "content_len":
        order_clause = f"ORDER BY length(raw_content) {order_dir}"
    elif sort_by and sort_by in _SORT_FIELDS:
        order_clause = f"ORDER BY {sort_by} {order_dir}"
    else:
        order_clause = "ORDER BY id DESC"

    # stage2 虚拟状态：SQLite 存在 EXISTS 子查询 + OFFSET 失效的 bug，
    # 必须用 WHERE id IN (SELECT id FROM crawl_tasks WHERE <exists条件>) 包一层来绕过
    # 「Stage2 完成」改为按占比判定：有答案题目中，超过 50% 已区分粗答(raw_answer)与精答(answer_text)。
    _STAGE2_RATIO_EXPR = (
        "("
        "SELECT COALESCE(SUM("
        "CASE WHEN LENGTH(TRIM(COALESCE(q.answer_text,''))) > 0 "
        "AND LENGTH(TRIM(COALESCE(q.raw_answer,''))) > 0 "
        "AND TRIM(COALESCE(q.answer_text,'')) != TRIM(COALESCE(q.raw_answer,'')) "
        "THEN 1 ELSE 0 END"
        "), 0) * 1.0 / "
        "NULLIF(COALESCE(SUM(CASE WHEN LENGTH(TRIM(COALESCE(q.answer_text,''))) > 0 THEN 1 ELSE 0 END), 0), 0) "
        "FROM questions q WHERE q.source_url = crawl_tasks.source_url"
        ")"
    )
    _STAGE2_INCOMPLETE_INNER = (
        "crawl_tasks.status = 'done' "
        "AND EXISTS (SELECT 1 FROM questions q WHERE q.source_url = crawl_tasks.source_url) "
        "AND EXISTS ("
        "SELECT 1 FROM questions q3 WHERE q3.source_url = crawl_tasks.source_url "
        "AND LENGTH(TRIM(COALESCE(q3.answer_text,''))) > 0"
        ") "
        f"AND COALESCE({_STAGE2_RATIO_EXPR}, 0.0) <= 0.5"
    )
    _STAGE2_COMPLETE_INNER = (
        "crawl_tasks.status = 'done' "
        "AND EXISTS (SELECT 1 FROM questions q WHERE q.source_url = crawl_tasks.source_url) "
        "AND EXISTS ("
        "SELECT 1 FROM questions q3 WHERE q3.source_url = crawl_tasks.source_url "
        "AND LENGTH(TRIM(COALESCE(q3.answer_text,''))) > 0"
        ") "
        f"AND COALESCE({_STAGE2_RATIO_EXPR}, 0.0) > 0.5"
    )

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        if _stage2_status:
            # 绕过 SQLite EXISTS+OFFSET bug：先用子查询取出所有符合条件的 id，
            # 外层再对这批 id 做普通 WHERE id IN (...) + 其他筛选条件 + LIMIT/OFFSET
            _inner_cond = _STAGE2_INCOMPLETE_INNER if _stage2_status == "incomplete" else _STAGE2_COMPLETE_INNER
            _extra_where_parts = [p for p in where_parts]  # platform/keyword/title 筛选（此时 where_parts 里不含 stage2 条件）
            _extra_where = (" AND " + " AND ".join(_extra_where_parts)) if _extra_where_parts else ""
            _id_subquery = f"SELECT id FROM crawl_tasks WHERE {_inner_cond}"
            _count_sql = f"SELECT COUNT(*) FROM crawl_tasks WHERE id IN ({_id_subquery}){_extra_where}"
            _rows_sql = (
                f"SELECT id, task_id, source_url, source_platform, post_title, status, "
                f"company, position, questions_count, discovered_at, processed_at, post_time, error_msg, "
                f"length(raw_content) AS content_len, discover_keyword, extraction_source, "
                f"extract_duration_min, agent_used_tool, trace_session_id, stage2_trace_session_id "
                f"FROM crawl_tasks WHERE id IN ({_id_subquery}){_extra_where} "
                f"{order_clause} LIMIT ? OFFSET ?"
            )
            total = conn.execute(_count_sql, params).fetchone()[0]
            rows = conn.execute(_rows_sql, params + [limit, offset]).fetchall()
        else:
            total = conn.execute(
                f"SELECT COUNT(*) FROM crawl_tasks {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"SELECT id, task_id, source_url, source_platform, post_title, status, "
                f"company, position, questions_count, discovered_at, processed_at, post_time, error_msg, "
                f"length(raw_content) AS content_len, discover_keyword, extraction_source, "
                f"extract_duration_min, agent_used_tool, trace_session_id, stage2_trace_session_id "
                f"FROM crawl_tasks {where} {order_clause} LIMIT ? OFFSET ?",
                params + [limit, offset]
            ).fetchall()



    # 转换时间为北京时间

    from backend.utils.time_utils import timestamp_to_beijing

    tasks = []

    for r in rows:

        task = dict(r)

        # 转换discovered_at和processed_at为北京时间

        if task.get("discovered_at"):

            task["discovered_at"] = timestamp_to_beijing(task["discovered_at"])

        if task.get("processed_at"):

            task["processed_at"] = timestamp_to_beijing(task["processed_at"])

        tasks.append(task)



    return {"total": total, "tasks": tasks}





@app.get("/api/crawler/tasks/{task_id}/questions")

def get_task_questions(task_id: str):

    """获取指定任务关联的已提取题目列表"""

    import sqlite3

    import json as _json

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(

            "SELECT source_url FROM crawl_tasks WHERE task_id = ?", (task_id,)

        ).fetchone()

    if not row:

        raise HTTPException(status_code=404, detail="任务不存在")

    source_url = row["source_url"]

    questions = sqlite_service.get_questions_by_source_url(source_url)

    for q in questions:

        try:

            q["topic_tags"] = _json.loads(q.get("topic_tags") or "[]")

        except Exception:

            q["topic_tags"] = []

    return {"questions": questions}





@app.get("/api/crawler/tasks/{task_id}")

def get_crawl_task_detail(task_id: str):

    """获取单个任务的完整内容（含正文、图片相对路径）"""

    import sqlite3

    import json as _json

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(

            "SELECT * FROM crawl_tasks WHERE task_id = ?", (task_id,)

        ).fetchone()

    if not row:

        raise HTTPException(status_code=404, detail="任务不存在")

    d = dict(row)

    # image_paths 存为 JSON，转为列表；前端用 /post-images/{path} 访问

    img_raw = d.get("image_paths") or "[]"

    try:

        d["image_paths"] = _json.loads(img_raw)

    except Exception:

        d["image_paths"] = []

    return d


@app.delete("/api/crawler/tasks/{task_id}")
def delete_crawl_task(task_id: str):
    """删除指定帖子及其关联数据（题目、日志、图片等）。"""
    deleted = sqlite_service.delete_by_task_id(task_id)
    if deleted < 0:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"status": "ok", "message": f"已删除帖子及 {deleted} 道题目", "questions_deleted": deleted}


@app.post("/api/crawler/tasks/delete-batch")
def delete_crawl_tasks_batch(body: dict):
    """批量删除帖子及其关联数据。请求体: { "task_ids": ["uuid1", ...] }"""
    task_ids = body.get("task_ids") or []
    if not isinstance(task_ids, list):
        task_ids = []
    total_deleted = 0
    posts_deleted = 0
    not_found = []
    for tid in task_ids[:100]:
        if not tid or not isinstance(tid, str):
            continue
        d = sqlite_service.delete_by_task_id(tid)
        if d >= 0:
            posts_deleted += 1
            total_deleted += d
        else:
            not_found.append(tid)
    return {
        "status": "ok",
        "message": f"已删除 {posts_deleted} 条帖子、{total_deleted} 道题目",
        "posts_deleted": posts_deleted,
        "questions_deleted": total_deleted,
        "not_found": not_found,
    }


# ══════════════════════════════════════════════════════════════

# 微调数据 API

# ══════════════════════════════════════════════════════════════



from backend.services.finetune import finetune_service as _ft





@app.get("/api/finetune/stats")

async def finetune_stats():

    """微调数据统计（样本数、标注数等）"""

    return _ft.get_stats()





@app.get("/api/finetune/log-files")

async def finetune_log_files():

    """列出 微调/llm_logs/ 下所有日志文件"""

    return _ft.list_log_files()





@app.post("/api/finetune/import-all")

async def finetune_import_all():

    """扫描 微调/llm_logs/ 下所有 JSONL 并全量导入（已有记录跳过）"""

    import asyncio

    return await asyncio.get_event_loop().run_in_executor(None, _ft.import_all_logs)





@app.post("/api/finetune/import")

async def finetune_import(body: dict):

    """从指定日志文件导入样本到 SQLite"""

    log_path = body.get("log_path", "")

    if not log_path:

        raise HTTPException(status_code=400, detail="log_path 不能为空")

    return _ft.import_from_log_file(log_path)


@app.post("/api/finetune/fix-merged")
async def finetune_fix_merged(body: dict = None):
    """
    修复已导入样本：对 stage2_output 不完整的记录，用 stage1_output 补齐缺失字段。
    body 可选: {"source": "miner_two_stage"} 仅处理指定来源，不传则处理 miner_two_stage。
    """
    source = (body or {}).get("source", "miner_two_stage")
    return _ft.fix_merged_stage2_samples(source_filter=source)


@app.get("/api/finetune/samples")

async def finetune_samples(

    status: str = Query(None),

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

    order: str = Query("asc", pattern="^(asc|desc)$"),

):

    """分页查询微调样本列表"""

    return _ft.list_samples(status=status, page=page, page_size=page_size, order=order)





@app.get("/api/finetune/samples/{sample_id}")

async def finetune_sample_detail(sample_id: int):

    """获取单条样本完整内容"""

    s = _ft.get_sample(sample_id)

    if not s:

        raise HTTPException(status_code=404, detail="样本不存在")

    return s





@app.post("/api/finetune/assist")

async def finetune_assist(body: dict):

    """

    调用远程大模型对面经原文辅助生成标注结果。

    可传 sample_id（自动取 content）或直接传 content。

    可选传 model / api_key / base_url 覆盖 .env 配置。

    """

    import asyncio

    sample_id = body.get("sample_id")

    content = body.get("content", "")

    title = body.get("title", "")

    

    if sample_id and not content:

        s = _ft.get_sample(int(sample_id))

        if not s:

            raise HTTPException(status_code=404, detail="样本不存在")

        content = s["content"]

        title = s.get("title", "")

    

    if not content:

        raise HTTPException(status_code=400, detail="content 不能为空")



    result = await asyncio.get_event_loop().run_in_executor(

        None,

        lambda: _ft.assist_generate(

            content=content,

            title=title,

            model=body.get("model"),

            api_key=body.get("api_key"),

            base_url=body.get("base_url"),

            temperature=body.get("temperature"),

        )

    )

    # 同时保存 assist_output 到样本

    if sample_id and "output" in result:

        _ft.save_assist_output(int(sample_id), result["output"])

    return result





@app.post("/api/finetune/label")

async def finetune_label(body: dict):

    """

    保存人工确认的最终标注结果。

    body: {sample_id, final_output, is_modified}

    """

    sample_id = body.get("sample_id")

    final_output = body.get("final_output", "")

    is_modified = body.get("is_modified", False)

    if not sample_id or not final_output:

        raise HTTPException(status_code=400, detail="sample_id 和 final_output 不能为空")

    return _ft.save_label(int(sample_id), final_output, is_modified)





@app.post("/api/finetune/export")
async def finetune_export(body: dict = None):
    """导出已标注样本为 微调/labeled_data.jsonl，body.sample_ids 可选指定要导出的样本 ID"""
    sample_ids = (body or {}).get("sample_ids")
    return _ft.export_labeled(sample_ids=sample_ids)


@app.get("/api/finetune/run-config")
async def finetune_get_run_config():
    """获取一键微调配置"""
    return _ft.get_run_config()


@app.post("/api/finetune/run-config")
async def finetune_save_run_config(body: dict):
    """保存一键微调配置"""
    return _ft.save_run_config(body)


@app.get("/api/finetune/runs")
async def finetune_list_runs(limit: int = 50):
    """分页查询微调训练记录"""
    return sqlite_service.list_finetune_runs(limit=limit)


@app.post("/api/finetune/generate-training")
async def finetune_generate_training(body: dict = None):
    """根据配置生成训练脚本并转换数据；默认在后台启动训练（body.run_training=false 则仅生成脚本）"""
    body = body or {}
    config = body.get("config")
    sample_ids = body.get("sample_ids")
    run_training = body.get("run_training", True)
    if not isinstance(run_training, bool):
        run_training = bool(run_training)
    return _ft.generate_training_script(
        config=config, sample_ids=sample_ids, run_training=run_training
    )


@app.get("/api/finetune/compare-presets")
async def finetune_compare_presets():
    """模型对比页：可选预设列表（与微调辅助相同的提取提示，不同 endpoint/model）"""
    return _ft.list_model_compare_presets()


@app.post("/api/finetune/compare")
async def finetune_compare(body: dict = None):
    """
    并行对比多个模型/端点在同一面经上的结构化提取结果。
    body: { preset_ids: [str, ...], content?, title?, sample_id? }
    """
    import asyncio

    body = body or {}
    preset_ids = body.get("preset_ids") or []
    if not isinstance(preset_ids, list):
        raise HTTPException(status_code=400, detail="preset_ids 须为数组")
    if len(preset_ids) < 2:
        raise HTTPException(status_code=400, detail="至少选择 2 个模型对比")
    if len(preset_ids) > 4:
        raise HTTPException(status_code=400, detail="最多同时对比 4 个模型")
    content = (body.get("content") or "").strip()
    title = (body.get("title") or "").strip()
    sample_id = body.get("sample_id")
    if sample_id is not None:
        s = _ft.get_sample(int(sample_id))
        if not s:
            raise HTTPException(status_code=404, detail="样本不存在")
        content = (s.get("content") or "").strip()
        title = (s.get("title") or title or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: _ft.compare_models_parallel(preset_ids, content, title)
    )


@app.delete("/api/finetune/samples/{sample_id}")
async def finetune_delete_sample(sample_id: int):
    """删除指定微调样本"""
    res = _ft.delete_sample(sample_id)
    if res.get("deleted", 0) == 0:
        raise HTTPException(status_code=404, detail="样本不存在")
    return res


@app.post("/api/finetune/delete-log")
async def finetune_delete_log(body: dict):
    """删除指定日志文件（仅限 微调/llm_logs/ 下）"""
    log_path = body.get("log_path", "")
    if not log_path:
        raise HTTPException(status_code=400, detail="log_path 不能为空")
    res = _ft.delete_log_file(log_path)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "删除失败"))
    return res


@app.post("/api/finetune/preview-log")
async def finetune_preview_log(body: dict):
    """
    预览日志文件前N条记录
    body: {log_path, limit}
    """
    log_path = body.get("log_path", "")
    limit = body.get("limit", 10)
    if not log_path:
        raise HTTPException(status_code=400, detail="log_path 不能为空")
    return _ft.preview_log_file(log_path, limit)


@app.post("/api/finetune/upload-faq")
async def finetune_upload_faq(
    file: UploadFile = File(...),
    save_to_bank: bool = Form(True),
    save_to_finetune: bool = Form(True),
):
    """
    上传 FAQ 文件（问题+答案），支持 CSV/JSON/JSONL/TXT。
    1. save_to_bank=True：保存到题库（SQLite + Neo4j）
    2. save_to_finetune=True：写入微调样本，用于模型 SFT
    """
    import asyncio
    content = (await file.read()).decode("utf-8", errors="replace")
    filename = file.filename or ""
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _ft.import_faq(
            content=content,
            filename=filename,
            save_to_bank=save_to_bank,
            save_to_finetune=save_to_finetune,
        ),
    )
    if result.get("errors"):
        # 有错误但不一定全部失败，仍返回结果
        pass
    return result


