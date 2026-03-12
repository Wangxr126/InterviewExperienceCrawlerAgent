"""
面试复习系统总编排器 (System Orchestrator) v3.0

设计原则：确定性流程用代码，判断性行为用 LLM。
─────────────────────────────────────────────────────────────────
确定性流程（Orchestrator 直接编码）：
  • 内容采集管道：爬取 → 清洗 → 校验 → OCR? → 元信息  (HunterPipeline)
  • 答题后钩子  ：SM-2更新 → 写情景记忆 → 判断推荐     (submit_answer)
  • Session 生命周期：开始 / 结束 / 记忆整合

LLM 负责（通过 Agent）：
  • 自然对话（出题、解释、推荐策略）         → InterviewerAgent
  • 答案结构化评估（打分 + 遗漏点）          → _evaluate_answer_structured()
  • 知识结构化（帖子 → 题目 JSON）           → KnowledgeManager
"""

from backend.utils.time_utils import now_beijing, now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import asyncio
import json
import logging
import re
import uuid
import requests
import time
from collections import defaultdict
from functools import partial
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.services.knowledge.knowledge_manager import knowledge_manager
from backend.agents.interviewer_agent import InterviewerAgent
from backend.config.config import settings
from backend.services.storage.sqlite_service import sqlite_service
from backend.tools.interviewer_tools import KnowledgeRecommender

logger = logging.getLogger(__name__)


def _save_eval_failure(input_preview: str, raw_output: str, error: str) -> None:
    """答题评估 LLM 解析失败时写入 llm_failures/answer_eval.jsonl"""
    try:
        from backend.services.logging.llm_parse_failures import save_failure
        save_failure(
            source="answer_eval",
            input_preview=input_preview,
            raw_output=raw_output,
            error=error,
            metadata={},
        )
    except Exception as e:
        logger.debug(f"保存评估失败记录异常: {e}")


# 全局懒加载的 KnowledgeRecommender（无状态工具，可共享）
_knowledge_recommender = KnowledgeRecommender()


# ===========================================================
# 记忆系统辅助
# ===========================================================

def _get_memory_tool(user_id: str):
    """获取或创建 hello-agents MemoryTool 实例（按 user_id 隔离）"""
    try:
        from hello_agents.tools import MemoryTool
        return MemoryTool(user_id=user_id)
    except ImportError:
        logger.debug("hello-agents MemoryTool 未安装（框架已移除），记忆功能降级")
        return None
    except Exception as e:
        logger.error(f"MemoryTool 初始化失败: {e}")
        return None


# ===========================================================
# 结构化评估（直接 LLM 调用，不走 ReAct 循环）
# ===========================================================

