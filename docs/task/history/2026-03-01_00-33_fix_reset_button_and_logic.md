# 修复重置按钮及清理逻辑

**日期时间**: 2026-03-01 00:33

## 1. 目标
解决在策略5.1（及其他运行在多策略框架下的策略）点击“重置”按钮无反应的问题，并明确重置的语义为“清空+停止”，而非重置后默认重新启动。

## 2. 问题分析与修复方案

### 2.1 修复前端重置信号未携参问题
- **现象**：前端在点击确认重置时，仅发送了 `socket.emit('reset_strategy')`。
- **原因**：后端在多策略框架下接不到具体的 `strategy_id`，且当时未能有效Fallback到默认策略，导致控制回调未被执行。
- **解决**：修改 `dashboard.html`，发送 `socket.emit('reset_strategy', { strategy_id: currentStrategyId })`。并更新了重置确认模态框的内容，明确告知用户重置后策略将停止运行。

### 2.2 修复后端重置后的自动启动问题
- **现象**：原有逻辑下，重置意味着清空持仓和图表，并立刻继续运行。
- **原因**：`MultiStrategyRunner.reset` 方法最后一句为 `slot.start()`。
- **解决**：在 `runner/multi_strategy_runner.py` 中注释掉 `slot.start()`，让策略在重置后保持在暂停（Stopped）状态。

### 2.3 修复前端按钮状态未能同步更新的问题
- **原因**：控制端接收重置指令后，虽然重置了相关组件，但未能有效将停止状态下发至UI。
- **解决**：在 `dashboard/server.py` 的重置逻辑中增加向指定房间发送 `status: 'stopped'` 的 `strategy_status_changed` 事件，确保前端的启动/暂停按钮变为正确的状态（即：启动按钮可点击，暂停按钮置灰）。

## 3. 修改的文件

- `c:\Projects\TradingGarage\CTS1\dashboard\templates\dashboard.html`
- `c:\Projects\TradingGarage\CTS1\dashboard\server.py`
- `c:\Projects\TradingGarage\CTS1\runner\multi_strategy_runner.py`

## 4. 验证方式
1. 打开网页版 Dashboard，选择策略。
2. 启动该策略，观察控制台数据流。
3. 点击“重置”，确认弹窗信息。
4. 点击“确认重置”，观察图表是否清空，状态栏和右上角的控制按钮是否回到了“尚未运行”的状态，终端不再产生新的开仓动作。

## 5. 结论
重置按钮功能已恢复，重置语义已修正为目标设定的“清空+停止”。
