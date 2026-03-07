# 面经题目提取 - 微调数据构造

本文件夹包含 1.5b 模型面经题目提取的微调数据构造脚本、样本及文档。

## 文件说明

| 文件 | 说明 |
|------|------|
| `finetune_data_builder.py` | 数据构造脚本 |
| `manual_samples.jsonl` | 手动标注样本（可编辑追加） |
| `finetune_samples.jsonl` | 生成的 SFT 格式输出 |
| `LLM提取改进分析与微调数据构造.md` | 问题分析与使用说明 |

## 快速使用

在**项目根目录**执行：

```bash
# 输出空模板
python 微调/finetune_data_builder.py --template

# 从手动样本生成 SFT 数据
python 微调/finetune_data_builder.py --from-manual

# 从 LLM 日志筛选可用样本
python 微调/finetune_data_builder.py --from-log
```

详见 `LLM提取改进分析与微调数据构造.md`。