def _evaluate_answer_structured(question_text: str,
                                 user_answer: str) -> Dict[str, Any]:
    """
    对用户答案做结构化评估，返回 JSON。
    直接调用 LLM（JSON mode），不经过 Agent ReAct 循环。
    这是代码层面确定性调用的"最小 LLM 单元"。

    Returns:
        {
          "score": int,            # 0-5
          "feedback": str,         # 综合评价
          "missed_points": [str],  # 遗漏/记错的具体知识点
          "strong_points": [str],  # 答对的要点
          "tags": [str]            # 涉及的技术标签
        }
    """
    system = (
        "你是一位技术面试评委。用户将提交面试题目和他们的回答。"
        "你需要评估回答质量，严格按以下 JSON 格式返回，不得添加任何额外字段或注释：\n"
        '{"score":3,"feedback":"总体评价","missed_points":["具体遗漏点1"],'
        '"strong_points":["答对的点"],"tags":["Redis","持久化"]}'
        "\n评分标准：0=完全不会，1=基本不会，2=大部分不会，3=勉强会有遗漏，4=基本掌握，5=完全掌握有延伸"
        "\nfeedback 要求：分条列点，用 1. 2. 3. 或 一、二、三、 格式，每条单独一行，便于用户阅读"
    )
    prompt = (
        f"【面试题目】\n{question_text}\n\n"
        f"【用户回答】\n{user_answer}"
    )

    default = {
        "score": 3,
        "feedback": "（评估服务暂时不可用，已记录原始答案）",
        "missed_points": [],
        "strong_points": [],
        "tags": []
    }

    try:
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json"
        }
        _model = settings.interviewer_model or settings.llm_model_id
        payload = {
            "model": _model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        # Ollama 等 OpenAI 兼容 API：base_url 已含 /v1，需拼接 /chat/completions
        _base = (settings.llm_base_url or "").rstrip("/")
        _url = f"{_base}/chat/completions" if "/chat/completions" not in _base else _base
        resp = requests.post(_url, headers=headers, json=payload, timeout=settings.llm_timeout or 60)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"_evaluate_answer_structured JSON 解析失败: {e}")
                _save_eval_failure(prompt, content, error=str(e))
                return default
            # 确保 score 在合法范围
            result["score"] = max(0, min(5, int(result.get("score", 3))))
            return result
        else:
            logger.warning(f"评估 LLM 返回 {resp.status_code}")
            _save_eval_failure(prompt, resp.text[:2000] if resp.text else "", error=f"HTTP {resp.status_code}")
            return default
    except Exception as e:
        logger.error(f"_evaluate_answer_structured 异常: {e}")
        _save_eval_failure(prompt, "", error=str(e))
        return default


