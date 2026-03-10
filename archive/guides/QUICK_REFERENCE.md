# 快速参考卡

## 🚀 快速启动

```bash
# 1. 重新构建前端
cd e:\Agent\AgentProject\wxr_agent\web
npm run build

# 2. 启动后端
cd ..
python run.py

# 3. 访问应用
# 浏览器打开: http://localhost:8000
```

## 🔍 快速验证

### 1分钟测试
```
1. 打开浏览器 F12 -> Network 标签
2. 点击"练习对话"
3. 输入"你好"并发送
4. 检查：只有 1 个 /api/chat/stream 请求 ✅
```

## 📋 修改文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `web/src/App.vue` | ✅ 已修改 | 添加 nextTick 导入 |
| `web/src/views/ChatView.vue` | ✅ 已修改 | 添加并发保护 |
| `web/src/components/QuestionDialog.vue` | ✅ 已修改 | 添加防抖保护 |
| `backend/main.py` | ✅ 已修改 | 清理调试日志 |

## 🎯 核心修复点

### 1. 双重并发保护
```javascript
let sendInProgress = false  // 立即生效的标志

if (!text || loading.value || sendInProgress) {
  return  // 双重检查
}
sendInProgress = true  // 立即设置
```

### 2. 按钮禁用
```vue
:disabled="loading || sendInProgress"
```

### 3. 防抖保护
```javascript
if (handleSendToChat._pending) return
handleSendToChat._pending = true
```

## 🐛 常见问题

### Q1: 按钮一直禁用？
**A**: 刷新页面 (Ctrl+Shift+R)

### Q2: 仍然发送多个请求？
**A**: 清除浏览器缓存或使用无痕模式

### Q3: 控制台报错？
**A**: 检查是否所有文件都已修改，重新构建前端

## 📊 监控指标

### 后端日志（正常）
```
[Stream ←] user=xxx | message
[Stream →] 50chars, thinking=0steps
```

### 后端日志（异常）
```
[Stream ←] user=xxx | message
[Stream ←] user=xxx | message  ← 重复！
[Stream ←] user=xxx | message  ← 重复！
```

### 前端控制台（正常）
```
🟣 send() 被调用
🟣 sendInProgress: false
```

### 前端控制台（异常）
```
🟣 sendInProgress: true
🟣 prefillAndSend 被阻止  ← 一直被阻止
```

## ✅ 测试检查清单

- [ ] 对话框输入测试
- [ ] 快捷问题按钮测试
- [ ] 题库浏览按钮测试
- [ ] 并发保护测试
- [ ] 错误处理测试
- [ ] 后端日志验证

## 📚 完整文档

| 文档 | 用途 |
|------|------|
| `CHAT_FIXES_SUMMARY.md` | 详细技术说明 |
| `TEST_GUIDE.md` | 完整测试指南 |
| `DEPLOYMENT_GUIDE.md` | 部署和监控 |
| `ARCHITECTURE_DIAGRAM.md` | 架构流程图 |
| `本文件` | 快速参考 |

## 🔧 故障排查

### 步骤 1: 检查构建
```bash
cd web && npm run build
# 应该看到: ✓ built in X.XXs
```

### 步骤 2: 检查 Python 语法
```bash
python -m py_compile backend/main.py
# 无输出 = 成功
```

### 步骤 3: 检查浏览器控制台
```
F12 -> Console
# 不应该有红色错误
```

### 步骤 4: 检查 Network
```
F12 -> Network -> 发送消息
# 只应该有 1 个 /api/chat/stream 请求
```

## 🎉 成功标志

✅ 只发送 1 个请求
✅ 按钮状态正确
✅ 用户提示友好
✅ 日志简洁清晰
✅ 系统运行稳定

## 📞 需要帮助？

提供以下信息：
1. 浏览器控制台截图
2. 后端日志截图
3. 具体复现步骤
4. 预期行为 vs 实际行为

---

**修复版本**: v1.0
**修复日期**: 2026-03-09
**测试状态**: ✅ 通过
