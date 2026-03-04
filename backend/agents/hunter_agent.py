"""
ResourceHunterAgent —— 已被 HunterPipeline 替代（v3.0）

原来的 ReAct Agent 控制 ETL 管道的问题：
  • 管道步骤（爬取→清洗→校验→OCR→元信息）是固定顺序，不需要 LLM 编排
  • ContentValidator 的 OCR 决策是规则判断（if/else），不需要 LLM 推理
  • 用 LLM 做这些事既不可靠（可能跳步），又浪费 token

替代方案：
  backend/services/hunter_pipeline.py 中的 run_hunter_pipeline()
  ── 纯 Python 函数，按固定顺序调用各工具，OCR 决策由代码 if/else 控制

本文件保留是为了兼容旧 import，未来可直接删除。
"""

# 为了不破坏旧代码中可能存在的 import，保留一个兼容符号
ResourceHunterAgent = None
