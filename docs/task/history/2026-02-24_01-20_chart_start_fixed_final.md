# 验收文档：RSI 与资产图表起始点深度修复 (Build-018)

## 最终修复方案
由于之前版本在处理 **全量快照 (Snapshot)** 和 **实时增量 (Tick)** 时存在逻辑分支冲突，导致刷新页面后 RSI 和资产曲线的显示出现异常。本次 Build-018 彻底解决了这一问题。

### 1. 彻底解决起始点偏移 (T0 对齐)
- **前端重构 (`dashboard.html`)**: 
    - 废弃了 `history_candles` 与实时点 `candle` 的 `if/else if` 互斥逻辑。现在的系统能够同时处理一条消息中的历史数据和实时最新点。
    - **逻辑增强**: 当系统检测到接收着历史 K 线（冷启动/重启）时，会主动调用 `rsiSeries.setData([])`，强制清除图表上可能存在的陈旧线条，确保持续显示是从当前时刻产生的。
- **后端持久化 (`dashboard.py`)**:
    - **缓存清理**: 当收到来自交易引擎的 `warmup` 批量数据时，`dashboard.py` 会自动清空其内部的 `history_rsi` 和 `history_equity` 缓存。
    - **实时追溯**: 此后的每一个实时 Tick 都会被后端缓存。这意味着您刷新页面后，已经产生的实时曲线会立即恢复。

### 2. 性能与稳定性
- 优化了主图网格线的绘制，仅在网格参数发生变化时重绘，避免了不必要的 DOM 消耗。
- 引入了 `prepareBatchData` 对所有历史数据进行前置去重和排序，确保 `lightweight-charts` 渲染层的稳定性。

## 版本信息
- **版本号**: V4.3
- **构建 ID**: 2026-02-24-Build-018
- **更新描述**: 彻底修复历史/实时逻辑冲突，确保起始点正确对齐 T0。

## 验证结论
- [x] 启动系统后，K 线有 200 根历史，而 RSI/资产曲线起始于第一根实时 K 线的位置。
- [x] 刷新页面，RSI/资产曲线能保留刷新前的实时部分，且不会回溯到更早的 K 线区间。
- [x] 时间轴 X 轴完全同步。

render_diffs(file:///c:/Projects/CTS1/dashboard.py)
render_diffs(file:///c:/Projects/CTS1/templates/dashboard.html)
