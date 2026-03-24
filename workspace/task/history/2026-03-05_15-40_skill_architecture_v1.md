# Walkthrough: Strategy Skill 化架构实鐜?(Zen-7-1 迁移)

## 任务目标
将原有的固化代码策略（`zen_7_1.py`）解耦重构为符合 Anthropic [agentskills.io](https://agentskills.io/specification) 标准的双模式 Skill 包，并配套升级系统的鍔ㄦ€佸姞载底座机鍒躲€?

## 主要变更

### 1. 新建 `runner/skill_loader.py`
创建了动态插件加载中心：
- 自动解析 `SKILL.md` 鐨?YAML 元数鎹€?
- 鍔ㄦ€?import 策略脚本（`scripts/strategy.py`），自动Ѱַ `BaseStrategy` 的子绫汇€?
- 实现 `config.local.json` 合并机制（允许跨机器浼犻€掔瓥略但不污染本地化配置锛夈€?
- 缁?Runner 底座鐨?`StrategySlot` 补充注入浜?`skill_meta`，为日后接入 AI Dashboard / MCP 预留上下鏂囥€?

### 2. 双模寮?Skill 包确绔?(`strategies/skills/zen-7-1/`)
实现浜?Agent-First 的包结构锛?
- **`SKILL.md` (Agent 指引)**：非面向人类锛岃€屾槸采用动词驱动和清晰触发点描述，指瀵?Agent 如何查验数据、更改参数以及部署该策略服务銆?
- **`config.json` (鐘舵€侀殧绂?**：将原写死在策略 `__init__` 的调优参数（濡?`resample_min`, `grid_drop_pct` 等）完全瑙ｈ€﹁繘 JSON銆?
- **`scripts/strategy.py` (业务引擎)**：移入该路径涓嬨€傚師 `on_data` 鍜?`on_fill` 代码原封不动完美兼容，仅闇€修改导包路径銆?
- **`scripts/verify.py` (Agent 自测探针)**：新增此组件，允璁?Agent 或服务在全量加载整个系统之前，仅用几鏍?Mock K线快速验证引鎿庨€昏緫与参数解析树正常工作銆?
- **`assets/backtest_summary.json` (知识外化)**：固化了此参数集在过去核心测试中的表现特征，渚?Agent 判断调用时机銆?

### 3. 标准落地
- 编写并固化了 `docs/trading_skill_spec.md`：团队与多代理共同遵守的策略插件结构弢㷢规鑼冦€?

## 验֤结论
- **API 接口完整鎬?*：执琛?`scripts/verify.py` 后，策略正常初始化并消化 65 根模鎷?K 线，内部指标（如 RSI 等）和信号生成均无异常报閿欍€?
- **SkillLoader 单元测试**：新添的 `tests/test_skill_loader.py` 全部 pass，成功读ȡ并组合了解耦出鐨?config 涓?strategy 绫汇€?

## 下一步建璁?
1. 此阶段暂未将 Runner 直接升格涓?MCP Server。待该标准在其他经典策略（如 `grid_jeff_6_5`）上复刻稳定后，再由 Agent ͳһ接管服务调度接口銆?
2. 完善策略层状态机的快照导出格式，浣?Agent 可以更精细地读取正在运行ʱ的实时鍔ㄦ€佸唴部指标（如正在持有的每一张网格单的状态）銆?
