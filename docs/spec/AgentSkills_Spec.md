# Agent Skills Specification (General)

## 1. 宗旨
Agent Skills 规范是一套通用的 AI 原生插件定义标准。它旨在通过强类型元数据（YAML Frontmatter）和标准化的文件系统布局，使 AI 智能体可以自主地识别、调用并组合不同的软件功能模块。

## 2. 核心特征
- **自描述 (Self-describing)**: 每一个 Skill 包通过 `SKILL.md` 自行宣告其身份和契约。
- **环境隔离**: 所有依赖与配置均限制在 Skill 包内目录中。
- **配置驱动**: 通过单一 `config.json` 进行行为注入。

## 3. 元数据核心字段
- `name`: 模块的全局唯一标识。
- `metadata.type`: 决定了该 Skill 的运行环境和接口预期。
- `metadata.version`: 语义化版本号。

## 4. 人机协作约定
- 文档统一使用 **UTF-8（无 BOM）** 编码。
- 逻辑代码与说明文档的分离设计。

---
> 它是 CTA2 模块化底座的基石。
> 更新日期: 2026-03-15
