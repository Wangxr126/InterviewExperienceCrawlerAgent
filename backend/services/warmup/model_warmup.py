"""
模型预热：LLM + Embedding + Reranker
避免首次请求冷启动导致超时
"""
import json
import logging
import time
import urllib.request
import urllib.error
from typing import List, Tuple, Optional

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

# 预热超时
WARMUP_TIMEOUT = 120


def _warmup_llm_model(base_url: str, model: str, timeout: int) -> bool:
    """预热单个 LLM 模型"""
    url = base_url.rstrip("/")
    if "/chat/completions" not in url:
        url = f"{url}/chat/completions"
    
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 2
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer ollama"
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[预热] LLM {model} 预热失败: {e}")
        return False


def _warmup_embedding_model(base_url: str, model: str, timeout: int) -> bool:
    """预热 Embedding 模型"""
    # Ollama Embedding API: POST /api/embeddings
    url = base_url.rstrip("/").replace("/v1", "")
    if "/api/embeddings" not in url:
        url = f"{url}/api/embeddings"
    
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    
    payload = {
        "model": model,
        "prompt": "hello"
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[预热] Embedding {model} 预热失败: {e}")
        return False


def _warmup_ocr_model(base_url: str, model: str, timeout: int) -> bool:
    """预热 OCR 视觉模型（ollama_vl 使用的 qwen3-vl 等）"""
    url = base_url.rstrip("/")
    if "/chat/completions" not in url:
        url = f"{url}/chat/completions" if "/v1" in url else f"{url}/v1/chat/completions"
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    # 1x1 像素 PNG，用于触发视觉模型加载
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png_b64}"}},
                {"type": "text", "text": "1"}
            ]
        }],
        "max_tokens": 2,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[预热] OCR {model} 预热失败: {e}")
        return False


