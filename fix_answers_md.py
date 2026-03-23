"""
对数据库中所有无Markdown格式的答案，直接调用Stage2模型重新生成并写回数据库。
不修改前端，直接改数据。

用法：python fix_answers_md.py [--limit N] [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, 'e:/Agent/AgentProject/wxr_agent')

from backend.config.config import settings
from backend.agents.prompts.two_stage_prompts import ENRICH_SYSTEM_PROMPT, ENRICH_USER_PROMPT_TEMPLATE
from backend.agents.two_stage_miner_agent import TwoStageExtractor
from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1
from hello_agents import SimpleAgent
from hello_agents.core.llm import HelloAgentsLLM

DB_PATH = str(settings.sqlite_db_path)
BATCH_SIZE = 10  # 每次批量送给LLM的题目数


def has_markdown(text: str) -> bool:
    if not text:
        return False
    return any(c in text for c in ['**', '\n\n', '## ', '### ', '1. ', '2. ', '- '])


def get_plain_questions(limit=None):
    """获取无Markdown答案的题目"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT q_id, question_text, answer_text, difficulty, question_type, topic_tags, company, position
        FROM questions
        WHERE answer_text IS NOT NULL AND answer_text != ''
          AND answer_text NOT LIKE '%**%'
          AND answer_text NOT LIKE '%' || char(10) || char(10) || '%'
          AND answer_text NOT LIKE '## %'
          AND answer_text NOT LIKE '### %'
        ORDER BY created_at DESC
    """
    if limit:
        sql += f" LIMIT {limit}"
    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    conn.close()
    return rows


def call_stage2_for_batch(questions: list) -> list:
    """调用Stage2模型为一批题目生成Markdown答案，返回[{q_id, answer_text}, ...]"""
    models = settings.miner_stage2_models
    if not models:
        raise RuntimeError('未配置Stage2模型，请检查.env中MINER_STAGE2_MODEL等配置')

    questions_text = '\n'.join(
        f"{i+1}. {q['question_text']}"
        for i, q in enumerate(questions)
    )
    enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)

    last_err = None
    for cfg in models:
        try:
            llm = HelloAgentsLLM(
                model=cfg['model'],
                api_key=cfg['api_key'],
                base_url=cfg['base_url'],
                temperature=settings.miner_stage2_temperature,
                timeout=int(cfg.get('timeout') or settings.miner_stage2_timeout),
                max_tokens=settings.miner_stage2_max_tokens,
            )
            agent = SimpleAgent(
                name='MD Fixer',
                llm=llm,
                system_prompt=ENRICH_SYSTEM_PROMPT,
            )
            result = (agent.run(enrich_input) or '').strip()
            if not result:
                continue
            result = TwoStageExtractor._strip_think_tags(result)
            result = TwoStageExtractor._extract_json_if_direct_reply(result)

            # 用stage1数据merge，补全缺失字段
            stage1_json = json.dumps([
                {
                    'q_id': q['q_id'],
                    'question_text': q['question_text'],
                    'answer_text': q.get('answer_text', ''),
                    'raw_answer': q.get('answer_text', ''),
                    'difficulty': q.get('difficulty', 'medium'),
                    'question_type': q.get('question_type', '技术题'),
                    'topic_tags': json.loads(q['topic_tags']) if isinstance(q.get('topic_tags'), str) and q['topic_tags'].startswith('[') else [],
                    'company': q.get('company', ''),
                    'position': q.get('position', ''),
                }
                for q in questions
            ], ensure_ascii=False)
            merged = merge_stage2_with_stage1(result, stage1_json)
            merged_list = json.loads(merged)
            return merged_list
        except Exception as e:
            last_err = e
            logger.error('Stage2调用失败 model=%s: %s', cfg['model'], e)
    raise RuntimeError(f'所有Stage2模型均失败: {last_err}')


def write_answers_to_db(items: list):
    """将生成的答案批量写回数据库"""
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for item in items:
        qid = (item.get('q_id') or '').strip()
        at = (item.get('answer_text') or '').strip()
        if not qid or not at:
            continue
        if not has_markdown(at):
            logger.warning('q_id=%s 生成的答案仍无Markdown，跳过写入', qid)
            continue
        conn.execute(
            'UPDATE questions SET answer_text=?, updated_at=CURRENT_TIMESTAMP WHERE q_id=?',
            (at, qid)
        )
        updated += 1
    conn.commit()
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少条题目')
    parser.add_argument('--dry-run', action='store_true', help='只统计数量不实际修改')
    parser.add_argument('--sleep', type=float, default=1.0, help='批次间隔秒数')
    parser.add_argument('--batch', type=int, default=BATCH_SIZE, help='每批题目数')
    args = parser.parse_args()

    rows = get_plain_questions(limit=args.limit)
    total = len(rows)
    logger.info('待修复题目数: %d', total)

    if args.dry_run:
        for r in rows[:20]:
            logger.info('  q_id=%s | %s', r['q_id'], (r['question_text'] or '')[:60])
        if total > 20:
            logger.info('  ... 共 %d 条', total)
        return

    ok = 0
    fail = 0
    for i in range(0, total, args.batch):
        batch = rows[i:i+args.batch]
        logger.info('[%d/%d] 处理第 %d~%d 条...', i+1, total, i+1, min(i+args.batch, total))
        try:
            merged = call_stage2_for_batch(batch)
            written = write_answers_to_db(merged)
            ok += written
            logger.info('  本批写入 %d 条', written)
        except Exception as e:
            fail += len(batch)
            logger.error('  本批失败: %s', e)
        if i + args.batch < total:
            time.sleep(args.sleep)

    logger.info('完成: 成功写入=%d, 失败=%d / 总计=%d', ok, fail, total)


if __name__ == '__main__':
    main()
