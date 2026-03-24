# 致命 Bug 修复：_update_data 5 分钟 K 线去閲?

V6.0 (`grid_mtf_6_0.py`) 鍜?V6.5 (`grid_mtf_6_5.py`) 鐨?`_update_data` 方法存在致命缺陷，导致所有ָ标计算基纭€错误銆?

## 问题描述

`OKXDataFeed.stream()` 姣?**2 绉?*轮询涓€娆?OKX 接口，返回当前正在形成的 5 分钟 K 线的实ʱ快照。但 `_update_data` 每次调用都直鎺?`self._data_5m.append(data)`，将每个 2 秒快照都当作涓€条新鐨?K 线记录参与后续计绠椼€?

涓€鏍?5 分钟 K 线的生命周期内，策略被调用约 **150 娆?* (300 绉?/ 2 绉?。`_data_5m` 存储的实际上鏄?2 秒快鐓ц€岄潪 5 分钟 K 绾裤€?

## 影响范围

| 组件 | 设计意图 | 实际行为（修复前锛?|
|------|----------|-------------------|
| RSI(14) | 基于 14 鏍?5m K绾?= 70 分钟 | 14 涓?2 秒快鐓?= **28 绉?* |
| ATR(14) | 70 分钟波动鐜?| 28 秒波动率 |
| MACD(12,26,9) | 15m 趋势过滤 | 噪声信号 |
| Pivot window=10 | 前后 50 分钟确认 | 前后 **20 绉?* |
| 买卖信号 | 每根 K 线最多触发一娆?| 同一鏍?K 线内触发绾?150 娆?|

直接导致锛?
- **V6.5 每笔交易亏损** 鈥?同一鏍?K 线内 RSI 微小抖动即触发买入并立刻卖出，扣费即浜?
- **Pivot 点始终扎鍫?* 鈥?window_size 实际只覆鐩?20 秒，无法识别结构
- **交易频率异常** 鈥?大量无效买卖信号

## 修复方案

鍦?`_update_data` 中按 **5 分钟取整时间鎴?*判断锛?
- 同一涓?5 分钟周期 鈫?**更新**鏈€后һ条记褰?(保留 open，更鏂?high/low/close锛?*volume 直接覆盖**而非累加)
- 新的 5 分钟周期 鈫?**追加**新记褰?

**注：Volume 计算修正**
OKX 返回的是单根 K 线的累计成交量，因此 5m K 线的 volume 只需要ֱ接覆盖更新为 `data.volume`。对浜?15m K 线，鍏?volume 由当鍓?15m 周期内所属的 5m 记录鐨?volume 总和构成銆?

前端价格仍然姣?2 秒刷新，不受影响銆?

## 同期修复

- **Pivot 选点策略**：从"按绝对价格取鏋佸€?改为"按时间取鏈€杩?N 个结构转折点"
- **Pivot window_size**：从 5 增大鍒?10（修复后 = 50 分钟确认窗口锛?
- **数据缓存**：`_data_5m` maxlen 浠?200 扩至 400（约 33 小时完整日结构）

## 文件变更清单

- [grid_mtf_6_0.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_0.py) 鈥?`_update_data`, `_find_pivot_points`
- [grid_mtf_6_5.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_5.py) 鈥?`_update_data`, `_find_pivot_points`
- [grid_mtf_6_5_doge.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_5_doge.py) 鈥?`_update_data`, `_find_pivot_points`
