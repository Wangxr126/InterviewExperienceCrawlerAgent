"""
数据库迁移脚本：将 extract_duration_sec 转换为 extract_duration_min（已归档，一次性）
"""
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.config.config import settings

def migrate():
    db_path = settings.sqlite_db_path
    print(f"📂 数据库路径: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cols = [r[1] for r in cursor.execute('PRAGMA table_info(crawl_tasks)').fetchall()]
        print(f"当前列: {', '.join(cols)}")
        
        if 'extract_duration_min' not in cols:
            print("\n🔧 添加 extract_duration_min 列...")
            cursor.execute('ALTER TABLE crawl_tasks ADD COLUMN extract_duration_min REAL')
            print("🔄 转换数据从秒到分钟...")
            cursor.execute('''
                UPDATE crawl_tasks 
                SET extract_duration_min = extract_duration_sec / 60.0 
                WHERE extract_duration_sec IS NOT NULL
            ''')
            affected = cursor.rowcount
            print(f"✅ 已转换 {affected} 条记录")
            conn.commit()
        else:
            print("⚠️ extract_duration_min 列已存在，跳过迁移")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
