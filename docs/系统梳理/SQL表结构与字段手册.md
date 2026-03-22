# SQL 表结构与字段手册

数据源：`backend/services/storage/sqlite_service.py`。  
说明：以下字段包含“建表字段 + 迁移补充字段”。  
仓库结构索引：[`docs/README.md`](../README.md)。

## 1. `questions`（题库主表）

**功能**：存储结构化面试题，支持题库检索、练习、GraphRAG、来源追溯。

| 字段 | 类型 | 说明 |
|---|---|---|
| q_id | TEXT PK | 题目唯一 ID |
| question_text | TEXT | 题目文本 |
| answer_text | TEXT | 标准答案 |
| difficulty | TEXT | 难度 |
| question_type | TEXT | 题型 |
| source_platform | TEXT | 来源平台 |
| source_url | TEXT | 来源链接 |
| company | TEXT | 公司 |
| position | TEXT | 岗位 |
| business_line | TEXT | 业务线 |
| topic_tags | TEXT(JSON) | 标签数组 |
| extraction_source | TEXT | 提取来源（content/image） |
| created_at / updated_at | DATETIME | 创建/更新时间 |
| crawl_task_id | INTEGER | 关联 `crawl_tasks.id` |
| raw_answer | TEXT | 原始答案（stage1 输出） |

## 2. `user_profiles`（用户画像）

**功能**：语义记忆层中的静态画像（技术栈、目标公司岗位）。

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | TEXT PK | 用户 ID |
| resume_text | TEXT | 简历文本 |
| tech_stack | TEXT(JSON) | 技术栈 |
| target_company | TEXT | 目标公司 |
| target_position | TEXT | 目标岗位 |
| experience_level | TEXT | 经验级别 |
| preferred_topics | TEXT(JSON) | 偏好标签 |
| created_at / updated_at | DATETIME | 创建/更新时间 |

## 3. `user_tag_mastery`（标签掌握度）

**功能**：学习诊断核心表，用于薄弱标签识别、学习报告、推荐。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| user_id | TEXT | 用户 ID |
| tag | TEXT | 标签 |
| total_attempts | INTEGER | 作答次数 |
| correct_count | INTEGER | 正确次数 |
| avg_score | REAL | 平均分 |
| mastery_level | TEXT | 掌握等级 |
| last_practiced | DATETIME | 最近练习时间 |
| last_updated | DATETIME | 最近更新时间 |
| UNIQUE(user_id, tag) | - | 用户标签唯一约束 |

## 4. `study_records`（做题记录）

**功能**：情景记忆核心表，记录每次作答与 SM-2 遗忘参数。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| user_id | TEXT | 用户 ID |
| question_id | TEXT | 题目 ID |
| session_id | TEXT | 会话 ID |
| message_id | TEXT | 消息 ID |
| score | REAL | 得分 |
| user_answer | TEXT | 用户答案 |
| ai_feedback | TEXT | 评语 |
| easiness_factor | REAL | SM-2 参数 |
| repetitions | INTEGER | 重复次数 |
| interval_days | INTEGER | 间隔天数 |
| next_review_at | DATETIME | 下次复习时间 |
| studied_at | DATETIME | 作答时间 |
| eval_details | TEXT(JSON) | 结构化评分细节 |

## 5. `interview_sessions`（会话表）

**功能**：工作记忆与会话上下文存储（含聊天历史）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| session_id | TEXT UNIQUE | 会话唯一 ID |
| user_id | TEXT | 用户 ID |
| session_type | TEXT | 会话类型 |
| topic_focus | TEXT | 主题 |
| target_company | TEXT | 目标公司 |
| conversation_history | TEXT(JSON) | 对话历史 |
| start_time / end_time | DATETIME | 开始/结束 |
| total_questions | INTEGER | 会话题目数 |
| avg_score | REAL | 会话平均分 |
| ai_summary | TEXT | 会话总结 |
| weak_tags | TEXT(JSON) | 会话薄弱标签 |
| session_meta | TEXT(JSON) | 会话元数据（迁移字段） |

## 6. `user_notes`（用户笔记）

**功能**：笔记与弱项沉淀（遗漏点/混淆点等）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| note_id | TEXT UNIQUE | 笔记 ID |
| user_id | TEXT | 用户 ID |
| question_id | TEXT | 关联题目 |
| title | TEXT | 标题 |
| content | TEXT | 内容 |
| tags | TEXT(JSON) | 标签 |
| note_type | TEXT | 类型（concept/weakness/confusion） |
| created_at / updated_at | DATETIME | 创建/更新时间 |

## 7. `crawl_logs`（爬取日志）

**功能**：记录 URL 级爬取结果与统计。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| url | TEXT | URL |
| status | TEXT | 状态 |
| title | TEXT | 标题 |
| source_platform | TEXT | 平台 |
| company / position | TEXT | 公司/岗位 |
| questions_extracted | INTEGER | 提取题数 |
| crawled_at | DATETIME | 爬取时间 |

## 8. `episodic_log`（情节记忆日志）

