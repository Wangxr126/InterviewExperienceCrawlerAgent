"""
ReAct 流式：每步仅一次 LLM 请求（stream=True + tools），替代 hello_agents 默认的
「先无 tools 流式、再 invoke_with_tools」双请求，避免两路输出不一致。

供 InterviewerAgent.arun_stream 在适配器实现 astream_invoke_with_tools 时使用。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from hello_agents.core.lifecycle import EventType, LifecycleHook
from hello_agents.core.message import Message
from hello_agents.core.streaming import StreamEvent, StreamEventType

from backend.llm.stream_delta import LLMStreamDelta

logger = logging.getLogger(__name__)


def _llm_stream_kwargs(agent: Any, arun_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(arun_kwargs)
    llm = getattr(agent, "llm", None)
    if llm is None:
        return out
    if "temperature" not in out and getattr(llm, "temperature", None) is not None:
        out["temperature"] = llm.temperature
    if getattr(llm, "max_tokens", None) and "max_tokens" not in out:
        out["max_tokens"] = llm.max_tokens
    return out


async def react_arun_stream_single_tool_stream(
    agent: Any,
    input_text: str,
    on_start: Optional[LifecycleHook] = None,
    on_step: Optional[LifecycleHook] = None,
    on_tool_call: Optional[LifecycleHook] = None,
    on_finish: Optional[LifecycleHook] = None,
    on_error: Optional[LifecycleHook] = None,
    **kwargs: Any,
) -> AsyncGenerator[StreamEvent, None]:
    """
    与 hello_agents ReActAgent.arun_stream 等价的事件序列，但每步只调用
    adapter.astream_invoke_with_tools（单次 API、同时流式正文 + 解析 tool_calls）。
    """
    session_start_time = datetime.now()

    yield StreamEvent.create(
        StreamEventType.AGENT_START,
        agent.name,
        input_text=input_text,
    )
    await agent._emit_event(EventType.AGENT_START, on_start, input_text=input_text)

    try:
        messages = agent._build_messages(input_text)
        tool_schemas = agent._build_tool_schemas()
        current_step = 0
        final_answer = None

        _n = len(input_text)
        try:
            from backend.config.config import settings as _settings

            _cap = int(getattr(_settings, "miner_log_input_preview_chars", 0) or 0)
        except Exception:
            _cap = 0
        if _cap <= 0:
            _prev = input_text
            logger.info("🤖 %s 开始处理问题（完整日志 %d 字）: %s", agent.name, _n, _prev)
        else:
            _prev = input_text[:_cap] + ("…" if _n > _cap else "")
            logger.info(
                "🤖 %s 开始处理问题（%d 字，预览前 %d 字，MINER_LOG_INPUT_PREVIEW_CHARS）: %s",
                agent.name,
                _n,
                _cap,
                _prev,
            )
            logger.debug("%s 完整 user 输入:\n%s", agent.name, input_text)
        logger.info("[react_stream_single] 每步单请求 stream+tools（astream_invoke_with_tools）")

        stream_kw = _llm_stream_kwargs(agent, kwargs)
        adapter = getattr(getattr(agent, "llm", None), "_adapter", None)

        while current_step < agent.max_steps:
            current_step += 1

            yield StreamEvent.create(
                StreamEventType.STEP_START,
                agent.name,
                step=current_step,
                max_steps=agent.max_steps,
            )
            await agent._emit_event(EventType.STEP_START, on_step, step=current_step)
            logger.info("--- 第 %d 步 ---", current_step)

            try:
                async for part in adapter.astream_invoke_with_tools(
                    messages,
                    tool_schemas,
                    tool_choice="auto",
                    **stream_kw,
                ):
                    if isinstance(part, LLMStreamDelta):
                        if part.channel == "content" and part.text:
                            yield StreamEvent.create(
                                StreamEventType.LLM_CHUNK,
                                agent.name,
                                chunk=part.text,
                                step=current_step,
                            )
                            print(part.text, end="", flush=True)
                        elif part.channel == "reasoning" and part.text:
                            yield StreamEvent.create(
                                StreamEventType.THINKING,
                                agent.name,
                                chunk=part.text,
                                step=current_step,
                            )
                    elif isinstance(part, str) and part:
                        yield StreamEvent.create(
                            StreamEventType.LLM_CHUNK,
                            agent.name,
                            chunk=part,
                            step=current_step,
                        )
                        print(part, end="", flush=True)
                print()

                if hasattr(agent.llm, "last_call_stats"):
                    agent.llm.last_call_stats = getattr(adapter, "last_stats", None)

            except Exception as e:
                error_msg = f"LLM 调用失败: {str(e)}"
                print(f"❌ {error_msg}")
                yield StreamEvent.create(
                    StreamEventType.ERROR,
                    agent.name,
                    error=error_msg,
                    step=current_step,
                )
                await agent._emit_event(EventType.AGENT_ERROR, on_error, error=error_msg)
                break

            response = getattr(adapter, "_last_stream_with_tools_response", None)
            if response is None:
                error_msg = "LLM 流式结束但未生成 tool 响应对象"
                yield StreamEvent.create(
                    StreamEventType.ERROR,
                    agent.name,
                    error=error_msg,
                    step=current_step,
                )
                await agent._emit_event(EventType.AGENT_ERROR, on_error, error=error_msg)
                break

            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if not tool_calls:
                final_answer = (
                    (response_message.content or "")
                    or "抱歉，我无法回答这个问题。"
                )
                # 必须先 STEP_FINISH：InterviewerAgent.arun_stream 仅在 STEP_FINISH 时把本步
                # thought/tools 并入 thinking_steps；若直接 AGENT_FINISH，持久化与刷新后推理会丢。
                yield StreamEvent.create(
                    StreamEventType.STEP_FINISH,
                    agent.name,
                    step=current_step,
                )
                yield StreamEvent.create(
                    StreamEventType.AGENT_FINISH,
                    agent.name,
                    result=final_answer,
                    total_steps=current_step,
                )
                await agent._emit_event(EventType.AGENT_FINISH, on_finish, result=final_answer)
                agent.add_message(Message(input_text, "user"))
                agent.add_message(Message(final_answer, "assistant"))
                return

            asst_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            _stat = getattr(adapter, "last_stats", None)
            _rc = getattr(_stat, "reasoning_content", None) if _stat else None
            if _rc is not None:
                asst_msg["reasoning_content"] = _rc
            else:
                asst_msg["reasoning_content"] = getattr(
                    response_message, "reasoning_content", None
                ) or ""

            messages.append(asst_msg)

            try:
                tool_results = await agent._execute_tools_async_stream(
                    tool_calls,
                    current_step,
                    on_tool_call,
                )
            except Exception as e:
                error_msg = f"工具执行失败: {str(e)}"
                print(f"❌ {error_msg}")
                yield StreamEvent.create(
                    StreamEventType.ERROR,
                    agent.name,
                    error=error_msg,
                    step=current_step,
                )
                await agent._emit_event(EventType.AGENT_ERROR, on_error, error=error_msg)
                break

            for tool_name, tool_call_id, result_dict in tool_results:
                yield StreamEvent.create(
                    StreamEventType.TOOL_CALL_FINISH,
                    agent.name,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    result=result_dict["content"],
                    step=current_step,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_dict["content"],
                    }
                )

                if tool_name == "Finish":
                    try:
                        args = json.loads(tool_calls[0].function.arguments)
                        final_answer = args.get("answer", result_dict["content"])
                    except Exception:
                        final_answer = result_dict["content"]

                    yield StreamEvent.create(
                        StreamEventType.STEP_FINISH,
                        agent.name,
                        step=current_step,
                    )
                    yield StreamEvent.create(
                        StreamEventType.AGENT_FINISH,
                        agent.name,
                        result=final_answer,
                        total_steps=current_step,
                    )
                    await agent._emit_event(
                        EventType.AGENT_FINISH, on_finish, result=final_answer
                    )
                    agent.add_message(Message(input_text, "user"))
                    agent.add_message(Message(final_answer, "assistant"))
                    return

            yield StreamEvent.create(
                StreamEventType.STEP_FINISH,
                agent.name,
                step=current_step,
            )

        if not final_answer:
            final_answer = "抱歉，已达到最大步数限制，无法完成任务。"
            yield StreamEvent.create(
                StreamEventType.STEP_FINISH,
                agent.name,
                step=current_step,
            )
            yield StreamEvent.create(
                StreamEventType.AGENT_FINISH,
                agent.name,
                result=final_answer,
                total_steps=current_step,
                max_steps_reached=True,
            )
            await agent._emit_event(EventType.AGENT_FINISH, on_finish, result=final_answer)
            agent.add_message(Message(input_text, "user"))
            agent.add_message(Message(final_answer, "assistant"))

    except Exception as e:
        error_msg = f"Agent 执行失败: {str(e)}"
        yield StreamEvent.create(
            StreamEventType.ERROR,
            agent.name,
            error=error_msg,
            error_type=type(e).__name__,
        )
        await agent._emit_event(EventType.AGENT_ERROR, on_error, error=error_msg)
        raise
