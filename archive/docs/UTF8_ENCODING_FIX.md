# Agent Terminal UTF-8 编码修复

## 问题描述
在 Windows 系统上，通过 `subprocess.Popen` 启动的子进程（agent）默认使用系统编码（通常是 GBK），导致中文输出出现乱码。

## 解决方案
在启动子进程时，通过环境变量设置 UTF-8 编码：

```python
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"  # Python I/O 使用 UTF-8
env["PYTHONUTF8"] = "1"            # Python 3.7+ UTF-8 模式

subprocess.Popen(
    cmd,
    env=env,  # 传入修改后的环境变量
    ...
)
```

## 修改的文件

### 1. `backend/services/llm_warmup.py`
**函数**: `_start_ollama_serve()`

**修改内容**:
```python
def _start_ollama_serve():
    """后台启动 ollama serve（设置OLLAMA_KEEP_ALIVE=-1保持模型常驻）"""
    try:
        env = os.environ.copy()
        env["OLLAMA_KEEP_ALIVE"] = "-1"
        
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
                env=env,  # ← 添加 env 参数
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,  # ← 添加 env 参数
            )
        ...
```

### 2. `backend/main.py`
**位置**: XHS 爬虫触发器（约第 1529 行）

**修改内容**:
```python
logger.info(f"启动 XHS worker 子进程: {' '.join(cmd)}")

# 设置 UTF-8 编码环境变量
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

subprocess.Popen(
    cmd,
    cwd=str(_PROJECT_ROOT),
    creationflags=0,
    env=env,  # ← 添加 env 参数
)
```

## 环境变量说明

### `PYTHONIOENCODING=utf-8`
- 设置 Python 标准输入/输出/错误流的编码
- 影响 `sys.stdout`, `sys.stderr`, `sys.stdin`
- 适用于所有 Python 版本

### `PYTHONUTF8=1`
- Python 3.7+ 引入的 UTF-8 模式
- 强制所有文本 I/O 使用 UTF-8
- 包括文件操作、命令行参数等
- 更全面的 UTF-8 支持

## 测试验证

修改后，子进程的中文输出应该正常显示：

```python
# 测试代码
import subprocess
import os

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

result = subprocess.run(
    ["python", "-c", "print('测试中文输出')"],
    env=env,
    capture_output=True,
    text=True
)

print(result.stdout)  # 应该正确显示：测试中文输出
```

## 注意事项

1. **仅影响子进程**: 这些环境变量只影响通过 `subprocess.Popen` 启动的子进程，不影响主进程
2. **Windows 特定**: 主要解决 Windows 系统的编码问题，Linux/macOS 默认使用 UTF-8
3. **向后兼容**: 这些环境变量不会影响已有功能，只是确保编码正确
4. **全局生效**: 如果需要所有子进程都使用 UTF-8，可以在程序启动时设置：
   ```python
   import os
   os.environ["PYTHONIOENCODING"] = "utf-8"
   os.environ["PYTHONUTF8"] = "1"
   ```

## 相关资源

- [PEP 540 - Add a new UTF-8 Mode](https://www.python.org/dev/peps/pep-0540/)
- [Python subprocess 文档](https://docs.python.org/3/library/subprocess.html)
- [PYTHONIOENCODING 环境变量](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONIOENCODING)
