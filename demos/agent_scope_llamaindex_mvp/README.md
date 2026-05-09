# AgentScope + LlamaIndex MVP 运行说明

本目录保存一个可离线运行的最小可行演示，用来验证 AgentScope 作为多步骤编排层、LlamaIndex 作为检索层的拆分方式是否成立。

## 目录说明

| 文件 | 说明 |
|---|---|
| [mvp.py](mvp.py) | 核心演示脚本，内置小型面经知识库与确定性回答模型 |
| [requirements.txt](requirements.txt) | 演示所需的 Python 依赖版本 |

## 技术栈

- Python 3.12
- agentscope 1.0.19.post1
- llama-index-core 0.14.21
- llama-index-retrievers-bm25 0.7.1

## 运行方式

1. 安装依赖

    python -m pip install -r requirements.txt

2. 执行脚本

    python mvp.py

说明：在 Windows 上运行时，BM25 检索器可能输出 resource module not available on Windows 的提示，这是已知现象，不影响脚本运行。

## 运行结果

- 第一轮回答：说明 AgentScope 负责编排、LlamaIndex 负责检索、Java 主服务负责治理。
- 第二轮回答：说明检索轨迹应单独落库 query、召回候选、分数、重排结果、模型版本、prompt 版本、trace_id。

## 扩展建议

- 将 BM25 替换为向量库或混合检索。
- 增加 HTTP 接口，便于 Java 主服务调用。
- 把检索轨迹写入独立审计表。
- 增加 OpenTelemetry 跟踪和日志采集。
- 用真实模型替换确定性模型。

验证过程见 [架构验证报告](../../docs/选型记录/02_agent_scope_llamaindex_验证报告.md)。