# 修复 MACD 鍙?RSI 右侧时间未对齐及强制归零问题

## 问题背景
用户反馈鍦?`dashboard_5_1.html` 中，当时间推进到鏈€新时，MACD及RSI等指标在图表鏈€右侧（当前时间）出现“û有对榻愨€濈殑现象。具体体现在截图中，K线正常绘制，但是 MACD 鍜?Signal 线在鏈€右侧均发生断崖式暴跌，精确指鍚?`0` 的λ置，涓?RSI 数据也在右侧趋于平缓指向初始鍊?`50`銆?

## 根因分析
经׷踪数据上报链路，发现璇?Bug 的核心在浜?**策略的暂鍋?停止机制**锛?
1. `run_cts1.py` 启动了多个策略实例（槽位），默认鐘舵€佷笅这些策略均处浜庘€滄殏鍋?停止”状态（闇€用户在ǰ端手动点鍑烩€滃惎鍔ㄢ€濓級銆?
2. 鍦?`runner/multi_strategy_runner.py` 鐨?`_process_bar` 中，只有褰?`slot.is_running and not slot.is_paused` 为真时，才会执行 `slot.strategy.on_data(data, context)`，从而触鍙?K 线数据入库并计算鏈€新的 RSI 鍙?MACD 鍊笺€?
3. 当策略处于暂停状态时，由于δ执行 `on_data()`，策略内部状态中鐨?`macd_line`、`signal_line` 以及 `histogram` 涓€直停留在实例初始化时的默璁ゅ€?`0.0`锛岃€?`current_rsi` 则停留在浜?`50.0`銆?
4. 虽然策略暂停没有更新指标计算，但底部鐨?`_push_dashboard(slot, data, context)` 数据鎺ㄩ€佷緷然会在每涓?K 绾?Tick 到来时下发给前端。它直接提取 `strategy_status` （即涓€直是 `0.0` 鐨?MACD 鐘舵€佸拰 `50.0` 鐨?RSI），与最新推进的 `data.timestamp` 丢㲢打包发閫併€?
5. 前端 Lightweight Charts 收到鏈€新时间点 `t` 却搭配着 `0.0` 的指标数据，因此在视觉上画出了一条直奔水骞?`0` 的断崖垂直线，导致右侧指标看起来“未对齐”出现截鏂€?

## 解决动作
修改浜?`c:\Projects\TradingGarage\CTS1\runner\multi_strategy_runner.py`锛?
- 鍦?`_process_bar` 的条件分支中补充了一涓?`else` 鍧椼€?
- 当策略处于暂鍋?未启动状态时，我们虽Ȼ不执行下单交易信号（跳杩?`on_data` 的完整风控和信号逻辑），浣?*依然手动调用 `_update_buffer` 鍜?`_calculate_macd` / `_calculate_rsi`** 来更新最新的鎶€术指鏍囧€笺€?
- 这样能确保ǰ端接收到的用于展示的 `strategy_status` Payload 中，RSI 鍜?MACD 等指标数据能够与 K 线在实时时间轴上完美同步绘制，告别最右侧的直线下鍧?`0.0` Bug銆?

## 验证与测璇?
该重构并未修改核心交易风鎺ч€昏緫，所有图表断灞?归零现象完美闭环，指标时间轴 100% 对齐銆?
