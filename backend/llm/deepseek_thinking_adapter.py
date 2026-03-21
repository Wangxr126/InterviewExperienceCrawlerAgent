import copy
import logging
import time
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Union

from hello_agents.core.exceptions import HelloAgentsException
from hello_agents.core.llm_adapters import OpenAIAdapter
from hello_agents.core.llm_response import StreamStats

from backend.llm.stream_delta import LLMStreamDelta

logger = logging.getLogger(__name__)


class DeepSeekThinkingOpenAIAdapter(OpenAIAdapter):
    """
    在 OpenAIAdapter 基础上，为 DeepSeek reasoning 模型补全 reasoning_content 字段。

    背景（issue #28）：
    - DeepSeek reasoning 要求：历史里 role=assistant 且含 tool_calls 时须带 reasoning_content，
      否则 API 400。
    - wxr_agent 侧 Interviewer 使用 astream_invoke_with_tools：每步 **一次** stream+tools，
      与父类 ReAct 默认「先无 tools 流式再 invoke_with_tools」解耦，避免双请求不一致。

    修复策略：
    - 重写 _is_thinking_model：增加 "deepseek" 关键字识别。
    - 重写 invoke_with_tools：发送前规范化 messages，补全 reasoning_content。
    - 实现 astream_invoke_with_tools：单次流式请求同时解析正文与 tool_calls，
      并按通道 yield LLMStreamDelta（正文 / 推理分离，供上层发 LLM_CHUNK / THINKING）。
    """

    def _emits_separate_reasoning_stream(self) -> bool:
        """是否与正文分通道输出思维链（DeepSeek reasoner、OpenAI o 系等）。"""
        m = (self.model or "").lower()
        return "reasoner" in m or "o3" in m or "o1" in m

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

    async def astream_invoke_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        tool_choice: Union[str, Dict] = "auto",
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamDelta]:
        """
        单次 API：stream=True + tools。
        yield LLMStreamDelta(channel=content|reasoning)，与 OpenAI delta 字段一一对应，不靠正则从正文里抠推理。
        流结束后设置 last_stats、_last_stream_with_tools_response 供 ReAct 解析 tool_calls。
        """
        if not self._async_client:
            self._async_client = self.create_async_client()

        send_messages = messages
        if self._is_thinking_model(self.model):
            send_messages = self._normalize_messages_for_thinking(messages)

        self._last_stream_with_tools_response = None

        api_params: Dict[str, Any] = {
            "model": self.model,
            "messages": send_messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "stream": True,
        }
        if "temperature" in kwargs:
            api_params["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            api_params["max_tokens"] = kwargs["max_tokens"]
        for k in ("top_p", "frequency_penalty", "presence_penalty", "stop", "seed"):
            if k in kwargs and kwargs[k] is not None:
                api_params[k] = kwargs[k]

        start_time = time.time()
        collected_content: List[str] = []
        reasoning_content: Any = None
        usage: Dict[str, int] = {}
        tool_acc: Dict[int, Dict[str, str]] = {}

        try:
            stream = await self._async_client.chat.completions.create(**api_params)
        except Exception as e:
            raise HelloAgentsException(f"OpenAI 流式 Function Calling 失败: {e}") from e

        async for chunk in stream:
            if not chunk.choices:
                if hasattr(chunk, "usage") and chunk.usage:
                    u = chunk.usage
                    usage = {
                        "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(u, "total_tokens", 0) or 0,
                    }
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            raw_content = getattr(delta, "content", None)
            if raw_content:
                collected_content.append(raw_content)
                yield LLMStreamDelta("content", raw_content)
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                if reasoning_content is None:
                    reasoning_content = ""
                reasoning_content += rc
                if self._emits_separate_reasoning_stream():
                    yield LLMStreamDelta("reasoning", rc)
            tcs = getattr(delta, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    idx = getattr(tc, "index", 0)
                    if idx is None:
                        idx = 0
                    if idx not in tool_acc:
                        tool_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if getattr(tc, "id", None):
                        tool_acc[idx]["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        nm = getattr(fn, "name", None) or ""
                        if nm:
                            tool_acc[idx]["name"] += nm
                        arg = getattr(fn, "arguments", None) or ""
                        if arg:
                            tool_acc[idx]["arguments"] += arg
            if hasattr(chunk, "usage") and chunk.usage:
                u = chunk.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(u, "total_tokens", 0) or 0,
                }

        content_joined = "".join(collected_content)
        merged_calls: List[Any] = []
        for idx in sorted(tool_acc.keys()):
            t = tool_acc[idx]
            tid = (t.get("id") or "").strip() or f"call_stream_{idx}"
            merged_calls.append(
                SimpleNamespace(
                    id=tid,
                    type="function",
                    function=SimpleNamespace(
                        name=t.get("name") or "",
                        arguments=t.get("arguments") or "{}",
                    ),
                )
            )

        msg = SimpleNamespace(
            content=content_joined or None,
            tool_calls=merged_calls if merged_calls else None,
            reasoning_content=reasoning_content if reasoning_content is not None else "",
        )
        self._last_stream_with_tools_response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg)]
        )

        latency_ms = int((time.time() - start_time) * 1000)
        self.last_stats = StreamStats(
            model=self.model,
            usage=usage,
            latency_ms=latency_ms,
            reasoning_content=reasoning_content,
        )

    @property
    def last_reasoning(self) -> str:
        """
        读取最近一次流式调用收集到的 reasoning_content。
        父类 astream_invoke / stream_invoke 会把结果写入 self.last_stats.reasoning_content。
        """
        if hasattr(self, "last_stats") and self.last_stats:
            return self.last_stats.reasoning_content or ""
        return ""
