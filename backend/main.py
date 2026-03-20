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

# 禁用 requests/urllib3 版本兼容性警告
os.environ['PYTHONWARNINGS'] = 'ignore::requests.exceptions.RequestsDependencyWarning'
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

_MEMORY_DIR = Path(_cfg.memory_data_dir)

_XHS_DATA_DIR = Path(_cfg.xhs_user_data_dir)

_POST_IMAGES_DIR = _cfg.post_images_dir

_NOWCODER_OUTPUT_DIR = _cfg.nowcoder_output_dir



for _d in [_BACKEND_DATA, _BACKEND_LOGS, _MEMORY_DIR, _XHS_DATA_DIR, _POST_IMAGES_DIR, _NOWCODER_OUTPUT_DIR]:

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
from backend.services.crawler.task_executor import (
    execute as task_execute,
    get_source_info as task_get_source_info,
    prepare_extract_pending,
    prepare_retry_errors,
    prepare_re_extract_all,
    get_fetched_task_ids,
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

app.include_router(scheduler_router)



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

    # Miner Agent（two_stage 时 Stage1 用本地模型，Stage2 用专项配置）
    if s.miner_mode == "two_stage":
        mm_stage1 = s.miner_local_model or s.llm_local_model or "(未设置)"
        mm_stage2 = s.miner_stage2_model or "(未设置)"
        logger.info(f"  [Miner Agent] mode=two_stage")
        logger.info(f"    Stage1(本地): model={mm_stage1}, base={s.miner_local_base_url or s.llm_local_base_url}")
        logger.info(f"    Stage2(精加工): model={mm_stage2}, base={s.miner_stage2_base_url or '(未设置)'}")
    else:
        mm = s.miner_model or s.llm_model_id or "(未设置)"
        logger.info(f"  [Miner Agent] mode={s.miner_mode}, model={mm}, temperature={s.miner_temperature}, max_tokens={s.miner_max_tokens}, base={s.miner_base_url or s.llm_base_url or '(同全局)'}")

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
    from backend.services.stage2_processor import run_stage2_processor_now

    _print_miner_config_once()
    _print_agent_llm_config()
    crawl_scheduler.start()
    _src = getattr(_s, "crawler_source", "local")
    logger.info(f"爬虫调度器已启动 | 牛客抓取来源={_src}")

    # Stage2 恢复补跑：后端重启后，优先处理上次遗留的 pending/in_progress
    # （即使不足 batch_size，也会 lease 并按实际数量处理）
    try:
        if sqlite_service.get_stage2_queue_count() > 0:
            logger.info("[Startup] Stage2 队列存在遗留任务，后台补跑 Stage2 ...")
            # 强制恢复 in_progress：通常表示“上次后端已不存在”，应立即回到 pending 供处理
            sqlite_service.recover_stale_stage2_pending(0)
            asyncio.create_task(asyncio.to_thread(run_stage2_processor_now))
    except Exception:
        logger.warning("[Startup] Stage2 补跑失败（不影响主服务启动）", exc_info=True)

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
                    "[Startup] 检测到 fetched 遗留任务 %d 条，启动子进程自动恢复（batch_size=%d）",
                    fetched_count,
                    resume_batch_size,
                )
                _spawn_process_tasks_worker(
                    batch_size=resume_batch_size,
                    reason="startup-resume-fetched",
                )
    except Exception:
        logger.warning("[Startup] fetched 自动恢复失败（不影响主服务启动）", exc_info=True)

    # 同步预热 LLM，确保首次请求不因冷启动超时
    if _s.llm_warmup_enabled and _s.llm_base_url:
        await asyncio.to_thread(_warmup_llm_sync)
    # Embedding/Reranker/OCR 预热（仅题目提取可关闭以加快启动）
    if _s.warmup_embedding_rerank_ocr_enabled:
        await asyncio.to_thread(_warmup_embedding_rerank_sync)


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI 停止时关闭调度器"""
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

@app.get("/")

def root():

    return {"status": "ok", "message": "面经 Agent API 运行中", "docs": "/docs"}





@app.get("/api/health")

def health():

    return {"status": "ok"}





# ══════════════════════════════════════════════════════

# 题库浏览 API

# ══════════════════════════════════════════════════════



@app.get("/api/questions")
def get_questions(
    company: Optional[str] = Query(None, description="公司名，模糊匹配"),
    position: Optional[str] = Query(None, description="岗位，模糊匹配"),
    difficulty: Optional[str] = Query(None, description="难度：easy/medium/hard"),
    question_type: Optional[str] = Query(None, description="题目类型：技术题/算法题/系统设计/行为题/HR问题"),
    tag: Optional[str] = Query(None, description="技术标签，如 Redis"),
    keyword: Optional[str] = Query(None, description="关键词，搜索题目文本"),
    source_platform: Optional[str] = Query(None, description="来源平台：nowcoder/xiaohongshu"),
    rand: bool = Query(False, description="true 时随机返回"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页题目数量"),
    sort_by: Optional[str] = Query(None, description="排序字段：created_at/difficulty/company/question_type/question_text"),
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
            sort_by=sort_by or "created_at", sort_order=sort_order or "desc"
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

            question_types = ["技术题", "算法题", "系统设计", "行为题", "HR问题"]



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
def get_chat_history(user_id: str):
    """获取用户对话历史：优先读取 .env 默认会话，不存在再回退到用户最近一次会话。"""
    import re as _re
    from datetime import datetime as _dt, timedelta as _td
    from backend.config.config import settings as _settings
    fixed_session_id = _settings.default_session_id
    session = sqlite_service.get_session(fixed_session_id)
    if not session or session.get("user_id") != user_id:
        session = sqlite_service.get_latest_session_for_user(user_id)
    if not session:
        return {"messages": [], "session_id": None}

    raw_history = session.get("conversation_history") or []
    session_id = session.get("session_id")

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


def _read_extraction_trace_steps():
    """读取最新 trace 文件的推理步骤，供轮询和 SSE 复用"""
    import json
    from pathlib import Path
    trace_dir = Path(_cfg.backend_data_dir) / "memory" / "traces"
    if not trace_dir.exists():
        return [], None
    files = sorted(trace_dir.glob("trace-s-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
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
    trace_dir = Path(_cfg.backend_data_dir) / "memory" / "traces"
    # 安全校验：session_id 只允许字母数字和连字符
    if not _re.match(r"^s-[a-zA-Z0-9\-]+$", session_id):
        raise HTTPException(status_code=400, detail="无效的 session_id")
    html_path = trace_dir / f"trace-{session_id}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Trace 文件不存在或已清理")
    return FileResponse(html_path, media_type="text/html; charset=utf-8")





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
    """手动触发任务处理队列（同步处理队列，阻塞等待）"""
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





@app.post("/api/crawler/extract-pending")
async def extract_pending_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """异步提取所有 fetched 状态（已爬取正文但尚未提取题目）的帖子。子进程执行，不阻塞主进程（chat/提交作答等）。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 提取未处理帖子 被调用 batch_size={batch_size}")
    pending_count, initial_by_platform = prepare_extract_pending()
    if pending_count == 0:
        logger.info("[API] 提取未处理帖子 无待处理，直接返回")
        return {
            "status": "ok",
            "message": "没有待提取的帖子（状态为 fetched 的记录为 0）",
            "pending": 0,
            "source_info": task_get_source_info(),
        }
    task_ids = get_fetched_task_ids(batch_size)
    if not task_ids:
        return {
            "status": "ok",
            "message": "没有符合条件的待提取帖子",
            "pending": 0,
            "source_info": task_get_source_info(),
        }
    log_path = _BACKEND_LOGS / "batch_extract.log"
    cmd = [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker"] + task_ids
    _spawn_batch_extract_subprocess(cmd, log_path, total_count=len(task_ids))
    logger.info(f"[API] 提取未处理帖子 已启动子进程，共 {len(task_ids)} 条，日志: {log_path}")
    return {
        "status": "ok",
        "message": f"已提交子进程后台提取，共 {len(task_ids)} 条，日志: {log_path}",
        "pending": pending_count,
        "source_info": task_get_source_info(),
    }





@app.post("/api/crawler/stage2-process")
async def trigger_stage2_process():
    """手动触发 Stage2 批量处理（处理 stage2_pending 队列中剩余项，不足 batch_size 也会处理）"""
    from backend.services.stage2_processor import run_stage2_processor_now
    from backend.services.storage import sqlite_service
    count = sqlite_service.get_stage2_queue_count()
    if count == 0:
        return {"status": "ok", "message": "Stage2 队列为空", "processed": 0}
    await asyncio.to_thread(run_stage2_processor_now)
    return {"status": "ok", "message": f"已触发 Stage2 处理（队列原有 {count} 条）", "queued": count}


@app.post("/api/crawler/clean-data")
async def clean_unrelated_data(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """清洗无关帖：1) 直接删除 unrelated 状态；2) 对 done 帖子用 LLM 二次判断，无关则删除。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 清洗数据 被调用 batch_size={batch_size}")
    result = await asyncio.to_thread(task_execute, "clean_data", "button", batch_size=batch_size)
    logger.info(f"[API] 清洗数据 完成: {result.get('message', '')}")
    return result





@app.post("/api/crawler/retry-errors")
async def retry_error_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """将 error 且有正文的帖子重置为 fetched 后台提取；无正文的重置为 pending 重新抓取。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 重试失败帖子 被调用 batch_size={batch_size}")
    to_extract, to_fetch, total, initial_by_platform = prepare_retry_errors()
    if total == 0:
        logger.info("[API] 重试失败帖子 无可重试，直接返回")
        return {
            "status": "ok",
            "message": "没有可重试的帖子（error 记录为 0）",
            "reset": 0,
            "source_info": task_get_source_info(),
        }
    run_mode = getattr(_cfg, "crawler_background_run_mode", "process")
    logger.info(f"[API] 重试失败帖子 重置 {total} 条，后台模式={run_mode}")
    global _extraction_running, _extraction_initial_by_platform

    def _bg_thread():
        global _extraction_running, _extraction_initial_by_platform
        try:
            _extraction_running = True
            _extraction_initial_by_platform = initial_by_platform
            task_execute("process_tasks", "button", batch_size=batch_size)
            logger.info(f"[API] 重试失败帖子 后台完成")
        except Exception as e:
            logger.error(f"重试失败: {e}")
        finally:
            _extraction_running = False
            _extraction_initial_by_platform = {}

    if run_mode == "process":
        import threading
        _extraction_running = True
        _extraction_initial_by_platform = initial_by_platform
        _p = _spawn_process_tasks_worker(batch_size=batch_size, reason="retry-errors")

        def _watch():
            global _extraction_running, _extraction_initial_by_platform
            try:
                _p.wait()
            finally:
                _extraction_running = False
                _extraction_initial_by_platform = {}

        threading.Thread(target=_watch, daemon=True).start()
    else:
        import threading
        _t = threading.Thread(target=_bg_thread, daemon=True)
        _t.start()
        logger.info(f"[后台线程] ▶ 启动 重试提取线程 tid={_t.ident} | 重置 {total} 条 | batch_size={batch_size}")
    msg_parts = []
    if to_extract:
        msg_parts.append(f"{to_extract} 条待重新提取")
    if to_fetch:
        msg_parts.append(f"{to_fetch} 条待重新抓取")
    return {
        "status": "ok",
        "message": "；".join(msg_parts),
        "reset": total,
        "source_info": task_get_source_info(),
    }





@app.post("/api/crawler/re-extract-all")
async def re_extract_all_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):
    """重新提取所有问题：删除旧题目、重置为待提取，后台重新 LLM 提取。"""
    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size
    logger.info(f"[API] 重新提取所有问题 被调用 batch_size={batch_size}")
    reset_count, deleted_questions, initial_by_platform = await asyncio.to_thread(prepare_re_extract_all)
    if reset_count == 0:
        return {
            "status": "ok",
            "message": "没有可重新提取的帖子（done/error 且含正文）",
            "reset": 0,
            "source_info": task_get_source_info(),
        }
    run_mode = getattr(_cfg, "crawler_background_run_mode", "process")
    logger.info(f"[API] 重新提取所有问题 重置 {reset_count} 条，删除 {deleted_questions} 道旧题目，后台模式={run_mode}")
    global _extraction_running, _extraction_initial_by_platform
    from backend.services.crawler import question_extractor
    _run_suffix = now_beijing_str("%Y%m%d_%H%M%S")
    question_extractor._llm_log_run_suffix = _run_suffix
    logger.info(f"[API] 重新提取 LLM 日志将写入: llm_prompt_log_{_run_suffix}.jsonl")

    def _bg_thread():
        global _extraction_running, _extraction_initial_by_platform
        try:
            _extraction_running = True
            _extraction_initial_by_platform = initial_by_platform
            task_execute("process_tasks", "button", batch_size=batch_size)
            logger.info(f"[API] 重新提取所有问题 后台完成")
        except Exception as e:
            logger.error(f"重新提取失败: {e}", exc_info=True)
        finally:
            _extraction_running = False
            _extraction_initial_by_platform = {}
            question_extractor._llm_log_run_suffix = None

    if run_mode == "process":
        import threading
        _extraction_running = True
        _extraction_initial_by_platform = initial_by_platform
        _p = _spawn_process_tasks_worker(batch_size=batch_size, reason="re-extract-all")

        def _watch():
            global _extraction_running, _extraction_initial_by_platform
            try:
                _p.wait()
            finally:
                _extraction_running = False
                _extraction_initial_by_platform = {}
                question_extractor._llm_log_run_suffix = None

        threading.Thread(target=_watch, daemon=True).start()
    else:
        import threading
        threading.Thread(target=_bg_thread, daemon=True).start()
    return {
        "status": "ok",
        "message": f"已重置 {reset_count} 条帖子（删除 {deleted_questions} 道旧题），开始重新提取",
        "reset": reset_count,
        "questions_deleted": deleted_questions,
        "source_info": task_get_source_info(),
    }





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
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "backend.services.scheduling.process_tasks_worker",
        "--batch-size",
        str(batch_size),
    ]
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd,
        cwd=str(_PROJECT_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
        **kwargs,
    )
    logger.info(f"[后台子进程] ▶ 启动 process_tasks worker pid={proc.pid} reason={reason} batch_size={batch_size}")
    return proc


