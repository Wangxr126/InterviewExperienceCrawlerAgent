"""
多个 OpenAI 兼容端点按序故障转移，与 MINER_REMOTE_FALLBACK_MODELS 等配置语义一致。
供 Miner / Interviewer 等 ReAct 场景复用。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from hello_agents.core.llm import HelloAgentsLLM

logger = logging.getLogger(__name__)


def is_recoverable_remote_error(exc: BaseException) -> bool:
    """
    是否应尝试下一备用端点（额度/鉴权/限流/超时/连接类等）。
    过宽会误切换；过窄会漏掉可恢复错误。与 two_stage 中 Stage1/Stage2 策略对齐。
    """
    msg = (str(exc) or "").lower()
    keys = (
        "429",
        "403",
        "401",
        "402",
        "quota",
        "rate",
        "limit",
        "ratelimit",
        "allocationquota",
        "freetier",
        "free tier",
        "exhausted",
        "insufficient",
        "invalid_api_key",
        "incorrect api key",
        "timed out",
        "timeout",
        "connection refused",
        "connection reset",
        "remote end closed",
        "eof occurred",
        "ssl",
        "bad gateway",
        "502",
        "503",
        "504",
    )
    return any(k in msg for k in keys)


class ChainedHelloAgentsLLM(HelloAgentsLLM):
    """
    包装多条已构造的 HelloAgentsLLM，invoke / 工具调用 / 流式 等在失败时按序切换。
    首端点参数用于满足父类初始化（与 chain[0] 一致）。
    """

    def __init__(self, llms: List[HelloAgentsLLM], *, chain_name: str = "chain") -> None:
        if not llms:
            raise ValueError("ChainedHelloAgentsLLM: 至少 1 个 HelloAgentsLLM")
        self._chain_llms = llms
        self._chain_name = chain_name
        first = llms[0]
        _kw = getattr(first, "kwargs", None)
        _extra = _kw if isinstance(_kw, dict) else {}
        super().__init__(
            model=first.model,
            api_key=first.api_key,
            base_url=first.base_url,
            temperature=first.temperature,
            max_tokens=first.max_tokens,
            timeout=first.timeout,
            **_extra,
        )

    def _run_chained(self, fn_name: str, runner, n_llms: int) -> Any:
        last_err: Optional[BaseException] = None
        for i in range(n_llms):
            llm = self._chain_llms[i]
            try:
                return runner(llm)
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n_llms:
                    logger.warning(
                        "[%s] %s 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        fn_name,
                        i + 1,
                        n_llms,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err
        return None

    def invoke(self, messages, **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            return self._chain_llms[0].invoke(messages, **kwargs)
        return self._run_chained("invoke", lambda m: m.invoke(messages, **kwargs), n)

    def invoke_with_tools(self, messages, tools, tool_choice="auto", **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            return self._chain_llms[0].invoke_with_tools(messages, tools, tool_choice, **kwargs)
        return self._run_chained(
            "invoke_with_tools",
            lambda m: m.invoke_with_tools(messages, tools, tool_choice, **kwargs),
            n,
        )

    def stream_invoke(self, messages, **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            yield from self._chain_llms[0].stream_invoke(messages, **kwargs)
            return
        last_err: Optional[BaseException] = None
        for i in range(n):
            llm = self._chain_llms[i]
            try:
                yield from llm.stream_invoke(messages, **kwargs)
                return
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n:
                    logger.warning(
                        "[%s] stream_invoke 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        i + 1,
                        n,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err

    def think(self, messages, temperature=None):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            yield from self._chain_llms[0].think(messages, temperature=temperature)
            return
        last_err: Optional[BaseException] = None
        for i in range(n):
            llm = self._chain_llms[i]
            try:
                yield from llm.think(messages, temperature=temperature)
                return
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n:
                    logger.warning(
                        "[%s] think 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        i + 1,
                        n,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err

    async def ainvoke(self, messages, **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            return await self._chain_llms[0].ainvoke(messages, **kwargs)
        last_err: Optional[BaseException] = None
        for i in range(n):
            llm = self._chain_llms[i]
            try:
                return await llm.ainvoke(messages, **kwargs)
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n:
                    logger.warning(
                        "[%s] ainvoke 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        i + 1,
                        n,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err

    async def astream_invoke(self, messages, **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            async for chunk in self._chain_llms[0].astream_invoke(messages, **kwargs):
                yield chunk
            return
        last_err: Optional[BaseException] = None
        for i in range(n):
            llm = self._chain_llms[i]
            try:
                async for chunk in llm.astream_invoke(messages, **kwargs):
                    yield chunk
                return
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n:
                    logger.warning(
                        "[%s] astream_invoke 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        i + 1,
                        n,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err

    async def ainvoke_with_tools(self, messages, tools, tool_choice="auto", **kwargs):  # type: ignore[override]
        n = len(self._chain_llms)
        if n == 1:
            return await self._chain_llms[0].ainvoke_with_tools(messages, tools, tool_choice, **kwargs)
        last_err: Optional[BaseException] = None
        for i in range(n):
            llm = self._chain_llms[i]
            try:
                return await llm.ainvoke_with_tools(messages, tools, tool_choice, **kwargs)
            except Exception as e:
                last_err = e
                if is_recoverable_remote_error(e) and i + 1 < n:
                    logger.warning(
                        "[%s] ainvoke_with_tools 端点 %d/%d 失败，切换备用: %s",
                        self._chain_name,
                        i + 1,
                        n,
                        e,
                    )
                    continue
                raise
        if last_err:
            raise last_err


def build_miner_hello_llm_list(settings) -> List[HelloAgentsLLM]:
    """remote Miner：按 miner_remote_models 构造 HelloAgentsLLM 列表。"""
    from hello_agents.core.llm import HelloAgentsLLM

    eps = settings.miner_remote_models or []
    out: List[HelloAgentsLLM] = []
    for ep in eps:
        m = (ep.get("model") or "").strip()
        b = (ep.get("base_url") or "").strip().rstrip("/")
        if not m or not b:
            continue
        out.append(
            HelloAgentsLLM(
                model=m,
                api_key=(ep.get("api_key") or "").strip() or "sk-dummy",
                base_url=b,
                temperature=settings.miner_temperature,
                max_tokens=settings.miner_max_tokens,
                timeout=int(ep.get("timeout") or settings.miner_timeout or 180),
            )
        )
    return out


def build_interviewer_hello_llm_list(settings) -> List[HelloAgentsLLM]:
    """Interviewer：按 interviewer_remote_models 构造列表（local / remote 均已展开为链）。"""
    from hello_agents.core.llm import HelloAgentsLLM

    eps = settings.interviewer_remote_models or []
    out: List[HelloAgentsLLM] = []
    for ep in eps:
        m = (ep.get("model") or "").strip()
        b = (ep.get("base_url") or "").strip().rstrip("/")
        if not m or not b:
            continue
        out.append(
            HelloAgentsLLM(
                model=m,
                api_key=(ep.get("api_key") or "").strip() or "sk-dummy",
                base_url=b,
                temperature=settings.interviewer_temperature,
                max_tokens=settings.interviewer_max_tokens,
                timeout=int(ep.get("timeout") or settings.interviewer_timeout or settings.llm_timeout or 180),
            )
        )
    return out
