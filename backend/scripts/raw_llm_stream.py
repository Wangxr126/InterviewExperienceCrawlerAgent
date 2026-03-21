"""兼容入口：转发至 llm_observability/scripts/raw_llm_stream.py"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _ROOT / "llm_observability" / "scripts" / "raw_llm_stream.py"
if not _TARGET.is_file():
    sys.exit(f"缺失 {_TARGET}")
runpy.run_path(str(_TARGET), run_name="__main__")