def _spawn_batch_extract_subprocess(cmd: list, log_path: Path, total_count: int) -> None:
    """启动批量提取子进程，日志全量写文件，控制台每 60 秒打印一次进度条"""
    import subprocess
    import threading

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "a", encoding="utf-8")
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
            msg = f"\r{ts} | INFO    | [批量提取] {bar} {completed}/{total_count} ({pct}%)\n"
            sys.stdout.write(_with_color(msg, C_PROGRESS))
            sys.stdout.flush()

    def read_and_tee(pipe):
        nonlocal completed
        try:
            for line in iter(pipe.readline, b""):
                if not line:
                    break
                try:
                    text = line.decode("utf-8", errors="replace")
                except Exception:
                    text = str(line)
                logf.write(text)
                logf.flush()
                # 解析进度：完成 task_id=xxx 或 全部完成
                if "[BatchExtractWorker] 完成 task_id=" in text:
                    with lock:
                        completed += 1
                if "[BatchExtractWorker] 全部完成" in text:
                    with lock:
                        completed = total_count
                # 主终端透传 Stage2 关键进度（队列触发/开始/单任务完成/失败/本轮汇总）
                if "[Stage2Processor]" in text:
                    if (
                        "队列 " in text
                        or "开始处理 " in text
                        or "处理中 " in text
                        or "完成 task_id=" in text
                        or "处理失败 task_id=" in text
                        or "本轮完成 " in text
                    ):
                        sys.stdout.write(_colorize_log_line(text if text.endswith("\n") else text + "\n"))
                        sys.stdout.flush()
                # 主终端透传 BatchExtractWorker 关键日志（开始/处理中/完成/异常）
                if "[BatchExtractWorker]" in text:
                    if (
                        "开始批量提取" in text
                        or "处理 " in text
                        or "完成 task_id=" in text
                        or "批量提取异常" in text
                        or "全部完成" in text
                    ):
                        sys.stdout.write(_colorize_log_line(text if text.endswith("\n") else text + "\n"))
                        sys.stdout.flush()
                # 每 60 秒打印一次进度
                now = time.time()
                if now - last_print_time[0] >= 60:
                    last_print_time[0] = now
                    _print_progress()
        finally:
            pipe.close()
            with lock:
                _print_progress()
            logf.close()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=os.environ,
        **({"start_new_session": True} if sys.platform != "win32" else {}),
    )
    t = threading.Thread(target=read_and_tee, args=(proc.stdout,), daemon=True)
    t.start()


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
    # 子进程日志全量写 batch_extract.log，控制台每 60 秒打印进度条
    cmd = [sys.executable, "-m", "backend.services.scheduling.batch_extract_worker"] + valid_ids
    log_path = _BACKEND_LOGS / "batch_extract.log"
    _spawn_batch_extract_subprocess(cmd, log_path, len(valid_ids))
    logger.info(f"[API] 批量重新提取已启动（子进程），共 {len(valid_ids)} 条，日志: {log_path}")
    return {"status": "ok", "message": f"已提交 {len(valid_ids)} 条，后台执行中", "count": len(valid_ids)}


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
    log_path = _BACKEND_LOGS / "batch_extract.log"
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

    status: Optional[str] = Query(None, description="pending/fetched/done/error"),

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

    if status:

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



    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        total = conn.execute(

            f"SELECT COUNT(*) FROM crawl_tasks {where}", params

        ).fetchone()[0]

        rows = conn.execute(

            f"SELECT id, task_id, source_url, source_platform, post_title, status, "

            f"company, position, questions_count, discovered_at, processed_at, post_time, error_msg, "

            f"length(raw_content) AS content_len, discover_keyword, extraction_source, "

            f"extract_duration_min, agent_used_tool, trace_session_id "

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
    """根据配置生成训练脚本并转换数据，body.sample_ids 可选指定训练样本"""
    body = body or {}
    config = body.get("config")
    sample_ids = body.get("sample_ids")
    return _ft.generate_training_script(config=config, sample_ids=sample_ids)


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


