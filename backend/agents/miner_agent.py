"""
Miner Agent - 信息挖掘师
职责：从面经原文中智能挖掘结构化信息（使用 OpenAI function-calling 循环）

实现说明：
- 不继承 hello_agents ReActAgent（其 run() 不注入 system_prompt，也不使用 tool_registry）
- 直接使用 HelloAgentsLLM._adapter._client（OpenAI 兼容客户端）进行 function-calling 循环
- LLM 自主判断是否调用 ocr_images 工具，最终通过 Finish 工具返回 JSON 数组
"""
import json
import logging
import re
from typing import List, Optional

from hello_agents.core.llm import HelloAgentsLLM

from backend.config.config import settings
from backend.agents.prompts.miner_prompt import get_miner_prompt
from backend.tools.miner_tools import OcrImagesTool

logger = logging.getLogger(__name__)

# OpenAI function schema：ocr_images 工具
_OCR_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ocr_images",
        "description": (
            "对面经帖子中的图片进行 OCR 文字识别。"
            "当正文内容太笼统（如只有寥寥数语）、无面试题可提取时调用此工具，"
            "获取图片中的文字后再提取面试题目。"
            "无图片时返回空字符串。"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

# OpenAI function schema：Finish 工具（返回最终 JSON 数组）
_FINISH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "Finish",
        "description": "提取完成后调用此工具返回最终结果。answer 是 JSON 数组字符串。",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": (
                        "JSON 数组字符串，每项包含 question_text/answer_text/difficulty/"
                        "question_type/topic_tags/company/position 字段。"
                        "无题目时填 '[]'。"
                    ),
                }
            },
            "required": ["answer"],
        },
    },
}

_ALL_TOOLS = [_OCR_TOOL_SCHEMA, _FINISH_TOOL_SCHEMA]


