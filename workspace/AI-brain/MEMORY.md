# CTA2 AI Long-term Memory (MEMORY.md)

这是 CTA2 项目的长期记忆库，记录了项目的灵魂、核心原则、重大决策演进及不可逾越的底线。它是 AI 跨 session 维持认知一致性的基石。

## 1. 项目愿景与使命 (Vision)
- **目标**: 构建一个高度模块化、Agent 友好的量化交易系统 (Agentic Trading System)。
- **核心价值**: 解耦决策与执行，利用 AI 增强交易洞察，保持系统的极致灵活性。

## 2. 核心设计原则 (Guiding Principles)
- **Skill 化一切**: 策略、数据、执行必须全部 Skill 化，遵循统一的加载规范。
    - **[Agent Skills Spec](../../docs/spec/AgentSkills_Spec.md)**: 符合anthropics制定的行业标准，可以对skill基础组件化与元数据定义标准。
    - **[Trading Skill Spec](../../docs/spec/trading_skill_v2.md)**: 属于CTA/ATS系统即交易专用 Skill 的接口与目录规范。
- **解耦第一**: 策略大脑不关心数据来源和执行细节，Bridge 层负责屏蔽外部复杂性。
- **密钥隔离**: 严禁在代码或 `config.json` 中明文存储 API 密钥。敏感信息必须通过各 Skill 目录下的 `.env` 文件独立管理。
- **透明性**: 所有的决策过程（Decision Trace）必须可记录、可追溯。

## 3. 重大架构决策记录 (ADR)
- **2026-03-15 (v2.0 架构确立)**:
    - 引入 `SkillLoader` 和 `ats.py` 驱动的动态插拔机制与 Agent 友好控制平面。
    - 确立文档双轨制：`docs/` (对外 Wiki) 与 `workspace/` (对内协作)。
- **2026-03-25 (v3.1 异步总线架构)**: [NEW]
    - 完成从单体同步到 **完全异步事件驱动 (EventBus)** 的演进。
    - 确立 **Dashboard Skill 化** 决策：UI 作为数据消费者，支持“宿主看板+策略插件”的双端展示模式。

## 4. 开发规范与底线 (Conventions)
- **文档演进工作流 (Workflow: INS -> ADR)**:
    - **INS (Insight)**: 重要讨论内容的沉淀、思考洞察或尚未执行的预研存档。
    - **ADR (Architectural Decision Record)**: 讨论达成共识、且进入执行阶段的最终技术决策。它是**开发指令的最高准则**。
- **编码**: 强制执行 **UTF-8 (No BOM)**。禁止在文档中使用 GBK 编码以避免乱码危机。
- **命名**: 协作文档遵循 `[类型][ID]-[名称]-[日期]` 规范。
- **注释**: 核心逻辑必须有清晰的中文注释，以方便人类开发者理解和审计。

## 5. 项目进化历程 (Evolution)
- **CTS1 时代**: 经典的单文件网格策略。
- **CTA2 转型期**: 开始 Skill 化重构，引入 Runner-Skill 范式。
- **文档大重构 (2026-03-15)**: 解决了毁灭性的乱码灾难，建立了科学的文档体系。
- **异步微服务化 (2026-03-25)**: 突破同步阻塞瓶颈，实现全链路异步化与插件式 UI。

---
> 保持记忆，持续进化。
> Last Updated: 2026-03-25
