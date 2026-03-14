"""
修复 hello_agents 工具参数 JSON 解析失败问题

问题：LLM 调用 Finish 等工具时，若 answer 参数包含大量 JSON（如 100+ 道题），
模型可能输出带未转义换行的 JSON，导致 json.loads 报 "Unterminated string"。

解决：在解析失败时，尝试将字符串值内的字面换行替换为 \\n 后再解析。
"""
import json as _stdlib_json
import logging
import types

logger = logging.getLogger(__name__)


# JSON 字符串内不允许的未转义控制字符 → 转义形式
_CONTROL_ESCAPES = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\f": "\\f",
    "\b": "\\b",
}


def _repair_tool_arguments_json(s: str) -> str:
    """
    尝试修复工具参数 JSON 中的常见问题（如字符串值内的未转义换行、制表符等）。
    仅当标准解析失败且错误为 Unterminated string / Invalid control character 时使用。
    """
    if not isinstance(s, str) or len(s) < 2:
        return s
    result = []
    i = 0
    in_string = False
    escape = False
    while i < len(s):
        c = s[i]
        if in_string:
            if escape:
                result.append(c)
                escape = False
            elif c == "\\":
                result.append(c)
                escape = True
            elif c == '"':
                in_string = False
                result.append(c)
            elif c in _CONTROL_ESCAPES:
                result.append(_CONTROL_ESCAPES[c])
            elif ord(c) < 32:
                # 其他 JSON 不允许的控制字符
                result.append(f"\\u{ord(c):04x}")
            else:
                result.append(c)
        else:
            result.append(c)
            if c == '"':
                in_string = True
        i += 1
    return "".join(result)


def _patched_json_loads(s, *args, **kwargs):
    """带修复的 json.loads，仅在解析失败时尝试修复。"""
    try:
        return _stdlib_json.loads(s, *args, **kwargs)
    except _stdlib_json.JSONDecodeError as e:
        err_str = str(e)
        if any(x in err_str for x in ("Unterminated string", "Expecting value", "Invalid control character")):
            try:
                repaired = _repair_tool_arguments_json(s)
                result = _stdlib_json.loads(repaired, *args, **kwargs)
                logger.debug("工具参数 JSON 解析失败后修复成功: %s", err_str[:80])
                return result
            except _stdlib_json.JSONDecodeError:
                pass
        raise


def _create_patched_json_module():
    """创建带 patched loads 的 json 模块副本，不修改全局 json。"""
    patched = types.ModuleType("json")
    for attr in dir(_stdlib_json):
        if not attr.startswith("_"):
            setattr(patched, attr, getattr(_stdlib_json, attr))
    patched.loads = _patched_json_loads
    return patched


def apply_patch():
    """
    对 hello_agents 的 agent 模块应用补丁：将其命名空间内的 json 替换为
    带修复逻辑的副本，仅影响这些模块，不影响全局 json。
    """
    try:
        patched_json = _create_patched_json_module()
        for mod_name in (
            "hello_agents.agents.react_agent",
            "hello_agents.agents.simple_agent",
            "hello_agents.agents.reflection_agent",
            "hello_agents.agents.plan_solve_agent",
        ):
            try:
                import importlib
                mod = importlib.import_module(mod_name)
                mod.json = patched_json
            except ImportError:
                pass
        logger.info("已应用工具参数 JSON 解析修复补丁")
    except Exception as e:
        logger.warning("应用工具参数 JSON 解析补丁失败: %s", e)
