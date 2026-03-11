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

    # 统一的日志格式：完整日期时间 | 级别（7字符宽） | 消息
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"

    _loguru_logger.add(

        sys.stderr,

        colorize=True,

        format=_log_format,

        level="INFO",

    )

    _loguru_logger.add(

        _BACKEND_LOGS / "backend.log",

        rotation="10 MB",

        retention=5,

        encoding="utf-8",

        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",

        level="INFO",

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

from typing import Optional, List



import asyncio

import json

import requests

from fastapi import FastAPI, Query, HTTPException

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import StreamingResponse

from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel



from backend.agents.orchestrator import get_orchestrator

from backend.services.storage.sqlite_service import sqlite_service

from backend.services.scheduling.scheduler import crawl_scheduler



# 后台提取运行状态（供前端刷新后恢复进度显示）

_extraction_running = False

_extraction_initial_by_platform = {}  # 开始时的 fetched 数量按平台，如 {"nowcoder": 5, "xiaohongshu": 17}



app = FastAPI(

    title="面经 Agent API",

    description="面试复习助手后端接口",

    version="3.0"

)



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

    # Miner Agent

    mm = s.llm_model_id  # Miner 使用全局模型

    logger.info(f"  [Miner Agent] model={mm}, temperature={s.miner_temperature}, max_tokens={s.miner_max_tokens}, base={s.llm_base_url or '(同全局)'}")

    # Interviewer Agent

    im = s.interviewer_model or s.llm_model_id

    logger.info(f"  [Interviewer Agent] model={im}, temperature={s.interviewer_temperature}, base={s.interviewer_base_url or s.llm_base_url or '(同全局)'}")

    logger.info("=" * 60)





@app.on_event("startup")

async def startup_event():

    """FastAPI 启动时启动后台调度器，并可选预热 LLM"""

    from backend.config.config import settings as _s

    from backend.services.crawler.question_extractor import _print_miner_config_once

    

    # 初始化 Miner Agent 配置（提前打印，避免首次提取时才显示）

    _print_miner_config_once()

    

    _print_agent_llm_config()

    crawl_scheduler.start()

    logger.info("爬虫调度器已启动")



    # 同步预热 LLM，确保首次提取不因冷启动超时

    if _s.llm_warmup_enabled and _s.llm_base_url:

        await asyncio.to_thread(_warmup_llm_sync)





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

    """前端配置：默认用户 ID、Agent 最大步数等（来自 .env）"""

    from backend.config.config import settings as _s

    return {

        "default_user_id": _s.default_user_id,

        "interviewer_max_steps": _s.interviewer_max_steps,

        "crawler_process_batch_size": _s.crawler_process_batch_size,

    }





@app.get("/api/user/{user_id}/chat/history")

def get_chat_history(user_id: str):

    """获取用户最近一次对话历史，用于前端打开时自动加载"""

    session = sqlite_service.get_latest_session_for_user(user_id)

    if not session:

        return {"session_id": None, "messages": []}

    history = session.get("conversation_history") or []

    # 转为前端格式 [{role, content}]

    messages = [

        {"role": m.get("role", "user"), "content": m.get("content", "")}

        for m in history if m.get("content")

    ]

    return {"session_id": session["session_id"], "messages": messages}





# ══════════════════════════════════════════════════════

# 请求 / 响应模型

# ══════════════════════════════════════════════════════



class IngestRequest(BaseModel):

    url: str

    user_id: str = "default"

    source_platform: str = ""   # nowcoder / xiaohongshu





class ChatRequest(BaseModel):

    user_id: str

    message: str

    resume: Optional[str] = None

    session_id: Optional[str] = None





class SubmitAnswerRequest(BaseModel):

    user_id: str

    session_id: str

    question_id: str

    question_text: str

    user_answer: str

    question_tags: Optional[List[str]] = None





class EndSessionRequest(BaseModel):

    user_id: str

    session_id: str

    session_summary: str = ""





class NoteRequest(BaseModel):

    action: str         # create / list / update / delete

    user_id: str

    note_id: Optional[str] = None

    question_id: Optional[str] = None

    title: Optional[str] = None

    content: Optional[str] = None

    tags: Optional[List[str]] = None

    note_type: str = "concept"





# ══════════════════════════════════════════════════════

# 健康检查

# ══════════════════════════════════════════════════════



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

    _chat_logger = _logging.getLogger("chat")

    _chat_logger.info(f"[Chat ←] user={req.user_id} | {req.message[:120]}")



    last_err = None

    for attempt in range(3):

        try:

            reply, thinking_steps = await asyncio.wait_for(

                orchestrator.chat(

                    user_id=req.user_id,

                    message=req.message,

                    resume=req.resume,

                    session_id=req.session_id

                ),

                timeout=90.0

            )

            _chat_logger.info(

                f"[Chat →] user={req.user_id} | reply({len(reply)}chars): "

                f"{reply[:300]}{'...' if len(reply) > 300 else ''}"

            )

            return {"reply": reply, "thinking": thinking_steps}

        except asyncio.TimeoutError as e:

            last_err = e

            if attempt < 2:

                _chat_logger.warning(f"[Chat] 超时，重试 {attempt + 2}/3...")

                await asyncio.sleep(2)

            else:

                _chat_logger.error(f"[Chat ✗] user={req.user_id} TIMEOUT 90s")

                return {"reply": "⚠️ 响应超时（90s），LLM 服务可能繁忙，请稍后重试。", "error": "timeout"}

        except Exception as e:

            last_err = e

            err_msg = str(e)

            if attempt < 2 and _is_retryable_error(e):

                _chat_logger.warning(f"[Chat] 连接错误，重试 {attempt + 2}/3: {err_msg[:80]}")

                await asyncio.sleep(2)

                continue

            _chat_logger.error(f"[Chat ✗] user={req.user_id} error: {err_msg[:300]}")

            if "429" in err_msg or "SetLimitExceeded" in err_msg or "TooManyRequests" in err_msg:

                return {"reply": "⚠️ LLM 接口调用超出限额（429）。请前往火山引擎控制台 → 模型推理 → 安全体验模式，关闭或调整限制后重试。", "error": "rate_limit"}

            if "LLM调用失败" in err_msg or "api" in err_msg.lower() or "connection" in err_msg.lower():

                return {"reply": f"⚠️ LLM 接口调用失败，请检查 API Key 和网络连接：{err_msg[:200]}", "error": "llm_error"}

            return {"reply": f"⚠️ 内部错误：{err_msg[:200]}", "error": "server_error"}





@app.post("/api/chat/stream")

async def api_chat_stream(req: ChatRequest):

    """

    流式对话接口（SSE）：

    先等待 LLM 完整回复，然后按词推送 text/event-stream，给前端打字机效果。

    连接/超时错误会自动重试 2 次。

    """

    import logging as _logging

    _chat_logger = _logging.getLogger("chat")

    _chat_logger.info(f"[Stream ←] user={req.user_id} | {req.message[:120]}")



    async def generate():

        for attempt in range(3):

            try:

                _chat_logger.info(f"[Stream] 开始调用 orchestrator.chat(), attempt={attempt+1}")

                reply, thinking_steps = await asyncio.wait_for(

                    orchestrator.chat(

                        user_id=req.user_id,

                        message=req.message,

                        resume=req.resume,

                        session_id=req.session_id,

                    ),

                    timeout=90.0,

                )

                _chat_logger.info(f"[Stream] orchestrator.chat() 返回成功")

                _chat_logger.info(f"[Stream] reply 类型: {type(reply)}, 长度: {len(reply) if isinstance(reply, str) else 'N/A'}")

                _chat_logger.info(f"[Stream] thinking_steps 类型: {type(thinking_steps)}, 长度: {len(thinking_steps) if isinstance(thinking_steps, list) else 'N/A'}")

                _chat_logger.info(f"[Stream] reply 内容（前100字）: {str(reply)[:100]}")

                _chat_logger.info(f"[Stream] thinking_steps: {thinking_steps}")

                

                # 类型检查和转换

                if not isinstance(reply, str):

                    _chat_logger.error(f"[Stream] ❌ reply 不是字符串! 类型: {type(reply)}, 值: {reply}")

                    reply = str(reply) if reply else ""

                

                if not isinstance(thinking_steps, list):

                    _chat_logger.error(f"[Stream] ❌ thinking_steps 不是列表! 类型: {type(thinking_steps)}, 值: {thinking_steps}")

                    thinking_steps = []

                _chat_logger.info(f"[Stream →] {len(reply)}chars, thinking={len(thinking_steps)}steps")



                if thinking_steps:

                    data = json.dumps({"thinking": thinking_steps}, ensure_ascii=False)

                    yield f"data: {data}\n\n"

                    await asyncio.sleep(0)



                chunk_size = 3

                for i in range(0, len(reply), chunk_size):

                    chunk = reply[i:i + chunk_size]

                    data = json.dumps({"delta": chunk}, ensure_ascii=False)

                    yield f"data: {data}\n\n"

                    await asyncio.sleep(0.015)



                yield "data: [DONE]\n\n"

                return

            except asyncio.TimeoutError:

                if attempt < 2:

                    _chat_logger.warning(f"[Stream] 超时，重试 {attempt + 2}/3...")

                    await asyncio.sleep(2)

                else:

                    err = json.dumps({"error": "⚠️ 响应超时（90s），LLM 服务可能繁忙，请稍后重试"}, ensure_ascii=False)

                    yield f"data: {err}\n\n"

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

                    err = json.dumps({"error": msg}, ensure_ascii=False)

                else:

                    err = json.dumps({"error": f"⚠️ 错误：{err_str[:300]}"}, ensure_ascii=False)

                yield f"data: {err}\n\n"



    return StreamingResponse(

        generate(),

        media_type="text/event-stream",

        headers={

            "Cache-Control": "no-cache",

            "X-Accel-Buffering": "no",    # 禁止 nginx 缓冲

        },

    )





@app.post("/api/submit_answer")

async def api_submit_answer(req: SubmitAnswerRequest):

    """

    答题提交接口（确定性答题链）：

    评估 → SM-2更新 → 记忆写入 → 知识推荐（score ≤ 2 时）

    """

    try:

        result = await orchestrator.submit_answer(

            user_id=req.user_id,

            session_id=req.session_id,

            question_id=req.question_id,

            question_text=req.question_text,

            user_answer=req.user_answer,

            question_tags=req.question_tags

        )

        return result

    except Exception as e:

        err_msg = str(e)

        if "429" in err_msg or "SetLimitExceeded" in err_msg:

            raise HTTPException(status_code=429, detail="LLM 调用超出限额，请调整火山引擎安全体验模式")

        raise HTTPException(status_code=500, detail=err_msg[:500])





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

    profile = sqlite_service.get_user_profile(user_id)

    return {

        "user_id": user_id,

        "profile": profile,

        "mastery_summary": summary,

        "weak_tags": weak_tags,

        "recent_history": history

    }





@app.get("/api/user/{user_id}/reviews")

def get_due_reviews(user_id: str, limit: int = 10):

    """获取 SM-2 到期需要复习的题目"""

    due = sqlite_service.get_due_reviews(user_id, limit=limit)

    return {"user_id": user_id, "due_count": len(due), "questions": due}





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

    """获取爬虫调度器状态及统计信息"""

    return crawl_scheduler.get_stats()





@app.get("/api/crawler/extraction-status")

def get_extraction_status():

    """获取后台提取是否正在运行（前端刷新后可据此恢复进度显示）"""

    return {"running": _extraction_running, "initial_by_platform": _extraction_initial_by_platform}





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

        # 发现帖子（HTTP 请求，通常几秒）

        try:

            added, discovered_links = await asyncio.wait_for(

                loop.run_in_executor(

                    None,

                    lambda: crawl_scheduler.trigger_nowcoder_discovery(

                        keywords=req.keywords,

                        max_pages=req.max_pages,

                    )

                ),

                timeout=120,  # 发现阶段 2 分钟足够

            )

        except asyncio.TimeoutError:

            logger.warning("牛客帖子发现超时（120s）")

            raise HTTPException(status_code=504, detail="牛客帖子发现超时，请减少爬取页数后重试。")



        # LLM 提取题目（慢，使用本地 Ollama 时可能每帖需分钟级）

        # → 在后台线程中异步执行，立即返回给前端，无需等待

        if req.process and added > 0:

            def _bg_process():

                try:

                    cnt = crawl_scheduler.trigger_process_tasks(batch_size=added + 5)

                    logger.info(f"牛客后台提取完成：{cnt} 道题目入库")

                except Exception as e:

                    logger.error(f"牛客后台提取失败: {e}", exc_info=True)

            threading.Thread(target=_bg_process, daemon=True).start()



        tip = f"发现 {added} 条新帖子" + ("，LLM 提取已在后台进行，完成后可刷新任务列表" if req.process and added > 0 else "")

        return {

            "status": "ok",

            "platform": "nowcoder",

            "discovered": added,

            "discovered_links": discovered_links or [],

            "questions_added": -1,  # 后台异步，此时尚未完成

            "message": tip,

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

    count = await loop.run_in_executor(

        None,

        lambda: crawl_scheduler.trigger_process_tasks(batch_size=batch_size)

    )

    stats = sqlite_service.get_crawl_stats()

    logger.info(f"[API] 同步处理队列 完成 questions_added={count}")

    return {"status": "ok", "questions_added": count, "queue_stats": stats}





@app.post("/api/crawler/extract-pending")

async def extract_pending_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):

    """

    异步提取所有 fetched 状态（已爬取正文但尚未提取题目）的帖子。

    立即返回启动确认，LLM 提取在后台线程执行。

    """

    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size

    logger.info(f"[API] 提取未处理帖子 被调用 batch_size={batch_size}")

    import threading

    import sqlite3



    # 查询当前 fetched 数量

    with sqlite3.connect(sqlite_service.db_path) as conn:

        row = conn.execute(

            "SELECT COUNT(*) FROM crawl_tasks WHERE status='fetched'"

        ).fetchone()

    pending_count = row[0] if row else 0



    if pending_count == 0:

        logger.info("[API] 提取未处理帖子 无待处理，直接返回")

        return {"status": "ok", "message": "没有待提取的帖子（状态为 fetched 的记录为 0）", "pending": 0}



    logger.info(f"[API] 提取未处理帖子 启动后台线程，待处理 {pending_count} 条")

    global _extraction_running, _extraction_initial_by_platform



    # 查询各平台 fetched 数量作为初始值

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"

        ).fetchall()

    initial_by_platform = {r["source_platform"]: r["cnt"] for r in rows}



    def _bg():

        global _extraction_running, _extraction_initial_by_platform

        try:

            _extraction_running = True

            _extraction_initial_by_platform = initial_by_platform

            cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)

            logger.info(f"[API] 提取未处理帖子 后台完成：{cnt} 道题目入库")

        except Exception as e:

            logger.error(f"后台提取失败: {e}", exc_info=True)

        finally:

            _extraction_running = False

            _extraction_initial_by_platform = {}



    _t = threading.Thread(target=_bg, daemon=True)

    _t.start()

    logger.info(f"[后台线程] ▶ 启动 LLM提取线程 tid={_t.ident} | 待处理 {pending_count} 条 | batch_size={batch_size}")

    return {

        "status": "ok",

        "message": f"已启动后台提取，共 {pending_count} 条待处理帖子，batch_size={batch_size}",

        "pending": pending_count,

    }





