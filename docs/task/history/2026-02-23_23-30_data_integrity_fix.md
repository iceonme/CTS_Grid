# 验收文档 - 2026-02-23 23:30

## 全面审查并修复数据完整性问题

### 问题描述
Dashboard K 线图数据不连续、出现间断。经全链路代码审查，发现多处数据类型不一致和遗漏问题。

### 全链路修复清单

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | 轮询间隔 60s，每分钟才更新一次 | 缩短至 2s，实现近实时效果 |
| 2 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | `stream_ohlcv` 传递 `symbol` 字符串混入 DataFrame 导致数值列异常 | 移除 `symbol` 字段 |
| 3 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | `get_candles` 返回额外列 (`volCcy`, `confirm` 等)，与 tick 数据列不一致 | 只保留 OHLCV 五列 |
| 4 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | timestamp 传 `pd.Timestamp` 对象，后续处理不一致 | 统一传毫秒整数 |
| 5 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | `on_tick` 用毫秒整数做索引，与 warmup 的 `pd.Timestamp` 索引冲突 | 统一转换为 `pd.Timestamp` + 去重排序 |
| 6 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | warmup 历史用 ISO 字符串，on_tick 用毫秒，时区偏移导致不连续 | 全部统一为毫秒整数 |
| 7 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | warmup 缺少 `position_value` 字段 | 补充该字段 |
| 8 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | `history_candles` 重复时间戳累积 | 同时间戳替换而非追加 |
| 9 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | 连接时双发 `history_update` + `update` | 只发一次 `update` |
| 10 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | `setData` 前未去重，`Value is null` 崩溃 | `Map` 去重 + `update()` 增量更新 |

### 验证方式
重启 `run_live_grid.py` 并刷新浏览器（确认 `Build-005`），观察：
- K 线数据从历史到实时应无间断
- 每 2 秒刷新一次最新价格
- 无报错信息
