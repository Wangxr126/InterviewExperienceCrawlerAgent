"""
面经 Agent 功能调试脚本（无需前端）
运行方式：
    python debug_test.py

提供交互式菜单，可以逐一测试后端所有核心功能。
不依赖 uvicorn，直接调用 Python 类。
"""
import asyncio
import json
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(__file__))


# ─────────────────────────────────────────────────
# 颜色输出工具
# ─────────────────────────────────────────────────
def c(text, color="green"):
    codes = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
             "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m", "end": "\033[0m"}
    return f"{codes.get(color,'')}{text}{codes['end']}"


def title(text):
    print(f"\n{c('═'*55, 'blue')}")
    print(f"  {c(text, 'bold')}")
    print(f"{c('═'*55, 'blue')}")


def ok(text):  print(f"  {c('✅', 'green')} {text}")
def warn(text): print(f"  {c('⚠️ ', 'yellow')} {text}")
def err(text):  print(f"  {c('❌', 'red')} {text}")
def info(text): print(f"  {c('ℹ️ ', 'cyan')} {text}")


# ─────────────────────────────────────────────────
# 测试函数
# ─────────────────────────────────────────────────

def test_sqlite():
    """测试 SQLite 连接和基本操作"""
    title("SQLite 数据库测试")
    try:
        from backend.services.sqlite_service import sqlite_service
        ok("SQLite 服务初始化成功")

        # 写入测试题目
        q_id = "DBG-Q-001"
        sqlite_service.upsert_question(
            q_id=q_id,
            question_text="什么是 Redis 的 AOF 持久化？",
            answer_text="AOF 是 Append Only File，记录每次写命令...",
            tags=["Redis", "持久化", "AOF"],
            difficulty="medium",
            company="字节跳动",
            position="后端工程师",
            source_platform="nowcoder",
            source_url="https://example.com/test"
        )
        ok(f"写入测试题目 {q_id}")

        # 过滤查询
        results = sqlite_service.filter_questions(company="字节", limit=5)
        ok(f"按公司过滤 (字节)：返回 {len(results)} 条")
        if results:
            info(f"  第一条：{results[0]['question_text'][:40]}...")

        # 知识资源
        resources = sqlite_service.get_resources_by_tags(["Redis"], limit=3)
        ok(f"知识资源库：查到 {len(resources)} 条 Redis 资源")
        for r in resources[:2]:
            info(f"  · {r['title']}")

        # 用户画像
        sqlite_service.upsert_user_profile(
            user_id="debug_user",
            tech_stack=["Java", "Redis", "MySQL"],
            target_company="字节跳动",
            target_position="后端工程师",
            experience_level="junior"
        )
        profile = sqlite_service.get_user_profile("debug_user")
        ok(f"用户画像写入/读取：{profile.get('tech_stack')[:30]}")

        # 掌握度
        sqlite_service.update_tag_mastery("debug_user", "Redis", score=2)
        sqlite_service.update_tag_mastery("debug_user", "MySQL", score=4)
        weak = sqlite_service.get_weak_tags("debug_user", threshold=2.5)
        ok(f"薄弱标签查询：{weak}")

    except Exception as e:
        err(f"SQLite 测试失败：{e}")
        import traceback; traceback.print_exc()


def test_filter_questions():
    """测试题目过滤（多种条件）"""
    title("题目过滤测试")
    try:
        from backend.services.sqlite_service import sqlite_service

        filters = [
            {"label": "全部（最新20条）", "kwargs": {"limit": 20}},
            {"label": "按公司过滤（字节）", "kwargs": {"company": "字节", "limit": 5}},
            {"label": "按难度过滤（hard）", "kwargs": {"difficulty": "hard", "limit": 5}},
            {"label": "按标签过滤（Redis）", "kwargs": {"tags": ["Redis"], "limit": 5}},
            {"label": "关键词搜索（AOF）", "kwargs": {"keyword": "AOF", "limit": 5}},
        ]

        for f in filters:
            results = sqlite_service.filter_questions(**f["kwargs"])
            ok(f"{f['label']}：返回 {len(results)} 条")

    except Exception as e:
        err(f"过滤测试失败：{e}")


