"""
修复脚本：将有正文但状态是"待抓取"的记录更新为"已抓取"
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    load_dotenv(dotenv_path=str(_env_file), override=True)

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.database.db_manager import DatabaseManager

def fix_post_status():
    db = DatabaseManager()
    
    # 查询有正文但状态是待抓取的记录
    query = """
    SELECT id, title, LENGTH(content) as content_len, status, extraction_status
    FROM posts 
    WHERE status = '待抓取' 
      AND content IS NOT NULL 
      AND LENGTH(TRIM(content)) > 50
    ORDER BY id DESC
    """
    
    results = db.execute_query(query)
    print(f"找到 {len(results)} 条需要修复的记录\n")
    
    if not results:
        print("没有需要修复的记录")
        return
    
    # 显示前10条
    print("前10条记录：")
    for i, row in enumerate(results[:10], 1):
        print(f"{i}. ID={row[0]}, 标题={row[1][:40]}..., 正文长度={row[2]}, 状态={row[3]}, 提取状态={row[4]}")
    
    print(f"\n共 {len(results)} 条记录")
    
    # 询问是否修复
    confirm = input("\n是否将这些记录的状态更新为'已抓取'？(y/n): ")
    if confirm.lower() != 'y':
        print("取消操作")
        return
    
    # 批量更新
    update_query = """
    UPDATE posts 
    SET status = '已抓取',
        updated_at = CURRENT_TIMESTAMP
    WHERE status = '待抓取' 
      AND content IS NOT NULL 
      AND LENGTH(TRIM(content)) > 50
    """
    
    db.execute_update(update_query)
    print(f"\n✅ 已更新 {len(results)} 条记录的状态为'已抓取'")
    
    # 验证
    verify_query = """
    SELECT COUNT(*) 
    FROM posts 
    WHERE status = '待抓取' 
      AND content IS NOT NULL 
      AND LENGTH(TRIM(content)) > 50
    """
    remaining = db.execute_query(verify_query)[0][0]
    print(f"剩余待修复记录：{remaining} 条")

if __name__ == "__main__":
    fix_post_status()
