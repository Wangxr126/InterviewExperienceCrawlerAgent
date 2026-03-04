"""
面试官工具箱 (Interviewer Tools) v2.0
新增：SM-2 遗忘曲线算法 / NoteTool / FilterTool / MasteryReporter
"""
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from hello_agents.tools import Tool, ToolParameter
from backend.services.neo4j_service import neo4j_service
from backend.services.sqlite_service import sqlite_service
from backend.tools.architect_tools import generate_embedding

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. 智能推荐引擎 (SmartRecommendationEngine)
# 优先级：遗忘曲线到期 → 薄弱标签新题 → 个性化新题
# ==============================================================================

class SmartRecommendationEngine(Tool):
    """
    智能出题引擎，融合四种推荐策略：
    1. 遗忘曲线：到期复习题优先
    2. 薄弱点强化：novice/learning 级别标签
    3. 相似/变体：换个问法
    4. 个性化新题：按用户技术栈
    """
    def __init__(self):
        super().__init__(
            name="get_recommended_question",
            description=(
                "获取下一道推荐面试题。"
                "mode 可选：auto（自动）、review（复习到期题）、weakness（薄弱点）、new（新题）、company（按公司）。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string", description="用户ID", required=True),
            ToolParameter(name="mode", type="string",
                          description="推荐模式: auto/review/weakness/new/company", required=False),
            ToolParameter(name="topic", type="string",
                          description="指定主题标签，如 Redis、MySQL", required=False),
            ToolParameter(name="company", type="string",
                          description="指定公司，如 字节跳动", required=False),
            ToolParameter(name="difficulty", type="string",
                          description="指定难度: easy/medium/hard", required=False),
            ToolParameter(name="exclude_ids", type="array",
                          description="本次会话已出过的题目ID列表，避免重复", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        mode = parameters.get("mode", "auto")
        topic = parameters.get("topic", "")
        company = parameters.get("company", "")
        exclude_ids = parameters.get("exclude_ids") or []

        if not user_id:
            return "❌ 缺少 user_id"

        try:
            # ── 策略 1：遗忘曲线复习（auto 或 review 模式）──
            if mode in ("auto", "review"):
                due_list = sqlite_service.get_due_reviews(user_id, limit=5)
                due_list = [d for d in due_list if d["question_id"] not in exclude_ids]
                if due_list:
                    q = due_list[0]
                    days_overdue = _days_overdue(q.get("next_review_at", ""))
                    return self._format_question(q, mode_label="【📅 复习题】",
                                                 note=f"上次评分: {q.get('score', '?')}/5，已超期 {days_overdue} 天")

            # ── 策略 2：薄弱点强化 ──
            if mode in ("auto", "weakness"):
                weak_tags = sqlite_service.get_weak_tags(user_id)
                if weak_tags:
                    weak_tag = weak_tags[0]["tag"]
                    results = neo4j_service.recommend_by_tag(weak_tag, limit=3, exclude_ids=exclude_ids)
                    if results:
                        q = results[0]
                        return self._format_question(q, mode_label="【⚠️ 薄弱点强化】",
                                                     note=f"标签「{weak_tag}」需要加强练习")

            # ── 策略 3：按公司推荐（company 模式或指定 company）──
            if company or mode == "company":
                results = neo4j_service.recommend_by_company(
                    company or "字节跳动", limit=3, exclude_ids=exclude_ids
                )
                if results:
                    return self._format_question(results[0], mode_label=f"【🏢 {company} 真题】")

            # ── 策略 4：按主题推荐新题 ──
            if topic:
                results = neo4j_service.recommend_by_tag(topic, limit=3, exclude_ids=exclude_ids)
                if results:
                    return self._format_question(results[0], mode_label=f"【📚 {topic} 新题】")

            # ── 策略 5：按用户技术栈推荐个性化新题 ──
            profile = sqlite_service.get_user_profile(user_id)
            tech_stack = profile.get("tech_stack", []) if profile else []

            # 获取用户已做过的题目ID
            history = sqlite_service.get_study_history(user_id, limit=100)
            seen_ids = list({r["question_id"] for r in history}) + exclude_ids

            if tech_stack:
                results = neo4j_service.get_unseen_questions(tech_stack, seen_ids, limit=3)
                if results:
                    return self._format_question(results[0], mode_label="【✨ 个性化新题】")

            return "暂无匹配题目。请先爬取更多面经，或调整练习主题。"

        except Exception as e:
            logger.error(f"SmartRecommendationEngine 异常: {e}")
            return f"推荐引擎异常: {str(e)}"

    @staticmethod
    def _format_question(q: Dict, mode_label: str = "", note: str = "") -> str:
        lines = [mode_label] if mode_label else []
        lines.append(f"**题目ID**: {q.get('id') or q.get('question_id', '?')}")
        lines.append(f"**题目**: {q.get('text') or q.get('question_text', '（无题目）')}")
        if q.get("difficulty"):
            lines.append(f"**难度**: {q['difficulty']}")
        if q.get("company"):
            lines.append(f"**来源公司**: {q['company']}")
        if note:
            lines.append(f"*{note}*")
        lines.append("\n请回答上面这道题，回答完毕后告诉我「评分」或继续下一题。")
        return "\n".join(lines)


def _days_overdue(next_review_str: str) -> int:
    try:
        dt = datetime.strptime(next_review_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - dt
        return max(0, delta.days)
    except Exception:
        return 0


# ==============================================================================
# 2. 进度打分机（含 SM-2 更新 + 标签掌握度更新）
# ==============================================================================

class ProgressTracker(Tool):
    """
    记录用户答题结果（0-5分），自动运行 SM-2 算法更新遗忘曲线参数，
    并同步更新用户的标签掌握度。
    """
    def __init__(self):
        super().__init__(
            name="update_progress",
            description=(
                "记录用户的答题得分（0-5分）并更新遗忘曲线参数。"
                "评分标准：0=完全不会，1=基本不会，2=大部分不会，"
                "3=勉强会，4=基本掌握，5=完全掌握。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string", required=True),
            ToolParameter(name="question_id", type="string", required=True),
            ToolParameter(name="score", type="integer",
                          description="评分 0-5", required=True),
            ToolParameter(name="user_answer", type="string",
                          description="用户的回答原文", required=False),
            ToolParameter(name="ai_feedback", type="string",
                          description="AI 的详细评价", required=False),
            ToolParameter(name="session_id", type="string",
                          description="当前面试 session ID", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        question_id = parameters.get("question_id", "")
        score = int(parameters.get("score", 0))
        user_answer = parameters.get("user_answer", "")
        ai_feedback = parameters.get("ai_feedback", "")
        session_id = parameters.get("session_id", "")

        if not user_id or not question_id:
            return "❌ 缺少 user_id 或 question_id"
        if not (0 <= score <= 5):
            return "❌ score 必须在 0-5 之间"

        try:
            sm2_result = sqlite_service.add_study_record(
                user_id=user_id, question_id=question_id,
                score=score, user_answer=user_answer,
                ai_feedback=ai_feedback, session_id=session_id
            )

            # 更新 session 对话历史
            if session_id:
                sqlite_service.update_session_history(session_id, "user_score",
                                                      f"题目 {question_id} 得分: {score}")

            msg = f"✅ 进度已记录 | 得分: {score}/5\n"
            msg += f"📅 下次复习时间: {sm2_result['next_review_at']}"
            if score < 3:
                msg += "\n💡 建议：这道题需要重点复习，明天将再次出现。"
            elif score >= 4:
                msg += f"\n🎉 掌握得不错！下次复习间隔: {sm2_result['interval_days']} 天"
            return msg

        except Exception as e:
            logger.error(f"ProgressTracker 异常: {e}")
            return f"❌ 记录失败: {str(e)}"


# ==============================================================================
# 3. 举一反三 / 换个问法（SimilaritySearchTool）
# ==============================================================================

class SimilaritySearchTool(Tool):
    """
    查找与当前题目语义相似的题目（举一反三）或变体题目（换个问法）。
    """
    def __init__(self):
        super().__init__(
            name="find_similar_questions",
            description=(
                "查找与指定题目相似的其他题目，用于举一反三或换个问法。"
                "mode: similar（语义相似）/ variant（换个问法）。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="query_text", type="string",
                          description="当前题目文本或知识点描述", required=True),
            ToolParameter(name="question_id", type="string",
                          description="当前题目ID（用于排除自身）", required=False),
            ToolParameter(name="mode", type="string",
                          description="similar（相似）或 variant（变体/换个问法）", required=False),
            ToolParameter(name="top_k", type="integer",
                          description="返回数量，默认3", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        query_text = parameters.get("query_text", "")
        question_id = parameters.get("question_id", "")
        mode = parameters.get("mode", "similar")
        top_k = int(parameters.get("top_k", 3))

        if not query_text.strip():
            return "❌ 查询文本不能为空"

        try:
            exclude_ids = [question_id] if question_id else []

            if mode == "variant" and question_id:
                # 换个问法：查 VARIANT_OF 图关系
                results = neo4j_service.get_variants(question_id)
                if results:
                    return self._format_results(results, title="【🔄 换个问法推荐】")
                # 没有预计算变体时，降级为相似度检索
                logger.info("未找到 VARIANT_OF 关系，降级为语义相似检索")

            # 语义相似检索
            vector = generate_embedding(query_text)
            if not vector:
                return "❌ 向量生成失败，无法检索相似题目"

            results = neo4j_service.search_similar(vector, top_k=top_k,
                                                    score_threshold=0.65,
                                                    exclude_ids=exclude_ids)
            if not results:
                return "未找到相似题目。"

            return self._format_results(results, title="【🔗 相关题目推荐（举一反三）】")

        except Exception as e:
            logger.error(f"SimilaritySearchTool 异常: {e}")
            return f"检索失败: {str(e)}"

    @staticmethod
    def _format_results(results: List[Dict], title: str = "") -> str:
        lines = [title] if title else []
        for idx, item in enumerate(results, 1):
            text = item.get("text", item.get("question_text", ""))
            q_id = item.get("id", item.get("question_id", ""))
            diff = item.get("difficulty", "")
            score = item.get("score", "")
            line = f"{idx}. [ID:{q_id}] {text[:60]}..."
            if diff:
                line += f" | 难度:{diff}"
            if score:
                line += f" | 相似度:{score:.2f}"
            lines.append(line)
        return "\n".join(lines)


# ==============================================================================
# 4. 题目过滤器 (FilterTool) —— 纯 SQL，不需要 LLM
# ==============================================================================

class FilterTool(Tool):
    """
    按条件过滤题目（公司/岗位/难度/标签/时间/关键词）。
    完全基于 SQLite，无需 LLM，秒级响应。
    """
    def __init__(self):
        super().__init__(
            name="filter_questions",
            description=(
                "按条件过滤题库中的题目。支持：公司、岗位、难度、标签、时间范围、关键词。"
                "结果按入库时间倒序返回。不需要 LLM，直接数据库查询。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="company", type="string",
                          description="公司名称，如 字节跳动", required=False),
            ToolParameter(name="position", type="string",
                          description="岗位，如 后端研发", required=False),
            ToolParameter(name="difficulty", type="string",
                          description="难度: easy/medium/hard", required=False),
            ToolParameter(name="tags", type="array",
                          description="标签列表，如 [\"Redis\", \"MySQL\"]", required=False),
            ToolParameter(name="source_platform", type="string",
                          description="来源: nowcoder/xiaohongshu", required=False),
            ToolParameter(name="date_from", type="string",
                          description="开始日期，如 2026-01-01", required=False),
            ToolParameter(name="date_to", type="string",
                          description="结束日期，如 2026-02-28", required=False),
            ToolParameter(name="keyword", type="string",
                          description="关键词，模糊匹配题目正文", required=False),
            ToolParameter(name="limit", type="integer",
                          description="返回数量上限，默认10", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        company = parameters.get("company")
        position = parameters.get("position")
        difficulty = parameters.get("difficulty")
        tags = parameters.get("tags") or []
        source_platform = parameters.get("source_platform")
        date_from = parameters.get("date_from")
        date_to = parameters.get("date_to")
        keyword = parameters.get("keyword")
        limit = int(parameters.get("limit", 10))

        try:
            results = sqlite_service.filter_questions(
                company=company, position=position, difficulty=difficulty,
                tags=tags, source_platform=source_platform,
                date_from=date_from, date_to=date_to,
                keyword=keyword, limit=limit
            )

            if not results:
                return "未找到符合条件的题目。请尝试放宽过滤条件。"

            lines = [f"🔍 共找到 {len(results)} 道题目：\n"]
            for idx, q in enumerate(results, 1):
                q_tags = json.loads(q.get("topic_tags") or "[]")
                line = (
                    f"{idx}. [{q['q_id']}] {q['question_text'][:60]}...\n"
                    f"   📌 难度:{q.get('difficulty','?')} | "
                    f"🏢 {q.get('company','') or '未知公司'} | "
                    f"🏷️ {', '.join(q_tags[:3]) or '无标签'} | "
                    f"📅 {q.get('created_at', '')[:10]}"
                )
                lines.append(line)

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"FilterTool 异常: {e}")
            return f"过滤查询失败: {str(e)}"


# ==============================================================================
# 5. 笔记工具 (NoteTool)
# ==============================================================================

class NoteTool(Tool):
    """
    管理用户笔记（创建/查看/更新/删除）。
    笔记可以关联到具体题目，支持标签、类型分类。
    """
    def __init__(self):
        super().__init__(
            name="manage_note",
            description=(
                "管理用户的学习笔记。"
                "action: create（新建）、list（查看）、update（修改）、delete（删除）。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="action", type="string",
                          description="操作: create/list/update/delete", required=True),
            ToolParameter(name="user_id", type="string", description="用户ID", required=True),
            ToolParameter(name="note_id", type="string",
                          description="笔记ID（update/delete 时必填）", required=False),
            ToolParameter(name="question_id", type="string",
                          description="关联的题目ID", required=False),
            ToolParameter(name="title", type="string", description="笔记标题", required=False),
            ToolParameter(name="content", type="string", description="笔记内容", required=False),
            ToolParameter(name="tags", type="array", description="笔记标签", required=False),
            ToolParameter(name="note_type", type="string",
                          description="类型: concept/mistake/tip/summary", required=False),
            ToolParameter(name="keyword", type="string",
                          description="关键词（list 时模糊搜索）", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        action = parameters.get("action", "list").lower()
        user_id = parameters.get("user_id", "")
        note_id = parameters.get("note_id")
        question_id = parameters.get("question_id")
        title = parameters.get("title", "")
        content = parameters.get("content", "")
        tags = parameters.get("tags") or []
        note_type = parameters.get("note_type", "concept")
        keyword = parameters.get("keyword")

        if not user_id:
            return "❌ 缺少 user_id"

        try:
            if action == "create":
                if not content.strip():
                    return "❌ 笔记内容不能为空"
                note_id = sqlite_service.create_note(
                    user_id=user_id, content=content, title=title,
                    question_id=question_id, tags=tags, note_type=note_type
                )
                return f"✅ 笔记已保存！ID: {note_id} | 类型: {note_type} | 标签: {tags}"

            elif action == "list":
                notes = sqlite_service.get_notes(
                    user_id=user_id, tags=tags if tags else None,
                    question_id=question_id, note_type=note_type if note_type != "concept" else None,
                    keyword=keyword, limit=10
                )
                if not notes:
                    return "暂无笔记。使用 create 操作新建笔记。"
                lines = [f"📓 你的笔记（共 {len(notes)} 条）：\n"]
                for n in notes:
                    lines.append(
                        f"[{n['note_id']}] 📌 {n['title'] or '无标题'} | {n['note_type']} | "
                        f"标签: {', '.join(n['tags']) or '无'}\n"
                        f"  {n['content'][:80]}...\n"
                        f"  📅 {n['updated_at'][:10]}"
                    )
                return "\n".join(lines)

            elif action == "update":
                if not note_id:
                    return "❌ update 操作必须提供 note_id"
                ok = sqlite_service.update_note(
                    note_id=note_id, user_id=user_id,
                    content=content or None,
                    title=title or None,
                    tags=tags or None
                )
                return "✅ 笔记已更新" if ok else "❌ 未找到该笔记或无权限修改"

            elif action == "delete":
                if not note_id:
                    return "❌ delete 操作必须提供 note_id"
                ok = sqlite_service.delete_note(note_id=note_id, user_id=user_id)
                return "✅ 笔记已删除" if ok else "❌ 未找到该笔记或无权限删除"

            else:
                return f"❌ 不支持的 action: {action}。可用：create/list/update/delete"

        except Exception as e:
            logger.error(f"NoteTool 异常: {e}")
            return f"笔记操作失败: {str(e)}"


# ==============================================================================
# 6. 掌握度报告 (MasteryReporter)
# ==============================================================================

class MasteryReporter(Tool):
    """
    生成用户的技术标签掌握度报告，展示各标签的平均分和掌握等级。
    完全基于 SQLite 聚合查询，不需要 LLM。
    """
    def __init__(self):
        super().__init__(
            name="get_mastery_report",
            description="生成用户的技术掌握度报告，包含各标签的平均分、掌握等级和练习次数。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string", description="用户ID", required=True),
            ToolParameter(name="tags", type="array",
                          description="指定查询的标签列表，不填则查全部", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        tags = parameters.get("tags") or []

        if not user_id:
            return "❌ 缺少 user_id"

        try:
            summary = sqlite_service.get_mastery_summary(user_id)
            by_level = summary["by_level"]

            lines = [
                f"📊 **技术掌握度报告**",
                f"总练习题数: {summary['total_questions_practiced']} | "
                f"平均分: {summary['overall_avg_score']}/5 | "
                f"正确率: {summary['correct_rate']}%\n"
            ]

            level_icons = {
                "expert": "🏆 已精通（Expert）",
                "proficient": "📚 良好掌握（Proficient）",
                "learning": "📖 学习中（Learning）",
                "novice": "❌ 待提升（Novice）"
            }

            has_data = False
            for level, label in level_icons.items():
                items = by_level.get(level, [])
                if tags:
                    items = [i for i in items if i["tag"] in tags]
                if not items:
                    continue
                has_data = True
                lines.append(label + "：")
                for item in items:
                    icon = "✅" if level in ("expert", "proficient") else ("⚠️" if level == "learning" else "🔴")
                    lines.append(
                        f"  {icon} {item['tag']} "
                        f"（avg: {item['avg_score']:.1f}/5, "
                        f"做了{item['total_attempts']}题）"
                    )

            if not has_data:
                return "暂无练习记录，开始刷题后这里会显示你的掌握情况。"

            # 推荐弱点
            weak = [i["tag"] for i in by_level.get("novice", []) + by_level.get("learning", [])]
            if weak:
                lines.append(f"\n💡 建议优先复习: {', '.join(weak[:3])}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"MasteryReporter 异常: {e}")
            return f"报告生成失败: {str(e)}"


# ==============================================================================
# 7. 简历分析工具 (ResumeAnalysisTool) —— 升级为 LLM 提取
# ==============================================================================

class ResumeAnalysisTool(Tool):
    """分析用户简历，提取核心技术栈标签和经验等级，并更新用户画像。"""

    def __init__(self):
        super().__init__(
            name="analyze_resume",
            description="分析用户简历，提取技术栈、经验等级，并保存用户画像。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string", required=True),
            ToolParameter(name="resume_text", type="string",
                          description="简历原文", required=True),
            ToolParameter(name="target_company", type="string",
                          description="目标公司", required=False),
            ToolParameter(name="target_position", type="string",
                          description="目标岗位", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        resume_text = parameters.get("resume_text", "")
        target_company = parameters.get("target_company", "")
        target_position = parameters.get("target_position", "")

        if not resume_text.strip():
            return "❌ 简历内容为空"

        # 使用规则提取（快速）
        common_tech = [
            "Java", "Python", "Go", "C++", "JavaScript", "TypeScript",
            "Redis", "MySQL", "MongoDB", "PostgreSQL", "Elasticsearch",
            "Spring", "SpringBoot", "MyBatis", "Kafka", "RocketMQ",
            "Docker", "Kubernetes", "K8s", "Nginx", "Linux",
            "Hadoop", "Spark", "Flink", "Hive", "HBase",
            "Vue", "React", "Node.js", "Git", "CI/CD",
            "微服务", "分布式", "高并发", "设计模式"
        ]
        tech_stack = [t for t in common_tech if t.lower() in resume_text.lower()]

        # 经验等级判断（简单规则）
        experience_level = "junior"
        if any(kw in resume_text for kw in ["5年", "6年", "7年", "8年", "9年", "10年", "资深", "专家"]):
            experience_level = "senior"
        elif any(kw in resume_text for kw in ["3年", "4年", "中级", "P6", "P7"]):
            experience_level = "mid"

        # 保存用户画像
        try:
            sqlite_service.upsert_user_profile(
                user_id=user_id,
                resume_text=resume_text,
                tech_stack=tech_stack,
                target_company=target_company or None,
                target_position=target_position or None,
                experience_level=experience_level
            )
        except Exception as e:
            logger.warning(f"保存用户画像失败: {e}")

        result = f"✅ 简历分析完成\n"
        result += f"📌 提取技术栈（{len(tech_stack)}项）: {', '.join(tech_stack[:10]) or '通用技能'}\n"
        result += f"🎯 经验等级: {experience_level}\n"
        if target_company:
            result += f"🏢 目标公司: {target_company}\n"
        if target_position:
            result += f"💼 目标岗位: {target_position}"
        return result


# ==============================================================================
# 8. 面试评估工具 (InterviewEvaluator)
# ==============================================================================

class InterviewEvaluator(Tool):
    """生成本次面试/练习的评估报告，包含得分统计和薄弱点分析。"""

    def __init__(self):
        super().__init__(
            name="generate_evaluation",
            description="生成本次面试或练习的评估报告，统计得分并分析薄弱点。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string", required=True),
            ToolParameter(name="session_id", type="string",
                          description="指定 session ID，不填则统计最近10条记录", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        session_id = parameters.get("session_id", "")

        if not user_id:
            return "❌ 缺少 user_id"

        try:
            records = sqlite_service.get_study_history(user_id, limit=10)
            if session_id:
                records = [r for r in records if r.get("session_id") == session_id]

            if not records:
                return "暂无面试记录，开始练习后这里会显示评估报告。"

            total = len(records)
            avg_score = sum(r["score"] for r in records) / total
            excellent = sum(1 for r in records if r["score"] >= 4)
            needs_work = sum(1 for r in records if r["score"] < 3)

            # 统计薄弱标签
            weak_tags_count: Dict[str, int] = {}
            for r in records:
                if r["score"] < 3:
                    tags = json.loads(r.get("topic_tags") or "[]")
                    for t in tags:
                        weak_tags_count[t] = weak_tags_count.get(t, 0) + 1

            weak_sorted = sorted(weak_tags_count.items(), key=lambda x: x[1], reverse=True)

            lines = [
                "📋 **面试评估报告**\n",
                f"本次共回答 {total} 道题",
                f"平均分: {avg_score:.1f}/5.0",
                f"优秀（≥4分）: {excellent} 题",
                f"需改进（<3分）: {needs_work} 题\n",
            ]

            if avg_score >= 4.0:
                lines.append("🏆 总体表现优秀！继续保持。")
            elif avg_score >= 3.0:
                lines.append("📈 总体表现良好，还有提升空间。")
            else:
                lines.append("📚 基础需要加强，建议多复习薄弱点。")

            if weak_sorted:
                lines.append(f"\n⚠️ 薄弱知识点（需重点复习）：")
                for tag, cnt in weak_sorted[:5]:
                    lines.append(f"  • {tag}（失误 {cnt} 次）")

            # 关闭 session
            if session_id:
                sqlite_service.close_session(
                    session_id=session_id,
                    ai_summary="\n".join(lines),
                    weak_tags=[t for t, _ in weak_sorted[:5]]
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"InterviewEvaluator 异常: {e}")
            return f"评估报告生成失败: {str(e)}"


# ==============================================================================
# 9. 知识补强推荐（KnowledgeRecommender）
# 薄弱标签 → 推荐学习章节 + 列出近期错题和遗漏点
# ==============================================================================

class KnowledgeRecommender(Tool):
    """
    知识补强推荐工具。
    针对用户掌握薄弱的技术标签，自动：
    1. 列出近期在该知识点上答错的题目及 AI 反馈中的遗漏/记错点
    2. 推荐对应的学习资源（章节、文章、视频链接）
    """

    def __init__(self):
        super().__init__(
            name="get_knowledge_recommendation",
            description=(
                "针对用户薄弱的技术标签，推荐相关学习章节，"
                "并列出近期该知识块的错题和遗漏点。"
                "当用户某个标签连续多次得分低（≤2分）时调用。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="user_id", type="string",
                          description="用户ID", required=True),
            ToolParameter(name="tags", type="array",
                          description="需要补强的技术标签列表，如 [\"Redis\", \"分布式\"]",
                          required=True),
            ToolParameter(name="max_resources", type="integer",
                          description="每个标签最多推荐几个资源，默认2", required=False),
            ToolParameter(name="max_mistakes", type="integer",
                          description="最多展示几道错题，默认3", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        user_id = parameters.get("user_id", "")
        tags = parameters.get("tags") or []
        max_resources = int(parameters.get("max_resources", 2))
        max_mistakes = int(parameters.get("max_mistakes", 3))

        if not user_id:
            return "❌ 缺少 user_id"
        if not tags:
            return "❌ 请指定需要补强的标签列表"

        try:
            lines = [f"📚 **知识补强推荐报告**\n"]
            lines.append(f"针对薄弱标签：{', '.join(tags)}\n")

            # ── Part 1：近期错题 + 遗漏点 ──
            mistakes = sqlite_service.get_weak_study_records(
                user_id=user_id, tags=tags, limit=max_mistakes
            )
            if mistakes:
                lines.append("## ❌ 近期这块的错题与遗漏点\n")
                for idx, rec in enumerate(mistakes, 1):
                    q_text = (rec.get("question_text") or "（题目未找到）")[:80]
                    score = rec.get("score", "?")
                    feedback = rec.get("ai_feedback") or ""
                    studied_at = (rec.get("studied_at") or "")[:10]

                    lines.append(f"**{idx}. {q_text}...**")
                    lines.append(f"   得分：{score}/5  |  答题日期：{studied_at}")

                    # 提取 AI 反馈中的遗漏/记错信息
                    if feedback:
                        missed_points = _extract_missed_points(feedback)
                        if missed_points:
                            lines.append(f"   🔍 遗漏/记错的点：")
                            for pt in missed_points:
                                lines.append(f"      • {pt}")
                    lines.append("")
            else:
                lines.append("## ✅ 近期没有该知识块的错题记录\n")

            # ── Part 2：推荐学习资源 ──
            lines.append("## 📖 推荐学习章节\n")
            resources = sqlite_service.get_resources_by_tags(tags, limit=max_resources * len(tags))

            if not resources:
                lines.append("暂无匹配的推荐资源，可以通过「添加资源」功能手动添加。")
            else:
                # 按 tag 分组展示
                shown_ids = set()
                for tag in tags:
                    tag_resources = [
                        r for r in resources
                        if tag in r.get("tags", []) and r["resource_id"] not in shown_ids
                    ][:max_resources]
                    if not tag_resources:
                        continue
                    lines.append(f"**{tag} 相关资源：**")
                    for res in tag_resources:
                        shown_ids.add(res["resource_id"])
                        url = res.get("url") or "暂无链接"
                        desc = (res.get("description") or "")[:80]
                        lines.append(f"  📌 [{res['title']}]({url})")
                        if desc:
                            lines.append(f"     > {desc}")
                    lines.append("")

            # ── Part 3：复习建议 ──
            lines.append("## 💡 复习建议\n")
            if mistakes:
                lines.append(
                    f"建议先阅读上方推荐章节，重点看遗漏的知识点，"
                    f"然后通过「开始练习」重新练习这 {len(mistakes)} 道题。"
                )
            lines.append("可以对重要概念使用「记个笔记」功能，帮助记忆。")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"KnowledgeRecommender 异常: {e}")
            return f"推荐报告生成失败: {str(e)}"


def _extract_missed_points(feedback: str) -> List[str]:
    """
    从 AI 反馈文本中提取关键的遗漏/记错点。
    策略：按句号/换行切割，筛选包含「遗漏」「未提到」「忘记」「错误」「缺少」
    「没有说」「没有提」关键词的句子。
    """
    if not feedback:
        return []

    # 切割成句子
    import re
    sentences = re.split(r'[。\n；;]', feedback)
    miss_keywords = ["遗漏", "未提到", "未提及", "忘记", "没有提", "没有说",
                     "记错", "错误", "缺少", "缺乏", "不完整", "不足", "没有涉及"]
    missed = []
    for s in sentences:
        s = s.strip()
        if len(s) < 5:
            continue
        if any(kw in s for kw in miss_keywords):
            # 截取 60 字以内
            missed.append(s[:60] + ("..." if len(s) > 60 else ""))
        if len(missed) >= 4:
            break
    return missed
