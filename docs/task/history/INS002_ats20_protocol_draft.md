# INS002: ATS-20 代理交易通信协议草案 (Agentic Trading Skill Protocol)

## 1. 核心思想 (The "ERC-20" of Quant Trading)
为了实现真正的“插件包即服务”（Skill as a Service），并确保 Agent 拿到任意一个 Trading Skill 即可理解它的边界和输入输出方式，必须将现行依赖具体项目代码库（如 `from cts1.core import...`）的紧耦合方式，升格为一种**抽象的接口协议**。ATS-20 拟作为这一接口的参考实现指引。

## 2. 协议要求与规范

### A. 接口 (Interfaces)
任何声称为 ATS-20 兼容的 Strategy Skill 必须实现以下接口签名。
*(注意：这些接口必须只能使用 Python 原生类型或公开的三方轻量类型，无需依赖私有底层)*

- `initialize(params: dict) -> bool`
  - **职责**: 使用给定的参数初始化策略内部状态（如动能缓冲区、网格计数器）。
- `on_data(data: dict) -> list[dict]`
  - **职责**: 策略的核心。接受一个标准的行情快照（Tick 或 K线），输出0个或多个标准买卖指令字典。
- `on_event(event_type: str, payload: dict) -> None`
  - **职责**: 接收来自宿主/交易所的外部事件（如：订单成交、订单拒绝、爆仓警告）。
- `get_status() -> dict`
  - **职责**: 暴露策略当前内部的关键状态（如：当前仓位成本、距下一次购买的价格差、内部 RSI 值），以便仪表盘渲染或 Agent 查询。

### B. 数据契约 (Data Schemas)
引擎和策略之间通过**纯数据结构（Data Contracts）**通信，而非复杂的类实例。

**标准输入: MarketData**
```json
{
  "symbol": "BTC-USDT",
  "timestamp": 1709420000000,
  "close": 65000.50,
  "high": 65100.00,
  "low": 64900.00,
  "open": 64950.00,
  "volume": 12.5
}
```

**标准输出: Signal**
```json
{
  "skill_name": "zen-7-1",
  "symbol": "BTC-USDT",
  "side": "BUY",
  "type": "MARKET",
  "size": 0.05,
  "price": null, 
  "rationale": "RSI(25) deeply oversold & BBW expanded"
}
```

### C. 事件体系 (Events)
引擎需保证产生的事件包含标准化 `topic`。例如：
- `topic: "ORDER_FILLED"` (包含成交价与数量，用于策略内扣减/推进网格)
- `topic: "RISK_MARGIN_CALL"` (引擎侧发出警告，策略应立刻输出平仓 Signal)

## 3. 实现路线图 (Roadmap for Architecture 3.x)
1. **第一阶段 (当前)**: 从文件层面上实现了 Skill 的打包 (`zen-7-1`)。
2. **第二阶段 (ATS-20 Wrapper)**: 写一个极其轻量的 `ats_core.py` (不包含任何逻辑，仅包含 Protocol 定义和 TypeDict / Pydantic BaseModel)。
3. **第三阶段 (完全独立化)**: `zen-7-1` 修改其 `scripts/strategy.py` 代码，完全只依赖 `ats_core` 进行类型标注。Runner 端负责将 OKX 传来的脏数据抹平为 `ATS-20` 数据格式，再喂给策略；同时拦截策略吐出的信号，翻译为 OKX API 执行。

## 4. 商业/生态价值
如果未来我们将 `ats_core` 发布到 PyPI (`pip install ats-core`)：
世界上任何 Agent (如 GPT-5, Claude 3.5) 生成的代码，只要它 `implement ATS-20`，它就能无损地插在我们的 CTS1 以及未来任何开源引擎上跑实盘。这就彻底解开了内容生产（Strategy）和基础设施（Runner）的绑定生态。
