"""
LLM 预热：杀死旧 Ollama 进程 → 启动 ollama serve → 预加载 .env 中配置的模型。
Ollama 冷启动约 30s～数分钟，预热可避免首次提取超时。
"""
import json
import logging
import subprocess
import sys
import time
import urllib.request
import urllib.error

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)

# 预热超时：2 分钟（Ollama 冷启动可能较久）
WARMUP_TIMEOUT = 120


def _get_warmup_models():
    """从 config 读取需预热的模型（全局 + Architect + Interviewer，去重）"""
    try:
        from backend.config.config import settings
        models = [
            settings.llm_model_id,
            settings.architect_model,
            settings.interviewer_model,
        ]
        seen = set()
        out = []
        for m in models:
            if m and m.strip() and m not in seen:
                seen.add(m)
                out.append(m.strip())
        return out if out else [settings.llm_model_id or "gemma3:4b"]
    except Exception:
        return ["gemma3:4b"]


def _kill_ollama():
    """杀死所有 Ollama 进程"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "ollama.exe"],
                capture_output=True,
                timeout=10,
            )
        else:
            subprocess.run(["pkill", "-9", "ollama"], capture_output=True, timeout=10)
        time.sleep(2)  # 等待进程完全退出
        logger.info("[LLM 预热] 已终止 Ollama 进程")
    except Exception as e:
        logger.warning("[LLM 预热] 终止 Ollama: {}", e)


def _start_ollama_serve():
    """后台启动 ollama serve"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        logger.info("[LLM 预热] 已启动 ollama serve")
    except Exception as e:
        logger.error("[LLM 预热] 启动 ollama serve 失败: {}", e)
        raise


def _wait_ollama_ready(base_url: str, timeout: int) -> bool:
    """等待 Ollama 服务就绪"""
    root = base_url.rstrip("/").replace("/v1", "").rstrip("/") or base_url
    url = root + "/api/tags"  # 轻量接口
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as _:
                return True
        except Exception:
            time.sleep(1)
    return False


def _warmup_one_model(base_url: str, model: str, timeout: int) -> bool:
    """对单个模型发送预热请求"""
    base = base_url.rstrip("/")
    url = base if "/chat/completions" in base else f"{base}/chat/completions"
    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")
    payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 2}
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
    except Exception:
        return False


def warmup_llm(timeout: int = WARMUP_TIMEOUT) -> bool:
    """
    同步预热 LLM：杀死 Ollama → 启动 ollama serve → 预加载 .env 中配置的模型。
    仅当 base_url 为 localhost/127.0.0.1 时执行完整流程；云端 LLM 仅发预热请求。
    """
    try:
        from backend.config.config import settings
    except ImportError:
        logger.debug("LLM 预热跳过（缺少依赖）")
        return False

    base = (settings.llm_base_url or "").strip()
    if not base:
        logger.info("[LLM 预热] 跳过（未配置 base_url）")
        return False

    use_timeout = min(timeout, settings.llm_timeout or WARMUP_TIMEOUT)
    is_local = "localhost" in base or "127.0.0.1" in base

    if is_local:
        warmup_models = _get_warmup_models()
        # 本地 Ollama：杀进程 → 启动 serve → 预加载 .env 中配置的模型
        logger.info("[LLM 预热] 本地 Ollama：终止旧进程 → 启动 serve → 预加载模型 {}", warmup_models)
        _kill_ollama()
        try:
            _start_ollama_serve()
        except Exception as e:
            logger.error("[LLM 预热] ❌ 启动失败: {}", e)
            return False

        wait_sec = min(60, use_timeout // 2)
        if not _wait_ollama_ready(base, wait_sec):
            logger.error("[LLM 预热] ❌ Ollama 服务 {}s 内未就绪", wait_sec)
            return False
        logger.info("[LLM 预热] Ollama 服务已就绪")

        ok_count = 0
        for model in warmup_models:
            t0 = time.time()
            logger.info("[LLM 预热] 预加载 {}...", model)
            if _warmup_one_model(base, model, use_timeout // 2):
                elapsed = time.time() - t0
                logger.info("[LLM 预热] ✅ {} 已加载（{:.1f}s）", model, elapsed)
                ok_count += 1
            else:
                logger.warning("[LLM 预热] ⚠️ {} 加载失败", model)
        return ok_count > 0
    else:
        # 云端 LLM：仅发预热请求
        model = settings.llm_model_id or "gpt-3.5-turbo"
        url = f"{base.rstrip('/')}/chat/completions"
        logger.info("[LLM 预热] 云端预热 model={}", model)
        return _warmup_one_model(base, model, use_timeout)
