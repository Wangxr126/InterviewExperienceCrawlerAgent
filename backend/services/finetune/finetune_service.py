"""
微调数据服务
职责：
  - 从微调日志（微调/llm_logs/）导入样本到 SQLite finetune_samples 表
  - 调用远程大模型辅助生成标注结果
  - 保存人工确认的最终标注数据
  - 导出 labeled_data.jsonl 用于微调训练
  - FAQ 上传：解析问题+答案文件，保存到题库并写入微调样本
"""
from backend.utils.time_utils import now_beijing, now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import csv
import io
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

from backend.config.config import settings, _get as _env_get
from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1, is_stage2_incomplete

logger = logging.getLogger(__name__)

_TRAIN_SPAWN_LOCK = threading.Lock()

_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # backend/services/finetune -> 项目根
_FINETUNE_DIR = _PROJECT_ROOT / "微调"
_FINETUNE_LOGS_DIR = Path(settings.finetune_logs_dir)
_LABELED_PATH = _FINETUNE_DIR / "labeled_data.jsonl"
_RUN_CONFIG_PATH = _FINETUNE_DIR / "finetune_run_config.json"

# 辅助大模型使用的系统提示词（与 question_extractor 一致，但更严格要求完整题目）
_ASSIST_SYSTEM_PROMPT = """你是面经结构化专家，从面经原文中精准提取所有面试题，输出严格的 JSON 数组。

## 核心规则
- 必须且仅从「面经原文」中提取，不编造、不输出原文不存在的题目
- 从叙述句中挖掘题目（如「问了 RAG 原理」→ 提取为「请介绍 RAG 的原理」）
- 从叙述句中提取答案片段（如「我说了 RDB 和 AOF」→ answer_text 填 "RDB、AOF"）
- 开放性问题若原文无答案，基于知识给出高质量的实质性参考答案（分条列点）
- **口语化改写**：如果提取的题目过于口语化或不规范，改写为标准的面试问题形式（如「聊了下Redis」→「请介绍Redis的应用场景和特点」）
- **连续提问处理**：如果是连续的追问（如「Redis用过吗？怎么用的？为什么选它？」），可以合并为一个完整问题，或为每个子问题添加简单的场景背景

## 题目边界识别
- 编号：1. 2. ① ② 一、二、（1）（2）等
- 换行：每行独立知识点或问题，单独提取
- 分号：「；」或「;」连接的多个问题，逐个拆分
- 关键词：「问了」「手写」「手撕」「聊了」「介绍一下」后跟的内容

## 无效内容过滤（一律不提取）
- 纯过渡语：「然后」「接下来」「还有」「另外」「问了一些」
- 情绪感叹：「好难啊」「麻了」「凉了」「没答上来」
- 流程描述：「整体难度...」「面试官很和善」「共面了 XX 分钟」
- 少于 8 字且不含技术词汇的片段

## answer_text 格式
高质量分条列点答案，每条「1. 」「2. 」开头，换行分隔。

## 输出格式
直接输出 JSON 数组，不加 markdown 代码块或任何解释。
完全无关帖子输出 {"reason":"帖子与面经无关"}，无题目但相关时输出 []。

## question_type 分类（必须从以下类型中选择一个）
**算法编程类：**
- DP编程题：动态规划相关算法题
- 回溯编程题：回溯、DFS、BFS相关
- 贪心编程题：贪心算法相关
- 图算法题：图论、最短路径等
- 树算法题：二叉树、树的遍历等
- 链表题：链表操作相关
- 数组题：数组、字符串操作
- 其他算法题：其他算法类题目

**AI/ML相关：**
- LLM原理题：大语言模型原理、架构
- LLM算法题：Transformer、Attention等
- 模型结构题：神经网络结构设计
- 模型训练题：训练技巧、优化器等
- RAG题：检索增强生成相关
- Agent题：智能体、工具调用等
- CV题：计算机视觉相关
- NLP题：自然语言处理相关

**工程实践类：**
- 系统设计题：架构设计、分布式系统
- 数据库题：SQL、索引、事务等
- 缓存题：Redis、Memcached等
- 消息队列题：Kafka、RabbitMQ等
- 微服务题：服务拆分、治理等
- 性能优化题：性能调优相关
- 并发编程题：多线程、锁等

**基础理论类：**
- 操作系统题：进程、内存管理等
- 计算机网络题：TCP/IP、HTTP等
- 数据结构题：栈、队列、哈希表等
- 编程语言题：Python、Java等语言特性

**软技能类：**
- 项目经验题：项目介绍、难点等
- 行为题：团队协作、冲突处理等
- HR题：职业规划、薪资期望等

数组元素：{"question_text":"题目","answer_text":"高质量答案","difficulty":"easy/medium/hard或空","question_type":"从上述分类中选择","topic_tags":["标签"],"company":"","position":""}"""


def _get_db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """兼容旧库：检测表字段是否存在。"""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any((r[1] if isinstance(r, tuple) else r["name"]) == column for r in rows)
    except Exception:
        return False


# ===========================================================
# 导入：从 llm_logs 文件读取并写入 SQLite
# ===========================================================

def _classify_import_error(err_msg: str) -> str:
    """把导入异常归类为更可读的失败原因。"""
    msg = (err_msg or "").lower()
    if "expecting value" in msg or "jsondecodeerror" in msg:
        return "JSON 解析失败"
    if "no such table" in msg:
        return "数据库表不存在"
    if "database is locked" in msg:
        return "数据库被锁定"
    if "integrityerror" in msg or "unique constraint failed" in msg:
        return "数据库约束冲突"
    if "unicode" in msg or "decode" in msg:
        return "编码解析失败"
    return "其他异常"


