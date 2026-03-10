"""
微调数据服务
职责：
  - 从微调日志（微调/llm_logs/）导入样本到 SQLite finetune_samples 表
  - 调用远程大模型辅助生成标注结果
  - 保存人工确认的最终标注数据
  - 导出 labeled_data.jsonl 用于微调训练
"""
from backend.utils.time_utils import now_beijing, now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from backend.config.config import settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FINETUNE_DIR = _PROJECT_ROOT / "微调"
_LABELED_PATH = _FINETUNE_DIR / "labeled_data.jsonl"

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


# ===========================================================
# 导入：从 llm_logs 文件读取并写入 SQLite
# ===========================================================

def import_from_log_file(log_path: str, skip_existing: bool = True) -> Dict[str, int]:
    """
    从指定 JSONL 日志文件导入样本到 finetune_samples 表。
    返回 {"imported": N, "skipped": N}
    """
    p = Path(log_path)
    if not p.exists():
        return {"imported": 0, "skipped": 0, "failed": 0, "error": "文件不存在"}

    imported = skipped = failed = 0
    failed_samples = []  # 收集失败的样本用于最后统一输出
    
    with _get_db_conn() as conn:
        for line_num, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                content = (rec.get("user_content", "") or rec.get("content", "")).strip()
                title = rec.get("title", "")
                source_url = rec.get("source_url", "")
                llm_raw = rec.get("llm_response", "") or rec.get("llm_raw", "")
                ts = rec.get("ts", now_beijing_str())
                if not content:
                    continue
                if skip_existing:
                    exists = conn.execute(
                        "SELECT 1 FROM finetune_samples WHERE content=? AND created_at=?",
                        (content, ts)
                    ).fetchone()
                    if exists:
                        skipped += 1
                        continue
                conn.execute(
                    "INSERT INTO finetune_samples (content, title, source_url, llm_raw, status, created_at) VALUES (?,?,?,?,?,?)",
                    (content, title, source_url, llm_raw, "pending", ts)
                )
                imported += 1
            except Exception as e:
                failed += 1
                failed_samples.append({
                    "line": line_num,
                    "error": str(e),
                    "preview": line[:80]
                })
        conn.commit()
    
    # 统一输出结果
    logger.info("导入完成: imported=%d skipped=%d failed=%d from %s", imported, skipped, failed, p.name)
    
    # 只有失败时才输出详细信息
    if failed > 0:
        logger.warning("导入失败详情 (%d条):", failed)
        for sample in failed_samples[:5]:  # 最多显示前5条
            logger.warning("  行%d: %s | %s", sample["line"], sample["error"], sample["preview"])
        if failed > 5:
            logger.warning("  ... 还有 %d 条失败记录未显示", failed - 5)
    
    return {"imported": imported, "skipped": skipped, "failed": failed}


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
    log_root = _FINETUNE_DIR / "llm_logs"
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
    """列出 微调/llm_logs/ 下所有 JSONL 文件，返回文件信息列表"""
    log_root = _FINETUNE_DIR / "llm_logs"
    result = []
    if not log_root.exists():
        return result
    for f in sorted(log_root.rglob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        rel = f.relative_to(_FINETUNE_DIR)
        parts = rel.parts  # (llm_logs, model_name, source_date.jsonl)
        model = parts[1] if len(parts) > 2 else "unknown"
        line_count = sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
        result.append({
            "path": str(f),
            "rel_path": str(rel),
            "model": model,
            "filename": f.name,
            "line_count": line_count,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return result


# ===========================================================
# 样本列表 & 详情
# ===========================================================

def list_samples(status: str = None, page: int = 1, page_size: int = 20, order: str = "asc") -> Dict:
    """分页查询 finetune_samples，可按 status 过滤，支持排序"""
    offset = (page - 1) * page_size
    where = "WHERE status=?" if status else ""
    params_count = (status,) if status else ()
    params_list = (status, page_size, offset) if status else (page_size, offset)
    
    # 排序：asc=正序（ID从小到大），desc=倒序（ID从大到小）
    order_by = "ORDER BY id ASC" if order == "asc" else "ORDER BY id DESC"

    with _get_db_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM finetune_samples {where}", params_count
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, content as content_preview,
                       status, is_modified, created_at, labeled_at
                FROM finetune_samples {where}
                {order_by} LIMIT ? OFFSET ?""",
            params_list
        ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


def get_sample(sample_id: int) -> Optional[Dict]:
    """获取单条样本完整内容"""
    with _get_db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM finetune_samples WHERE id=?", (sample_id,)
        ).fetchone()
    return dict(row) if row else None


# ===========================================================
# 辅助大模型生成
# ===========================================================

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

    if not _base_url:
        return {"error": "未配置 FINETUNE_LLM_BASE_URL"}

    # 拼接标题和内容
    full_content = content
    if title:
        full_content = f"【帖子标题】{title}\n\n【面经正文】\n{content}"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=_api_key or "sk-dummy", base_url=_base_url, timeout=120)
        resp = client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": _ASSIST_SYSTEM_PROMPT},
                {"role": "user", "content": f"## 面经原文\n{full_content}\n\n请提取所有面试题并输出 JSON 数组。"},
            ],
            temperature=_temp,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return {"output": raw, "model": _model}
    except Exception as e:
        logger.error("辅助大模型调用失败: %s", e)
        return {"error": str(e)}


# ===========================================================
# 保存标注 & 导出
# ===========================================================

def save_label(sample_id: int, final_output: str, is_modified: bool = False) -> Dict:
    """保存人工确认的最终标注结果"""
    now = now_beijing().isoformat(timespec="seconds")
    with _get_db_conn() as conn:
        conn.execute(
            """UPDATE finetune_samples
               SET final_output=?, is_modified=?, status='labeled', labeled_at=?
               WHERE id=?""",
            (final_output, 1 if is_modified else 0, now, sample_id)
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


def export_labeled(output_path: str = None) -> Dict:
    """
    将所有 labeled 状态的样本导出为 labeled_data.jsonl（prompt/completion 格式）。
    返回导出数量。
    """
    out_p = Path(output_path) if output_path else _LABELED_PATH
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with _get_db_conn() as conn:
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
    with _get_db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM finetune_samples").fetchone()[0]
        labeled = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE status='labeled'").fetchone()[0]
        modified = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE is_modified=1").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM finetune_samples WHERE status='pending'").fetchone()[0]
    return {
        "total": total,
        "pending": pending,
        "labeled": labeled,
        "modified": modified,
        "log_files": len(list_log_files()),
    }


def preview_log_file(log_path: str, limit: int = 10) -> Dict:
    """
    预览日志文件前N条记录
    返回 {"samples": [...], "total": N}
    """
    p = Path(log_path)
    if not p.exists():
        return {"error": "文件不存在", "samples": [], "total": 0}
    
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
                    # 解析 llm_raw 为对象
                    llm_raw_obj = None
                    if rec.get("llm_raw"):
                        try:
                            llm_raw_obj = json.loads(rec["llm_raw"])
                        except:
                            llm_raw_obj = {"error": "无效JSON", "raw": rec["llm_raw"]}
                    
                    samples.append({
                        "content": rec.get("content", ""),
                        "title": rec.get("title", ""),
                        "source_url": rec.get("source_url", ""),
                        "llm_raw": rec.get("llm_raw", ""),
                        "llm_raw_obj": llm_raw_obj,
                        "ts": rec.get("ts", ""),
                    })
                except Exception as e:
                    logger.warning("解析日志行失败: %s", e)
                    continue
    except Exception as e:
        logger.error("读取日志文件失败: %s", e)
        return {"error": str(e), "samples": [], "total": 0}
    
    return {"samples": samples, "total": total, "showing": len(samples)}
