-- =============================================================================
-- 将历史「AI 大类 / 脏值」题目类型细化为 AI-* 子类（SQLite questions 表）
-- 使用前请备份数据库；执行后前端「题目类型」下拉来自 DISTINCT question_type。
-- 全库逐题复查请用：python -m backend.scripts.reclassify_question_types
--
-- 路径请按本机修改，示例：
--   sqlite3 "E:/Agent/AgentProject/wxr_agent/data/questions.db" ".read backend/scripts/migrate_question_type_ai_subtypes.sql"
-- =============================================================================

BEGIN TRANSACTION;

-- 合并常见脏值为统一集合，便于 CASE（可按需增删 IN 列表）
UPDATE questions
SET question_type = CASE
  WHEN (
    question_text LIKE '%工具调用%' OR question_text LIKE '%Function Call%'
    OR question_text LIKE '%function calling%' OR question_text LIKE '%插件调用%'
    OR question_text LIKE '%MCP%' OR lower(question_text) LIKE '%tool%'
    OR topic_tags LIKE '%工具调用%' OR topic_tags LIKE '%MCP%'
  ) THEN 'AI-Agent工具调用'

  WHEN (
    question_text LIKE '%RAG%' OR topic_tags LIKE '%RAG%'
    OR question_text LIKE '%检索增强%' OR question_text LIKE '%向量检索%'
  ) THEN 'AI-RAG与检索增强'

  WHEN (
    question_text LIKE '%长期记忆%' OR question_text LIKE '%短期记忆%'
    OR question_text LIKE '%记忆机制%' OR question_text LIKE '%记忆管理%'
    OR question_text LIKE '%记忆压缩%' OR question_text LIKE '%向量数据库%'
    OR question_text LIKE '%向量库%' OR topic_tags LIKE '%记忆%'
    OR topic_tags LIKE '%向量数据库%'
  ) THEN 'AI-Agent记忆'

  WHEN (
    question_text LIKE '%上下文%' OR question_text LIKE '%上下文窗口%'
    OR question_text LIKE '%上下文污染%' OR question_text LIKE '%上下文隔离%'
    OR question_text LIKE '%token%' OR question_text LIKE '%Token%'
    OR question_text LIKE '%窗口长度%' OR topic_tags LIKE '%上下文%'
  ) THEN 'AI-Agent上下文与窗口'

  WHEN (
    question_text LIKE '%多智能体%' OR question_text LIKE '%Multi-Agent%'
    OR question_text LIKE '%multi agent%' OR question_text LIKE '%智能体编排%'
    OR topic_tags LIKE '%多智能体%' OR topic_tags LIKE '%Multi-Agent%'
  ) THEN 'AI-多智能体与编排'

  WHEN (
    question_text LIKE '%幻觉%' OR question_text LIKE '%对齐%'
    OR question_text LIKE '%越狱%' OR question_text LIKE '%提示注入%'
    OR topic_tags LIKE '%幻觉%'
  ) THEN 'AI-可靠性与幻觉治理'

  WHEN (
    question_text LIKE '%ReAct%' OR question_text LIKE '%CoT%'
    OR question_text LIKE '%思维链%' OR question_text LIKE '%推理链%'
    OR question_text LIKE '%Agent 设计模式%' OR question_text LIKE '%设计模式%'
    OR topic_tags LIKE '%ReAct%' OR topic_tags LIKE '%CoT%'
  ) THEN 'AI-推理与规划'

  WHEN (
    question_text LIKE '%Transformer%' OR question_text LIKE '%Attention%'
    OR question_text LIKE '%注意力机制%' OR question_text LIKE '%Tokenizer%'
    OR question_text LIKE '%KV Cache%' OR question_text LIKE '%大模型原理%'
    OR question_text LIKE '%LLM%' OR topic_tags LIKE '%Transformer%'
  ) THEN 'AI-LLM原理与结构'

  WHEN (
    question_text LIKE '%微调%' OR question_text LIKE '%LoRA%'
    OR question_text LIKE '%RLHF%' OR question_text LIKE '%SFT%'
    OR question_text LIKE '%预训练%' OR question_text LIKE '%损失函数%'
  ) THEN 'AI-训练微调与评估'

  WHEN (
    question_text LIKE '%Agent%' OR question_text LIKE '%智能体%'
    OR lower(question_text) LIKE '%agent%' OR topic_tags LIKE '%Agent%'
  ) THEN 'AI-推理与规划'

  ELSE 'AI-其他'
END
WHERE question_type IN (
  'AI类', 'AI', 'AI/Agent类', 'AI应用开发', 'AI概念', 'AI模型', 'AI类/工程类'
);
-- 若库中仍有「以 AI 开头」的自定义大类，可改为追加：
--    OR question_type LIKE 'AI%'
-- 不要使用过于宽泛的 %AI%，以免误伤不含 AI 考点的类型字符串。

COMMIT;

-- -----------------------------------------------------------------------------
-- Neo4j（可选）：题目节点属性 question_type 与 text，需与 SQLite 一致时可执行。
-- 在 Neo4j Browser 中分步执行；属性名为 text（见 neo4j_service.add_question）。
-- 若图谱与库不同步，也可用应用侧「按 q_id 从 SQLite 回写」脚本代替。
--
-- MATCH (q:Question)
-- WHERE q.question_type IN ['AI类','AI','AI/Agent类','AI应用开发','AI概念','AI模型','AI类/工程类']
--    OR q.question_type ENDS WITH 'AI' OR q.question_type STARTS WITH 'AI'
-- SET q.question_type = CASE
--   WHEN q.text CONTAINS '工具调用' OR q.text CONTAINS 'MCP' THEN 'AI-Agent工具调用'
--   WHEN q.text CONTAINS 'RAG' THEN 'AI-RAG与检索增强'
--   WHEN q.text CONTAINS '记忆' OR q.text CONTAINS '向量数据库' THEN 'AI-Agent记忆'
--   WHEN q.text CONTAINS '上下文' THEN 'AI-Agent上下文与窗口'
--   WHEN q.text CONTAINS '多智能体' THEN 'AI-多智能体与编排'
--   WHEN q.text CONTAINS '幻觉' THEN 'AI-可靠性与幻觉治理'
--   WHEN q.text CONTAINS 'ReAct' OR q.text CONTAINS '思维链' THEN 'AI-推理与规划'
--   WHEN q.text CONTAINS 'Transformer' OR q.text CONTAINS 'Attention' THEN 'AI-LLM原理与结构'
--   WHEN q.text CONTAINS '微调' OR q.text CONTAINS 'LoRA' THEN 'AI-训练微调与评估'
--   WHEN q.text CONTAINS 'Agent' OR q.text CONTAINS '智能体' THEN 'AI-推理与规划'
--   ELSE 'AI-其他'
-- END;
-- -----------------------------------------------------------------------------
