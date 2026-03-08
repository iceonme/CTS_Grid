# Walkthrough: Strategy Skill 化架构实现 (Zen-7-1 迁移)

## 任务目标
将原有的固化代码策略（`zen_7_1.py`）解耦重构为符合 Anthropic [agentskills.io](https://agentskills.io/specification) 标准的双模式 Skill 包，并配套升级系统的动态加载底座机制。

## 主要变更

### 1. 新建 `runner/skill_loader.py`
创建了动态插件加载中心：
- 自动解析 `SKILL.md` 的 YAML 元数据。
- 动态 import 策略脚本（`scripts/strategy.py`），自动寻址 `BaseStrategy` 的子类。
- 实现 `config.local.json` 合并机制（允许跨机器传递策略但不污染本地化配置）。
- 给 Runner 底座的 `StrategySlot` 补充注入了 `skill_meta`，为日后接入 AI Dashboard / MCP 预留上下文。

### 2. 双模式 Skill 包确立 (`strategies/skills/zen-7-1/`)
实现了 Agent-First 的包结构：
- **`SKILL.md` (Agent 指引)**：非面向人类，而是采用动词驱动和清晰触发点描述，指导 Agent 如何查验数据、更改参数以及部署该策略服务。
- **`config.json` (状态隔离)**：将原写死在策略 `__init__` 的调优参数（如 `resample_min`, `grid_drop_pct` 等）完全解耦进 JSON。
- **`scripts/strategy.py` (业务引擎)**：移入该路径下。原 `on_data` 和 `on_fill` 代码原封不动完美兼容，仅需修改导包路径。
- **`scripts/verify.py` (Agent 自测探针)**：新增此组件，允许 Agent 或服务在全量加载整个系统之前，仅用几根 Mock K线快速验证引擎逻辑与参数解析树正常工作。
- **`assets/backtest_summary.json` (知识外化)**：固化了此参数集在过去核心测试中的表现特征，供 Agent 判断调用时机。

### 3. 标准落地
- 编写并固化了 `docs/trading_skill_spec.md`：团队与多代理共同遵守的策略插件结构开发规范。

## 验证结论
- **API 接口完整性**：执行 `scripts/verify.py` 后，策略正常初始化并消化 65 根模拟 K 线，内部指标（如 RSI 等）和信号生成均无异常报错。
- **SkillLoader 单元测试**：新添的 `tests/test_skill_loader.py` 全部 pass，成功读取并组合了解耦出的 config 与 strategy 类。

## 下一步建议
1. 此阶段暂未将 Runner 直接升格为 MCP Server。待该标准在其他经典策略（如 `grid_jeff_6_5`）上复刻稳定后，再由 Agent 统一接管服务调度接口。
2. 完善策略层状态机的快照导出格式，使 Agent 可以更精细地读取正在运行时的实时动态内部指标（如正在持有的每一张网格单的状态）。