@app.post("/api/crawler/clean-data")

async def clean_unrelated_data(batch_size: int | None = Query(default=None, ge=1, le=200)):

    """

    清洗无关帖：
    1. 直接删除所有 unrelated 状态的帖子（LLM 提取时已判断无关）
    2. 对 done 状态帖子用 LLM 二次判断，无关则删除

    返回：checked 检查数，deleted 删除数。

    """

    import sqlite3

    from backend.services.crawler.question_extractor import check_contents_related_batch



    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size

    logger.info(f"[API] 清洗数据 被调用 batch_size={batch_size}")

    deleted_total = 0



    # ── Step 1: 直接删除所有 unrelated 状态帖子 ──────────────────────

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        unrelated_rows = conn.execute(

            "SELECT task_id, source_url, post_title FROM crawl_tasks WHERE status='unrelated'"

        ).fetchall()



    for r in unrelated_rows:

        url = r["source_url"]

        title = (r["post_title"] or "")[:40]

        cnt = sqlite_service.delete_by_source_url(url)

        deleted_total += cnt

        logger.warning(f"  [unrelated] 直接删除无关帖: {title} | url={url[:80]} | 删除 {cnt} 题")



    logger.info(f"[API] 清洗数据 Step1 完成: 删除 {len(unrelated_rows)} 条 unrelated 帖，{deleted_total} 道题")



    # ── Step 2: 对 done 帖子用 LLM 二次判断 ─────────────────────────

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            """SELECT task_id, source_url, raw_content, post_title

               FROM crawl_tasks WHERE status='done' AND raw_content IS NOT NULL

               LIMIT ?""",

            (batch_size,),

        ).fetchall()



    if not rows:

        if not unrelated_rows:

            logger.info("[API] 清洗数据 无可清洗记录")

            return {"status": "ok", "message": "没有可清洗的记录", "checked": 0, "deleted": 0}

        stats = sqlite_service.get_crawl_stats()

        msg = f"已清洗 {len(unrelated_rows)} 条无关帖，删除 {deleted_total} 道无关题目"

        logger.info(f"[API] 清洗数据 完成: {msg}")

        return {"status": "ok", "message": msg, "checked": len(unrelated_rows), "deleted": deleted_total, "queue_stats": stats}



    tasks = [dict(r) for r in rows]

    contents = [t["raw_content"] or "" for t in tasks]

    BATCH = 5



    for i in range(0, len(contents), BATCH):

        chunk = contents[i : i + BATCH]

        chunk_tasks = tasks[i : i + BATCH]

        results = check_contents_related_batch(chunk)

        for j, related in enumerate(results):

            if not related:

                url = chunk_tasks[j]["source_url"]

                title = (chunk_tasks[j].get("post_title") or "")[:40]

                cnt = sqlite_service.delete_by_source_url(url)

                deleted_total += cnt

                logger.warning(f"  [done→删除] 内容与面经无关: {title}... | url={url[:80]} | 删除 {cnt} 题")



    stats = sqlite_service.get_crawl_stats()

    total_checked = len(unrelated_rows) + len(tasks)

    msg = f"已检查 {total_checked} 条（{len(unrelated_rows)} 条无关帖 + {len(tasks)} 条已完成），删除 {deleted_total} 道无关题目" if deleted_total else f"已检查 {total_checked} 条，均与面经相关"

    logger.info(f"[API] 清洗数据 完成: {msg}")

    return {"status": "ok", "message": msg, "checked": total_checked, "deleted": deleted_total, "queue_stats": stats}





