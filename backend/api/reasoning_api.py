"""推理过程查询 API 端点"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])


@router.get("/sessions")
async def list_reasoning_sessions(
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """列出推理会话"""
    sessions = reasoning_trace_service.list_sessions(
        user_id=user_id,
        limit=limit,
        offset=offset
    )
    return {
        "total": len(sessions),
        "sessions": sessions
    }


@router.get("/sessions/{session_id}")
async def get_reasoning_session(session_id: str):
    """获取推理会话详情"""
    session = reasoning_trace_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions/{session_id}/trace")
async def get_full_trace(session_id: str):
    """获取完整推理追踪"""
    trace = reasoning_trace_service.get_full_trace(session_id)
    if not trace:
        raise HTTPException(status_code=404, detail="会话不存在")
    return trace


@router.get("/sessions/{session_id}/steps")
async def get_reasoning_steps(session_id: str):
    """获取推理步骤"""
    session = reasoning_trace_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    steps = reasoning_trace_service.get_steps(session_id)
    return {
        "session_id": session_id,
        "total_steps": len(steps),
        "steps": steps
    }


@router.get("/sessions/{session_id}/result")
async def get_reasoning_result(session_id: str):
    """获取推理结果"""
    result = reasoning_trace_service.get_result(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="结果不存在")
    return result


@router.get("/sessions/{session_id}/tool-calls")
async def get_tool_calls(session_id: str):
    """获取工具调用记录"""
    session = reasoning_trace_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    tool_calls = reasoning_trace_service.get_tool_calls(session_id)
    return {
        "session_id": session_id,
        "total_calls": len(tool_calls),
        "tool_calls": tool_calls
    }


@router.get("/sessions/{session_id}/stats")
async def get_session_stats(session_id: str):
    """获取会话统计信息"""
    stats = reasoning_trace_service.get_session_stats(session_id)
    if not stats:
        raise HTTPException(status_code=404, detail="会话不存在")
    return stats


@router.get("/sessions/{session_id}/export")
async def export_trace(session_id: str, format: str = Query("json", regex="^(json|html)$")):
    """导出推理追踪"""
    trace = reasoning_trace_service.get_full_trace(session_id)
    if not trace:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if format == "json":
        return trace
    elif format == "html":
        # 生成 HTML 报告
        html = _generate_html_report(trace)
        return {"html": html}


def _generate_html_report(trace: dict) -> str:
    """生成 HTML 报告"""
    session = trace.get('session', {})
    steps = trace.get('steps', [])
    result = trace.get('result', {})
    tool_calls = trace.get('tool_calls', [])
    
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>推理过程追踪报告</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
            h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
            h2 {{ color: #555; margin-top: 30px; }}
            .session-info {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .step {{ background: #f0f8ff; padding: 15px; margin: 10px 0; border-left: 4px solid #007bff; border-radius: 3px; }}
            .step.thinking {{ border-left-color: #28a745; }}
            .step.action {{ border-left-color: #ffc107; }}
            .step.observation {{ border-left-color: #17a2b8; }}
            .step-title {{ font-weight: bold; color: #333; }}
            .step-content {{ margin-top: 10px; color: #666; white-space: pre-wrap; word-break: break-word; }}
            .result {{ background: #d4edda; padding: 15px; border-radius: 5px; margin: 15px 0; border: 1px solid #c3e6cb; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 15px 0; }}
            .stat-box {{ background: #e7f3ff; padding: 15px; border-radius: 5px; text-align: center; }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #007bff; }}
            .stat-label {{ color: #666; margin-top: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>推理过程追踪报告</h1>
            
            <div class="session-info">
                <h2>会话信息</h2>
                <p><strong>会话ID:</strong> {session.get('session_id', 'N/A')}</p>
                <p><strong>用户ID:</strong> {session.get('user_id', 'N/A')}</p>
                <p><strong>模型:</strong> {session.get('model_name', 'N/A')} / {session.get('model_version', 'N/A')}</p>
                <p><strong>状态:</strong> {session.get('status', 'N/A')}</p>
                <p><strong>创建时间:</strong> {session.get('created_at', 'N/A')}</p>
            </div>
            
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-value">{session.get('total_steps', 0)}</div>
                    <div class="stat-label">总步骤数</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{session.get('total_tokens', 0)}</div>
                    <div class="stat-label">总Token数</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{session.get('reasoning_tokens', 0)}</div>
                    <div class="stat-label">推理Token数</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{session.get('duration_seconds', 0):.2f}s</div>
                    <div class="stat-label">耗时</div>
                </div>
            </div>
            
            <h2>推理步骤</h2>
    """
    
    for i, step in enumerate(steps, 1):
        step_type = step.get('step_type', 'unknown')
        html += f"""
            <div class="step {step_type}">
                <div class="step-title">步骤 {i}: {step_type.upper()}</div>
        """
        
        if step.get('thinking'):
            html += f"<div class='step-content'><strong>思考:</strong> {step['thinking']}</div>"
        if step.get('action_name'):
            html += f"<div class='step-content'><strong>行动:</strong> {step['action_name']}</div>"
        if step.get('action_input'):
            html += f"<div class='step-content'><strong>输入:</strong> {step['action_input']}</div>"
        if step.get('observation'):
            html += f"<div class='step-content'><strong>观察:</strong> {step['observation']}</div>"
        if step.get('tool_result'):
            html += f"<div class='step-content'><strong>工具结果:</strong> {step['tool_result']}</div>"
        
        html += "</div>"
    
    if result:
        html += f"""
            <h2>最终结果</h2>
            <div class="result">
                <p><strong>答案类型:</strong> {result.get('answer_type', 'N/A')}</p>
                <p><strong>置信度:</strong> {result.get('confidence_score', 0):.2%}</p>
                <div class="step-content"><strong>最终答案:</strong> {result.get('final_answer', 'N/A')}</div>
                {f"<div class='step-content'><strong>总结:</strong> {result.get('reasoning_summary', '')}</div>" if result.get('reasoning_summary') else ""}
            </div>
        """
    
    html += """
        </div>
    </body>
    </html>
    """
    
    return html
