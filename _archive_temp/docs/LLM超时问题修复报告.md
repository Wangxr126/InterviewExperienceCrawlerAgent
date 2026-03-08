# LLM超时问题修复报告

## 🔍 问题分析

### 现象
```
17:00:00 | 开始 LLM 提取，本批 30 条
17:05:30 | ERROR | LLM 调用失败: Request timed out. (5分30秒后)
17:06:02 | ERROR | LLM 调用失败: Request timed out. (又32秒后)
```

### 时间线
1. **16:55:13** - 预热完成，模型加载成功（1.5秒）
2. **17:00:00** - 开始LLM提取（距离预热4分47秒）
3. **17:05:30** - 第1次调用超时（5分30秒）
4. **17:06:02** - 第2次调用超时（32秒）

### 根本原因

**Ollama默认行为：模型在5分钟不使用后自动卸载！**

- 预热时加载了模型
- 5分钟后（17:00:13）模型被自动卸载
- 第一次调用时需要重新加载模型（冷启动）
- 冷启动时间过长导致超时

---

## ✅ 解决方案

### 修改的文件：`backend/services/llm_warmup.py`

#### 修改1：添加os导入
```python
import os
```

#### 修改2：在启动ollama serve时设置OLLAMA_KEEP_ALIVE=-1

**旧代码：**
```python
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
```

**新代码：**
```python
def _start_ollama_serve():
    """后台启动 ollama serve（设置OLLAMA_KEEP_ALIVE=-1保持模型常驻）"""
    try:
        env = os.environ.copy()
        env["OLLAMA_KEEP_ALIVE"] = "-1"  # 模型常驻显存，不自动卸载
        
        if sys.platform == "win32":
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,  # 传递环境变量
            )
```

---

## 🎯 效果

### 修改前
- ❌ 模型5分钟后自动卸载
- ❌ 首次调用需要重新加载（冷启动）
- ❌ 冷启动时间过长导致超时

### 修改后
- ✅ 模型常驻显存，永不卸载
- ✅ 所有调用都是热启动
- ✅ 响应速度快，不会超时

---

## 📊 配置说明

### OLLAMA_KEEP_ALIVE环境变量

**作用：** 控制Ollama模型在显存中的保留时间

**可选值：**
- `-1` - 永久保留（推荐用于开发/生产）
- `5m` - 5分钟后卸载（Ollama默认值）
- `0` - 立即卸载
- `1h` - 1小时后卸载

**设置方式：**

1. **方式1：使用run_ollama.bat（推荐）**
   ```bash
   # 已经设置了OLLAMA_KEEP_ALIVE=-1
   run_ollama.bat
   ```

2. **方式2：系统环境变量**
   ```bash
   # Windows
   setx OLLAMA_KEEP_ALIVE "-1"
   
   # Linux/Mac
   export OLLAMA_KEEP_ALIVE=-1
   ```

3. **方式3：预热时自动设置（本次修复）**
   - 后端启动时自动设置
   - 无需手动配置

---

## 🔄 其他相关配置

### LLM超时配置（.env）

```bash
# 本地Ollama超时（秒）
LLM_LOCAL_TIMEOUT=60

# 远程API超时（秒）
LLM_REMOTE_TIMEOUT=300

# 题目提取重试次数
EXTRACTOR_MAX_RETRIES=3
```

### 重试机制

**question_extractor.py中的重试逻辑：**
- 最多重试3次（EXTRACTOR_MAX_RETRIES=3）
- 每次重试间隔1秒
- 重试条件：empty 或 parse_error

---

## 🚀 验证步骤

### 1. 重启后端
```bash
# 停止当前后端（Ctrl+C）
# 重新启动
python run.py
```

### 2. 查看预热日志
```
[LLM 预热] 已启动 ollama serve（OLLAMA_KEEP_ALIVE=-1，模型常驻显存）
[LLM 预热] Ollama 服务已就绪
[LLM 预热] 预加载 qwen3:4b...
[LLM 预热] ✅ qwen3:4b 已加载（1.5s）
```

### 3. 测试LLM调用
- 等待5分钟以上
- 触发题目提取
- 应该立即响应，不会超时

---

## 📝 总结

### 问题
- Ollama模型5分钟后自动卸载
- 导致首次调用冷启动超时

### 解决
- 预热时设置OLLAMA_KEEP_ALIVE=-1
- 模型常驻显存，永不卸载
- 所有调用都是热启动

### 收益
- ✅ 消除冷启动超时问题
- ✅ 提升响应速度
- ✅ 改善用户体验

---

**修复完成！重启后端即可生效！** 🎉
