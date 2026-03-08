"""
Miner Agent 服务封装
提供统一的接口供其他模块调用
"""
import logging
from typing import Dict, List, Any, Tuple
from backend.services.crawler.question_extractor import extract_questions_from_post

logger = logging.getLogger(__name__)


class MinerAgent:
    """
    信息挖掘师 Agent
    
    职责：从面经原文中智能挖掘结构化信息
    - 使用LLM进行语义理解（不用正则）
    - 提取元信息（公司、岗位、难度）
    - 提取题目列表（题目、答案、标签）
    """
    
    def extract(
        self,
        content: str,
        platform: str = "nowcoder",
        company: str = "",
        position: str = "",
        business_line: str = "",
        difficulty: str = "",
        source_url: str = "",
        post_title: str = "",
        extraction_source: str = "content"
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
        """
        从面经原文中提取信息
        
        Args:
            content: 面经原文
            platform: 来源平台
            company: 公司
            position: 岗位
            business_line: 业务线
            difficulty: 难度
            source_url: 原帖链接
            post_title: 帖子标题
            extraction_source: 提取来源
        
        Returns:
            (meta, questions, status)
            - meta: 元信息字典
            - questions: 题目列表
            - status: 状态（success/unrelated/parse_error）
        """
        try:
            # 调用底层提取函数
            questions, status = extract_questions_from_post(
                content=content,
                platform=platform,
                company=company,
                position=position,
                business_line=business_line,
                difficulty=difficulty,
                source_url=source_url,
                post_title=post_title,
                extraction_source=extraction_source
            )
            
            # 构建元信息
            meta = {
                "company": company,
                "position": position,
                "business_line": business_line,
                "difficulty": difficulty,
                "source_platform": platform,
                "source_url": source_url,
                "post_title": post_title
            }
            
            return meta, questions, status
            
        except Exception as e:
            logger.error(f"Miner Agent提取失败: {e}")
            return {}, [], "parse_error"


# 全局实例
miner_agent = MinerAgent()
