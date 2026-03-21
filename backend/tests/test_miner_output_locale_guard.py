"""miner_output_locale_guard 单元测试（可直接 python -m backend.tests.test_miner_output_locale_guard）。"""

from backend.services.crawler.miner_output_locale_guard import (
    source_expects_chinese,
    validate_chinese_extraction,
)


def test_source_expects_chinese_xhs_style():
    title = "快手AI agent开发实习生一二面面经"
    body = "一面问了 BM25、rerank、MySQL MVCC，手撕反转链表。"
    assert source_expects_chinese(f"【标题】{title}\n\n【正文】\n{body}") is True


def test_source_expects_chinese_pure_english():
    text = "This is an English-only interview post with no Chinese characters at all."
    assert source_expects_chinese(text) is False


def test_validate_passes_chinese_questions():
    src = "【标题】测试\n\n【正文】\n问了 Redis 持久化，手撕 LRU。"
    items = [
        {
            "question_text": "请介绍 Redis 的持久化方式",
            "answer_text": "RDB 与 AOF 两种，RDB 为快照，AOF 为日志追加。",
            "topic_tags": ["Redis", "持久化", "RDB"],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert ok and reason == ""


def test_validate_passes_english_question_on_chinese_source():
    """弱化英文主导后：中文原帖下允许英文题干。"""
    src = "【标题】快手面经\n\n【正文】\nWhy do you introduce BM25? 问了 rerank。"
    items = [
        {
            "question_text": "Why do you introduce parent-child indexes and what is the reranking ratio?",
            "answer_text": "简要说明检索与重排序流程。",
            "topic_tags": ["RAG", "检索", "重排序"],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert ok and reason == ""


def test_validate_passes_empty_tags():
    """仅乱码检测：空标签不再拦截。"""
    src = "中文面经正文足够长" * 5
    items = [
        {
            "question_text": "请说明布隆过滤器的原理与误判率",
            "answer_text": "哈希与位数组，可能假阳性。",
            "topic_tags": [],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert ok and reason == ""


def test_validate_fails_replacement_char():
    src = "任意正文"
    items = [
        {
            "question_text": "正常题干\ufffd尾部损坏",
            "answer_text": "答案正常",
            "topic_tags": ["标签"],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert not ok
    assert "FFFD" in reason or "替换" in reason


def test_validate_fails_nul_in_answer():
    src = "任意正文"
    items = [
        {
            "question_text": "题干",
            "answer_text": "坏\x00答案",
            "topic_tags": ["x"],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert not ok
    assert "NUL" in reason or "空字节" in reason


def test_validate_skips_when_source_not_chinese():
    """英文源下同样做乱码检测；无乱码则通过。"""
    src = "Pure English leetcode discussion without CJK."
    items = [
        {
            "question_text": "Why is quicksort average O(n log n)?",
            "answer_text": "Because partition balances expected.",
            "topic_tags": ["Algorithms", "Sorting"],
        }
    ]
    ok, reason = validate_chinese_extraction(items, src)
    assert ok


if __name__ == "__main__":
    test_source_expects_chinese_xhs_style()
    test_source_expects_chinese_pure_english()
    test_validate_passes_chinese_questions()
    test_validate_passes_english_question_on_chinese_source()
    test_validate_passes_empty_tags()
    test_validate_fails_replacement_char()
    test_validate_fails_nul_in_answer()
    test_validate_skips_when_source_not_chinese()
    print("miner_output_locale_guard: all tests ok")
