import copy
import logging
from typing import List, Dict, Any, Union

from hello_agents.core.llm_adapters import OpenAIAdapter
from hello_agents.core.exceptions import HelloAgentsException


logger = logging.getLogger(__name__)


class DeepSeekThinkingOpenAIAdapter(OpenAIAdapter):
    """
    在 OpenAIAdapter 基础上，为 DeepSeek reasoning 模型补全 reasoning_content 字段。

    背景（issue #28）：
    - DeepSeek reasoning 模型要求：历史消息中 role=assistant 且含 tool_calls 的条目，
      必须同时携带 reasoning_content 字段，否则 API 返回 400。
    - hello_agents 框架的 ReActAgent.arun_stream 流程：
        Step N:
          1. astream_invoke(messages)          ← 流式收集文本 & reasoning_content
          2. invoke_with_tools(messages, tools) ← 获取 tool_calls（非流式）
          3. messages.append({role:assistant, tool_calls:[...]})  ← 没有 reasoning_content！
          4. Step N+1: invoke_with_tools(messages, ...) ← 400 错误
    - 父类 astream_invoke 已正确把 reasoning_content 收集到 self.last_stats.reasoning_content。

    修复策略：
    - 重写 _is_thinking_model：增加 "deepseek" 关键字识别。
    - 重写 invoke_with_tools：发送前对 messages 做规范化，
      对 role=assistant + tool_calls 的历史消息自动补 reasoning_content=""。
    - 不重写 astream_invoke / stream_invoke：父类已正确处理 reasoning_content，
      结果存于 self.last_stats.reasoning_content，供外部读取。
    """

    def _is_thinking_model(self, model_name: str) -> bool:
        """
        在父类关键字基础上增加 'deepseek'，识别 DeepSeek reasoning 模型。
        父类关键字：reasoner, o1, o3, thinking
        """
        thinking_keywords = ["reasoner", "o1", "o3", "thinking", "deepseek"]
        model_lower = (model_name or "").lower()
        return any(k in model_lower for k in thinking_keywords)

    def _normalize_messages_for_thinking(self, messages: List[Dict]) -> List[Dict]:
        """
        规范化消息列表：对 role=assistant 且含 tool_calls 的历史消息，
        补全缺失或为 None 的 reasoning_content 为空字符串。

        不修改原列表，返回新列表（仅对需要补字段的消息做 deepcopy）。
        """
        if not messages:
            return messages

        normalized: List[Dict[str, Any]] = []
        for m in messages:
            if (
                isinstance(m, dict)
                and m.get("role") == "assistant"
                and m.get("tool_calls")
                and m.get("reasoning_content") is None  # 缺失或显式为 None
            ):
                mm = copy.deepcopy(m)
                mm["reasoning_content"] = ""
                logger.debug(
                    "[DeepSeekThinkingAdapter] "
                    "补全 assistant+tool_calls 消息的 reasoning_content 为 \"\""
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
        重写 invoke_with_tools：
        - 对 thinking 模型，在发送前规范化 messages，防止 DeepSeek 400 错误。
        - 其余逻辑与父类完全一致。
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
            return response
        except Exception as e:
            raise HelloAgentsException(f"OpenAI Function Calling调用失败: {e}")

    async def astream_invoke(self, messages: List[Dict], **kwargs):
        """
        重写 astream_invoke：对 thinking 模型发送前规范化 messages，
        防止 DeepSeek 400 'Missing reasoning_content' 错误。
        """
        send_messages = messages
        if self._is_thinking_model(self.model):
            send_messages = self._normalize_messages_for_thinking(messages)
        async for chunk in super().astream_invoke(send_messages, **kwargs):
            yield chunk

    @property
    def last_reasoning(self) -> str:
        """
        读取最近一次流式调用收集到的 reasoning_content。
        父类 astream_invoke / stream_invoke 会把结果写入 self.last_stats.reasoning_content。
        """
        if hasattr(self, "last_stats") and self.last_stats:
            return self.last_stats.reasoning_content or ""
        return ""
