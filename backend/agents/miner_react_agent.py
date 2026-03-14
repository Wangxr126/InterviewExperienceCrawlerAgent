"""
MinerReActAgent：在 ReActAgent 基础上增加 mark_unrelated 终止逻辑。
当 mark_unrelated 被调用且返回 __UNRELATED__ 时，立即结束循环，不再执行后续步骤。
"""
from hello_agents import ReActAgent
from hello_agents.tools.registry import ToolRegistry


# 终止工具：调用后立即结束，不再继续
TERMINATING_TOOLS = {"mark_unrelated"}
TERMINATING_SIGNAL = "__UNRELATED__"


class MinerReActAgent(ReActAgent):
    """
    扩展 ReActAgent，支持 mark_unrelated 等终止工具。
    当终止工具返回约定信号时，立即 return，避免模型重复调用。
    """

    def _run_impl(self, input_text: str, session_start_time, **kwargs) -> str:
        """与 ReActAgent 相同，但在用户工具执行后检查是否为终止工具"""
        import json
        from datetime import datetime
        from hello_agents.core.message import Message

        messages = self._build_messages(input_text)
        tool_schemas = self._build_tool_schemas()

        current_step = 0
        total_tokens = 0

        if self.trace_logger:
            self.trace_logger.log_event(
                "message_written",
                {"role": "user", "content": input_text}
            )

        print(f"\n🤖 {self.name} 开始处理问题: {input_text}")

        while current_step < self.max_steps:
            current_step += 1
            print(f"\n--- 第 {current_step} 步 ---")

            self._current_step = current_step

            try:
                response = self.llm.invoke_with_tools(
                    messages=messages,
                    tools=tool_schemas,
                    tool_choice="auto",
                    **kwargs
                )
            except Exception as e:
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
            if not tool_calls:
                final_answer = response_message.content or "抱歉，我无法回答这个问题。"
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
                    result = self._handle_builtin_tool(tool_name, arguments)
                    print(f"🔧 {tool_name}: {result['content']}")

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

                    result = self._execute_tool_call(tool_name, arguments)

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
