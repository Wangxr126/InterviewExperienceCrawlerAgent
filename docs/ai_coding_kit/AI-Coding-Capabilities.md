# 推荐 Skill 列表（每项为可实现/自动化的能力）

更新时间: 2026-05-07

以下为精简的“Skill 列表”，每项代表一项可实现或自动化的能力，便于在不同项目间迁移与复用。
---

## 推荐 Skill 列表（精简）

- SDD 文档生成器
- API 合约生成器（OpenAPI）
- Spec → Test 生成器（测试骨架自动化）
- 契约测试（Provider/Consumer，Pact）
- Mock Server / API Sandbox（Prism/WireMock）
- Type / DTO 生成器（openapi-generator / quicktype）
- 接收/验收标准化（Acceptance Criteria 自动化）
- 设计审查 & Checklist 生成器
- 变更日志与 Spec Diff（openapi-diff）
- 文档协同写作助手（草稿生成与审校）
- 可视化 Diagram 生成器（mermaid/UML）

---

## VS Code 插件清单（配合 AI-Coding）

下面这份是“可直接复制名字去 VS Code 安装”的插件建议，我按优先级整理为必装、推荐和可选三类；你给出的插件我已纳入，并补充了少量通用增强项。

### 必装

- Markdown All in One
- Markdown Preview Mermaid Support
- Mermaid Editor
- OpenAPI (Swagger) Editor
- 42Crunch OpenAPI
- Rest Client
- Todo Tree
- Git Graph

### 推荐

- Mermaid Markdown Syntax Highlighting
- PlantUML
- Pact DSL
- Test Explorer UI
- JSON Schema Generator
- Compare Folders
- Markdownlint
- EditorConfig for VS Code
- YAML
- Python
- Pylance
- Docker
- GitLens

### 可选

- Live Share
- Prettier - Code formatter
- ESLint
- Code Spell Checker
- Remote - Containers

### 说明

- 文档 / SDD 写作主要依赖 Markdown 相关插件，方便目录、预览、Mermaid 图和协作审阅。
- API / OpenAPI 主要依赖 Swagger 编辑、校验和 Rest Client，便于接口契约驱动开发。
- 图表 / 架构图依赖 Mermaid 与 PlantUML，便于把 SDD 和设计图统一在仓库中维护。
- 测试 / 契约依赖 Pact、Test Explorer 和 JSON Schema 工具，便于把 Spec 转成可执行验证。
- 工程效率依赖 Todo Tree、Git Graph、GitLens、Compare Folders，便于追踪设计变更与版本演化。

---

（文档仅列出“Skill 名称”，如需将某项能力落地为脚本/工具，请告诉我优先次序，我会按序自动下载/安装所需依赖。）
