"""推理过程数据格式适配器 - 将新的追踪数据转换为前端期望的格式"""
import json
from typing import Dict, List, Any, Optional
from backend.services.storage.reasoning_trace_service import reasoning_trace_service


class ReasoningTraceAdapter:
    """将推理追踪数据适配为前端渲染格式"""
    
    @staticmethod
    def convert_to_thinking_format(session_id: str) -> List[Dict[str, Any]]:
        """
        将推理会话转换为前端期望的 thinking 数组格式
        
        前端期望格式:
        [
            {
                "thought": "思考内容",
                "action": "工具名称",
                "toolArgs": {"key": "value"},
                "tools": [
                    {
                        "name": "工具名",
                        "args": {"key": "value"},
                        "result": "结果",
                        "observation": "观察"
                    }
                ]
            }
        ]
        """
        trace = reasoning_trace_service.get_full_trace(session_id)
        if not trace:
            return []
        
        steps = trace.get('steps', [])
        tool_calls = trace.get('tool_calls', [])
        
        # 按 step_id 索引工具调用
        tool_calls_by_step = {}
        for call in tool_calls:
            step_id = call.get('step_id')
            if step_id:
                if step_id not in tool_calls_by_step:
                    tool_calls_by_step[step_id] = []
                tool_calls_by_step[step_id].append(call)
        
        thinking_array = []
        
        for step in steps:
            step_type = step.get('step_type', '')
            step_id = step.get('step_id')
            
            # 构建单个思考步骤
            think_item = {}
            
            # 添加思考内容
            if step.get('thinking'):
                think_item['thought'] = step['thinking']
            
            # 添加推理内容（如果有）
            if step.get('reasoning_content'):
                think_item['reasoning'] = step['reasoning_content']
            
            # 添加行动信息
            if step.get('action_name'):
                think_item['action'] = step['action_name']
                
                # 解析工具参数
                if step.get('action_input'):
                    try:
                        think_item['toolArgs'] = json.loads(step['action_input']) \
                            if isinstance(step['action_input'], str) else step['action_input']
                    except:
                        think_item['toolArgs'] = {'input': step['action_input']}
            
            # 添加观察结果
            if step.get('observation'):
                think_item['observation'] = step['observation']
            
            # 添加工具结果
            if step.get('tool_result'):
                think_item['result'] = step['tool_result']
            
            # 添加关联的工具调用
            if step_id and step_id in tool_calls_by_step:
                think_item['tools'] = []
                for tool_call in tool_calls_by_step[step_id]:
                    tool_item = {
                        'name': tool_call.get('tool_name', ''),
                        'args': {},
                        'result': tool_call.get('tool_output', ''),
                        'observation': tool_call.get('tool_output', '')
                    }
                    
                    # 解析工具输入参数
                    if tool_call.get('tool_input'):
                        try:
                            tool_item['args'] = json.loads(tool_call['tool_input']) \
                                if isinstance(tool_call['tool_input'], str) else tool_call['tool_input']
                        except:
                            tool_item['args'] = {'input': tool_call['tool_input']}
                    
                    think_item['tools'].append(tool_item)
            
            if think_item:  # 只添加非空项
                thinking_array.append(think_item)
        
        return thinking_array
    
    @staticmethod
    def convert_to_message_format(session_id: str, role: str = 'assistant') -> Dict[str, Any]:
        """
        将推理会话转换为完整的消息格式
        
        返回格式:
        {
            "role": "assistant",
            "content": "最终答案",
            "thinking": [...],
            "timestamp": "2026-03-18T10:30:00"
        }
        """
        trace = reasoning_trace_service.get_full_trace(session_id)
        if not trace:
            return {}
        
        session = trace.get('session', {})
        result = trace.get('result', {})
        
        message = {
            'role': role,
            'content': result.get('final_answer', ''),
            'thinking': ReasoningTraceAdapter.convert_to_thinking_format(session_id),
            'timestamp': session.get('created_at', ''),
            'metadata': {
                'session_id': session_id,
                'total_steps': session.get('total_steps', 0),
                'total_tokens': session.get('total_tokens', 0),
                'reasoning_tokens': session.get('reasoning_tokens', 0),
                'completion_tokens': session.get('completion_tokens', 0),
                'duration_seconds': session.get('duration_seconds', 0),
                'model': f"{session.get('model_name', '')}/{session.get('model_version', '')}"
            }
        }
        
        return message
    
    @staticmethod
    def convert_from_thinking_format(thinking_array: List[Dict[str, Any]], 
                                     user_id: str, question_text: str = None) -> str:
        """
        从前端的 thinking 数组格式转换为推理追踪格式并保存
        
        返回: session_id
        """
        session_id = reasoning_trace_service.create_session(
            user_id=user_id,
            question_text=question_text,
            model_name='deepseek',
            model_version='v3',
            chat_type='chat'
        )
        
        for step_num, think_item in enumerate(thinking_array, 1):
            step_type = 'thinking'
            
            # 确定步骤类型
            if think_item.get('action') or think_item.get('tools'):
                step_type = 'action'
            elif think_item.get('observation') or think_item.get('result'):
                step_type = 'observation'
            
            # 添加步骤
            step_id = reasoning_trace_service.add_step(
                session_id=session_id,
                step_number=step_num,
                step_type=step_type,
                thinking=think_item.get('thought'),
                action_name=think_item.get('action'),
                action_input=json.dumps(think_item.get('toolArgs', {}), ensure_ascii=False),
                observation=think_item.get('observation'),
                tool_result=think_item.get('result'),
                reasoning_content=think_item.get('reasoning'),
                status='success'
            )
            
            # 添加工具调用
            for tool in think_item.get('tools', []):
                reasoning_trace_service.record_tool_call(
                    session_id=session_id,
                    tool_name=tool.get('name', ''),
                    tool_input=json.dumps(tool.get('args', {}), ensure_ascii=False),
                    tool_output=tool.get('result', ''),
                    status='success',
                    step_id=step_id
                )
        
        # 保存结果
        final_answer = thinking_array[-1].get('observation') or thinking_array[-1].get('result', '') \
            if thinking_array else ''
        
        reasoning_trace_service.save_result(
            session_id=session_id,
            final_answer=final_answer,
            answer_type='text',
            confidence_score=0.9
        )
        
        # 更新会话状态
        reasoning_trace_service.update_session_status(
            session_id=session_id,
            status='completed',
            total_steps=len(thinking_array)
        )
        
        return session_id
    
    @staticmethod
    def migrate_chat_history_to_traces(messages: List[Dict[str, Any]], 
                                       user_id: str, session_id: str = None) -> List[str]:
        """
        将聊天历史中的 thinking 数据迁移到推理追踪系统
        
        返回: 创建的 session_id 列表
        """
        created_sessions = []
        
        for msg in messages:
            if msg.get('role') == 'assistant' and msg.get('thinking'):
                trace_session_id = ReasoningTraceAdapter.convert_from_thinking_format(
                    thinking_array=msg['thinking'],
                    user_id=user_id,
                    question_text=msg.get('content', '')[:200]
                )
                created_sessions.append(trace_session_id)
        
        return created_sessions


# 便捷函数
def get_thinking_format(session_id: str) -> List[Dict[str, Any]]:
    """获取推理追踪的前端格式"""
    return ReasoningTraceAdapter.convert_to_thinking_format(session_id)


def get_message_format(session_id: str, role: str = 'assistant') -> Dict[str, Any]:
    """获取推理追踪的消息格式"""
    return ReasoningTraceAdapter.convert_to_message_format(session_id, role)


def save_thinking_format(thinking_array: List[Dict[str, Any]], 
                        user_id: str, question_text: str = None) -> str:
    """保存前端格式的推理过程"""
    return ReasoningTraceAdapter.convert_from_thinking_format(thinking_array, user_id, question_text)


def migrate_chat_history(messages: List[Dict[str, Any]], 
                        user_id: str, session_id: str = None) -> List[str]:
    """迁移聊天历史"""
    return ReasoningTraceAdapter.migrate_chat_history_to_traces(messages, user_id, session_id)
