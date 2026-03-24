# 验收文档：图表时间轴对齐与标准化 (Build-015)

## 变更总结
解决了 Dashboard 中 RSI 图表和资产曲线图表在页面刷新后与 K 线图表起始点对齐失败、时区错位的问题。

### 1. 时间戳全链路标准化
- **后端 (`run_live_grid.py`)**: 
    - 废弃了 ISO 字符串格式，全链路统一使用 **Unix 毫秒整数**。
    - 无论是在 `warmup` 阶段还是实时 `on_tick` 推送，始终确保 `t` 为整数。
- **前端 (`dashboard.html`)**:
    - 简化了 `convertTime` 函数，专注于解析毫秒级整数，消除了因日期字符串解析导致的时区跳变。

### 2. 补全图表预热数据 (History Alignment)
- 修改了 `warmup` 逻辑，在推送历史 K 线的同时，生成对应长度的 `history_rsi` 和 `history_equity` 锚点数据。
- 确保三个图表具有相同的起始时间参考，从而实现 X 轴（时间轴）的完美对齐。

### 3. 前端逻辑优化
- 优化了 Socket 接收历史数据后的渲染顺序。
- 实现了初始资金参考线在历史加载后立即同步，不再依赖第一个实时点。

## 验证结论
- **时间轴对齐**: 所有图表现在从相同的历史时间点开始。
- **稳定性**: 统一为数值戳后，消除了 `new Date()` 带来的潜在解析错误。
- **视觉一致性**: 实时更新点在三张图中保持严格垂直对齐。

render_diffs(file:///c:/Projects/CTS1/run_live_grid.py)
render_diffs(file:///c:/Projects/CTS1/templates/dashboard.html)
