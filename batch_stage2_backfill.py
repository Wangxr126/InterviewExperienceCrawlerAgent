"""
批量对无Markdown答案的老题目执行Stage2回填。
按 source_url 分组，每组调用 enrich_task_stage2。

用法：
    conda activate NewCoderAgent
    python batch_stage2_backfill.py [--limit 50] [--dry-run]
"""
import argparse
import importlib
import os
import sqlite3
import sys
import time
from collections import defaultdict
from dotenv import load_dotenv

sys.path.insert(0, 'e:/Agent/AgentProject/wxr_agent')

# 强制重新加载 .env，覆盖进程启动时的缓存
load_dotenv('e:/Agent/AgentProject/wxr_agent/.env', override=True)

import backend.config.config as _cfg_mod
importlib.reload(_cfg_mod)
from backend.config.config import settings
from backend.services.crawler.stage2_enrich_service import enrich_task_stage2

DB_PATH = str(settings.sqlite_db_path)


def get_urls_needing_stage2(limit: int = None):
    """找出有纯文本答案（无Markdown）或无答案的题目所属source_url，并找对应task_id"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    curs = conn.cursor()

    # 找需要回填的题目：无答案 OR 答案不含Markdown特征
    sql = """
        SELECT DISTINCT q.source_url
        FROM questions q
        WHERE q.source_url IS NOT NULL AND q.source_url != ''
          AND (
              q.answer_text IS NULL OR q.answer_text = ''
              OR (
                  q.answer_text NOT LIKE '%**%'
                  AND q.answer_text NOT LIKE '%' || char(10) || '%'
              )
          )
        ORDER BY q.source_url
    """
    if limit:
        sql += f" LIMIT {limit}"

    urls = [r['source_url'] for r in curs.execute(sql).fetchall()]

    # 为每个url找task_id
    result = []
    for url in urls:
        row = curs.execute(
            "SELECT task_id FROM crawl_tasks WHERE source_url = ? LIMIT 1",
            (url,)
        ).fetchone()
        if row:
            result.append((url, row['task_id']))
        else:
            # 无task记录则跳过（enrich_task_stage2 需要task_id）
            pass

    conn.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个URL（默认全部）')
    parser.add_argument('--dry-run', action='store_true', help='只列出待处理URL，不实际调用Stage2')
    parser.add_argument('--sleep', type=float, default=2.0, help='每次调用间隔秒数（避免限流）')
    args = parser.parse_args()

    items = get_urls_needing_stage2(limit=args.limit)
    print(f'待回填URL数: {len(items)}')
    if not items:
        print('无需回填，退出。')
        return

    if args.dry_run:
        for url, task_id in items:
            print(f'  task_id={task_id} | {url[:80]}')
        return

    ok_count = 0
    fail_count = 0
    for i, (url, task_id) in enumerate(items):
        print(f'[{i+1}/{len(items)}] task_id={task_id} | {url[:70]}')
        try:
            result = enrich_task_stage2(task_id)
            if result.get('ok'):
                ok_count += 1
                print(f'  ✓ {result["message"]}')
            else:
                fail_count += 1
                print(f'  ✗ {result["message"]}')
        except Exception as e:
            fail_count += 1
            print(f'  ✗ 异常: {e}')

        if i + 1 < len(items):
            time.sleep(args.sleep)

    print(f'\n完成: 成功={ok_count}, 失败={fail_count}')


if __name__ == '__main__':
    main()
