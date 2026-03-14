"""
Neo4j 服务层 v2.0
职责：知识图谱存储 + 向量检索（RAG 核心）
节点：Question / Tag / Company / Position / Concept
关系：HAS_TAG / FROM_COMPANY / FOR_POSITION / COVERS_CONCEPT / RELATED_TO / VARIANT_OF
"""
import logging
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from backend.config.config import settings

logger = logging.getLogger(__name__)


class Neo4jService:
    def __init__(self):
        self.uri = settings.neo4j_uri
        self.user = settings.neo4j_username
        self.password = settings.neo4j_password
        self.db_name = settings.neo4j_database
        self.driver = None
        self.available = False   # 连接失败时降级运行，不阻塞启动

        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                connection_timeout=5,    # 5 秒超时，避免长时间阻塞
                max_connection_lifetime=3600
            )
            self.check_connection()
            self._create_indices()
            self.available = True
        except Exception as e:
            logger.warning(
                f"⚠️  Neo4j 连接失败（降级运行，向量检索/图关系功能不可用）: {e}\n"
                f"    → 系统将继续启动，SQLite 题库功能正常可用。"
            )
            # 不 raise，允许系统降级运行

    def _check_available(self, op_name: str = "") -> bool:
        """方法调用前检查连接可用性，不可用时打印一次警告并返回 False"""
        if not self.available:
            logger.debug(f"Neo4j 不可用，跳过操作: {op_name}")
            return False
        return True

    def close(self):
        if self.driver:
            self.driver.close()

    def check_connection(self):
        with self.driver.session(database=self.db_name) as session:
            session.run("RETURN 1")
            logger.info("✅ Neo4j 连接成功")

    def _create_indices(self):
        """创建约束和向量索引"""
        statements = [
            # 唯一性约束
            "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:Question) REQUIRE q.id IS UNIQUE",
            "CREATE CONSTRAINT tag_name_unique IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT company_name_unique IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT position_name_unique IF NOT EXISTS FOR (p:Position) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
            # 向量索引（1024 维，DashScope text-embedding-v3）
            """
            CREATE VECTOR INDEX question_embeddings IF NOT EXISTS
            FOR (n:Question) ON (n.embedding)
            OPTIONS {indexConfig: {
              `vector.dimensions`: 1024,
              `vector.similarity_function`: 'cosine'
            }}
            """,
        ]
        with self.driver.session(database=self.db_name) as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    # 索引/约束已存在时不报错
                    if "already exists" not in str(e).lower():
                        logger.warning(f"索引创建警告: {e}")
        logger.info("✅ Neo4j 索引/约束检查完成")

    # ===========================================================
    # 写入：添加题目节点及关联
    # ===========================================================
    def delete_questions_by_source_url(self, source_url: str) -> int:
        """按 source_url 删除 Neo4j 中的题目节点及关联边。返回删除的节点数。"""
        if not self._check_available("delete_questions_by_source_url"):
            return 0
        if not source_url:
            return 0
        query = """
        MATCH (q:Question) WHERE q.source = $source_url
        WITH collect(q) AS to_delete
        FOREACH (n IN to_delete | DETACH DELETE n)
        RETURN size(to_delete) AS cnt
        """
        try:
            logger.info("[Graph] 保存/删除: delete_questions_by_source_url source_url=%s", source_url[:80])
            with self.driver.session(database=self.db_name) as session:
                result = session.run(query, source_url=source_url)
                record = result.single()
                cnt = record["cnt"] if record else 0
                logger.info("[Graph] 保存/删除: delete_questions_by_source_url 完成，删除 %d 道", cnt)
                return cnt
        except Exception as e:
            logger.warning("Neo4j 删除题目失败 %s: %s", source_url[:50], e)
            return 0

    def delete_questions_by_source_platform(self, platforms: List[str]) -> int:
        """按 source_platform 删除 Neo4j 中的题目节点。用于清除所有时的兜底。"""
        if not self._check_available("delete_questions_by_source_platform"):
            return 0
        if not platforms:
            return 0
        query = """
        MATCH (q:Question) WHERE q.source_platform IN $platforms
        WITH collect(q) AS to_delete
        FOREACH (n IN to_delete | DETACH DELETE n)
        RETURN size(to_delete) AS cnt
        """
        try:
            logger.info("[Graph] 保存/删除: delete_questions_by_source_platform platforms=%s", platforms)
            with self.driver.session(database=self.db_name) as session:
                result = session.run(query, platforms=platforms)
                record = result.single()
                cnt = record["cnt"] if record else 0
                logger.info("[Graph] 保存/删除: delete_questions_by_source_platform 完成，删除 %d 道", cnt)
                return cnt
        except Exception as e:
            logger.warning("Neo4j 按平台删除题目失败: %s", e)
            return 0

    def add_question(self, q_id: str, text: str, answer: str,
                     tags: List[str], embedding: List[float],
                     metadata: Dict = None) -> bool:
        if not self._check_available("add_question"):
            return False
        """
        写入题目节点，关联 Tag / Company / Position。
        metadata 支持: difficulty, source, company, position, question_type, source_platform
        """
        meta = metadata or {}
        source = meta.get("source", "")
        difficulty = meta.get("difficulty", "medium")
        question_type = meta.get("question_type", "技术题")
        source_platform = meta.get("source_platform", "")
        company = meta.get("company", "")
        position = meta.get("position", "")
        raw_answer = meta.get("raw_answer", "")

        query = """
        MERGE (q:Question {id: $q_id})
        SET q.text            = $text,
            q.answer          = $answer,
            q.raw_answer       = $raw_answer,
            q.embedding       = $embedding,
            q.difficulty      = $difficulty,
            q.question_type   = $question_type,
            q.source_platform = $source_platform,
            q.source          = $source,
            q.company         = $company,
            q.position        = $position,
            q.created_at      = datetime()

        WITH q
        UNWIND $tags AS tag_name
        MERGE (t:Tag {name: tag_name})
        MERGE (q)-[:HAS_TAG]->(t)

        WITH q
        WHERE $company <> ''
        MERGE (c:Company {name: $company})
        MERGE (q)-[:FROM_COMPANY]->(c)

        WITH q
        WHERE $position <> ''
        MERGE (p:Position {name: $position})
        MERGE (q)-[:FOR_POSITION]->(p)
        """
        logger.info("[Graph] 保存: add_question q_id=%s tags=%s", q_id, tags[:5] if tags else [])
        with self.driver.session(database=self.db_name) as session:
            session.run(query,
                        q_id=q_id, text=text, answer=answer, raw_answer=raw_answer,
                        tags=tags, embedding=embedding,
                        difficulty=difficulty, question_type=question_type,
                        source_platform=source_platform, source=source,
                        company=company, position=position)
        logger.info("[Graph] 保存: add_question 完成 q_id=%s", q_id)

    def link_concept(self, q_id: str, concept_name: str, description: str = ""):
        if not self._check_available("link_concept"):
            return
        """关联题目与知识点概念（Concept节点）"""
        query = """
        MATCH (q:Question {id: $q_id})
        MERGE (c:Concept {name: $concept_name})
        SET c.description = $description
        MERGE (q)-[:COVERS_CONCEPT]->(c)
        """
        logger.info("[Graph] 保存: link_concept q_id=%s concept_name=%s", q_id, concept_name)
        with self.driver.session(database=self.db_name) as session:
            session.run(query, q_id=q_id, concept_name=concept_name, description=description)
        logger.info("[Graph] 保存: link_concept 完成")

    def link_variant(self, source_id: str, target_id: str):
        if not self._check_available("link_variant"):
            return
        """标记两道题是换个问法的变体关系"""
        query = """
        MATCH (a:Question {id: $source_id}), (b:Question {id: $target_id})
        MERGE (a)-[:VARIANT_OF]->(b)
        """
        logger.info("[Graph] 保存: link_variant source_id=%s target_id=%s", source_id, target_id)
        with self.driver.session(database=self.db_name) as session:
            session.run(query, source_id=source_id, target_id=target_id)
        logger.info("[Graph] 保存: link_variant 完成")

    # ===========================================================
    # 向量检索（RAG 核心）
    # ===========================================================
    def search_similar(self, query_embedding: List[float], top_k: int = 5,
                       score_threshold: float = 0.75,
                       exclude_ids: List[str] = None) -> List[Dict]:
        """
        根据向量找相似题目（查重 / 举一反三）。
        exclude_ids: 排除的题目ID列表（避免推荐当前题目自身）
        """
        if not self._check_available("search_similar"):
            return []
        if not query_embedding:
            return []

        exclude = exclude_ids or []
        query = """
        CALL db.index.vector.queryNodes('question_embeddings', $top_k, $embedding)
        YIELD node, score
        WHERE score >= $threshold AND NOT node.id IN $exclude_ids
        RETURN node.id AS id, node.text AS text, node.answer AS answer,
               node.difficulty AS difficulty, node.company AS company,
               node.question_type AS question_type, score
        ORDER BY score DESC
        """
        logger.info("[Graph] 搜索: search_similar top_k=%d threshold=%.2f exclude_ids=%s",
                    top_k, score_threshold, exclude[:5] if exclude else [])
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, top_k=top_k + len(exclude),
                                 embedding=query_embedding,
                                 threshold=score_threshold,
                                 exclude_ids=exclude)
            rows = [record.data() for record in result][:top_k]
        logger.info("[Graph] 搜索: search_similar 返回 %d 条", len(rows))
        return rows

    def check_duplicate(self, embedding: List[float], threshold: float = 0.92) -> Optional[Dict]:
        if not self._check_available("check_duplicate"):
            return None
        """
        入库时查重：若有相似度 > threshold 的题目则返回，否则返回 None。
        """
        if not embedding:
            return None
        logger.info("[Graph] 搜索: check_duplicate threshold=%.2f", threshold)
        results = self.search_similar(embedding, top_k=1, score_threshold=threshold)
        out = results[0] if results else None
        logger.info("[Graph] 搜索: check_duplicate %s", "发现重复" if out else "无重复")
        return out

    # ===========================================================
    # 图关系推荐
    # ===========================================================
    def recommend_by_tag(self, tag: str, limit: int = 5,
                         exclude_ids: List[str] = None) -> List[Dict]:
        if not self._check_available("recommend_by_tag"):
            return []
        """按标签推荐题目（随机）"""
        exclude = exclude_ids or []
        query = """
        MATCH (t:Tag {name: $tag})<-[:HAS_TAG]-(q:Question)
        WHERE NOT q.id IN $exclude_ids
        RETURN q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.company AS company
        ORDER BY rand()
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: recommend_by_tag tag=%s limit=%d", tag, limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, tag=tag, limit=limit, exclude_ids=exclude)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: recommend_by_tag 返回 %d 条", len(rows))
        return rows

    def recommend_by_company(self, company: str, limit: int = 5,
                             exclude_ids: List[str] = None) -> List[Dict]:
        if not self._check_available("recommend_by_company"):
            return []
        """按公司推荐历史真题"""
        exclude = exclude_ids or []
        query = """
        MATCH (c:Company {name: $company})<-[:FROM_COMPANY]-(q:Question)
        WHERE NOT q.id IN $exclude_ids
        RETURN q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.question_type AS question_type
        ORDER BY rand()
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: recommend_by_company company=%s limit=%d", company, limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, company=company, limit=limit, exclude_ids=exclude)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: recommend_by_company 返回 %d 条", len(rows))
        return rows

    def get_variants(self, q_id: str) -> List[Dict]:
        if not self._check_available("get_variants"):
            return []
        """获取某题的所有换个问法变体"""
        logger.info("[Graph] 搜索: get_variants q_id=%s", q_id)
        query = """
        MATCH (q:Question {id: $q_id})-[:VARIANT_OF]-(v:Question)
        RETURN v.id AS id, v.text AS text, v.difficulty AS difficulty
        """
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, q_id=q_id)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_variants 返回 %d 条", len(rows))
        return rows

    def get_questions_by_tags(self, tags: List[str], limit: int = 10,
                              exclude_ids: List[str] = None) -> List[Dict]:
        if not self._check_available("get_questions_by_tags"):
            return []
        """按多个标签（OR）查找题目"""
        exclude = exclude_ids or []
        query = """
        MATCH (q:Question)-[:HAS_TAG]->(t:Tag)
        WHERE t.name IN $tags AND NOT q.id IN $exclude_ids
        RETURN DISTINCT q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.company AS company
        ORDER BY rand()
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: get_questions_by_tags tags=%s limit=%d", tags[:5], limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, tags=tags, limit=limit, exclude_ids=exclude)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_questions_by_tags 返回 %d 条", len(rows))
        return rows

    def get_question_by_id(self, q_id: str) -> Optional[Dict]:
        if not self._check_available("get_question_by_id"):
            return None
        """通过ID获取题目详情"""
        query = """
        MATCH (q:Question {id: $q_id})
        OPTIONAL MATCH (q)-[:HAS_TAG]->(t:Tag)
        RETURN q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.company AS company,
               q.question_type AS question_type,
               q.source_platform AS source_platform,
               collect(t.name) AS tags
        """
        logger.info("[Graph] 搜索: get_question_by_id q_id=%s", q_id)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, q_id=q_id)
            record = result.single()
            out = record.data() if record else None
        logger.info("[Graph] 搜索: get_question_by_id %s", "命中" if out else "未命中")
        return out

    def get_unseen_questions(self, tech_stack: List[str], seen_ids: List[str],
                             limit: int = 5) -> List[Dict]:
        if not self._check_available("get_unseen_questions"):
            return []
        """获取用户未做过的题目（按技术栈标签）"""
        query = """
        MATCH (q:Question)-[:HAS_TAG]->(t:Tag)
        WHERE t.name IN $tags AND NOT q.id IN $seen_ids
        RETURN DISTINCT q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.company AS company
        ORDER BY rand()
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: get_unseen_questions tech_stack=%s limit=%d", tech_stack[:5] if tech_stack else [], limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, tags=tech_stack or [], seen_ids=seen_ids, limit=limit)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_unseen_questions 返回 %d 条", len(rows))
        return rows

    # ===========================================================
    # GraphRAG：Concept 相关查询（延伸知识点场景）
    # ===========================================================
    def get_concepts_by_question(self, q_id: str) -> List[Dict]:
        """获取某题目覆盖的知识点概念（Concept 节点）"""
        if not self._check_available("get_concepts_by_question"):
            return []
        logger.info("[Graph] 搜索: get_concepts_by_question q_id=%s", q_id)
        query = """
        MATCH (q:Question {id: $q_id})-[:COVERS_CONCEPT]->(c:Concept)
        RETURN c.name AS name, c.description AS description
        """
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, q_id=q_id)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_concepts_by_question 返回 %d 条", len(rows))
        return rows

    def get_related_concepts(self, concept_name: str, limit: int = 5) -> List[Dict]:
        """
        获取与某概念相关的其他概念（GraphRAG）。
        策略：① 通过 RELATED_TO 关系；② 若无则通过共现（同题目覆盖的其他 Concept）
        """
        if not self._check_available("get_related_concepts"):
            return []
        # 策略1：RELATED_TO 关系
        query1 = """
        MATCH (c:Concept {name: $concept_name})-[:RELATED_TO]-(other:Concept)
        RETURN DISTINCT other.name AS name, other.description AS description
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: get_related_concepts concept_name=%s limit=%d", concept_name, limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query1, concept_name=concept_name, limit=limit)
            rows = [record.data() for record in result]
        if rows:
            logger.info("[Graph] 搜索: get_related_concepts (RELATED_TO) 返回 %d 条", len(rows))
            return rows
        # 策略2：共现（同题目覆盖的其他 Concept，排除自身）
        query2 = """
        MATCH (c:Concept {name: $concept_name})<-[:COVERS_CONCEPT]-(q:Question)-[:COVERS_CONCEPT]->(other:Concept)
        WHERE other.name <> $concept_name
        RETURN other.name AS name, other.description AS description
        ORDER BY rand()
        LIMIT $limit
        """
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query2, concept_name=concept_name, limit=limit)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_related_concepts (共现) 返回 %d 条", len(rows))
        return rows

    def get_questions_by_concept(self, concept_name: str, limit: int = 5,
                                 exclude_ids: List[str] = None) -> List[Dict]:
        """获取覆盖某知识点的题目（RAG 题目检索）"""
        if not self._check_available("get_questions_by_concept"):
            return []
        exclude = exclude_ids or []
        query = """
        MATCH (c:Concept {name: $concept_name})<-[:COVERS_CONCEPT]-(q:Question)
        WHERE NOT q.id IN $exclude_ids
        RETURN q.id AS id, q.text AS text, q.answer AS answer,
               q.difficulty AS difficulty, q.company AS company
        ORDER BY rand()
        LIMIT $limit
        """
        logger.info("[Graph] 搜索: get_questions_by_concept concept_name=%s limit=%d", concept_name, limit)
        with self.driver.session(database=self.db_name) as session:
            result = session.run(query, concept_name=concept_name,
                                exclude_ids=exclude, limit=limit)
            rows = [record.data() for record in result]
        logger.info("[Graph] 搜索: get_questions_by_concept 返回 %d 条", len(rows))
        return rows


# 单例
neo4j_service = Neo4jService()