@app.post("/api/crawler/retry-errors")

async def retry_error_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):

    """

    将 error 状态且有正文的帖子重置为 fetched，后台异步 LLM 提取。

    将 error 状态且无正文的帖子重置为 pending，等待重新抓取。

    """

    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size

    logger.info(f"[API] 重试失败帖子 被调用 batch_size={batch_size}")

    import threading, sqlite3



    with sqlite3.connect(sqlite_service.db_path) as conn:

        # 有正文或有图片：重置为 fetched，进行 LLM 提取（会自动触发 OCR）

        r1 = conn.execute(

            "UPDATE crawl_tasks SET status='fetched', error_msg=NULL "

            "WHERE status='error' AND ("

            "  raw_content IS NOT NULL "

            "  OR (image_paths IS NOT NULL AND image_paths != '[]')"

            ")"

        )

        to_extract = r1.rowcount

        # 无正文且无图片：重置为 pending，重新抓取

        r2 = conn.execute(

            "UPDATE crawl_tasks SET status='pending', error_msg=NULL "

            "WHERE status='error' "

            "AND (raw_content IS NULL OR trim(raw_content) = '') "

            "AND (image_paths IS NULL OR image_paths = '[]')"

        )

        to_fetch = r2.rowcount

        conn.commit()



    total = to_extract + to_fetch

    if total == 0:

        logger.info("[API] 重试失败帖子 无可重试，直接返回")

        return {"status": "ok", "message": "没有可重试的帖子（error 记录为 0）", "reset": 0}



    logger.info(f"[API] 重试失败帖子 重置 {total} 条，启动后台线程")

    global _extraction_running, _extraction_initial_by_platform



    # 重试后查询各平台 fetched 数量

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"

        ).fetchall()

    initial_by_platform = {r["source_platform"]: r["cnt"] for r in rows} if rows else {"nowcoder": total, "xiaohongshu": 0}



    def _bg():

        global _extraction_running, _extraction_initial_by_platform

        try:

            _extraction_running = True

            _extraction_initial_by_platform = initial_by_platform

            cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)

            logger.info(f"[API] 重试失败帖子 后台完成：{cnt} 道题目入库")

        except Exception as e:

            logger.error(f"重试失败: {e}")

        finally:

            _extraction_running = False

            _extraction_initial_by_platform = {}



    _t = threading.Thread(target=_bg, daemon=True)

    _t.start()

    logger.info(f"[后台线程] ▶ 启动 重试提取线程 tid={_t.ident} | 重置 {total} 条 | batch_size={batch_size}")

    msg_parts = []

    if to_extract:

        msg_parts.append(f"{to_extract} 条待重新提取")

    if to_fetch:

        msg_parts.append(f"{to_fetch} 条待重新抓取")

    return {"status": "ok", "message": "；".join(msg_parts), "reset": total}





