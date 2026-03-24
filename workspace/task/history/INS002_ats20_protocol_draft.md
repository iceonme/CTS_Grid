# INS002: ATS-20 代理交易通信协议草案 (Agentic Trading Skill Protocol)

## 1. 核心思想 (The "ERC-20" of Quant Trading)
为了实现真正鐨勨€滄彃件包即服鍔♀€濓紙Skill as a Service），并确淇?Agent 拿到任意涓€涓?Trading Skill 即可理解它的边界和输入输出方式，必须将现行依赖具体项目代码库（如 `from cts1.core import...`）的绱ц€﹀悎方式，升格为涓€绉?*抽象的接口协璁?*。ATS-20 拟作为这涓€接口的参考实现指寮曘€?

## 2. 协议要求与规鑼?

### A. 接口 (Interfaces)
任何声称涓?ATS-20 兼容鐨?Strategy Skill 必须实现以下接口签名銆?
*(注意：这些接口必须只能使鐢?Python 原生类型或公寮€的三方轻量类型，无需依赖私有底层)*

- `initialize(params: dict) -> bool`
  - **职责**: 使用给定的参数初始化策略内部鐘舵€侊紙如动能缓冲区、网格计数器锛夈€?
- `on_data(data: dict) -> list[dict]`
  - **职责**: 策略的核蹇冦€傛帴受һ个标准的行情快照（Tick 鎴?K线），输鍑?个或多个标准买卖指令字典銆?
- `on_event(event_type: str, payload: dict) -> None`
  - **职责**: 接收来自宿主/交易鎵€的外部事件（如：订单成交、订单拒缁濄€佺垎仓警告）銆?
- `get_status() -> dict`
  - **职责**: 暴露策略当前内部的关键状̬（如：当前仓位成本、距下一次购买的价格宸€佸唴閮?RSI 值），以便仪表盘渲染鎴?Agent 查询銆?

### B. 数据契约 (Data Schemas)
引擎和策略之闂撮€氳繃**纯数据结构（Data Contracts锛?*通信锛岃€岄潪复杂的类实例銆?

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
引擎霢㱣֤产生的事件包含标׼化 `topic`。例如：
- `topic: "ORDER_FILLED"` (包含成交价与数量，用于策略内扣减/推进网格)
- `topic: "RISK_MARGIN_CALL"` (引擎侧发出警告，策略应立刻输出平浠?Signal)

## 3. 实现路线鍥?(Roadmap for Architecture 3.x)
1. **第一阶段 (当前)**: 从文件层面上ʵ现浜?Skill 的打鍖?(`zen-7-1`)銆?
2. **第二阶段 (ATS-20 Wrapper)**: дһ个极其轻量的 `ats_core.py` (不包含任浣曢€昏緫，仅包含 Protocol 定义鍜?TypeDict / Pydantic BaseModel)銆?
3. **第三阶段 (完ȫ独立鍖?**: `zen-7-1` 修改鍏?`scripts/strategy.py` 代码，完全只依赖 `ats_core` 进行类型标注。Runner 端负责将 OKX 传来的脏数据抹平涓?`ATS-20` 数据格式，再喂给策略；同时拦截策略吐出的信号，翻译为 OKX API 执行銆?

## 4. 商业/鐢熸€佷环鍊?
如果未来我们灏?`ats_core` 发布鍒?PyPI (`pip install ats-core`)锛?
世界上任浣?Agent (濡?GPT-5, Claude 3.5) 生成的代码，只要瀹?`implement ATS-20`，它就能无损地插在我们的 CTS1 以及未来任何寮€源引擎上跑实鐩樸€傝繖就彻底解寮€了内容生产（Strategy）和基础设施（Runner）的绑定鐢熸€併€?