def import_from_log_file(log_path: str, skip_existing: bool = True) -> Dict[str, int]:
    """
    从指定 JSONL 日志文件导入样本到 finetune_samples 表。
    支持 Miner 两阶段格式（stage1_output/stage2_output）和旧版 llm_logs 格式。
    返回 {"imported": N, "skipped": N, "failed": N, "details": {...}}
    """
    p = Path(log_path)
    if not p.exists():
        return {"imported": 0, "skipped": 0, "failed": 0, "error": "文件不存在", "details": {}}

    imported = skipped = failed = 0
    failed_samples = []
    error_summary: Dict[str, int] = {}
    now_ts = now_beijing().isoformat(timespec="seconds")
    import_log_id = f"import_{int(time.time() * 1000)}"  # 唯一导入ID

    with _get_db_conn() as conn:
        has_import_log_id = _table_has_column(conn, "finetune_samples", "import_log_id")
        for line_num, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                # Miner 两阶段格式
                if "stage1_output" in rec or "stage2_output" in rec:
                    content = (rec.get("content_preview", "") or rec.get("content", "")).strip()
                    stage1 = rec.get("stage1_output", "")
                    stage2 = rec.get("stage2_output", "")
                    # 若 Stage2 不完整（为省 token 只返回 answer 等），用 Stage1 补齐
                    if stage1 and stage2 and is_stage2_incomplete(stage2, stage1):
                        stage2 = merge_stage2_with_stage1(stage2, stage1)
                    stage1_model = rec.get("stage1_model", "")
                    stage2_model = rec.get("stage2_model", "")
                    title = rec.get("title", "")
                    source_url = rec.get("source_url", "")
                    ts = rec.get("ts", now_ts)
                    if not content and not stage1 and not stage2:
                        continue
                    if skip_existing:
                        exists = conn.execute(
                            "SELECT 1 FROM finetune_samples WHERE content=? AND stage1_output=? AND created_at=?",
                            (content[:500], stage1[:500] if stage1 else "", ts)
                        ).fetchone()
                        if exists:
                            skipped += 1
                            continue
                    if has_import_log_id:
                        conn.execute(
                            """INSERT INTO finetune_samples
                               (content, stage1_output, stage2_output, stage1_model, stage2_model, title, source_url, status, source, created_at, import_log_id)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (content or "(无原文)", stage1, stage2, stage1_model, stage2_model, title, source_url, "pending", "miner_two_stage", ts, import_log_id)
                        )
                    else:
                        conn.execute(
                            """INSERT INTO finetune_samples
                               (content, stage1_output, stage2_output, stage1_model, stage2_model, title, source_url, status, source, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (content or "(无原文)", stage1, stage2, stage1_model, stage2_model, title, source_url, "pending", "miner_two_stage", ts)
                        )
                else:
                    # 旧版 llm_logs 格式（兼容）
                    content = (rec.get("user_content", "") or rec.get("content", "")).strip()
                    title = rec.get("title", "")
                    source_url = rec.get("source_url", "")
                    stage2 = rec.get("llm_response", "") or rec.get("llm_raw", "")
                    ts = rec.get("ts", now_ts)
                    if not content:
                        continue
                    if skip_existing:
                        exists = conn.execute(
                            "SELECT 1 FROM finetune_samples WHERE content=? AND created_at=?",
                            (content[:500], ts)
                        ).fetchone()
                        if exists:
                            skipped += 1
                            continue
                    if has_import_log_id:
                        conn.execute(
                            """INSERT INTO finetune_samples
                               (content, stage1_output, stage2_output, title, source_url, status, source, created_at, import_log_id)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (content, "", stage2, title, source_url, "pending", "llm_logs", ts, import_log_id)
                        )
                    else:
                        conn.execute(
                            """INSERT INTO finetune_samples
                               (content, stage1_output, stage2_output, title, source_url, status, source, created_at)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (content, "", stage2, title, source_url, "pending", "llm_logs", ts)
                        )
                imported += 1
            except Exception as e:
                failed += 1
                reason = _classify_import_error(str(e))
                error_summary[reason] = error_summary.get(reason, 0) + 1
                failed_samples.append({"line": line_num, "reason": reason, "error": str(e), "preview": line[:80]})
        conn.commit()
    
    # 保存导入日志到数据库
    _save_import_log(import_log_id, p.name, imported, skipped, failed, failed_samples)
    
    # 统一输出结果
    logger.info("导入完成: imported=%d skipped=%d failed=%d from %s (log_id=%s)", 
                imported, skipped, failed, p.name, import_log_id)
    
    return {
        "imported": imported, 
        "skipped": skipped, 
        "duplicated": skipped,
        "failed": failed,
        "import_log_id": import_log_id,
        "details": {
            "file": p.name,
            "total_lines": imported + skipped + failed,
            "duplicate_count": skipped,
            "error_summary": error_summary,
            "failed_samples": failed_samples[:10]  # 前10条失败样本
        }
    }


def fix_merged_stage2_samples(source_filter: str = "miner_two_stage") -> Dict[str, int]:
    """
    修复已导入的标注样本：对 stage2_output 不完整的记录，用 stage1_output 补齐缺失字段。
    可选 source_filter 仅处理指定来源（默认 miner_two_stage）。
    返回 {"fixed": N, "skipped": N, "failed": N}
    """
    fixed = skipped = failed = 0
    with _get_db_conn() as conn:
        if source_filter:
            rows = conn.execute(
                """SELECT id, stage1_output, stage2_output, final_output FROM finetune_samples WHERE source=?""",
                (source_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, stage1_output, stage2_output, final_output FROM finetune_samples"""
            ).fetchall()
        for row in rows:
            sid = row["id"]
            stage1 = row["stage1_output"] or ""
            stage2 = row["stage2_output"] or ""
            final = row["final_output"] or ""
            if not stage1 or not stage2:
                skipped += 1
                continue
            if not is_stage2_incomplete(stage2, stage1):
                skipped += 1
                continue
            try:
                merged = merge_stage2_with_stage1(stage2, stage1)
                conn.execute(
                    "UPDATE finetune_samples SET stage2_output=? WHERE id=?",
                    (merged, sid),
                )
                # 若 final_output 与 stage2_output 相同（用户点「无需修改」），一并更新
                if final == stage2:
                    conn.execute(
                        "UPDATE finetune_samples SET final_output=? WHERE id=?",
                        (merged, sid),
                    )
                fixed += 1
            except Exception as e:
                failed += 1
                logger.warning("修复样本 id=%d 失败: %s", sid, e)
        conn.commit()
    logger.info("修复 Stage2 合并: fixed=%d skipped=%d failed=%d", fixed, skipped, failed)
    return {"fixed": fixed, "skipped": skipped, "failed": failed}


def import_all_logs() -> Dict:
    """
    扫描 微调/llm_logs/ 下所有 JSONL 文件，逐个导入（跳过已存在记录）。
    返回汇总结果。
    """
    files = list_log_files()
    total_imported = total_skipped = 0
    for f in files:
        res = import_from_log_file(f["path"])
        total_imported += res.get("imported", 0)
        total_skipped += res.get("skipped", 0)
    logger.info("全量导入完成: imported=%d skipped=%d files=%d", total_imported, total_skipped, len(files))
    return {"imported": total_imported, "skipped": total_skipped, "files": len(files)}


def import_all_logs() -> Dict[str, int]:
    """
    扫描 微调/llm_logs/ 下所有 JSONL 文件，全量导入到 finetune_samples。
    已存在的记录自动跳过（content+created_at 去重）。
    返回汇总结果 {"imported": N, "skipped": N, "files": N}
    """
    log_root = _FINETUNE_LOGS_DIR
    total_imported = total_skipped = file_count = 0
    if not log_root.exists():
        return {"imported": 0, "skipped": 0, "files": 0}
    for f in sorted(log_root.rglob("*.jsonl"), key=lambda x: x.stat().st_mtime):
        res = import_from_log_file(str(f))
        total_imported += res.get("imported", 0)
        total_skipped += res.get("skipped", 0)
        file_count += 1
    logger.info("全量导入完成: files=%d imported=%d skipped=%d", file_count, total_imported, total_skipped)
    return {"imported": total_imported, "skipped": total_skipped, "files": file_count}


def list_log_files() -> List[Dict]:
    """列出 微调/llm_logs/ 下所有 JSONL 文件，Miner 两阶段日志排最前"""
    log_root = _FINETUNE_LOGS_DIR
    result = []
    if not log_root.exists():
        log_root.mkdir(parents=True, exist_ok=True)
    for f in sorted(log_root.rglob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        rel = f.relative_to(log_root)
        parts = rel.parts
        if "miner_two_stage" in f.name:
            model = "Miner两阶段"
        elif len(parts) > 1:
            model = parts[0]
        else:
            model = "默认目录"
        try:
            line_count = sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            line_count = 0
        result.append({
            "path": str(f),
            "rel_path": str(rel),
            "model": model,
            "filename": f.name,
            "line_count": line_count,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
        })
    # Miner 两阶段日志排最前，其余按修改时间倒序
    miners = [r for r in result if "miner_two_stage" in r.get("filename", "")]
    others = [r for r in result if "miner_two_stage" not in r.get("filename", "")]
    others.sort(key=lambda r: r.get("mtime", ""), reverse=True)
    return miners + others


def delete_log_file(log_path: str) -> Dict:
    """删除指定日志文件，仅允许删除 微调/llm_logs/ 下的文件"""
    log_root = _FINETUNE_LOGS_DIR
    p = Path(log_path).resolve()
    try:
        root_resolved = log_root.resolve()
        try:
            p.relative_to(root_resolved)
        except ValueError:
            return {"status": "error", "message": "只能删除微调/llm_logs/下的文件"}
        if not p.exists():
            return {"status": "error", "message": "文件不存在"}
        if not p.is_file():
            return {"status": "error", "message": "路径不是文件"}
        p.unlink()
        logger.info("已删除日志文件: %s", p.name)
        return {"status": "ok", "message": f"已删除 {p.name}"}
    except Exception as e:
        logger.warning("删除日志文件失败: %s", e)
        return {"status": "error", "message": str(e)}


# ===========================================================
# 样本列表 & 详情
# ===========================================================

def list_samples(status: str = None, page: int = 1, page_size: int = 20, order: str = "asc") -> Dict:
    """分页查询 finetune_samples，可按 status 过滤，支持排序"""
    offset = (page - 1) * page_size
    where = "WHERE status=?" if status else ""
    params_count = (status,) if status else ()
    params_list = (status, page_size, offset) if status else (page_size, offset)
    order_by = "ORDER BY id ASC" if order == "asc" else "ORDER BY id DESC"

    with _get_db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM finetune_samples {where}", params_count
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, content,
                       status, is_modified, created_at, modified_at, labeled_at, source,
                       title, source_url
                FROM finetune_samples {where}
                {order_by} LIMIT ? OFFSET ?""",
            params_list
        ).fetchall()
    
    items = []
    for r in rows:
        item = dict(r)
        
        # 添加 content_preview 字段（前端需要）
        item["content_preview"] = item.get("content") or ""
        
        # 如果没有 source_url，尝试根据内容从 crawl_tasks 表中查找
        if not item.get("source_url") and item.get("content_preview"):
            with _get_db_conn() as conn:
                content_prefix = item["content_preview"][:500]
                match_row = conn.execute(
                    """
                    SELECT source_url, post_title
                    FROM crawl_tasks
                    WHERE raw_content LIKE ? OR raw_content LIKE ?
                    LIMIT 1
                    """,
                    (f"%{content_prefix[:100]}%", f"%{content_prefix[-100:]}%")
                ).fetchone()
                
                if match_row:
                    item["source_url"] = match_row["source_url"]
                    if not item.get("title"):
                        item["title"] = match_row["post_title"]
        
        items.append(item)
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def get_sample(sample_id: int) -> Optional[Dict]:
    """获取单条样本完整内容"""
    with _get_db_conn() as conn:
        # finetune_samples.content 来自 llm_logs 的 content_preview，可能被截断。
        # 若该样本有 source_url，则尝试从 crawl_tasks.raw_content 读取完整原文。
        row = conn.execute(
            """
            SELECT fs.*,
                   ct.raw_content AS raw_content
            FROM finetune_samples fs
            LEFT JOIN crawl_tasks ct
              ON ct.source_url = fs.source_url
            WHERE fs.id=?
            """,
            (sample_id,),
        ).fetchone()
    
    if not row:
        return None
    
    result = dict(row)
    
    # 如果没有 source_url，尝试根据内容从 crawl_tasks 表中查找
    if not result.get("source_url") and result.get("content"):
        with _get_db_conn() as conn:
            # 根据内容的前500字符模糊匹配查找相关的爬虫任务
            content_prefix = result["content"][:500]
            match_row = conn.execute(
                """
                SELECT source_url, raw_content, post_title
                FROM crawl_tasks
                WHERE raw_content LIKE ? OR raw_content LIKE ?
                LIMIT 1
                """,
                (f"%{content_prefix[:100]}%", f"%{content_prefix[-100:]}%")
            ).fetchone()
            
            if match_row:
                result["source_url"] = match_row["source_url"]
                if not result.get("raw_content"):
                    result["raw_content"] = match_row["raw_content"]
                if not result.get("title"):
                    result["title"] = match_row["post_title"]
    
    return result


# ===========================================================
# 辅助大模型生成
# ===========================================================

def openai_miner_style_extract(
    *,
    content: str,
    title: str = "",
    model: str,
    api_key: Optional[str],
    base_url: str,
    temperature: float,
    timeout: float = 120.0,
) -> Dict:
    """
    使用与「微调辅助标注」相同的 system prompt，通过 OpenAI 兼容接口做一次面经结构化提取。
    成功返回 {"output": str, "model": str}，失败返回 {"error": str}
    """
    if not base_url:
        return {"error": "未配置 base_url"}
    if not model:
        return {"error": "未配置 model"}
    full_content = content
    if title:
        full_content = f"【帖子标题】{title}\n\n【面经正文】\n{content}"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key or "sk-dummy", base_url=base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _ASSIST_SYSTEM_PROMPT},
                {"role": "user", "content": f"## 面经原文\n{full_content}\n\n请提取所有面试题并输出 JSON 数组。"},
            ],
            temperature=temperature,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return {"output": raw, "model": model}
    except Exception as e:
        logger.error("openai_miner_style_extract 失败: %s", e)
        return {"error": str(e)}


