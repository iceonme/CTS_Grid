# CTA2 系统全景图 v2.0

## 1. 核心设计：模块化加载架构

CTA2 (Crypto Trading Agent 2.0) 采用 **“平台(Runner) + 技能包(Skill)”** 的插件化设计。系统核心不再硬编码具体的策略或接口，而是通过一套标准协议动态加载和组装 trading 组件。

### 1.1 技能包分类 (Skill Types)
系统将交易逻辑解构为三种标准 Skill：
- **Strategy (策略卡带)**: 执行核心数学模型与决策逻辑（如 `grid-v60`）。
- **DataFeed (数据网关)**: 负责与交易所建立通信并推送实时行情（如 `okx-feed`）。
- **Executor (指令执行)**: 负责落实买卖订单、管理仓位及对账（如 `paper-executor`）。

---

## 2. 逻辑架构图

```mermaid
graph TD
    subgraph "Console Layer (控制台层)"
        L[launcher.py] --> SL[SkillLoader]
        L --> R[MultiStrategyRunner]
    end

    subgraph "Bridge Layer (桥接层 - Bridge Skills)"
        DF[DataFeed Skill] -- 推送市场数据 --> R
        E[Executor Skill] -- 执行交易指令 --> R
    end

    subgraph "Cartridge Layer (卡带层 - Strategy Skill)"
        S[Strategy Skill] -- 输出交易信号 --> R
    end

    R -- 状态同步 --> D[Dashboard Server]
    D -- 可视化 --> U[Frontend UI]
```

---

## 3. 核心组件交互流程

1.  **加载阶段**: `launcher.py` 调用 `SkillLoader` 扫描指定的目录，读取 `SKILL.md` 的 Frontmatter 元数据。
2.  **实例化**: `SkillLoader` 动态导入 `scripts/` 下的入口脚本，并注入 `config.json` 中的参数。
3.  **运行循环**:
    - `DataFeed` 获取原始数据，解析为标准的 `MarketData` 对象。
    - `Runner` 将数据分发至挂载的 `Strategy`。
    - `Strategy` 输出 `Signal`。
    - `Runner` 协调 `Executor` 根据信号下达真实的 `Order`。

---

## 4. 目录规范

- `cartridges/strategies/`: 存放各种策略“卡带”。
- `cartridges/bridge/`: 存放连接外部世界的“桥接器”（DataFeeds, Executors）。
- `console/`: 存放系统的“游戏机底座”（Runner, Loader, Dashboard）。

---

> 更新日期: 2026-03-15
> 文档标准: v2.0 (Agentic Architecture Standard)
