# Insight: 真正独立的 Agentic Trading Skill 架构路线

## 背景
在完成 Strategy Skill 化（Architecture 2.0+）后，目前的 Skill 包（如 `zen-7-1`）实现了从 Runner 的“物理文件解耦”，但依然存在“运行时逻辑耦合”。
比如：`strategy.py` 中 `from core import MarketData, Signal` 的设计，导致外来 Agent（如直接调用的 Claude 或独立微服务）在没有完整 CTS1 项目环境时，无法独立运行该策略。

## 用户的进阶愿景 (Agentic Trading Skill)
策略 Skill 不应该仅仅是一个“被特定 Runner 调用的代码块”，而应该是一个**自带完整元语义与最小执行环境的独立知识实体**。
- **能验证**：自带微型模拟器/验证脚本。
- **能问答**：Agent 可以把它作为一个 Tool/Skill 学习，只要提供外部数据源（如传入当前一小时的 K 线），它就能直接返回人类可读的交易建议。
- **能微服务化**：任何兼容该标准轻量输入输出的执行终端（不限于 CTS1 Runner），都可以挂载它。

## 实现路径（架构 3.0 预研方向）
为了达到真正的脱离宿主独立运行，我们需要对 Skill 包进行依赖逆转（Dependency Inversion）：
1. **自带核心数据结构存根 (Stub)**：
   Skill 包内新增 `scripts/types.py`，自定义简化版的 `MarketData` 和 `Signal` 等类。彻底移除 `from core import ...` 这种跨包强依赖。
   *Runner 端加载时，将自己的数据通过接口适配器（Adapter）转换为 Skill 内置的轻量数据结构。*
2. **新增 Agent 对话接口 (`scripts/agent_api.py`)**：
   暴露语义化接口，如 `def get_trading_advice(price_history: List[dict]) -> str`。
   Agent 拿到了大盘数据，只需要把数据序列化扔进去，Skill 内部算完指标后，返回：“当前 RSI=20 严重超卖，且触碰布林带下轨，建议执行 BUY 100 USDT”。
3. **完善 `SKILL.md` 的学习材料属性**：
   文档明确告知 Agent：“你可以调用 `scripts/agent_api.py` 的 `analyze()` 方法，我将为你进行复杂的数学模型和动态网格运算并给出建议。”

## 结论
这个思路非常超前且正确——**将量化策略从“代码”升格为“Agent 的可插拔神经模块”**。它将指导我们下一阶段的架构设计。
当我们需要让 Agent 具备真正的自主交易决策能力时，这将是我们的首要改造目标。

## 理论引申：双层标准套娃与开放依赖生态
在推进 Architecture 3.0+ 架构时，需谨记由本项目的开发者提出的 **双层标准继承 (Protocol Inheritance)** 以及 **Npm 化依赖** 思想：

### 1. 继承与套壳
Trading Skill 架构并非闭门造车，而是建立在兼容 `agentskills.io` 宽泛规范的底座之上：
- **外壳 (Base Protocol)**：遵循 Anthropic 定义的 `SKILL.md` 与指令映射约束。任何支持智能体的系统通过扫描该目录，就能识别它是一个可调用的工具。
- **内核 (Application Protocol)**：在该结构内部（如强制的 `scripts/strategy.py`、继承 `BaseStrategy`、配套 `config.json`），又实现了本项目强硬的量化执行标准，让核心 Runner 得以直接接管。

### 2. NPM 化的“声明式依赖” (Declarative Dependency)
真正的瘦技能（Thin Skill）不应把执行器引擎（Runner）和底层行情通道（Datafeed）打包进仓库冗余分发。
相反，应当在 `SKILL.md` (或元数据文件) 内显式声明**所需宿主环境能力**（例如：必须兼容某版本的 CTS Runner 和 OKX Datafeed）。
**Agent 扮演了如同 `npm install` 包管理器的角色**：拿到某个 Skill（如 `zen-7-1`）后，看到里面有相关依赖说明，便主动寻找或下载对应的标准执行环境与之拼装起效，真正做到“即插即用”和生态开放。
