-- =============================================================================
-- 将历史「算法类 / 工程类 / 基础类 / 软技能」细化为 算法-/工程-/基础-/软技能- 小类
-- 在 migrate_question_type_ai_subtypes.sql 之后执行亦可；执行前请备份 questions.db。
-- 规则为关键词优先匹配（SQLite CASE 自上而下），与 miner_schema 推断尽量一致。
--
-- 若需对每一行按题干+topic_tags 再校验（含「已是小类但分错」），请用 Python 脚本：
--   python -m backend.scripts.reclassify_question_types --dry-run
--   python -m backend.scripts.reclassify_question_types
-- =============================================================================

BEGIN TRANSACTION;

-- —— 原 question_type = '算法类' ——
UPDATE questions
SET question_type = CASE
  WHEN question_text LIKE '%动态规划%' OR question_text LIKE '%背包%' OR topic_tags LIKE '%动态规划%' OR topic_tags LIKE '%DP%' THEN '算法-动态规划'
  WHEN question_text LIKE '%回溯%' OR question_text LIKE '%全排列%' OR question_text LIKE '%N皇后%' OR topic_tags LIKE '%回溯%' THEN '算法-回溯与搜索'
  WHEN question_text LIKE '%BFS%' OR question_text LIKE '%广度优先%' OR question_text LIKE '%拓扑%' OR topic_tags LIKE '%BFS%' THEN '算法-BFS与图遍历'
  WHEN question_text LIKE '%贪心%' OR topic_tags LIKE '%贪心%' THEN '算法-贪心'
  WHEN question_text LIKE '%最短路%' OR question_text LIKE '%Dijkstra%' OR question_text LIKE '%并查集%' OR question_text LIKE '%最小生成树%' THEN '算法-图论'
  WHEN question_text LIKE '%二叉树%' OR question_text LIKE '%BST%' OR topic_tags LIKE '%二叉树%' THEN '算法-树与二叉树'
  WHEN question_text LIKE '%链表%' OR topic_tags LIKE '%链表%' THEN '算法-链表'
  WHEN question_text LIKE '%堆%' OR question_text LIKE '%优先队列%' OR question_text LIKE '%TopK%' OR question_text LIKE '%第K大%' THEN '算法-堆与优先队列'
  WHEN question_text LIKE '%二分%' OR question_text LIKE '%排序%' OR question_text LIKE '%快排%' OR topic_tags LIKE '%二分%' THEN '算法-排序与二分查找'
  WHEN question_text LIKE '%位运算%' OR question_text LIKE '%异或%' THEN '算法-位运算与数学'
  WHEN question_text LIKE '%LRU%' OR question_text LIKE '%Trie%' OR question_text LIKE '%前缀树%' OR question_text LIKE '%最小栈%' THEN '算法-经典结构实现'
  WHEN question_text LIKE '%滑动窗口%' OR question_text LIKE '%双指针%' OR question_text LIKE '%前缀和%' OR topic_tags LIKE '%滑动窗口%' THEN '算法-数组与字符串'
  WHEN question_text LIKE '%手撕%' OR question_text LIKE '%手写%' OR question_text LIKE '%编程题%' THEN '算法-其他'
  ELSE '算法-其他'
END
WHERE question_type = '算法类';

