"""
LLM 预热：杀死旧 Ollama 进程 → 启动 ollama serve → 预加载 .env 中配置的模型。
Ollama 冷启动约 30s～数分钟，预热可避免首次提取超时。
"""
import json
import logging
import os
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


def _get_warmup_targets():
    """
    从 config 读取各 agent 实际使用的 (base_url, model) 组合，去重。
    每个 agent 有独立的 mode/base_url/model，只预热本地（localhost/127.0.0.1）的模型。
    """
    try:
        from backend.config.config import settings
        candidates = [
            # Miner（题目提取器）
            (settings.miner_base_url, settings.miner_model),
            # Architect / Knowledge Manager
            (settings.knowledge_manager_base_url, settings.knowledge_manager_model),
            # Interviewer（面试官）
            (settings.interviewer_base_url, settings.interviewer_model),
        ]
        seen = set()
        out = []
        for base_url, model in candidates:
            if not base_url or not model:
                continue
            # 只预热本地 Ollama，跳过云端
            if "localhost" not in base_url and "127.0.0.1" not in base_url:
                continue
            key = (base_url.strip(), model.strip())
            if key not in seen:
                seen.add(key)
                out.append(key)
        return out
    except Exception:
        return []


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
    """后台启动 ollama serve（设置OLLAMA_KEEP_ALIVE=-1保持模型常驻）"""
    try:
        env = os.environ.copy()
        env["OLLAMA_KEEP_ALIVE"] = "-1"  # 模型常驻显存，不自动卸载
        
        # 设置 UTF-8 编码（Windows）
        if sys.platform == "win32":
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
        
        if sys.platform == "win32":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        logger.info("[LLM 预热] 已启动 ollama serve（OLLAMA_KEEP_ALIVE=-1，模型常驻显存）")
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
        warmup_targets = _get_warmup_targets()
        if not warmup_targets:
            logger.warning("[LLM 预热] 未找到需要预热的本地模型，跳过")
            return False

        model_names = [m for _, m in warmup_targets]
        # 本地 Ollama：杀进程 → 启动 serve → 按各 agent 实际配置预热
        logger.info("[LLM 预热] 本地 Ollama：终止旧进程 → 启动 serve → 预加载模型 {}", model_names)
        _kill_ollama()
        try:
            _start_ollama_serve()
        except Exception as e:
            logger.error("[LLM 预热] ❌ 启动失败: {}", e)
            return False

        # 用第一个本地 base_url 等待 Ollama 就绪
        first_base = warmup_targets[0][0]
        wait_sec = min(60, use_timeout // 2)
        if not _wait_ollama_ready(first_base, wait_sec):
            logger.error("[LLM 预热] ❌ Ollama 服务 {}s 内未就绪", wait_sec)
            return False
        logger.info("[LLM 预热] Ollama 服务已就绪")

        ok_count = 0
        for target_base, model in warmup_targets:
            t0 = time.time()
            logger.info("[LLM 预热] 预加载 {}...", model)
            if _warmup_one_model(target_base, model, use_timeout // 2):
                elapsed = time.time() - t0
                logger.info("[LLM 预热] ✅ {} 已加载（{:.1f}s）", model, elapsed)
                ok_count += 1
            else:
                logger.warning("[LLM 预热] ⚠️ {} 加载失败", model)
        return ok_count > 0
    else:
        # 云端 LLM：仅发预热请求（只预热全局 base_url 对应的模型）
        model = settings.llm_model_id or "gpt-3.5-turbo"
        url = f"{base.rstrip('/')}/chat/completions"
        logger.info("[LLM 预热] 云端预热 model={}", model)
        return _warmup_one_model(base, model, use_timeout)