def assist_generate(content: str, title: str = "", model: str = None, api_key: str = None,
                    base_url: str = None, temperature: float = None) -> Dict:
    """
    调用远程大模型对面经原文生成高质量标注结果。
    返回 {"output": "JSON字符串", "model": "..."}
    """
    _model = model or settings.finetune_llm_model
    _api_key = api_key or settings.finetune_llm_api_key
    _base_url = base_url or settings.finetune_llm_base_url
    _temp = temperature if temperature is not None else settings.finetune_llm_temperature
    to = float(settings.finetune_llm_timeout or 120)
    return openai_miner_style_extract(
        content=content,
        title=title,
        model=_model,
        api_key=_api_key,
        base_url=_base_url,
        temperature=_temp,
        timeout=to,
    )


def list_model_compare_presets() -> List[Dict]:
    """模型对比页可选预设（不含密钥）。"""
    finetuned = settings.compare_finetuned_ollama_model
    presets = [
        {
            "id": "miner_local",
            "label": "Miner · 本地",
            "description": "与数据采集/Miner 一致的本地 OpenAI 兼容端点（通常为 Ollama 基座）",
            "model": settings.miner_local_model or "",
            "base_url": settings.miner_local_base_url or "",
            "configured": bool(
                (settings.miner_local_model or "").strip() and (settings.miner_local_base_url or "").strip()
            ),
        },
        {
            "id": "finetuned_local",
            "label": "本地 · 微调后",
            "description": "同一本地端点，换用 COMPARE_FINETUNED_OLLAMA_MODEL 指定的模型名（如已导入的 LoRA/GGUF）",
            "model": finetuned,
            "base_url": settings.miner_local_base_url or "",
            "configured": bool(
                finetuned and (settings.miner_local_base_url or "").strip()
            ),
        },
        {
            "id": "miner_remote",
            "label": "Miner · 远程",
            "description": "Miner 远程 API（如火山等）",
            "model": settings.miner_remote_model or "",
            "base_url": (settings.miner_remote_base_url or "")[:56] + "…"
            if len(settings.miner_remote_base_url or "") > 56
            else (settings.miner_remote_base_url or ""),
            "configured": bool(
                (settings.miner_remote_model or "").strip()
                and (settings.miner_remote_base_url or "").strip()
            ),
        },
        {
            "id": "finetune_assist",
            "label": "标注辅助模型",
            "description": "微调页「AI 辅助」当前使用的 FINETUNE_* 配置",
            "model": settings.finetune_llm_model or "",
            "base_url": (settings.finetune_llm_base_url or "")[:56] + "…"
            if len(settings.finetune_llm_base_url or "") > 56
            else (settings.finetune_llm_base_url or ""),
            "configured": bool(
                (settings.finetune_llm_model or "").strip()
                and (settings.finetune_llm_base_url or "").strip()
            ),
        },
        {
            "id": "app_remote",
            "label": "全局远程（练习对话）",
            "description": "与 LLM_MODE=remote 时主对话相同的远程模型",
            "model": settings.llm_remote_model or "",
            "base_url": (settings.llm_remote_base_url or "")[:56] + "…"
            if len(settings.llm_remote_base_url or "") > 56
            else (settings.llm_remote_base_url or ""),
            "configured": bool(
                (settings.llm_remote_model or "").strip()
                and (settings.llm_remote_base_url or "").strip()
            ),
        },
    ]
    return presets


def _resolve_compare_preset(preset_id: str) -> Optional[Dict]:
    """解析预设为 openai_miner_style_extract 参数。失败返回 None。"""
    temp = settings.finetune_llm_temperature
    if preset_id == "miner_local":
        if not (settings.miner_local_model and settings.miner_local_base_url):
            return None
        return {
            "model": settings.miner_local_model,
            "api_key": _env_get("MINER_LOCAL_API_KEY") or settings.llm_local_api_key,
            "base_url": settings.miner_local_base_url,
            "timeout": float(settings.miner_local_timeout or 120),
            "temperature": temp,
        }
    if preset_id == "finetuned_local":
        m = settings.compare_finetuned_ollama_model
        if not m or not settings.miner_local_base_url:
            return None
        return {
            "model": m,
            "api_key": _env_get("MINER_LOCAL_API_KEY") or settings.llm_local_api_key,
            "base_url": settings.miner_local_base_url,
            "timeout": float(settings.miner_local_timeout or 120),
            "temperature": temp,
        }
    if preset_id == "miner_remote":
        if not (settings.miner_remote_model and settings.miner_remote_base_url):
            return None
        return {
            "model": settings.miner_remote_model,
            "api_key": settings.miner_remote_api_key,
            "base_url": settings.miner_remote_base_url,
            "timeout": float(settings.miner_remote_timeout or 180),
            "temperature": temp,
        }
    if preset_id == "finetune_assist":
        if not (settings.finetune_llm_model and settings.finetune_llm_base_url):
            return None
        return {
            "model": settings.finetune_llm_model,
            "api_key": settings.finetune_llm_api_key,
            "base_url": settings.finetune_llm_base_url,
            "timeout": float(settings.finetune_llm_timeout or 120),
            "temperature": temp,
        }
    if preset_id == "app_remote":
        if not (settings.llm_remote_model and settings.llm_remote_base_url):
            return None
        return {
            "model": settings.llm_remote_model,
            "api_key": settings.llm_remote_api_key,
            "base_url": settings.llm_remote_base_url,
            "timeout": float(settings.llm_remote_timeout or 300),
            "temperature": temp,
        }
    return None


