# 验收文档 - 2026-02-23 23:17

## 修复: Dashboard 图表刷新报错 (Value is null) — 根因修复

### 根因分析

上一轮修复（`isFinite` 校验 + `update` 方式）未生效。经深入分析发现：

**真正根因是 `history_candles` 列表中存在重复时间戳。`lightweight-charts` 的 `setData()` 要求时间序列严格递增，重复时间戳直接导致库内部坐标计算崩溃，抛出 `Value is null`。**

重复时间戳的来源：
1. **后端累积逻辑缺陷**：`dashboard.py` 每收到一个 tick 就无条件 `append` candle 到 `history_candles`，但同一分钟内 tick 频率远高于 K 线周期，导致数百个相同时间戳的 candle 被堆积。
2. **连接时双重发送**：`handle_connect` 先发 `history_update` 事件（含 candles），马上又发 `update` 事件（也含 `history_candles`），前端对同一批数据做了两次 `setData`。

### 修复内容

| 层级 | 文件 | 修复内容 |
|------|------|----------|
| 后端 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | `history_candles` 按时间戳去重：若最后一根 K 线时间戳相同则替换而非追加 |
| 后端 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | `handle_connect` 去掉 `history_update` 事件双发，只发一个 `update` |
| 前端 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | `updateChart` 批量加载前用 `Map` 按时间戳去重，确保传给 `setData` 的数据严格递增 |
| 前端 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | 单根更新使用 `series.update()` 增量方式 |
| 前端 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | RSI 参考线时间戳 `Math.floor` 取整 |
| 前端 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | 版本号更新为 `Build-003`（可验证浏览器加载了最新代码） |

### 验证方式

请重启 `run_live_grid.py` 并刷新浏览器页面：
- 控制台应输出 `版本验证: 2026-02-23-Build-003`
- 不应再出现 `Uncaught Error: Value is null`
- K 线图和 RSI 图应正常实时跳动
