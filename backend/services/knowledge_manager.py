"""
Knowledge Manager 服务
职责：知识管理（无 LLM）
- 元信息提取
- 知识结构化
- 查重
- 双写入库
"""
import logging
from backend.config.config import settings
from backend.tools.knowledge_manager_tools import (
    MetaExtractor,
    KnowledgeStructurer,
    DuplicateChecker,
    BaseManager
)

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """
    知识管理器（纯服务，无 LLM）
    
    职责：
    - 元信息提取
    - 知识结构化
    - 查重
    - 双写入库
    """
    
    def __init__(self):
        self.meta_extractor = MetaExtractor()
        self.knowledge_structurer = KnowledgeStructurer()
        self.duplicate_checker = DuplicateChecker()
        self.base_manager = BaseManager()
        
        logger.info("✅ Knowledge Manager 初始化完成")
        logger.info("   - 元信息提取器")
        logger.info("   - 知识结构化器")
        logger.info("   - 查重器")
        logger.info("   - 数据库管理器")
    
    def process_question(self, question_data: dict) -> dict:
        """处理单个题目"""
        # 1. 提取元信息
        meta = self.meta_extractor.extract(question_data)
        
        # 2. 结构化知识
        structured = self.knowledge_structurer.structure(meta)
        
        # 3. 查重
        is_duplicate = self.duplicate_checker.check(structured)
        
        # 4. 入库
        if not is_duplicate:
            self.base_manager.save(structured)
        
        return structured


# 全局实例
knowledge_manager = KnowledgeManager()