def test_study_record():
    """测试答题记录 + SM-2 更新"""
    title("答题记录 & SM-2 测试")
    try:
        from backend.services.sqlite_service import sqlite_service

        sqlite_service.add_study_record(
            user_id="debug_user",
            question_id="DBG-Q-001",
            score=2,
            user_answer="AOF 是记录所有写命令的文件",
            ai_feedback="遗漏了 AOF 重写机制（BGREWRITEAOF）和重写时子进程处理方式",
            session_id="sess_debug_001"
        )
        ok("答题记录写入成功（score=2）")

        # 查询待复习
        due = sqlite_service.get_due_reviews("debug_user", limit=5)
        ok(f"SM-2 待复习题目：{len(due)} 条")

        # 查历史
        history = sqlite_service.get_study_history("debug_user", limit=3)
        ok(f"学习历史：{len(history)} 条记录")
        if history:
            info(f"  最近一次：得分 {history[0].get('score')}/5，时间 {history[0].get('studied_at','')[:10]}")

    except Exception as e:
        err(f"答题记录测试失败：{e}")


def test_knowledge_recommender():
    """测试知识推荐工具"""
    title("知识推荐工具测试")
    try:
        from backend.tools.interviewer_tools import KnowledgeRecommender
        rec = KnowledgeRecommender()
        result = rec.run({
            "user_id": "debug_user",
            "tags": ["Redis", "持久化"],
            "max_resources": 2,
            "max_mistakes": 2
        })
        ok("KnowledgeRecommender 调用成功")
        print()
        # 打印前 600 字
        print(result[:600] + ("..." if len(result) > 600 else ""))
    except Exception as e:
        err(f"知识推荐测试失败：{e}")
        import traceback; traceback.print_exc()


def test_content_validator():
    """测试内容校验器（相关性判断 + OCR 决策）"""
    title("ContentValidator 测试")
    try:
        from backend.tools.hunter_tools import ContentValidator
        cv = ContentValidator()

        cases = [
            {
                "label": "场景A：纯文字面经（应 relevant=True, needs_ocr=False）",
                "text": ("字节跳动后端面试经历分享。\n"
                         "面试官问了Redis持久化，问了AOF和RDB的区别？\n"
                         "还问了如何解决缓存雪崩？什么是缓存击穿？\n"
                         "MySQL事务的隔离级别是什么？MVCC的原理？\n"
                         "分布式锁如何实现？Zookeeper和Redis方案有什么区别？\n"
                         "还考了JVM的GC算法，说说G1和ZGC的区别？\n"
                         "总体来说考察了很多基础知识，要认真准备。"),
                "platform": "nowcoder"
            },
            {
                "label": "场景B：图片面经（应 relevant=True, needs_ocr=True）",
                "text": ("今天去字节跳动面试了，感觉还不错，分享一下！\n"
                         "[IMAGE_URL]: https://cdn.example.com/img1.jpg\n"
                         "[IMAGE_URL]: https://cdn.example.com/img2.jpg\n"
                         "[IMAGE_URL]: https://cdn.example.com/img3.jpg"),
                "platform": "xiaohongshu"
            },
            {
                "label": "场景C：非面经内容（应 relevant=False）",
                "text": "今天天气真好，推荐大家去公园散步！超级开心的一天。",
                "platform": "xiaohongshu"
            },
        ]

        for case in cases:
            result_json = cv.run({
                "scraped_text": case["text"],
                "source_platform": case["platform"]
            })
            result = json.loads(result_json)
            status = c("✅", "green") if True else ""
            print(f"\n  [{case['label']}]")
            info(f"  relevant={result['relevant']}, needs_ocr={result.get('needs_ocr')}, "
                 f"quality={result.get('content_quality')}, images={result.get('image_count')}")
            info(f"  原因：{result.get('reason','')}")

    except Exception as e:
        err(f"ContentValidator 测试失败：{e}")
        import traceback; traceback.print_exc()


