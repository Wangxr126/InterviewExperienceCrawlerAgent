# 前端 Step 显示位置错误 - 修复总结

## 问题描述
后端推送 `step: 1`，但前端渲染时显示错了位置（例如显示"第 2 步"或"第 3 步"）。

## 根本原因
`computeStepDisplay()` 函数的计算逻辑有缺陷：
```javascript
// ❌ 旧逻辑：计算"到当前位置为止有多少个非pending步"
function computeStepDisplay(thinking, idx) {
  let num = 0
  for (let i = 0; i <= idx; i++) {
    if (thinking[i].__step !== 'pending') num++
  }
  return num  // 这会导致错位！
}
```

**问题**：
- 这个函数计算的是数组中"到当前位置为止有多少个非pending步"
- 但后端已经在 `__step` 字段中设置了正确的步号
- 重新计算反而会导致错位

## 修复方案
直接使用后端传来的 `__step` 值，而不是重新计算：

```javascript
// ✅ 新逻辑：优先使用后端的 __step 值
function computeStepDisplay(thinking, idx) {
  const step = thinking[idx]
  if (!step) return idx + 1
  // 优先使用后端的 __step 值（已验证正确）
  if (typeof step.__step === 'number' && step.__step > 0) {
    return step.__step
  }
  // 降级：按数组位置计算（兼容旧数据）
  let num = 0
  for (let i = 0; i <= idx; i++) {
    if (thinking[i].__step !== 'pending') num++
  }
  return num
}
```

## 修改文件
- **文件**：`web/src/views/ChatView.vue`
- **函数**：`computeStepDisplay(thinking, idx)`
- **行号**：约 430-440 行

## 验证方法
1. 启动后端和前端
2. 发送一条包含多步推理的问题
3. 观察推理过程展开时，步骤编号是否正确
4. 后端推送 `step: 1` 时，前端应显示"第 1 步"
5. 后端推送 `step: 2` 时，前端应显示"第 2 步"

## 相关修复
这是流式推送问题的第 7 个修复，前面还有：
1. ✅ 后端 step 编号追踪逻辑
2. ✅ 后端 result 和 thinking_steps 分离
3. ✅ 后端数据库保存逻辑
4. ✅ 前端 SSE 事件处理
5. ✅ 前端 thinking 步骤合并
6. ✅ 前端 pending 步骤管理
7. ✅ **前端 step 显示位置**（本修复）

## 测试状态
- [x] 代码修改完成
- [ ] 功能测试（待验证）
