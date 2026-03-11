"""
数据库迁移脚本：将 extract_duration_sec 转换为 extract_duration_min
"""
import sqlite3
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config.config import settings

def migrate():
    db_path = settings.sqlite_db_path
    print(f"📂 数据库路径: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. 检查当前列
        cols = [r[1] for r in cursor.execute('PRAGMA table_info(crawl_tasks)').fetchall()]
        print(f"当前列: {', '.join(cols)}")
        
        if 'extract_duration_min' not in cols:
            # 2. 添加新列
            print("\n🔧 添加 extract_duration_min 列...")
            cursor.execute('ALTER TABLE crawl_tasks ADD COLUMN extract_duration_min REAL')
            
            # 3. 转换数据
            print("🔄 转换数据从秒到分钟...")
            cursor.execute('''
                UPDATE crawl_tasks 
                SET extract_duration_min = extract_duration_sec / 60.0 
                WHERE extract_duration_sec IS NOT NULL
            ''')
            affected = cursor.rowcount
            print(f"✅ 已转换 {affected} 条记录")
            
            # 4. 统计
            cursor.execute('SELECT COUNT(*) FROM crawl_tasks WHERE extract_duration_min IS NOT NULL')
            count = cursor.fetchone()[0]
            print(f"📊 共有 {count} 条记录包含耗时数据（分钟）")
            
            # 5. 显示示例数据
            cursor.execute('''
                SELECT task_id, post_title, extract_duration_sec, extract_duration_min 
                FROM crawl_tasks 
                WHERE extract_duration_min IS NOT NULL 
                LIMIT 5
            ''')
            print("\n📋 示例数据（前5条）:")
            for row in cursor.fetchall():
                print(f"  {row[1][:30]:30s} | {row[2]:6.1f}s -> {row[3]:6.2f}min")
            
            conn.commit()
            print("\n✅ 数据迁移完成！")
        else:
            print("⚠️ extract_duration_min 列已存在，跳过迁移")
            
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
