"""
金牌面试官 Agent v5.0 — Agent + Orchestrator 合并版

设计原则：
  • 确定性流程（submit_answer / ingest / end_session）用代码直接编排，无需中间层
  • 判断性流程（chat / chat_stream）走 ReAct LLM 循环
  • ReAct 范式：Thought → Action（工具）→ Observation → 循环，直到 Finish
  • session 由项目 SQLite 管理，每次 chat 前从 SQLite 加载历史到 history_manager
"""
import asyncio
import json
import logging
import re
import requests
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.llm.chained_hello_llm import ChainedHelloAgentsLLM, build_interviewer_hello_llm_list
from backend.tools.interviewer_tools import get_interviewer_tools, KnowledgeRecommender
from backend.agents.prompts.interviewer_prompt import interviewer_prompt
from backend.llm.deepseek_thinking_adapter import DeepSeekThinkingOpenAIAdapter
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.logging.agent_tool_runtime_stats import (
    agent_tool_runtime_stats,
    tool_execution_success_for_stats,
)
from backend.agents.dsml_utils import strip_dsml_from_text

logger = logging.getLogger(__name__)


# ===========================================================
# 模块级辅助
# ===========================================================

def _save_eval_failure(input_preview: str, raw_output: str, error: str) -> None:
    try:
        from backend.services.logging.llm_parse_failures import save_failure
        save_failure(source="answer_eval", input_preview=input_preview,
                     raw_output=raw_output, error=error, metadata={})
    except Exception as e:
        logger.debug(f"保存评估失败记录异常: {e}")


def _chat_stream_user_requests_eval(message: str) -> bool:
    """判断本轮用户是否在「做题并要求评分」场景。

    此类回合里模型可能在工具返回前就流式输出一版草稿评分。抑制正文 llm_chunk 时，
    前端仅以 agent_finish 中的模型最终正文为准，避免先看到与终稿不一致的片段。
    """
    if not message or not str(message).strip():
        return False
    s = str(message).strip()
    if "评分" in s:
        return True
    if "q_id:" in s and ("练习" in s or "道题" in s):
        return True
    return False





_knowledge_recommender = KnowledgeRecommender()


def _is_obs_json(s: str) -> bool:
    """判断观察结果是否为 JSON 格式"""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if not (s.startswith('{') or s.startswith('[')):
        return False
    try:
        import json as _j; _j.loads(s); return True
    except Exception:
        return False


def _normalize_thinking_steps_for_db(steps: list) -> list:
    """
    规范化 thinking_steps 为统一的 DB 存储格式：
    - 去除工具名的 🔧 前缀
    - 统一 result/observation 字段
    - 保留 thought、__step、tools 字段
    - thought 中剔除 DSML，避免推理区展示工具调用原文
    """
    if not isinstance(steps, list):
        return []
    result = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        tools = []
        for t in (step.get('tools') or []):
            if not isinstance(t, dict):
                continue
            name = t.get('name', '') or ''
            if isinstance(name, str):
                name = name.strip()
                while name.startswith('🔧'):
                    name = name[len('🔧'):].strip()
            obs = t.get('result') or t.get('observation') or ''
            obs_str = str(obs) if obs else ''
            tools.append({
                'name': name,
                'args': t.get('args') or {},
                'result': obs_str,
                'observation': obs_str,
                'observationIsJson': _is_obs_json(obs_str),
            })
        _th = step.get("thought", "")
        _thought = strip_dsml_from_text(str(_th) if _th else "")
        result.append({
            '__step': step.get('__step', idx + 1),
            'thought': _thought,
            'tools': tools,
        })
    return result


def _evaluate_answer_structured(question_text: str,
                                user_answer: str,
                                reference_answer: Optional[str] = None) -> Dict[str, Any]:
    """
    结构化评估：直接调用 LLM（JSON mode），不走 ReAct 循环。
    Returns: {score, feedback, shortcomings, error_points, missed_points, strong_points, tags}
    """
    ref_block = ""
    if reference_answer and reference_answer.strip():
        ref_block = f"\n【参考答案/标准答案】（来自题库，用于对比）\n{reference_answer.strip()}\n"

    system = (
        "你是一位技术面试评委。用户将提交面试题目和他们的回答。"
        "你需要评估回答质量，严格按以下 JSON 格式返回，不得添加任何额外字段或注释：\n"
        '{"score":3,"feedback":"总体评价","shortcomings":["不足1"],'
        '"error_points":[{"wrong":"错误表述","correct":"正确表述"}],'
        '"missed_points":["遗漏点"],"strong_points":["答对的点"],"tags":["标签"]}'
        "\n\n【评分规则】"
        "\n1. score 取值仅为以下之一：0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0"
        "\n2. score<5 时，shortcomings 必须列出具体不足"
        "\n3. error_points：含 wrong（错误/不严谨表述）和 correct（正确表述），用于混淆点；无则 []"
        "\n4. missed_points：用户遗漏的知识点，尽量与参考答案维度逐项对齐"
        "\n5. feedback：须含评分细则 + ✓答对 + ✗遗漏 + ⚠混淆点（与 error_points 一致；无混淆时写「无明显概念性混淆」）"
        "\n\n【评分细则】"
        "\n依据：①答对要点占比 ②遗漏要点数 ③混淆/错误数"
        "\n· 5.0：答对核心要点 ≥90%，无遗漏、无错误"
        "\n· 4.0-4.5：答对 ≥70%，遗漏 ≤1 个次要点，无错误"
        "\n· 3.0-3.5：答对 ≥50%，遗漏 1-2 个要点，无严重错误"
        "\n· 2.0-2.5：答对 30%-50%，或存在 1 处概念混淆/错误"
        "\n· 1.0-1.5：答对 <30%，或存在 2+ 处错误"
        "\n· 0-0.5：几乎未答对、大量错误或完全偏题"
    )
    prompt = f"【面试题目】\n{question_text}\n\n【用户回答】\n{user_answer}{ref_block}"

    default = {"score": 3, "feedback": "（评估服务暂时不可用，已记录原始答案）",
               "shortcomings": [], "error_points": [], "missed_points": [],
               "strong_points": [], "tags": [], "_eval_failed": True}
    try:
        _model = settings.interviewer_model or settings.llm_model_id
        # 优先使用 interviewer 专用配置，避免 base_url/api_key 混用导致 404
        _base = (settings.interviewer_base_url or settings.llm_base_url or "").rstrip("/")
        _api_key = settings.interviewer_api_key or settings.llm_api_key
        _timeout = settings.interviewer_timeout or settings.llm_timeout or 60
        _url = f"{_base}/chat/completions" if "/chat/completions" not in _base else _base
        # deepseek-reasoner（R1）不支持 response_format json_object，需去掉该参数
        _is_reasoner = "reasoner" in _model.lower() or "r1" in _model.lower()
        _req_body: Dict[str, Any] = {
            "model": _model,
            "messages": [{"role": "user", "content": f"{system}\n\n{prompt}"}] if _is_reasoner
                         else [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}],
            "temperature": 0.1 if not _is_reasoner else 1,  # reasoner 温度固定为 1
        }
        if not _is_reasoner:
            _req_body["response_format"] = {"type": "json_object"}
        resp = requests.post(
            _url,
            headers={"Authorization": f"Bearer {_api_key}",
                     "Content-Type": "application/json"},
            json=_req_body,
            timeout=_timeout,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"_evaluate_answer_structured JSON 解析失败: {e}")
                _save_eval_failure(prompt, content, error=str(e))
                return default
            raw_score = result.get("score", 3)
            try:
                score_val = float(raw_score)
            except (TypeError, ValueError):
                score_val = 3.0
            result["score"] = max(0.0, min(5.0, round(score_val * 2) / 2))
            return result
        else:
            logger.warning(f"评估 LLM 返回 {resp.status_code}")
            _save_eval_failure(prompt, resp.text[:2000] if resp.text else "",
                               error=f"HTTP {resp.status_code}")
            return default
    except Exception as e:
        logger.error(f"_evaluate_answer_structured 异常: {e}")
        _save_eval_failure(prompt, "", error=str(e))
        return default


