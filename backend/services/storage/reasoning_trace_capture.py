"""推理过程捕获集成模块 - 自动记录 Agent 的推理过程"""
import logging
import time
import json
from typing import Dict, Any, Optional
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

logger = logging.getLogger(__name__)


class ReasoningTraceCapture:
    """自动捕获和记录推理过程"""
    
    def __init__(self, user_id: str, question_id: str = None, 
                 question_text: str = None, interview_session_id: str = None):
        self.user_id = user_id
        self.question_id = question_id
        self.question_text = question_text
        self.interview_session_id = interview_session_id
        self.session_id = None
        self.step_count = 0
        self.start_time = None
        self.step_start_time = None
    
    def start_session(self, model_name: str = "deepseek", model_version: str = "v3",
                     chat_type: str = "chat", metadata: Dict = None) -> str:
        """开始推理会话"""
        self.start_time = time.time()
        self.session_id = reasoning_trace_service.create_session(
            user_id=self.user_id,
            question_id=self.question_id,
            question_text=self.question_text,
            interview_session_id=self.interview_session_id,
            model_name=model_name,
            model_version=model_version,
            chat_type=chat_type,
            metadata=metadata
        )
        return self.session_id
    
    def record_thinking(self, thinking: str):
        """记录思考过程"""
        if not self.session_id:
            return
        
        self.step_count += 1
        self.step_start_time = time.time()
        
        reasoning_trace_service.add_step(
            session_id=self.session_id,
            step_number=self.step_count,
            step_type="thinking",
            thinking=thinking,
            status="success"
        )
        logger.debug(f"记录思考步骤 {self.step_count}: {thinking[:100]}")
    
    def record_action(self, action_name: str, action_input: str = None, 
                     action_type: str = "tool_call") -> str:
        """记录行动"""
        if not self.session_id:
            return None
        
        self.step_count += 1
        self.step_start_time = time.time()
        
        step_id = reasoning_trace_service.add_step(
            session_id=self.session_id,
            step_number=self.step_count,
            step_type="action",
            action_type=action_type,
            action_name=action_name,
            action_input=action_input,
            status="in_progress"
        )
        logger.debug(f"记录行动步骤 {self.step_count}: {action_name}")
        return step_id
    
    def record_observation(self, observation: str, tool_result: str = None, 
                          step_id: str = None, tokens_used: int = 0):
        """记录观察结果"""
        if not self.session_id:
            return
        
        duration_ms = int((time.time() - self.step_start_time) * 1000) if self.step_start_time else 0
        
        if step_id:
            # 更新现有步骤
            with reasoning_trace_service._get_conn() as conn:
                conn.execute("""UPDATE reasoning_steps 
                    SET observation = ?, tool_result = ?, tokens_used = ?, 
                        duration_ms = ?, status = 'success'
                    WHERE step_id = ?""",
                    (observation, tool_result, tokens_used, duration_ms, step_id))
                conn.commit()
        else:
            # 创建新步骤
            self.step_count += 1
            reasoning_trace_service.add_step(
                session_id=self.session_id,
                step_number=self.step_count,
                step_type="observation",
                observation=observation,
                tool_result=tool_result,
                tokens_used=tokens_used,
                duration_ms=duration_ms,
                status="success"
            )
        
        logger.debug(f"记录观察: {observation[:100]}")
    
    def record_tool_call(self, tool_name: str, tool_input: str = None,
                        tool_output: str = None, execution_time_ms: int = 0,
                        status: str = "success", error_msg: str = None, step_id: str = None):
        """记录工具调用"""
        if not self.session_id:
            return
        
        reasoning_trace_service.record_tool_call(
            session_id=self.session_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            execution_time_ms=execution_time_ms,
            status=status,
            error_msg=error_msg,
            step_id=step_id
        )
        logger.debug(f"记录工具调用: {tool_name}")
    
    def finish_session(self, final_answer: str, answer_type: str = "text",
                      confidence_score: float = 0.0, reasoning_summary: str = None,
                      key_insights: list = None):
        """完成推理会话"""
        if not self.session_id:
            return
        
        duration_seconds = time.time() - self.start_time if self.start_time else 0
        
        # 更新会话状态
        reasoning_trace_service.update_session_status(
            session_id=self.session_id,
            status="completed",
            duration_seconds=duration_seconds,
            total_steps=self.step_count
        )
        
        # 保存结果
        reasoning_trace_service.save_result(
            session_id=self.session_id,
            final_answer=final_answer,
            answer_type=answer_type,
            confidence_score=confidence_score,
            reasoning_summary=reasoning_summary,
            key_insights=key_insights
        )
        
        logger.info(f"完成推理会话 {self.session_id}: {self.step_count} 步, {duration_seconds:.2f}秒")
        return self.session_id
    
    def get_trace(self) -> Dict:
        """获取完整推理追踪"""
        if not self.session_id:
            return None
        return reasoning_trace_service.get_full_trace(self.session_id)
    
    def export_json(self) -> str:
        """导出为 JSON"""
        if not self.session_id:
            return None
        return reasoning_trace_service.export_trace_json(self.session_id)


def create_trace_capture(user_id: str, question_id: str = None,
                        question_text: str = None, 
                        interview_session_id: str = None) -> ReasoningTraceCapture:
    """工厂函数：创建推理追踪捕获器"""
    return ReasoningTraceCapture(
        user_id=user_id,
        question_id=question_id,
        question_text=question_text,
        interview_session_id=interview_session_id
    )
