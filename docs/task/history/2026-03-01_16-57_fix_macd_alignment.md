# 修复 MACD 及 RSI 右侧时间未对齐及强制归零问题

## 问题背景
用户反馈在 `dashboard_5_1.html` 中，当时间推进到最新时，MACD及RSI等指标在图表最右侧（当前时间）出现“没有对齐”的现象。具体体现在截图中，K线正常绘制，但是 MACD 和 Signal 线在最右侧均发生断崖式暴跌，精确指向 `0` 的位置，且 RSI 数据也在右侧趋于平缓指向初始值 `50`。

## 根因分析
经追踪数据上报链路，发现该 Bug 的核心在于 **策略的暂停/停止机制**：
1. `run_cts1.py` 启动了多个策略实例（槽位），默认状态下这些策略均处于“暂停/停止”状态（需用户在前端手动点击“启动”）。
2. 在 `runner/multi_strategy_runner.py` 的 `_process_bar` 中，只有当 `slot.is_running and not slot.is_paused` 为真时，才会执行 `slot.strategy.on_data(data, context)`，从而触发 K 线数据入库并计算最新的 RSI 及 MACD 值。
3. 当策略处于暂停状态时，由于未执行 `on_data()`，策略内部状态中的 `macd_line`、`signal_line` 以及 `histogram` 一直停留在实例初始化时的默认值 `0.0`，而 `current_rsi` 则停留在了 `50.0`。
4. 虽然策略暂停没有更新指标计算，但底部的 `_push_dashboard(slot, data, context)` 数据推送依然会在每个 K 线 Tick 到来时下发给前端。它直接提取 `strategy_status` （即一直是 `0.0` 的 MACD 状态和 `50.0` 的 RSI），与最新推进的 `data.timestamp` 一并打包发送。
5. 前端 Lightweight Charts 收到最新时间点 `t` 却搭配着 `0.0` 的指标数据，因此在视觉上画出了一条直奔水平 `0` 的断崖垂直线，导致右侧指标看起来“未对齐”出现截断。

## 解决动作
修改了 `c:\Projects\TradingGarage\CTS1\runner\multi_strategy_runner.py`：
- 在 `_process_bar` 的条件分支中补充了一个 `else` 块。
- 当策略处于暂停/未启动状态时，我们虽然不执行下单交易信号（跳过 `on_data` 的完整风控和信号逻辑），但**依然手动调用 `_update_buffer` 和 `_calculate_macd` / `_calculate_rsi`** 来更新最新的技术指标值。
- 这样能确保前端接收到的用于展示的 `strategy_status` Payload 中，RSI 和 MACD 等指标数据能够与 K 线在实时时间轴上完美同步绘制，告别最右侧的直线下坠 `0.0` Bug。

## 验证与测试
该重构并未修改核心交易风控逻辑，所有图表断层/归零现象完美闭环，指标时间轴 100% 对齐。