def _generate_explanation(question_text: str,
                          evaluation: Dict,
                          recommendation_text: Optional[str],
                          standard_answer: Optional[str] = None) -> str:
    """根据评估结果生成自然语言解释（对话式，面向用户）。"""
    score = evaluation.get("score", 3)
    missed = evaluation.get("missed_points", [])
    strong = evaluation.get("strong_points", [])
    shortcomings = evaluation.get("shortcomings", [])
    error_points = evaluation.get("error_points", [])

    parts = [
        f"题目：{question_text[:200]}",
        f"得分：{score:.1f}/5",
        f"答对的点：{', '.join(strong) if strong else '无'}",
    ]
    if score < 5 and shortcomings:
        parts.append(f"不足（需改进）：{', '.join(shortcomings)}")
    if error_points:
        err_strs = [f"「{e.get('wrong','')}」应改为「{e.get('correct','')}」" for e in error_points[:3]]
        parts.append(f"错误纠正：{'；'.join(err_strs)}")
    if missed:
        parts.append(f"遗漏的点：{', '.join(missed)}")
    parts.append(f"综合评价：{evaluation.get('feedback', '')}")
    if standard_answer and standard_answer.strip():
        parts.append(f"\n【标准答案】（来自题库）\n{standard_answer[:600]}")
    if recommendation_text:
        parts.append(f"\n【知识推荐】\n{recommendation_text[:500]}")

    prompt = "\n".join(parts) + (
        "\n\n请基于以上评估结果，用亲切、鼓励的语气给出解释和建议。"
        "必须做到：1) score<5 时明确指出不足；2) 若有错误点，逐条纠正；"
        "3) 若有遗漏，补充说明；4) 若有标准答案，可引用关键部分帮助用户理解。中文回复，400字以内。"
    )
    try:
        _model = settings.interviewer_model or settings.llm_model_id
        _base = (settings.interviewer_base_url or settings.llm_base_url or "").rstrip("/")
        _url = f"{_base}/chat/completions" if "/chat/completions" not in _base else _base
        _key = settings.interviewer_api_key or settings.llm_api_key
        resp = requests.post(
            _url,
            headers={"Authorization": f"Bearer {_key}",
                     "Content-Type": "application/json"},
            json={"model": _model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7},
            timeout=settings.interviewer_timeout or settings.llm_timeout or 60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"_generate_explanation 异常: {e}")

    # 降级
    lines = [f"✅ 你的得分：{score:.1f}/5\n"]
    if score < 5 and shortcomings:
        lines.append("**不足：** " + "、".join(shortcomings))
    if error_points:
        for e in error_points[:3]:
            lines.append(f"**纠正：** 「{e.get('wrong','')}」→「{e.get('correct','')}」")
    if strong:
        lines.append("**答对的要点：** " + "、".join(strong))
    if missed:
        lines.append("**遗漏的点：** " + "、".join(missed))
    if standard_answer and standard_answer.strip():
        lines.append(f"\n**标准答案：**\n{standard_answer[:400]}")
    return "\n".join(lines)


# ===========================================================
# 辅助函数（流式处理用）
# ===========================================================

