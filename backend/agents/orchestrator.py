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
  • 知识结构化（帖子 → 题目 JSON）           → KnowledgeArchitectAgent
"""

import asyncio
import json
import logging
import re
import uuid
import requests
from collections import defaultdict
from functools import partial
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.agents.architect_agent import KnowledgeArchitectAgent
from backend.agents.interviewer_agent import InterviewerAgent
from backend.config.config import settings
from backend.services.hunter_pipeline import run_hunter_pipeline
from backend.services.sqlite_service import sqlite_service
from backend.tools.interviewer_tools import KnowledgeRecommender

logger = logging.getLogger(__name__)

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
        logger.warning("⚠️ hello-agents MemoryTool 未安装，记忆功能降级")
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
            result = json.loads(content)
            # 确保 score 在合法范围
            result["score"] = max(0, min(5, int(result.get("score", 3))))
            return result
        else:
            logger.warning(f"评估 LLM 返回 {resp.status_code}")
            return default
    except Exception as e:
        logger.error(f"_evaluate_answer_structured 异常: {e}")
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
      ingest()        : 调用 HunterPipeline（纯代码 ETL）+ ArchitectAgent
      submit_answer() : 评估→SM-2→记忆→推荐，全部在代码里完成
      end_session()   : 记忆整合 + 评估报告（代码触发）

    ─ 判断性流程（LLM Agent）────────────────────────────────
      chat()          : 自由对话、出题推荐、笔记、查看掌握度等
    """

    def __init__(self):
        logger.info("🔄 初始化面试系统编排器 v3.0...")
        try:
            self.architect = KnowledgeArchitectAgent()
            self.interviewer = InterviewerAgent()
            # 按 user_id 缓存 MemoryTool（懒加载）
            self._user_memory_tools: Dict[str, Any] = {}
            # 按 user_id 缓存 session 内的标签失误计数 {user_id: {session_id: {tag: count}}}
            self._session_weak_counts: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
                lambda: defaultdict(lambda: defaultdict(int))
            )
            logger.info("✅ 编排器初始化完成（KnowledgeArchitect + Interviewer）")
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise

    # ===========================================================
    # 记忆辅助
    # ===========================================================

    def _get_user_memory(self, user_id: str):
        if user_id not in self._user_memory_tools:
            self._user_memory_tools[user_id] = _get_memory_tool(user_id)
        return self._user_memory_tools.get(user_id)

    def _write_episodic(self, user_id: str, content: str,
                         importance: float = 0.75,
                         event_type: str = "study_event",
                         session_id: str = "", **kw):
        mt = self._get_user_memory(user_id)
        if not mt:
            return
        try:
            mt.execute("add", content=content, memory_type="episodic",
                       importance=importance, event_type=event_type,
                       session_id=session_id, **kw)
        except Exception as e:
            logger.warning(f"写情景记忆失败: {e}")

    def _write_semantic(self, user_id: str, content: str,
                         importance: float = 0.85,
                         knowledge_type: str = "user_profile", **kw):
        mt = self._get_user_memory(user_id)
        if not mt:
            return
        try:
            mt.execute("add", content=content, memory_type="semantic",
                       importance=importance, knowledge_type=knowledge_type, **kw)
        except Exception as e:
            logger.warning(f"写语义记忆失败: {e}")

    def _write_working(self, user_id: str, content: str,
                        importance: float = 0.5, session_id: str = ""):
        mt = self._get_user_memory(user_id)
        if not mt:
            return
        try:
            mt.execute("add", content=content, memory_type="working",
                       importance=importance, session_id=session_id,
                       timestamp=datetime.now().isoformat())
        except Exception as e:
            logger.warning(f"写工作记忆失败: {e}")

    def _write_perceptual(self, user_id: str, content: str,
                           modality: str = "text", importance: float = 0.7,
                           file_path: str = None, **kw):
        mt = self._get_user_memory(user_id)
        if not mt:
            return
        try:
            kwargs = dict(content=content, memory_type="perceptual",
                          importance=importance, modality=modality, **kw)
            if file_path:
                kwargs["file_path"] = file_path
            mt.execute("add", **kwargs)
        except Exception as e:
            logger.warning(f"写感知记忆失败: {e}")

    def _search_memory(self, user_id: str, query: str,
                        memory_types: List[str] = None, limit: int = 5) -> str:
        mt = self._get_user_memory(user_id)
        if not mt:
            return ""
        try:
            result = mt.execute("search", query=query,
                                memory_types=memory_types, limit=limit,
                                min_importance=0.3)
            return result if isinstance(result, str) else ""
        except Exception as e:
            logger.warning(f"记忆检索失败: {e}")
            return ""

    def _consolidate_session_memories(self, user_id: str):
        mt = self._get_user_memory(user_id)
        if not mt:
            return
        try:
            mt.execute("consolidate", from_type="working", to_type="episodic",
                       importance_threshold=0.65)
            mt.execute("forget", strategy="importance_based", threshold=0.3)
            logger.info(f"✅ 用户 {user_id} session 记忆整合完成")
        except Exception as e:
            logger.warning(f"记忆整合失败: {e}")

    def _build_memory_context(self, user_id: str, user_message: str) -> str:
        parts = []
        semantic = self._search_memory(user_id, "用户技术栈 目标岗位 掌握程度",
                                        memory_types=["semantic"], limit=3)
        if semantic and "未找到" not in semantic:
            parts.append(f"[用户知识画像]\n{semantic}")
        if user_message:
            episodic = self._search_memory(user_id, user_message,
                                            memory_types=["episodic"], limit=3)
            if episodic and "未找到" not in episodic:
                parts.append(f"[近期相关学习记录]\n{episodic}")
        return "\n\n".join(parts)

    # ===========================================================
    # 确定性流程 1：内容采集管道（代码驱动 ETL）
    # ===========================================================

    async def _run_ingestion_pipeline(self, url: str,
                                       user_id: str = "",
                                       source_platform: str = "") -> str:
        """
        Hunter 阶段（纯代码管道）+ Architect 阶段（LLM 结构化）。
        HunterPipeline 的每一步由代码固定控制，Architect 只做语义理解。
        """
        logger.info(f"📡 [HunterPipeline] 开始处理: {url}")

        # ── 纯代码管道（爬取/清洗/校验/OCR/元信息）──
        pipeline_result = await run_hunter_pipeline(url, source_platform)

        if not pipeline_result.success:
            reason = pipeline_result.skip_reason or "未知原因"
            logger.info(f"⏭️  管道跳过: {reason}")
            return f"跳过（{reason}）"

        logger.info(f"🏗️  [ArchitectAgent] 开始结构化入库 (文本长度 {len(pipeline_result.text)})...")

        # 将元信息附加到文本头，帮助 Architect 提取更准确
        meta_hint = ""
        if pipeline_result.meta:
            meta_hint = f"[元信息提示] {json.dumps(pipeline_result.meta, ensure_ascii=False)}\n\n"

        # ReActAgent.run() 是同步函数，用 run_in_executor 在线程池中运行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            self.architect.run,
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

    async def chat(self, user_id: str, message: str,
                   resume: Optional[str] = None,
                   session_id: Optional[str] = None) -> str:
        """
        自由对话接口：出题推荐、概念解释、笔记管理、掌握度查询等。
        InterviewerAgent 只做"需要 LLM 理解和推理"的事。
        具体的答题评估请走 submit_answer()。
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        # 构建记忆上下文注入（代码负责检索，不让 Agent 自己决定）
        memory_context = self._build_memory_context(user_id, message)

        # 写用户输入到工作记忆（确定性，总是执行）
        self._write_working(user_id, f"用户：{message}", session_id=session_id)

        # 简历写入感知记忆（确定性）
        if resume:
            self._write_perceptual(user_id, f"简历内容（{len(resume)}字）",
                                    modality="text", importance=0.8,
                                    session_id=session_id)

        # 组装注入上下文（记忆 + 用户信息）
        context_prefix = "\n".join(filter(None, [
            f"[系统] user_id={user_id}, session_id={session_id}",
            memory_context,
            f"[简历]\n{resume}" if resume else "",
        ]))
        full_input = f"{context_prefix}\n\n[用户消息]\n{message}" if context_prefix.strip() else message

        logger.info(f"💬 [InterviewerAgent] 处理用户 {user_id} 的对话，消息: {message[:80]}")
        # ReActAgent.run() 是同步函数，在线程池中运行
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, self.interviewer.run, full_input)
        except Exception as agent_err:
            logger.error(f"❌ [InterviewerAgent] run() 抛出异常: {agent_err}", exc_info=True)
            raise
        logger.info(f"✅ [InterviewerAgent] 回复完成 ({len(response)}字): {response[:200]}")

        # 写 AI 回复到工作记忆（确定性）
        self._write_working(user_id, f"AI：{response[:200]}", importance=0.4,
                             session_id=session_id)

        # 写对话事件到情景记忆（确定性）
        self._write_episodic(
            user_id=user_id,
            content=f"对话：「{message[:60]}」→「{response[:60]}」",
            importance=0.5,
            event_type="dialogue",
            session_id=session_id
        )

        return response

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
        mt = self._get_user_memory(user_id)
        if not mt:
            return "记忆系统未初始化"
        try:
            return mt.execute("summary", limit=10)
        except Exception as e:
            return f"获取记忆摘要失败: {e}"


# ===========================================================
# 单例
# ===========================================================
_orchestrator_instance = None


def get_orchestrator() -> InterviewSystemOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = InterviewSystemOrchestrator()
    return _orchestrator_instance
