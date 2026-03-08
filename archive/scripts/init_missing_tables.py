"""
手动初始化缺失的数据库表
"""
import sqlite3
import sys

db_path = 'backend/data/local_data.db'

ddl_statements = [
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
    """
]

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("开始创建缺失的表...")
    for i, ddl in enumerate(ddl_statements, 1):
        cursor.execute(ddl)
        print(f"  [{i}/{len(ddl_statements)}] 执行成功")
    
    conn.commit()
    print("\n✓ 所有表创建成功！")
    
    # 验证表是否创建成功
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n当前数据库中的表 ({len(tables)} 个):")
    for table in tables:
        print(f"  - {table}")
    
    conn.close()
    
except Exception as e:
    print(f"\n✗ 错误: {e}", file=sys.stderr)
    sys.exit(1)