def _is_obs_json(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    if not (t.startswith("{") or t.startswith("[")):
        return False
    try:
        json.loads(t)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _normalize_thought_for_step(thought: str) -> str:
    if not thought or not thought.strip():
        return thought or ""
    s = thought.strip()
    if s.startswith("[{") and '"name"' in s[:200]:
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "name" in parsed[0]:
                names = [x.get("name", "?") for x in parsed if isinstance(x, dict) and x.get("name")][:5]
                return "（计划调用: " + ", ".join(names) + (" …" if len(parsed) > 5 else "") + "）"
        except (json.JSONDecodeError, TypeError):
            pass
    if len(s) > 800:
        return s[:800].rstrip() + "…"
    return s


# ===========================================================
# InterviewerAgent：ReAct Agent + 业务编排一体
# ===========================================================

class InterviewerAgent(ReActAgent):
    """
    面试系统核心类 v5.0（Agent + Orchestrator 合并）

    职责：
    ─ 确定性流程（代码）─────────────────────────────────────
      submit_answer()  : 评估→SM-2→记忆→推荐
      ingest_instant() : 立即收录 URL（HunterPipeline + KnowledgeManager）
      ingest_batch()   : 批量收录
      end_session()    : 记忆整合
      update_user_profile() : 写入用户技术画像

    ─ 判断性流程（LLM）──────────────────────────────────────
      chat()           : 同步对话（支持 ThinkingCapture）
      chat_stream()    : 真正流式（arun_stream + SSE）
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

        # ── LLM 配置：INTERVIEWER_REMOTE_FALLBACK_MODELS 多端点故障转移 ─
        _llms = build_interviewer_hello_llm_list(settings)
        _model = settings.interviewer_model or settings.llm_model_id
        if not _llms:
            llm = HelloAgentsLLM(
                model=_model,
                api_key=settings.interviewer_api_key or settings.llm_api_key,
                base_url=settings.interviewer_base_url or settings.llm_base_url,
                temperature=settings.interviewer_temperature,
                timeout=settings.interviewer_timeout or settings.llm_timeout,
            )
        elif len(_llms) > 1:
            for _h in _llms:
                try:
                    _mn = (_h.model or "").strip()
                    if _mn and DeepSeekThinkingOpenAIAdapter(None, None, 1, "")._is_thinking_model(_mn):
                        _h._adapter = DeepSeekThinkingOpenAIAdapter(
                            api_key=_h.api_key,
                            base_url=_h.base_url,
                            timeout=_h.timeout,
                            model=_h.model,
                        )
                except Exception as _e:
                    logger.debug("[InterviewerAgent] DeepSeek adapter 跳过: %s", _e)
            llm = ChainedHelloAgentsLLM(_llms, chain_name="interviewer")
        else:
            llm = _llms[0]
            try:
                if DeepSeekThinkingOpenAIAdapter(None, None, 1, "")._is_thinking_model(_model):
                    llm._adapter = DeepSeekThinkingOpenAIAdapter(
                        api_key=llm.api_key,
                        base_url=llm.base_url,
                        timeout=llm.timeout,
                        model=llm.model,
                    )
                    logger.info(f"[InterviewerAgent] 使用 DeepSeekThinkingOpenAIAdapter：{_model}")
            except Exception as e:
                logger.warning(f"[InterviewerAgent] DeepSeekThinkingOpenAIAdapter 初始化失败: {e}")

        # ── 工具注册 ──────────────────────────────────────────────
        registry = ToolRegistry()
        for tool in get_interviewer_tools():
            registry.register_tool(tool)

        # ── hello-agents Config ──────────────────────────────────
        _data_dir = str(settings.backend_data_dir / "memory")
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        _agent_config = HelloAgentsConfig(
            trace_enabled=True,
            trace_dir=f"{_data_dir}/traces",
            trace_sanitize=True,
            session_enabled=True,
            session_dir="sqlite",
            auto_save_enabled=True,
            auto_save_interval=2,
            context_window=128000,
            compression_threshold=0.8,
            min_retain_rounds=10,
            enable_smart_compression=settings.enable_smart_compression,
            todowrite_enabled=True,
            todowrite_persistence_dir=f"{_data_dir}/todos",
            devlog_enabled=True,
            devlog_persistence_dir=f"{_data_dir}/devlogs",
            skills_enabled=False,
            skills_dir=_skills_dir,
            skills_auto_register=False,
            circuit_enabled=True,
            circuit_failure_threshold=3,
            tool_output_max_lines=500,
            tool_output_max_bytes=20480,
            tool_output_dir=f"{_data_dir}/tool-output",
            subagent_enabled=True,
            async_enabled=True,
            max_concurrent_tools=3,
            hook_timeout_seconds=5.0,
            stream_enabled=settings.interviewer_streamable,
            stream_buffer_size=100,
            stream_include_thinking=True,
            stream_include_tool_calls=True,
        )

        max_steps = getattr(settings, "interviewer_max_steps", 3)

        super().__init__(
            name="InterviewerAgent",
            llm=llm,
            tool_registry=registry,
            system_prompt=interviewer_prompt,
            max_steps=max_steps,
            config=_agent_config,
        )

        if _agent_config.session_enabled:
            from backend.services.storage.sqlite_session_store import SqliteSessionStore
            self.session_store = SqliteSessionStore(session_dir="sqlite")

        # 按 user_id 缓存 session 内的标签失误计数
        self._session_weak_counts: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )

        # 懒加载 KnowledgeManager（避免循环导入）
        self._knowledge_manager = None

        _ep_n = len(_llms) if _llms else 1
        logger.info(
            f"[InterviewerAgent] 初始化完成 endpoints={_ep_n} model={_model} "
            f"base_url={settings.interviewer_base_url or settings.llm_base_url} "
            f"max_steps={max_steps} streamable={settings.interviewer_streamable}"
        )

    @property
    def knowledge_manager(self):
        if self._knowledge_manager is None:
            from backend.services.knowledge.knowledge_manager import knowledge_manager
            self._knowledge_manager = knowledge_manager
        return self._knowledge_manager

    # ===========================================================
    # _build_messages：注入对话历史
    # ===========================================================

    def _build_messages(self, input_text: str) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        history = self.history_manager.get_history()
        max_msgs = settings.interviewer_history_max_messages
        recent = history[-max_msgs:] if len(history) > max_msgs else history
        for msg in recent:
            if msg.role in ("user", "assistant") and (msg.content or "").strip():
                messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": input_text})
        return messages

    # ===========================================================
    # 记忆辅助（四层记忆系统）
    # ===========================================================

    # ===========================================================
    # 重写 _execute_tools_async_stream：在 TOOL_CALL_FINISH 中携带 args
    # ===========================================================

    async def _execute_tools_async_stream(
        self,
        tool_calls,
        current_step: int,
        on_tool_call=None,
    ):
        """
        重写父类方法，使 TOOL_CALL_FINISH StreamEvent 的 data 中包含 args 字段，
        便于前端或其它消费者关联工具入参与结果。
        """
        import asyncio as _asyncio
        from hello_agents.core.streaming import StreamEvent, StreamEventType
        from hello_agents.core.lifecycle import EventType
        from backend.agents.context import get_current_user_id

        results = []
        # 记录本轮流式工具参数（按 tool_call_id 索引），用于 TOOL_CALL_FINISH 丢参时兜底补回。
        # 注意：这是“后端真实参数缓存”，不是前端推断。
        if not hasattr(self, "_stream_tool_args_cache"):
            self._stream_tool_args_cache = {}

        builtin_calls = [tc for tc in tool_calls if tc.function.name in self._builtin_tools]
        user_calls = [tc for tc in tool_calls if tc.function.name not in self._builtin_tools]

        # 1. 串行执行内置工具
        for tc in builtin_calls:
            tool_name = tc.function.name
            tool_call_id = tc.id
            _t0 = time.time()
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                results.append((tool_name, tool_call_id, {"content": f"错误：参数格式不正确 - {str(e)}", "args": {}}))
                self._stream_tool_args_cache[tool_call_id] = {}
                agent_tool_runtime_stats.record(
                    agent_name=self.name,
                    tool_name=tool_name,
                    success=False,
                    execution_time_ms=(time.time() - _t0) * 1000.0,
                    user_id=get_current_user_id(),
                )
                continue
            self._stream_tool_args_cache[tool_call_id] = arguments

            await self._emit_event(
                EventType.TOOL_CALL, on_tool_call,
                tool_name=tool_name, tool_call_id=tool_call_id,
                args=arguments, step=current_step
            )

            if tool_name == "Thought":
                reasoning = arguments.get("reasoning", "")
                print(f"💭 思考: {reasoning}")
                result_content = f"已记录推理过程: {reasoning}"
            elif tool_name == "Finish":
                answer = arguments.get("answer", "")
                print(f"✅ 最终答案: {answer}")
                result_content = answer
            else:
                result_content = f"未知的内置工具: {tool_name}"

            results.append((tool_name, tool_call_id, {"content": result_content, "args": arguments}))
            agent_tool_runtime_stats.record(
                agent_name=self.name,
                tool_name=tool_name,
                success=tool_execution_success_for_stats(str(result_content)),
                execution_time_ms=(time.time() - _t0) * 1000.0,
                user_id=get_current_user_id(),
            )

        # 2. 并行执行用户工具
        if user_calls:
            max_concurrent = getattr(self.config, "max_concurrent_tools", 3)
            semaphore = _asyncio.Semaphore(max_concurrent)

            async def execute_one(tc):
                async with semaphore:
                    tool_name = tc.function.name
                    tool_call_id = tc.id
                    _t0 = time.time()
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as e:
                        self._stream_tool_args_cache[tool_call_id] = {}
                        agent_tool_runtime_stats.record(
                            agent_name=self.name,
                            tool_name=tool_name,
                            success=False,
                            execution_time_ms=(time.time() - _t0) * 1000.0,
                            user_id=get_current_user_id(),
                        )
                        return (tool_name, tool_call_id, {"content": f"错误：参数格式不正确 - {str(e)}", "args": {}})
                    self._stream_tool_args_cache[tool_call_id] = arguments

                    await self._emit_event(
                        EventType.TOOL_CALL, on_tool_call,
                        tool_name=tool_name, tool_call_id=tool_call_id,
                        args=arguments, step=current_step
                    )

                    print(f"🔧 调用工具: {tool_name}({arguments})")

                    tool = self.tool_registry.get_tool(tool_name)
                    response_status = None
                    if not tool:
                        result_content = f"❌ 工具 {tool_name} 不存在"
                    else:
                        try:
                            tool_response = await tool.arun_with_timing(arguments)
                            response_status = tool_response.status
                            result_content = tool_response.text
                            truncate_result = self.truncator.truncate(
                                tool_name=tool_name, output=result_content
                            )
                            result_content = truncate_result.get("preview", result_content)
                        except Exception as e:
                            result_content = f"❌ 工具执行失败: {str(e)}"

                    if self.trace_logger:
                        self.trace_logger.log_event(
                            "tool_result",
                            {"tool_name": tool_name, "tool_call_id": tool_call_id, "result": result_content},
                            step=current_step
                        )

                    if result_content.startswith("❌"):
                        print(result_content)
                    elif result_content.startswith("⚠️"):
                        print(result_content)
                    else:
                        print(f"👀 观察: {result_content}")

                    agent_tool_runtime_stats.record(
                        agent_name=self.name,
                        tool_name=tool_name,
                        success=tool_execution_success_for_stats(
                            str(result_content),
                            response_status=response_status,
                        ),
                        execution_time_ms=(time.time() - _t0) * 1000.0,
                        user_id=get_current_user_id(),
                    )

                    # ✅ 携带 args，便于流式事件消费方读取工具参数
                    return (tool_name, tool_call_id, {"content": result_content, "args": arguments})

            user_results = await _asyncio.gather(*[execute_one(tc) for tc in user_calls])
            results.extend(user_results)

        return results

    def _execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        同步 run() 路径的工具调用统计（chat 非流式兜底）。
        """
        from backend.agents.context import get_current_user_id

        _t0 = time.time()
        try:
            result = super()._execute_tool_call(tool_name, arguments)
            ok = tool_execution_success_for_stats(str(result))
            agent_tool_runtime_stats.record(
                agent_name=self.name,
                tool_name=tool_name,
                success=ok,
                execution_time_ms=(time.time() - _t0) * 1000.0,
                user_id=get_current_user_id(),
            )
            return result
        except Exception:
            agent_tool_runtime_stats.record(
                agent_name=self.name,
                tool_name=tool_name,
                success=False,
                execution_time_ms=(time.time() - _t0) * 1000.0,
                user_id=get_current_user_id(),
            )
            raise

    def _write_episodic(self, user_id: str, content: str,
                        importance: float = 0.75,
                        event_type: str = "study_event",
                        session_id: str = "", **kw):
        try:
            sqlite_service.add_episodic_log(
                user_id=user_id, content=content, importance=importance,
                event_type=event_type,
                session_id=session_id or kw.get("session_id", ""),
                question_id=kw.get("question_id", ""),
                score=kw.get("score"),
            )
        except Exception as e:
            logger.warning(f"[情节记忆] 写入失败: {e}")

    def _write_semantic(self, user_id: str, content: str,
                        importance: float = 0.85,
                        knowledge_type: str = "user_profile", **kw):
        try:
            sqlite_service.add_episodic_log(
                user_id=user_id, content=content, importance=importance,
                event_type=f"semantic_{knowledge_type}", session_id="",
            )
        except Exception as e:
            logger.warning(f"[语义记忆] 写入失败: {e}")

    def _write_working(self, user_id: str, content: str,
                       importance: float = 0.5, session_id: str = ""):
        logger.debug(f"[工作记忆] user={user_id} session={session_id} len={len(content)}")

    def _write_perceptual(self, user_id: str, content: str,
                          modality: str = "text", importance: float = 0.7,
                          file_path: str = None, **kw):
        pass  # 面经场景不需要图像/音频感知

    def _consolidate_session_memories(self, user_id: str):
        logger.debug(f"[记忆整合] user={user_id} - SQLite 自动持久化")

    # ===========================================================
    # 确定性流程：内容采集管道
    # ===========================================================

    async def _run_ingestion_pipeline(self, url: str,
                                      user_id: str = "",
                                      source_platform: str = "") -> str:
        from backend.services.crawler.hunter_pipeline import run_hunter_pipeline
        logger.info(f"📡 [HunterPipeline] 开始处理: {url}")
        pipeline_result = await run_hunter_pipeline(url, source_platform)
        if not pipeline_result.success:
            reason = pipeline_result.skip_reason or "未知原因"
            logger.info(f"⏭️  管道跳过: {reason}")
            return f"跳过（{reason}）"

        logger.info(f"🏗️  [KnowledgeManagerAgent] 开始结构化入库 (文本长度 {len(pipeline_result.text)})...")
        meta_hint = ""
        if pipeline_result.meta:
            meta_hint = f"[元信息提示] {json.dumps(pipeline_result.meta, ensure_ascii=False)}\n\n"

        # 兼容两套 KnowledgeManager 接口：
        # - 旧版：knowledge_manager.run(prompt)
        # - 新版：仅保留 process_question，无 run（爬虫流程已完成题目入库）
        km = self.knowledge_manager
        if hasattr(km, "run") and callable(getattr(km, "run")):
            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                None,
                km.run,
                f"请处理以下文本并存入数据库:\n\n{meta_hint}{pipeline_result.text[:5000]}"
            )
        else:
            q_added = (pipeline_result.meta or {}).get("questions_added", 0)
            t_id = (pipeline_result.meta or {}).get("task_id", "")
            report = f"收录完成：task_id={t_id}，新增题目 {q_added} 道"
        if user_id:
            ocr_note = "（含OCR图片识别）" if pipeline_result.ocr_triggered else ""
            self._write_episodic(
                user_id=user_id,
                content=f"收录面经：{url}{ocr_note}，结果：{report[:80]}",
                importance=0.6,
                event_type="content_ingestion"
            )
        return report

    # ===========================================================
    # 确定性流程：答题提交钩子
    # ===========================================================

    async def submit_answer(self,
                            user_id: str,
                            session_id: str,
                            question_id: str,
                            question_text: str,
                            user_answer: str,
                            question_tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        用户提交答案的确定性处理链：
        A. 获取标准答案  B. 结构化评估  C. SM-2 更新
        C'. 遗漏/混淆写入  D. 标签掌握度  E. 情节记忆
        F. 语义记忆  G. 知识推荐  H. 自然语言解释
        """
        tags = question_tags or []

        # A: 从题库获取标准答案
        reference_answer: Optional[str] = None
        try:
            q_row = sqlite_service.get_question_by_id(question_id)
            if q_row and (q_row.get("answer_text") or "").strip():
                reference_answer = (q_row.get("answer_text") or "").strip()
        except Exception as e:
            logger.warning(f"[submit_answer] 获取标准答案失败: {e}")

        # B: 结构化评估
        logger.info(f"📝 [submit_answer] 评估 q={question_id}")
        loop = asyncio.get_event_loop()
        evaluation = await loop.run_in_executor(
            None,
            lambda: _evaluate_answer_structured(question_text, user_answer,
                                                reference_answer=reference_answer),
        )
        # 评估失败时不继续，直接返回错误（避免用 default score=3 冒充真实评分）
        if evaluation.get("_eval_failed"):
            logger.warning(f"⚠️ [submit_answer] 评估失败，跳过后续流程 q={question_id}")
            raise RuntimeError("评估服务不可用，请稍后重试")
        score = evaluation["score"]
        merged_tags = list(set(tags + evaluation.get("tags", [])))

        # C: SM-2 更新
        feedback_parts = [evaluation.get("feedback", "")]
        if evaluation.get("shortcomings"):
            feedback_parts.append("不足：" + "、".join(evaluation["shortcomings"]))
        if evaluation.get("error_points"):
            errs = [f"{e.get('wrong','')}→{e.get('correct','')}" for e in evaluation["error_points"][:3]]
            feedback_parts.append("错误纠正：" + "；".join(errs))
        if evaluation.get("missed_points"):
            feedback_parts.append("遗漏：" + "、".join(evaluation["missed_points"][:5]))
        ai_feedback = "；".join(feedback_parts)
        eval_details = {
            "shortcomings": evaluation.get("shortcomings", []),
            "error_points": evaluation.get("error_points", []),
            "missed_points": evaluation.get("missed_points", []),
            "strong_points": evaluation.get("strong_points", []),
        }
        message_id = f"eval_{question_id}_{int(time.time() * 1000)}"
        sqlite_service.add_study_record(
            user_id=user_id, question_id=question_id, score=score,
            user_answer=user_answer, ai_feedback=ai_feedback,
            session_id=session_id, message_id=message_id, eval_details=eval_details,
        )

        # C': 遗漏/混淆写入 episodic_log + user_notes
        missed_points = list(evaluation.get("missed_points") or [])
        error_points = list(evaluation.get("error_points") or [])
        if not missed_points and evaluation.get("shortcomings"):
            missed_points.extend([s for s in evaluation["shortcomings"] if s and str(s).strip()])
        for m in missed_points:
            if not (m and str(m).strip()):
                continue
            content = f"遗漏点：{m}"
            sqlite_service.add_episodic_log(
                user_id=user_id, content=content, importance=0.85,
                event_type="user_missed", session_id=session_id or "",
                question_id=question_id, score=score,
            )
            try:
                sqlite_service.add_note(user_id=user_id, content=content,
                                        question_id=question_id,
                                        note_type="weakness", tags=["遗漏点"])
            except Exception as ex:
                logger.debug("add_note(遗漏) 忽略: %s", ex)
        for e in (error_points or []):
            if not isinstance(e, dict):
                continue
            w, c = e.get("wrong", ""), e.get("correct", "")
            content = (f"混淆点：用户说的「{w}」应改为「{c}」" if w and c and w != c
                       else f"混淆点：{w or c}")
            sqlite_service.add_episodic_log(
                user_id=user_id, content=content, importance=0.85,
                event_type="user_confusion", session_id=session_id or "",
                question_id=question_id, score=score,
            )
            try:
                sqlite_service.add_note(user_id=user_id, content=content,
                                        question_id=question_id,
                                        note_type="confusion", tags=["混淆点"])
            except Exception as ex:
                logger.debug("add_note(混淆) 忽略: %s", ex)

        # D: 标签掌握度
        if merged_tags:
            sqlite_service.update_tag_mastery(user_id, merged_tags, score)

        # E: 情节记忆
        self._write_episodic(
            user_id=user_id,
            content=(
                f"回答了题目【{question_text[:60]}】，得分 {score}/5。"
                f"标签：{', '.join(merged_tags)}。"
                + (f"遗漏：{evaluation['missed_points'][:2]}"
                   if evaluation.get("missed_points") else "")
            ),
            importance=0.65 + score * 0.05,
            event_type="study_record",
            question_id=question_id, score=score, session_id=session_id
        )

        # F: 语义记忆
        if score <= 2:
            self._write_semantic(
                user_id=user_id,
                content=f"用户对【{'、'.join(merged_tags)}】掌握薄弱（{score}/5），需重点加强",
                importance=0.82, knowledge_type="weakness"
            )
        elif score >= 4:
            self._write_semantic(
                user_id=user_id,
                content=f"用户对【{'、'.join(merged_tags)}】掌握较好（{score}/5）",
                importance=0.75, knowledge_type="strength"
            )

        # G: 连续薄弱检测 + 知识推荐
        recommendation_text: Optional[str] = None
        if score <= 2 and merged_tags:
            for tag in merged_tags:
                self._session_weak_counts[user_id][session_id][tag] += 1
            recommendation_text = _knowledge_recommender.run({
                "user_id": user_id, "tags": merged_tags,
                "max_resources": 2, "max_mistakes": 3
            })
            consecutive_tags = [
                t for t in merged_tags
                if self._session_weak_counts[user_id][session_id][t] >= 2
            ]
            if consecutive_tags:
                logger.info(f"🔁 连续薄弱标签: {consecutive_tags}")
                self._write_semantic(
                    user_id=user_id,
                    content=f"用户对【{'、'.join(consecutive_tags)}】多次失误，需系统学习",
                    importance=0.92, knowledge_type="repeated_weakness"
                )

        # H: 生成自然语言解释
        explanation = await loop.run_in_executor(
            None,
            lambda: _generate_explanation(question_text, evaluation,
                                          recommendation_text,
                                          standard_answer=reference_answer),
        )

        logger.info(f"✅ [submit_answer] score={score}, tags={merged_tags}")
        return {
            "score": score,
            "feedback": evaluation.get("feedback", ""),
            "shortcomings": evaluation.get("shortcomings", []),
            "error_points": evaluation.get("error_points", []),
            "missed_points": evaluation.get("missed_points", []),
            "strong_points": evaluation.get("strong_points", []),
            "explanation": explanation,
            "recommendation": recommendation_text,
            "standard_answer": reference_answer or "",
            "tags": merged_tags
        }

    # ===========================================================
    # 对话接口（同步，支持 ThinkingCapture）
    # ===========================================================

    async def chat(
        self,
        user_id: str,
        message: str,
        resume: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> tuple:
        """自由对话：出题推荐、概念解释、笔记管理、掌握度查询等。
        返回 (reply: str, thinking_steps: List[Dict])。
        """
        start_time = time.time()
        logger.info("=" * 60)
        logger.info(f"[对话处理] 开始处理用户 {user_id} 的消息")

        if not session_id:
            session_id = settings.default_session_id

        from backend.agents.context import set_current_user_id, set_current_session_id, set_current_user_message
        from backend.agents.thinking_capture import ThinkingCapture
        set_current_user_id(user_id)
        set_current_session_id(session_id)
        set_current_user_message(message)

        sqlite_service.ensure_session_exists(session_id, user_id)
        self._write_working(user_id, f"用户：{message}", session_id=session_id)
        if resume:
            self._write_perceptual(user_id, f"简历内容（{len(resume)}字）",
                                   modality="text", importance=0.8, session_id=session_id)

        session_path = f"{user_id}:{session_id}"
        try:
            self.load_session(session_path, check_consistency=False)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[对话处理] load_session 失败: {e}")

        context_prefix = "\n".join(filter(None, [
            f"[系统] user_id={user_id}, session_id={session_id}",
            f"[简历]\n{resume}" if resume else "",
        ]))
        full_input = f"{context_prefix}\n\n[用户消息]\n{message}" if context_prefix.strip() else message

        logger.info(f"[对话处理] 💬 处理消息: {message[:80]}")
        loop = asyncio.get_event_loop()

        def _run_with_capture():
            with ThinkingCapture() as tc:
                return self.run(full_input), tc.get_steps()

        try:
            timeout_cfg = getattr(settings, "interviewer_timeout", None) or getattr(settings, "llm_timeout", None)
            timeout = float(timeout_cfg or 60)
            response, thinking_steps = await asyncio.wait_for(
                loop.run_in_executor(None, _run_with_capture),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[对话处理] ⚠️ Agent 超时（{timeout}s）")
            response = "抱歉，处理您的请求耗时较长，请稍后重试。"
            thinking_steps = []
        except Exception as agent_err:
            logger.error(f"[对话处理] ❌ run() 异常: {agent_err}", exc_info=True)
            raise

        logger.info(f"[对话处理] ✅ 回复完成 ({len(response)}字, 思考{len(thinking_steps)}步)")

        try:
            self.save_session(session_id)
        except Exception as e:
            logger.warning(f"[对话处理] save_session 失败: {e}")

        self._write_working(user_id, f"AI：{response[:200]}", importance=0.4, session_id=session_id)
        self._write_episodic(
            user_id=user_id,
            content=f"对话：「{message[:60]}」→「{response[:60]}」",
            importance=0.5, event_type="dialogue", session_id=session_id
        )

        try:
            from backend.services.logging.interviewer_logger import get_interviewer_logger
            il = get_interviewer_logger()
            il.log_chat(user_id=user_id, session_id=session_id,
                        user_message=message, ai_response=response,
                        thinking_steps=thinking_steps,
                        metadata={"has_resume": bool(resume),
                                  "resume_length": len(resume) if resume else 0,
                                  "full_input_length": len(full_input)})
            if thinking_steps:
                il.log_thinking(user_id=user_id, session_id=session_id,
                                user_message=message, thinking_steps=thinking_steps)
        except Exception as log_err:
            logger.warning(f"日志保存失败: {log_err}")

        # 🔧 关键修复：持久化推理步骤到数据库，确保刷新后仍能显示
        try:
            normalized_steps = _normalize_thinking_steps_for_db(thinking_steps) if thinking_steps else None
            sqlite_service.patch_last_assistant_content(
                session_id,
                response or "（无文本回答）",
                normalized_steps or None,
                int((time.time() - start_time) * 1000),
            )
            logger.info(f"[对话处理] 💾 推理步骤已持久化: {len(normalized_steps) if normalized_steps else 0} 步")
        except Exception as e:
            logger.error(f"[对话处理] 推理步骤持久化失败: {e}", exc_info=True)

        logger.info(f"[性能] 总耗时: {time.time() - start_time:.2f}s")
        logger.info("=" * 60)
        return response, thinking_steps

    # ===========================================================
    # 流式对话
    # ===========================================================

    async def chat_stream(
        self,
        user_id: str,
        message: str,
        resume: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """流式对话：hello_agents arun_stream()；事件推送前端。

        评分类用户消息（含「评分」或 练习+q_id）时：可不向客户端转发正文 llm_chunk；
        agent_finish 中的正文为 ReAct 返回的模型最终输出（final answer），不再用 submit_answer
        的 JSON 覆盖聊天内容。

        若 settings.interviewer_streamable 为 False，整轮仍完整跑完 arun_stream（不省略推理/思考/工具/正文），
        仅在结束后按相同事件顺序一次性 yield SSE。"""
        start_time = time.time()
        if not session_id:
            session_id = settings.default_session_id

        from backend.agents.context import set_current_user_id, set_current_session_id, set_current_user_message
        set_current_user_id(user_id)
        set_current_session_id(session_id)
        set_current_user_message(message)

        await asyncio.to_thread(sqlite_service.ensure_session_exists, session_id, user_id)
        self._write_working(user_id, f"用户：{message}", session_id=session_id)
        if resume:
            self._write_perceptual(user_id, f"简历内容（{len(resume)}字）",
                                   modality="text", importance=0.8, session_id=session_id)

        session_path = f"{user_id}:{session_id}"
        try:
            await asyncio.to_thread(lambda: self.load_session(session_path, check_consistency=False))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[chat_stream] load_session 失败: {e}")

        context_prefix = "\n".join(filter(None, [
            f"[系统] user_id={user_id}, session_id={session_id}",
            f"[简历]\n{resume}" if resume else "",
        ]))
        full_input = f"{context_prefix}\n\n[用户消息]\n{message}" if context_prefix.strip() else message

        await asyncio.to_thread(sqlite_service.update_session_history, session_id, "user", message)
        await asyncio.to_thread(sqlite_service.update_session_history, session_id, "assistant", "（生成中...）")

        full_content = ""
        duration_ms = 0
        final_thinking_steps: list = []
        raw_agent_finish_result = ""
        _sse_buffer: list = []
        _stream_to_client = settings.interviewer_streamable
        if not _stream_to_client:
            logger.info("[chat_stream] INTERVIEWER_STREAMABLE=false，将整轮完成后一次性下发（跳过 llm_chunk）")

        suppress_eval_body_chunks = bool(_stream_to_client and _chat_stream_user_requests_eval(message))
        if suppress_eval_body_chunks:
            logger.info("[chat_stream] 评分类消息：抑制正文 llm_chunk 下发，最终以 agent_finish 模型终稿为准")

        def _sanitize_stream_text(raw: str) -> str:
            """直接返回原始文本，DeepSeek 已能正确处理。"""
            return str(raw) if raw else ""

        try:
            from hello_agents.core.streaming import StreamEvent, StreamEventType

            _last_db_progress_ts = 0.0
            _db_progress_interval_sec = 0.45

            async for event in self.arun_stream(full_input):
                # 累积最终文本 & 推理步骤
                if event.type.value == "llm_chunk":
                    chunk = event.data.get("chunk") or event.data.get("content") or ""
                    full_content += chunk
                    # 流式正文节流落库：刷新页面时至少能恢复已生成的部分正文（推理步骤由前端 localStorage 兜底）
                    _now_pg = time.time()
                    if _now_pg - _last_db_progress_ts >= _db_progress_interval_sec:
                        _strip = (full_content or "").strip()
                        if len(_strip) >= 12:
                            _last_db_progress_ts = _now_pg
                            try:
                                await asyncio.to_thread(
                                    sqlite_service.patch_last_assistant_content,
                                    session_id,
                                    full_content,
                                    None,
                                    None,
                                )
                            except Exception as _pg_err:
                                logger.debug("[chat_stream] 中间落库跳过: %s", _pg_err)
                elif event.type.value == "agent_finish":
                    result = event.data.get("result") or ""
                    raw_agent_finish_result = str(result or "")
                    full_content = _sanitize_stream_text(result)
                    raw_steps = event.data.get("thinking") or []
                    if isinstance(raw_steps, list) and raw_steps:
                        final_thinking_steps = _normalize_thinking_steps_for_db(raw_steps)

                skip_chunk_to_client = (
                    suppress_eval_body_chunks and event.type.value == "llm_chunk"
                )
                if event.type.value == "agent_finish":
                    _agent_name = getattr(event, "agent_name", None) or self.name
                    _finish_data = dict(event.data or {})
                    _finish_data["result"] = full_content
                    sse_line = StreamEvent.create(
                        StreamEventType.AGENT_FINISH,
                        _agent_name,
                        **_finish_data,
                    ).to_sse()
                else:
                    sse_line = event.to_sse()

                if isinstance(sse_line, str) and sse_line.strip():
                    if not _stream_to_client and event.type.value == "llm_chunk":
                        continue  # 非流式模式跳过 llm_chunk，正文仅在 agent_finish 整块展示
                    if skip_chunk_to_client:
                        continue
                    if not sse_line.endswith("\n\n"):
                        sse_line += "\n\n"
                    if _stream_to_client:
                        yield sse_line
                    else:
                        _sse_buffer.append(sse_line)

            # 流结束：持久化
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "[chat_stream] DeepSeek最终返回 raw_len=%s final_len=%s preview=%r",
                len(raw_agent_finish_result or ""),
                len(full_content or ""),
                (full_content or "")[:300],
            )
            try:
                await asyncio.to_thread(self.save_session, session_id)
                await asyncio.to_thread(
                    sqlite_service.patch_last_assistant_content,
                    session_id,
                    full_content or "（无文本回答）",
                    final_thinking_steps or None,
                    duration_ms,
                )
            except Exception as e:
                logger.error(f"[chat_stream] 保存失败: {e}", exc_info=True)

            if not _stream_to_client and _sse_buffer:
                logger.info(
                    "[chat_stream] interviewer_streamable=false，一次性下发 %s 条 SSE（内容未删减）",
                    len(_sse_buffer),
                )
                for _line in _sse_buffer:
                    yield _line

            self._write_working(user_id, f"AI：{full_content[:100]}", importance=0.4, session_id=session_id)
            await asyncio.to_thread(
                lambda: self._write_episodic(
                    user_id, f"对话：「{message[:60]}」→「{full_content[:60]}」",
                    importance=0.5, event_type="dialogue", session_id=session_id
                )
            )

        except asyncio.TimeoutError:
            _to = settings.interviewer_timeout
            logger.warning(f"[chat_stream] 超时（{_to}s）")
            from hello_agents.core.streaming import StreamEvent, StreamEventType
            err_ev = StreamEvent.create(StreamEventType.ERROR, "InterviewerAgent",
                                        error=f"⚠️ 响应超时（{_to}s），请稍后重试")
            yield err_ev.to_sse()
        except Exception as e:
            logger.error(f"[chat_stream] 异常: {e}", exc_info=True)
            from hello_agents.core.streaming import StreamEvent, StreamEventType
            error_msg = str(e)
            if "Connection error" in error_msg or "连接" in error_msg:
                display_msg = "⚠️ 工具调用失败：连接错误，请检查后端服务状态"
            elif "timeout" in error_msg.lower():
                display_msg = "⚠️ 工具调用失败：请求超时，请稍后重试"
            elif "submit_answer" in error_msg:
                display_msg = "⚠️ 答案提交失败：无法保存评分，请检查数据库连接"
            else:
                display_msg = f"⚠️ 工具调用失败：{error_msg[:200]}"
            err_ev = StreamEvent.create(
                StreamEventType.ERROR,
                "InterviewerAgent",
                error=display_msg,
                tool_error=error_msg[:500]
            )
            yield err_ev.to_sse()

    # ===========================================================
    # 公开接口
    # ===========================================================

    async def ingest_instant(self, url: str, user_id: str,
                             source_platform: str = "") -> Dict[str, Any]:
        """立即收录一条 URL"""
        logger.info(f"⚡ 用户 {user_id} 触发立即收录: {url}")
        try:
            report = await self._run_ingestion_pipeline(url, user_id, source_platform)
            return {"status": "success", "details": report}
        except Exception as e:
            logger.error(f"❌ 立即收录失败: {e}")
            return {"status": "error", "message": str(e)}

    async def ingest_batch(self, urls: List[str],
                           source_platform: str = "") -> Dict[str, Any]:
        """批量收录"""
        logger.info(f"⏰ 批量收录: {len(urls)} 条")
        results = []
        for url in urls:
            try:
                report = await self._run_ingestion_pipeline(url, source_platform=source_platform)
                results.append({"url": url, "status": "success", "report": report})
            except Exception as e:
                logger.error(f"⚠️ 处理失败 {url}: {e}")
                results.append({"url": url, "status": "failed", "error": str(e)})
        success_count = sum(1 for r in results if r["status"] == "success")
        return {"summary": f"成功: {success_count}/{len(urls)}", "details": results}

    async def end_session(self, user_id: str, session_id: str,
                          session_summary: str = ""):
        """结束 session：整合记忆。"""
        if session_summary:
            self._write_episodic(
                user_id=user_id,
                content=f"Session 结束：{session_summary}",
                importance=0.88, event_type="session_complete", session_id=session_id
            )
        self._consolidate_session_memories(user_id)
        if user_id in self._session_weak_counts:
            self._session_weak_counts[user_id].pop(session_id, None)
        logger.info(f"✅ Session {session_id} 已结束")

    async def update_user_profile(self, user_id: str, tech_stack: List[str],
                                  target_company: str = "",
                                  target_position: str = "",
                                  experience_level: str = "junior"):
        """写入用户技术画像到语义记忆。"""
        parts = [f"用户技术栈：{', '.join(tech_stack)}"]
        if target_company:
            parts.append(f"目标公司：{target_company}")
        if target_position:
            parts.append(f"目标岗位：{target_position}")
        parts.append(f"经验等级：{experience_level}")
        self._write_semantic(user_id, "。".join(parts), importance=0.92,
                             knowledge_type="user_profile")
        logger.info(f"✅ 用户 {user_id} 技术画像写入语义记忆")

    async def arun_stream(self, input_text: str, **kwargs):
        """
        覆盖父类：
        1. 若适配器实现 astream_invoke_with_tools（DeepSeekThinkingOpenAIAdapter）：每步仅一次
           stream+tools 请求，不再使用父类「无 tools 流式 + invoke_with_tools」双请求。
        2. 在 LLM_CHUNK 之后检测 reasoning_content，补推 THINKING 事件（DeepSeek 思维链）
        3. 在 TOOL_CALL_FINISH 之前补推 TOOL_CALL_START 事件
        4. 在 AGENT_FINISH 时把完整 thinking_steps 附加到事件 data 中
        """
        from hello_agents.core.streaming import StreamEvent, StreamEventType

        step_counter = 0
        current_step = 0
        thinking_steps: list = []           # 汇总所有步骤，附到 agent_finish
        current_step_obj: dict = {}          # 当前步骤的数据
        step_tools_started: dict = {}        # step_no -> [tool_name, ...]
        thinking_emitted_for_step: set = set()  # 已推 thinking 的 step 编号
        step_incremental_thinking: set = set()  # 已通过 THINKING 流式推过的 step，避免 STEP_FINISH 再整包重复

        def _normalize_tool_args(raw_args: Any) -> Dict[str, Any]:
            if raw_args is None:
                return {}
            if isinstance(raw_args, dict):
                return raw_args
            if isinstance(raw_args, str):
                s = raw_args.strip()
                if not s:
                    return {}
                try:
                    parsed = json.loads(s)
                    return parsed if isinstance(parsed, dict) else {"_raw": s}
                except Exception:
                    return {"_raw": s}
            return {"_raw": str(raw_args)}

        _adapter = getattr(getattr(self, "llm", None), "_adapter", None)
        if _adapter is not None and callable(
            getattr(_adapter, "astream_invoke_with_tools", None)
        ):
            from backend.agents.react_stream_single_request import (
                react_arun_stream_single_tool_stream,
            )

            _base_stream = react_arun_stream_single_tool_stream(
                self, input_text, **kwargs
            )
        else:
            _base_stream = super().arun_stream(input_text, **kwargs)

        async for event in _base_stream:
            ev_name = event.type.name  # 'STEP_START' / 'LLM_CHUNK' / ...

            if ev_name == "STEP_START":
                step_counter += 1
                current_step = event.data.get("step", step_counter)
                current_step_obj = {"__step": current_step, "thought": "", "tools": []}
                step_tools_started[current_step] = []
                yield event

            elif ev_name == "LLM_CHUNK":
                yield event
            elif ev_name == "THINKING":
                # 适配层已按 delta.reasoning_content 拆片；直接透传，并在本步聚合 thought（供 agent_finish）
                raw_step = event.data.get("step", current_step)
                try:
                    step_no = int(raw_step)
                except (TypeError, ValueError):
                    step_no = current_step
                chunk = event.data.get("chunk") or ""
                if chunk:
                    step_incremental_thinking.add(step_no)
                    if current_step_obj.get("__step") == step_no:
                        prev = current_step_obj.get("thought") or ""
                        current_step_obj["thought"] = prev + chunk
                yield event
            elif ev_name == "TOOL_CALL":
                # 框架若能在工具执行前发出 TOOL_CALL，这里直接转成前端消费的 TOOL_CALL_START，
                # 避免只能在 TOOL_CALL_FINISH 时“补发 start”，导致看起来不实时。
                tool_name = event.data.get("tool_name", "")
                step_no = event.data.get("step", current_step)
                args = _normalize_tool_args(
                    event.data.get("args", event.data.get("tool_args", event.data.get("arguments")))
                )
                started = step_tools_started.get(step_no, [])
                if tool_name and tool_name not in ("Thought", "Finish") and tool_name not in started:
                    started.append(tool_name)
                    step_tools_started[step_no] = started
                    yield StreamEvent.create(
                        StreamEventType.TOOL_CALL_START,
                        self.name,
                        tool_name=tool_name,
                        args=args,
                        step=step_no,
                    )
            elif ev_name == "TOOL_CALL_FINISH":
                tool_name = event.data.get("tool_name", "")
                step_no = event.data.get("step", current_step)
                tool_call_id = event.data.get("tool_call_id", "")
                raw_args = (
                    event.data.get("args")
                    if "args" in event.data
                    else event.data.get("tool_args", event.data.get("arguments"))
                )
                # 若底层 finish 事件丢参，强制使用后端执行时缓存的真实 args 回填
                if (raw_args is None or raw_args == "" or raw_args == {}) and tool_call_id:
                    raw_args = getattr(self, "_stream_tool_args_cache", {}).get(tool_call_id)
                args = _normalize_tool_args(raw_args)
                result = event.data.get("result", "")

                # 若该工具尚未推 start，补发一个（框架未推 TOOL_CALL_START）
                started = step_tools_started.get(step_no, [])
                if tool_name not in started and tool_name not in ("Thought", "Finish"):
                    started.append(tool_name)
                    step_tools_started[step_no] = started
                    yield StreamEvent.create(
                        StreamEventType.TOOL_CALL_START,
                        self.name,
                        tool_name=tool_name,
                        args=args,
                        step=step_no,
                    )

                # 记录到当前步骤汇总
                if tool_name not in ("Thought", "Finish"):
                    current_step_obj["tools"].append({
                        "name": tool_name,
                        "args": args,
                        "result": result,
                    })
                # 强制回传 args，避免部分底层适配器在 finish 事件里丢参
                enriched_finish = dict(event.data or {})
                enriched_finish["args"] = args
                if "result" not in enriched_finish:
                    enriched_finish["result"] = result
                if "step" not in enriched_finish:
                    enriched_finish["step"] = step_no
                if "tool_name" not in enriched_finish:
                    enriched_finish["tool_name"] = tool_name
                if "tool_call_id" not in enriched_finish and tool_call_id:
                    enriched_finish["tool_call_id"] = tool_call_id
                yield StreamEvent.create(
                    StreamEventType.TOOL_CALL_FINISH,
                    self.name,
                    **enriched_finish,
                )
                if tool_call_id:
                    try:
                        getattr(self, "_stream_tool_args_cache", {}).pop(tool_call_id, None)
                    except Exception:
                        pass

            elif ev_name == "STEP_FINISH":
                # 保存当前步骤到汇总
                # 流式推理已在 THINKING 事件中按片发出；此处用 last_stats 中的全文做 canonical thought（含 DSML 清洗）
                rc = ""
                _adapter = getattr(getattr(self, "llm", None), "_adapter", None)
                if _adapter and hasattr(_adapter, "last_stats"):
                    _stats = _adapter.last_stats
                    rc = getattr(_stats, "reasoning_content", None) or ""
                if not rc:
                    _llm = getattr(self, "llm", None)
                    _stats = getattr(_llm, "last_call_stats", None)
                    rc = getattr(_stats, "reasoning_content", None) or ""
                rc_show = strip_dsml_from_text(rc) if rc else ""
                if rc_show:
                    current_step_obj["thought"] = rc_show
                had_incremental = current_step in step_incremental_thinking
                if current_step not in thinking_emitted_for_step:
                    if rc_show and not had_incremental:
                        logger.info(f"[arun_stream] THINKING(整包) step={current_step} len={len(rc_show)}")
                        yield StreamEvent.create(
                            StreamEventType.THINKING,
                            self.name,
                            chunk=rc_show,
                            step=current_step,
                        )
                    elif rc_show and had_incremental:
                        logger.debug(
                            f"[arun_stream] step={current_step} 已流式 THINKING，STEP_FINISH 不再整包重复"
                        )
                    elif not rc_show and rc:
                        logger.debug(
                            f"[arun_stream] THINKING step={current_step} 经 DSML 清洗后为空，跳过整包"
                        )
                    elif not rc:
                        logger.debug(
                            f"[arun_stream] THINKING 缺失 step={current_step}（adapter 未返回 reasoning_content）"
                        )
                    thinking_emitted_for_step.add(current_step)
                if current_step_obj.get("__step"):
                    thinking_steps.append(dict(current_step_obj))
                yield event

            elif ev_name == "AGENT_FINISH":
                # 把完整 thinking_steps 附加到 agent_finish 事件
                # 兜底：部分流实现可能直接 AGENT_FINISH 而未发 STEP_FINISH，此时 current_step_obj 尚未并入
                if current_step_obj.get("__step"):
                    _sn = current_step_obj.get("__step")
                    if not any(
                        isinstance(s, dict) and s.get("__step") == _sn for s in thinking_steps
                    ):
                        _th = (current_step_obj.get("thought") or "").strip()
                        _tools = current_step_obj.get("tools") or []
                        if _th or _tools:
                            thinking_steps.append(dict(current_step_obj))
                enriched = dict(event.data)
                enriched["thinking"] = thinking_steps
                yield StreamEvent.create(
                    StreamEventType.AGENT_FINISH,
                    self.name,
                    **enriched,
                )

            else:
                yield event


# ===========================================================
# 单例（供 main.py 通过 get_orchestrator() 获取，零改动）
# ===========================================================
_agent_instance: Optional[InterviewerAgent] = None


def get_orchestrator() -> InterviewerAgent:
    """返回 InterviewerAgent 单例（原 get_orchestrator 接口，向后兼容）。"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = InterviewerAgent()
    return _agent_instance 