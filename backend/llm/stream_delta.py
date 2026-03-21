"""LLM 流式片段：区分正文与推理通道（OpenAI/DeepSeek delta 语义，非正则拼凑）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Channel = Literal["content", "reasoning"]


@dataclass(frozen=True)
class LLMStreamDelta:
    """
    astream_invoke_with_tools 的产出单元。
    - content: 对用户可见的正文（delta.content）
    - reasoning: 思维链（delta.reasoning_content，仅 reasoning 类模型）
    """

    channel: Channel
    text: str

    def __post_init__(self) -> None:
        if self.channel not in ("content", "reasoning"):
            raise ValueError(f"invalid channel: {self.channel}")
