# LLM提取公司信息自动更新功能实现报告

## 🎯 需求

当LLM从面经内容中提取到公司信息后，自动更新crawl_tasks表中对应URL的公司字段，避免前端显示空白。

---

## 💡 实现方案

### 核心逻辑

在`_save_questions`函数中，保存题目后：
1. 收集所有题目中LLM提取到的公司信息
2. 按URL分组，建立URL→公司的映射
3. 批量更新crawl_tasks表中对应URL的公司字段
4. 只更新原本为空或"未知"的记录，避免覆盖已有的正确信息

---

## 📝 修改内容

### 修改位置
`backend/services/scheduler.py` 第483行（`_save_questions`函数末尾）

### 新增代码

```python
# ── 更新crawl_tasks表中的公司信息（如果LLM提取到了）─────────
if saved > 0 and questions:
    # 收集所有URL对应的公司信息
    url_company_map = {}
    for q in questions:
        if isinstance(q, dict):
            url = q.get("source_url", "")
            company = q.get("company", "").strip()
            # 只有当LLM提取到了公司信息，且不是"未知"时才更新
            if url and company and company != "未知":
                url_company_map[url] = company
    
    # 批量更新crawl_tasks表
    if url_company_map:
        try:
            with sqlite_service._get_conn() as conn:
                for url, company in url_company_map.items():
                    # 只更新company字段为空或"未知"的记录
                    conn.execute("""
                        UPDATE crawl_tasks 
                        SET company = ? 
                        WHERE source_url = ? 
                        AND (company IS NULL OR company = '' OR company = '未知')
                    """, (company, url))
                conn.commit()
            logger.debug(f"✅ 已更新 {len(url_company_map)} 个URL的公司信息")
        except Exception as e:
            logger.warning(f"更新crawl_tasks公司信息失败: {e}")

return saved
```

---

## 🎯 工作流程

### 原有流程
```
1. LLM提取题目（包含公司信息）
2. 保存题目到questions表
3. 保存题目到Neo4j（可选）
4. 返回保存数量
```

### 新流程
```
1. LLM提取题目（包含公司信息）
2. 保存题目到questions表
3. 保存题目到Neo4j（可选）
4. 收集所有题目中的公司信息
5. 批量更新crawl_tasks表中对应URL的公司字段 ✨
6. 返回保存数量
```

---

## 📊 示例场景

### 场景1：爬取时未获取到公司信息

**初始状态（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/xxx
company: NULL
post_title: 某大厂面经
```

**LLM提取后（questions表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/xxx
company: 阿里巴巴
question_text: 请介绍Redis的应用场景
```

**自动更新后（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/xxx
company: 阿里巴巴  ✅ 已更新
post_title: 某大厂面经
```

---

### 场景2：爬取时已有公司信息

**初始状态（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/yyy
company: 字节跳动
post_title: 字节AI面经
```

**LLM提取后（questions表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/yyy
company: 字节跳动
question_text: 请介绍Transformer架构
```

**自动更新后（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/yyy
company: 字节跳动  ✅ 保持不变（已有正确信息）
post_title: 字节AI面经
```

---

### 场景3：公司信息为"未知"

**初始状态（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/zzz
company: 未知
post_title: 某公司面经
```

**LLM提取后（questions表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/zzz
company: 腾讯
question_text: 请介绍微信的架构设计
```

**自动更新后（crawl_tasks表）：**
```
source_url: https://www.nowcoder.com/feed/main/detail/zzz
company: 腾讯  ✅ 已更新（替换"未知"）
post_title: 某公司面经
```

---

## 🎯 更新规则

### 何时更新
- ✅ 当LLM成功提取到公司信息时
- ✅ 当公司信息不是"未知"时
- ✅ 当crawl_tasks表中的公司字段为空、空字符串或"未知"时

### 何时不更新
- ❌ LLM未提取到公司信息
- ❌ LLM提取的公司是"未知"
- ❌ crawl_tasks表中已有明确的公司信息

### SQL更新条件
```sql
UPDATE crawl_tasks 
SET company = ? 
WHERE source_url = ? 
AND (company IS NULL OR company = '' OR company = '未知')
```

---

## 📊 日志输出

### 成功更新
```
✅ 已更新 5 个URL的公司信息
```

### 无需更新
```
（无日志输出，静默跳过）
```

### 更新失败
```
⚠️ 更新crawl_tasks公司信息失败: [错误信息]
```

---

## 🎯 优化点

### 1. 智能更新
- ✅ 只更新空白或"未知"的记录
- ✅ 不覆盖已有的正确信息
- ✅ 避免重复更新

### 2. 批量处理
- ✅ 收集所有URL的公司信息
- ✅ 一次性批量更新
- ✅ 提高性能

### 3. 容错处理
- ✅ 更新失败不影响题目保存
- ✅ 记录警告日志便于排查
- ✅ 静默跳过无效数据

### 4. 数据质量
- ✅ 过滤"未知"等无效值
- ✅ 去除空白字符
- ✅ 验证URL和公司都存在

---

## 🚀 效果

### 修改前
```
前端显示：
┌─────────────────────────────────────┐
│ 标题：阿里淘天大模型Agent校招面经    │
│ 公司：（空白）                      │  ❌
│ 状态：待提取                        │
└─────────────────────────────────────┘
```

### 修改后
```
前端显示：
┌─────────────────────────────────────┐
│ 标题：阿里淘天大模型Agent校招面经    │
│ 公司：阿里巴巴                      │  ✅
│ 状态：已完成                        │
└─────────────────────────────────────┘
```

---

## 📝 总结

### 修改的文件
1. ✅ `backend/services/scheduler.py` - 添加公司信息自动更新逻辑

### 核心改进
- ✅ LLM提取的公司信息自动回填到crawl_tasks表
- ✅ 前端显示更完整的公司信息
- ✅ 智能更新规则，避免覆盖已有数据
- ✅ 批量处理，提高性能

### 适用场景
- ✅ 爬取时未获取到公司信息
- ✅ 爬取时公司信息为"未知"
- ✅ 标题中包含公司但未解析出来

### 不适用场景
- ❌ 爬取时已有明确的公司信息（保持不变）
- ❌ LLM未提取到公司信息（无法更新）

---

## 🎯 验证方法

### 1. 重启后端
```bash
python run.py
```

### 2. 触发爬取任务
- 前端点击【开始爬取】
- 等待LLM提取完成

### 3. 查看日志
```
✅ 已更新 5 个URL的公司信息
```

### 4. 查看前端
- 刷新任务列表
- 检查公司列是否显示正确

---

**LLM提取公司信息自动更新功能实现完成！重启后端即可生效！** 🎉
