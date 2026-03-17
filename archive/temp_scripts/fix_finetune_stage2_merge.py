#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复已导入的微调样本：对 stage2_output 不完整的记录，用 stage1_output 补齐缺失字段。
用法: python scripts/fix_finetune_stage2_merge.py
"""
import sys
from pathlib import Path

# 确保项目根目录在 path 中
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.services.finetune.finetune_service import fix_merged_stage2_samples

if __name__ == "__main__":
    res = fix_merged_stage2_samples(source_filter="miner_two_stage")
    print(f"修复完成: fixed={res['fixed']} skipped={res['skipped']} failed={res['failed']}")
