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
import requests
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.tools.interviewer_tools import get_interviewer_tools, KnowledgeRecommender
from backend.agents.prompts.interviewer_prompt import interviewer_prompt
from backend.llm.deepseek_thinking_adapter import DeepSeekThinkingOpenAIAdapter
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.logging.agent_tool_runtime_stats import agent_tool_runtime_stats

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


def _fix_json_invalid_escape(s: str) -> str:
    """修复 LLM 返回的 JSON 中非法转义，避免 Invalid \\escape 解析失败。"""
    if not s or "\\" not in s:
        return s
    res = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in '"\\/bfnrt':
                res.append(s[i])
                res.append(n)
                i += 2
                continue
            if n == "u" and i + 5 <= len(s):
                hex_part = s[i + 2 : i + 6]
                if all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    res.append(s[i : i + 6])
                    i += 6
                    continue
            res.append("\\\\")
            res.append(n)
            i += 2
            continue
        res.append(s[i])
        i += 1
    return "".join(res)


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
        result.append({
            '__step': step.get('__step', idx + 1),
            'thought': step.get('thought', ''),
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
        "\n3. error_points：含 wrong（错误）和 correct（正确），用于纠正"
        "\n4. missed_points：用户遗漏的知识点"
        "\n5. feedback：分条列点，包含亮点、不足、错误纠正、遗漏补充、改进建议"
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
            result = None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                try:
                    result = json.loads(_fix_json_invalid_escape(content))
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

        # ── LLM 配置 ──────────────────────────────────────────────
        _model = settings.interviewer_model or settings.llm_model_id
        llm = HelloAgentsLLM(
            model=_model,
            api_key=settings.interviewer_api_key or settings.llm_api_key,
            base_url=settings.interviewer_base_url or settings.llm_base_url,
            temperature=settings.interviewer_temperature,
            timeout=settings.interviewer_timeout or settings.llm_timeout,
        )

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
            stream_enabled=True,
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

        logger.info(
            f"[InterviewerAgent] 初始化完成 model={_model} "
            f"base_url={settings.interviewer_base_url or settings.llm_base_url} "
            f"max_steps={max_steps}"
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
        从而让 chat_stream 的 tool_call_finish 处理逻辑能正确读取工具参数。
        """
        import asyncio as _asyncio
        from hello_agents.core.streaming import StreamEvent, StreamEventType
        from hello_agents.core.lifecycle import EventType
        from backend.agents.context import get_current_user_id

        results = []

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
                agent_tool_runtime_stats.record(
                    agent_name=self.name,
                    tool_name=tool_name,
                    success=False,
                    execution_time_ms=(time.time() - _t0) * 1000.0,
                    user_id=get_current_user_id(),
                )
                continue

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
                success=not str(result_content).startswith("❌"),
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
                        agent_tool_runtime_stats.record(
                            agent_name=self.name,
                            tool_name=tool_name,
                            success=False,
                            execution_time_ms=(time.time() - _t0) * 1000.0,
                            user_id=get_current_user_id(),
                        )
                        return (tool_name, tool_call_id, {"content": f"错误：参数格式不正确 - {str(e)}", "args": {}})

                    await self._emit_event(
                        EventType.TOOL_CALL, on_tool_call,
                        tool_name=tool_name, tool_call_id=tool_call_id,
                        args=arguments, step=current_step
                    )

                    print(f"🔧 调用工具: {tool_name}({arguments})")

                    tool = self.tool_registry.get_tool(tool_name)
                    if not tool:
                        result_content = f"❌ 工具 {tool_name} 不存在"
                    else:
                        try:
                            tool_response = await tool.arun_with_timing(arguments)
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
                    else:
                        print(f"👀 观察: {result_content}")

                    agent_tool_runtime_stats.record(
                        agent_name=self.name,
                        tool_name=tool_name,
                        success=not str(result_content).startswith("❌"),
                        execution_time_ms=(time.time() - _t0) * 1000.0,
                        user_id=get_current_user_id(),
                    )

                    # ✅ 携带 args，供 chat_stream 的 tool_call_finish 处理逻辑读取
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
            ok = not str(result).startswith("❌")
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

        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            self.knowledge_manager.run,
            f"请处理以下文本并存入数据库:\n\n{meta_hint}{pipeline_result.text[:5000]}"
        )
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
        """流式对话：直接使用 hello_agents arun_stream()，所有事件原样推送前端。"""
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
        final_thinking_steps: list = []  # 从 agent_finish 提取的完整推理步骤

        try:
            async for event in self.arun_stream(full_input):
                sse_line = event.to_sse()
                # 累积最终文本 & 推理步骤
                if event.type.value == "llm_chunk":
                    chunk = event.data.get("chunk") or event.data.get("content") or ""
                    full_content += chunk
                elif event.type.value == "agent_finish":
                    result = event.data.get("result") or ""
                    if result.strip():
                        full_content = result  # agent_finish.result 是最终完整答案，直接覆盖
                    # 提取 arun_stream 附加的完整 thinking_steps
                    raw_steps = event.data.get("thinking") or []
                    if isinstance(raw_steps, list) and raw_steps:
                        final_thinking_steps = _normalize_thinking_steps_for_db(raw_steps)
                if isinstance(sse_line, str) and sse_line.strip():
                    if not sse_line.endswith("\n\n"):
                        sse_line += "\n\n"
                    yield sse_line

            # 流结束：持久化
            duration_ms = int((time.time() - start_time) * 1000)
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
        1. 在 LLM_CHUNK 之后检测 reasoning_content，补推 THINKING 事件（DeepSeek 思维链）
        2. 在 TOOL_CALL_FINISH 之前补推 TOOL_CALL_START 事件
        3. 在 AGENT_FINISH 时把完整 thinking_steps 附加到事件 data 中
        """
        from hello_agents.core.streaming import StreamEvent, StreamEventType

        step_counter = 0
        current_step = 0
        thinking_steps: list = []           # 汇总所有步骤，附到 agent_finish
        current_step_obj: dict = {}          # 当前步骤的数据
        step_tools_started: dict = {}        # step_no -> [tool_name, ...]
        thinking_emitted_for_step: set = set()  # 已推 thinking 的 step 编号

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

        async for event in super().arun_stream(input_text, **kwargs):
            ev_name = event.type.name  # 'STEP_START' / 'LLM_CHUNK' / ...

            if ev_name == "STEP_START":
                step_counter += 1
                current_step = event.data.get("step", step_counter)
                current_step_obj = {"__step": current_step, "thought": "", "tools": []}
                step_tools_started[current_step] = []
                yield event

            elif ev_name == "LLM_CHUNK":
                yield event
            elif ev_name == "TOOL_CALL_FINISH":
                tool_name = event.data.get("tool_name", "")
                step_no = event.data.get("step", current_step)
                raw_args = (
                    event.data.get("args")
                    if "args" in event.data
                    else event.data.get("tool_args", event.data.get("arguments"))
                )
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

                yield event

            elif ev_name == "STEP_FINISH":
                # 保存当前步骤到汇总
                # Read reasoning_content here: stream is done, last_stats is ready
                if current_step not in thinking_emitted_for_step:
                    rc = ""
                    # Try adapter.last_stats first (written after astream_invoke finishes)
                    _adapter = getattr(getattr(self, "llm", None), "_adapter", None)
                    if _adapter and hasattr(_adapter, "last_stats"):
                        _stats = _adapter.last_stats
                        rc = getattr(_stats, "reasoning_content", None) or ""
                    # Fallback: llm.last_call_stats
                    if not rc:
                        _llm = getattr(self, "llm", None)
                        _stats = getattr(_llm, "last_call_stats", None)
                        rc = getattr(_stats, "reasoning_content", None) or ""
                    if rc:
                        thinking_emitted_for_step.add(current_step)
                        current_step_obj["thought"] = rc
                        yield StreamEvent.create(
                            StreamEventType.THINKING,
                            self.name,
                            chunk=rc,
                            step=current_step,
                        )
                if current_step_obj.get("__step"):
                    thinking_steps.append(dict(current_step_obj))
                yield event

            elif ev_name == "AGENT_FINISH":
                # 把完整 thinking_steps 附加到 agent_finish 事件
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