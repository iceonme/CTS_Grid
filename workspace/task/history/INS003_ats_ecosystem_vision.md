# INS003: ATS 智能体量化交易生态术语与Ը景

## 鐢熸€佺郴统定涔?(The Ecosystem)

在这个体ϵ中，我们不再是写几行只能跑在本地的 Python 代码锛岃€屾槸构建涓€个名涓?**ATS (Agentic Trading System)** 的开源与商业大生鎬併€傚畠是一个允璁?AI Agent 鍍?*“插卡带打游鎴忊€?*涓€样，随插随用地获取ȫ自动化量化交易能力的寮€放协同环澧冦€?

## 关键术语与架构层娆?(Key Terminology)

### 1. 协议层：TSP (Trading-Skill-Protocol)
*鍦?Anthropic 鐨?`agentskills.io`（提供泛用的 Agent 对接边界）基纭€之上，专属叠加的面向金融量化交易的接口协璁€?
任何遵守 TSP 命名和数据格式规范（原暂定名 ATS-20）的项目，都能实现接口的标准化：输入标准鐨?K 线字典，吐出标׼的订单指令字鍏搞€傚畠是整个生态的“USB 接口定义标准鈥濄€?

### 2. 组件层：Trading Cartridge (Cart, 交易卡带)
*鐢熸€佷腑供流閫氥€佷笅载和安装的具体功能模块（原来鐨?Skill 包）銆?
之所以不使用模糊鐨?"Skill"锛岃€岄噰用极具辨识度鐨?**“Cartridge (卡带)鈥?* 或简绉?**Cart**，是因为它的“即插即鐢ㄢ€濆拰“硬件模块化”隐喻最为贴鍒囥€傚紑鍙戣€呬滑可以自由编写锛?
- **Strategy Cart (策略卡带)**：如含有交易逻辑鐨?`zen-7-1`銆?
- **Exchange/Data Cart (数据与执行卡甯?**：如用来对接行情或下单的 `okx-spot-connector`、`hyperliquid-connector`銆?
无论 Agent 拿到浠€涔?Cart，只闇€理解它的外层 `SKILL.md`，即可掌握它的具体用娉曘€?

### 3. 主机驱动层：Runner
*用来插入海量不同 Cart (卡带) 的实体机器或底层服务设施，负责硬件级交互串联，如 WebSocket 的长连接维持、本地数据库的持久化銆?
Runner 在这个生̬里如同任天堂的主机台（Console锛夈€傜敱于世界上存在各种类别的金融资产和通讯Ҫ求，Runner 闇€要高度定鍒躲€?
本生̬自带且当前演进中的核心官方示例项目，特命名为：
**CTS (Crypto Trading Station)**
*(原名 Crypto Trading Squad。更名为 Station（主机空闂?操作台），完美契合其作为 Crypto 策略卡带插槽站点的生态定浣嶃€?*

---

## 运作模式：Agent 监管涓?Token 节能 (Agent Regulation)
ATS 架构致力于将大语瑷€模型（LLM Agent，如 Claude/Cursor）与量化底层系统完美结合，解决大模型高频调用带来的高延迟与高 Token 娑堣€楀嵄机：

**运作原理锛?*
1. 量化计算如高频的价格扫描、指标运算（例如计算 RSI 和多层网格）、订单簿鐨?Tick 监测，这些对计算频次极高的脏活累活，全交给由 TSP 协议编写鐨?**Cartridge** 插在楂橀€熺殑 **Runner (CTS)** 里硬核心智运行（0 Token 娑堣€楋紝毫秒级响应）銆?
2. **Agent 转变为监绠¤€?(Supervisor/Orchestrator)**锛?
   Agent 不再是每秒钟看着价格做决策的浜恒€傚畠是那个拿鐫€扳手调整“机鍣ㄢ€濈殑浜恒€傚畠可以锛?
   - 根据当前的宏观经济报告或社交媒体情绪，动态装配或拔出某张**策略卡带**（Cart锛夈€?
   - 璁?Runner 帮它去向涓€张卡带发起一次纯数据查询推演（如 `agent_api.py` 的作用），获取建璁€?
   - 修改某张卡带背后鐨?`config.json` 去调整资金配姣斻€?

这种结构真正做到浜?*“AI 负责宏观ս略，Cartridge(代码) 负责高频ս术，Runner 负责基础设施保障鈥?* 的未来交易愿鏅€?

---

## 商业化闭环：MaaS (Model-as-a-Service) 与云绔?MCP 分成搴?
灏?ATS 鐢熸€佸欢伸到云端，可以彻底打閫?*“策略即服务 (Strategy-as-a-Service)鈥?*的商业闭鐜€?

**云端 Runner 架构体系锛?*
1. **云主机托绠?(Cloud Runner)**：Runner (濡?CTS) 并不丢㶨需要部署在用户的本地电脑上。它可以作为涓€个高可用、低延迟的云端微服务节点运行，背靠顶级交易所的同机房线·（如 AWS Tokyo for Binance锛夈€?
2. **MCP (Model Context Protocol) 接口暴露**：云绔?Runner 缁?Agent 预留了标准的 MCP Server 通道。用户自己的 AI Agent（如 Claude Desktop）可浠ラ€氳繃鉴权 Token 直接向云绔?Runner 鍙戦€侀暱连接/API 指令銆?
3. **订阅付费与自动分成模鍨?*锛?
   - 寮€鍙戣€?A 写了涓€张胜率极高的策略 Cartridge（卡带），并挂载在云商的 Runner 涓娿€?
   - 玩家 B 没有弢㷢能力，但他鐨?Agent 决定“订闃呪€濆苟调用这张云端卡带提供交易建议甚至代执琛屻€?
   - runner 底层记录每一次的调用次数或最终的盈利分润，自动完成开鍙戣€?A (鎶€术提供方)、系统平鍙?(设施提供鏂? 和玩瀹?B (资金鏂? 之间的账单拆鍒嗐€?

这就是彻底解放量化交易生产力鐨?**App Store 模ʽ**，让朢㶮金融算法的人赚钱，让最懂宏观分析和提示词的浜洪€氳繃 Agent 赚取财富锛岃€?ATS 则是他们共同赖以生存的空气和土壤銆?
