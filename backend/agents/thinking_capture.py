"""
思考步骤捕获器 (ThinkingCapture)

hello_agents 在每一步推理时会通过 print() 输出类似：
    --- 第 N 步 ---
    🤔 思考: ...
    🎬 行动: tool_name[...]
    👀 观察: ...

本模块在全局替换 sys.stdout 为一个线程感知的代理：
  - 处于捕获状态的线程：print 输出写入线程本地缓冲区
  - 其余线程：透明转发到原始 stdout

使用方式（在 orchestrator.py 中）：
    from backend.agents.thinking_capture import ThinkingCapture
    with ThinkingCapture() as tc:
        response = agent.run(input_text)
    steps = tc.get_steps()   # List[Dict]
"""

from __future__ import annotations

import io
import re
import sys
import threading
from typing import Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# 线程本地缓冲区
# ─────────────────────────────────────────────────────────────────────────────
_tl = threading.local()
_original_stdout: Optional[object] = None


class _ThreadLocalStdout:
    """全局 stdout 替代品：写到当前线程的 capture_buf，若无则写原始 stdout。"""

    def write(self, text: str) -> int:
        buf: Optional[io.StringIO] = getattr(_tl, "capture_buf", None)
        if buf is not None:
            return buf.write(text)
        # Windows 兼容：处理 emoji 等特殊字符
        try:
            return _original_stdout.write(text)  # type: ignore[union-attr]
        except UnicodeEncodeError:
            # 替换无法编码的字符
            safe_text = text.encode('utf-8', errors='replace').decode('utf-8')
            return _original_stdout.write(safe_text)  # type: ignore[union-attr]

    def flush(self) -> None:
        _original_stdout.flush()  # type: ignore[union-attr]

    def fileno(self) -> int:
        return _original_stdout.fileno()  # type: ignore[union-attr]

    def isatty(self) -> bool:
        return False

    # 确保 uvicorn / logging 不会因缺少属性而报错
    @property
    def encoding(self) -> str:
        return getattr(_original_stdout, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        return getattr(_original_stdout, "errors", "replace")


def install() -> None:
    """
    在应用启动时调用一次（main.py lifespan 或顶层），
    将 sys.stdout 替换为线程感知代理。
    幂等：多次调用无副作用。
    """
    global _original_stdout
    if _original_stdout is not None:
        return
    _original_stdout = sys.stdout
    sys.stdout = _ThreadLocalStdout()


# ─────────────────────────────────────────────────────────────────────────────
# 上下文管理器
# ─────────────────────────────────────────────────────────────────────────────

class ThinkingCapture:
    """
    在 with 块内捕获当前线程的 print 输出。

    注意：必须在 install() 之后才能生效；
    agent.run() 须在同一线程内执行（run_in_executor 的 executor 线程）。
    """

    def __enter__(self) -> "ThinkingCapture":
        _tl.capture_buf = io.StringIO()
        return self

    def __exit__(self, *_) -> None:
        # 不在此处清除缓冲，让 get_steps() 还能访问
        pass

    def get_steps(self) -> List[Dict]:
        """返回结构化步骤列表，并清理线程本地缓冲区。"""
        buf: Optional[io.StringIO] = getattr(_tl, "capture_buf", None)
        _tl.capture_buf = None
        if buf is None:
            return []
        return _parse_steps(buf.getvalue())


# ─────────────────────────────────────────────────────────────────────────────
# 解析逻辑
# ─────────────────────────────────────────────────────────────────────────────

_STEP_RE = re.compile(r"^-+\s*第\s*\d+\s*步\s*-+$")


def _parse_steps(text: str) -> List[Dict]:
    """
    将 hello_agents 的 print 输出解析为结构化步骤列表。

    每个步骤字典包含（存在则含）：
      thought      : 思考内容
      action       : 工具调用字符串（如 get_recommended_question[mode=auto]）
      observation  : 工具返回内容
      warning      : 警告信息
      info         : 超时/终止等提示
    """
    steps: List[Dict] = []
    current: Dict = {}

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        if _STEP_RE.match(s):
            if current:
                steps.append(current)
            current = {}
        elif s.startswith("🤔 思考:"):
            current["thought"] = s[len("🤔 思考:"):].strip()
        elif s.startswith("🎬 行动:"):
            current["action"] = s[len("🎬 行动:"):].strip()
        elif s.startswith("👀 观察:"):
            current["observation"] = s[len("👀 观察:"):].strip()
        elif s.startswith("⚠️"):
            current.setdefault("warning", s)
        elif s.startswith("⏰"):
            current.setdefault("info", s)

    if current:
        steps.append(current)

    return steps
