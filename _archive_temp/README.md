# 归档文件说明

归档时间：2026-03-08

## 📁 归档内容

### 根目录测试文件
- `newcoder_analysis.json` - 牛客数据分析测试文件
- `nowcoder_final_complete.txt` - 牛客测试数据
- `nowcoder_posts_full.txt` - 牛客帖子测试数据
- `nowcoder_posts.txt` - 牛客帖子测试数据
- `nowcoder_real_full_text.txt` - 牛客真实数据测试
- `nowcoder_test_result.json` - 牛客测试结果

### 根目录临时文档
- `AGENTS.md` - Agent说明（已整合到docs）
- `ENVIRONMENT.md` - 环境说明（已整合到docs）
- `启动检查清单.md` - 启动检查（已整合到docs）
- `工作目录说明.md` - 目录说明（已整合到docs）
- `面经Agent完整设计方案2.md` - 旧版设计方案

### docs目录临时报告
- `4个问题修复完成报告.md` - 临时修复报告
- `Agent配置日志优化完成报告.md` - 临时优化报告
- `LLM提取公司信息自动更新功能实现报告.md` - 临时功能报告
- `LLM超时问题修复报告.md` - 临时修复报告
- `Max_Tokens配置完成总结.md` - 临时配置报告
- `Prompt优化完成总结.md` - 临时优化报告
- `架构重构完成报告.md` - 临时重构报告
- `架构重构进度报告.md` - 临时进度报告
- `递归重试机制实现完成报告.md` - 临时功能报告
- `项目文件整理总结.md` - 临时整理报告

### backend备份文件
- `backend/services/crawler/question_extractor.py.backup` - 代码备份
- `backend/test_main.http` - HTTP测试文件

---

## 📝 保留的核心文档

### 根目录
- `README.md` - 项目说明文档
- `requirements.txt` - Python依赖
- `run.py` - 启动脚本
- `start.bat` / `start.sh` - 启动脚本
- `run_ollama.bat` / `run_ollama.sh` - Ollama启动脚本
- `docker-compose.yml` - Docker配置
- `.gitignore` - Git忽略配置

### docs目录
- `Agent命名方案.md` - Agent命名规范
- `Agent架构重构方案.md` - 架构重构方案
- `Agent架构重构方案_修订版.md` - 架构重构方案修订版
- `环境配置说明.md` - 环境配置文档

### 微调目录
- `微调/` - 完整保留（包含微调数据和文档）

---

## 🎯 归档原因

1. **测试文件** - 开发测试用的临时数据文件，已完成测试
2. **临时报告** - 开发过程中的临时修复/优化报告，功能已稳定
3. **备份文件** - 代码备份文件，已有Git版本控制
4. **重复文档** - 内容已整合到核心文档中

---

## 🔄 恢复方法

如需恢复归档文件：
```bash
# 恢复单个文件
cp _archive_temp/文件名 ./

# 恢复整个目录
cp -r _archive_temp/docs/* docs/
```

---

## 📌 注意事项

- 归档文件不会被删除，仅移动到 `_archive_temp` 目录
- 如有需要可随时恢复
- 建议定期清理归档目录