def _warmup_reranker_model(base_url: str, model: str, timeout: int) -> bool:
    """预热 Reranker 模型"""
    # Ollama Reranker API: POST /api/rerank（与 rerank_service 一致）
    url = base_url.rstrip("/").replace("/v1", "")
    if "/api/rerank" not in url:
        url = f"{url}/api/rerank"
    
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    
    payload = {
        "model": model,
        "query": "test",
        "documents": ["test document"],
        "top_n": 1,
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[预热] Reranker {model} 预热失败: {e}")
        return False


def warmup_embedding_rerank(timeout: int = WARMUP_TIMEOUT) -> dict:
    """
    仅预热 Embedding + Reranker（不预热 LLM）。
    供 main.py 在 warmup_llm 之后调用，避免 LLM 重复预热。
    """
    try:
        from backend.config.config import settings
    except ImportError:
        logger.warning("[预热] 无法导入 settings，跳过 Embedding/Reranker 预热")
        return {}

    start_time = time.time()
    results = {"embedding": {"success": 0, "failed": 0}, "reranker": {"success": 0, "failed": 0}, "ocr": {"success": 0, "failed": 0}}

    # OCR 视觉模型（ollama_vl 时预热，避免首次 OCR 冷启动超时/失败）
    if settings.ocr_method == "ollama_vl":
        ocr_model = settings.ocr_model or "qwen3-vl:2b"
        ocr_url = "http://localhost:11434/v1"
        t0 = time.time()
        logger.info("[预热] 预热 OCR 视觉模型: %s...", ocr_model)
        if _warmup_ocr_model(ocr_url, ocr_model, timeout // 2):
            logger.info("[预热] ✅ OCR %s 已加载（%.1fs）", ocr_model, time.time() - t0)
            results["ocr"] = {"success": 1, "failed": 0}
        else:
            logger.warning("[预热] ⚠️ OCR %s 加载失败", ocr_model)
            results["ocr"] = {"success": 0, "failed": 1}

    # Embedding
    if settings.embed_model_type == "ollama" and settings.embed_model_name:
        embed_url = settings.embed_ollama_url or "http://localhost:11434"
        if "localhost" in embed_url or "127.0.0.1" in embed_url:
            t0 = time.time()
            logger.info("[预热] 预热 Embedding: %s...", settings.embed_model_name)
            if _warmup_embedding_model(embed_url, settings.embed_model_name, timeout // 2):
                logger.info("[预热] ✅ Embedding %s 已加载（%.1fs）", settings.embed_model_name, time.time() - t0)
                results["embedding"]["success"] = 1
            else:
                logger.warning("[预热] ⚠️ Embedding %s 加载失败", settings.embed_model_name)
                results["embedding"]["failed"] = 1

    # Reranker
    if settings.rerank_enabled and settings.rerank_model:
        rerank_url = settings.rerank_ollama_url or "http://localhost:11434"
        if "localhost" in rerank_url or "127.0.0.1" in rerank_url:
            t0 = time.time()
            logger.info("[预热] 预热 Reranker: %s...", settings.rerank_model)
            if _warmup_reranker_model(rerank_url, settings.rerank_model, timeout // 2):
                logger.info("[预热] ✅ Reranker %s 已加载（%.1fs）", settings.rerank_model, time.time() - t0)
                results["reranker"]["success"] = 1
            else:
                logger.warning("[预热] ⚠️ Reranker %s 加载失败", settings.rerank_model)
                results["reranker"]["failed"] = 1

    elapsed = time.time() - start_time
    if results["embedding"]["success"] or results["reranker"]["success"] or results.get("ocr", {}).get("success"):
        logger.info("[预热] Embedding/Reranker/OCR 预热完成，耗时 %.1fs", elapsed)
    return results


def warmup_all_models(timeout: int = WARMUP_TIMEOUT) -> dict:
    """
    预热所有模型：LLM + Embedding + Reranker
    
    Returns:
        dict: 预热结果统计
            {
                "llm": {"success": 2, "failed": 0, "models": ["qwen3:4b", ...]},
                "embedding": {"success": 1, "failed": 0, "models": ["qwen3-embedding:0.6b"]},
                "reranker": {"success": 1, "failed": 0, "models": ["Qwen3-Reranker-8B:Q4_K_M"]},
                "total_time": 12.5
            }
    """
    try:
        from backend.config.config import settings
    except ImportError:
        logger.warning("[预热] 无法导入 settings，跳过预热")
        return {}
    
    start_time = time.time()
    results = {
        "llm": {"success": 0, "failed": 0, "models": []},
        "embedding": {"success": 0, "failed": 0, "models": []},
        "reranker": {"success": 0, "failed": 0, "models": []},
        "ocr": {"success": 0, "failed": 0, "models": []},
        "total_time": 0
    }
    
    # ========== 0. 预热 OCR 视觉模型（ollama_vl）==========
    if settings.ocr_method == "ollama_vl":
        ocr_model = settings.ocr_model or "qwen3-vl:2b"
        ocr_url = "http://localhost:11434/v1"
        t0 = time.time()
        logger.info(f"[预热] 预热 OCR 视觉模型: {ocr_model}...")
        if _warmup_ocr_model(ocr_url, ocr_model, timeout // 2):
            elapsed = time.time() - t0
            logger.info(f"[预热] ✅ OCR {ocr_model} 预热成功 ({elapsed:.1f}s)")
            results["ocr"]["success"] += 1
            results["ocr"]["models"].append(ocr_model)
        else:
            logger.warning(f"[预热] ⚠️ OCR {ocr_model} 预热失败")
            results["ocr"]["failed"] += 1
    
    # ========== 1. 预热 LLM 模型 ==========
    logger.info("[预热] 开始预热 LLM 模型...")
    
    llm_targets = []
    
    # Miner Agent
    if settings.miner_base_url and settings.miner_model:
        if "localhost" in settings.miner_base_url or "127.0.0.1" in settings.miner_base_url:
            llm_targets.append((settings.miner_base_url, settings.miner_model, "Miner"))
    
    # Knowledge Manager Agent
    if settings.knowledge_manager_base_url and settings.knowledge_manager_model:
        if "localhost" in settings.knowledge_manager_base_url or "127.0.0.1" in settings.knowledge_manager_base_url:
            llm_targets.append((settings.knowledge_manager_base_url, settings.knowledge_manager_model, "KnowledgeManager"))
    
    # Interviewer Agent
    if settings.interviewer_base_url and settings.interviewer_model:
        if "localhost" in settings.interviewer_base_url or "127.0.0.1" in settings.interviewer_base_url:
            llm_targets.append((settings.interviewer_base_url, settings.interviewer_model, "Interviewer"))
    
    # 去重
    seen_llm = set()
    for base_url, model, agent_name in llm_targets:
        key = (base_url, model)
        if key in seen_llm:
            continue
        seen_llm.add(key)
        
        t0 = time.time()
        logger.info(f"[预热] 预热 LLM: {model} ({agent_name})...")
        
        if _warmup_llm_model(base_url, model, timeout // 2):
            elapsed = time.time() - t0
            logger.info(f"[预热] ✅ LLM {model} 预热成功 ({elapsed:.1f}s)")
            results["llm"]["success"] += 1
            results["llm"]["models"].append(model)
        else:
            logger.warning(f"[预热] ⚠️ LLM {model} 预热失败")
            results["llm"]["failed"] += 1
    
    # ========== 2. 预热 Embedding 模型 ==========
    logger.info("[预热] 开始预热 Embedding 模型...")
    
    if settings.embed_model_type == "ollama" and settings.embed_model_name:
        embed_url = settings.embed_ollama_url or "http://localhost:11434"
        
        if "localhost" in embed_url or "127.0.0.1" in embed_url:
            t0 = time.time()
            logger.info(f"[预热] 预热 Embedding: {settings.embed_model_name}...")
            
            if _warmup_embedding_model(embed_url, settings.embed_model_name, timeout // 2):
                elapsed = time.time() - t0
                logger.info(f"[预热] ✅ Embedding {settings.embed_model_name} 预热成功 ({elapsed:.1f}s)")
                results["embedding"]["success"] += 1
                results["embedding"]["models"].append(settings.embed_model_name)
            else:
                logger.warning(f"[预热] ⚠️ Embedding {settings.embed_model_name} 预热失败")
                results["embedding"]["failed"] += 1
    
    # ========== 3. 预热 Reranker 模型 ==========
    logger.info("[预热] 开始预热 Reranker 模型...")
    
    if settings.rerank_enabled and settings.rerank_model:
        rerank_url = settings.rerank_ollama_url or "http://localhost:11434"
        
        if "localhost" in rerank_url or "127.0.0.1" in rerank_url:
            t0 = time.time()
            logger.info(f"[预热] 预热 Reranker: {settings.rerank_model}...")
            
            if _warmup_reranker_model(rerank_url, settings.rerank_model, timeout // 2):
                elapsed = time.time() - t0
                logger.info(f"[预热] ✅ Reranker {settings.rerank_model} 预热成功 ({elapsed:.1f}s)")
                results["reranker"]["success"] += 1
                results["reranker"]["models"].append(settings.rerank_model)
            else:
                logger.warning(f"[预热] ⚠️ Reranker {settings.rerank_model} 预热失败")
                results["reranker"]["failed"] += 1
    
    # ========== 统计 ==========
    results["total_time"] = time.time() - start_time
    
    total_success = results["llm"]["success"] + results["embedding"]["success"] + results["reranker"]["success"] + results["ocr"]["success"]
    total_failed = results["llm"]["failed"] + results["embedding"]["failed"] + results["reranker"]["failed"] + results["ocr"]["failed"]
    
    logger.info(
        f"[预热] 完成！成功 {total_success} 个，失败 {total_failed} 个，"
        f"耗时 {results['total_time']:.1f}s"
    )
    
    return results
