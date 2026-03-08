# ATS (Agentic Trading System) 智能体量化交易生态白皮书 (v1.0 草案)

## 1. 摘要与愿景 (Abstract & Vision)

随着大语言模型 (LLM) 和自主智能体 (Autonomous Agents) 的爆发，金融交易的护城河正在重构。传统的量化系统（单体架构、高代码耦合、配置极其晦涩）已经无法适应当下 AI 原生的交互方式。

**ATS (Agentic Trading System)** 致力于打造世界首个**“面向智能体的量化交易开放生态”**。
我们的愿景是：让 AI 像插拔 U 盘或打游戏插卡带一样，随时随地获取金融数据分析与全自动量化化交易的能力。在 ATS 生态中，最懂金融算法的极客负责开发“卡带”，最懂宏观分析和提示词工程的用户通过 Agent 监管“主机”，通过云端 MCP (Model Context Protocol) 协议实现生态内各链条的价值流转与利益分成。

---

## 2. 核心架构与术语 (Core Architecture & Terminology)

为了实现彻底的解耦与多语言多主机的互操作性，ATS 生态以极简的 **“三层结构”** 为内核：

### 2.1 协议层：TSP (Trading-Skill-Protocol)
这是 ATS 生态运作的“USB 标准定义”，建立在 Anthropic `agentskills.io` 标准基础之上：
- **纯化通信 (Pure Data Schema)**： TSP 规定策略大脑与基础设施之间的通信必须是基于原生 JSON/字典字典 的 `MarketData` 和 `Signal`，拒绝任何底层框架代码的交叉引用 (0 框架依赖)。

### 2.2 组件层：Trading Cartridge (交易卡带 / Cart)
遵守 TSP 标准开发出来的、可独立流通的微型功能包。
- **Strategy Cart (策略卡带)**：如 `zen-7-1`。它是一个纯粹的代码“脑组织”，输入标准历史 K 线流，输出买卖决策点。它可以是一个包含了几十页数学公式推导的纯 Python 脚本，并附带 `SKILL.md` 指令声明。
- **Provider Cart (数据与执行卡带)**：如对接 OKX, Binance, 或 DeFi (Hyperliquid) 的纯通道连接器。

### 2.3 宿主引擎层：Runner
负责将各类 Cartridges（卡带）组合在一起并提供物理运行保障的执行底座（Console）。
- **CTS (Crypto Trading Station)**：ATS 生态官方首发且自带的针对数字货币交易环境高度特化的主机 Runner。它负责极速读取行情 WebSocket，将其转译为 TSP 结构喂给卡带，并将卡带回传的信号送往交易所。

---

## 3. 运行模式：Agent 的范式转移

在 ATS 中，大模型 AI 挣脱了微观时序数据的束缚（解决高 Token 与高延迟痼疾）：
- **零消耗执行**：底层的高频 K 线监控、毫秒级网格摊薄，全由无情的 Cartridge 卡带代码接管。
- **Agent 化身统帅 (Supervisor)**：用户的 Agent 退居二线进行“监管”。它可以根据当前宏观新闻（“美联储加息”），决定调用 Runner 的接口**拔出**当前的 `震荡网格.Cart`，**插入**一张最新的 `空头趋势.Cart`。

---

## 4. 商业化闭环：MaaS (Model-as-a-Service) 与云端协同

ATS 生态不仅仅是开源架构，更是全新的商业分润网络。

### 4.1 云端节点与 MCP
CTS Runner 可以作为高可用微服务部署在 AWS 东京（靠近交易所机房）。它向用户的 Agent (如 Claude Desktop) 提供标准的 MCP 接口。

### 4.2 策略即服务 (Strategy-as-a-Service)
- **开发者保护**：顶尖策略师将算法卡带部署在云端并设为私密，避免源代码被窃取。
- **订阅与调用分成**：用户的 Agent 通过 MCP Token 调用该云端卡带获取“决策咨询”或“授权代理下单”。Runner 底层清算每次调用的 Token 或记录产生盈利，自动完成**开发者**、**平台方**与**用户**间的高效分润。

打造量化领域的 **App Store** —— 让算法极客变现，让无代码用户赚钱，是 ATS 永恒的使命。
