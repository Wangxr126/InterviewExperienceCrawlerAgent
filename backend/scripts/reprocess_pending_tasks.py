"""
列出 pending 状态的任务（需 OCR 识别图片内容）
运行：python -m backend.scripts.reprocess_pending_tasks
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

import json
from backend.config.config import settings

def main():
    import sqlite3
    db_path = settings.sqlite_db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT task_id, post_title, source_url, image_paths, raw_content
        FROM crawl_tasks 
        WHERE status = 'pending'
        ORDER BY id DESC
    """)
    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        print("✅ 没有待处理的任务")
        return

    print(f"找到 {len(tasks)} 个待处理的任务：\n")
    for i, task in enumerate(tasks, 1):
        task_id = task['task_id']
        title = task['post_title']
        url = task['source_url']
        image_paths = json.loads(task['image_paths'] or '[]')
        content_len = len(task['raw_content'] or '')
        print(f"{i}. {title}")
        print(f"   Task ID: {task_id}")
        print(f"   URL: {url}")
        print(f"   正文长度: {content_len} 字符")
        print(f"   图片数量: {len(image_paths)}")
        print()

    print("=" * 80)
    print("这些任务的正文内容很短，需要通过 OCR 识别图片内容。")
    print("请在前端点击「开始提取」按钮，系统会自动：")
    print("  1. 检测到正文过短")
    print("  2. 自动调用 OCR 识别图片")
    print("  3. 从图片中提取面试题")
    print("  4. 更新状态为 'done'")
    print("=" * 80)

if __name__ == "__main__":
    main()