def _preset_label(preset_id: str) -> str:
    for p in list_model_compare_presets():
        if p["id"] == preset_id:
            return p["label"]
    return preset_id


def compare_models_parallel(preset_ids: List[str], content: str, title: str = "") -> Dict:
    """
    并行对多个预设调用同一套面经提取提示，用于对比输出。
    preset_ids 顺序在返回结果中保持。
    """
    import concurrent.futures
    import time as _time

    def _one(pid: str) -> Dict:
        t0 = _time.perf_counter()
        meta = _resolve_compare_preset(pid)
        if not meta:
            return {
                "preset_id": pid,
                "label": _preset_label(pid),
                "ok": False,
                "error": "该预设未配置完整，请检查 .env",
                "output": "",
                "model": "",
                "latency_ms": 0,
                "question_count": None,
            }
        r = openai_miner_style_extract(
            content=content,
            title=title,
            model=meta["model"],
            api_key=meta["api_key"],
            base_url=meta["base_url"],
            temperature=meta["temperature"],
            timeout=meta["timeout"],
        )
        ms = int((_time.perf_counter() - t0) * 1000)
        if r.get("error"):
            return {
                "preset_id": pid,
                "label": _preset_label(pid),
                "ok": False,
                "error": r["error"],
                "output": "",
                "model": meta.get("model", ""),
                "latency_ms": ms,
                "question_count": None,
            }
        out = r.get("output") or ""
        qn = None
        try:
            parsed = json.loads(out)
            if isinstance(parsed, list):
                qn = len(parsed)
        except Exception:
            pass
        return {
            "preset_id": pid,
            "label": _preset_label(pid),
            "ok": True,
            "error": None,
            "output": out,
            "model": r.get("model", meta.get("model", "")),
            "latency_ms": ms,
            "question_count": qn,
        }

    n = len(preset_ids)
    results: List[Optional[Dict]] = [None] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, n)) as ex:
        futs = {ex.submit(_one, preset_ids[i]): i for i in range(n)}
        for fut in concurrent.futures.as_completed(futs):
            idx = futs[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                results[idx] = {
                    "preset_id": preset_ids[idx],
                    "label": _preset_label(preset_ids[idx]),
                    "ok": False,
                    "error": str(e),
                    "output": "",
                    "model": "",
                    "latency_ms": 0,
                    "question_count": None,
                }
    return {"results": [r for r in results if r is not None]}


# ===========================================================
# 保存标注 & 导出
# ===========================================================

def save_label(sample_id: int, final_output: str, is_modified: bool = False) -> Dict:
    """保存人工确认的最终标注结果，同时更新 modified_at"""
    now = now_beijing().isoformat(timespec="seconds")
    with _get_db_conn() as conn:
        conn.execute(
            """UPDATE finetune_samples
               SET final_output=?, is_modified=?, status='labeled', labeled_at=?, modified_at=?
               WHERE id=?""",
            (final_output, 1 if is_modified else 0, now, now, sample_id)
        )
        conn.commit()
    return {"status": "ok", "labeled_at": now}


def save_assist_output(sample_id: int, assist_output: str) -> Dict:
    """保存大模型辅助输出（中间结果，不改变标注状态）"""
    with _get_db_conn() as conn:
        conn.execute(
            "UPDATE finetune_samples SET assist_output=? WHERE id=?",
            (assist_output, sample_id)
        )
        conn.commit()
    return {"status": "ok"}


def delete_sample(sample_id: int) -> Dict:
    """删除指定微调样本"""
    with _get_db_conn() as conn:
        cur = conn.execute("DELETE FROM finetune_samples WHERE id=?", (sample_id,))
        conn.commit()
        return {"status": "ok", "deleted": cur.rowcount}


def export_labeled(output_path: str = None, sample_ids: List[int] = None) -> Dict:
    """
    将 labeled 状态的样本导出为 labeled_data.jsonl（prompt/completion 格式）。
    sample_ids: 可选，指定则只导出这些 ID；否则导出全部已标注。
    返回导出数量。
    """
    out_p = Path(output_path) if output_path else _LABELED_PATH
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with _get_db_conn() as conn:
        if sample_ids:
            placeholders = ",".join("?" * len(sample_ids))
            rows = conn.execute(
                f"""SELECT content, final_output, is_modified, labeled_at FROM finetune_samples
                    WHERE id IN ({placeholders}) AND status='labeled' AND final_output IS NOT NULL""",
                sample_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content, final_output, is_modified, labeled_at FROM finetune_samples WHERE status='labeled' AND final_output IS NOT NULL"
            ).fetchall()

    count = 0
    with open(out_p, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            record = {
                "prompt": row["content"],
                "completion": row["final_output"],
                "is_modified": bool(row["is_modified"]),
                "labeled_at": row["labeled_at"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    logger.info("导出标注数据 %d 条 → %s", count, out_p)
    return {"exported": count, "path": str(out_p)}


def get_stats() -> Dict:
    """微调数据统计"""
    def _count_questions(output_text: str) -> int:
        """统计单条输出中的题目数量，异常或非数组返回 0。"""
        if not output_text:
            return 0
        try:
            parsed = json.loads(output_text)
        except Exception:
            return 0
        return len(parsed) if isinstance(parsed, list) else 0

    with _get_db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM finetune_samples").fetchone()[0]
        labeled = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE status='labeled'").fetchone()[0]
        modified = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE is_modified=1").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE status='pending'").fetchone()[0]
        rows = conn.execute(
            """
            SELECT final_output, assist_output, stage2_output, stage1_output
            FROM finetune_samples
            """
        ).fetchall()

    # 题目总数按“可用于微调的最终结果优先”统计：
    # final_output > assist_output > stage2_output > stage1_output
    question_total = 0
    for row in rows:
        best_output = (
            row["final_output"]
            or row["assist_output"]
            or row["stage2_output"]
            or row["stage1_output"]
            or ""
        )
        question_total += _count_questions(best_output)

    return {
        "total": total,
        "pending": pending,
        "labeled": labeled,
        "modified": modified,
        "question_total": question_total,
        "log_files": len(list_log_files()),
    }


# ===========================================================
# 导入日志管理（新增）
# ===========================================================

def _save_import_log(import_log_id: str, filename: str, imported: int, skipped: int, 
                     failed: int, failed_samples: List[Dict]) -> None:
    """
    保存导入日志到数据库（finetune_import_logs 表）
    用于追踪每次导入的详细信息
    """
    try:
        with _get_db_conn() as conn:
            # 检查表是否存在，不存在则创建
            conn.execute("""
                CREATE TABLE IF NOT EXISTS finetune_import_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_log_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    imported INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    failed_samples TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            now = now_beijing_str()
            conn.execute("""
                INSERT INTO finetune_import_logs 
                (import_log_id, filename, imported, skipped, failed, failed_samples, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                import_log_id,
                filename,
                imported,
                skipped,
                failed,
                json.dumps(failed_samples[:10], ensure_ascii=False),  # 只保存前10条
                now,
                now
            ))
            conn.commit()
            logger.info("导入日志已保存: %s", import_log_id)
    except Exception as e:
        logger.warning("保存导入日志失败: %s", e)


def get_import_logs(limit: int = 20) -> List[Dict]:
    """
    获取最近的导入日志列表
    返回 [{"import_log_id": "...", "filename": "...", "imported": N, "skipped": N, "failed": N, "created_at": "...", ...}]
    """
    try:
        with _get_db_conn() as conn:
            rows = conn.execute("""
                SELECT import_log_id, filename, imported, skipped, failed, failed_samples, created_at
                FROM finetune_import_logs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("获取导入日志失败: %s", e)
        return []


def get_import_log_detail(import_log_id: str) -> Optional[Dict]:
    """
    获取单条导入日志的详细信息
    返回 {"import_log_id": "...", "filename": "...", "imported": N, "skipped": N, "failed": N, "failed_samples": [...], "created_at": "..."}
    """
    try:
        with _get_db_conn() as conn:
            row = conn.execute("""
                SELECT import_log_id, filename, imported, skipped, failed, failed_samples, created_at
                FROM finetune_import_logs
                WHERE import_log_id = ?
            """, (import_log_id,)).fetchone()
            if row:
                result = dict(row)
                # 解析 failed_samples JSON
                try:
                    result["failed_samples"] = json.loads(result.get("failed_samples", "[]"))
                except Exception:
                    result["failed_samples"] = []
                # 兼容前端展示：重复数=跳过数，并聚合失败原因统计
                result["duplicate_count"] = result.get("skipped", 0)
                summary: Dict[str, int] = {}
                for s in result.get("failed_samples", []):
                    reason = (s or {}).get("reason") or _classify_import_error((s or {}).get("error", ""))
                    summary[reason] = summary.get(reason, 0) + 1
                result["error_summary"] = summary
                return result
    except Exception as e:
        logger.warning("获取导入日志详情失败: %s", e)
    return None


def get_samples_by_import_log(import_log_id: str, page: int = 1, page_size: int = 20) -> Dict:
    """
    获取某次导入的所有样本
    返回 {"total": N, "items": [...], "import_log_id": "..."}
    """
    offset = (page - 1) * page_size
    try:
        with _get_db_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM finetune_samples WHERE import_log_id = ?",
                (import_log_id,)
            ).fetchone()[0]
            
            rows = conn.execute("""
                SELECT id, content as content_preview, status, is_modified, created_at, 
                       modified_at, labeled_at, source, stage1_model, stage2_model
                FROM finetune_samples
                WHERE import_log_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (import_log_id, page_size, offset)).fetchall()
            
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "import_log_id": import_log_id,
                "items": [dict(r) for r in rows]
            }
    except Exception as e:
        logger.warning("获取导入样本失败: %s", e)
        return {"total": 0, "items": [], "import_log_id": import_log_id}


def delete_import_log(import_log_id: str) -> Dict:
    """
    删除某次导入的所有样本和日志记录
    返回 {"status": "ok", "deleted_samples": N}
    """
    try:
        with _get_db_conn() as conn:
            # 删除样本
            cur = conn.execute(
                "DELETE FROM finetune_samples WHERE import_log_id = ?",
                (import_log_id,)
            )
            deleted_count = cur.rowcount
            
            # 删除日志
            conn.execute(
                "DELETE FROM finetune_import_logs WHERE import_log_id = ?",
                (import_log_id,)
            )
            conn.commit()
            
            logger.info("已删除导入日志 %s，共删除 %d 条样本", import_log_id, deleted_count)
            return {"status": "ok", "deleted_samples": deleted_count}
    except Exception as e:
        logger.warning("删除导入日志失败: %s", e)
        return {"status": "error", "message": str(e)}


def preview_log_file(log_path: str, limit: int = 10) -> Dict:
    """
    预览日志文件前N条记录，支持 Miner 两阶段格式和旧版 llm_logs 格式
    返回 {"samples": [...], "total": N, "showing": N}
    
    【重要】Stage2 豆包答案显示规则：
    - 若 stage2_output 存在且有效 → 显示为 stage2_obj
    - 若 stage2_output 不完整 → 用 stage1_output 补齐后显示
    - 若都不存在 → 显示 None
    """
    p = Path(log_path)
    if not p.exists():
        return {"error": "文件不存在", "samples": [], "total": 0, "showing": 0}
    samples = []
    total = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            total += 1
            if len(samples) < limit:
                try:
                    rec = json.loads(line)
                    
                    def _parse_json(s):
                        """安全解析 JSON，失败返回错误对象"""
                        if not s:
                            return None
                        try:
                            return json.loads(s)
                        except Exception:
                            return {"error": "无效JSON", "raw": str(s)[:200]}
                    
                    # Miner 两阶段格式
                    if "stage1_output" in rec or "stage2_output" in rec:
                        content = rec.get("content_preview", "") or rec.get("content", "")
                        title = rec.get("title", "")
                        source_url = rec.get("source_url", "")
                        stage1_raw = rec.get("stage1_output", "")
                        stage2_raw = rec.get("stage2_output", "")
                        stage1_model = rec.get("stage1_model", "")
                        stage2_model = rec.get("stage2_model", "")
                        ts = rec.get("ts", "")
                        
                        # 解析 Stage1
                        stage1_obj = _parse_json(stage1_raw)
                        
                        # 解析 Stage2（关键：若不完整则补齐）
                        stage2_obj = None
                        if stage2_raw:
                            if is_stage2_incomplete(stage2_raw, stage1_raw):
                                # Stage2 不完整，用 Stage1 补齐
                                stage2_merged = merge_stage2_with_stage1(stage2_raw, stage1_raw)
                                stage2_obj = _parse_json(stage2_merged)
                            else:
                                # Stage2 完整，直接解析
                                stage2_obj = _parse_json(stage2_raw)
                        
                        samples.append({
                            "content": content,
                            "title": title,
                            "source_url": source_url,
                            "llm_raw": stage1_raw,
                            "llm_raw_obj": stage1_obj,
                            "stage2_output": stage2_raw,
                            "stage2_obj": stage2_obj,  # 【关键】已补齐的 Stage2 对象
                            "stage1_model": stage1_model,
                            "stage2_model": stage2_model,
                            "ts": ts,
                        })
                    else:
                        # 旧版 llm_logs 格式
                        content = rec.get("content", "") or rec.get("user_content", "")
                        title = rec.get("title", "")
                        source_url = rec.get("source_url", "")
                        llm_raw = rec.get("llm_raw", "") or rec.get("llm_response", "")
                        ts = rec.get("ts", "")
                        
                        llm_raw_obj = _parse_json(llm_raw)
                        
                        samples.append({
                            "content": content,
                            "title": title,
                            "source_url": source_url,
                            # 旧版日志只有单阶段输出：为避免“看不到豆包答案”的误解，
                            # 这里把 llm_logs 的输出映射到 Stage2 展示。
                            "stage2_output": llm_raw,
                            "stage2_obj": llm_raw_obj,
                            "ts": ts,
                        })
                except Exception as e:
                    logger.warning("解析日志行失败: %s", e)
                    continue
    except Exception as e:
        logger.error("读取日志文件失败: %s", e)
        return {"error": str(e), "samples": [], "total": 0, "showing": 0}
    return {"samples": samples, "total": total, "showing": len(samples)}


# ===========================================================
# FAQ 上传：解析问题+答案文件，保存题库 + 微调样本
# ===========================================================

def _parse_faq_csv(content: str) -> List[Dict[str, str]]:
    """解析 CSV：支持 question/answer、question_text/answer_text、问题/答案 等列名"""
    rows = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        q = (row.get("question") or row.get("question_text") or row.get("问题") or "").strip()
        a = (row.get("answer") or row.get("answer_text") or row.get("答案") or "").strip()
        if q:
            rows.append({"question": q, "answer": a})
    return rows


def _parse_faq_json(content: str) -> List[Dict[str, str]]:
    """解析 JSON：支持 [{"question":"...","answer":"..."}] 或 [{"question_text":"...","answer_text":"..."}]"""
    data = json.loads(content)
    if not isinstance(data, list):
        data = [data]
    rows = []
    for item in data:
        if isinstance(item, dict):
            q = (item.get("question") or item.get("question_text") or "").strip()
            a = (item.get("answer") or item.get("answer_text") or "").strip()
            if q:
                rows.append({"question": q, "answer": a})
    return rows


def _parse_faq_jsonl(content: str) -> List[Dict[str, str]]:
    """解析 JSONL：每行一个 JSON 对象"""
    rows = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                q = (item.get("question") or item.get("question_text") or "").strip()
                a = (item.get("answer") or item.get("answer_text") or "").strip()
                if q:
                    rows.append({"question": q, "answer": a})
        except json.JSONDecodeError:
            continue
    return rows


def _parse_faq_txt(content: str) -> List[Dict[str, str]]:
    """解析 TXT：Q: 问题 / A: 答案 或 问题\n答案（空行分隔）格式"""
    rows = []
    for block in re.split(r"\n\s*\n+", content):
        block = block.strip()
        if not block:
            continue
        # 格式1: Q: xxx  A: xxx 或 Q: xxx\nA: xxx
        m = re.search(r"Q[：:]\s*(.+?)(?:\s*A[：:]\s*(.+))?$", block, re.DOTALL)
        if m:
            q, a = m.group(1).strip(), (m.group(2) or "").strip()
            if q:
                rows.append({"question": q, "answer": a})
            continue
        # 格式2: 第一行问题，其余为答案
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if lines:
            rows.append({"question": lines[0], "answer": "\n".join(lines[1:]) if len(lines) > 1 else ""})
    return rows


def parse_faq_file(content: str, filename: str = "") -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    根据文件内容解析 FAQ（问题+答案）列表。
    支持：.csv, .json, .jsonl, .txt
    返回 (rows, error)，error 非空表示解析失败。
    """
    content = content.strip()
    if not content:
        return [], "文件内容为空"

    ext = (Path(filename).suffix or "").lower() if filename else ""
    if ext == ".csv" or (not ext and "," in (content.split("\n")[0] or "") and ("question" in content.lower() or "问题" in content)):
        try:
            rows = _parse_faq_csv(content)
            return rows, None
        except Exception as e:
            return [], f"CSV 解析失败: {e}"

    if ext == ".jsonl":
        try:
            rows = _parse_faq_jsonl(content)
            return rows, None
        except Exception as e:
            return [], f"JSONL 解析失败: {e}"

    if ext == ".json":
        try:
            rows = _parse_faq_json(content)
            return rows, None
        except json.JSONDecodeError as e:
            return [], f"JSON 解析失败: {e}"

    if ext == ".txt" or not ext:
        try:
            rows = _parse_faq_txt(content)
            if rows:
                return rows, None
        except Exception as e:
            return [], f"TXT 解析失败: {e}"
        # 兜底尝试 JSON
        try:
            rows = _parse_faq_json(content)
            if rows:
                return rows, None
        except Exception:
            pass
        return [], "无法识别文件格式，请使用 CSV/JSON/JSONL/TXT"

    return [], f"不支持的文件格式: {ext}"


def import_faq(
    content: str,
    filename: str = "",
    save_to_bank: bool = True,
    save_to_finetune: bool = True,
    source_platform: str = "faq_upload",
) -> Dict[str, Any]:
    """
    解析 FAQ 文件并：
    1. save_to_bank=True：保存到 questions 题库（SQLite + 可选 Neo4j）
    2. save_to_finetune=True：写入 finetune_samples，status=labeled，用于模型微调

    返回 {"parsed": N, "bank_saved": N, "finetune_saved": N, "errors": [...]}
    """
    from backend.services.storage.sqlite_service import sqlite_service
    from backend.tools.knowledge_manager_tools import generate_embedding

    rows, err = parse_faq_file(content, filename)
    if err:
        return {"parsed": 0, "bank_saved": 0, "finetune_saved": 0, "errors": [err]}

    bank_saved = 0
    finetune_saved = 0
    errors = []
    now = now_beijing_str()

    try:
        neo4j = __import__("backend.services.storage.neo4j_service", fromlist=["neo4j_service"]).neo4j_service
    except Exception:
        neo4j = None

    for i, item in enumerate(rows):
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        if not q:
            continue

        q_id = f"FAQ-{uuid.uuid4().hex[:12]}"

        # 1. 保存到题库
        if save_to_bank:
            try:
                tags = ["FAQ"]
                sqlite_service.upsert_question(
                    question_text=q,
                    answer_text=a,
                    difficulty="medium",
                    question_type="技术题",
                    source_platform=source_platform,
                    source_url="",
                    company="",
                    position="",
                    topic_tags=tags,
                    q_id=q_id,
                )
                bank_saved += 1

                # 可选：写入 Neo4j（用于语义检索）
                if neo4j and neo4j.available:
                    emb = generate_embedding(q)
                    if emb:
                        neo4j.add_question(
                            q_id=q_id,
                            text=q,
                            answer=a,
                            tags=tags,
                            embedding=emb,
                            metadata={"source": "faq_upload"},
                        )
            except Exception as e:
                errors.append(f"第{i+1}条入库失败: {e}")

        # 2. 写入微调样本（用于模型 SFT）
        if save_to_finetune:
            try:
                final_output = json.dumps(
                    [{"question_text": q, "answer_text": a}],
                    ensure_ascii=False,
                )
                with _get_db_conn() as conn:
                    conn.execute(
                        """INSERT INTO finetune_samples
                           (content, title, final_output, is_modified, status, source, created_at, labeled_at, modified_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (q, f"FAQ#{i+1}", final_output, 0, "labeled", "faq_upload", now, now, now),
                    )
                    conn.commit()
                finetune_saved += 1
            except Exception as e:
                errors.append(f"第{i+1}条微调样本写入失败: {e}")

    logger.info("FAQ 导入完成: parsed=%d bank_saved=%d finetune_saved=%d", len(rows), bank_saved, finetune_saved)
    return {
        "parsed": len(rows),
        "bank_saved": bank_saved,
        "finetune_saved": finetune_saved,
        "errors": errors[:10],
    }


# ===========================================================
# 一键微调：配置保存 + 训练脚本生成（LoRA/QLoRA）
# ===========================================================

DEFAULT_RUN_CONFIG = {
    "base_model": "qwen3:4b",
    # 8GB 显存笔记本默认用 QLoRA（4bit），全精度 LoRA 易 OOM
    "method": "qlora",
    "output_name": "qwen3-4b-miner-lora",
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "lora_target_modules": "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
    "learning_rate": 2e-4,
    "num_epochs": 3,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 8,
    "max_seq_length": 4096,
    "warmup_ratio": 0.1,
    "weight_decay": 0.01,
    "use_rslora": True,
    "precision": "bf16",
}


def _normalize_max_seq_length(v) -> int:
    """与前端一致：256–8192（长输出 SFT 可设 4096/8192，8GB 建议先试 4096）。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = int(DEFAULT_RUN_CONFIG["max_seq_length"])
    return max(256, min(8192, n))


def get_run_config() -> Dict:
    """获取当前微调运行配置"""
    if _RUN_CONFIG_PATH.exists():
        try:
            data = json.loads(_RUN_CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = {**DEFAULT_RUN_CONFIG, **data}
            cfg["max_seq_length"] = _normalize_max_seq_length(cfg.get("max_seq_length"))
            return cfg
        except Exception as e:
            logger.warning("读取微调配置失败: %s", e)
    return dict(DEFAULT_RUN_CONFIG)


def save_run_config(config: Dict) -> Dict:
    """保存微调运行配置"""
    _FINETUNE_DIR.mkdir(parents=True, exist_ok=True)
    allowed = set(DEFAULT_RUN_CONFIG.keys()) | {"lora_target_modules"}
    merged = {**DEFAULT_RUN_CONFIG, **{k: v for k, v in config.items() if k in allowed}}
    merged.pop("bf16", None)  # 兼容旧配置，不再保存 bf16
    merged["max_seq_length"] = _normalize_max_seq_length(merged.get("max_seq_length"))
    _RUN_CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "path": str(_RUN_CONFIG_PATH)}


def _parse_lr(v) -> float:
    """解析学习率，支持 2e-4 或 0.0002"""
    if v is None:
        return 2e-4
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return 2e-4


def _finetune_train_log_path(run_id: int) -> Path:
    d = _FINETUNE_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"train_run_{run_id}.log"


def _run_finetune_training_worker(run_id: int, script_path: Path) -> None:
    """后台线程：在「微调」目录下用当前 Python 解释器执行 train_lora.py，日志写入文件。"""
    from backend.services.storage.sqlite_service import sqlite_service

    cwd = _FINETUNE_DIR.resolve()
    log_path = _finetune_train_log_path(run_id)
    log_path_resolved = log_path.resolve()
    exe = sys.executable
    script_name = script_path.name
    try:
        with open(log_path, "ab") as logf:
            header = f"\n# ---- run_id={run_id} {now_beijing_str()} ----\n"
            logf.write(header.encode("utf-8", errors="replace"))
            logf.flush()
            child_env = os.environ.copy()
            # Windows + Unsloth：减少 torch.compile / inductor 与 triton-windows 的冲突
            child_env.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
            child_env.setdefault("TOKENIZERS_PARALLELISM", "false")
            # 国内访问 huggingface.co 易超时：默认走镜像（可用环境变量 HF_ENDPOINT 覆盖）
            child_env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            child_env.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
            child_env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                [exe, "-u", script_name],
                cwd=str(cwd),
                stdout=logf,
                stderr=subprocess.STDOUT,
                env=child_env,
            )
            logger.info(
                "微调训练子进程已启动 run_id=%s 日志文件=%s 路径=%s",
                run_id,
                log_path_resolved.name,
                log_path_resolved,
            )
            code = proc.wait()
    except Exception:
        logger.exception("微调训练进程异常 run_id=%s", run_id)
        ended = now_beijing().isoformat(timespec="seconds")
        sqlite_service.update_finetune_run_status(run_id, "failed", ended_at=ended)
        return
    ended = now_beijing().isoformat(timespec="seconds")
    if code == 0:
        sqlite_service.update_finetune_run_status(run_id, "completed", ended_at=ended)
        logger.info("微调训练完成 run_id=%s", run_id)
    else:
        sqlite_service.update_finetune_run_status(run_id, "failed", ended_at=ended)
        logger.warning(
            "微调训练非正常退出 run_id=%s code=%s 日志文件=%s 路径=%s",
            run_id,
            code,
            log_path_resolved.name,
            log_path_resolved,
        )


def _try_spawn_finetune_training(run_id: int, script_path: Path) -> Dict:
    """在进程内启动后台训练；同一时刻仅允许一条 running。"""
    from backend.services.storage.sqlite_service import sqlite_service

    with _TRAIN_SPAWN_LOCK:
        if sqlite_service.finetune_has_running_run():
            return {
                "training_started": False,
                "training_error": "已有任务正在训练中，请等待结束后再启动",
                "train_log_path": None,
            }
        started = now_beijing().isoformat(timespec="seconds")
        if not sqlite_service.update_finetune_run_status(run_id, "running", started_at=started):
            return {"training_started": False, "training_error": "训练记录更新失败", "train_log_path": None}
    t = threading.Thread(
        target=_run_finetune_training_worker,
        args=(run_id, script_path),
        name=f"finetune_train_{run_id}",
        daemon=True,
    )
    t.start()
    return {
        "training_started": True,
        "training_error": None,
        "train_log_path": str(_finetune_train_log_path(run_id)),
    }


def generate_training_script(
    config: Dict = None, sample_ids: List[int] = None, run_training: bool = True
) -> Dict:
    """
    根据配置生成 Unsloth LoRA/QLoRA 训练脚本。
    数据格式：将 labeled_data.jsonl (prompt/completion) 转为 instruction 格式。
    sample_ids: 可选，指定则先导出这些样本到 labeled_data.jsonl，再生成脚本；否则使用已有 labeled_data.jsonl。
    run_training: True 时在后台用当前解释器启动 train_lora.py（需已安装 unsloth 等，且与后端 Python 环境一致）。
    """
    cfg = {**DEFAULT_RUN_CONFIG, **(config or {})}
    cfg["max_seq_length"] = _normalize_max_seq_length(cfg.get("max_seq_length"))
    cfg["learning_rate"] = _parse_lr(cfg.get("learning_rate"))
    _FINETUNE_DIR.mkdir(parents=True, exist_ok=True)

    # 若指定了 sample_ids，先导出选中样本到 labeled_data.jsonl
    if sample_ids:
        export_labeled(sample_ids=sample_ids)

    # 1. 转换数据格式：prompt/completion -> instruction/input/output (Alpaca)
    converted_path = _FINETUNE_DIR / "training_data_alpaca.jsonl"
    if not _LABELED_PATH.exists():
        return {"status": "error", "message": "请先导出标注数据（微调/labeled_data.jsonl）"}
    count = 0
    with open(_LABELED_PATH, "r", encoding="utf-8") as fin:
        with open(converted_path, "w", encoding="utf-8", newline="\n") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    prompt = rec.get("prompt", "")
                    completion = rec.get("completion", "")
                    if not prompt or not completion:
                        continue
                    alpaca = {
                        "instruction": "从面经原文中提取面试题，输出 JSON 数组，每项含 question_text、answer_text、difficulty、question_type、topic_tags 等字段。",
                        "input": prompt,
                        "output": completion,
                    }
                    fout.write(json.dumps(alpaca, ensure_ascii=False) + "\n")
                    count += 1
                except Exception:
                    continue
    if count == 0:
        return {"status": "error", "message": "labeled_data.jsonl 无有效样本"}

    # 2. 生成训练脚本
    method = (cfg.get("method") or "lora").lower()
    load_in_4bit = method == "qlora"
    target_modules = [x.strip() for x in (cfg.get("lora_target_modules") or "").split(",") if x.strip()]
    if not target_modules:
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    output_name = cfg.get("output_name") or "qwen3-4b-miner-lora"
    output_dir = _FINETUNE_DIR / "lora_output" / output_name

    base_model = (cfg.get("base_model") or "qwen3:4b").strip()
    if base_model in ("qwen3:4b", "qwen3:4B"):
        hf_model = "unsloth/Qwen3-4B"
    else:
        hf_model = base_model

    # 训练精度（写入 train_lora.py 的常量，不可在 f-string 里写 _prec=cfg... 否则会当作外层求值）
    _prec_raw = cfg.get("precision")
    if isinstance(_prec_raw, str) and _prec_raw.strip():
        prec = _prec_raw.strip().lower()
    elif isinstance(cfg.get("bf16"), bool):
        prec = "bf16" if cfg.get("bf16") else "fp16"
    else:
        prec = "bf16"
    bf16_training = prec in ("bf16", "4bit")
    fp16_training = prec == "fp16"

    script_content = f'''# -*- coding: utf-8 -*-
# 一键微调脚本（Unsloth LoRA/QLoRA）
# 生成时间: {now_beijing_str()}
# 使用: pip install unsloth datasets trl transformers && python train_lora.py
# 建议用无缓冲运行: python -u train_lora.py（后端子进程已带 -u）

import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# 须在 import unsloth 之前：降低 Windows 上 inductor/triton 相关问题
os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 国内网络：拉取基座模型（默认可用环境变量 HF_ENDPOINT 覆盖为官方源）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

import json
import time
from datetime import datetime

from unsloth import FastLanguageModel
from datasets import load_dataset
import torch


def tlog(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{{ts}}] {{msg}}", flush=True)

# 路径相对本脚本目录，避免 Windows 下反斜杠转义（\\\\t 等）导致路径错误
_SCRIPT_DIR = Path(__file__).resolve().parent
_OUTPUT_SUBDIR = {json.dumps(output_name)}
OUTPUT_DIR = str(_SCRIPT_DIR / "lora_output" / _OUTPUT_SUBDIR)
DATA_PATH = str(_SCRIPT_DIR / "training_data_alpaca.jsonl")

# ========== 配置（来自微调界面） ==========
# 基座模型：{base_model} -> {hf_model}
BASE_MODEL = "{hf_model}"
LOAD_IN_4BIT = {str(load_in_4bit)}
MAX_SEQ_LENGTH = {int(cfg["max_seq_length"])}
LORA_R = {int(cfg.get("lora_r", 16))}
LORA_ALPHA = {int(cfg.get("lora_alpha", 32))}
LORA_DROPOUT = {float(cfg.get("lora_dropout", 0.05))}
LEARNING_RATE = {float(cfg.get("learning_rate", 2e-4))}
NUM_EPOCHS = {int(cfg.get("num_epochs", 3))}
BATCH_SIZE = {int(cfg.get("per_device_train_batch_size", 2))}
GRAD_ACCUM = {int(cfg.get("gradient_accumulation_steps", 8))}
WARMUP_RATIO = {float(cfg.get("warmup_ratio", 0.1))}
WEIGHT_DECAY = {float(cfg.get("weight_decay", 0.01))}
USE_RSLORA = {str(cfg.get("use_rslora", True))}
# 训练精度: {prec}（bf16/fp16；QLoRA 时 4bit 与 bf16 训练可并存）
BF16 = {str(bf16_training)}
FP16 = {str(fp16_training)}
# Windows 上 datasets 多进程易出问题，改为 0（主进程）
_DATASET_NUM_PROC = 0 if sys.platform == "win32" else 2
# 调试时可设 FINETUNE_MAX_STEPS=10 只跑几步验证链路（不设则按 num_epochs 完整训练）
_fin_ms = os.environ.get("FINETUNE_MAX_STEPS", "").strip()
TRAIN_MAX_STEPS = int(_fin_ms) if _fin_ms.isdigit() else -1
_ls = os.environ.get("FINETUNE_LOGGING_STEPS", "").strip()
LOGGING_STEPS = max(1, int(_ls)) if _ls.isdigit() else 1
_rep = os.environ.get("FINETUNE_REPORT_TO", "").strip().lower()
if _rep in ("tensorboard", "tb"):
    REPORT_TO = "tensorboard"
elif _rep == "wandb":
    REPORT_TO = "wandb"
else:
    REPORT_TO = "none"

def main():
    if not Path(DATA_PATH).is_file():
        raise SystemExit(f"数据文件不存在: {{DATA_PATH}}")
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA：请安装 GPU 版 PyTorch（如 2.5.1+cu124）后再训练。")
    tlog("加载模型...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=LOAD_IN_4BIT,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules={target_modules},
        use_rslora=USE_RSLORA,
    )
    tlog("加载数据...")
    dataset = load_dataset("json", data_files=DATA_PATH, split="train")
    def format_instruction(example):
        text = f"""<|im_start|>user
{{example["instruction"]}}

{{example["input"]}}<|im_end|>
<|im_start|>assistant
{{example["output"]}}<|im_end|>"""
        return {{"text": text}}
    dataset = dataset.map(
        format_instruction,
        remove_columns=dataset.column_names,
        num_proc=_DATASET_NUM_PROC,
    )
    from trl import SFTTrainer
    from transformers import TrainingArguments, TrainerCallback

    class _StepHeartbeatCallback(TrainerCallback):
        def __init__(self):
            self._seen = False

        def on_step_begin(self, args, state, control, **kwargs):
            if not self._seen:
                self._seen = True
                tlog("已进入训练迭代：第 1 个 micro-batch 开始（长序列/首次 GPU 计算可能较慢，请等待 loss 日志）")

        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs:
                return
            parts = []
            for k, v in logs.items():
                if isinstance(v, float):
                    parts.append(f"{{k}}={{v:.6f}}")
                else:
                    parts.append(f"{{k}}={{v}}")
            tlog(f"step {{state.global_step}} | " + " | ".join(parts))

    class _EpochTimingCallback(TrainerCallback):
        def __init__(self, out_path: Path):
            self.out_path = out_path
            self._train_t0 = None
            self._epoch_t0 = None
            self._epoch_num = None
            self.per_epoch = []

        def on_train_begin(self, args, state, control, **kwargs):
            self._train_t0 = time.perf_counter()

        def on_epoch_begin(self, args, state, control, **kwargs):
            self._epoch_t0 = time.perf_counter()
            try:
                self._epoch_num = int(state.epoch) + 1
            except (TypeError, ValueError):
                self._epoch_num = 1

        def on_epoch_end(self, args, state, control, **kwargs):
            if self._epoch_t0 is None:
                return
            dur = time.perf_counter() - self._epoch_t0
            en = self._epoch_num or 1
            rec = dict(
                epoch=en,
                duration_sec=round(dur, 3),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            self.per_epoch.append(rec)
            tlog(f"Epoch {{en}} 完成，本 epoch 用时 {{dur:.1f}}s（约 {{dur / 60:.2f}} min）")
            self._write_json(total_sec=None)

        def on_train_end(self, args, state, control, **kwargs):
            total = None
            if self._train_t0 is not None:
                total = round(time.perf_counter() - self._train_t0, 3)
            self._write_json(total_sec=total)
            if total is not None:
                tlog(
                    f"训练总用时 {{total}}s（约 {{total / 60:.2f}} min），各 epoch 耗时已写入 {{self.out_path}}"
                )

        def _write_json(self, total_sec):
            payload = dict(
                output_dir=str(self.out_path.parent.resolve()),
                per_epoch=self.per_epoch,
                total_training_sec=total_sec,
                updated_at=datetime.now().isoformat(timespec="seconds"),
            )
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            self.out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    epoch_json = Path(OUTPUT_DIR) / "epoch_times.json"
    n_gpu = max(1, torch.cuda.device_count())
    eff_batch = BATCH_SIZE * GRAD_ACCUM * n_gpu
    tlog(
        f"有效 batch size = 每卡{{BATCH_SIZE}} × 梯度累积{{GRAD_ACCUM}} × GPU{{n_gpu}} = {{eff_batch}}；"
        "慢多为序列长与反传开销，非单纯「batch 大」。OOM 时优先减 BATCH_SIZE 或 MAX_SEQ_LENGTH。"
    )
    tlog(f"开始训练… logging_steps={{LOGGING_STEPS}}，max_steps={{TRAIN_MAX_STEPS}}，样本数={{len(dataset)}}，report_to={{REPORT_TO}}")
    if REPORT_TO == "tensorboard":
        _tb = Path(OUTPUT_DIR) / "tensorboard"
        tlog(
            "TensorBoard 目录: "
            + str(_tb.resolve())
            + '  执行: tensorboard --logdir "'
            + str(_tb)
            + '"'
        )
    elif REPORT_TO == "wandb":
        tlog("已启用 W&B，需本机已 wandb login；浏览器可查看曲线。")
    tlog("首个 optimizer step 前向+反传可能需数分钟，请等待下方带时间的 loss 行。")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=_DATASET_NUM_PROC,
        packing=False,
        callbacks=[
            _StepHeartbeatCallback(),
            _EpochTimingCallback(epoch_json),
        ],
        args=TrainingArguments(
            output_dir=OUTPUT_DIR,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            learning_rate=LEARNING_RATE,
            num_train_epochs=NUM_EPOCHS,
            warmup_ratio=WARMUP_RATIO,
            weight_decay=WEIGHT_DECAY,
            bf16=BF16,
            fp16=FP16,
            logging_steps=LOGGING_STEPS,
            save_strategy="epoch",
            report_to=REPORT_TO,
            logging_dir=str(Path(OUTPUT_DIR) / "tensorboard")
            if REPORT_TO == "tensorboard"
            else None,
            dataloader_pin_memory=False,
            max_steps=TRAIN_MAX_STEPS,
            disable_tqdm=False,
        ),
    )
    trainer.train()
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    tlog(f"训练完成，模型已保存到 {{OUTPUT_DIR}}")

if __name__ == "__main__":
    main()
'''

    script_path = _FINETUNE_DIR / "train_lora.py"
    script_path.write_text(script_content, encoding="utf-8")
    logger.info("训练脚本已生成: %s", script_path)

    # 保存训练记录到 SQLite
    try:
        from backend.services.storage.sqlite_service import sqlite_service
        run_id = sqlite_service.add_finetune_run(
            config_json=json.dumps(cfg, ensure_ascii=False),
            output_dir=str(output_dir),
            script_path=str(script_path),
            data_path=str(converted_path),
            sample_count=count,
            status="generated",
        )
    except Exception as e:
        logger.warning("保存训练记录失败: %s", e)
        run_id = None

    out = {
        "status": "ok",
        "run_id": run_id,
        "script_path": str(script_path),
        "data_path": str(converted_path),
        "output_dir": str(output_dir),
        "sample_count": count,
        "training_started": False,
        "train_log_path": None,
        "training_error": None,
        "message": f"已生成训练脚本，共 {count} 条样本。",
    }
    if run_id is not None and run_training:
        sp = _try_spawn_finetune_training(run_id, script_path)
        out["training_started"] = sp["training_started"]
        out["train_log_path"] = sp.get("train_log_path")
        out["training_error"] = sp.get("training_error")
        if sp["training_started"]:
            out["message"] = (
                f"已生成脚本并于服务器后台启动训练（{count} 条）。日志：{sp.get('train_log_path')}"
            )
        elif sp.get("training_error"):
            out["message"] = (
                f"已生成训练脚本（{count} 条），但未启动后台训练：{sp['training_error']}"
            )
    elif run_id is not None and not run_training:
        out["message"] = (
            f"已生成训练脚本，共 {count} 条。未自动训练；可在本机「微调」目录下使用与后端相同的 Python 执行 {script_path.name}。"
        )
    return out
