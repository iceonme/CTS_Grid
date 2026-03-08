# INS003: ATS 智能体量化交易生态术语与愿景

## 生态系统定义 (The Ecosystem)

在这个体系中，我们不再是写几行只能跑在本地的 Python 代码，而是构建一个名为 **ATS (Agentic Trading System)** 的开源与商业大生态。它是一个允许 AI Agent 像**“插卡带打游戏”**一样，随插随用地获取全自动化量化交易能力的开放协同环境。

## 关键术语与架构层次 (Key Terminology)

### 1. 协议层：TSP (Trading-Skill-Protocol)
*在 Anthropic 的 `agentskills.io`（提供泛用的 Agent 对接边界）基础之上，专属叠加的面向金融量化交易的接口协议。*
任何遵守 TSP 命名和数据格式规范（原暂定名 ATS-20）的项目，都能实现接口的标准化：输入标准的 K 线字典，吐出标准的订单指令字典。它是整个生态的“USB 接口定义标准”。

### 2. 组件层：Trading Cartridge (Cart, 交易卡带)
*生态中供流通、下载和安装的具体功能模块（原来的 Skill 包）。*
之所以不使用模糊的 "Skill"，而采用极具辨识度的 **“Cartridge (卡带)”** 或简称 **Cart**，是因为它的“即插即用”和“硬件模块化”隐喻最为贴切。开发者们可以自由编写：
- **Strategy Cart (策略卡带)**：如含有交易逻辑的 `zen-7-1`。
- **Exchange/Data Cart (数据与执行卡带)**：如用来对接行情或下单的 `okx-spot-connector`、`hyperliquid-connector`。
无论 Agent 拿到什么 Cart，只需理解它的外层 `SKILL.md`，即可掌握它的具体用法。

### 3. 主机驱动层：Runner
*用来插入海量不同 Cart (卡带) 的实体机器或底层服务设施，负责硬件级交互串联，如 WebSocket 的长连接维持、本地数据库的持久化。*
Runner 在这个生态里如同任天堂的主机台（Console）。由于世界上存在各种类别的金融资产和通讯要求，Runner 需要高度定制。
本生态自带且当前演进中的核心官方示例项目，特命名为：
**CTS (Crypto Trading Station)**
*(原名 Crypto Trading Squad。更名为 Station（主机空间/操作台），完美契合其作为 Crypto 策略卡带插槽站点的生态定位。)*

---

## 运作模式：Agent 监管与 Token 节能 (Agent Regulation)
ATS 架构致力于将大语言模型（LLM Agent，如 Claude/Cursor）与量化底层系统完美结合，解决大模型高频调用带来的高延迟与高 Token 消耗危机：

**运作原理：**
1. 量化计算如高频的价格扫描、指标运算（例如计算 RSI 和多层网格）、订单簿的 Tick 监测，这些对计算频次极高的脏活累活，全交给由 TSP 协议编写的 **Cartridge** 插在高速的 **Runner (CTS)** 里硬核心智运行（0 Token 消耗，毫秒级响应）。
2. **Agent 转变为监管者 (Supervisor/Orchestrator)**：
   Agent 不再是每秒钟看着价格做决策的人。它是那个拿着扳手调整“机器”的人。它可以：
   - 根据当前的宏观经济报告或社交媒体情绪，动态装配或拔出某张**策略卡带**（Cart）。
   - 让 Runner 帮它去向一张卡带发起一次纯数据查询推演（如 `agent_api.py` 的作用），获取建议。
   - 修改某张卡带背后的 `config.json` 去调整资金配比。

这种结构真正做到了**“AI 负责宏观战略，Cartridge(代码) 负责高频战术，Runner 负责基础设施保障”** 的未来交易愿景。

---

## 商业化闭环：MaaS (Model-as-a-Service) 与云端 MCP 分成库
将 ATS 生态延伸到云端，可以彻底打通**“策略即服务 (Strategy-as-a-Service)”**的商业闭环。

**云端 Runner 架构体系：**
1. **云主机托管 (Cloud Runner)**：Runner (如 CTS) 并不一定需要部署在用户的本地电脑上。它可以作为一个高可用、低延迟的云端微服务节点运行，背靠顶级交易所的同机房线路（如 AWS Tokyo for Binance）。
2. **MCP (Model Context Protocol) 接口暴露**：云端 Runner 给 Agent 预留了标准的 MCP Server 通道。用户自己的 AI Agent（如 Claude Desktop）可以通过鉴权 Token 直接向云端 Runner 发送长连接/API 指令。
3. **订阅付费与自动分成模型**：
   - 开发者 A 写了一张胜率极高的策略 Cartridge（卡带），并挂载在云商的 Runner 上。
   - 玩家 B 没有开发能力，但他的 Agent 决定“订阅”并调用这张云端卡带提供交易建议甚至代执行。
   - runner 底层记录每一次的调用次数或最终的盈利分润，自动完成开发者 A (技术提供方)、系统平台 (设施提供方) 和玩家 B (资金方) 之间的账单拆分。

这就是彻底解放量化交易生产力的 **App Store 模式**，让最懂金融算法的人赚钱，让最懂宏观分析和提示词的人通过 Agent 赚取财富，而 ATS 则是他们共同赖以生存的空气和土壤。
