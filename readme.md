# CTS1 - Grid RSI Trading System (Refactored)

鍔ㄦ€佺綉鏍?+ RSI 绛栫暐浜ゆ槗绯荤粺 - 閲嶆瀯鐗?

## 馃彈锔?鏋舵瀯璁捐

### 鍒嗗眰鏋舵瀯

```
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 搴旂敤灞?(Applications)                                   鈹?
鈹? 鈹溾攢鈹€ main.py              # 缁熶竴鍏ュ彛                     鈹?
鈹? 鈹溾攢鈹€ run_backtest.py      # 鍥炴祴鍏ュ彛                     鈹?
鈹? 鈹溾攢鈹€ run_paper.py         # 妯℃嫙鐩樺叆鍙?                  鈹?
鈹? 鈹斺攢鈹€ run_live.py          # 瀹炵洏鍏ュ彛                     鈹?
鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 寮曟搸灞?(Engines)                                        鈹?
鈹? 鈹溾攢鈹€ backtest.py          # 鍥炴祴寮曟搸锛堜簨浠堕┍鍔級          鈹?
鈹? 鈹斺攢鈹€ live.py              # 瀹炵洏寮曟搸                     鈹?
鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 绛栫暐灞?(Strategies)  鈫?绾€昏緫锛屾棤鐘舵€侊紝鍙緭鍑轰俊鍙?       鈹?
鈹? 鈹溾攢鈹€ base.py              # 绛栫暐鍩虹被                     鈹?
鈹? 鈹斺攢鈹€ grid_rsi.py          # 缃戞牸RSI绛栫暐                  鈹?
鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 鎵ц灞?(Execution)                                      鈹?
鈹? 鈹溾攢鈹€ base.py              # 鎵ц鍣ㄥ熀绫?                  鈹?
鈹? 鈹溾攢鈹€ paper.py             # 妯℃嫙鎵ц                     鈹?
鈹? 鈹斺攢鈹€ okx.py               # OKX鐪熷疄鎵ц                  鈹?
鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 鏁版嵁灞?(Data)                                           鈹?
鈹? 鈹溾攢鈹€ base.py              # 鏁版嵁鎺ュ彛                     鈹?
鈹? 鈹溾攢鈹€ csv_feed.py          # CSV鍘嗗彶鏁版嵁                  鈹?
鈹? 鈹斺攢鈹€ okx_feed.py          # OKX瀹炴椂鏁版嵁                  鈹?
鈹溾攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹? 鏍稿績灞?(Core)                                           鈹?
鈹? 鈹斺攢鈹€ types.py             # 鍏变韩鏁版嵁绫诲瀷                 鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

## 馃殌 蹇€熷紑濮?

### 1. 瀹夎渚濊禆

```bash
pip install pandas numpy flask flask-socketio requests
```

### 2. 杩愯鍥炴祴

```bash
python main.py backtest --data btc_1m.csv --capital 10000
```

鎴栫洿鎺ヤ娇鐢細

```bash
python run_backtest.py --data btc_1m.csv
```

### 3. 杩愯妯℃嫙鐩橈紙甯?Dashboard锛?

```bash
python main.py paper --data btc_1m.csv --port 5000
```

鐒跺悗璁块棶 http://localhost:5000

### 4. 杩愯 OKX 妯℃嫙鐩?

```bash
export OKX_API_KEY="your_key"
export OKX_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

python main.py live --demo
```

## 馃З 妯″潡璇存槑

### 绛栫暐灞?(Strategies)

绛栫暐鍙礋璐?*杈撳嚭淇″彿**锛屼笉鍏冲績濡備綍鎵ц銆?

```python
from strategies import GridRSIStrategy
from core import MarketData, StrategyContext

strategy = GridRSIStrategy(symbol="BTC-USDT", grid_levels=10)

# 鍦ㄥ洖娴?瀹炵洏寮曟搸涓嚜鍔ㄨ皟鐢?
for data in market_feed:
    context = engine.get_context()  # 寮曟搸鎻愪緵褰撳墠璐︽埛鐘舵€?
    signals = strategy.on_data(data, context)  # 绛栫暐杈撳嚭淇″彿
    for signal in signals:
        engine.execute(signal)  # 寮曟搸鎵ц淇″彿
```

### 鎵ц灞?(Executors)

缁熶竴鎺ュ彛锛屾敮鎸佹ā鎷熸墽琛屽拰鐪熷疄浜ゆ槗鏃犵紳鍒囨崲銆?

```python
from executors import PaperExecutor, OKXExecutor

# 妯℃嫙鎵ц
executor = PaperExecutor(
    initial_capital=10000,
    fee_rate=0.001,
    slippage_model='adaptive'
)

# 鐪熷疄鎵ц锛圤KX锛?
executor = OKXExecutor(
    api_key="xxx",
    api_secret="xxx",
    passphrase="xxx",
    is_demo=True  # 妯℃嫙鐩?
)
```

### 鏁版嵁灞?(DataFeeds)

```python
from datafeeds import CSVDataFeed, OKXDataFeed

