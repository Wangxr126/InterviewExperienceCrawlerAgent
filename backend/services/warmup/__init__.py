"""
预热层：启动时预热 Ollama 本地模型
包括 LLM、Embedding、Reranker 三类模型
"""
from backend.services.warmup.model_warmup import warmup_all_models, warmup_embedding_rerank
from backend.services.warmup.llm_warmup import warmup_llm

__all__ = ["warmup_all_models", "warmup_embedding_rerank", "warmup_llm"]