@app.post("/api/crawler/re-extract-all")

async def re_extract_all_posts(batch_size: int | None = Query(default=None, ge=1, le=200)):

    """

    重新提取所有问题：将「已完成」或「失败」且有正文的帖子重置为待提取，删除旧题目，后台重新 LLM 提取。

    """

    batch_size = batch_size if batch_size is not None else _cfg.crawler_process_batch_size

    logger.info(f"[API] 重新提取所有问题 被调用 batch_size={batch_size}")

    import threading

    import sqlite3



    _re_extract_cond = "status IN ('done','error') AND raw_content IS NOT NULL"



    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            f"""SELECT task_id, source_url FROM crawl_tasks

               WHERE {_re_extract_cond}

               LIMIT ?""",

            (batch_size,),

        ).fetchall()

    tasks = [dict(r) for r in rows]



    if not tasks:

        logger.info("[API] 重新提取所有问题 无 done/error 记录可重提取")

        return {"status": "ok", "message": "没有可重新提取的帖子（done/error 且含正文）", "reset": 0}



    urls = [t["source_url"] for t in tasks]

    deleted_questions = 0

    # 同步删除 Neo4j 题库中的题目节点

    try:

        from backend.services.storage.neo4j_service import neo4j_service

        for url in urls:

            neo4j_service.delete_questions_by_source_url(url)

    except Exception as e:

        logger.warning("Neo4j 删除题目失败（SQLite 将照常删除）: %s", e)

    with sqlite3.connect(sqlite_service.db_path) as conn:

        for url in urls:

            cur = conn.execute("DELETE FROM questions WHERE source_url=?", (url,))

            deleted_questions += cur.rowcount

        conn.execute(

            f"""UPDATE crawl_tasks SET status='fetched', questions_count=0, error_msg=NULL, extraction_source=NULL

               WHERE {_re_extract_cond}

               AND source_url IN (""" + ",".join("?" * len(urls)) + ")",

            urls,

        )

        conn.commit()



    logger.info(f"[API] 重新提取所有问题 重置 {len(tasks)} 条，删除 {deleted_questions} 道旧题目，启动后台提取")

    global _extraction_running, _extraction_initial_by_platform



    # 本次重新提取使用独立日志文件（按时间戳）

    from datetime import datetime

    from backend.services.crawler import question_extractor

    _run_suffix = now_beijing_str("%Y%m%d_%H%M%S")

    question_extractor._llm_log_run_suffix = _run_suffix

    logger.info(f"[API] 重新提取 LLM 日志将写入: llm_prompt_log_{_run_suffix}.jsonl")



    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"

        ).fetchall()

    initial_by_platform = {r["source_platform"]: r["cnt"] for r in rows} if rows else {}



    def _bg():

        global _extraction_running, _extraction_initial_by_platform

        try:

            _extraction_running = True

            _extraction_initial_by_platform = initial_by_platform

            cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)

            logger.info(f"[API] 重新提取所有问题 后台完成：{cnt} 道题目入库")

        except Exception as e:

            logger.error(f"重新提取失败: {e}", exc_info=True)

        finally:

            _extraction_running = False

            _extraction_initial_by_platform = {}

            question_extractor._llm_log_run_suffix = None



    threading.Thread(target=_bg, daemon=True).start()

    return {

        "status": "ok",

        "message": f"已重置 {len(tasks)} 条帖子（删除 {deleted_questions} 道旧题），开始重新提取",

        "reset": len(tasks),

        "questions_deleted": deleted_questions,

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

    # 清理可能残留的 crawl_tasks / crawl_logs（delete_by_source_url 已删，此处兜底）

    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.execute("DELETE FROM crawl_tasks")

        conn.execute("DELETE FROM crawl_logs")

        # 兜底：删除所有来源为牛客/小红书的题目（crawl_tasks 为空时上面循环不会删题）

        # 同步删除 Neo4j 题库中的对应题目

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





@app.post("/api/crawler/tasks/{task_id}/re-extract")
async def re_extract_single_task(task_id: str):
    """
    对单个任务重新执行完整的 OCR + MinerAgent 提取流程（异步后台执行）。

    适用场景：
    - 任务状态为 error/fetched/done，需重新提取
    - 帖子包含图片，想验证 OCR 效果
    - 调试单条任务的提取结果

    立即返回启动确认，提取在后台线程执行。
    """
    import threading
    import sqlite3

    # 校验 task_id 存在
    with sqlite3.connect(sqlite_service.db_path) as conn:
        row = conn.execute(
            "SELECT task_id, status, post_title, length(raw_content) as clen FROM crawl_tasks WHERE task_id=?",
            (task_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")

    post_title = dict(row).get("post_title") or "(无标题)"
    content_len = dict(row).get("clen") or 0
    if content_len < 50:
        raise HTTPException(status_code=400, detail=f"任务正文为空或过短（{content_len}字），请先抓取正文")

    logger.info(f"[API] 单任务重新提取 task_id={task_id} title={post_title[:40]}...")

    result_holder = {}

    def _bg():
        from backend.services.scheduling.scheduler import process_single_task
        try:
            result = process_single_task(task_id)
            result_holder.update(result)
            logger.info(f"[API] 单任务提取完成 task_id={task_id}: {result}")
        except Exception as e:
            logger.error(f"[API] 单任务提取异常 task_id={task_id}: {e}")
            result_holder.update({"status": "error", "message": str(e)})

    t = threading.Thread(target=_bg, daemon=True)
    t.start()
    # 等待最多 300 秒（单任务含 OCR 通常在 30~120s 内完成）
    t.join(timeout=300)

    if t.is_alive():
        return {
            "status": "running",
            "task_id": task_id,
            "message": "提取仍在后台运行（超过 300s），请稍后刷新任务列表查看结果",
        }

    return {
        "task_id": task_id,
        **result_holder,
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

    sqlite_service.update_task_content(task_id, post_title=title, raw_content=content, image_paths=image_paths)

    logger.info(f"[API] 重抓正文成功 task_id={task_id} title={title[:40]}... ({len(content)} 字)")

    return {"status": "ok", "message": f"已更新正文 {len(content)} 字，可参与「从正文提取」"}





@app.get("/api/crawler/tasks")

def get_crawl_tasks(

    status: Optional[str] = Query(None, description="pending/fetched/done/error"),

    platform: Optional[str] = Query(None),

    keyword: Optional[str] = Query(None, description="发现关键词筛选"),

    limit: int = Query(20, ge=1, le=100),

    offset: int = Query(0, ge=0),

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

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""



    with sqlite3.connect(sqlite_service.db_path) as conn:

        conn.row_factory = sqlite3.Row

        total = conn.execute(

            f"SELECT COUNT(*) FROM crawl_tasks {where}", params

        ).fetchone()[0]

        rows = conn.execute(

            f"SELECT id, task_id, source_url, source_platform, post_title, status, "

            f"company, position, questions_count, discovered_at, processed_at, error_msg, "

            f"length(raw_content) AS content_len, discover_keyword, extraction_source, extract_duration_min "

            f"FROM crawl_tasks {where} ORDER BY id DESC LIMIT ? OFFSET ?",

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





@app.get("/api/finetune/samples")

async def finetune_samples(

    status: str = Query(None),

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

    order: str = Query("asc", regex="^(asc|desc)$"),

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

async def finetune_export():

    """将所有已标注样本导出为 微调/labeled_data.jsonl"""

    return _ft.export_labeled()


@app.post("/api/finetune/preview-log")
async def finetune_preview_log(body: dict):
    """
    预览日志文件前N条记录
    body: {log_path, limit}
    """
    from backend.services.finetune_preview import preview_log_file
    log_path = body.get("log_path", "")
    limit = body.get("limit", 10)
    if not log_path:
        raise HTTPException(status_code=400, detail="log_path 不能为空")
    return preview_log_file(log_path, limit)