**功能**：跨流程事件日志（答题、遗漏、混淆、收录等）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| user_id | TEXT | 用户 ID |
| content | TEXT | 事件内容 |
| importance | REAL | 重要度 |
| event_type | TEXT | 事件类型 |
| session_id | TEXT | 会话 ID |
| question_id | TEXT | 题目 ID |
| score | INTEGER | 分数快照 |
| created_at | DATETIME | 创建时间 |

## 9. `ingestion_logs`（入库日志）

**功能**：记录题目入库来源，便于回溯。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| question_id | TEXT | 题目 ID |
| source_url | TEXT | 来源 URL |
| tags | TEXT(JSON) | 标签 |
| created_at | DATETIME | 创建时间 |

## 10. `knowledge_resources`（学习资源库）

**功能**：按标签推荐的知识资源（预置 + 用户补充）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| resource_id | TEXT UNIQUE | 资源 ID |
| title | TEXT | 标题 |
| url | TEXT | 链接 |
| description | TEXT | 描述 |
| tags | TEXT(JSON) | 标签 |
| resource_type | TEXT | 资源类型 |
| source | TEXT | 来源 |
| created_at | DATETIME | 创建时间 |

## 11. `finetune_samples`（微调样本）

**功能**：两阶段抽取后的样本标注与导出核心表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| content | TEXT | 原始内容 |
| stage1_output / stage2_output | TEXT | 两阶段输出 |
| stage1_model / stage2_model | TEXT | 模型标记 |
| title / source_url | TEXT | 来源信息 |
| assist_output | TEXT | 助手建议 |
| final_output | TEXT | 最终标注 |
| is_modified | INTEGER | 是否人工修改 |
| status | TEXT | 状态（pending/labeled 等） |
| source | TEXT | 来源类型 |
| created_at / modified_at / labeled_at | DATETIME/TEXT | 时间字段 |

## 12. `finetune_runs`（训练运行记录）

**功能**：每次「生成并训练」写入一条记录；后台线程执行 `train_lora.py` 时更新时间与状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| config_json | TEXT | 配置快照 |
| output_dir | TEXT | 输出目录 |
| script_path | TEXT | 脚本路径 |
| data_path | TEXT | 数据路径 |
| sample_count | INTEGER | 样本数 |
| status | TEXT | `generated`（仅生成脚本）/ `running` / `completed` / `failed` |
| created_at / started_at / ended_at | DATETIME | 时间字段 |

训练进程标准输出日志文件路径（非 DB 字段）：`微调/logs/train_run_{id}.log`。

## 13. `crawl_tasks`（采集任务队列）

**功能**：发现 -> 抓取 -> 提取全链路任务主表。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| task_id | TEXT UNIQUE | 任务 ID |
| source_url | TEXT UNIQUE | 源链接（去重） |
| source_platform | TEXT | 平台 |
| post_title | TEXT | 标题 |
| status | TEXT | 状态（pending/fetched/processed/error） |
| company / position / business_line | TEXT | 业务元信息 |
| difficulty / post_type | TEXT | 难度/帖子类型 |
| raw_content | TEXT | 正文原文 |
| image_paths | TEXT(JSON) | 图片路径数组 |
| questions_count | INTEGER | 提取题数 |
| error_msg | TEXT | 错误信息 |
| discovered_at / processed_at | DATETIME | 发现/处理时间 |
| discover_keyword | TEXT | 发现关键词（迁移） |
| extraction_source | TEXT | 提取来源（content/image） |
| agent_used_tool | INTEGER | Miner 是否用工具 |
| extract_duration_min | REAL | 提取耗时（分钟） |
| trace_session_id | TEXT | 推理追踪会话 ID |
| post_time | TEXT | 帖子发布时间 |

## 14. `stage2_pending`（Stage2 异步队列）

**功能**：两阶段提取的 MQ 替代队列，支持 lease/重试/恢复。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 主键 |
| task_id | TEXT UNIQUE | 关联任务 ID |
| content | TEXT | 内容片段 |
| stage1_output | TEXT | 第一阶段输出 |
| rough_questions | TEXT | 粗抽题结果 |
| enrich_input | TEXT | stage2 输入 |
| company / position | TEXT | 元信息 |
| source_url / post_title | TEXT | 来源 |
| trace_session_id | TEXT | 推理追踪 ID |
| agent_used_tool / ocr_called | INTEGER | 调用标记 |
| status | TEXT | pending/in_progress/done/error |
| worker_id | TEXT | 租约工作节点 |
| locked_at | DATETIME | 租约锁时间 |
| attempts | INTEGER | 重试次数 |
| last_error | TEXT | 最近错误 |
| created_at | DATETIME | 创建时间 |

## 15. 关系与职责总览

- 题库主链路：`crawl_tasks -> questions -> study_records -> user_tag_mastery`。
- 会话与记忆：`interview_sessions`（工作记忆）+ `episodic_log`（情景记忆）+ `user_profiles`（语义记忆）。
- 微调链路：`finetune_samples -> finetune_runs`；效果对比见前端「模型对比」页（`GET/POST /api/finetune/compare*`）。
- 推荐链路：`user_tag_mastery + study_records + knowledge_resources`。