# CSV 鍘嗗彶鏁版嵁
feed = CSVDataFeed(filepath="btc_1m.csv", symbol="BTC-USDT")

# OKX 瀹炴椂鏁版嵁
feed = OKXDataFeed(
    symbol="BTC-USDT",
    timeframe="1m",
    api_key="xxx",
    api_secret="xxx",
    passphrase="xxx"
)
```

### 寮曟搸灞?(Engines)

```python
from engines import BacktestEngine, LiveEngine

# 鍥炴祴寮曟搸
engine = BacktestEngine(
    strategy=strategy,
    executor=executor,
    initial_capital=10000
)
results = engine.run(data_feed)

# 瀹炵洏寮曟搸
engine = LiveEngine(
    strategy=strategy,
    executor=executor,
    data_feed=feed
)
engine.run()
```

## 馃И 鍗曞厓娴嬭瘯

```bash
python -m pytest tests/test_strategy.py -v
```

## 馃搳 Dashboard

鍚姩鍚庤闂?http://localhost:5000

瀹炴椂鐩戞帶锛?
- 浠锋牸璧板娍
- 璧勪骇鏇茬嚎
- 鎸佷粨鐘舵€?
- 浜ゆ槗璁板綍

## 馃敡 绛栫暐鍙傛暟

```python
strategy = GridRSIStrategy(
    symbol="BTC-USDT",
    # 缃戞牸鍙傛暟
    grid_levels=10,
    grid_refresh_period=100,
    grid_buffer_pct=0.1,
    # RSI 鍙傛暟
    rsi_period=14,
    rsi_oversold=35,
    rsi_overbought=65,
    adaptive_rsi=True,
    # 浠撲綅鍙傛暟
    base_position_pct=0.1,
    max_positions=5,
    use_kelly_sizing=True,
    # 姝㈡崯鍙傛暟
    stop_loss_pct=0.05,
    trailing_stop=True,
)
```

## 馃搧 鐩綍缁撴瀯

```
cts1/
鈹溾攢鈹€ core/                   # 鏍稿績绫诲瀷瀹氫箟
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹斺攢鈹€ types.py
鈹溾攢鈹€ strategies/             # 绛栫暐灞?
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ base.py
鈹?  鈹斺攢鈹€ grid_rsi.py
鈹溾攢鈹€ executors/              # 鎵ц灞?
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ base.py
鈹?  鈹溾攢鈹€ paper.py
鈹?  鈹斺攢鈹€ okx.py
鈹溾攢鈹€ datafeeds/              # 鏁版嵁灞?
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ base.py
鈹?  鈹溾攢鈹€ csv_feed.py
鈹?  鈹斺攢鈹€ okx_feed.py
鈹溾攢鈹€ engines/                # 寮曟搸灞?
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ backtest.py
鈹?  鈹斺攢鈹€ live.py
鈹溾攢鈹€ dashboard/              # 鐩戞帶闈㈡澘
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ server.py
鈹?  鈹斺攢鈹€ templates/
鈹?      鈹斺攢鈹€ dashboard.html
鈹溾攢鈹€ config/                 # 閰嶇疆
鈹?  鈹斺攢鈹€ okx_config.py
鈹溾攢鈹€ tests/                  # 娴嬭瘯
鈹?  鈹斺攢鈹€ test_strategy.py
鈹溾攢鈹€ main.py                 # 缁熶竴鍏ュ彛
鈹溾攢鈹€ run_backtest.py         # 鍥炴祴鍏ュ彛
鈹溾攢鈹€ run_paper.py            # 妯℃嫙鐩樺叆鍙?
鈹溾攢鈹€ run_live.py             # 瀹炵洏鍏ュ彛
鈹斺攢鈹€ backup/                 # 鍘熸枃浠跺浠?
```

## 馃攧 涓庡師鐗堟湰鐨勫尯鍒?

| 鐗规€?| 鍘熺増鏈?| 閲嶆瀯鐗?|
|-----|--------|--------|
| 绛栫暐鐘舵€?| 鑷淮鎶?positions/capital | 鏃犵姸鎬侊紝寮曟搸缁存姢鐪熺浉 |
| 鑱岃矗鍒嗙 | 娣锋潅 | 娓呮櫚鍒嗗眰 |
| 鍙祴璇曟€?| 闅?| 鏄擄紙绾嚱鏁板紡锛?|
| 澶氱瓥鐣ユ敮鎸?| 闅?| 鏄?|
| Skill 鍖?| 闅?| 澶╃劧鏀寔 |

## 馃摑 TODO

- [ ] WebSocket 鏁版嵁鎺ュ叆浼樺寲
- [ ] 鏇村绛栫暐瀹炵幇
- [ ] 椋庨櫓绠＄悊绯荤粺
- [ ] 瀹屾暣鐨勮鍗曠敓鍛藉懆鏈熺鐞嗭紙鎾ゅ崟銆佹敼鍗曪級