-- —— 原 question_type = '工程类' ——
UPDATE questions
SET question_type = CASE
  WHEN question_text LIKE '%系统设计%' OR question_text LIKE '%秒杀%' OR question_text LIKE '%高并发%' OR question_text LIKE '%高可用%' OR question_text LIKE '%架构%' THEN '工程-系统设计与架构'
  WHEN question_text LIKE '%MySQL%' OR question_text LIKE '%索引%' OR question_text LIKE '%事务%' OR question_text LIKE '%分库%' OR topic_tags LIKE '%MySQL%' THEN '工程-数据库与SQL'
  WHEN question_text LIKE '%Redis%' OR question_text LIKE '%缓存%' OR topic_tags LIKE '%Redis%' THEN '工程-缓存与Redis'
  WHEN question_text LIKE '%Kafka%' OR question_text LIKE '%消息队列%' OR question_text LIKE '%RocketMQ%' OR question_text LIKE '%RabbitMQ%' THEN '工程-消息队列'
  WHEN question_text LIKE '%微服务%' OR question_text LIKE '%注册中心%' OR question_text LIKE '%网关%' OR question_text LIKE '%熔断%' OR question_text LIKE '%限流%' THEN '工程-微服务与治理'
  WHEN question_text LIKE '%并发%' OR question_text LIKE '%多线程%' OR question_text LIKE '%锁%' OR question_text LIKE '%线程池%' THEN '工程-并发与多线程'
  WHEN question_text LIKE '%HTTP%' OR question_text LIKE '%TCP%' OR question_text LIKE '%RPC%' OR question_text LIKE '%gRPC%' OR question_text LIKE '%WebSocket%' THEN '工程-网络与RPC'
  WHEN question_text LIKE '%慢查询%' OR question_text LIKE '%调优%' OR question_text LIKE '%性能优化%' OR question_text LIKE '%JVM%' THEN '工程-性能与调优'
  WHEN question_text LIKE '%降级%' OR question_text LIKE '%幂等%' OR question_text LIKE '%容灾%' OR question_text LIKE '%重试%' THEN '工程-稳定性与容灾'
  WHEN question_text LIKE '%Elasticsearch%' OR question_text LIKE '%ES %' OR question_text LIKE '%全文检索%' THEN '工程-搜索与Elasticsearch'
  WHEN question_text LIKE '%Docker%' OR question_text LIKE '%Kubernetes%' OR question_text LIKE '%K8s%' OR question_text LIKE '%CI/CD%' THEN '工程-云原生与DevOps'
  WHEN question_text LIKE '%安全%' OR question_text LIKE '%鉴权%' OR question_text LIKE '%XSS%' OR question_text LIKE '%CSRF%' THEN '工程-安全与合规'
  WHEN question_text LIKE '%React%' OR question_text LIKE '%Vue%' OR question_text LIKE '%前端%' THEN '工程-前端工程'
  ELSE '工程-其他'
END
WHERE question_type = '工程类';

-- —— 原 question_type = '基础类' ——
UPDATE questions
SET question_type = CASE
  WHEN question_text LIKE '%进程%' OR question_text LIKE '%线程%' OR question_text LIKE '%虚拟内存%' OR question_text LIKE '%死锁%' THEN '基础-操作系统'
  WHEN question_text LIKE '%三次握手%' OR question_text LIKE '%四次挥手%' OR question_text LIKE '%TCP%' OR question_text LIKE '%HTTP%' OR question_text LIKE '%DNS%' THEN '基础-计算机网络'
  WHEN question_text LIKE '%时间复杂度%' OR question_text LIKE '%栈%' OR question_text LIKE '%队列%' OR question_text LIKE '%哈希表%' THEN '基础-数据结构'
  WHEN question_text LIKE '%Java%' OR question_text LIKE '%Python%' OR question_text LIKE '%Go %' OR question_text LIKE '%C++%' THEN '基础-编程语言'
  ELSE '基础-其他'
END
WHERE question_type = '基础类';

-- —— 原 question_type = '软技能' ——
UPDATE questions
SET question_type = CASE
  WHEN question_text LIKE '%薪资%' OR question_text LIKE '%职业规划%' OR question_text LIKE '%离职%' OR question_text LIKE '%加班%' THEN '软技能-HR与职业规划'
  WHEN question_text LIKE '%冲突%' OR question_text LIKE '%压力%' OR question_text LIKE '%团队%' OR question_text LIKE '%困难%' OR question_text LIKE '%失败%' THEN '软技能-行为与情景'
  WHEN question_text LIKE '%沟通%' OR question_text LIKE '%跨部门%' THEN '软技能-沟通与协作'
  WHEN question_text LIKE '%管理%' OR question_text LIKE '%Leader%' OR question_text LIKE '%带人%' THEN '软技能-管理与领导力'
  WHEN question_text LIKE '%项目%' OR question_text LIKE '%难点%' OR question_text LIKE '%挑战%' OR question_text LIKE '%负责%' THEN '软技能-项目深度'
  ELSE '软技能-其他'
END
WHERE question_type = '软技能';

COMMIT;
