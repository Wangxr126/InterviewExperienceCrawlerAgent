"""
SQLite 服务层 v2.0
职责：存储所有结构化数据（用户数据、学习记录、遗忘曲线参数、笔记等）
对应四层记忆：
  - Working Memory  → interview_sessions.conversation_history
  - Episodic Memory → study_records + interview_sessions
  - Semantic Memory → user_profiles + user_tag_mastery
"""
from backend.utils.time_utils import now_beijing, now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import sqlite3
import logging
import json
import uuid
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from backend.config.config import settings

logger = logging.getLogger(__name__)


class SqliteService:
    def __init__(self):
        self.db_path = settings.sqlite_db_path
        import pathlib
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ===========================================================
    # 初始化所有表
    # ===========================================================
    def _init_tables(self):
        ddl_statements = [
            # ── 题目元数据补充表（与 Neo4j 双写，支持结构化过滤）──
            """
            CREATE TABLE IF NOT EXISTS questions (
                q_id            TEXT PRIMARY KEY,
                question_text   TEXT NOT NULL,
                answer_text     TEXT,
                difficulty      TEXT DEFAULT 'medium',
                question_type   TEXT DEFAULT '技术题',
                source_platform TEXT,
                source_url      TEXT,
                company         TEXT,
                position        TEXT,
                business_line   TEXT,
                topic_tags      TEXT DEFAULT '[]',
                extraction_source TEXT DEFAULT 'content',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 用户画像（语义记忆层）──
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id           TEXT PRIMARY KEY,
                resume_text       TEXT,
                tech_stack        TEXT DEFAULT '[]',
                target_company    TEXT,
                target_position   TEXT,
                experience_level  TEXT DEFAULT 'junior',
                preferred_topics  TEXT DEFAULT '[]',
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 标签掌握度（语义记忆层，推荐引擎核心数据）──
            """
            CREATE TABLE IF NOT EXISTS user_tag_mastery (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT NOT NULL,
                tag             TEXT NOT NULL,
                total_attempts  INTEGER DEFAULT 0,
                correct_count   INTEGER DEFAULT 0,
                avg_score       REAL DEFAULT 0.0,
                mastery_level   TEXT DEFAULT 'novice',
                last_practiced  DATETIME,
                last_updated    DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, tag)
            )
            """,
            # ── 做题记录，含 SM-2 遗忘曲线字段（情景记忆层）──
            """
            CREATE TABLE IF NOT EXISTS study_records (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          TEXT NOT NULL,
                question_id      TEXT NOT NULL,
                session_id       TEXT,
                score            INTEGER DEFAULT 0,
                user_answer      TEXT,
                ai_feedback      TEXT,
                easiness_factor  REAL DEFAULT 2.5,
                repetitions      INTEGER DEFAULT 0,
                interval_days    INTEGER DEFAULT 1,
                next_review_at   DATETIME,
                studied_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 面试会话（情景记忆层）──
            """
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id            TEXT UNIQUE NOT NULL,
                user_id               TEXT NOT NULL,
                session_type          TEXT DEFAULT 'practice',
                topic_focus           TEXT,
                target_company        TEXT,
                conversation_history  TEXT DEFAULT '[]',
                start_time            DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time              DATETIME,
                total_questions       INTEGER DEFAULT 0,
                avg_score             REAL DEFAULT 0.0,
                ai_summary            TEXT,
                weak_tags             TEXT DEFAULT '[]'
            )
            """,
            # ── 用户笔记（Note 工具）──
            """
            CREATE TABLE IF NOT EXISTS user_notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id     TEXT UNIQUE NOT NULL,
                user_id     TEXT NOT NULL,
                question_id TEXT,
                title       TEXT,
                content     TEXT NOT NULL,
                tags        TEXT DEFAULT '[]',
                note_type   TEXT DEFAULT 'concept',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 爬取日志（扩展版）──
            """
            CREATE TABLE IF NOT EXISTS crawl_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                url                 TEXT NOT NULL,
                status              TEXT,
                title               TEXT,
                source_platform     TEXT,
                company             TEXT,
                position            TEXT,
                questions_extracted INTEGER DEFAULT 0,
                crawled_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 入库日志 ──
            """
            CREATE TABLE IF NOT EXISTS ingestion_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                source_url  TEXT,
                tags        TEXT DEFAULT '[]',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 知识学习资源（章节推荐用）──
            """
            CREATE TABLE IF NOT EXISTS knowledge_resources (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id   TEXT UNIQUE NOT NULL,
                title         TEXT NOT NULL,
                url           TEXT,
                description   TEXT,
                tags          TEXT DEFAULT '[]',
                resource_type TEXT DEFAULT 'article',
                source        TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # ── 微调样本表 ──
            """
            CREATE TABLE IF NOT EXISTS finetune_samples (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                content         TEXT NOT NULL,
                title           TEXT,
                source_url      TEXT,
                llm_raw         TEXT,
                assist_output   TEXT,
                final_output    TEXT,
                is_modified     INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'pending',
                created_at      TEXT NOT NULL,
                labeled_at      TEXT
            )
            """,
            # ── 爬虫任务队列（去重 + 状态追踪）──
            # 含：原始链接、标题、正文、图片相对路径（JSON 数组）
            # raw_content 使用 TEXT，SQLite 无长度限制（理论约 1GB），完整保存原文不截断
            """
            CREATE TABLE IF NOT EXISTS crawl_tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id         TEXT UNIQUE NOT NULL,
                source_url      TEXT NOT NULL,
                source_platform TEXT NOT NULL,
                post_title      TEXT,
                status          TEXT DEFAULT 'pending',
                company         TEXT,
                position        TEXT,
                business_line   TEXT,
                difficulty      TEXT,
                post_type       TEXT,
                raw_content     TEXT,
                image_paths     TEXT,
                questions_count INTEGER DEFAULT 0,
                error_msg       TEXT,
                discovered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at    DATETIME,
                UNIQUE(source_url)
            )
            """,
        ]

        with self._get_conn() as conn:
            for ddl in ddl_statements:
                conn.execute(ddl)
            # 迁移：为已有 crawl_tasks 表添加 image_paths 列
            cols = [r[1] for r in conn.execute("PRAGMA table_info(crawl_tasks)").fetchall()]
            if "image_paths" not in cols:
                conn.execute("ALTER TABLE crawl_tasks ADD COLUMN image_paths TEXT")
                cols = [r[1] for r in conn.execute("PRAGMA table_info(crawl_tasks)").fetchall()]
            # 迁移：为 crawl_tasks 添加 discover_keyword 列（发现该帖子时使用的搜索关键词）
            if "discover_keyword" not in cols:
                conn.execute("ALTER TABLE crawl_tasks ADD COLUMN discover_keyword TEXT")
            # 迁移：为 crawl_tasks 添加 extraction_source 列（content/image，帖子维度）
            if "extraction_source" not in cols:
                conn.execute("ALTER TABLE crawl_tasks ADD COLUMN extraction_source TEXT")
            # 迁移：为 questions 表添加 extraction_source 列（content/image）
            qcols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
            if "extraction_source" not in qcols:
                conn.execute("ALTER TABLE questions ADD COLUMN extraction_source TEXT DEFAULT 'content'")
            # 迁移：为 crawl_tasks 添加 agent_used_tool 列（MinerAgent 是否进行了工具调用）
            if "agent_used_tool" not in cols:
                conn.execute("ALTER TABLE crawl_tasks ADD COLUMN agent_used_tool INTEGER DEFAULT 0")
            # 迁移：为 crawl_tasks 添加 extract_duration_sec 列（LLM 提取耗时，秒）
            if "extract_duration_sec" not in cols:
                conn.execute("ALTER TABLE crawl_tasks ADD COLUMN extract_duration_sec REAL")
            conn.commit()
        logger.info("✅ SQLite 所有表初始化完成")
        self._seed_knowledge_resources()

    # ===========================================================
    # questions 表操作
    # ===========================================================
    
    @staticmethod
    def _clean_question_text(text: str) -> str:
        """清洗题目文本，去除开头的标号"""
        if not text:
            return text
        # 去除开头的各种标号格式：
        # 1. 数字+点：1. 2. 10. 
        # 2. 数字+括号：1) 2) (1) (2)
        # 3. 中文数字：一、二、三、
        # 4. 圆圈数字：① ② ③
        # 5. 字母：a. b. A. B.
        patterns = [
            r'^\d+[\.\)、]\s*',           # 1. 2) 3、
            r'^\(\d+\)\s*',               # (1) (2)
            r'^[一二三四五六七八九十]+[、\.]\s*',  # 一、二、
            r'^[①②③④⑤⑥⑦⑧⑨⑩]+\s*',      # ① ②
            r'^[a-zA-Z][\.\)]\s*',        # a. b) A. B)
        ]
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned)
        
        return cleaned.strip()
    
    def upsert_question(self, question_text: str, answer_text: str,
                        difficulty: str = "medium", question_type: str = "技术题",
                        source_platform: str = "", source_url: str = "",
                        company: str = "", position: str = "", business_line: str = "",
                        topic_tags: List[str] = None, extraction_source: str = "content"):
        # 清洗题目文本，去除标号
        question_text = self._clean_question_text(question_text)
        
        tags_json = json.dumps(topic_tags or [], ensure_ascii=False)
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO questions
                    (question_text, answer_text, difficulty, question_type,
                     source_platform, source_url, company, position, business_line,
                     topic_tags, extraction_source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                
            """, (question_text, answer_text, difficulty, question_type,
                  source_platform, source_url, company, position, business_line, tags_json, extraction_source))
            conn.commit()
            # 返回自动生成的 q_id
            return cursor.lastrowid

    def _build_question_conditions(self, company=None, position=None, difficulty=None,
                                      question_type=None, tags=None, source_platform=None,
                                      date_from=None, date_to=None, keyword=None):
        """构建 WHERE 条件，供 filter_questions 和 count_questions 共用"""
        conditions = []
        params = []
        if company:
            conditions.append("company LIKE ?")
            params.append(f"%{company}%")
        if position:
            conditions.append("position LIKE ?")
            params.append(f"%{position}%")
        if difficulty:
            conditions.append("difficulty = ?")
            params.append(difficulty)
        if question_type:
            conditions.append("question_type = ?")
            params.append(question_type)
        if source_platform:
            conditions.append("source_platform = ?")
            params.append(source_platform)
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)
        if keyword:
            conditions.append("question_text LIKE ?")
            params.append(f"%{keyword}%")
        if tags:
            for tag in tags:
                conditions.append("topic_tags LIKE ?")
                params.append(f'%"{tag}"%')
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    def count_questions(self, company: str = None, position: str = None,
                        difficulty: str = None, question_type: str = None,
                        tags: List[str] = None, source_platform: str = None,
                        date_from: str = None, date_to: str = None,
                        keyword: str = None) -> int:
        """统计符合条件的题目总数，用于分页"""
        where_clause, params = self._build_question_conditions(
            company=company, position=position, difficulty=difficulty,
            question_type=question_type, tags=tags, source_platform=source_platform,
            date_from=date_from, date_to=date_to, keyword=keyword
        )
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM questions WHERE {where_clause}", params
            )
            return cursor.fetchone()[0]

    def filter_questions(self, company: str = None, position: str = None,
                         difficulty: str = None, question_type: str = None,
                         tags: List[str] = None, source_platform: str = None,
                         date_from: str = None, date_to: str = None,
                         keyword: str = None, limit: int = 20, offset: int = 0,
                         sort_by: str = "created_at", sort_order: str = "desc") -> List[Dict]:
        """
        纯 SQL 过滤题目，不需要 LLM。支持按公司/岗位/难度/标签/时间/关键词过滤，支持分页和排序。
        """
        _ALLOWED_SORT_COLS = {"created_at", "difficulty", "company", "question_type", "question_text"}
        _col = sort_by if sort_by in _ALLOWED_SORT_COLS else "created_at"
        _order = "ASC" if sort_order and sort_order.lower() == "asc" else "DESC"

        where_clause, params = self._build_question_conditions(
            company=company, position=position, difficulty=difficulty,
            question_type=question_type, tags=tags, source_platform=source_platform,
            date_from=date_from, date_to=date_to, keyword=keyword
        )
        params.extend([limit, offset])

        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM questions WHERE {where_clause} ORDER BY {_col} {_order} LIMIT ? OFFSET ?",
                params
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_questions_by_source_url(self, source_url: str) -> List[Dict]:
        """按帖子 source_url 查询已提取的题目列表"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM questions WHERE source_url = ? ORDER BY created_at",
                (source_url,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ===========================================================
    # user_profiles 表操作
    # ===========================================================
    def upsert_user_profile(self, user_id: str, resume_text: str = None,
                            tech_stack: List[str] = None, target_company: str = None,
                            target_position: str = None, experience_level: str = None,
                            preferred_topics: List[str] = None):
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()

            if existing:
                updates, vals = [], []
                if resume_text is not None:
                    updates.append("resume_text = ?"); vals.append(resume_text)
                if tech_stack is not None:
                    updates.append("tech_stack = ?"); vals.append(json.dumps(tech_stack, ensure_ascii=False))
                if target_company is not None:
                    updates.append("target_company = ?"); vals.append(target_company)
                if target_position is not None:
                    updates.append("target_position = ?"); vals.append(target_position)
                if experience_level is not None:
                    updates.append("experience_level = ?"); vals.append(experience_level)
                if preferred_topics is not None:
                    updates.append("preferred_topics = ?"); vals.append(json.dumps(preferred_topics, ensure_ascii=False))
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    vals.append(user_id)
                    conn.execute(f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?", vals)
            else:
                conn.execute("""
                    INSERT INTO user_profiles
                        (user_id, resume_text, tech_stack, target_company, target_position,
                         experience_level, preferred_topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    resume_text or "",
                    json.dumps(tech_stack or [], ensure_ascii=False),
                    target_company or "",
                    target_position or "",
                    experience_level or "junior",
                    json.dumps(preferred_topics or [], ensure_ascii=False)
                ))
            conn.commit()

    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            profile = dict(row)
            for key in ("tech_stack", "preferred_topics"):
                profile[key] = json.loads(profile.get(key) or "[]")
            return profile

    # ===========================================================
    # user_tag_mastery 表操作
    # ===========================================================
    def _compute_mastery_level(self, avg_score: float, total_attempts: int, correct_count: int) -> str:
        if total_attempts < 3 or avg_score < 2.0:
            return "novice"
        elif avg_score < 3.5:
            return "learning"
        elif avg_score < 4.5:
            return "proficient"
        else:
            return "expert" if correct_count >= 5 else "proficient"

    def update_tag_mastery(self, user_id: str, tags: List[str], score: int):
        """每次做题后调用，更新相关标签的掌握度"""
        with self._get_conn() as conn:
            for tag in tags:
                existing = conn.execute(
                    "SELECT * FROM user_tag_mastery WHERE user_id = ? AND tag = ?",
                    (user_id, tag)
                ).fetchone()

                if existing:
                    row = dict(existing)
                    total = row["total_attempts"] + 1
                    correct = row["correct_count"] + (1 if score >= 3 else 0)
                    avg = ((row["avg_score"] * row["total_attempts"]) + score) / total
                    level = self._compute_mastery_level(avg, total, correct)
                    conn.execute("""
                        UPDATE user_tag_mastery
                        SET total_attempts = ?, correct_count = ?, avg_score = ?,
                            mastery_level = ?, last_practiced = CURRENT_TIMESTAMP,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE user_id = ? AND tag = ?
                    """, (total, correct, avg, level, user_id, tag))
                else:
                    avg = float(score)
                    level = self._compute_mastery_level(avg, 1, 1 if score >= 3 else 0)
                    conn.execute("""
                        INSERT INTO user_tag_mastery
                            (user_id, tag, total_attempts, correct_count, avg_score,
                             mastery_level, last_practiced)
                        VALUES (?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (user_id, tag, 1 if score >= 3 else 0, avg, level))
            conn.commit()

    def get_tag_mastery(self, user_id: str, tags: List[str] = None) -> List[Dict]:
        with self._get_conn() as conn:
            if tags:
                placeholders = ",".join("?" * len(tags))
                cursor = conn.execute(
                    f"SELECT * FROM user_tag_mastery WHERE user_id = ? AND tag IN ({placeholders}) ORDER BY avg_score ASC",
                    [user_id] + tags
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM user_tag_mastery WHERE user_id = ? ORDER BY avg_score ASC",
                    (user_id,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_weak_tags(self, user_id: str, level_filter: List[str] = None) -> List[Dict]:
        """获取薄弱标签，默认返回 novice 和 learning 级别"""
        levels = level_filter or ["novice", "learning"]
        placeholders = ",".join("?" * len(levels))
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM user_tag_mastery WHERE user_id = ? AND mastery_level IN ({placeholders}) ORDER BY avg_score ASC",
                [user_id] + levels
            )
            return [dict(row) for row in cursor.fetchall()]

    # ===========================================================
    # study_records 表操作（含 SM-2 算法）
    # ===========================================================
    @staticmethod
    def compute_sm2(score: int, easiness_factor: float, repetitions: int,
                    interval_days: int) -> tuple:
        """
        SM-2 算法核心：根据用户得分更新遗忘曲线参数。
        Returns: (new_ef, new_repetitions, new_interval_days, next_review_at)
        """
        if score < 3:
            repetitions = 0
            interval_days = 1
        else:
            if repetitions == 0:
                interval_days = 1
            elif repetitions == 1:
                interval_days = 6
            else:
                interval_days = max(1, round(interval_days * easiness_factor))
            repetitions += 1

        easiness_factor = max(
            1.3,
            easiness_factor + 0.1 - (5 - score) * (0.08 + (5 - score) * 0.02)
        )
        next_review_at = now_beijing_str() + timedelta(days=interval_days)
        return easiness_factor, repetitions, interval_days, next_review_at

    def add_study_record(self, user_id: str, question_id: str, score: int,
                         user_answer: str = "", ai_feedback: str = "",
                         session_id: str = "") -> Dict:
        """
        记录一次做题，自动计算 SM-2 参数，更新标签掌握度。
        Returns: SM-2 更新结果
        """
        # 读取该题的历史记录（取最新一条获取当前 SM-2 状态）
        with self._get_conn() as conn:
            last = conn.execute("""
                SELECT easiness_factor, repetitions, interval_days
                FROM study_records
                WHERE user_id = ? AND question_id = ?
                ORDER BY studied_at DESC LIMIT 1
            """, (user_id, question_id)).fetchone()

        ef = last["easiness_factor"] if last else 2.5
        reps = last["repetitions"] if last else 0
        interval = last["interval_days"] if last else 1

        new_ef, new_reps, new_interval, next_review = self.compute_sm2(score, ef, reps, interval)

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO study_records
                    (user_id, question_id, session_id, score, user_answer, ai_feedback,
                     easiness_factor, repetitions, interval_days, next_review_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, question_id, session_id, score, user_answer, ai_feedback,
                  new_ef, new_reps, new_interval, next_review.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

        # 查找该题的 tags 并更新掌握度
        with self._get_conn() as conn:
            q_row = conn.execute("SELECT topic_tags FROM questions WHERE q_id = ?", (question_id,)).fetchone()
        if q_row:
            tags = json.loads(q_row["topic_tags"] or "[]")
            self.update_tag_mastery(user_id, tags, score)

        return {
            "easiness_factor": round(new_ef, 2),
            "repetitions": new_reps,
            "interval_days": new_interval,
            "next_review_at": next_review.strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_due_reviews(self, user_id: str, limit: int = 10) -> List[Dict]:
        """获取到期需要复习的题目（遗忘曲线到期）"""
        now = now_beijing_str("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT sr.question_id, sr.score, sr.next_review_at,
                       sr.easiness_factor, sr.repetitions, sr.interval_days,
                       q.question_text, q.answer_text, q.topic_tags,
                       q.difficulty, q.company
                FROM study_records sr
                LEFT JOIN questions q ON sr.question_id = q.q_id
                WHERE sr.user_id = ? AND sr.next_review_at <= ?
                ORDER BY sr.next_review_at ASC
                LIMIT ?
            """, (user_id, now, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_study_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取用户做题历史"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT sr.*, q.question_text, q.topic_tags
                FROM study_records sr
                LEFT JOIN questions q ON sr.question_id = q.q_id
                WHERE sr.user_id = ?
                ORDER BY sr.studied_at DESC LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # ===========================================================
    # interview_sessions 表操作
    # ===========================================================
    def create_session(self, user_id: str, session_type: str = "practice",
                       topic_focus: str = "", target_company: str = "") -> str:
        session_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO interview_sessions
                    (session_id, user_id, session_type, topic_focus, target_company)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, user_id, session_type, topic_focus, target_company))
            conn.commit()
        return session_id

    def update_session_history(self, session_id: str, role: str, content: str,
                               reasoning: str = None, max_turns: int = 50):
        """追加对话记录（含可选 reasoning，用于 LLM 思考过程）"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT conversation_history FROM interview_sessions WHERE session_id = ?",
                (session_id,)
            ).fetchone()
            if not row:
                return

            history = json.loads(row["conversation_history"] or "[]")
            msg = {"role": role, "content": content, "ts": now_beijing().isoformat()}
            if reasoning:
                msg["reasoning"] = reasoning
            history.append(msg)
            if len(history) > max_turns:
                history = history[-max_turns:]

            conn.execute(
                "UPDATE interview_sessions SET conversation_history = ? WHERE session_id = ?",
                (json.dumps(history, ensure_ascii=False), session_id)
            )
            conn.commit()

    def ensure_session_exists(self, session_id: str, user_id: str) -> bool:
        """确保 session 存在，不存在则创建。返回是否为新创建"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM interview_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row:
                return False
            conn.execute("""
                INSERT INTO interview_sessions (session_id, user_id, session_type)
                VALUES (?, ?, 'practice')
            """, (session_id, user_id))
            conn.commit()
            return True

    def get_latest_session_for_user(self, user_id: str) -> Optional[Dict]:
        """获取用户最近一次会话（含对话历史）"""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM interview_sessions
                WHERE user_id = ? ORDER BY start_time DESC LIMIT 1
            """, (user_id,)).fetchone()
            if not row:
                return None
            s = dict(row)
            s["conversation_history"] = json.loads(s.get("conversation_history") or "[]")
            s["weak_tags"] = json.loads(s.get("weak_tags") or "[]")
            return s

    def close_session(self, session_id: str, ai_summary: str = "", weak_tags: List[str] = None):
        """关闭 session，计算统计数据"""
        with self._get_conn() as conn:
            stats = conn.execute("""
                SELECT COUNT(*) as total, AVG(score) as avg_score
                FROM study_records WHERE session_id = ?
            """, (session_id,)).fetchone()

            conn.execute("""
                UPDATE interview_sessions
                SET end_time = CURRENT_TIMESTAMP,
                    total_questions = ?,
                    avg_score = ?,
                    ai_summary = ?,
                    weak_tags = ?
                WHERE session_id = ?
            """, (
                stats["total"] if stats else 0,
                round(stats["avg_score"] or 0, 2) if stats else 0,
                ai_summary,
                json.dumps(weak_tags or [], ensure_ascii=False),
                session_id
            ))
            conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM interview_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            s = dict(row)
            s["conversation_history"] = json.loads(s.get("conversation_history") or "[]")
            s["weak_tags"] = json.loads(s.get("weak_tags") or "[]")
            return s

    # ===========================================================
    # user_notes 表操作
    # ===========================================================
    def create_note(self, user_id: str, content: str, title: str = "",
                    question_id: str = None, tags: List[str] = None,
                    note_type: str = "concept") -> str:
        note_id = str(uuid.uuid4())[:8]
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO user_notes
                    (note_id, user_id, question_id, title, content, tags, note_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, user_id, question_id, title, content,
                  json.dumps(tags or [], ensure_ascii=False), note_type))
            conn.commit()
        return note_id

    def update_note(self, note_id: str, user_id: str, content: str = None,
                    title: str = None, tags: List[str] = None) -> bool:
        updates, vals = [], []
        if content is not None:
            updates.append("content = ?"); vals.append(content)
        if title is not None:
            updates.append("title = ?"); vals.append(title)
        if tags is not None:
            updates.append("tags = ?"); vals.append(json.dumps(tags, ensure_ascii=False))
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        vals.extend([note_id, user_id])
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE user_notes SET {', '.join(updates)} WHERE note_id = ? AND user_id = ?",
                vals
            )
            conn.commit()
        return True

    def delete_note(self, note_id: str, user_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_notes WHERE note_id = ? AND user_id = ?",
                (note_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_notes(self, user_id: str, tags: List[str] = None,
                  question_id: str = None, note_type: str = None,
                  keyword: str = None, limit: int = 20) -> List[Dict]:
        conditions = ["user_id = ?"]
        params = [user_id]
        if question_id:
            conditions.append("question_id = ?"); params.append(question_id)
        if note_type:
            conditions.append("note_type = ?"); params.append(note_type)
        if keyword:
            conditions.append("(title LIKE ? OR content LIKE ?)"); params.extend([f"%{keyword}%"] * 2)
        if tags:
            for t in tags:
                conditions.append("tags LIKE ?"); params.append(f'%"{t}"%')
        params.append(limit)
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM user_notes WHERE {' AND '.join(conditions)} ORDER BY updated_at DESC LIMIT ?",
                params
            )
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                r["tags"] = json.loads(r.get("tags") or "[]")
            return rows

    # ===========================================================
    # crawl_logs / ingestion_logs 操作（扩展版）
    # ===========================================================
    def log_crawl(self, url: str, status: str, title: str = "",
                  source_platform: str = "", company: str = "", position: str = ""):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO crawl_logs (url, status, title, source_platform, company, position)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url, status, title, source_platform, company, position))
            conn.commit()

    def update_crawl_questions_count(self, url: str, count: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE crawl_logs SET questions_extracted = ? WHERE url = ?",
                (count, url)
            )
            conn.commit()

    def log_ingestion(self, q_id: str, source_url: str, tags: list):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO ingestion_logs (question_id, source_url, tags) VALUES (?, ?, ?)",
                (q_id, source_url, json.dumps(tags, ensure_ascii=False))
            )
            conn.commit()

    # ===========================================================
    # 统计查询（供 MasteryReporter 使用）
    # ===========================================================
    def get_mastery_summary(self, user_id: str) -> Dict:
        """获取用户的完整掌握度摘要"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM user_tag_mastery WHERE user_id = ? ORDER BY avg_score DESC",
                (user_id,)
            ).fetchall()
            mastery_data = [dict(r) for r in rows]

            stats = conn.execute("""
                SELECT COUNT(*) as total_records,
                       AVG(score) as overall_avg,
                       SUM(CASE WHEN score >= 3 THEN 1 ELSE 0 END) as correct_count
                FROM study_records WHERE user_id = ?
            """, (user_id,)).fetchone()

        by_level = {"expert": [], "proficient": [], "learning": [], "novice": []}
        for item in mastery_data:
            level = item.get("mastery_level", "novice")
            by_level.setdefault(level, []).append(item)

        return {
            "by_level": by_level,
            "total_questions_practiced": stats["total_records"] if stats else 0,
            "overall_avg_score": round(stats["overall_avg"] or 0, 2) if stats else 0,
            "correct_rate": round(
                (stats["correct_count"] / stats["total_records"] * 100) if stats and stats["total_records"] else 0, 1
            )
        }


    # ===========================================================
    # knowledge_resources 表操作
    # ===========================================================

    def _seed_knowledge_resources(self):
        """预置常用技术学习资源（首次运行时写入，已有数据则跳过）"""
        with self._get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM knowledge_resources").fetchone()[0]
            if count > 0:
                return  # 已有数据，跳过 seed

        resources = [
            # ── Redis ──
            ("RES-Redis-001", "小林coding · Redis 持久化（RDB/AOF）",
             "https://xiaolincoding.com/redis/storage/aof.html",
             "详解 RDB 快照机制、AOF 日志追加、AOF 重写 BGREWRITEAOF 的原理与对比",
             ["Redis", "持久化", "RDB", "AOF"], "article", "小林coding"),
            ("RES-Redis-002", "小林coding · Redis 主从复制原理",
             "https://xiaolincoding.com/redis/cluster/master_slave_replication.html",
             "全量同步、增量同步、repl_backlog 环形缓冲区、心跳检测机制",
             ["Redis", "主从复制", "分布式"], "article", "小林coding"),
            ("RES-Redis-003", "小林coding · Redis 哨兵机制",
             "https://xiaolincoding.com/redis/cluster/sentinel.html",
             "哨兵选主、故障转移、脑裂问题及解决方案",
             ["Redis", "哨兵", "高可用"], "article", "小林coding"),
            ("RES-Redis-004", "JavaGuide · Redis 数据结构",
             "https://javaguide.cn/database/redis/redis-data-structures-01/",
             "String/List/Hash/Set/ZSet 底层实现（SDS/跳表/压缩列表/整数集合）",
             ["Redis", "数据结构", "跳表"], "article", "JavaGuide"),
            ("RES-Redis-005", "小林coding · Redis 缓存雪崩/穿透/击穿",
             "https://xiaolincoding.com/redis/cluster/cache_problem.html",
             "三种缓存问题的定义、产生场景和解决方案（布隆过滤器、互斥锁、逻辑过期）",
             ["Redis", "缓存", "布隆过滤器", "高并发"], "article", "小林coding"),

            # ── MySQL ──
            ("RES-MySQL-001", "小林coding · MySQL 索引原理",
             "https://xiaolincoding.com/mysql/index/index_interview.html",
             "B+树索引结构、聚簇索引 vs 非聚簇、覆盖索引、索引失效场景",
             ["MySQL", "索引", "B+树"], "article", "小林coding"),
            ("RES-MySQL-002", "小林coding · MySQL 事务与锁",
             "https://xiaolincoding.com/mysql/lock/mysql_lock.html",
             "ACID、隔离级别、MVCC、行锁/表锁/间隙锁，解决幻读的原理",
             ["MySQL", "事务", "锁", "MVCC", "隔离级别"], "article", "小林coding"),
            ("RES-MySQL-003", "小林coding · MySQL 日志（redo/undo/binlog）",
             "https://xiaolincoding.com/mysql/log/how_update.html",
             "三种日志的作用、两阶段提交、崩溃恢复流程",
             ["MySQL", "redo log", "binlog", "事务"], "article", "小林coding"),

            # ── 操作系统 ──
            ("RES-OS-001", "小林coding · 进程与线程",
             "https://xiaolincoding.com/os/4_process/process_base.html",
             "进程 vs 线程的区别、PCB、线程同步方式（互斥锁/信号量/条件变量）",
             ["操作系统", "进程", "线程", "并发"], "article", "小林coding"),
            ("RES-OS-002", "小林coding · 内存管理",
             "https://xiaolincoding.com/os/3_memory/vmem.html",
             "虚拟内存、分页机制、TLB、缺页中断、页面置换算法（LRU/LFU/Clock）",
             ["操作系统", "内存", "虚拟内存", "分页"], "article", "小林coding"),
            ("RES-OS-003", "小林coding · 死锁",
             "https://xiaolincoding.com/os/4_process/deadlock.html",
             "死锁四个必要条件、死锁检测与预防、银行家算法",
             ["操作系统", "死锁", "并发"], "article", "小林coding"),

            # ── 计算机网络 ──
            ("RES-Net-001", "小林coding · TCP 三次握手/四次挥手",
             "https://xiaolincoding.com/network/3_tcp/tcp_interview.html",
             "详解握手/挥手过程、TIME_WAIT 状态、SYN洪泛攻击、半连接队列",
             ["网络", "TCP", "三次握手", "四次挥手"], "article", "小林coding"),
            ("RES-Net-002", "小林coding · HTTP vs HTTPS",
             "https://xiaolincoding.com/network/2_http/http_interview.html",
             "HTTP/1.1/2/3 对比、HTTPS TLS握手、证书验证、数字签名原理",
             ["网络", "HTTP", "HTTPS", "TLS"], "article", "小林coding"),

            # ── Java ──
            ("RES-Java-001", "JavaGuide · Java 集合框架",
             "https://javaguide.cn/java/collection/java-collection-questions-01/",
             "HashMap/ConcurrentHashMap 原理、ArrayList vs LinkedList、红黑树扩容",
             ["Java", "HashMap", "集合", "红黑树"], "article", "JavaGuide"),
            ("RES-Java-002", "JavaGuide · JVM 内存模型与GC",
             "https://javaguide.cn/java/jvm/memory-area/",
             "堆/栈/方法区/程序计数器、Minor GC/Full GC、G1/ZGC收集器",
             ["Java", "JVM", "GC", "内存"], "article", "JavaGuide"),
            ("RES-Java-003", "JavaGuide · Java 并发编程",
             "https://javaguide.cn/java/concurrent/java-concurrent-questions-01/",
             "synchronized/volatile/ReentrantLock 原理、AQS、ThreadLocal、线程池参数",
             ["Java", "并发", "线程池", "AQS", "synchronized"], "article", "JavaGuide"),

            # ── 分布式 / 微服务 ──
            ("RES-Dist-001", "JavaGuide · 分布式事务",
             "https://javaguide.cn/distributed-system/distributed-transaction/",
             "2PC/3PC/TCC/Saga 模式、消息队列最终一致性、分布式锁（Redis/ZK）",
             ["分布式", "分布式事务", "TCC", "2PC"], "article", "JavaGuide"),
            ("RES-Dist-002", "JavaGuide · CAP 理论与 BASE",
             "https://javaguide.cn/distributed-system/theorem&algorithm/cap&base-theorem/",
             "CAP 不可能三角、BASE 理论（基本可用、软状态、最终一致性）",
             ["分布式", "CAP", "一致性"], "article", "JavaGuide"),

            # ── 消息队列 ──
            ("RES-MQ-001", "JavaGuide · Kafka 核心原理",
             "https://javaguide.cn/message-queue/kafka/kafka-questions-01/",
             "Topic/Partition/Consumer Group、消息有序性、消息丢失、重复消费",
             ["Kafka", "消息队列", "分布式"], "article", "JavaGuide"),

            # ── 算法 ──
            ("RES-Algo-001", "LeetCode · 二叉树高频题集",
             "https://leetcode.cn/problem-list/2ckc81c/",
             "前/中/后序遍历、层序BFS、最近公共祖先、二叉搜索树",
             ["算法", "二叉树", "BFS", "DFS"], "problemset", "LeetCode"),
            ("RES-Algo-002", "LeetCode · 动态规划高频题集",
             "https://leetcode.cn/problem-list/2cktkvj/",
             "背包问题、最长公共子序列、股票买卖、打家劫舍系列",
             ["算法", "动态规划", "DP"], "problemset", "LeetCode"),
            ("RES-Algo-003", "LeetCode · 滑动窗口 & 双指针",
             "https://leetcode.cn/problem-list/2ckfu3g/",
             "无重复字符的最长子串、最小覆盖子串、三数之和",
             ["算法", "滑动窗口", "双指针"], "problemset", "LeetCode"),

            # ── 系统设计 ──
            ("RES-SD-001", "System Design Primer · 缓存设计",
             "https://github.com/donnemartin/system-design-primer#cache",
             "缓存策略（Cache-Aside/Write-Through/Write-Behind）、缓存一致性",
             ["系统设计", "缓存", "Redis"], "github", "system-design-primer"),
            ("RES-SD-002", "System Design Primer · 消息队列设计",
             "https://github.com/donnemartin/system-design-primer#message-queues",
             "异步解耦、削峰填谷、消息持久化、消费者组设计",
             ["系统设计", "消息队列", "Kafka"], "github", "system-design-primer"),
        ]

        with self._get_conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO knowledge_resources
                    (resource_id, title, url, description, tags, resource_type, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (r[0], r[1], r[2], r[3],
                 json.dumps(r[4], ensure_ascii=False), r[5], r[6])
                for r in resources
            ])
            conn.commit()
        logger.info(f"✅ 知识资源库预置完成（共 {len(resources)} 条）")

    def get_resources_by_tags(self, tags: List[str], limit: int = 3) -> List[Dict]:
        """根据标签列表查找匹配的学习资源（任一标签命中即返回）"""
        if not tags:
            return []
        with self._get_conn() as conn:
            # 用 OR 逻辑：任何一个 tag 命中即可
            conditions = " OR ".join(["tags LIKE ?" for _ in tags])
            params = [f'%"{t}"%' for t in tags] + [limit]
            cursor = conn.execute(
                f"SELECT * FROM knowledge_resources WHERE {conditions} LIMIT ?",
                params
            )
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                r["tags"] = json.loads(r.get("tags") or "[]")
            return rows

    def add_knowledge_resource(self, title: str, url: str, description: str,
                                tags: List[str], resource_type: str = "article",
                                source: str = "") -> str:
        """用户手动添加学习资源"""
        resource_id = f"RES-USER-{uuid.uuid4().hex[:6].upper()}"
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO knowledge_resources
                    (resource_id, title, url, description, tags, resource_type, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (resource_id, title, url, description,
                  json.dumps(tags, ensure_ascii=False), resource_type, source))
            conn.commit()
        return resource_id

    def get_weak_study_records(self, user_id: str, tags: List[str],
                                limit: int = 5) -> List[Dict]:
        """
        获取用户在指定标签上的近期错题记录（score < 3）。
        包含题目文本和 AI 反馈，用于展示遗漏/记错的点。
        """
        if not tags:
            return []
        # 先找出这些 tag 下的 question_id
        tag_conditions = " OR ".join(["topic_tags LIKE ?" for _ in tags])
        tag_params = [f'%"{t}"%' for t in tags]

        with self._get_conn() as conn:
            cursor = conn.execute(
                f"""
                SELECT sr.question_id, sr.score, sr.user_answer, sr.ai_feedback,
                       sr.studied_at, q.question_text, q.topic_tags
                FROM study_records sr
                LEFT JOIN questions q ON sr.question_id = q.q_id
                WHERE sr.user_id = ?
                  AND sr.score < 3
                  AND ({tag_conditions})
                ORDER BY sr.studied_at DESC
                LIMIT ?
                """,
                [user_id] + tag_params + [limit]
            )
            return [dict(r) for r in cursor.fetchall()]


    # ===========================================================
    # 爬虫任务队列
    # ===========================================================

    def add_crawl_task(self, source_url: str, source_platform: str,
                       post_title: str = "", company: str = "", position: str = "",
                       business_line: str = "", difficulty: str = "", post_type: str = "",
                       discover_keyword: str = "") -> Optional[str]:
        """添加爬虫任务（URL已存在则忽略，返回 task_id；重复时返回 None）"""
        task_id = f"TASK-{uuid.uuid4().hex[:10].upper()}"
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO crawl_tasks
                        (task_id, source_url, source_platform, post_title,
                         company, position, business_line, difficulty, post_type, discover_keyword)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (task_id, source_url, source_platform, post_title,
                      company, position, business_line, difficulty, post_type, discover_keyword or ""))
                conn.commit()
            return task_id
        except Exception:
            return None  # 唯一约束冲突（已处理过的 URL）

    def get_pending_tasks(self, platform: str = None, limit: int = 20) -> List[Dict]:
        """获取待处理任务"""
        where = "WHERE status = 'pending'"
        params = []
        if platform:
            where += " AND source_platform = ?"
            params.append(platform)
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM crawl_tasks {where} ORDER BY discovered_at ASC LIMIT ?",
                params + [limit]
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_tasks_by_status(self, status: str, platform: str = None, limit: int = 100) -> List[Dict]:
        """根据状态获取任务"""
        where = "WHERE status = ?"
        params = [status]
        if platform:
            where += " AND source_platform = ?"
            params.append(platform)
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"SELECT * FROM crawl_tasks {where} ORDER BY discovered_at ASC LIMIT ?",
                params + [limit]
            )
            return [dict(r) for r in cursor.fetchall()]

    def update_task_status(self, task_id: str, status: str,
                           questions_count: int = 0, error_msg: str = "",
                           raw_content: Optional[str] = None, image_paths: Optional[List[str]] = None,
                           extraction_source: str = "", agent_used_tool: Optional[bool] = None,
                           extract_duration_sec: Optional[float] = None):
        """更新任务状态。raw_content/image_paths 为 None 时不更新该列（保留原文），避免误覆盖。
        extraction_source: content=正文提取, image=图片OCR提取（帖子维度）
        agent_used_tool: MinerAgent 是否进行了工具调用（True/False/None=不更新）
        extract_duration_sec: LLM 提取耗时（秒），None=不更新"""
        import json as _json
        sets = ["status=?", "questions_count=?", "error_msg=?", "extraction_source=?", "processed_at=CURRENT_TIMESTAMP"]
        params: list = [status, questions_count, error_msg, extraction_source or None]
        if raw_content is not None:
            sets.append("raw_content=?")
            params.append(raw_content or "")
        if image_paths is not None:
            sets.append("image_paths=?")
            params.append(_json.dumps(image_paths or [], ensure_ascii=False))
        if agent_used_tool is not None:
            sets.append("agent_used_tool=?")
            params.append(1 if agent_used_tool else 0)
        if extract_duration_sec is not None:
            sets.append("extract_duration_sec=?")
            params.append(round(extract_duration_sec, 1))
        params.append(task_id)
        with self._get_conn() as conn:
            conn.execute("UPDATE crawl_tasks SET " + ", ".join(sets) + " WHERE task_id=?", params)
            conn.commit()

    def update_task_content(self, task_id: str, post_title: str, raw_content: str,
                            image_paths: List[str] = None):
        """重抓正文后更新任务：标题、正文、图片路径，并重置为 fetched 待提取"""
        import json as _json
        img_val = _json.dumps(image_paths or [], ensure_ascii=False) if image_paths else ""
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE crawl_tasks SET post_title=?, raw_content=?, image_paths=?,
                    status='fetched', error_msg=NULL, questions_count=0,
                    extraction_source=NULL, processed_at=CURRENT_TIMESTAMP
                WHERE task_id=?
            """, (post_title or "", raw_content or "", img_val, task_id))
            conn.commit()

    def is_url_crawled(self, url: str) -> bool:
        """检查 URL 是否已爬取（已入队或已处理）"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM crawl_tasks WHERE source_url=?", (url,)
            ).fetchone()
            return row is not None

    def delete_by_source_url(self, source_url: str) -> int:
        """
        删除该链接关联的所有数据（帖子与面经无关或提取失败时调用）。
        删除：questions、ingestion_logs、crawl_tasks、crawl_logs、Neo4j 题库节点，以及 post_images 目录。
        返回删除的题目数量。
        """
        import shutil
        from pathlib import Path
        from backend.config.config import settings

        # 同步删除 Neo4j 题库中的题目节点
        try:
            from backend.services.storage.neo4j_service import neo4j_service
            neo4j_service.delete_questions_by_source_url(source_url)
        except Exception as e:
            logger.warning("Neo4j 删除题目失败（SQLite 已删除）: %s", e)

        with self._get_conn() as conn:
            # 获取 task_id 用于删除图片目录
            row = conn.execute(
                "SELECT task_id FROM crawl_tasks WHERE source_url=?", (source_url,)
            ).fetchone()
            task_id = row["task_id"] if row else None

            # 删除题目
            cur = conn.execute("DELETE FROM questions WHERE source_url=?", (source_url,))
            deleted_questions = cur.rowcount

            conn.execute("DELETE FROM ingestion_logs WHERE source_url=?", (source_url,))
            conn.execute("DELETE FROM crawl_tasks WHERE source_url=?", (source_url,))
            conn.execute("DELETE FROM crawl_logs WHERE url=?", (source_url,))
            conn.commit()

        # 删除 post_images 目录
        if task_id:
            img_dir = settings.post_images_dir / task_id
            if img_dir.exists():
                try:
                    shutil.rmtree(img_dir)
                    logger.info(f"已删除图片目录: {img_dir}")
                except Exception as e:
                    logger.warning(f"删除图片目录失败 {img_dir}: {e}")

        logger.info(f"🗑️已删除 source_url 关联数据，共 {deleted_questions} 道题目 | URL: {source_url[:80]}...")
        return deleted_questions

    def get_crawl_stats(self) -> Dict:
        """获取爬取统计"""
        with self._get_conn() as conn:
            stats = conn.execute("""
                SELECT status, COUNT(*) as cnt, SUM(questions_count) as total_questions
                FROM crawl_tasks GROUP BY status
            """).fetchall()
            result = {r["status"]: {"count": r["cnt"], "questions": r["total_questions"] or 0}
                      for r in stats}
            # 按平台的 fetched 数量（用于提取进度分平台显示）
            by_platform = conn.execute("""
                SELECT source_platform, COUNT(*) as cnt
                FROM crawl_tasks WHERE status = 'fetched'
                GROUP BY source_platform
            """).fetchall()
            result["fetched_by_platform"] = {r["source_platform"]: r["cnt"] for r in by_platform}
            return result

    def get_crawl_keywords(self) -> List[str]:
        """获取帖子记录中已有关键词列表（用于筛选下拉）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT discover_keyword FROM crawl_tasks "
                "WHERE discover_keyword IS NOT NULL AND trim(discover_keyword) != '' "
                "ORDER BY discover_keyword"
            ).fetchall()
            return [r["discover_keyword"] for r in rows]


# 单例
sqlite_service = SqliteService()