def _generate_explanation(question_text: str,
                           evaluation: Dict,
                           recommendation_text: Optional[str]) -> str:
    """
    根据评估结果生成自然语言解释（对话式，面向用户）。
    单独的 LLM 调用，专注"解释"这一件事。
    """
    score = evaluation.get("score", 3)
    missed = evaluation.get("missed_points", [])
    strong = evaluation.get("strong_points", [])

    parts = [
        f"题目：{question_text[:200]}",
        f"得分：{score}/5",
        f"答对的点：{', '.join(strong) if strong else '无'}",
        f"遗漏的点：{', '.join(missed) if missed else '无'}",
        f"综合评价：{evaluation.get('feedback', '')}",
    ]
    if recommendation_text:
        parts.append(f"\n【知识推荐】\n{recommendation_text[:500]}")

    prompt = "\n".join(parts) + (
        "\n\n请基于以上评估结果，用亲切、鼓励的语气给出解释和建议。"
        "若有遗漏点请详细讲解正确内容。若有学习资源推荐请简明展示。中文回复，300字以内。"
    )

    try:
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json"
        }
        _model = settings.interviewer_model or settings.llm_model_id
        payload = {
            "model": _model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        _base = (settings.llm_base_url or "").rstrip("/")
        _url = f"{_base}/chat/completions" if "/chat/completions" not in _base else _base
        resp = requests.post(_url, headers=headers, json=payload, timeout=settings.llm_timeout or 60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"_generate_explanation 异常: {e}")

    # 降级：直接拼接
    lines = [f"✅ 你的得分：{score}/5\n"]
    if strong:
        lines.append("**答对的要点：** " + "、".join(strong))
    if missed:
        lines.append("**需要补充的点：** " + "、".join(missed))
    return "\n".join(lines)


# ===========================================================
# 主编排器
# ===========================================================

class InterviewSystemOrchestrator:
    """
    面试系统编排器 v3.0

    职责边界：
    ─ 确定性流程（代码）─────────────────────────────────────
      ingest()        : 调用 HunterPipeline（纯代码 ETL）+ KnowledgeManagerAgent
      submit_answer() : 评估→SM-2→记忆→推荐，全部在代码里完成
      end_session()   : 记忆整合 + 评估报告（代码触发）

    ─ 判断性流程（LLM Agent）────────────────────────────────
      chat()          : 自由对话、出题推荐、笔记、查看掌握度等
    """

    def __init__(self):
        logger.info("🔄 初始化面试系统编排器 v3.0...")
        try:
            from backend.services.knowledge.knowledge_manager import knowledge_manager
            self.knowledge_manager = knowledge_manager
            self.interviewer = InterviewerAgent()
            # 按 user_id 缓存 session 内的标签失误计数 {user_id: {session_id: {tag: count}}}
            self._session_weak_counts: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
                lambda: defaultdict(lambda: defaultdict(int))
            )
            logger.info("✅ 编排器初始化完成（KnowledgeManager + Interviewer）")
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise

    # ===========================================================
    # 记忆辅助
    # ===========================================================

    # ===========================================================
    # 四层记忆系统（基于 SQLite + ContextBuilder 实现）
    # hello-agents 1.0.0 移除了 MemoryTool，改用项目自有存储实现
    # working   → SQLite session_history（当前会话上下文）
    # episodic  → SQLite study_records（答题经历）
    # semantic  → SQLite tag_mastery + user_progress（用户画像）
    # perceptual→ 面经场景不需要，忽略
    # ===========================================================

    def _write_episodic(self, user_id: str, content: str,
                         importance: float = 0.75,
                         event_type: str = "study_event",
                         session_id: str = "", **kw):
        """情节记忆：答题经历写入 SQLite study_records（已由 submit_answer 确定性写入，此处为补充）"""
        # study_records 已在 submit_answer 中确定性写入，这里只记录 debug
        logger.debug(f"[情节记忆] user={user_id} event={event_type} len={len(content)}")

    def _write_semantic(self, user_id: str, content: str,
                         importance: float = 0.85,
                         knowledge_type: str = "user_profile", **kw):
        """语义记忆：用户画像写入 SQLite tag_mastery（已由 submit_answer 确定性写入）"""
        logger.debug(f"[语义记忆] user={user_id} type={knowledge_type} len={len(content)}")

    def _write_working(self, user_id: str, content: str,
                        importance: float = 0.5, session_id: str = ""):
        """工作记忆：当前 session 上下文，已由 sqlite_service.update_session_history 维护"""
        logger.debug(f"[工作记忆] user={user_id} session={session_id} len={len(content)}")

    def _write_perceptual(self, user_id: str, content: str,
                           modality: str = "text", importance: float = 0.7,
                           file_path: str = None, **kw):
        """感知记忆：面经场景不需要图像/音频感知，忽略"""
        pass

    def _consolidate_session_memories(self, user_id: str):
        """Session 结束时的记忆整合（SQLite 自动持久化，无需额外操作）"""
        logger.debug(f"[记忆整合] user={user_id} - SQLite 自动持久化，无需整合")

    # 记忆由 hello_agents 框架提供：
    # - HistoryManager + SessionStore（对话历史）
    # - recall_memory 工具（用户画像、薄弱点、答题记录）
    # 不再在此构建 memory_context，Agent 通过工具按需获取

    # ===========================================================
    # 确定性流程 1：内容采集管道（代码驱动 ETL）
    # ===========================================================

    async def _run_ingestion_pipeline(self, url: str,
                                       user_id: str = "",
                                       source_platform: str = "") -> str:
        """
        Hunter 阶段（纯代码管道）+ KnowledgeManager 阶段（LLM 结构化）。
        HunterPipeline 的每一步由代码固定控制，KnowledgeManager 只做语义理解。
        """
        logger.info(f"📡 [HunterPipeline] 开始处理: {url}")

        # ── 纯代码管道（爬取/清洗/校验/OCR/元信息）──
        pipeline_result = await run_hunter_pipeline(url, source_platform)

        if not pipeline_result.success:
            reason = pipeline_result.skip_reason or "未知原因"
            logger.info(f"⏭️  管道跳过: {reason}")
            return f"跳过（{reason}）"

        logger.info(f"🏗️  [KnowledgeManagerAgent] 开始结构化入库 (文本长度 {len(pipeline_result.text)})...")

        # 将元信息附加到文本头，帮助 KnowledgeManager 提取更准确
        meta_hint = ""
        if pipeline_result.meta:
            meta_hint = f"[元信息提示] {json.dumps(pipeline_result.meta, ensure_ascii=False)}\n\n"

        # ReActAgent.run() 是同步函数，用 run_in_executor 在线程池中运行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            self.knowledge_manager.run,
            f"请处理以下文本并存入数据库:\n\n{meta_hint}{pipeline_result.text[:5000]}"
        )

        # ── 记录爬取事件到情景记忆（确定性，总是执行）──
        if user_id:
            ocr_note = "（含OCR图片识别）" if pipeline_result.ocr_triggered else ""
            self._write_episodic(
                user_id=user_id,
                content=f"收录面经：{url}{ocr_note}，结果：{report[:80]}",
                importance=0.6,
                event_type="content_ingestion"
            )

        return report

    # ===========================================================
    # 确定性流程 2：答题提交钩子
    # 这是与 /chat 并列的独立 API 端点的后端逻辑
    # ===========================================================

    async def submit_answer(self,
                             user_id: str,
                             session_id: str,
                             question_id: str,
                             question_text: str,
                             user_answer: str,
                             question_tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        用户提交答案时的确定性处理链。
        每个步骤都是无条件执行的代码，不依赖 LLM 决定"要不要做"。

        Returns:
            {
              "score": int,
              "feedback": str,
              "missed_points": [str],
              "strong_points": [str],
              "explanation": str,          # LLM 生成的自然语言解释
              "recommendation": str | None  # score ≤ 2 时的知识推荐
            }
        """
        tags = question_tags or []

        # ── Step A：结构化评估（最小 LLM 调用，JSON mode）──────
        logger.info(f"📝 [submit_answer] 评估用户答案 q={question_id}")
        evaluation = _evaluate_answer_structured(question_text, user_answer)
        score = evaluation["score"]

        # 如果 LLM 返回了 tags，合并进来
        llm_tags = evaluation.get("tags", [])
        merged_tags = list(set(tags + llm_tags))

        # ── Step B：SM-2 更新（确定性，总是执行）───────────────
        ai_feedback = (
            evaluation.get("feedback", "") +
            ("；遗漏：" + "、".join(evaluation["missed_points"])
             if evaluation.get("missed_points") else "")
        )
        sqlite_service.add_study_record(
            user_id=user_id,
            question_id=question_id,
            score=score,
            user_answer=user_answer,
            ai_feedback=ai_feedback,
            session_id=session_id
        )

        # ── Step C：标签掌握度更新（确定性）─────────────────────
        if merged_tags:
            sqlite_service.update_tag_mastery(user_id, merged_tags, score)

        # ── Step D：情景记忆（确定性，总是执行）─────────────────
        self._write_episodic(
            user_id=user_id,
            content=(
                f"回答了题目【{question_text[:60]}】，得分 {score}/5。"
                f"标签：{', '.join(merged_tags)}。"
                + (f"遗漏：{evaluation['missed_points'][:2]}"
                   if evaluation.get("missed_points") else "")
            ),
            importance=0.65 + score * 0.05,
            event_type="study_record",
            question_id=question_id,
            score=score,
            session_id=session_id
        )

        # ── Step E：语义记忆更新（确定性，按得分写弱/强）────────
        if score <= 2:
            self._write_semantic(
                user_id=user_id,
                content=f"用户对【{'、'.join(merged_tags)}】掌握薄弱（{score}/5），需重点加强",
                importance=0.82,
                knowledge_type="weakness"
            )
        elif score >= 4:
            self._write_semantic(
                user_id=user_id,
                content=f"用户对【{'、'.join(merged_tags)}】掌握较好（{score}/5）",
                importance=0.75,
                knowledge_type="strength"
            )

        # ── Step F：连续薄弱检测 + 知识推荐（确定性计数器）──────
        recommendation_text: Optional[str] = None

        if score <= 2 and merged_tags:
            # 更新本 session 内的标签失误计数
            for tag in merged_tags:
                self._session_weak_counts[user_id][session_id][tag] += 1

            # 触发条件：本次得分 ≤ 2（单次失误即推荐），或累计 ≥ 2 次
            trigger_tags = merged_tags  # 本次失误标签全部推荐
            consecutive_tags = [
                tag for tag in merged_tags
                if self._session_weak_counts[user_id][session_id][tag] >= 2
            ]
            if consecutive_tags:
                logger.info(f"🔁 连续薄弱标签: {consecutive_tags}，触发强化推荐")

            recommendation_text = _knowledge_recommender.run({
                "user_id": user_id,
                "tags": trigger_tags,
                "max_resources": 2,
                "max_mistakes": 3
            })

            # 连续薄弱写入语义记忆（更高 importance）
            if consecutive_tags:
                self._write_semantic(
                    user_id=user_id,
                    content=f"用户对【{'、'.join(consecutive_tags)}】多次失误，需系统学习",
                    importance=0.92,
                    knowledge_type="repeated_weakness"
                )

        # ── Step G：生成自然语言解释（LLM，专注"解释"这一件事）─
        explanation = _generate_explanation(question_text, evaluation, recommendation_text)

        logger.info(f"✅ [submit_answer] 完成 score={score}, tags={merged_tags}, "
                    f"recommendation={'有' if recommendation_text else '无'}")

        return {
            "score": score,
            "feedback": evaluation.get("feedback", ""),
            "missed_points": evaluation.get("missed_points", []),
            "strong_points": evaluation.get("strong_points", []),
            "explanation": explanation,
            "recommendation": recommendation_text,
            "tags": merged_tags
        }

    # ===========================================================
    # 对话接口（InterviewerAgent 专注开放对话）
    # ===========================================================

    async def chat(
        self,
        user_id: str,
        message: str,
        resume: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> tuple:
        """
        自由对话接口：出题推荐、概念解释、笔记管理、掌握度查询等。
        返回 (reply: str, thinking_steps: List[Dict])。
        对话记录与 LLM 回复均入库，支持前端加载历史。
        """
        import time
        start_time = time.time()
        
        logger.info("=" * 60)
        logger.info(f"[对话处理] 开始处理用户 {user_id} 的消息")
        logger.info("=" * 60)
        
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        # 注入 user_id、session_id 到线程上下文（SqliteSessionStore 与工具依赖）
        from backend.agents.context import set_current_user_id, set_current_session_id
        from backend.agents.thinking_capture import ThinkingCapture
        set_current_user_id(user_id)
        set_current_session_id(session_id)

        # 确保 session 存在
        sqlite_service.ensure_session_exists(session_id, user_id)

        self._write_working(user_id, f"用户：{message}", session_id=session_id)
        if resume:
            self._write_perceptual(user_id, f"简历内容（{len(resume)}字）",
                                    modality="text", importance=0.8,
                                    session_id=session_id)

        # 使用 hello_agents 原生 load_session：恢复 HistoryManager（框架记忆能力）
        session_path = f"{user_id}:{session_id}"
        try:
            self.interviewer.load_session(session_path, check_consistency=False)
            logger.debug(f"[对话处理] 已加载 session: {session_path}")
        except FileNotFoundError:
            logger.debug(f"[对话处理] 新 session，无历史: {session_path}")
        except Exception as e:
            logger.warning(f"[对话处理] load_session 失败，使用空历史: {e}")

        # 记忆由框架提供：HistoryManager(load_session) + recall_memory 工具
        # 不再在此注入 memory_context，Agent 通过 recall_memory 按需获取
        context_prefix = "\n".join(filter(None, [
            f"[系统] user_id={user_id}, session_id={session_id}",
            f"[简历]\n{resume}" if resume else "",
        ]))
        full_input = f"{context_prefix}\n\n[用户消息]\n{message}" if context_prefix.strip() else message

        logger.info(f"[对话处理] 💬 [InterviewerAgent] 处理用户 {user_id} 的对话，消息: {message[:80]}")

        # ── hello_agents：run() + ThinkingCapture（思考步骤需线程内 print 捕获）──
        # arun() 为原生异步，不经过 executor，ThinkingCapture 无法捕获；故保留 run
        loop = asyncio.get_event_loop()

        def _run_with_capture():
            with ThinkingCapture() as tc:
                return self.interviewer.run(full_input), tc.get_steps()

        try:
            agent_start = time.time()
            timeout = getattr(settings, "interviewer_timeout", 30)
            response, thinking_steps = await asyncio.wait_for(
                loop.run_in_executor(None, _run_with_capture),
                timeout=float(timeout)
            )
            agent_time = time.time() - agent_start
            logger.info(f"[性能] Agent 执行耗时: {agent_time:.2f}s")
        except asyncio.TimeoutError:
            logger.warning(f"[对话处理] ⚠️ Agent 执行超时（{timeout}s），返回部分结果")
            response = "抱歉，处理您的请求耗时较长，请稍后重试。"
            thinking_steps = []
        except Exception as agent_err:
            logger.error(f"[对话处理] ❌ [InterviewerAgent] run() 抛出异常: {agent_err}", exc_info=True)
            raise
        logger.info(f"[对话处理] ✅ [InterviewerAgent] 回复完成 ({len(response)}字, 思考{len(thinking_steps)}步): {response[:200]}")

        # hello_agents SessionStore：持久化 HistoryManager 到 SqliteSessionStore
        try:
            self.interviewer.save_session(session_id)
            logger.debug(f"[对话处理] 已保存 session: {session_id}")
        except Exception as e:
            logger.warning(f"[对话处理] save_session 失败: {e}")

        self._write_working(user_id, f"AI：{response[:200]}", importance=0.4,
                             session_id=session_id)
        self._write_episodic(
            user_id=user_id,
            content=f"对话：「{message[:60]}」→「{response[:60]}」",
            importance=0.5,
            event_type="dialogue",
            session_id=session_id
        )


        # ── 📝 记录详细的交互日志（推理过程、工具调用等）──
        try:
            from backend.services.logging.interviewer_logger import get_interviewer_logger
            interviewer_logger = get_interviewer_logger()
            
            # 记录完整对话
            interviewer_logger.log_chat(
                user_id=user_id,
                session_id=session_id,
                user_message=message,
                ai_response=response,
                thinking_steps=thinking_steps,
                metadata={
                    "has_resume": bool(resume),
                    "resume_length": len(resume) if resume else 0,
                    "full_input_length": len(full_input)
                }
            )
            
            # 记录详细推理过程
            if thinking_steps:
                interviewer_logger.log_thinking(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=message,
                    thinking_steps=thinking_steps
                )
            
            logger.debug(f"Log saved to interviewer_logs/")
        except Exception as log_err:
            logger.warning(f"Failed to save log: {log_err}")

        total_time = time.time() - start_time
        logger.info(f"[性能] 总耗时: {total_time:.2f}s")
        logger.info("=" * 60)
        logger.info("[对话处理] 对话处理完成")
        logger.info("=" * 60)

        return response, thinking_steps

    # ===========================================================
    # 流式对话（简化版：run() + executor + 伪流式）
    # ===========================================================

    async def chat_stream(
        self,
        user_id: str,
        message: str,
        resume: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """
        流式对话：使用 run() + executor 的简化方案。
        
        策略：
        1. 在 executor 中同步执行 run()，获得完整答案
        2. 将答案按 token 分块，逐个推送给前端（伪流式）
        3. 前端收到每个 chunk 后立即更新 DOM，实现流式效果
        
        优点：
        - 逻辑简单，无需复杂的事件过滤
        - 多轮对话连贯性由 HistoryManager 保证
        - 工具调用正常工作
        
        缺点：
        - 延迟略高（一次性等待完整答案）
        - 但对用户体验影响不大（通常 5-30s 内完成）
        """
        import time as _time
        start_time = _time.time()

        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        from backend.agents.context import set_current_user_id, set_current_session_id
        set_current_user_id(user_id)
        set_current_session_id(session_id)

        sqlite_service.ensure_session_exists(session_id, user_id)
        self._write_working(user_id, f"用户：{message}", session_id=session_id)
        if resume:
            self._write_perceptual(user_id, f"简历内容（{len(resume)}字）",
                                   modality="text", importance=0.8, session_id=session_id)

        session_path = f"{user_id}:{session_id}"
        try:
            self.interviewer.load_session(session_path, check_consistency=False)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[chat_stream] load_session 失败: {e}")

        context_prefix = "\n".join(filter(None, [
            f"[系统] user_id={user_id}, session_id={session_id}",
            f"[简历]\n{resume}" if resume else "",
        ]))
        full_input = f"{context_prefix}\n\n[用户消息]\n{message}" if context_prefix.strip() else message

        try:
            # Step 1: 在 executor 中同步执行 run()，获得完整答案
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, self.interviewer.run, full_input),
                timeout=90.0
            )

            # Step 2: 从 hello_agents 的 history_manager 中提取思考步骤
            thinking_steps = []
            if hasattr(self.interviewer, 'history_manager'):
                history = self.interviewer.history_manager.get_history()
                for msg in history:
                    if msg.role == "assistant" and msg.metadata:
                        if msg.metadata.get("type") == "thought":
                            thinking_steps.append({"thought": msg.content})
                        elif msg.metadata.get("type") == "action":
                            thinking_steps.append({"action": msg.content})

            # Step 3: 构造思考步骤事件
            for step in thinking_steps:
                payload = {
                    "type": "tool_call_finish",
                    "data": {
                        "tool_name": "Thought" if step.get("thought") else "Action",
                        "result": step.get("thought") or step.get("action") or ""
                    }
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)  # 让前端有机会处理

            # Step 4: 按 token 分块推送答案（真正流式）
            # 简单策略：按句子或固定字符数分块
            chunk_size = 50  # 每个 chunk 约 50 个字符
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i+chunk_size]
                payload = {
                    "type": "llm_chunk",
                    "data": {
                        "chunk": chunk
                    }
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)  # 模拟流式延迟，让前端有时间渲染

            # Step 5: 发送完成事件
            finish_payload = {
                "type": "agent_finish",
                "data": {
                    "result": response,
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
            }
            yield f"data: {json.dumps(finish_payload, ensure_ascii=False)}\n\n"

            # Step 5: 持久化
            try:
                self.interviewer.save_session(session_id)
                if response.strip():
                    sqlite_service.patch_last_assistant_content(session_id, response)
            except Exception as e:
                logger.warning(f"[chat_stream] save_session 失败: {e}")

            self._write_working(user_id, f"AI：{response[:100]}", importance=0.4, session_id=session_id)
            self._write_episodic(
                user_id=user_id,
                content=f"对话：「{message[:60]}」→「{response[:60]}」",
                importance=0.5,
                event_type="dialogue",
                session_id=session_id
            )

        except asyncio.TimeoutError:
            logger.warning(f"[chat_stream] 超时（90s）")
            from hello_agents.core.streaming import StreamEvent, StreamEventType
            err_ev = StreamEvent.create(
                StreamEventType.ERROR,
                "Orchestrator",
                error="⚠️ 响应超时（90s），LLM 服务可能繁忙，请稍后重试"
            )
            yield err_ev.to_sse()

        except Exception as e:
            logger.error(f"[chat_stream] 异常: {e}", exc_info=True)
            from hello_agents.core.streaming import StreamEvent, StreamEventType
            err_ev = StreamEvent.create(
                StreamEventType.ERROR,
                "Orchestrator",
                error=str(e)[:500]
            )
            yield err_ev.to_sse()

    # ===========================================================
    # 公开接口
    # ===========================================================

    async def ingest_instant(self, url: str, user_id: str,
                              source_platform: str = "") -> Dict[str, Any]:
        """API：立即收录一条 URL"""
        logger.info(f"⚡ 用户 {user_id} 触发立即收录: {url}")
        try:
            report = await self._run_ingestion_pipeline(url, user_id, source_platform)
            return {"status": "success", "details": report}
        except Exception as e:
            logger.error(f"❌ 立即收录失败: {e}")
            return {"status": "error", "message": str(e)}

    async def ingest_batch(self, urls: List[str],
                            source_platform: str = "") -> Dict[str, Any]:
        """API：批量收录"""
        logger.info(f"⏰ 批量收录任务：{len(urls)} 条")
        results = []
        for url in urls:
            try:
                report = await self._run_ingestion_pipeline(url, source_platform=source_platform)
                results.append({"url": url, "status": "success", "report": report})
            except Exception as e:
                logger.error(f"⚠️ 处理失败 {url}: {e}")
                results.append({"url": url, "status": "failed", "error": str(e)})
        success_count = sum(1 for r in results if r["status"] == "success")
        return {"summary": f"成功: {success_count}/{len(urls)}", "details": results}

    async def end_session(self, user_id: str, session_id: str,
                           session_summary: str = ""):
        """
        结束 session：整合记忆（确定性）。
        不再需要 Agent 帮我们"记得"调用这个。
        """
        if session_summary:
            self._write_episodic(
                user_id=user_id,
                content=f"Session 结束：{session_summary}",
                importance=0.88,
                event_type="session_complete",
                session_id=session_id
            )
        self._consolidate_session_memories(user_id)

        # 清理本 session 的失误计数
        if user_id in self._session_weak_counts:
            self._session_weak_counts[user_id].pop(session_id, None)

        logger.info(f"✅ Session {session_id} 已结束并整合记忆")

    async def update_user_profile(self, user_id: str, tech_stack: List[str],
                                   target_company: str = "",
                                   target_position: str = "",
                                   experience_level: str = "junior"):
        """写入用户技术画像到语义记忆（确定性，简历分析后由代码调用）"""
        parts = [f"用户技术栈：{', '.join(tech_stack)}"]
        if target_company:
            parts.append(f"目标公司：{target_company}")
        if target_position:
            parts.append(f"目标岗位：{target_position}")
        parts.append(f"经验等级：{experience_level}")
        self._write_semantic(user_id, "。".join(parts), importance=0.92,
                              knowledge_type="user_profile")
        logger.info(f"✅ 用户 {user_id} 技术画像写入语义记忆")

    def get_memory_summary(self, user_id: str) -> str:
        mt = _get_memory_tool(user_id)
        if not mt:
            return "记忆系统未初始化"
        try:
            return mt.execute("summary", limit=10)
        except Exception as e:
            return f"获取记忆摘要失败: {e}"


# ===========================================================
# 辅助函数
# ===========================================================

def _format_thinking_for_db(steps: list) -> str:
    """将思考步骤列表格式化为纯文本，用于入库摘要。"""
    if not steps:
        return ""
    lines = []
    for i, s in enumerate(steps, 1):
        lines.append(f"--- 第 {i} 步 ---")
        if s.get("thought"):
            lines.append(f"🤔 {s['thought']}")
        if s.get("action"):
            lines.append(f"🎬 {s['action']}")
        if s.get("observation"):
            lines.append(f"👀 {s['observation']}")
        if s.get("warning"):
            lines.append(s["warning"])
    return "\n".join(lines)


# ===========================================================
# 单例
# ===========================================================
_orchestrator_instance = None


def get_orchestrator() -> InterviewSystemOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = InterviewSystemOrchestrator()
    return _orchestrator_instance