class MinerAgent:
    """
    信息挖掘师 Agent（OpenAI function-calling 循环）

    职责：从面经原文中智能挖掘结构化信息
    - LLM 自主决定是否调用 ocr_images 工具
    - 正文有题目时：调用 Finish 直接返回 JSON
    - 正文无题目但有图片时：先调用 ocr_images，再调用 Finish 返回 JSON
    - 最终结果从 Finish.answer 中提取
    """

    def __init__(self, image_paths: List[str] = None, task_id: str = ""):
        self._image_paths = image_paths or []
        self._task_id = task_id
        self._ocr_tool = OcrImagesTool(
            image_paths=self._image_paths,
            task_id=self._task_id,
        )
        self._llm = HelloAgentsLLM(
            model=settings.miner_model,
            api_key=settings.miner_api_key,
            base_url=settings.miner_base_url,
            temperature=settings.miner_temperature,
            timeout=settings.miner_timeout,
        )
        self._max_steps = 5  # Thought → (ocr_images?) → Finish，最多 5 轮

        logger.debug(f"[MinerAgent] 初始化完成，images={len(self._image_paths)}, task_id={self._task_id}")

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, arguments: dict) -> str:
        """根据工具名执行对应工具，返回字符串结果。"""
        if name == "ocr_images":
            return self._ocr_tool.run({}) or ""
        logger.warning(f"[MinerAgent] 未知工具调用: {name}")
        return f"未知工具: {name}"

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """过滤 deepseek-r1 等模型输出的 <think>...</think> 推理标签，只保留正式答案部分。"""
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
        return text.strip()

    def run(self, input_text: str, **kwargs) -> str:
        """
        运行 MinerAgent function-calling 循环。

        流程：
          1. 发送 system + user 消息，携带 ocr_images / Finish 两个 tool schema
          2. 若 LLM 调用 ocr_images → 执行 → 追加 tool result → 继续
          3. 若 LLM 调用 Finish → 返回 answer 字段内容（JSON 字符串）
          4. 若 LLM 直接回复文本（不走工具）→ 根据情况决定是否强制 OCR 或提示调用 Finish
          5. 超过 max_steps → 返回空字符串，由 question_extractor 重试

        OCR 触发策略：
          - LLM 自主调用 ocr_images（推荐路径）：LLM 判断正文无技术内容时主动调用
          - 强制兜底触发（仅当 step 1 返回空文本 + 有图片且尚未 OCR）：
            说明 LLM 完全没有输出，可能是模型故障，此时才强制 OCR
          - 若 LLM 返回了有内容的文本分析（长度 > 0），说明它在分析正文，
            不触发强制 OCR，直接让它调用 Finish

        Returns:
            Tuple[str, bool]：(JSON 字符串（Finish.answer）或降级文本或空字符串, ocr_called（是否调用了 ocr_images 工具）)
        """
        messages = [
            {"role": "system", "content": get_miner_prompt()},
            {"role": "user",   "content": input_text},
        ]

        client = self._llm._adapter._client  # 底层 OpenAI 兼容客户端（1.0.0 通过 _adapter 访问）
        if client is None:
            self._llm._adapter._client = self._llm._adapter.create_client()
            client = self._llm._adapter._client
        model  = self._llm.model
        temperature = self._llm.temperature
        timeout = self._llm.timeout

        last_text = ""
        ocr_called = False  # 记录 ocr_images 是否已被调用

        for step in range(1, self._max_steps + 1):
            logger.debug(f"[MinerAgent] step {step}/{self._max_steps}, messages={len(messages)}")
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=_ALL_TOOLS,
                    tool_choice="auto",
                    temperature=temperature,
                    timeout=timeout,
                )
            except Exception as e:
                logger.error(f"[MinerAgent] LLM 调用失败 (step {step}): {e}")
                return "", ocr_called

            choice = resp.choices[0]
            msg = choice.message

            # ── 情况 A：LLM 直接返回文本（未调用工具）──────────────
            if not msg.tool_calls:
                text = (msg.content or "").strip()
                logger.info(f"[MinerAgent] step {step}: 纯文本回复（未调用工具），长度={len(text)}")
                last_text = text
                messages.append({"role": "assistant", "content": text})

                if not text and self._image_paths and not ocr_called:
                    # 空文本 + 有图片 + 尚未 OCR → 强制兜底触发 OCR
                    # （LLM 完全没有输出，可能是模型未理解任务）
                    logger.info(f"[MinerAgent] step {step}: 空回复且有图片，强制调用 ocr_images")
                    ocr_result = self._ocr_tool.run({}) or ""
                    ocr_called = True
                    logger.info(f"[MinerAgent] 强制 OCR 完成，结果长度: {len(ocr_result)}")
                    if ocr_result:
                        messages.append({
                            "role": "user",
                            "content": f"图片OCR识别结果如下：\n{ocr_result}\n\n请基于正文和OCR内容提取所有面试题，调用 Finish 工具返回 JSON 数组。"
                        })
                    else:
                        messages.append({
                            "role": "user",
                            "content": "图片OCR未识别到文字。请调用 Finish 工具返回提取结果（无题目时填 '[]'）。"
                        })
                elif not text:
                    # 空文本但无图片（或已 OCR）：提示 LLM 重新分析
                    messages.append({
                        "role": "user",
                        "content": (
                            "请仔细阅读面经正文，按以下步骤操作：\n"
                            "1. 先用 Thought 工具分析正文中的面试题数量和类型\n"
                            "2. 若正文无技术内容且有图片，调用 ocr_images 工具识别图片\n"
                            "3. 最后调用 Finish 工具返回提取结果（有题目填 JSON 数组，完全无关填 NO_RELATED_CONTENT）\n"
                            "注意：禁止直接返回空数组 []，必须先分析内容。"
                        )
                    })
                else:
                    # LLM 已返回有内容的文本分析（正在推理），直接让它调用 Finish
                    # 不触发强制 OCR，让 LLM 自主决定是否需要 OCR
                    messages.append({
                        "role": "user",
                        "content": "请调用 Finish 工具返回提取结果（JSON 数组字符串）。"
                    })
                continue

            # ── 情况 B：LLM 调用了工具 ─────────────────────────────
            # 把 assistant 消息（含 tool_calls）加入消息链
            messages.append(msg)

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(f"[MinerAgent] step {step}: 工具调用 → {tool_name}")

                # ── Finish：提取 answer 并返回 ──────────────────────
                if tool_name == "Finish":
                    answer = self._strip_think_tags(tool_args.get("answer", ""))
                    logger.info(f"[MinerAgent] step {step}: 工具调用 → Finish")
                    logger.debug(f"[MinerAgent] Finish 输出前500字: {answer[:500]}")
                    return answer, ocr_called

                # ── ocr_images：执行并追加 tool result ──────────────
                if tool_name == "ocr_images":
                    ocr_called = True
                tool_result = self._execute_tool(tool_name, tool_args)
                logger.info(f"[MinerAgent] {tool_name} 执行完成，结果长度: {len(tool_result)}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        # 超出最大步数
        logger.warning(f"[MinerAgent] 超过最大步数 {self._max_steps}，返回最后文本")
        return self._strip_think_tags(last_text), ocr_called