async def test_submit_answer():
    """测试 Orchestrator.submit_answer() 确定性答题链"""
    title("submit_answer 答题链测试")
    try:
        from backend.agents.orchestrator import get_orchestrator
        orch = get_orchestrator()

        print("  ⏳ 调用结构化评估 + 知识推荐（需要 LLM，可能稍慢）...")
        result = await orch.submit_answer(
            user_id="debug_user",
            session_id="sess_debug_001",
            question_id="DBG-Q-001",
            question_text="Redis 的 AOF 持久化原理是什么？AOF 重写机制如何工作？",
            user_answer="AOF 是把所有写命令追加到文件里，这样重启可以恢复数据。",
            question_tags=["Redis", "持久化", "AOF"]
        )

        ok(f"评估完成！得分：{result['score']}/5")
        info(f"综合评价：{result['feedback'][:80]}...")
        if result.get('missed_points'):
            info(f"遗漏点：{result['missed_points']}")
        ok(f"SM-2 已更新，记忆已写入")
        if result.get('recommendation'):
            ok("触发了知识推荐（score ≤ 2）")

    except Exception as e:
        err(f"submit_answer 测试失败：{e}")
        import traceback; traceback.print_exc()


async def test_chat():
    """测试 Orchestrator.chat()"""
    title("对话接口测试")
    try:
        from backend.agents.orchestrator import get_orchestrator
        orch = get_orchestrator()

        print("  ⏳ 发送对话请求（需要 LLM）...")
        response = await orch.chat(
            user_id="debug_user",
            message="你好，帮我推荐一道 Redis 相关的面试题",
            session_id="sess_debug_001"
        )
        ok("对话成功")
        print(f"\n  Agent 回复：\n  {'─'*40}")
        for line in response[:500].split('\n'):
            print(f"  {line}")
        if len(response) > 500:
            print(f"  ...（共 {len(response)} 字）")

    except Exception as e:
        err(f"对话测试失败：{e}")
        import traceback; traceback.print_exc()


async def test_ingest_pipeline():
    """测试 HunterPipeline（用一个真实 URL）"""
    title("HunterPipeline 爬取管道测试")
    url = input("  输入要测试的 URL（直接回车跳过）: ").strip()
    if not url:
        warn("跳过爬取测试")
        return
    try:
        from backend.services.hunter_pipeline import run_hunter_pipeline
        print(f"  ⏳ 开始处理 {url}...")
        result = await run_hunter_pipeline(url, source_platform="nowcoder")
        if result.success:
            ok(f"管道成功！文本长度：{len(result.text)}")
            ok(f"触发了OCR：{result.ocr_triggered}，图片数：{result.image_count}")
            ok(f"元信息：{result.meta}")
        else:
            warn(f"管道跳过：{result.skip_reason}")
    except Exception as e:
        err(f"管道测试失败：{e}")
        import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────
# 主菜单
# ─────────────────────────────────────────────────

MENU = [
    ("1", "SQLite 数据库基础操作", test_sqlite, False),
    ("2", "题目过滤（多条件）", test_filter_questions, False),
    ("3", "答题记录 & SM-2 更新", test_study_record, False),
    ("4", "知识推荐工具", test_knowledge_recommender, False),
    ("5", "内容校验器（相关性+OCR决策）", test_content_validator, False),
    ("6", "答题提交链（需LLM，稍慢）", test_submit_answer, True),
    ("7", "对话接口（需LLM，稍慢）", test_chat, True),
    ("8", "爬取管道（需输入URL）", test_ingest_pipeline, True),
    ("a", "运行所有非 LLM 测试", None, False),
    ("q", "退出", None, False),
]


async def run_all_local():
    test_sqlite()
    test_filter_questions()
    test_study_record()
    test_knowledge_recommender()
    test_content_validator()


async def main():
    print(c("""
╔════════════════════════════════════════════╗
║     面经 Agent 功能调试工具  debug_test.py  ║
╚════════════════════════════════════════════╝""", "cyan"))

    while True:
        print(f"\n{c('请选择要测试的功能：', 'bold')}")
        for key, label, _, needs_llm in MENU:
            llm_tag = c(" [需LLM]", "yellow") if needs_llm else ""
            print(f"  {c(key, 'cyan')}. {label}{llm_tag}")

        choice = input("\n输入编号: ").strip().lower()

        if choice == "q":
            print("再见！")
            break
        elif choice == "a":
            await run_all_local()
        else:
            matched = [(fn, is_async) for k, _, fn, is_async in MENU
                       if k == choice and fn is not None]
            if not matched:
                warn("无效选项")
                continue
            fn, is_async = matched[0]
            if is_async:
                await fn()
            else:
                fn()

        input(f"\n{c('按回车继续...', 'blue')}")


if __name__ == "__main__":
    asyncio.run(main())
