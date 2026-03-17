import copy
import logging
from typing import List, Dict, Any, Union, AsyncIterator, Iterator

from hello_agents.core.llm_adapters import OpenAIAdapter
from hello_agents.core.exceptions import HelloAgentsException


logger = logging.getLogger(__name__)


class DeepSeekThinkingOpenAIAdapter(OpenAIAdapter):
    """
    在原 OpenAIAdapter 基础上，为 DeepSeek thinking + tool_calls 场景补全 reasoning_content。

    背景：
    - DeepSeek thinking 模式要求：assistant 消息若包含 tool_calls，必须同时包含 reasoning_content 字段，
      否则会返回 400 错误（Missing reasoning_content field in the assistant message）。
    - hello_agents 框架会把历史消息（包括之前的工具调用轮次）一并发给 API，如果历史里某条
      assistant + tool_calls 消息缺少 reasoning_content，就会触发这个 400。

    设计：
    - 不修改 hello_agents 源码，也不修改你下载的 react_agent，而是在项目层定义一个自定义 Adapter。
    - 在 invoke_with_tools 前，对 messages 做一次轻量规范化：
        * 对 role=assistant 且含 tool_calls 的消息：
            - 若无 reasoning_content 字段，补上 reasoning_content=""；
            - 若 reasoning_content 为 None，也改成 ""。
        * 不修改原始列表，使用浅拷贝 + 针对需要修改的项做 deepcopy。
    - 仅在 DeepSeek / reasoning 模型下启用，其他模型保持原逻辑。
    """

    def _is_thinking_model(self, model_name: str) -> bool:
        """
        复用原有逻辑并增加 DeepSeek 关键字，用于识别需要特殊处理的思考模型。
        """
        thinking_keywords = ["reasoner", "o1", "o3", "thinking", "deepseek"]
        model_lower = (model_name or "").lower()
        return any(k in model_lower for k in thinking_keywords)

    def _normalize_messages_for_thinking(self, messages: List[Dict]) -> List[Dict]:
        """
        对 messages 做规范化：
        - 仅当 role=assistant 且含 tool_calls 时检查 reasoning_content。
        - 缺失或为 None 时，置为 ""，以满足 DeepSeek 的参数约束。
        - 不在原列表上修改，返回新的列表。
        """
        if not messages:
            return messages

        normalized: List[Dict[str, Any]] = []
        for m in messages:
            # 只对需要补字段的消息做 deepcopy，其他消息直接复用
            if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
                mm = copy.deepcopy(m)
                val = mm.get("reasoning_content")
                mm["reasoning_content"] = val if val is not None else ""
                if not val:
                    logger.debug(
                        "[DeepSeekThinkingOpenAIAdapter] "
                        "补全 assistant.tool_calls 消息的 reasoning_content 为空字符串"
                    )
                normalized.append(mm)
            else:
                normalized.append(m)
        return normalized

    def invoke_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        tool_choice: Union[str, Dict] = "auto",
        **kwargs: Any,
    ) -> Any:
        """
        在原 OpenAIAdapter.invoke_with_tools 基础上，对 thinking 模型自动规范化 messages。
        同时将每步产生的 reasoning_content 累积到 self.last_reasoning，
        供 chat_stream 在 step_finish/agent_finish 时读取并推送 thinking SSE。
        """
        if not self._client:
            self._client = self.create_client()

        send_messages = messages
        if self._is_thinking_model(self.model):
            send_messages = self._normalize_messages_for_thinking(messages)

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=send_messages,
                tools=tools,
                tool_choice=tool_choice,
                **kwargs,
            )
            # 模型返回的思考过程（reasoning_content）单独打印，与 content / tool_calls 区分
            if self._is_thinking_model(self.model) and response.choices:
                msg = response.choices[0].message
                reasoning = getattr(msg, "reasoning_content", None) or ""
                if reasoning:
                    # 保存到 last_reasoning，供 chat_stream 流程读取推送 SSE
                    self.last_reasoning = reasoning
                    # 同步一份到 stdout，供 ThinkingCapture 捕获并展示为「思考」步骤。
                    try:
                        print(f"🤔 思考: {reasoning}")
                    except Exception:
                        # stdout 写入失败不影响主流程
                        pass
                # ⚠️ 不再在 reasoning 为空时清空 last_reasoning：
                # astream_invoke 流式阶段已收集到 reasoning，invoke_with_tools
                # 紧随其后执行时 tool_calls 响应可能不含 reasoning_content（为空），
                # 若此处清空会导致流式收集的推理内容丢失，chat_stream 无法推送 thinking SSE。
            return response
        except Exception as e:
            raise HelloAgentsException(f"OpenAI Function Calling调用失败: {e}")

    def stream_invoke(self, messages: List[Dict], **kwargs: Any) -> Iterator[str]:
        """流式调用前对 thinking 模型的 messages 做 reasoning_content 规范化。"""
        send_messages = messages
        if self._is_thinking_model(self.model):
            send_messages = self._normalize_messages_for_thinking(messages)
        return super().stream_invoke(send_messages, **kwargs)

    REASONING_PREFIX = "\x00THINKING\x00"  # 保留兼容旧引用，实际不再用于流式注入

    @staticmethod
    def _messages_have_tool_calls(messages: List[Dict]) -> bool:
        """检查消息历史中是否已有 tool_calls（即多轮工具调用对话）。"""
        return any(
            isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls")
            for m in messages
        )

    async def astream_invoke(self, messages: List[Dict], **kwargs: Any) -> AsyncIterator[str]:
        """
        异步流式调用：规范化 messages（防止 400），收集 reasoning_content 到
        self.last_reasoning，供 chat_stream 在流结束后一次性读取推送给前端。
        普通文本 chunk 直接 yield，行为与父类完全一致。

        特殊处理（deepseek-reasoner 等 thinking 模型）：
        当消息历史中已有 tool_calls 时，跳过流式预调——框架的 arun_stream 在流式调用
        之后还会再次调用 invoke_with_tools 获取真正的工具调用结构；如果此处不跳过，
        模型在没有 tools schema 的流式请求中会退化输出原生 DSML 格式文本，污染输出。
        """
        send_messages = messages
        if self._is_thinking_model(self.model):
            send_messages = self._normalize_messages_for_thinking(messages)

        if not self._is_thinking_model(self.model):
            async for chunk in super().astream_invoke(send_messages, **kwargs):
                yield chunk
            return

        # thinking 模型：若历史已含 tool_calls，跳过流式预调，避免输出 DSML 文本
        if self._messages_have_tool_calls(send_messages):
            logger.debug(
                "[DeepSeekThinkingOpenAIAdapter] 检测到历史 tool_calls，"
                "跳过流式预调，由后续 invoke_with_tools 处理工具调用"
            )
            self.last_reasoning = ""
            return

        if not self._async_client:
            self._async_client = self.create_async_client()

        self.last_reasoning = ""  # 每次调用前重置

        try:
            response = await self._async_client.chat.completions.create(
                model=self.model,
                messages=send_messages,
                stream=True,
                **kwargs,
            )

            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # 收集 reasoning_content（不 yield，避免污染 full_response）
                reasoning_chunk = getattr(delta, "reasoning_content", None)
                if reasoning_chunk:
                    self.last_reasoning += reasoning_chunk

                # 普通文本 chunk 正常 yield
                if delta.content:
                    yield delta.content

        except Exception as e:
            raise HelloAgentsException(f"DeepSeek 异步流式调用失败: {e}")

