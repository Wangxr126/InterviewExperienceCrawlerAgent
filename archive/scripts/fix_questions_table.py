"""
修复 questions 表结构：将 q_id 从 INTEGER 改为 TEXT (UUID)

问题：
1. 数据库表定义：q_id INTEGER PRIMARY KEY AUTOINCREMENT
2. 代码生成：q_id = str(uuid.uuid4())  # TEXT 类型
3. 结果：类型不匹配导致插入失败

解决方案：
修改表结构，将 q_id 改为 TEXT 类型，使用 UUID 作为主键
"""
import sqlite3
from pathlib import Path

# 数据库路径
db_path = Path(r"e:\Agent\AgentProject\wxr_agent\backend\data\interview_agent.db")

if not db_path.exists():
    print(f"[WARN] 数据库文件不存在: {db_path}")
    print("首次运行时会自动创建，无需手动修复")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查当前表结构
cursor.execute("PRAGMA table_info(questions)")
columns = cursor.fetchall()
print("\n当前 questions 表结构:")
for col in columns:
    print(f"  {col[1]}: {col[2]} (PK={col[5]})")

# 检查 q_id 类型
q_id_type = None
for col in columns:
    if col[1] == 'q_id':
        q_id_type = col[2]
        break

if q_id_type == 'TEXT':
    print("\n[OK] q_id 已经是 TEXT 类型，无需修复")
    conn.close()
    exit(0)

print(f"\n[WARN] q_id 当前类型: {q_id_type}，需要改为 TEXT")

# 检查是否有数据
cursor.execute("SELECT COUNT(*) FROM questions")
count = cursor.fetchone()[0]
print(f"当前题目数量: {count}")

if count > 0:
    response = input(f"\n表中有 {count} 条数据，是否继续修复？(yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("已取消")
        conn.close()
        exit(0)

print("\n开始修复...")

# 备份旧表
cursor.execute("ALTER TABLE questions RENAME TO questions_old")
print("[1/5] 已备份旧表为 questions_old")

# 创建新表（q_id 为 TEXT）
cursor.execute("""
    CREATE TABLE questions (
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
""")
print("[2/5] 已创建新表（q_id 为 TEXT）")

# 迁移数据（如果有）
if count > 0:
    cursor.execute("""
        INSERT INTO questions 
        SELECT 
            'Q' || CAST(q_id AS TEXT) as q_id,  -- 将旧的整数 ID 转为 'Q1', 'Q2' 格式
            question_text, answer_text, difficulty, question_type,
            source_platform, source_url, company, position, business_line,
            topic_tags, extraction_source, created_at, updated_at
        FROM questions_old
    """)
    print(f"[3/5] 已迁移 {count} 条数据")
else:
    print("[3/5] 无数据需要迁移")

# 删除旧表
cursor.execute("DROP TABLE questions_old")
print("[4/5] 已删除旧表")

conn.commit()
print("[5/5] 已提交更改")

# 验证
cursor.execute("PRAGMA table_info(questions)")
columns = cursor.fetchall()
print("\n修复后的 questions 表结构:")
for col in columns:
    print(f"  {col[1]}: {col[2]} (PK={col[5]})")

cursor.execute("SELECT COUNT(*) FROM questions")
new_count = cursor.fetchone()[0]
print(f"\n题目数量: {new_count}")

conn.close()
print("\n[OK] 修复完成！")
