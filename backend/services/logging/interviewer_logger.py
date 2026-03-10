"""
面试官 Agent 交互日志记录器

功能：
1. 记录每次对话的完整交互过程
2. 保存推理步骤（thinking steps）
3. 记录工具调用详情
4. 按模型名称和日期组织日志文件

日志结构：
interviewer_logs/
├── {model_name}/
│   ├── chat_YYYYMMDD.jsonl          # 每日对话日志
│   ├── thinking_YYYYMMDD.jsonl      # 推理过程详细日志
│   └── tools_YYYYMMDD.jsonl         # 工具调用日志
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.config.config import settings

logger = logging.getLogger(__name__)


class InterviewerLogger:
    """面试官 Agent 交互日志记录器"""
    
    def __init__(self, base_dir: str = "interviewer_logs"):
        """
        初始化日志记录器
        
        Args:
            base_dir: 日志根目录，默认为项目根目录下的 interviewer_logs
        """
        self.project_root = Path(__file__).parent.parent.parent
        self.base_dir = self.project_root / base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取当前使用的模型名称
        self.model_name = self._get_model_name()
        self.model_dir = self.base_dir / self.model_name
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ InterviewerLogger 初始化完成，日志目录: {self.model_dir}")
    
    def _get_model_name(self) -> str:
        """获取当前使用的模型名称，用于创建子目录"""
        model = settings.interviewer_model or settings.llm_model_id
        # 清理模型名称，移除特殊字符
        clean_name = model.replace("/", "_").replace(":", "_").replace(" ", "_")
        return clean_name
    
    def _get_log_path(self, log_type: str) -> Path:
        """
        获取日志文件路径
        
        Args:
            log_type: 日志类型 (chat/thinking/tools)
        
        Returns:
            日志文件路径
        """
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{log_type}_{date_str}.jsonl"
        return self.model_dir / filename
    
    def log_chat(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        ai_response: str,
        thinking_steps: List[Dict],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录完整的对话交互
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            user_message: 用户输入
            ai_response: AI回复
            thinking_steps: 推理步骤列表
            metadata: 额外的元数据（如简历、上下文等）
        """
        try:
            log_path = self._get_log_path("chat")
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "session_id": session_id,
                "user_message": user_message,
                "ai_response": ai_response,
                "response_length": len(ai_response),
                "thinking_steps_count": len(thinking_steps),
                "model": self.model_name,
                "metadata": metadata or {}
            }
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"💾 对话日志已保存: {log_path.name}")
            
        except Exception as e:
            logger.error(f"❌ 保存对话日志失败: {e}", exc_info=True)
    
    def log_thinking(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        thinking_steps: List[Dict]
    ):
        """
        记录详细的推理过程
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            user_message: 用户输入
            thinking_steps: 推理步骤列表，每个步骤包含 {step, thought, action, observation}
        """
        try:
            log_path = self._get_log_path("thinking")
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "session_id": session_id,
                "user_message": user_message,
                "model": self.model_name,
                "thinking_steps": thinking_steps,
                "total_steps": len(thinking_steps)
            }
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"🧠 推理日志已保存: {log_path.name} ({len(thinking_steps)} 步)")
            
        except Exception as e:
            logger.error(f"❌ 保存推理日志失败: {e}", exc_info=True)
    
    def log_tool_call(
        self,
        user_id: str,
        session_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Any,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        记录工具调用详情
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            tool_name: 工具名称
            tool_input: 工具输入参数
            tool_output: 工具输出结果
            success: 是否成功
            error: 错误信息（如果失败）
        """
        try:
            log_path = self._get_log_path("tools")
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output": str(tool_output)[:1000],  # 限制输出长度
                "success": success,
                "error": error,
                "model": self.model_name
            }
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"🔧 工具调用日志已保存: {tool_name}")
            
        except Exception as e:
            logger.error(f"❌ 保存工具调用日志失败: {e}", exc_info=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取日志统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = {
                "model": self.model_name,
                "log_dir": str(self.model_dir),
                "files": {}
            }
            
            for log_type in ["chat", "thinking", "tools"]:
                log_path = self._get_log_path(log_type)
                if log_path.exists():
                    with open(log_path, "r", encoding="utf-8") as f:
                        line_count = sum(1 for _ in f)
                    stats["files"][log_type] = {
                        "path": str(log_path),
                        "entries": line_count
                    }
                else:
                    stats["files"][log_type] = {
                        "path": str(log_path),
                        "entries": 0
                    }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取日志统计失败: {e}", exc_info=True)
            return {}


# 全局单例
_interviewer_logger: Optional[InterviewerLogger] = None


def get_interviewer_logger() -> InterviewerLogger:
    """获取全局 InterviewerLogger 实例"""
    global _interviewer_logger
    if _interviewer_logger is None:
        _interviewer_logger = InterviewerLogger()
    return _interviewer_logger
