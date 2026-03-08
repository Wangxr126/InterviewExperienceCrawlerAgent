"""
知识管理器 (Knowledge Manager)
职责：纯数据管理（不做提取，不做语义查重）
- 构建知识图谱（题目 → 知识点 → 技术栈）
- 双写入库（Neo4j + SQLite）
- 数据库层面去重（只避免完全重复）

注意：
1. 不使用LLM（纯数据操作）
2. 不做语义查重（保留所有相似题目，RAG检索时自然找到）
3. 只避免完全重复（相同question_text + 相同company）
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 尝试导入Neo4j和SQLite服务（如果不可用则降级）
try:
    from backend.services.neo4j_service import neo4j_service
    NEO4J_AVAILABLE = True
except ImportError:
    logger.warning("Neo4j服务不可用，将跳过图谱构建")
    neo4j_service = None
    NEO4J_AVAILABLE = False

try:
    from backend.services.sqlite_service import sqlite_service
    SQLITE_AVAILABLE = True
except ImportError:
    logger.warning("SQLite服务不可用")
    sqlite_service = None
    SQLITE_AVAILABLE = False


class KnowledgeManager:
    """
    知识管理器：纯数据管理服务
    
    职责：
    1. 构建知识图谱
    2. 双写入库（Neo4j + SQLite）
    3. 数据库去重（只避免完全重复）
    
    不做：
    - 不使用LLM
    - 不做语义查重
    - 不提取信息
    """
    
    def __init__(self):
        self.neo4j = neo4j_service if NEO4J_AVAILABLE else None
        self.sqlite = sqlite_service if SQLITE_AVAILABLE else None
        
        if not SQLITE_AVAILABLE:
            logger.error("SQLite服务不可用，Knowledge Manager无法正常工作")
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j服务不可用，将跳过图谱构建")
    
    def process(self, meta: Dict[str, Any], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        处理题目数据
        
        Args:
            meta: 元信息（公司、岗位、难度等）
            questions: 题目列表
        
        Returns:
            处理结果统计
        """
        try:
            result = {
                "success": True,
                "processed_count": 0,
                "graph_nodes_created": 0,
                "db_records_inserted": 0,
                "duplicates_skipped": 0
            }
            
            for question in questions:
                # 1. 检查完全重复（数据库层面）
                if self._is_duplicate(question, meta):
                    result["duplicates_skipped"] += 1
                    logger.info(f"跳过重复题目: {question.get('question_text', '')[:50]}")
                    continue
                
                # 2. 构建知识图谱
                graph_result = self._build_knowledge_graph(question, meta)
                result["graph_nodes_created"] += graph_result.get("nodes_created", 0)
                
                # 3. 写入数据库
                db_result = self._save_to_database(question, meta)
                if db_result:
                    result["db_records_inserted"] += 1
                
                result["processed_count"] += 1
            
            logger.info(f"知识管理完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"知识管理失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "processed_count": 0
            }
    
    def _is_duplicate(self, question: Dict[str, Any], meta: Dict[str, Any]) -> bool:
        """
        检查是否完全重复（数据库层面）
        
        只检查：相同question_text + 相同company
        不做语义查重
        
        Args:
            question: 题目数据
            meta: 元信息
        
        Returns:
            是否重复
        """
        if not SQLITE_AVAILABLE or not self.sqlite:
            return False
            
        try:
            question_text = question.get("question_text", "")
            company = meta.get("company", "")
            
            if not question_text or not company:
                return False
            
            # 查询SQLite
            existing = self.sqlite.query_question(
                question_text=question_text,
                company=company
            )
            
            return existing is not None
            
        except Exception as e:
            logger.error(f"检查重复失败: {e}")
            return False
    
    def _build_knowledge_graph(self, question: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建知识图谱
        
        节点类型：
        - Question: 题目节点
        - KnowledgePoint: 知识点节点
        - Company: 公司节点
        - Position: 岗位节点
        
        关系类型：
        - (Question)-[:BELONGS_TO]->(KnowledgePoint)
        - (Question)-[:ASKED_BY]->(Company)
        - (Question)-[:FOR_POSITION]->(Position)
        
        Args:
            question: 题目数据
            meta: 元信息
        
        Returns:
            创建的节点数量
        """
        if not NEO4J_AVAILABLE or not self.neo4j:
            logger.debug("Neo4j不可用，跳过图谱构建")
            return {"nodes_created": 0}
            
        try:
            nodes_created = 0
            
            # 1. 创建题目节点
            question_node = self.neo4j.create_question_node(question, meta)
            if question_node:
                nodes_created += 1
            
            # 2. 创建知识点节点（从topic_tags提取）
            topic_tags = question.get("topic_tags", [])
            for tag in topic_tags:
                knowledge_node = self.neo4j.create_knowledge_point_node(tag)
                if knowledge_node:
                    nodes_created += 1
                    # 创建关系：题目 → 知识点
                    self.neo4j.create_relationship(
                        question_node, knowledge_node, "BELONGS_TO"
                    )
            
            # 3. 创建公司节点
            company = meta.get("company")
            if company:
                company_node = self.neo4j.create_company_node(company)
                if company_node:
                    nodes_created += 1
                    # 创建关系：题目 → 公司
                    self.neo4j.create_relationship(
                        question_node, company_node, "ASKED_BY"
                    )
            
            # 4. 创建岗位节点
            position = meta.get("position")
            if position:
                position_node = self.neo4j.create_position_node(position)
                if position_node:
                    nodes_created += 1
                    # 创建关系：题目 → 岗位
                    self.neo4j.create_relationship(
                        question_node, position_node, "FOR_POSITION"
                    )
            
            return {"nodes_created": nodes_created}
            
        except Exception as e:
            logger.error(f"构建知识图谱失败: {e}")
            return {"nodes_created": 0}
    
    def _save_to_database(self, question: Dict[str, Any], meta: Dict[str, Any]) -> bool:
        """
        双写入库（Neo4j + SQLite）
        
        Args:
            question: 题目数据
            meta: 元信息
        
        Returns:
            是否成功
        """
        if not SQLITE_AVAILABLE or not self.sqlite:
            logger.error("SQLite不可用，无法保存数据")
            return False
            
        try:
            # 合并数据
            full_data = {**question, **meta}
            
            # 写入SQLite
            sqlite_result = self.sqlite.insert_question(full_data)
            
            # 写入Neo4j（已在_build_knowledge_graph中完成）
            
            return sqlite_result
            
        except Exception as e:
            logger.error(f"写入数据库失败: {e}")
            return False


# 全局实例
knowledge_manager = KnowledgeManager()
