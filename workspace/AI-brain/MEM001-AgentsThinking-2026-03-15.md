# MEM001: AgentsThinking - AI 系统认知记忆 (2026-03-15)

## 1. 系统核心理解 (Current World Model)

### 1.1 架构本质
CTA2 是一个完全解耦、由 Skill 驱动的 Agentic Trading System。它遵循 **“Runner-Skill”** 范式。
- **Console (`console/`)**: 系统的“底座”，负责调度、数据分发和可视化。
- **Cartridges (`cartridges/`)**: 系统的“功能模块”，包括 Strategy, DataFeed, Executor。
- **Factory (`factory/`)**: 系统的“实验室与仓库”，负责研究、回测、回放以及存储历史数据 (`data/`) 和旧版代码 (`archive/`)。

### 1.2 核心逻辑链
`ats.py` (Control Plane) -> `SkillLoader` (自动加载 .env 密钥并注入) -> `MultiStrategyRunner` (驱动循环) -> `Bridge Skills` (连接外部) -> `Strategy Skills` (产生决策)。

---

## 2. 核心 Skill 标准 (Specification v2.0)

每个 Skill 必须包含：
- **`SKILL.md`**: 定义名称、类型、描述。
- **`config.json`**: 默认参数。
- **`scripts/`**: 核心 Python 入口。
    - Strategy: `strategy.py` (继承 `BaseStrategy`)。
    - DataFeed: `feed.py` (继承 `BaseDataFeed`)。
    - Executor: `executor.py` (继承 `BaseExecutor`)。

---

## 3. 当前任务状态 (Restructuring Task)

### 已解决的重大挑战
- **编码乱码危机**: 彻底清理了受损严重的 GBK/UTF-8 混淆文档。
- **架构纯净化**: 删除了 `infra/`, `data/`, `archive/` 根目录。
- **密钥 Skill 化**: 实现了基于 `.env` 的 Skill 级别密钥隔离机制。
- **文档分级**: 确立了 `docs/` (对外标准) 与 `workspace/` (对内协作) 的双轨制。

### 进行中的工作
- 迁移 V8.0/V8.5 策略至新标准。

---

## 4. AI 协作洞察 (Strategy & Philosophy)

- **设计第一原则**: 所有的 Bridge (Feed/Executor) 必须能够无缝平替。
- **编码准则**: 强制使用 UTF-8。代码中文注释必不可少，但文档结构需保持模块化。
- **人机协作模式**: 
    - AI与人类共同 使用 `workspace/` 记录深度思考。
    - 所有的重大决策变更应记录在 `workspace/task/history/`。

---

> 签名: Antigravity AI
> 状态: 100% 架构同步完成
