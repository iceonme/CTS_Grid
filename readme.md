# CTS1 - Grid RSI Trading System (Refactored)

动态网格 + RSI 策略交易系统 - 重构版

## 🏗 架构设计

### 分层架构

```
┌──────────────────────────────────────────────────────────┐
│ 应用层 (Applications)                                   │
│ ├── main.py              # 统一入口                     │
│ ├── run_backtest.py      # 回测入口                     │
│ ├── run_paper.py         # 模拟盘入口                   │
│ └── run_live.py          # 实盘入口                     │
├──────────────────────────────────────────────────────────┤
│ 引擎层 (Engines)                                        │
│ ├── backtest.py          # 回测引擎（事件驱动）          │
│ └── live.py              # 实盘引擎                     │
├──────────────────────────────────────────────────────────┤
│ 策略层 (Strategies)  → 纯逻辑，无状态，只输出信号       │
│ ├── base.py              # 策略基类                     │
│ └── grid_rsi.py          # 网格RSI策略                  │
├──────────────────────────────────────────────────────────┤
│ 执行层 (Execution)                                      │
│ ├── base.py              # 执行器基类                   │
│ ├── paper.py             # 模拟执行                     │
│ └── okx.py               # OKX真实执行                  │
├──────────────────────────────────────────────────────────┤
│ 数据层 (Data)                                           │
│ ├── base.py              # 数据接口                     │
│ ├── csv_feed.py          # CSV历史数据                  │
│ └── okx_feed.py          # OKX实时数据                  │
├──────────────────────────────────────────────────────────┤
│ 核心层 (Core)                                           │
│ └── types.py             # 共享数据类型                 │
└──────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy flask flask-socketio requests
```

### 2. 运行回测

```bash
python main.py backtest --data btc_1m.csv --capital 10000
```

或直接使用：

```bash
python run_backtest.py --data btc_1m.csv
```

### 3. 运行模拟盘（带 Dashboard）

```bash
python main.py paper --data btc_1m.csv --port 5000
```

然后访问 http://localhost:5000

### 4. 运行 OKX 模拟盘

```bash
export OKX_API_KEY="your_key"
export OKX_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

python main.py live --demo
```

## 🧩 模块说明

### 策略层 (Strategies)

策略只负责**输出信号**，不关心如何执行。

```python
from strategies import GridRSIStrategy
from core import MarketData, StrategyContext

strategy = GridRSIStrategy(symbol="BTC-USDT", grid_levels=10)

# 在回测/实盘引擎中自动调用
for data in market_feed:
    context = engine.get_context()  # 引擎提供当前账户状态
    signals = strategy.on_data(data, context)  # 策略输出信号
    for signal in signals:
        engine.execute(signal)  # 引擎执行信号
```

### 执行层 (Executors)

统一接口，支持模拟执行和真实交易无缝切换。

```python
from executors import PaperExecutor, OKXExecutor

# 模拟执行
executor = PaperExecutor(
    initial_capital=10000,
    fee_rate=0.001,
    slippage_model='adaptive'
)

# 真实执行（OKX）
executor = OKXExecutor(
    api_key="xxx",
    api_secret="xxx",
    passphrase="xxx",
    is_demo=True  # 模拟盘
)
```

### 数据层 (DataFeeds)

```python
from datafeeds import CSVDataFeed, OKXDataFeed

# CSV 历史数据
feed = CSVDataFeed(filepath="btc_1m.csv", symbol="BTC-USDT")

# OKX 实时数据
feed = OKXDataFeed(
    symbol="BTC-USDT",
    timeframe="1m",
    api_key="xxx",
    api_secret="xxx",
    passphrase="xxx"
)
```

### 引擎层 (Engines)

```python
from engines import BacktestEngine, LiveEngine

# 回测引擎
engine = BacktestEngine(
    strategy=strategy,
    executor=executor,
    initial_capital=10000
)
results = engine.run(data_feed)

# 实盘引擎
engine = LiveEngine(
    strategy=strategy,
    executor=executor,
    data_feed=feed
)
engine.run()
```

## 🧪 单元测试

```bash
python -m pytest tests/test_strategy.py -v
```

## 📊 Dashboard

启动后访问 http://localhost:5000

实时监控：
- 价格走势
- 资产曲线
- 持仓状态
- 交易记录

## 🔧 策略参数

```python
strategy = GridRSIStrategy(
    symbol="BTC-USDT",
    # 网格参数
    grid_levels=10,
    grid_refresh_period=100,
    grid_buffer_pct=0.1,
    # RSI 参数
    rsi_period=14,
    rsi_oversold=35,
    rsi_overbought=65,
    adaptive_rsi=True,
    # 仓位参数
    base_position_pct=0.1,
    max_positions=5,
    use_kelly_sizing=True,
    # 止损参数
    stop_loss_pct=0.05,
    trailing_stop=True,
)
```

## 📁 目录结构

```
cts1/
├── core/                   # 核心类型定义
│   ├── __init__.py
│   └── types.py
├── strategies/             # 策略层
│   ├── __init__.py
│   ├── base.py
│   └── grid_rsi.py
├── executors/              # 执行层
│   ├── __init__.py
│   ├── base.py
│   ├── paper.py
│   └── okx.py
├── datafeeds/              # 数据层
│   ├── __init__.py
│   ├── base.py
│   ├── csv_feed.py
│   └── okx_feed.py
├── engines/                # 引擎层
│   ├── __init__.py
│   ├── backtest.py
│   └── live.py
├── dashboard/              # 监控面板
│   ├── __init__.py
│   ├── server.py
│   └── templates/
│       └── dashboard.html
├── config/                 # 配置
│   └── okx_config.py
├── tests/                  # 测试
│   └── test_strategy.py
├── main.py                 # 统一入口
├── run_backtest.py         # 回测入口
├── run_paper.py            # 模拟盘入口
├── run_live.py             # 实盘入口
└── backup/                 # 原文件备份
```

## 🔄 与原版本的区别

| 特性 | 原版本 | 重构版 |
|-----|--------|--------|
| 策略状态 | 自维护 positions/capital | 无状态，引擎维护真相 |
| 职责分离 | 混杂 | 清晰分层 |
| 可测试性 | 难 | 易（纯函数式） |
| 多策略支持 | 难 | 是 |
| Skill 化 | 难 | 天然支持 |

## 📝 TODO

- [ ] WebSocket 数据接入优化
- [ ] 更多策略实现
- [ ] 风险管理系统
- [ ] 完整的订单生命周期管理（撤单、改单）
