"""
回归：单请求 ReAct 流式中，适配层按 delta 拆出的 reasoning / content 应对应
THINKING → LLM_CHUNK 事件顺序（不依赖前后端正则拆流）。

运行（项目根目录）：
  conda activate NewCoderAgent
  python -m unittest discover -s backend/tests -p "test_*.py" -v
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from hello_agents.core.llm_response import StreamStats
from hello_agents.core.streaming import StreamEventType

from backend.agents.react_stream_single_request import react_arun_stream_single_tool_stream
from backend.llm.stream_delta import LLMStreamDelta


class FakeAdapter:
    """模拟 DeepSeekThinkingOpenAIAdapter.astream_invoke_with_tools 的产出与收尾。"""

    async def astream_invoke_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
        yield LLMStreamDelta("reasoning", "r1")
        yield LLMStreamDelta("reasoning", "r2")
        yield LLMStreamDelta("content", "c1")
        self.last_stats = StreamStats(
            model="fake-reasoner",
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            latency_ms=1,
            reasoning_content="r1r2",
        )
        msg = SimpleNamespace(
            content="c1",
            tool_calls=None,
            reasoning_content="r1r2",
        )
        self._last_stream_with_tools_response = SimpleNamespace(
            choices=[SimpleNamespace(message=msg)]
        )


class FakeAgent:
    name = "FakeInterviewer"
    max_steps = 1

    def __init__(self):
        self.adapter = FakeAdapter()
        self.llm = SimpleNamespace(_adapter=self.adapter, last_call_stats=None)

    async def _emit_event(self, *args, **kwargs):
        pass

    def _build_messages(self, text: str):
        return [{"role": "user", "content": text}]

    def _build_tool_schemas(self):
        return []

    def add_message(self, msg):
        pass


class TestLLMStreamDelta(unittest.TestCase):
    def test_channel_literal(self):
        d = LLMStreamDelta("content", "x")
        self.assertEqual(d.channel, "content")
        self.assertEqual(d.text, "x")
        with self.assertRaises(ValueError):
            LLMStreamDelta("invalid", "x")  # type: ignore[arg-type]


class TestReactStreamDeltaEvents(unittest.IsolatedAsyncioTestCase):
    async def test_thinking_chunks_before_llm_chunk_then_agent_finish(self):
        agent = FakeAgent()
        events = []
        async for ev in react_arun_stream_single_tool_stream(agent, "hello"):
            events.append(ev)

        self.assertGreaterEqual(len(events), 7, msg=[e.type.value for e in events])
        self.assertEqual(events[0].type, StreamEventType.AGENT_START)
        self.assertEqual(events[1].type, StreamEventType.STEP_START)
        self.assertEqual(events[1].data.get("step"), 1)

        self.assertEqual(events[2].type, StreamEventType.THINKING)
        self.assertEqual(events[2].data.get("chunk"), "r1")
        self.assertEqual(events[2].data.get("step"), 1)
        self.assertEqual(events[3].type, StreamEventType.THINKING)
        self.assertEqual(events[3].data.get("chunk"), "r2")

        self.assertEqual(events[4].type, StreamEventType.LLM_CHUNK)
        self.assertEqual(events[4].data.get("chunk"), "c1")
        self.assertEqual(events[4].data.get("step"), 1)

        self.assertEqual(events[-2].type, StreamEventType.STEP_FINISH)
        self.assertEqual(events[-2].data.get("step"), 1)
        self.assertEqual(events[-1].type, StreamEventType.AGENT_FINISH)
        self.assertEqual(events[-1].data.get("result"), "c1")

    async def test_legacy_str_yields_only_llm_chunk(self):
        class StrOnlyAdapter:
            async def astream_invoke_with_tools(self, messages, tools, **kwargs):
                yield "only"
                self.last_stats = StreamStats(
                    model="fake",
                    usage={},
                    latency_ms=0,
                    reasoning_content=None,
                )
                msg = SimpleNamespace(content="only", tool_calls=None, reasoning_content="")
                self._last_stream_with_tools_response = SimpleNamespace(
                    choices=[SimpleNamespace(message=msg)]
                )

        class A(FakeAgent):
            def __init__(self):
                self.adapter = StrOnlyAdapter()
                self.llm = SimpleNamespace(_adapter=self.adapter, last_call_stats=None)

        agent = A()
        types = []
        async for ev in react_arun_stream_single_tool_stream(agent, "x"):
            types.append(ev.type)
        self.assertIn(StreamEventType.LLM_CHUNK, types)
        self.assertNotIn(StreamEventType.THINKING, types)


if __name__ == "__main__":
    unittest.main()
