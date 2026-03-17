"""迁移历史推理数据到新的追踪系统"""
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_from_deepseek_adapter_log(log_file: str):
    """从 DeepSeek Adapter 的日志文件迁移推理数据"""
    logger.info(f"开始迁移: {log_file}")
    
    migrated_count = 0
    error_count = 0
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                
                # 提取基本信息
                user_id = data.get('user_id', 'unknown')
                question_text = data.get('question', '')
                model_name = data.get('model', 'deepseek')
                
                # 创建会话
                session_id = reasoning_trace_service.create_session(
                    user_id=user_id,
                    question_text=question_text,
                    model_name=model_name,
                    model_version='v3',
                    chat_type='chat'
                )
                
                # 提取推理过程
                reasoning_content = data.get('reasoning_content', '')
                response = data.get('response', '')
                
                # 添加推理步骤
                if reasoning_content:
                    reasoning_trace_service.add_step(
                        session_id=session_id,
                        step_number=1,
                        step_type='thinking',
                        thinking=reasoning_content,
                        reasoning_content=reasoning_content,
                        status='success'
                    )
                
                # 添加响应步骤
                if response:
                    reasoning_trace_service.add_step(
                        session_id=session_id,
                        step_number=2,
                        step_type='observation',
                        observation=response,
                        status='success'
                    )
                
                # 保存结果
                reasoning_trace_service.save_result(
                    session_id=session_id,
                    final_answer=response,
                    answer_type='text',
                    confidence_score=0.8
                )
                
                # 更新会话状态
                reasoning_trace_service.update_session_status(
                    session_id=session_id,
                    status='completed',
                    total_steps=2,
                    total_tokens=data.get('total_tokens', 0),
                    reasoning_tokens=data.get('reasoning_tokens', 0),
                    completion_tokens=data.get('completion_tokens', 0)
                )
                
                migrated_count += 1
                if migrated_count % 100 == 0:
                    logger.info(f"已迁移 {migrated_count} 条记录")
                
            except Exception as e:
                error_count += 1
                logger.error(f"第 {line_num} 行迁移失败: {e}")
                continue
    
    logger.info(f"迁移完成: 成功 {migrated_count} 条, 失败 {error_count} 条")
    return migrated_count, error_count


def migrate_from_generic_jsonl(log_file: str, format_type: str = 'auto'):
    """从通用 JSONL 格式迁移推理数据
    
    支持的格式:
    - auto: 自动检测
    - react: ReAct 格式 (thinking, action, observation)
    - simple: 简单格式 (question, answer)
    """
    logger.info(f"开始迁移 (格式: {format_type}): {log_file}")
    
    migrated_count = 0
    error_count = 0
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                
                # 自动检测格式
                if format_type == 'auto':
                    if 'steps' in data or 'thinking' in data:
                        detected_format = 'react'
                    else:
                        detected_format = 'simple'
                else:
                    detected_format = format_type
                
                # 根据格式迁移
                if detected_format == 'react':
                    session_id = _migrate_react_format(data)
                else:
                    session_id = _migrate_simple_format(data)
                
                if session_id:
                    migrated_count += 1
                    if migrated_count % 100 == 0:
                        logger.info(f"已迁移 {migrated_count} 条记录")
                
            except Exception as e:
                error_count += 1
                logger.error(f"第 {line_num} 行迁移失败: {e}")
                continue
    
    logger.info(f"迁移完成: 成功 {migrated_count} 条, 失败 {error_count} 条")
    return migrated_count, error_count


def _migrate_react_format(data: Dict[str, Any]) -> str:
    """迁移 ReAct 格式的数据"""
    user_id = data.get('user_id', 'unknown')
    question_text = data.get('question', data.get('question_text', ''))
    model_name = data.get('model', data.get('model_name', 'deepseek'))
    
    # 创建会话
    session_id = reasoning_trace_service.create_session(
        user_id=user_id,
        question_id=data.get('question_id'),
        question_text=question_text,
        interview_session_id=data.get('session_id'),
        model_name=model_name,
        model_version=data.get('model_version', 'v3'),
        chat_type=data.get('chat_type', 'chat')
    )
    
    # 添加步骤
    steps = data.get('steps', [])
    for i, step in enumerate(steps, 1):
        reasoning_trace_service.add_step(
            session_id=session_id,
            step_number=i,
            step_type=step.get('type', 'unknown'),
            thinking=step.get('thinking'),
            action_type=step.get('action_type'),
            action_name=step.get('action', step.get('action_name')),
            action_input=step.get('action_input'),
            observation=step.get('observation'),
            tool_result=step.get('tool_result'),
            reasoning_content=step.get('reasoning_content'),
            tokens_used=step.get('tokens', 0),
            duration_ms=step.get('duration_ms', 0),
            status=step.get('status', 'success')
        )
    
    # 保存结果
    result = data.get('result', {})
    if result or data.get('answer'):
        reasoning_trace_service.save_result(
            session_id=session_id,
            final_answer=result.get('answer', data.get('answer', '')),
            answer_type=result.get('type', 'text'),
            confidence_score=result.get('confidence', 0.8),
            reasoning_summary=result.get('summary'),
            key_insights=result.get('insights', [])
        )
    
    # 更新会话状态
    reasoning_trace_service.update_session_status(
        session_id=session_id,
        status=data.get('status', 'completed'),
        total_steps=len(steps),
        total_tokens=data.get('total_tokens', 0),
        reasoning_tokens=data.get('reasoning_tokens', 0),
        completion_tokens=data.get('completion_tokens', 0),
        duration_seconds=data.get('duration_seconds')
    )
    
    return session_id


def _migrate_simple_format(data: Dict[str, Any]) -> str:
    """迁移简单格式的数据"""
    user_id = data.get('user_id', 'unknown')
    question_text = data.get('question', data.get('question_text', ''))
    answer = data.get('answer', data.get('response', ''))
    
    # 创建会话
    session_id = reasoning_trace_service.create_session(
        user_id=user_id,
        question_text=question_text,
        model_name=data.get('model', 'deepseek'),
        model_version='v3',
        chat_type='chat'
    )
    
    # 添加单个步骤
    reasoning_trace_service.add_step(
        session_id=session_id,
        step_number=1,
        step_type='observation',
        observation=answer,
        status='success'
    )
    
    # 保存结果
    reasoning_trace_service.save_result(
        session_id=session_id,
        final_answer=answer,
        answer_type='text',
        confidence_score=0.8
    )
    
    # 更新会话状态
    reasoning_trace_service.update_session_status(
        session_id=session_id,
        status='completed',
        total_steps=1,
        total_tokens=data.get('total_tokens', 0)
    )
    
    return session_id


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python migrate_reasoning_data.py <log_file> [format_type]")
        print("format_type: auto (默认), react, simple, deepseek")
        sys.exit(1)
    
    log_file = sys.argv[1]
    format_type = sys.argv[2] if len(sys.argv) > 2 else 'auto'
    
    if not Path(log_file).exists():
        logger.error(f"文件不存在: {log_file}")
        sys.exit(1)
    
    # 根据格式类型选择迁移函数
    if format_type == 'deepseek':
        migrated, errors = migrate_from_deepseek_adapter_log(log_file)
    else:
        migrated, errors = migrate_from_generic_jsonl(log_file, format_type)
    
    logger.info(f"迁移统计: 成功 {migrated} 条, 失败 {errors} 条")


if __name__ == '__main__':
    main()
