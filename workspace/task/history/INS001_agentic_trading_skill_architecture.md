# Insight: 真正独立鐨?Agentic Trading Skill 架构路线

## 背景
在完鎴?Strategy Skill 化（Architecture 2.0+）后，目前的 Skill 包（濡?`zen-7-1`）实现了浠?Runner 鐨勨€滅墿理文件解鑰︹€濓紝但依然存鍦ㄢ€滆繍行时逻辑耦合鈥濄€?
比如：`strategy.py` 涓?`from core import MarketData, Signal` 的设计，导致外来 Agent（如直接调用鐨?Claude 或独立微服务）在没有完整 CTS1 项Ŀ环境时，无法独立运行该策鐣ャ€?

## 用户的进阶愿鏅?(Agentic Trading Skill)
策略 Skill 不应该仅仅是涓€涓€滆特定 Runner 调用的代码块”，而应该是涓€涓?*自带完整元语义与鏈€小执行环境的独立֪ʶʵ体**銆?
- **能验璇?*：自带微型模拟器/验证脚本銆?
- **能问绛?*：Agent 可以把它作为涓€涓?Tool/Skill 学习，只要提供外部数据源（如传入当前涓€小时鐨?K 线），它就能直接返回人类可读的交易建璁€?
- **能微服务鍖?*：任何兼容该标准轻量输入输出的执行终端（不限浜?CTS1 Runner），都可以挂载它銆?

## 实现路径（架鏋?3.0 预研方向锛?
为了达到真正的脱离宿主独立运行，我们闇€要对 Skill 包进行依璧栭€嗚浆（Dependency Inversion）：
1. **自带核心数据结构存根 (Stub)**锛?
   Skill 包内新增 `scripts/types.py`，自定义箢㻯版鐨?`MarketData` 鍜?`Signal` 等类。彻底移闄?`from core import ...` 这种跨包强依璧栥€?
   *Runner 端加载时，将自己的数鎹€氳繃接口适配器（Adapter）ת换为 Skill 内置的轻量数据结鏋勩€?
2. **新增 Agent 对话接口 (`scripts/agent_api.py`)**锛?
   暴¶语义化接口，濡?`def get_trading_advice(price_history: List[dict]) -> str`銆?
   Agent 拿到了大盘数据，只需要把数据序列化扔进去，Skill 内部算完指标后，返回锛氣€滃綋鍓?RSI=20 严重超卖，且触碰布林带下轨，建议执行 BUY 100 USDT鈥濄€?
3. **完善 `SKILL.md` 的学习材料属鎬?*锛?
   文档明确告知 Agent锛氣€滀綘可以调用 `scripts/agent_api.py` 鐨?`analyze()` 方法，我将为你进行复杂的数学ģ型和动态网格运算并给出建议銆傗€?

## 结论
这个思路非常超ǰ且正纭€斺€?*将量化策略从“代鐮佲€濆崌格为“Agent 的可插拔神经模块鈥?*。它将指导我们下涓€阶段的架构设璁°€?
当我们需要让 Agent 具备真正的自主交易决策能力时，这将是我们的首Ҫ改造目鏍囥€?

## 理论引申：双层标准套娃与寮€放依赖生鎬?
在推杩?Architecture 3.0+ 架构时，闇€谨记由本项目的开鍙戣€呮彁出的 **双层标准继承 (Protocol Inheritance)** 以及 **Npm 化依璧?* 思想锛?

### 1. 继承与套澹?
Trading Skill 架构并非闭门造车锛岃€屾槸建立在兼瀹?`agentskills.io` 宽泛规范的底座之上：
- **外壳 (Base Protocol)**：遵寰?Anthropic 定义鐨?`SKILL.md` 与指令映射约鏉熴€備换何支持智能体的系缁熼€氳繃扫描该目录，就能识别它是涓€个可调用的工鍏枫€?
- **内核 (Application Protocol)**：在该结构内部（如强制的 `scripts/strategy.py`、继鎵?`BaseStrategy`、配濂?`config.json`），又实现了本项目强硬的量化执行标׼，让核心 Runner 得以直接接管銆?

### 2. NPM 化的“声明式依赖鈥?(Declarative Dependency)
真正的瘦鎶€能（Thin Skill）不应把执行器引擎（Runner）和底层行情通道（Datafeed）打包进仓库冗余分发銆?
相反，应当在 `SKILL.md` (或元数据文件) 内显式声鏄?*鎵€闇€宿主环境能力**（例如：必须兼容ĳ版本的 CTS Runner 鍜?OKX Datafeed锛夈€?
**Agent 扮演了如鍚?`npm install` 包管理器的角鑹?*：拿到某涓?Skill（如 `zen-7-1`）后，看到里面有相关依赖说明，便主动寻找或下载对Ӧ的标׼执行环境与֮拼装起效，真正做鍒扳€滃嵆插即鐢ㄢ€濆拰鐢熸€佸紑鏀俱€?
