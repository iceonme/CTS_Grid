# 致命 Bug 修复：_update_data 5 分钟 K 线去重

V6.0 (`grid_mtf_6_0.py`) 和 V6.5 (`grid_mtf_6_5.py`) 的 `_update_data` 方法存在致命缺陷，导致所有指标计算基础错误。

## 问题描述

`OKXDataFeed.stream()` 每 **2 秒**轮询一次 OKX 接口，返回当前正在形成的 5 分钟 K 线的实时快照。但 `_update_data` 每次调用都直接 `self._data_5m.append(data)`，将每个 2 秒快照都当作一条新的 K 线记录参与后续计算。

一根 5 分钟 K 线的生命周期内，策略被调用约 **150 次** (300 秒 / 2 秒)。`_data_5m` 存储的实际上是 2 秒快照而非 5 分钟 K 线。

## 影响范围

| 组件 | 设计意图 | 实际行为（修复前） |
|------|----------|-------------------|
| RSI(14) | 基于 14 根 5m K线 = 70 分钟 | 14 个 2 秒快照 = **28 秒** |
| ATR(14) | 70 分钟波动率 | 28 秒波动率 |
| MACD(12,26,9) | 15m 趋势过滤 | 噪声信号 |
| Pivot window=10 | 前后 50 分钟确认 | 前后 **20 秒** |
| 买卖信号 | 每根 K 线最多触发一次 | 同一根 K 线内触发约 150 次 |

直接导致：
- **V6.5 每笔交易亏损** — 同一根 K 线内 RSI 微小抖动即触发买入并立刻卖出，扣费即亏
- **Pivot 点始终扎堆** — window_size 实际只覆盖 20 秒，无法识别结构
- **交易频率异常** — 大量无效买卖信号

## 修复方案

在 `_update_data` 中按 **5 分钟取整时间戳**判断：
- 同一个 5 分钟周期 → **更新**最后一条记录 (保留 open，更新 high/low/close，**volume 直接覆盖**而非累加)
- 新的 5 分钟周期 → **追加**新记录

**注：Volume 计算修正**
OKX 返回的是单根 K 线的累计成交量，因此 5m K 线的 volume 只需要直接覆盖更新为 `data.volume`。对于 15m K 线，其 volume 由当前 15m 周期内所属的 5m 记录的 volume 总和构成。

前端价格仍然每 2 秒刷新，不受影响。

## 同期修复

- **Pivot 选点策略**：从"按绝对价格取极值"改为"按时间取最近 N 个结构转折点"
- **Pivot window_size**：从 5 增大到 10（修复后 = 50 分钟确认窗口）
- **数据缓存**：`_data_5m` maxlen 从 200 扩至 400（约 33 小时完整日结构）

## 文件变更清单

- [grid_mtf_6_0.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_0.py) — `_update_data`, `_find_pivot_points`
- [grid_mtf_6_5.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_5.py) — `_update_data`, `_find_pivot_points`
- [grid_mtf_6_5_doge.py](file:///c:/CS/grid_multi/strategies/grid_mtf_6_5_doge.py) — `_update_data`, `_find_pivot_points`
