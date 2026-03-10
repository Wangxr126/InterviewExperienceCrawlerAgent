"""
test_react_agents.py - ReAct Agent 测试套件
运行方式: python test_react_agents.py
"""
import sys, os, json, logging
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
BLUE = "\033[94m"; RESET = "\033[0m"

def ok(m):     print(f"{GREEN}  PASS {m}{RESET}")
def fail(m):   print(f"{RED}  FAIL {m}{RESET}")
def info(m):   print(f"{BLUE}  INFO {m}{RESET}")
def warn(m):   print(f"{YELLOW}  WARN {m}{RESET}")
def section(t): print(f"\n{'='*55}\nTEST: {t}\n{'='*55}")

PASSED, FAILED = [], []


def _finish_resp(answer, cid="c001"):
    """构造 LLM 返回 Finish 工具调用的 Mock 响应"""
    tc = MagicMock()
    tc.function.name = "Finish"
    tc.function.arguments = json.dumps({"answer": answer})
    tc.id = cid
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message.content = None
    r.choices[0].message.tool_calls = [tc]
    r.usage = MagicMock(total_tokens=100)
    return r


def _tool_resp(name, args, cid):
    """构造 LLM 返回任意工具调用的 Mock 响应"""
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    tc.id = cid
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message.content = None
    r.choices[0].message.tool_calls = [tc]
    r.usage = MagicMock(total_tokens=60)
    return r
