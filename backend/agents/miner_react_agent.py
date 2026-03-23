"""
MinerReActAgent：在 ReActAgent 基础上增加 mark_unrelated 终止逻辑。
当 mark_unrelated 被调用且返回 __UNRELATED__ 时，立即结束循环，不再执行后续步骤。
"""
import logging

from hello_agents import ReActAgent
from hello_agents.tools.registry import ToolRegistry
from backend.services.logging.agent_tool_runtime_stats import (
    agent_tool_runtime_stats,
    tool_execution_success_for_stats,
)


# 终止工具：调用后立即结束，不再继续
TERMINATING_TOOLS = {"mark_unrelated"}
TERMINATING_SIGNAL = "__UNRELATED__"


class MinerReActAgent(ReActAgent):
    """
    扩展 ReActAgent，支持 mark_unrelated 等终止工具。
    当终止工具返回约定信号时，立即 return，避免模型重复调用。
    兼容部分本地模型将工具调用以 {"tool":"xxx","arguments":{}} 文本格式输出到 content 的情况。
    """

    def _parse_embedded_tool_call(self, content: str):
        """
        解析 content 中可能存在的内嵌工具调用格式。
        格式：{"tool": "verify_extraction_count", "arguments": {"extracted_count": 13, "expected_count": 13}}
        返回 (tool_name, arguments) 或 None。
        """
        import json
        s = content.strip()
        if not s or not s.startswith("{"):
            return None
        try:
            obj = json.loads(s)
            if not isinstance(obj, dict):
                return None
            tool = obj.get("tool") or obj.get("name")
            args = obj.get("arguments") or obj.get("args") or {}
            if tool and isinstance(args, dict):
                return (str(tool), args)
        except json.JSONDecodeError:
            pass
        return None

    def _run_impl(self, input_text: str, session_start_time, **kwargs) -> str:
        """与 ReActAgent 相同，但在用户工具执行后检查是否为终止工具"""
        import json
        import time
        from datetime import datetime
        from hello_agents.core.message import Message
        from backend.agents.context import get_current_user_id

        messages = self._build_messages(input_text)
        tool_schemas = self._build_tool_schemas()

        current_step = 0
        total_tokens = 0
        # LLM 调用异常时 break 出循环，不能与「达到最大步数」混为一谈
        llm_invoke_error: Exception | None = None

        if self.trace_logger:
            self.trace_logger.log_event(
                "message_written",
                {"role": "user", "content": input_text}
            )

        _ilog = logging.getLogger(__name__)
        _n = len(input_text)
        try:
            from backend.config.config import settings as _settings

            _cap = int(getattr(_settings, "miner_log_input_preview_chars", 0) or 0)
        except Exception:
            _cap = 0
        if _cap <= 0:
            _prev = input_text
            _ilog.info("🤖 %s 开始处理问题（完整日志 %d 字）: %s", self.name, _n, _prev)
        else:
            _prev = input_text[:_cap] + ("…" if _n > _cap else "")
            _ilog.info(
                "🤖 %s 开始处理问题（%d 字，预览前 %d 字，MINER_LOG_INPUT_PREVIEW_CHARS）: %s",
                self.name,
                _n,
                _cap,
                _prev,
            )
            _ilog.debug("%s 完整 user 输入:\n%s", self.name, input_text)

        while current_step < self.max_steps:
            current_step += 1
            _ilog.info("--- 第 %d 步 ---", current_step)

            self._current_step = current_step

            try:
                response = self.llm.invoke_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    **kwargs
                )
            except Exception as e:
                llm_invoke_error = e
                print(f"❌ LLM 调用失败: {e}")
                if self.trace_logger:
                    self.trace_logger.log_event(
                        "error",
                        {"error_type": "LLM_ERROR", "message": str(e)},
                        step=current_step
                    )
                break

            response_message = response.choices[0].message

            if response.usage:
                total_tokens += response.usage.total_tokens
                self._total_tokens = total_tokens

            if self.trace_logger:
                self.trace_logger.log_event(
                    "model_output",
                    {
                        "content": response_message.content or "",
                        "tool_calls": len(response_message.tool_calls) if response_message.tool_calls else 0,
                        "usage": {
                            "total_tokens": response.usage.total_tokens if response.usage else 0,
                            "cost": 0.0
                        }
                    },
                    step=current_step
                )

            tool_calls = response_message.tool_calls
            content = (response_message.content or "").strip()

            # 兼容：部分本地模型（如 qwen3:4b）不支持标准 tool_calls，将工具调用以 JSON 文本输出到 content
            # 格式：{"tool": "verify_extraction_count", "arguments": {...}}
            if not tool_calls and content:
                embedded = self._parse_embedded_tool_call(content)
                if embedded:
                    tool_name, arguments = embedded
                    tool_call_id = f"call_embedded_{current_step}"
                    print(f"🔧 [内嵌格式] 检测到工具调用: {tool_name}({arguments})")

                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [{
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False)
                            }
                        }]
                    })

                    if self.trace_logger:
                        self.trace_logger.log_event(
                            "tool_call",
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "args": arguments,
                                "source": "embedded_content",
                            },
                            step=current_step
                        )

                    if tool_name in self._builtin_tools:
                        _t0 = time.time()
                        result = self._handle_builtin_tool(tool_name, arguments)
                        result_content = result.get("content", str(result))
                        agent_tool_runtime_stats.record(
                            agent_name=self.name,
                            tool_name=tool_name,
                            success=tool_execution_success_for_stats(result_content),
                            execution_time_ms=(time.time() - _t0) * 1000.0,
                            user_id=get_current_user_id(),
                            params_input=arguments if isinstance(arguments, dict) else {},
                        )
                        print(f"🔧 {tool_name}: {result_content}")
                    else:
                        tool = self.tool_registry.get_tool(tool_name)
                        if not tool:
                            result_content = f"❌ 工具 {tool_name} 不存在"
                            _time_ms = 0.0
                            _status = None
                        else:
                            tool_response = tool.run_with_timing(arguments)
                            result_content = tool_response.text
                            _status = getattr(tool_response, "status", None)
                            _stats = getattr(tool_response, "stats", None)
                            _time_ms = float(_stats.get("time_ms")) if isinstance(_stats, dict) and _stats.get("time_ms") is not None else 0.0
                        agent_tool_runtime_stats.record(
                            agent_name=self.name,
                            tool_name=tool_name,
                            success=tool_execution_success_for_stats(result_content, response_status=_status),
                            execution_time_ms=_time_ms,
                            user_id=get_current_user_id(),
                            params_input=arguments if isinstance(arguments, dict) else {},
                        )
                        if not result_content.startswith("❌"):
                            print(f"👀 观察: {result_content}")

                    if self.trace_logger:
                        self.trace_logger.log_event(
                            "tool_result",
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "result": result_content,
                                "source": "embedded_content",
                            },
                            step=current_step
                        )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_content
                    })

                    if tool_name in TERMINATING_TOOLS and TERMINATING_SIGNAL in result_content:
                        return result_content

                    continue  # 继续下一轮，让模型根据工具结果输出 JSON

            if not tool_calls:
                final_answer = content or "抱歉，我无法回答这个问题。"
                if final_answer == "抱歉，我无法回答这个问题。":
                    content_preview = (content or "").strip()
                    print(
                        "[APOLOGY_REASON] 触发通用兜底回复："
                        f"content_empty={not bool(content_preview)}, "
                        f"tool_calls_count=0, "
                        f"step={current_step}, "
                        f"content_preview={content_preview[:200]!r}"
                    )
                print(f"💬 直接回复: {final_answer}")

                self.add_message(Message(input_text, "user"))
                self.add_message(Message(final_answer, "assistant"))

                if self.trace_logger:
                    duration = (datetime.now() - session_start_time).total_seconds()
                    self.trace_logger.log_event(
                        "session_end",
                        {
                            "duration": duration,
                            "total_steps": current_step,
                            "final_answer": final_answer,
                            "status": "success"
                        }
                    )
                    self.trace_logger.finalize()

                return final_answer

            messages.append({
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            })

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_call_id = tool_call.id

                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    print(f"❌ 工具参数解析失败: {e}")
                    agent_tool_runtime_stats.record(
                        agent_name=self.name,
                        tool_name=tool_name,
                        success=False,
                        execution_time_ms=0.0,
                        user_id=get_current_user_id(),
                        params_input={},
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"错误：参数格式不正确 - {str(e)}"
                    })
                    continue

                if self.trace_logger:
                    self.trace_logger.log_event(
                        "tool_call",
                        {
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "args": arguments
                        },
                        step=current_step
                    )

                if tool_name in self._builtin_tools:
                    _t0 = time.time()
                    result = self._handle_builtin_tool(tool_name, arguments)
                    print(f"🔧 {tool_name}: {result['content']}")
                    agent_tool_runtime_stats.record(
                        agent_name=self.name,
                        tool_name=tool_name,
                        success=tool_execution_success_for_stats(
                            str(result.get("content", ""))
                        ),
                        execution_time_ms=(time.time() - _t0) * 1000.0,
                        user_id=get_current_user_id(),
                        params_input=arguments if isinstance(arguments, dict) else {},
                    )

                    if self.trace_logger:
                        self.trace_logger.log_event(
                            "tool_result",
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "status": "success",
                                "result": result['content']
                            },
                            step=current_step
                        )

                    if tool_name == "Finish" and result.get("finished"):
                        final_answer = result["final_answer"]
                        print(f"🎉 最终答案: {final_answer}")

                        self.add_message(Message(input_text, "user"))
                        self.add_message(Message(final_answer, "assistant"))

                        if self.trace_logger:
                            duration = (datetime.now() - session_start_time).total_seconds()
                            self.trace_logger.log_event(
                                "session_end",
                                {
                                    "duration": duration,
                                    "total_steps": current_step,
                                    "final_answer": final_answer,
                                    "status": "success"
                                }
                            )
                            self.trace_logger.finalize()

                        return final_answer

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result['content']
                    })
                else:
                    print(f"🎬 调用工具: {tool_name}({arguments})")

                    tool = self.tool_registry.get_tool(tool_name)
                    if not tool:
                        result = f"❌ 工具 {tool_name} 不存在"
                        _status = None
                        _time_ms = 0.0
                    else:
                        tool_response = tool.run_with_timing(arguments)
                        result = tool_response.text
                        _status = getattr(tool_response, "status", None)
                        _stats = getattr(tool_response, "stats", None)
                        _time_ms = float(_stats.get("time_ms")) if isinstance(_stats, dict) and _stats.get("time_ms") is not None else 0.0
                    agent_tool_runtime_stats.record(
                        agent_name=self.name,
                        tool_name=tool_name,
                        success=tool_execution_success_for_stats(str(result), response_status=_status),
                        execution_time_ms=_time_ms,
                        user_id=get_current_user_id(),
                        params_input=arguments if isinstance(arguments, dict) else {},
                    )

                    if self.trace_logger:
                        self.trace_logger.log_event(
                            "tool_result",
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "result": result
                            },
                            step=current_step
                        )

                    if result.startswith("❌"):
                        print(result)
                    else:
                        print(f"👀 观察: {result}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result
                    })

                    # 终止工具：调用后立即返回，不再执行后续步骤
                    if tool_name in TERMINATING_TOOLS and TERMINATING_SIGNAL in result:
                        return result

        if llm_invoke_error is not None:
            final_answer = f"抱歉，Stage1 模型调用失败：{llm_invoke_error}"
            _ilog.error("%s %s", self.name, final_answer)
            self.add_message(Message(input_text, "user"))
            self.add_message(Message(final_answer, "assistant"))
            if self.trace_logger:
                duration = (datetime.now() - session_start_time).total_seconds()
                self.trace_logger.log_event(
                    "session_end",
                    {
                        "duration": duration,
                        "total_steps": current_step,
                        "final_answer": final_answer,
                        "status": "llm_error",
                    },
                )
                self.trace_logger.finalize()
            return final_answer

        print("⏰ 已达到最大步数，流程终止。")
        final_answer = "抱歉，我无法在限定步数内完成这个任务。"

        self.add_message(Message(input_text, "user"))
        self.add_message(Message(final_answer, "assistant"))

        if self.trace_logger:
            duration = (datetime.now() - session_start_time).total_seconds()
            self.trace_logger.log_event(
                "session_end",
                {
                    "duration": duration,
                    "total_steps": current_step,
                    "final_answer": final_answer,
                    "status": "timeout"
                }
            )
            self.trace_logger.finalize()

        return final_answer
